"""
Exercise 2 — Eviction and TTL: configure maxmemory, watch keys evicted live.

Time:   ~1 hour.
Goal:   Configure a Redis instance with a small maxmemory ceiling and an
        allkeys-lru policy, then fill it past the ceiling and observe the
        eviction in INFO stats. Repeat with allkeys-lfu, volatile-ttl, and
        noeviction. Build the intuition for which policy fits which workload.

Run:
    redis-cli FLUSHDB
    python3 exercise-02-eviction-and-ttl-experiments.py

Try:
    Watch the output. The script fills Redis with strings of a known size,
    runs INFO between batches, and reports the evicted_keys count for each
    policy variation. The numbers tell you what is keeping the working set
    in memory and what is being thrown away.

Cited:
    - https://redis.io/docs/latest/develop/reference/eviction/
    - https://redis.io/docs/latest/operate/oss_and_stack/management/config/
    - https://redis.io/commands/info/
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]


logger = logging.getLogger("eviction")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


# ---------------------------------------------------------------------------
# Part A — Configure Redis at runtime
# ---------------------------------------------------------------------------
#
# We change maxmemory and maxmemory-policy via CONFIG SET. The changes are
# in-memory only; restart Redis to revert. Do NOT run this against a
# production Redis — set the maxmemory to a tiny value (1 MB) for the demo.


async def configure_redis(
    r: "redis.Redis",
    maxmemory: str,
    policy: str,
) -> None:
    """Configure the running Redis with the given maxmemory and policy."""
    await r.config_set("maxmemory", maxmemory)
    await r.config_set("maxmemory-policy", policy)
    logger.info("Configured maxmemory=%s policy=%s", maxmemory, policy)


# ---------------------------------------------------------------------------
# Part B — Fill the cache and observe the eviction
# ---------------------------------------------------------------------------


async def fill_until_evictions(
    r: "redis.Redis",
    count: int,
    value_size: int,
    ttl: int | None = None,
) -> dict[str, Any]:
    """Write `count` keys of `value_size` bytes each. Return INFO snapshot.

    The ttl parameter, when set, applies to every written key. Useful for
    distinguishing volatile-* from allkeys-* policies — volatile-* only
    evicts keys with TTL.
    """
    value = "X" * value_size
    pipe = r.pipeline()
    for i in range(count):
        if ttl is not None:
            pipe.set(f"k:{i}", value, ex=ttl)
        else:
            pipe.set(f"k:{i}", value)
    await pipe.execute()

    stats = await r.info("stats")
    memory = await r.info("memory")
    return {
        "evicted_keys": stats.get("evicted_keys", 0),
        "keyspace_hits": stats.get("keyspace_hits", 0),
        "keyspace_misses": stats.get("keyspace_misses", 0),
        "used_memory_human": memory.get("used_memory_human", "?"),
        "maxmemory_human": memory.get("maxmemory_human", "?"),
    }


# ---------------------------------------------------------------------------
# Part C — A scenario per policy
# ---------------------------------------------------------------------------


async def scenario_allkeys_lru(r: "redis.Redis") -> dict[str, Any]:
    """allkeys-lru is the canonical cache policy. Fill, then observe."""
    await r.flushdb()
    await configure_redis(r, maxmemory="2mb", policy="allkeys-lru")
    stats = await fill_until_evictions(r, count=2000, value_size=2048)
    # Touch some keys to make them recently used; the others are LRU.
    for i in range(0, 500):
        await r.get(f"k:{i}")
    # Add more keys to force eviction; the recently-touched should survive.
    more_stats = await fill_until_evictions(r, count=1000, value_size=2048)
    return {"initial": stats, "after_more": more_stats}


async def scenario_allkeys_lfu(r: "redis.Redis") -> dict[str, Any]:
    """allkeys-lfu is better for skewed access. Hit some keys many times."""
    await r.flushdb()
    await configure_redis(r, maxmemory="2mb", policy="allkeys-lfu")
    stats = await fill_until_evictions(r, count=2000, value_size=2048)
    # Make keys 0..50 frequently used.
    for _ in range(20):
        for i in range(0, 50):
            await r.get(f"k:{i}")
    more_stats = await fill_until_evictions(r, count=1000, value_size=2048)
    return {"initial": stats, "after_more": more_stats}


async def scenario_volatile_ttl(r: "redis.Redis") -> dict[str, Any]:
    """volatile-ttl evicts the TTL-bearing key closest to expiry."""
    await r.flushdb()
    await configure_redis(r, maxmemory="2mb", policy="volatile-ttl")
    # Half with short TTL, half with long TTL.
    short_stats = await fill_until_evictions(r, count=1000, value_size=2048, ttl=60)
    long_stats = await fill_until_evictions(r, count=1000, value_size=2048, ttl=3600)
    more_stats = await fill_until_evictions(r, count=500, value_size=2048, ttl=300)
    return {"short": short_stats, "long": long_stats, "after_more": more_stats}


async def scenario_noeviction(r: "redis.Redis") -> dict[str, Any]:
    """noeviction returns error on SET past the ceiling. Catch the error."""
    await r.flushdb()
    await configure_redis(r, maxmemory="1mb", policy="noeviction")
    errors = 0
    sets = 0
    value = "X" * 4096
    for i in range(1000):
        try:
            await r.set(f"k:{i}", value)
            sets += 1
        except Exception as exc:  # noqa: BLE001
            errors += 1
            if errors == 1:
                logger.info("First noeviction error: %s", exc)
    memory = await r.info("memory")
    return {
        "successful_sets": sets,
        "errors": errors,
        "used_memory_human": memory.get("used_memory_human", "?"),
    }


# ---------------------------------------------------------------------------
# Part D — Main
# ---------------------------------------------------------------------------


async def main() -> None:
    if redis is None:
        logger.error("redis package not installed; pip install 'redis[hiredis]==5.0.*'")
        return

    r = redis.from_url("redis://localhost:6379/3", decode_responses=True)
    try:
        await r.ping()
    except Exception as exc:  # noqa: BLE001
        logger.error("Redis not reachable: %s", exc)
        return

    # Save the original config so we can restore it.
    orig_maxmemory = (await r.config_get("maxmemory")).get("maxmemory", "0")
    orig_policy = (await r.config_get("maxmemory-policy")).get("maxmemory-policy", "noeviction")

    try:
        logger.info("=== scenario_allkeys_lru ===")
        result = await scenario_allkeys_lru(r)
        logger.info("%s", result)

        logger.info("=== scenario_allkeys_lfu ===")
        result = await scenario_allkeys_lfu(r)
        logger.info("%s", result)

        logger.info("=== scenario_volatile_ttl ===")
        result = await scenario_volatile_ttl(r)
        logger.info("%s", result)

        logger.info("=== scenario_noeviction ===")
        result = await scenario_noeviction(r)
        logger.info("%s", result)

    finally:
        await r.flushdb()
        await r.config_set("maxmemory", orig_maxmemory)
        await r.config_set("maxmemory-policy", orig_policy)
        await r.aclose()


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------
#
# Run `python3 -m py_compile exercise-02-eviction-and-ttl-experiments.py`.
#
# TASK 1: After scenario_allkeys_lru, which key range survives the eviction
# pressure — keys 0..500 (recently touched) or keys 500..2000? Why? Cite
# the Redis eviction docs.
#
# TASK 2: scenario_allkeys_lfu touches keys 0..50 twenty times each. Compare
# the eviction outcome to scenario_allkeys_lru. Which policy retained the
# hot keys better?
#
# TASK 3: scenario_noeviction reports a count of successful_sets less than
# 1000. What is the first error message Redis returned, and what does it
# tell you about the noeviction policy's user-facing behaviour?
#
# Answer in SOLUTIONS.md.


if __name__ == "__main__":
    asyncio.run(main())
