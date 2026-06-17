"""Invalidation bus — Redis Pub/Sub for cache invalidation events.

The write paths publish messages to a single channel; every FastAPI worker
subscribes on startup and reacts to messages by DELing the named key or
sweeping the named pattern.

The pattern is fire-and-forget. A worker that is down when a message is
published misses it forever; the cached values' TTLs are the safety net.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]


logger = logging.getLogger("crunchcache.invalidation")


class InvalidationBus:
    """Pub/Sub-backed cache invalidation.

    Usage:
        bus = InvalidationBus(redis_client, channel="crunchcache:invalidate")
        await bus.start()  # subscribes; runs the listener in the background
        await bus.publish_key("v1:article:42")
        await bus.publish_pattern("v1:articles:popular:*")
        await bus.stop()
    """

    def __init__(self, r: "redis.Redis", channel: str) -> None:
        self._r = r
        self._channel = channel
        self._listener_task: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        """Start the subscriber loop. Idempotent."""
        if self._listener_task is not None:
            return
        self._stopping = False
        self._listener_task = asyncio.create_task(self._listen_forever())

    async def stop(self) -> None:
        """Stop the subscriber loop and wait for it to exit."""
        self._stopping = True
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._listener_task = None

    async def publish_key(self, key: str) -> None:
        """Publish 'delete this single cache key' to the bus.

        TODO: Wrap json.dumps({"key": key}) into self._r.publish.
        Catch and log RedisError so an invalidation failure does not
        propagate to the write path.
        """
        raise NotImplementedError("InvalidationBus.publish_key is a TODO")

    async def publish_pattern(self, pattern: str) -> None:
        """Publish 'SCAN MATCH this pattern and DEL every match' to the bus.

        TODO: same shape as publish_key.
        """
        raise NotImplementedError("InvalidationBus.publish_pattern is a TODO")

    async def _listen_forever(self) -> None:
        """The subscriber loop. Restart on disconnect."""
        while not self._stopping:
            try:
                await self._listen_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("invalidation listener crashed; reconnecting in 1s: %s", exc)
                await asyncio.sleep(1)

    async def _listen_once(self) -> None:
        """Run one subscription session until disconnect.

        TODO:
            pubsub = self._r.pubsub()
            await pubsub.subscribe(self._channel)
            async for message in pubsub.listen():
                if message["type"] != "message": continue
                payload = json.loads(message["data"])
                await self._handle_message(payload)
        """
        raise NotImplementedError("InvalidationBus._listen_once is a TODO")

    async def _handle_message(self, payload: dict[str, str]) -> None:
        """React to one invalidation message.

        The payload has exactly one of (key, pattern). For key: DEL.
        For pattern: SCAN MATCH, then DEL each.
        """
        if "key" in payload:
            try:
                await self._r.delete(payload["key"])
                logger.info("invalidated key=%s", payload["key"])
            except Exception as exc:  # noqa: BLE001
                logger.warning("invalidation DEL failed: %s", exc)
            return

        if "pattern" in payload:
            try:
                async for k in self._r.scan_iter(match=payload["pattern"], count=100):
                    await self._r.delete(k)
                logger.info("invalidated pattern=%s", payload["pattern"])
            except Exception as exc:  # noqa: BLE001
                logger.warning("invalidation pattern sweep failed: %s", exc)
