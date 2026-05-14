"""
crunchexports.routers_sse — the SSE relay endpoint.

GET /sse/exports/{job_id}

Subscribes to the per-job Redis Pub/Sub channel and yields each message
as a Server-Sent Event. Heartbeats every 15 seconds. Detects client
disconnect via Request.is_disconnected().

Cited:
    - https://html.spec.whatwg.org/multipage/server-sent-events.html
    - https://developer.mozilla.org/en-US/docs/Web/API/EventSource
    - https://github.com/sysid/sse-starlette
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse

from .progress import iter_messages, subscription
from .settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _sse_frame(event: str, data: str, event_id: int | None = None) -> bytes:
    """Encode one SSE frame as bytes.

    Per the HTML living standard's SSE section, each frame is a sequence
    of `name: value` lines followed by a blank line.
    """
    parts: list[str] = [f"event: {event}"]
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append(f"data: {data}")
    parts.append("")  # the blank line that terminates the frame
    parts.append("")
    return "\n".join(parts).encode("utf-8")


@router.get("/sse/exports/{job_id}")
async def stream_export_progress(job_id: str, request: Request) -> StreamingResponse:
    """Stream progress events for a job to the browser.

    The client opens with `new EventSource("/sse/exports/{id}")`; the browser
    handles reconnection. On reconnect, `Last-Event-ID` carries the last
    seen event ID; we use it to skip past events the client already saw.
    """
    settings = get_settings()
    redis = request.app.state.redis
    last_event_id_header = request.headers.get("last-event-id")
    skip_until: int = -1
    if last_event_id_header is not None:
        try:
            skip_until = int(last_event_id_header)
        except ValueError:
            skip_until = -1

    async def gen() -> AsyncIterator[bytes]:
        # Opening comment so the response body has bytes immediately.
        yield b": opening stream\n\n"

        if redis is None:
            yield _sse_frame(
                "failed",
                json.dumps({"error": "redis unavailable"}),
                event_id=0,
            )
            return

        seq = 0
        async with subscription(redis, settings.progress_channel_prefix, job_id) as pubsub:
            async for payload in iter_messages(pubsub):
                if await request.is_disconnected():
                    return

                seq += 1
                if seq <= skip_until:
                    continue

                # Classify the message and pick an event type.
                if payload.get("done"):
                    yield _sse_frame("done", json.dumps(payload), event_id=seq)
                    return
                if "error" in payload:
                    yield _sse_frame("failed", json.dumps(payload), event_id=seq)
                    return
                yield _sse_frame("progress", json.dumps(payload), event_id=seq)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
