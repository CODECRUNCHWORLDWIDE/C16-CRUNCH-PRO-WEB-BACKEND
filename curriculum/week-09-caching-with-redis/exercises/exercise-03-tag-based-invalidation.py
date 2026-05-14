"""
Exercise 3 — Tag-based invalidation: keys grouped by dependency.

Time:   ~1 hour.
Goal:   Implement a tag-based cache where each cached value declares the
        tags it depends on. Invalidating a tag sweeps every value that
        declared that tag. Useful for rendered-page caches where the
        dependency graph is wide.

Run:
    python3 exercise-03-tag-based-invalidation.py

Try:
    Read the main() flow. We cache three rendered pages, each depending on
    a different combination of article and author tags. We then invalidate
    one tag and observe which pages disappear.

Cited:
    - https://redis.io/commands/sadd/
    - https://redis.io/commands/smembers/
    - https://redis.io/commands/del/
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import BaseModel, Field, ConfigDict

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]


logger = logging.getLogger("tag_cache")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


# ---------------------------------------------------------------------------
# Part A — The Pydantic model for a cached entry
# ---------------------------------------------------------------------------


class CachedPage(BaseModel):
    """A rendered page; the value we cache."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    body: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Part B — The tag-based cache
# ---------------------------------------------------------------------------


class TagCache:
    """Cache where each value declares its tag dependencies.

    Layout:
        cache:<key>     -> JSON value
        tag:<tag>       -> SET of keys that depend on this tag

    Invalidating a tag iterates the SET and DELs every member, then DELs
    the SET itself.
    """

    def __init__(self, r: "redis.Redis", ttl: int = 3600) -> None:
        self._r = r
        self._ttl = ttl

    async def set(self, page: CachedPage) -> None:
        """Cache the page, registering it under each declared tag."""
        pipe = self._r.pipeline()
        pipe.set(f"cache:{page.key}", page.model_dump_json(), ex=self._ttl)
        for tag in page.tags:
            pipe.sadd(f"tag:{tag}", page.key)
            # The tag set's TTL is generous — outlive its members so we
            # don't lose the dependency map mid-flight.
            pipe.expire(f"tag:{tag}", self._ttl * 2)
        await pipe.execute()
        logger.info("cached key=%s tags=%s", page.key, page.tags)

    async def get(self, key: str) -> CachedPage | None:
        raw = await self._r.get(f"cache:{key}")
        if raw is None:
            return None
        return CachedPage.model_validate_json(raw)

    async def invalidate_tag(self, tag: str) -> int:
        """Remove every cached value declaring this tag. Returns the count."""
        tag_key = f"tag:{tag}"
        members = await self._r.smembers(tag_key)
        if not members:
            return 0
        pipe = self._r.pipeline()
        for member in members:
            pipe.delete(f"cache:{member}")
        pipe.delete(tag_key)
        await pipe.execute()
        count = len(members)
        logger.info("invalidated tag=%s; swept %d cache entries", tag, count)
        return count

    async def invalidate_key(self, key: str, tags: list[str]) -> None:
        """Remove one cached value and clean up its tag membership.

        The tags parameter is needed because Redis sets are membership-only;
        a cached page does not know which sets it belongs to without help.
        In production, you store the tag list alongside the cached value
        (which we do in the SET above), and you read it back before invalidating.
        """
        pipe = self._r.pipeline()
        pipe.delete(f"cache:{key}")
        for tag in tags:
            pipe.srem(f"tag:{tag}", key)
        await pipe.execute()
        logger.info("invalidated key=%s tags=%s", key, tags)


# ---------------------------------------------------------------------------
# Part C — A demonstration scenario
# ---------------------------------------------------------------------------


async def demo(r: "redis.Redis") -> None:
    cache = TagCache(r, ttl=300)

    # Three rendered pages. Each depends on a different mix of entities.
    page_a = CachedPage(
        key="homepage:en",
        body="<html>Homepage with articles 1, 2, 3</html>",
        tags=["article:1", "article:2", "article:3", "homepage"],
    )
    page_b = CachedPage(
        key="article:1:render:en",
        body="<html>Article 1 by Author 7</html>",
        tags=["article:1", "author:7"],
    )
    page_c = CachedPage(
        key="author:7:profile:en",
        body="<html>Author 7's profile</html>",
        tags=["author:7"],
    )

    await cache.set(page_a)
    await cache.set(page_b)
    await cache.set(page_c)

    logger.info("All three pages cached. Inspect:")
    for k in ("homepage:en", "article:1:render:en", "author:7:profile:en"):
        v = await cache.get(k)
        logger.info("  %s -> %s", k, "hit" if v else "miss")

    # Author 7 changes their display name. Sweep every page depending on author:7.
    logger.info("\nInvalidating tag=author:7 (Author 7 updated their name):")
    count = await cache.invalidate_tag("author:7")
    logger.info("Pages swept: %d", count)

    logger.info("After invalidation:")
    for k in ("homepage:en", "article:1:render:en", "author:7:profile:en"):
        v = await cache.get(k)
        logger.info("  %s -> %s", k, "hit" if v else "miss")

    # The homepage should still be cached (no author:7 dependency).
    # article:1:render:en and author:7:profile:en should be gone.

    # TASK 1: Trace the invalidation. Which Redis commands were issued?
    # Use MONITOR in a separate terminal to confirm. Document the trace
    # in SOLUTIONS.md.

    # Article 1 is deleted. Sweep every page depending on article:1.
    logger.info("\nInvalidating tag=article:1 (Article 1 deleted):")
    count = await cache.invalidate_tag("article:1")
    logger.info("Pages swept: %d", count)

    logger.info("After invalidation:")
    for k in ("homepage:en", "article:1:render:en", "author:7:profile:en"):
        v = await cache.get(k)
        logger.info("  %s -> %s", k, "hit" if v else "miss")

    # TASK 2: The homepage is now gone too. Why? Trace the dependency.
    # Document in SOLUTIONS.md.


# ---------------------------------------------------------------------------
# Part D — Main
# ---------------------------------------------------------------------------


async def main() -> None:
    if redis is None:
        logger.error("redis package not installed")
        return

    r = redis.from_url("redis://localhost:6379/4", decode_responses=True)
    try:
        await r.ping()
    except Exception as exc:  # noqa: BLE001
        logger.error("Redis not reachable: %s", exc)
        return
    await r.flushdb()
    try:
        await demo(r)
    finally:
        await r.aclose()


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------
#
# Run `python3 -m py_compile exercise-03-tag-based-invalidation.py`.
#
# TASK 3: The tag set's TTL is set to ttl * 2. What is the failure mode if
# the tag set's TTL is shorter than the cached values' TTL? Describe in
# SOLUTIONS.md.
#
# TASK 4: Modify the demo so a new page page_d is added with tags
# ["article:1", "premium"]. Invalidate tag="premium". Which other pages
# are affected? Document the expected result.


if __name__ == "__main__":
    asyncio.run(main())
