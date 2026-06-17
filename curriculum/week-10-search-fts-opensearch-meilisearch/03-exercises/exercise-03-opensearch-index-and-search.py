"""
Exercise 3 — OpenSearch: index a corpus with a custom analyzer; search
with multi_match boosts and a bool query; aggregate by author and tags;
highlight the matched substring.

Time:   ~1.5 hours.
Goal:   Create an OpenSearch index with a custom English analyzer; bulk
        index the seed corpus; run multi_match queries with field boosts;
        compose a bool query with filter and must clauses; request
        aggregations and highlighting in the same request.

Run:
    # 1. OpenSearch reachable on https://localhost:9200 with admin auth.
    docker run -d -p 9200:9200 -p 9600:9600 \
        -e "discovery.type=single-node" \
        -e "OPENSEARCH_INITIAL_ADMIN_PASSWORD=Crunch_Pro_W10_pw" \
        opensearchproject/opensearch:2.17.0

    # 2. Confirm.
    curl -ku admin:Crunch_Pro_W10_pw https://localhost:9200/

    # 3. Run.
    pip install 'opensearch-py==2.7.*'
    python3 exercise-03-opensearch-index-and-search.py

Try:
    Read the analyzer definition. Note that `crunch_english` uses
    `standard` tokenizer + lowercase + english_stop + english_stemmer.
    Run the script and observe: queries match stemmed terms; the
    aggregations return per-bucket document counts; highlight returns
    <em>-wrapped snippets.

Cited:
    - https://opensearch.org/docs/latest/api-reference/index-apis/create-index/
    - https://opensearch.org/docs/latest/query-dsl/full-text/multi-match/
    - https://opensearch.org/docs/latest/aggregations/

The TASK comments below mark prompts you should answer in SOLUTIONS.md.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

try:
    from opensearchpy import AsyncOpenSearch
    from opensearchpy.helpers import async_bulk
except ImportError:  # pragma: no cover
    AsyncOpenSearch = None  # type: ignore[assignment, misc]
    async_bulk = None  # type: ignore[assignment]


logger = logging.getLogger("opensearch_exercise")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


OS_HOST = os.environ.get("CC_W10_OS_HOST", "localhost")
OS_PORT = int(os.environ.get("CC_W10_OS_PORT", "9200"))
OS_USER = os.environ.get("CC_W10_OS_USER", "admin")
OS_PASS = os.environ.get("CC_W10_OS_PASS", "Crunch_Pro_W10_pw")
INDEX = "cc_w10_articles"


# ---------------------------------------------------------------------------
# Part A — The seed corpus
# ---------------------------------------------------------------------------


SEED_ARTICLES: list[dict[str, Any]] = [
    {
        "id": 1,
        "title": "Python async generators",
        "body": "Async generators in Python yield values lazily.",
        "author": "Avrot, Laetitia",
        "tags": ["python", "async", "tutorial"],
        "published_at": "2025-09-15T10:30:00Z",
    },
    {
        "id": 2,
        "title": "Asynchronous Django views",
        "body": "Django supports asynchronous view handlers since 3.1.",
        "author": "Manning, Christopher",
        "tags": ["django", "async", "tutorial"],
        "published_at": "2025-08-01T08:00:00Z",
    },
    {
        "id": 3,
        "title": "FastAPI dependencies and Pydantic v2",
        "body": "FastAPI's dependency injection composes with Pydantic v2.",
        "author": "Avrot, Laetitia",
        "tags": ["fastapi", "pydantic", "tutorial"],
        "published_at": "2025-10-20T12:00:00Z",
    },
    {
        "id": 4,
        "title": "Postgres full-text search",
        "body": "Postgres ships tsvector and tsquery types and ts_rank functions.",
        "author": "Bost, Craig",
        "tags": ["postgres", "search"],
        "published_at": "2024-06-12T14:15:00Z",
    },
    {
        "id": 5,
        "title": "Build a search bar",
        "body": "The user-facing search bar should accept a free-form query.",
        "author": "Turnbull, Doug",
        "tags": ["search", "ux"],
        "published_at": "2025-03-22T09:45:00Z",
    },
]


# ---------------------------------------------------------------------------
# Part B — The index settings and mapping
# ---------------------------------------------------------------------------


INDEX_BODY: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "crunch_english": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "english_stop", "english_stemmer"],
                }
            },
            "filter": {
                "english_stop":    {"type": "stop", "stopwords": "_english_"},
                "english_stemmer": {"type": "stemmer", "language": "english"},
            },
        },
    },
    "mappings": {
        "properties": {
            "title": {
                "type": "text",
                "analyzer": "crunch_english",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "body":         {"type": "text", "analyzer": "crunch_english"},
            "author":       {"type": "keyword"},
            "tags":         {"type": "keyword"},
            "published_at": {"type": "date"},
        }
    },
}


# ---------------------------------------------------------------------------
# Part C — Client factory
# ---------------------------------------------------------------------------


def make_client() -> Any:
    """Open an AsyncOpenSearch client against the local container."""
    if AsyncOpenSearch is None:
        raise RuntimeError("opensearch-py is not installed; pip install opensearch-py")
    return AsyncOpenSearch(
        hosts=[{"host": OS_HOST, "port": OS_PORT}],
        http_auth=(OS_USER, OS_PASS),
        use_ssl=True,
        verify_certs=False,
        ssl_show_warn=False,
    )


# ---------------------------------------------------------------------------
# Part D — Reset and seed
# ---------------------------------------------------------------------------


async def reset_index(client: Any) -> None:
    """Drop the index if it exists; recreate it; refresh."""
    exists = await client.indices.exists(index=INDEX)
    if exists:
        await client.indices.delete(index=INDEX)
        logger.info("dropped existing index %s", INDEX)
    await client.indices.create(index=INDEX, body=INDEX_BODY)
    logger.info("created index %s", INDEX)


async def bulk_index(client: Any, docs: list[dict[str, Any]]) -> None:
    """Bulk-index the seed corpus via the async_bulk helper."""

    async def gen() -> Any:
        for doc in docs:
            yield {
                "_index": INDEX,
                "_id":    str(doc["id"]),
                "_source": doc,
            }

    if async_bulk is None:  # pragma: no cover
        raise RuntimeError("opensearch-py async_bulk helper is not available")
    success, failed = await async_bulk(client, gen(), chunk_size=500)
    logger.info("bulk indexed: success=%s failed=%s", success, failed)
    await client.indices.refresh(index=INDEX)


# ---------------------------------------------------------------------------
# Part E — Search variants
# ---------------------------------------------------------------------------


async def match_search(client: Any, q: str) -> list[dict[str, Any]]:
    """Single-field match against the body."""
    body = {"query": {"match": {"body": q}}, "size": 25}
    result = await client.search(index=INDEX, body=body)
    return [hit["_source"] | {"_score": hit["_score"]} for hit in result["hits"]["hits"]]


async def multi_match_search(client: Any, q: str) -> list[dict[str, Any]]:
    """Multi-field with title boosted 3x."""
    body = {
        "query": {
            "multi_match": {
                "query": q,
                "fields": ["title^3", "body"],
                "type": "best_fields",
            }
        },
        "size": 25,
    }
    result = await client.search(index=INDEX, body=body)
    return [hit["_source"] | {"_score": hit["_score"]} for hit in result["hits"]["hits"]]


async def bool_search(client: Any, q: str, tag: str) -> list[dict[str, Any]]:
    """Bool query: must match q in body; filter by tag; must_not match a banned author."""
    body = {
        "query": {
            "bool": {
                "must":     [{"match": {"body": q}}],
                "filter":   [{"term":  {"tags": tag}}],
                "must_not": [{"term":  {"author": "spammer"}}],
            }
        },
        "size": 25,
    }
    result = await client.search(index=INDEX, body=body)
    return [hit["_source"] | {"_score": hit["_score"]} for hit in result["hits"]["hits"]]


async def search_with_aggs_and_highlight(client: Any, q: str) -> dict[str, Any]:
    """Multi-match with highlight, plus aggregations by author and tag."""
    body = {
        "query": {
            "multi_match": {"query": q, "fields": ["title^3", "body"]}
        },
        "size": 25,
        "highlight": {
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
            "fields": {
                "title": {"number_of_fragments": 0},
                "body":  {"number_of_fragments": 2, "fragment_size": 80},
            },
        },
        "aggs": {
            "by_author": {"terms": {"field": "author", "size": 10}},
            "by_tag":    {"terms": {"field": "tags",   "size": 20}},
            "by_month":  {
                "date_histogram": {"field": "published_at", "calendar_interval": "month"}
            },
        },
    }
    result = await client.search(index=INDEX, body=body)
    return {
        "hits": [
            {
                "_score": hit["_score"],
                "title":  hit["_source"]["title"],
                "highlight": hit.get("highlight", {}),
            }
            for hit in result["hits"]["hits"]
        ],
        "aggs": result.get("aggregations", {}),
    }


# ---------------------------------------------------------------------------
# Part F — The driver
# ---------------------------------------------------------------------------


async def run_demo() -> None:
    """Reset, seed, and run the four search variants."""
    if AsyncOpenSearch is None:
        logger.error("opensearch-py is not installed; pip install opensearch-py")
        return

    client = make_client()
    try:
        await reset_index(client)
        await bulk_index(client, SEED_ARTICLES)

        print("\n=== match on body for 'python' ===")
        for hit in await match_search(client, "python"):
            print(f"  {hit['_score']:.3f}  {hit['title']}")

        print("\n=== multi_match with title^3 for 'python async' ===")
        for hit in await multi_match_search(client, "python async"):
            print(f"  {hit['_score']:.3f}  {hit['title']}")

        print("\n=== bool: must='python' AND filter tags='async' ===")
        for hit in await bool_search(client, "python", "async"):
            print(f"  {hit['_score']:.3f}  {hit['title']}")

        print("\n=== Highlighted + aggregated multi_match for 'python async' ===")
        composite = await search_with_aggs_and_highlight(client, "python async")
        for hit in composite["hits"]:
            print(f"  {hit['_score']:.3f}  {hit['title']}")
            if hit["highlight"]:
                for field, fragments in hit["highlight"].items():
                    for frag in fragments:
                        print(f"    [{field}] {frag}")
        print("  aggregations:")
        for agg_name, agg_body in composite["aggs"].items():
            buckets = agg_body.get("buckets", [])
            print(f"    {agg_name}:")
            for b in buckets:
                key = b.get("key_as_string", b.get("key"))
                print(f"      {key}: {b['doc_count']}")

        # TASK 1: Use _analyze to inspect what the crunch_english analyzer
        #         produces for "Asynchronous generators are running". Add
        #         the call to this file and document the tokens in
        #         SOLUTIONS.md.

        # TASK 2: Demonstrate the difference between match and match_phrase
        #         for the query "python async" — find a document order
        #         where the two return different top results. Document in
        #         SOLUTIONS.md.

        # TASK 3: Tune the BM25 k1 and b parameters for the title field
        #         (per Lecture 2 §4.1). Index a fresh `cc_w10_articles_v2`
        #         with `similarity = {k1: 0.5, b: 0.0}` on title and
        #         compare top-1 ordering. Document the comparison.

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(run_demo())
