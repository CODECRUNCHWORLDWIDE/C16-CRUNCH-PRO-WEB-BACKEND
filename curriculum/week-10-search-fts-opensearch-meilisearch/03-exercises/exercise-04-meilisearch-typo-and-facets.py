"""
Exercise 4 — Meilisearch: index documents, tune ranking rules, demonstrate
typo tolerance, run faceted search.

Time:   ~1 hour.
Goal:   Create a Meilisearch index; configure searchableAttributes,
        filterableAttributes, sortableAttributes; index the seed corpus;
        run a search with typo tolerance and facet distribution; reorder
        the ranking rules and observe the effect.

Run:
    # 1. Meilisearch reachable on http://localhost:7700.
    docker run -d -p 7700:7700 -e MEILI_MASTER_KEY=Crunch_Pro_W10_key \
        getmeili/meilisearch:v1.10

    # 2. Confirm.
    curl -H "Authorization: Bearer Crunch_Pro_W10_key" http://localhost:7700/health

    # 3. Run.
    pip install 'meilisearch-python-sdk==2.10.*'
    python3 exercise-04-meilisearch-typo-and-facets.py

Try:
    Read the settings block. Note `searchableAttributes = [title, body]`
    means title-match ranks above body-match (per the `attribute`
    ranking rule). Run the script and observe: "pythn" (misspelled)
    finds "python" via typo tolerance; faceted search returns per-tag
    document counts.

Cited:
    - https://www.meilisearch.com/docs/learn/getting_started/quick_start
    - https://www.meilisearch.com/docs/learn/relevancy/ranking_rules
    - https://www.meilisearch.com/docs/reference/api/settings

The TASK comments below mark prompts you should answer in SOLUTIONS.md.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

try:
    from meilisearch_python_sdk import AsyncClient
except ImportError:  # pragma: no cover
    AsyncClient = None  # type: ignore[assignment, misc]


logger = logging.getLogger("meilisearch_exercise")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


MEILI_URL = os.environ.get("CC_W10_MEILI_URL", "http://localhost:7700")
MEILI_KEY = os.environ.get("CC_W10_MEILI_KEY", "Crunch_Pro_W10_key")
INDEX = "cc_w10_articles"


# ---------------------------------------------------------------------------
# Part A — The seed corpus (slightly larger so faceting has signal)
# ---------------------------------------------------------------------------


SEED_ARTICLES: list[dict[str, Any]] = [
    {
        "id": 1,
        "title": "Python async generators",
        "body": "Async generators in Python yield values lazily from an asynchronous iterator.",
        "author": "Avrot, Laetitia",
        "tags": ["python", "async", "tutorial"],
        "published_at": 1726395000,
        "view_count": 2840,
    },
    {
        "id": 2,
        "title": "Asynchronous Django views",
        "body": "Django supports asynchronous view handlers since 3.1.",
        "author": "Manning, Christopher",
        "tags": ["django", "async", "tutorial"],
        "published_at": 1722499200,
        "view_count": 1120,
    },
    {
        "id": 3,
        "title": "FastAPI dependencies and Pydantic v2",
        "body": "FastAPI's dependency injection composes with Pydantic v2 validators.",
        "author": "Avrot, Laetitia",
        "tags": ["fastapi", "pydantic", "tutorial"],
        "published_at": 1729426800,
        "view_count": 4310,
    },
    {
        "id": 4,
        "title": "Postgres full-text search",
        "body": "Postgres ships tsvector, tsquery, and ts_rank functions for full-text search.",
        "author": "Bost, Craig",
        "tags": ["postgres", "search"],
        "published_at": 1718203500,
        "view_count": 890,
    },
    {
        "id": 5,
        "title": "Build a search bar",
        "body": "The user-facing search bar should accept free-form input and rank results.",
        "author": "Turnbull, Doug",
        "tags": ["search", "ux"],
        "published_at": 1711100700,
        "view_count": 5210,
    },
    {
        "id": 6,
        "title": "Pydantic v2 validators",
        "body": "Pydantic v2 model validators run after field validation. Annotate with field_validator.",
        "author": "Avrot, Laetitia",
        "tags": ["pydantic", "validation"],
        "published_at": 1715423400,
        "view_count": 1670,
    },
    {
        "id": 7,
        "title": "Asynchronous I/O patterns",
        "body": "Coroutines, generators, and asynchronous iterators form the Python concurrency primitives.",
        "author": "Manning, Christopher",
        "tags": ["python", "async", "patterns"],
        "published_at": 1714294800,
        "view_count": 980,
    },
]


# ---------------------------------------------------------------------------
# Part B — Reset and seed
# ---------------------------------------------------------------------------


async def reset_index(client: Any) -> None:
    """Delete the index if present, then create it with our settings."""
    try:
        await client.delete_index(INDEX)
    except Exception:  # pragma: no cover - 404 if absent
        pass
    await client.create_index(INDEX, primary_key="id")
    index = client.index(INDEX)

    await index.update_settings(
        settings={
            "searchableAttributes": ["title", "body"],
            "filterableAttributes": ["author", "tags", "published_at"],
            "sortableAttributes":   ["published_at", "view_count"],
            "displayedAttributes":  [
                "id", "title", "body", "author", "tags", "published_at", "view_count",
            ],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "typoTolerance": {
                "enabled": True,
                "minWordSizeForTypos": {"oneTypo": 5, "twoTypos": 9},
            },
        }
    )


async def seed(client: Any, docs: list[dict[str, Any]]) -> None:
    """Add documents and wait for the indexing task to finish."""
    index = client.index(INDEX)
    task = await index.add_documents(docs)
    await client.wait_for_task(task.task_uid)


# ---------------------------------------------------------------------------
# Part C — Search variants
# ---------------------------------------------------------------------------


async def basic_search(client: Any, q: str) -> list[dict[str, Any]]:
    """Out-of-the-box search."""
    index = client.index(INDEX)
    result = await index.search(q, limit=25)
    return list(result.hits)


async def typo_search(client: Any, q: str) -> list[dict[str, Any]]:
    """Same engine, deliberately misspelled query."""
    index = client.index(INDEX)
    result = await index.search(q, limit=25)
    return list(result.hits)


async def faceted_search(client: Any, q: str, tag_filter: str | None = None) -> dict[str, Any]:
    """Search with a filter and facet distribution."""
    index = client.index(INDEX)
    opts: dict[str, Any] = {
        "limit": 25,
        "facets": ["author", "tags"],
        "attributesToHighlight": ["title", "body"],
        "cropLength": 20,
    }
    if tag_filter is not None:
        opts["filter"] = f"tags = '{tag_filter}'"
    result = await index.search(q, **opts)
    return {
        "hits": list(result.hits),
        "facets": result.facet_distribution or {},
        "estimated_total": result.estimated_total_hits,
        "ms": result.processing_time_ms,
    }


async def custom_rules_search(client: Any, q: str) -> list[dict[str, Any]]:
    """Reorder ranking rules to put exactness above typo, plus view_count tiebreaker."""
    index = client.index(INDEX)
    await index.update_settings(
        settings={
            "rankingRules": [
                "words",
                "exactness",   # exact matches above typo-corrected
                "typo",
                "proximity",
                "attribute",
                "sort",
                "view_count:desc",  # popularity tiebreaker
            ]
        }
    )
    # Updates are async on the server side; wait for the settings task.
    await asyncio.sleep(0.5)
    result = await index.search(q, limit=25)
    return list(result.hits)


# ---------------------------------------------------------------------------
# Part D — The driver
# ---------------------------------------------------------------------------


async def run_demo() -> None:
    """Reset, seed, and run the demonstration queries."""
    if AsyncClient is None:
        logger.error("meilisearch-python-sdk is not installed; pip install meilisearch-python-sdk")
        return

    async with AsyncClient(MEILI_URL, MEILI_KEY) as client:
        await reset_index(client)
        await seed(client, SEED_ARTICLES)

        print("\n=== basic search for 'python async' ===")
        for hit in await basic_search(client, "python async"):
            print(f"  {hit['id']}  {hit['title']}")

        print("\n=== typo tolerance: 'pythn async' (one-character typo) ===")
        for hit in await typo_search(client, "pythn async"):
            print(f"  {hit['id']}  {hit['title']}")

        print("\n=== typo tolerance: 'asycnhronous' (two-character typo, 12 chars) ===")
        for hit in await typo_search(client, "asycnhronous"):
            print(f"  {hit['id']}  {hit['title']}")

        print("\n=== faceted search for 'python' ===")
        composite = await faceted_search(client, "python")
        print(f"  total {composite['estimated_total']} hits in {composite['ms']} ms")
        for hit in composite["hits"]:
            print(f"    {hit['id']}  {hit['title']}")
        print("  facets:")
        for facet, dist in composite["facets"].items():
            print(f"    {facet}:")
            for key, count in dist.items():
                print(f"      {key}: {count}")

        print("\n=== filtered: tags='tutorial' on 'python' ===")
        composite = await faceted_search(client, "python", tag_filter="tutorial")
        print(f"  total {composite['estimated_total']} hits")
        for hit in composite["hits"]:
            print(f"    {hit['id']}  {hit['title']}  tags={hit['tags']}")

        print("\n=== custom ranking rules (exactness above typo + view_count desc) ===")
        for hit in await custom_rules_search(client, "python"):
            print(f"  {hit['id']}  views={hit['view_count']}  {hit['title']}")

        # TASK 1: Vary minWordSizeForTypos.oneTypo from 5 down to 3 and
        #         observe which queries pick up additional hits. Document
        #         in SOLUTIONS.md the trade-off (more recall, less
        #         precision).

        # TASK 2: Reorder searchableAttributes to [body, title] (body first).
        #         Re-run the basic search. Document in SOLUTIONS.md how the
        #         top-1 result changed and why (the `attribute` ranking
        #         rule).

        # TASK 3: Disable typo tolerance entirely (typoTolerance.enabled =
        #         False) and re-run "pythn async". Document the result.
        #         Conclude in SOLUTIONS.md whether typo tolerance is
        #         "essential" or "optional" for your use case.


if __name__ == "__main__":
    asyncio.run(run_demo())
