"""
Exercise 4 — Cache stampede: reproduce, then fix.

Time:   ~1 hour.
Goal:   Reproduce the cache stampede with 100 concurrent requests for the
        same expired key. Observe the database load amplification. Fix the
        stampede with request coalescing (single-flight). Compare to the
        XFetch (probabilistic early expiration) approach.

Run:
    redis-cli FLUSHDB
    python3 exercise-04-stampede-with-coalescing.py

Try:
    The script runs three scenarios — naive (stampede), coalescing, XFetch —
    each with 100 concurrent requests for the same key right after the
    cache has expired. The "loader_calls" counter is the smoking gun:
    naive should report ~100; coalescing should report 1; XFetch should
    report 1-2 in the steady state.

Cited:
    - https://arxiv.org/abs/1504.00922 (Vattani et al. 2015)
    - https://en.wikipedia.org/wiki/Cache_stampede
    - https://redis-py.readthedocs.io/en/stable/examples/asyncio_examples.html
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
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]


logger = logging.getLogger("stampede")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Part A — A loader with a counter
# ---------------------------------------------------------------------------


class CountedLoader:
    """Wraps an async loader. Tracks how many times it has actually run."""

    def __init__(self, name: str, latency_seconds: float = 0.2) -> None:
        self.name = name
        self.latency = latency_seconds
        self.calls = 0

    async def __call__(self) -> dict[str, Any]:
        self.calls += 1
        await asyncio.sleep(self.latency)
        return {"name": self.name, "loaded_at": time.time(), "call_number": self.calls}


# ---------------------------------------------------------------------------
# Part B — Naive cache-aside (the stampede)
# ---------------------------------------------------------------------------


async def naive_cache_aside(
    r: "redis.Redis",
    key: str,
    loader: Callable[[], Awaitable[T]],
    ttl: int,
) -> T:
    cached = await r.get(key)
    if cached is not None:
        return json.loads(cached)  # type: ignore[no-any-return]
    value = await loader()
    await r.set(key, json.dumps(value), ex=ttl)
    return value


# ---------------------------------------------------------------------------
# Part C — Request coalescing (single-flight)
# ---------------------------------------------------------------------------


class CoalescingCache:
    """Process-local single-flight cache wrapper around redis-py.

    Bounds rebuild concurrency at one per key per worker. Cross-worker
    coalescing requires a Redis SETNX lock (see Section D).
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
        cached = await self._r.get(key)
        if cached is not None:
            return json.loads(cached)

        async with self._lock:
            existing = self._inflight.get(key)
            if existing is not None:
                future = existing
            else:
                future = asyncio.get_running_loop().create_future()
                self._inflight[key] = future
                asyncio.create_task(self._do_load(key, loader, ttl, future))
        return await future

    async def _do_load(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        ttl: int,
        future: asyncio.Future[Any],
    ) -> None:
        try:
            value = await loader()
            await self._r.set(key, json.dumps(value), ex=ttl)
            future.set_result(value)
        except Exception as exc:  # noqa: BLE001
            future.set_exception(exc)
        finally:
            async with self._lock:
                self._inflight.pop(key, None)


# ---------------------------------------------------------------------------
# Part D — XFetch (Vattani et al. 2015, probabilistic early expiration)
# ---------------------------------------------------------------------------


def xfetch_should_refresh(
    expiry_unix: float,
    delta: float,
    beta: float = 1.0,
    now: float | None = None,
) -> bool:
    """Vattani, Chierichetti, Lowenstein (VLDB 2015) — XFetch algorithm.

    Returns True iff this caller should refresh the cache early. The
    probability is small when the cache is fresh and approaches 1 at expiry.
    """
    t = now if now is not None else time.time()
    # rand() returns [0, 1); we want (0, 1] for log to be defined.
    r_val = random.random() or 1e-9
    return t - delta * beta * math.log(r_val) >= expiry_unix


