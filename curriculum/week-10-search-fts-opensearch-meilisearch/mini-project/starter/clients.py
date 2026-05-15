"""Three backend search clients. Each implements search(query, limit, offset).

The interface is the same; the implementations differ. The /search router
in routers_search.py picks one of these by name.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]

try:
    from opensearchpy import AsyncOpenSearch
except ImportError:  # pragma: no cover
    AsyncOpenSearch = None  # type: ignore[assignment, misc]

try:
    from meilisearch_python_sdk import AsyncClient as MeiliAsyncClient
except ImportError:  # pragma: no cover
    MeiliAsyncClient = None  # type: ignore[assignment, misc]


# ---------------------------------------------------------------------------
# Postgres FTS
# ---------------------------------------------------------------------------


async def search_postgres(
    pool: "asyncpg.Pool",
    query: str,
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    """FTS-then-trigram-fallback against the articles_w10 table.

    Returns a dict with shape compatible with SearchResponse.
    """
    if asyncpg is None:
        raise RuntimeError("asyncpg is not installed; pip install asyncpg")

    fts_sql = """
        SELECT id, title, author, published_at,
               ts_rank_cd(tsv, websearch_to_tsquery('english', $1), 32) AS score,
               ts_headline(
                   'english', body,
                   websearch_to_tsquery('english', $1),
                   'StartSel=<em>,StopSel=</em>,MaxFragments=2,FragmentDelimiter=...'
               ) AS snippet,
               count(*) OVER () AS total_count
        FROM articles_w10
        WHERE tsv @@ websearch_to_tsquery('english', $1)
        ORDER BY score DESC
        LIMIT $2 OFFSET $3;
    """
    trgm_sql = """
        SELECT id, title, author, published_at,
               similarity(title, $1) AS score,
               title AS snippet,
               count(*) OVER () AS total_count
        FROM articles_w10
        WHERE title %% $1
        ORDER BY score DESC
        LIMIT $2 OFFSET $3;
    """
    start = time.perf_counter()
    async with pool.acquire() as conn:
        rows = await conn.fetch(fts_sql, query, limit, offset)
        used_fallback = False
        if len(rows) < 5 and offset == 0:
            rows = await conn.fetch(trgm_sql, query, limit, offset)
            used_fallback = True
    took_ms = (time.perf_counter() - start) * 1000.0

    hits: list[dict[str, Any]] = []
    total = rows[0]["total_count"] if rows else 0
    for row in rows:
        hits.append(
            {
                "id":           row["id"],
                "title":        row["title"],
                "author":       row["author"],
                "published_at": row["published_at"],
                "score":        float(row["score"]),
                "snippet":      row["snippet"],
                "backend":      "postgres",
            }
        )
    return {
        "total":         int(total),
        "took_ms":       took_ms,
        "hits":          hits,
        "used_fallback": used_fallback,
    }


# ---------------------------------------------------------------------------
# OpenSearch
# ---------------------------------------------------------------------------


async def search_opensearch(
    client: "AsyncOpenSearch",
    index: str,
    query: str,
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    """multi_match search with title^3 boost; returns SearchResponse-shaped dict."""
    if AsyncOpenSearch is None:
        raise RuntimeError("opensearch-py is not installed; pip install opensearch-py")
    body: dict[str, Any] = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["title^3", "body"],
                "type": "best_fields",
            }
        },
        "from": offset,
        "size": limit,
        "highlight": {
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
            "fields": {"body": {"number_of_fragments": 2, "fragment_size": 120}},
        },
    }
    start = time.perf_counter()
    result = await client.search(index=index, body=body)
    took_ms = (time.perf_counter() - start) * 1000.0

    total = result["hits"]["total"]["value"]
    hits: list[dict[str, Any]] = []
    for hit in result["hits"]["hits"]:
        src = hit["_source"]
        snippet_frags = hit.get("highlight", {}).get("body", [])
        snippet = " ... ".join(snippet_frags) if snippet_frags else None
        published_at = _parse_dt(src.get("published_at"))
        hits.append(
            {
                "id":           int(hit["_id"]),
                "title":        src["title"],
                "author":       src["author"],
                "published_at": published_at,
                "score":        float(hit["_score"]),
                "snippet":      snippet,
                "backend":      "opensearch",
            }
        )
    return {
        "total":   int(total),
        "took_ms": took_ms,
        "hits":    hits,
    }


# ---------------------------------------------------------------------------
# Meilisearch
# ---------------------------------------------------------------------------


async def search_meili(
    client: "MeiliAsyncClient",
    index_name: str,
    query: str,
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    """Meilisearch search with default ranking rules and typo tolerance."""
    if MeiliAsyncClient is None:
        raise RuntimeError("meilisearch-python-sdk is not installed; pip install meilisearch-python-sdk")
    index = client.index(index_name)
    start = time.perf_counter()
    result = await index.search(
        query,
        limit=limit,
        offset=offset,
        attributes_to_highlight=["body"],
        crop_length=30,
    )
    took_ms = (time.perf_counter() - start) * 1000.0

    hits: list[dict[str, Any]] = []
    for hit in result.hits:
        formatted = hit.get("_formatted", {})
        snippet = formatted.get("body") if isinstance(formatted, dict) else None
        published_at = _parse_dt(hit.get("published_at"))
        hits.append(
            {
                "id":           int(hit["id"]),
                "title":        hit["title"],
                "author":       hit.get("author", ""),
                "published_at": published_at,
                # Meilisearch does not expose a numeric score by default.
                # Use the negative rank as a stand-in (lower rank = better).
                "score":        1.0,
                "snippet":      snippet,
                "backend":      "meili",
            }
        )
    return {
        "total":   int(result.estimated_total_hits or 0),
        "took_ms": took_ms,
        "hits":    hits,
    }


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _parse_dt(value: Any) -> datetime:
    """Coerce a backend-provided published_at into a datetime.

    Accepts ISO strings (Postgres, OpenSearch) and unix epoch ints (Meilisearch).
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        # Postgres asyncpg returns datetime directly; this branch is the
        # OpenSearch ISO-8601 case.
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(tz=timezone.utc)
