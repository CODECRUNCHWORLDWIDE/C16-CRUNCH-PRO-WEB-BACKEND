"""ARQ workers that keep OpenSearch and Meilisearch in sync with Postgres.

Two workers, each subscribed to the `articles:changed` Redis Pub/Sub channel.
On every event:
    - re-fetch the article from Postgres
    - upsert into the secondary backend, or delete if the article is gone

The Postgres FTS path needs no worker — the generated tsvector column is
updated automatically on every INSERT/UPDATE/DELETE.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]

try:
    import redis.asyncio as redis_async
except ImportError:  # pragma: no cover
    redis_async = None  # type: ignore[assignment]

try:
    from opensearchpy import AsyncOpenSearch
except ImportError:  # pragma: no cover
    AsyncOpenSearch = None  # type: ignore[assignment, misc]

try:
    from meilisearch_python_sdk import AsyncClient as MeiliAsyncClient
except ImportError:  # pragma: no cover
    MeiliAsyncClient = None  # type: ignore[assignment, misc]

from .schemas import IndexEvent
from .settings import Settings, get_settings


logger = logging.getLogger("crunchsearch.workers")


# ---------------------------------------------------------------------------
# Re-fetch helper
# ---------------------------------------------------------------------------


async def fetch_article(pool: "asyncpg.Pool", article_id: int) -> dict[str, Any] | None:
    """Return the article row as a plain dict, or None if it was deleted."""
    sql = """
        SELECT id, title, body, author, tags, published_at
        FROM articles_w10
        WHERE id = $1;
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, article_id)
    if row is None:
        return None
    return dict(row)


# ---------------------------------------------------------------------------
# OpenSearch indexing worker
# ---------------------------------------------------------------------------


async def opensearch_apply_event(
    pool: "asyncpg.Pool",
    os_client: "AsyncOpenSearch",
    index: str,
    event: IndexEvent,
) -> None:
    """Apply a single index event to OpenSearch."""
    if event.op == "delete":
        try:
            await os_client.delete(index=index, id=str(event.id))
        except Exception as exc:  # pragma: no cover - 404 if absent
            logger.info("opensearch delete %s no-op: %s", event.id, exc)
        return

    article = await fetch_article(pool, event.id)
    if article is None:
        # Race: event said upsert; row already gone. Delete to converge.
        try:
            await os_client.delete(index=index, id=str(event.id))
        except Exception:  # pragma: no cover
            pass
        return

    # Convert datetime to ISO-8601 string for OpenSearch.
    published_at = article.get("published_at")
    if published_at is not None and not isinstance(published_at, str):
        article["published_at"] = published_at.isoformat()

    await os_client.index(index=index, id=str(event.id), body=article)


async def opensearch_worker_loop(settings: Settings | None = None) -> None:
    """Subscribe to articles:changed; apply each event to OpenSearch."""
    if redis_async is None or asyncpg is None or AsyncOpenSearch is None:
        raise RuntimeError("Missing dependencies; install redis, asyncpg, opensearch-py")
    settings = settings or get_settings()

    pool = await asyncpg.create_pool(settings.postgres_dsn, min_size=1, max_size=4)
    if pool is None:  # pragma: no cover
        raise RuntimeError("could not open the pg pool")
    redis_client = redis_async.from_url(settings.redis_url, decode_responses=True)
    os_client = AsyncOpenSearch(
        hosts=[{"host": settings.opensearch_host, "port": settings.opensearch_port}],
        http_auth=(settings.opensearch_user, settings.opensearch_pass),
        use_ssl=True,
        verify_certs=False,
        ssl_show_warn=False,
    )
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("articles:changed")
    logger.info("opensearch worker subscribed to articles:changed")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                payload = json.loads(message["data"])
                event = IndexEvent(**payload)
                await opensearch_apply_event(pool, os_client, settings.opensearch_index, event)
            except Exception:  # pragma: no cover
                logger.exception("opensearch worker error on message %r", message)
    finally:
        await pubsub.aclose()
        await redis_client.aclose()
        await os_client.close()
        await pool.close()


# ---------------------------------------------------------------------------
# Meilisearch indexing worker
# ---------------------------------------------------------------------------


async def meili_apply_event(
    pool: "asyncpg.Pool",
    meili_client: "MeiliAsyncClient",
    index_name: str,
    event: IndexEvent,
) -> None:
    """Apply a single index event to Meilisearch."""
    index = meili_client.index(index_name)
    if event.op == "delete":
        try:
            await index.delete_document(event.id)
        except Exception as exc:  # pragma: no cover
            logger.info("meili delete %s no-op: %s", event.id, exc)
        return

    article = await fetch_article(pool, event.id)
    if article is None:
        try:
            await index.delete_document(event.id)
        except Exception:  # pragma: no cover
            pass
        return

    # Meilisearch wants epoch seconds for published_at (numeric for sortability).
    published_at = article.get("published_at")
    if published_at is not None and hasattr(published_at, "timestamp"):
        article["published_at"] = int(published_at.timestamp())

    await index.add_documents([article])


async def meili_worker_loop(settings: Settings | None = None) -> None:
    """Subscribe to articles:changed; apply each event to Meilisearch."""
    if redis_async is None or asyncpg is None or MeiliAsyncClient is None:
        raise RuntimeError("Missing dependencies; install redis, asyncpg, meilisearch-python-sdk")
    settings = settings or get_settings()

    pool = await asyncpg.create_pool(settings.postgres_dsn, min_size=1, max_size=4)
    if pool is None:  # pragma: no cover
        raise RuntimeError("could not open the pg pool")
    redis_client = redis_async.from_url(settings.redis_url, decode_responses=True)
    async with MeiliAsyncClient(settings.meili_url, settings.meili_key) as meili_client:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("articles:changed")
        logger.info("meili worker subscribed to articles:changed")

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                    event = IndexEvent(**payload)
                    await meili_apply_event(pool, meili_client, settings.meili_index, event)
                except Exception:  # pragma: no cover
                    logger.exception("meili worker error on message %r", message)
        finally:
            await pubsub.aclose()
            await redis_client.aclose()
            await pool.close()


# ---------------------------------------------------------------------------
# Convenience driver: run both workers concurrently
# ---------------------------------------------------------------------------


async def run_workers() -> None:
    """Run both workers as concurrent asyncio tasks. Cancel with Ctrl+C."""
    await asyncio.gather(
        opensearch_worker_loop(),
        meili_worker_loop(),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run_workers())
