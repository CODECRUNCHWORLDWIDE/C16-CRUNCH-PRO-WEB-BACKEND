"""
crunchexports.progress — Redis Pub/Sub helper used by both the ARQ task and
the SSE relay endpoint.

The wire shape on the channel is JSON, one object per message:

    {"step": int, "of": int, "label": str}   — progress
    {"done": true, "rows": int, "file": str} — final success
    {"error": str, "step": int}              — failure

The channel name is `{prefix}:{job_id}`.

Cited:
    - https://redis.io/docs/latest/develop/interact/pubsub/
    - https://redis-py.readthedocs.io/en/stable/advanced_features.html#publish-subscribe
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)


def channel_for(prefix: str, job_id: str) -> str:
    """Return the Pub/Sub channel name for a job."""
    return f"{prefix}:{job_id}"


async def publish_progress(
    redis: Any,
    prefix: str,
    job_id: str,
    payload: dict[str, Any],
) -> None:
    """Publish a JSON payload to the per-job channel.

    `redis` is a redis.asyncio.Redis-compatible client (ArqRedis qualifies).
    """
    channel = channel_for(prefix, job_id)
    await redis.publish(channel, json.dumps(payload))


@asynccontextmanager
async def subscription(
    redis: Any,
    prefix: str,
    job_id: str,
) -> AsyncIterator[Any]:
    """An async context manager that opens, then closes, a Pub/Sub subscription.

    Usage:

        async with subscription(redis, "job-progress", job_id) as pubsub:
            async for message in pubsub.listen():
                ...

    The cleanup unsubscribes from the channel on exit.
    """
    channel = channel_for(prefix, job_id)
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    try:
        yield pubsub
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception as exc:  # noqa: BLE001 — best-effort cleanup
            logger.warning("unsubscribe failed: %s", exc)
        try:
            await pubsub.aclose()
        except Exception as exc:  # noqa: BLE001
            logger.warning("pubsub close failed: %s", exc)


async def iter_messages(pubsub: Any) -> AsyncIterator[dict[str, Any]]:
    """Yield decoded JSON payloads from a subscription.

    Non-message events (subscribe confirmation, etc.) are skipped.
    """
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        data = message["data"]
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            logger.warning("non-JSON message dropped: %r", data)
            continue