async def xfetch_cache_aside(
    r: "redis.Redis",
    key: str,
    loader: Callable[[], Awaitable[Any]],
    ttl: int,
    delta: float,
) -> Any:
    """Read with probabilistic early refresh."""
    pipe = r.pipeline()
    pipe.get(key)
    pipe.ttl(key)
    cached, remaining_ttl = await pipe.execute()
    if cached is None:
        value = await loader()
        await r.set(key, json.dumps(value), ex=ttl)
        return value

    expiry_unix = time.time() + remaining_ttl
    if xfetch_should_refresh(expiry_unix, delta):
        # Fire-and-forget refresh in the background.
        asyncio.create_task(_refresh_in_background(r, key, loader, ttl))
    return json.loads(cached)


async def _refresh_in_background(
    r: "redis.Redis",
    key: str,
    loader: Callable[[], Awaitable[Any]],
    ttl: int,
) -> None:
    try:
        value = await loader()
        await r.set(key, json.dumps(value), ex=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("background refresh failed: %s", exc)


# ---------------------------------------------------------------------------
# Part E — Run the three scenarios
# ---------------------------------------------------------------------------


async def scenario_naive(r: "redis.Redis", concurrency: int) -> int:
    await r.flushdb()
    loader = CountedLoader("naive", latency_seconds=0.2)
    # No warm-up: simulate the moment of expiry.
    tasks = [naive_cache_aside(r, "k", loader, ttl=60) for _ in range(concurrency)]
    await asyncio.gather(*tasks)
    return loader.calls


async def scenario_coalescing(r: "redis.Redis", concurrency: int) -> int:
    await r.flushdb()
    cache = CoalescingCache(r)
    loader = CountedLoader("coalesced", latency_seconds=0.2)
    tasks = [cache.get("k", loader, ttl=60) for _ in range(concurrency)]
    await asyncio.gather(*tasks)
    return loader.calls


async def scenario_xfetch(r: "redis.Redis", concurrency: int) -> int:
    await r.flushdb()
    loader = CountedLoader("xfetch", latency_seconds=0.2)
    # Warm the cache.
    await xfetch_cache_aside(r, "k", loader, ttl=5, delta=0.2)
    # Sleep until we are at the edge of expiry.
    await asyncio.sleep(4.5)
    # Burst the cache with concurrent reads.
    tasks = [xfetch_cache_aside(r, "k", loader, ttl=5, delta=0.2) for _ in range(concurrency)]
    await asyncio.gather(*tasks)
    return loader.calls


# ---------------------------------------------------------------------------
# Part F — Main
# ---------------------------------------------------------------------------


async def main() -> None:
    if redis is None:
        logger.error("redis package not installed")
        return

    r = redis.from_url("redis://localhost:6379/5", decode_responses=True)
    try:
        await r.ping()
    except Exception as exc:  # noqa: BLE001
        logger.error("Redis not reachable: %s", exc)
        return

    concurrency = 100

    try:
        logger.info("=== naive (stampede) ===")
        calls = await scenario_naive(r, concurrency)
        logger.info("loader_calls=%d concurrency=%d  (expected ~%d)",
                    calls, concurrency, concurrency)

        logger.info("=== coalescing (single-flight) ===")
        calls = await scenario_coalescing(r, concurrency)
        logger.info("loader_calls=%d concurrency=%d  (expected 1)",
                    calls, concurrency)

        logger.info("=== xfetch (probabilistic early expiration) ===")
        calls = await scenario_xfetch(r, concurrency)
        logger.info("loader_calls=%d concurrency=%d  (expected 1-2 in steady state)",
                    calls, concurrency)
    finally:
        await r.aclose()


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------
#
# Run `python3 -m py_compile exercise-04-stampede-with-coalescing.py`.
#
# TASK 1: scenario_naive should report loader_calls close to concurrency.
# Why is it not exactly equal to concurrency? Document in SOLUTIONS.md.
#
# TASK 2: scenario_coalescing reports loader_calls == 1. Walk through the
# coordination: when the second caller calls cache.get, what does it find
# in self._inflight? What does it await?
#
# TASK 3: scenario_xfetch reports 1-2 (the warm-up call plus possibly one
# probabilistic refresh during the burst). The exact number is non-
# deterministic. Run the script three times; record the calls counts.
# Comment on the distribution in SOLUTIONS.md.
#
# TASK 4 (stretch): Implement a fourth scenario using a Redis SETNX lock
# for cross-worker coalescing. Compare its loader_calls count against the
# process-local coalescing scenario.


if __name__ == "__main__":
    asyncio.run(main())
