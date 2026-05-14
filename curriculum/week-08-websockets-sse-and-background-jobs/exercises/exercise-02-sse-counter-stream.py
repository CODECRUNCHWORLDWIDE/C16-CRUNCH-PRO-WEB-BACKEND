"""
Exercise 2 — Server-Sent Events: a counter stream and a heartbeat.

Time:   ~2 hours.
Goal:   Build a FastAPI SSE endpoint two ways: (a) by hand, using
        starlette.responses.StreamingResponse, and (b) using the
        sse-starlette helper. Confirm the wire format with `curl --no-buffer`,
        observe automatic reconnect from a browser EventSource, and resume
        an interrupted stream with the Last-Event-ID header.

Run:
    fastapi dev exercise-02-sse-counter-stream.py
    # or:
    uvicorn exercise-02-sse-counter-stream:app --reload --port 8000

Try (in another terminal):
    curl --no-buffer http://localhost:8000/sse/counter
    # Observe text/event-stream framing. Ctrl-C to stop.

    # Browser test (paste into the DevTools console of any page):
    #   const es = new EventSource("http://localhost:8000/sse/counter");
    #   es.addEventListener("tick", (e) => console.log("tick", e.data));
    #   es.addEventListener("done", () => es.close());

Cited:
    - https://html.spec.whatwg.org/multipage/server-sent-events.html
    - https://developer.mozilla.org/en-US/docs/Web/API/EventSource
    - https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
    - https://www.starlette.io/responses/#streamingresponse
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

# sse_starlette is an optional dependency for Part C. The exercise compiles
# whether or not it is installed; the runtime import is guarded.

try:
    from sse_starlette.sse import EventSourceResponse  # type: ignore[import-not-found]

    HAS_SSE_STARLETTE = True
except ImportError:  # pragma: no cover — exercised by the optional install
    EventSourceResponse = None  # type: ignore[assignment,misc]
    HAS_SSE_STARLETTE = False


app = FastAPI(
    title="C16 W8 Exercise 2 — SSE counter stream",
    description=(
        "An SSE endpoint that emits an incrementing counter every second. "
        "Demonstrates the SSE wire format, the Last-Event-ID resume header, "
        "and the comment-line heartbeat."
    ),
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Part A — A Pydantic schema for the event payload
# ---------------------------------------------------------------------------


class TickEvent(BaseModel):
    """The payload of one tick event."""

    n: int = Field(ge=0, description="The current counter value.")
    ts: str = Field(description="ISO-8601 UTC timestamp.")


# ---------------------------------------------------------------------------
# Part B — Hand-rolled SSE with StreamingResponse
# ---------------------------------------------------------------------------


def _frame(event: str, data: str, event_id: int | None = None) -> bytes:
    """Encode one SSE frame.

    Each frame is `event: <name>`, `id: <id>` (optional), `data: <data>`,
    followed by a blank line.
    """
    parts: list[str] = [f"event: {event}"]
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append(f"data: {data}")
    parts.append("")  # the blank line that terminates the frame
    parts.append("")
    return "\n".join(parts).encode("utf-8")


async def _counter_gen(start: int, limit: int, request: Request) -> AsyncIterator[bytes]:
    """Yield a tick event every second; emit a heartbeat every 5 ticks."""
    # An opening comment, so the browser sees a body byte immediately.
    yield b": opening stream\n\n"

    n = start
    while n < limit:
        # Detect client disconnect; bail out cleanly so cleanup runs.
        if await request.is_disconnected():
            return

        tick = TickEvent(n=n, ts=datetime.now(timezone.utc).isoformat())
        yield _frame("tick", tick.model_dump_json(), event_id=n)

        # A heartbeat every 5 ticks. The browser ignores it; proxies do not.
        if n % 5 == 0 and n != start:
            yield b": heartbeat\n\n"

        await asyncio.sleep(1.0)
        n += 1

    yield _frame("done", json.dumps({"final": n}), event_id=n)


@app.get("/sse/counter")
async def sse_counter(request: Request, start: int = 0, limit: int = 10) -> StreamingResponse:
    """An SSE counter stream from `start` to `limit`, one tick per second.

    TASK 1: Run `curl --no-buffer http://localhost:8000/sse/counter` and copy
    the first three frames (including blank-line terminators) into
    SOLUTIONS.md. Confirm the framing matches the HTML living standard's
    SSE section.
    """
    # Last-Event-ID lets the browser resume from where it left off after
    # an automatic reconnect. We honour it by starting from the next index.
    last_event_id = request.headers.get("last-event-id")
    if last_event_id is not None:
        try:
            start = int(last_event_id) + 1
        except ValueError:
            pass  # malformed header; ignore and use the query param

    return StreamingResponse(
        _counter_gen(start, limit, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # tells Nginx/Cloudflare not to buffer
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Part C — The same thing with sse-starlette
# ---------------------------------------------------------------------------


@app.get("/sse/counter-helper")
async def sse_counter_helper(
    request: Request,
    start: int = 0,
    limit: int = 10,
):
    """The same counter, this time using sse_starlette.EventSourceResponse.

    TASK 2: Compare the response bodies of /sse/counter and /sse/counter-helper
    side by side (with `curl --no-buffer`). Identify the differences, if any,
    in the framing. Note in SOLUTIONS.md.
    """
    if not HAS_SSE_STARLETTE:
        return {
            "error": "sse-starlette not installed",
            "hint": "pip install 'sse-starlette==2.1.*'",
        }

    last_event_id = request.headers.get("last-event-id")
    if last_event_id is not None:
        try:
            start = int(last_event_id) + 1
        except ValueError:
            pass

    async def gen() -> AsyncIterator[dict[str, str]]:
        n = start
        while n < limit:
            if await request.is_disconnected():
                return
            tick = TickEvent(n=n, ts=datetime.now(timezone.utc).isoformat())
            yield {
                "event": "tick",
                "id": str(n),
                "data": tick.model_dump_json(),
            }
            await asyncio.sleep(1.0)
            n += 1
        yield {"event": "done", "id": str(n), "data": json.dumps({"final": n})}

    # The ping argument inserts a `: ping` comment every N seconds.
    return EventSourceResponse(gen(), ping=15)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Part D — A one-shot SSE that ends after a known number of events
# ---------------------------------------------------------------------------


@app.get("/sse/burst")
async def sse_burst(request: Request, count: int = 5) -> StreamingResponse:
    """Emit `count` events as fast as possible, then a 'done' event.

    TASK 3: Why is it useful to have a 'done' event emitted by the server
    even though the browser sees the response body end? Hint: think about
    EventSource's automatic reconnect behaviour. Note in SOLUTIONS.md.
    """

    async def gen() -> AsyncIterator[bytes]:
        for i in range(count):
            if await request.is_disconnected():
                return
            yield _frame("burst", json.dumps({"i": i}), event_id=i)
        yield _frame("done", json.dumps({"count": count}), event_id=count)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Part E — A health route
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {"status": "ok", "sse_starlette": HAS_SSE_STARLETTE}


# ---------------------------------------------------------------------------
# Self-check and tests
# ---------------------------------------------------------------------------
#
# Run `python3 -m py_compile exercise-02-sse-counter-stream.py`.
#
# TASK 4: In tests/test_exercise_02.py, write a pytest-asyncio test that:
#   - opens an httpx.AsyncClient with ASGITransport(app=app)
#   - calls client.stream("GET", "/sse/burst?count=3")
#   - collects the response body chunks
#   - parses the SSE frames and asserts the event sequence
#     is ["burst", "burst", "burst", "done"]
#
# TASK 5: Browser smoke test. Open the DevTools console of any page on
# http://localhost (a blank page from `python3 -m http.server` is fine).
# Paste:
#
#   const es = new EventSource("http://localhost:8000/sse/counter?limit=3");
#   es.addEventListener("tick", (e) => console.log("tick", e.data));
#   es.addEventListener("done", (e) => { console.log("done", e.data); es.close(); });
#
# Confirm three ticks and one done show up in the console. Confirm the
# Network tab shows the response as text/event-stream with the
# EventStream pane parsing every frame.
