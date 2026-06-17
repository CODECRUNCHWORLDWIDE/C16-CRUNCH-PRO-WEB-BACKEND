"""Cache layer for crunchcache.

Provides:
    - get_redis(): the lifecycle-managed Redis client.
    - cache_aside_get(): the cache-aside read helper with degradation.
    - CoalescingCache: the process-local single-flight wrapper.
    - xfetch_should_refresh(): the Vattani 2015 algorithm.

Fill in the TODOs. The shape is in the docstrings; the wiring is in place.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

try:
    import redis.asyncio as redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]
    RedisError = Exception  # type: ignore[assignment, misc]


logger = logging.getLogger("crunchcache.cache")

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


_redis_client: "redis.Redis | None" = None


async def get_redis(redis_url: str = "redis://localhost:6379/0") -> "redis.Redis":
    """Return the module-level Redis client; lazy-init on first call.

    The single connection pool serves every request. Closed by the
    FastAPI lifespan shutdown.
    """
    global _redis_client
    if _redis_client is None:
        if redis is None:
            raise RuntimeError("redis package not installed")
        _redis_client = redis.from_url(redis_url, decode_responses=True)
    return _redis_client


async def close_redis() -> None:
    """Close the module-level Redis client. Called by the lifespan shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


# ---------------------------------------------------------------------------
# Cache-aside with degradation
# ---------------------------------------------------------------------------


async def cache_aside_get(
    r: "redis.Redis",
    key: str,
    loader: Callable[[], Awaitable[T]],
    ttl: int,
) -> T:
    """Cache-aside read.

    On a hit, decode and return the cached value.
    On a miss, run the loader, write the cache, return the value.
    On any RedisError, degrade to running the loader directly.

    TODO: Implement the three-path body. The try/except shape is the load-bearing
    detail — every Redis call goes through it; the loader is the fallback.
    """
    raise NotImplementedError("cache_aside_get is a TODO for the student")


# ---------------------------------------------------------------------------
# Process-local single-flight (request coalescing)
# ---------------------------------------------------------------------------


class CoalescingCache:
    """Single-flight cache wrapper.

    100 concurrent misses for the same key result in exactly 1 loader call;
    the other 99 await the first one's Future.
    """

    def __init__(self, r: "redis.Redis") -> None:
        self._r = r
        self._inflight: dict[str, asyncio.Future[Any]] = {}
        self._lock = asyncio.Lock()

    async def get(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        ttl: int,
    ) -> Any:
        """Read with stampede protection.

        TODO: Implement the three branches:
            (1) Cache hit -> return.
            (2) In-flight load for this key -> await the existing Future.
            (3) No in-flight load -> create a Future, kick off _do_load, await it.
        """
        raise NotImplementedError("CoalescingCache.get is a TODO for the student")

    async def _do_load(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        ttl: int,
        future: asyncio.Future[Any],
    ) -> None:
        """Background task that runs the loader and resolves the Future.

        TODO: try/except/finally:
            - try: call loader; SET cache; future.set_result.
            - except Exception: future.set_exception.
            - finally: remove the in-flight entry under the lock.
        """
        raise NotImplementedError("CoalescingCache._do_load is a TODO for the student")


# ---------------------------------------------------------------------------
# XFetch (Vattani 2015) — probabilistic early expiration
# ---------------------------------------------------------------------------


def xfetch_should_refresh(
    expiry_unix: float,
    delta: float,
    beta: float = 1.0,
    now: float | None = None,
) -> bool:
    """Vattani, Chierichetti, Lowenstein (VLDB 2015).

    Returns True iff this caller should refresh the cache early.
    The probability rises as the TTL approaches expiry.

    Formula: t - delta * beta * log(rand()) >= expiry

    Note: log(rand()) is negative since rand() < 1, so subtracting it adds
    a positive amount. The amount is small when rand() is close to 1 and
    large when rand() is close to 0.
    """
    t = now if now is not None else time.time()
    r_val = random.random() or 1e-9
    return t - delta * beta * math.log(r_val) >= expiry_unix
