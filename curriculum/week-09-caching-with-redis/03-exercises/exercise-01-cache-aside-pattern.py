"""
Exercise 1 — Cache-aside: take a slow function, cache it, measure the win.

Time:   ~1 hour.
Goal:   Implement the cache-aside pattern for an artificially slow function;
        observe the latency drop in a small benchmark loop; confirm the cache
        miss / hit transitions by reading the Redis INFO stats.

Run:
    # In one terminal:
    redis-cli FLUSHDB
    redis-cli MONITOR              # Optional — watch every Redis command live

    # In another:
    python3 exercise-01-cache-aside-pattern.py

Try:
    Open the source. The slow_fetch_article function sleeps for 200 ms to
    simulate a database query. The exercise wraps it in a cache-aside
    helper. Run the script and observe the second-call latency drop from
    200 ms to ~1 ms.

Cited:
    - https://redis.io/docs/latest/develop/data-types/strings/
    - https://redis-py.readthedocs.io/en/stable/examples/asyncio_examples.html
    - https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside

The TASK comments below mark prompts you should answer in SOLUTIONS.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]


logger = logging.getLogger("cache_aside")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


T = TypeVar("T")


# ---------------------------------------------------------------------------
# Part A — The slow function we are caching
# ---------------------------------------------------------------------------


async def slow_fetch_article(article_id: int) -> dict[str, Any]:
    """Pretend to query a database. The sleep is the cost we are eliminating."""
    await asyncio.sleep(0.2)
    return {
        "id": article_id,
        "title": f"Article {article_id}",
        "body": "A" * 500,
        "fetched_at": time.time(),
    }


# ---------------------------------------------------------------------------
# Part B — The cache-aside helper
# ---------------------------------------------------------------------------


async def cache_aside_get(
    r: "redis.Redis",
    key: str,
    loader: Callable[[], Awaitable[T]],
    ttl: int = 60,
) -> T:
    """Read the cache; on miss, run the loader, write the cache, return.

    The classic cache-aside read path. The application owns the orchestration;
    the cache layer is a passive key-value store.

    TASK 1: What is the latency contribution of each line in this function
    on a cache hit? On a cache miss? Annotate in SOLUTIONS.md.
    """
    cached = await r.get(key)
    if cached is not None:
        return json.loads(cached)  # type: ignore[no-any-return]
    value = await loader()
    await r.set(key, json.dumps(value), ex=ttl)
    return value


# ---------------------------------------------------------------------------
# Part C — The benchmark harness
# ---------------------------------------------------------------------------


async def benchmark_uncached(article_id: int, n: int) -> tuple[float, float]:
    """Call slow_fetch_article n times; return (total_seconds, per_call_seconds)."""
    start = time.perf_counter()
    for _ in range(n):
        await slow_fetch_article(article_id)
    total = time.perf_counter() - start
    return total, total / n


async def benchmark_cached(
    r: "redis.Redis",
    article_id: int,
    n: int,
) -> tuple[float, float]:
    """Call cache_aside_get n times; return (total_seconds, per_call_seconds)."""
    key = f"v1:article:{article_id}"
    # First call to warm the cache. The warm-up is not counted.
    await cache_aside_get(r, key, lambda: slow_fetch_article(article_id), ttl=60)
    start = time.perf_counter()
    for _ in range(n):
        await cache_aside_get(r, key, lambda: slow_fetch_article(article_id), ttl=60)
    total = time.perf_counter() - start
    return total, total / n


# ---------------------------------------------------------------------------
# Part D — A small "is the cache offline" simulation
# ---------------------------------------------------------------------------


async def cache_aside_get_with_fallback(
    r: "redis.Redis",
    key: str,
    loader: Callable[[], Awaitable[T]],
    ttl: int = 60,
) -> T:
    """Cache-aside that degrades cleanly when Redis is unreachable.

    The service must keep working with the cache offline; the cache is a
    latency optimisation, not a source of truth.

    TASK 2: Why is the exception-handling shape "try cache, fall back on
    any RedisError" rather than "if r is None: skip cache"? Answer in
    SOLUTIONS.md.
    """
    try:
        cached = await r.get(key)
        if cached is not None:
            return json.loads(cached)  # type: ignore[no-any-return]
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache read failed; degrading: %s", exc)

    value = await loader()
    try:
        await r.set(key, json.dumps(value), ex=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache write failed; continuing: %s", exc)
    return value


# ---------------------------------------------------------------------------
# Part E — Main: run the benchmark
# ---------------------------------------------------------------------------


async def main() -> None:
    if redis is None:
        logger.error("redis package not installed; pip install 'redis[hiredis]==5.0.*'")
        return

    r = redis.from_url("redis://localhost:6379/0", decode_responses=True)
    try:
        await r.ping()
    except Exception as exc:  # noqa: BLE001
        logger.error("Redis not reachable at localhost:6379: %s", exc)
        return

    await r.flushdb()

    n = 100
    article_id = 42

    logger.info("--- Uncached: %d calls to slow_fetch_article ---", n)
    uncached_total, uncached_per = await benchmark_uncached(article_id, n)
    logger.info("Uncached: total=%.3fs per_call=%.4fs", uncached_total, uncached_per)

    logger.info("--- Cached: %d calls to cache_aside_get ---", n)
    cached_total, cached_per = await benchmark_cached(r, article_id, n)
    logger.info("Cached:   total=%.3fs per_call=%.6fs", cached_total, cached_per)

    speedup = uncached_per / cached_per if cached_per > 0 else float("inf")
    logger.info("Speedup: %.1fx", speedup)

    # TASK 3: The benchmark above measures the steady-state hit case. What
    # happens to per_call latency if you call await r.flushdb() between
    # every call? Why? Document the result in SOLUTIONS.md.

    # Inspect Redis state.
    info = await r.info("stats")
    logger.info(
        "Redis stats: hits=%s misses=%s ops_per_sec=%s",
        info.get("keyspace_hits"),
        info.get("keyspace_misses"),
        info.get("instantaneous_ops_per_sec"),
    )

    await r.aclose()


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------
#
# Run `python3 -m py_compile exercise-01-cache-aside-pattern.py`. It must
# succeed silently.
#
# TASK 4: Modify the benchmark to call cache_aside_get_with_fallback
# instead of cache_aside_get, then close the Redis client before the
# benchmark loop. Confirm the loop still returns valid articles (degraded
# to direct loader calls). Document the per_call latency in SOLUTIONS.md.


if __name__ == "__main__":
    asyncio.run(main())
