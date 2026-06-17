# Challenge 1 — The three-backend relevance harness

**Time**: ~3 hours.

**Goal**: Build a query set, hand-label expected results, run the queries through all three search backends, compute precision-at-5 per backend, and write the comparison table that lets you defend a backend choice on something other than vibes.

## The deliverable

A file `RELEVANCE.md` with:

1. The 50 queries you used, with expected top-5 results per query.
2. A precision-at-5 table — one row per backend (Postgres FTS, OpenSearch, Meilisearch), one column per query category (single-term, multi-term, phrase, misspelled, technical).
3. A two-paragraph summary: which backend won overall, where each backend was strong, where each was weak.
4. A two-sentence recommendation: which backend you would default to for the W7 service, and why.

The file goes into your repository alongside the mini-project. The number in cell `(Meilisearch, misspelled)` is the most important single number from this week.

## Prerequisites

- Exercises 1 through 4 working — you have all three backends indexed with a comparable corpus.
- A larger corpus than the 5–7 article seed used in the exercises. Use one of:
  - **Hacker News stories**: dump 10 000 stories via the Algolia HN API (<https://hn.algolia.com/api>). Free, ~5 MB.
  - **arXiv abstracts**: bulk download a subject category (e.g. cs.PL) from <https://export.arxiv.org/oai2>. Free, ~50 MB for one category.
  - **The MS-MARCO passage corpus** (commonly used in IR research): <https://microsoft.github.io/msmarco/Datasets>. Free, ~3 GB for the full passage corpus; sample a manageable subset.
  - **Your own data** if you have a domain corpus available (your team's GitHub issues, your company's docs site, etc.).

The corpus needs to be at least 5 000 documents for the relevance numbers to mean anything. Below 1 000, every backend trivially nails most queries; above 50 000, the difference between backends gets sharp and the harness is most informative.

## Step 1 — Build the query set

Pick 50 queries. Distribute roughly:

- **10 single-term queries** (`python`, `django`, `pydantic`, ...) — testing pure term recall.
- **15 multi-term unquoted queries** (`python async`, `fastapi pydantic`, `postgres index`, ...) — the bulk of real-world queries.
- **5 quoted phrase queries** (`"async generator"`, `"connection pool"`, ...) — testing phrase matching.
- **10 misspelled queries** (`pythn`, `posgres`, `asyncrnous`, `dependeny injection`, ...) — testing typo tolerance.
- **10 long technical queries** (`how to migrate from sync to async django`, `n+1 query in fastapi with sqlalchemy`, ...) — testing query length and term-spread handling.

For each query, write the expected top-5 document IDs. This is the hardest step. The rule: do not look at any backend's output. Decide what the *right* answer is, then measure how often each backend produces it.

You will disagree with yourself. The "right" top-5 for `python` in a 10 000-document corpus is not obvious. That is fine — the harness's job is not to find the absolute truth; it is to be *consistent*. The same query against three backends, scored against the same expected set, gives you three comparable numbers.

```python
from __future__ import annotations

from typing import Any

# Example query set; expand to 50.
QUERIES: list[dict[str, Any]] = [
    {
        "query": "python async",
        "category": "multi-term",
        "expected_ids": [42, 117, 203, 891, 944],
    },
    {
        "query": "pythn async",
        "category": "misspelled",
        "expected_ids": [42, 117, 203, 891, 944],  # same as above; we want typo tolerance to surface these
    },
    {
        "query": '"async generator"',
        "category": "phrase",
        "expected_ids": [42, 891],
    },
    # ... 47 more
]
```

## Step 2 — Wire the three backends

For each backend, build a function `search_<backend>(query: str, limit: int = 25) -> list[int]` that returns the ranked document IDs.

### Postgres

```python
from __future__ import annotations

from typing import Any

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]


async def search_postgres(
    pool: "asyncpg.Pool", query: str, limit: int = 25
) -> list[int]:
    sql = """
        SELECT id
        FROM articles_w10
        WHERE tsv @@ websearch_to_tsquery('english', $1)
        ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('english', $1), 32) DESC
        LIMIT $2;
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, query, limit)
    if len(rows) >= 5:
        return [r["id"] for r in rows]
    # Trigram fallback for sparse FTS results.
    sql_trgm = """
        SELECT id
        FROM articles_w10
        WHERE title %% $1
        ORDER BY similarity(title, $1) DESC
        LIMIT $2;
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql_trgm, query, limit)
    return [r["id"] for r in rows]
```

### OpenSearch

```python
async def search_opensearch(client: Any, query: str, limit: int = 25) -> list[int]:
    body = {
        "query": {
            "multi_match": {"query": query, "fields": ["title^3", "body"]}
        },
        "size": limit,
    }
    result = await client.search(index="articles", body=body)
    return [int(hit["_id"]) for hit in result["hits"]["hits"]]
```

### Meilisearch

```python
async def search_meilisearch(client: Any, query: str, limit: int = 25) -> list[int]:
    index = client.index("articles")
    result = await index.search(query, limit=limit)
    return [int(hit["id"]) for hit in result.hits]
```

## Step 3 — Run the harness

```python
def precision_at_k(returned: list[int], expected: set[int], k: int = 5) -> float:
    top_k = returned[:k]
    if not top_k:
        return 0.0
    return sum(1 for d in top_k if d in expected) / k


async def evaluate_backend(
    queries: list[dict[str, Any]],
    search_fn: Any,
) -> dict[str, float]:
    by_category: dict[str, list[float]] = {}
    for q in queries:
        returned = await search_fn(q["query"], limit=25)
        score = precision_at_k(returned, set(q["expected_ids"]), k=5)
        by_category.setdefault(q["category"], []).append(score)
    return {
        cat: sum(scores) / len(scores) if scores else 0.0
        for cat, scores in by_category.items()
    }
```

Run it for each backend; collect the per-category results into a table.

## Step 4 — The table

The output, in `RELEVANCE.md`:

```text
| Category    | Postgres FTS | OpenSearch | Meilisearch |
|-------------|-------------:|-----------:|------------:|
| single-term |         0.92 |       0.94 |        0.90 |
| multi-term  |         0.75 |       0.81 |        0.78 |
| phrase      |         0.84 |       0.88 |        0.62 |
| misspelled  |         0.10 |       0.22 |        0.84 |
| long-tech   |         0.41 |       0.58 |        0.52 |
| **overall** |     **0.60** |   **0.69** |    **0.73** |
```

(Your numbers will differ; the point is the shape.)

## Step 5 — The interpretation

Two paragraphs in `RELEVANCE.md`:

> Paragraph 1: which backend won overall and by how much; which categories favoured which backend; whether the gaps are large enough to matter (>10 percentage points usually does; 1-2 points is in the noise).
>
> Paragraph 2: the operational considerations that *also* go into the picker. Cost (Meilisearch is one container; OpenSearch is a cluster). Latency (measure separately; the relevance harness does not). Team familiarity. Existing infrastructure.

## Acceptance criteria

- [ ] At least 50 queries with hand-labelled expected results.
- [ ] All three backends return non-empty results for at least 40 queries each.
- [ ] The precision-at-5 table is in `RELEVANCE.md`.
- [ ] The recommendation is concrete: a backend name and a one-paragraph defence.
- [ ] The script is reproducible: re-running it against the same corpus produces the same numbers (±2 percentage points for OpenSearch, which has cluster-state-dependent IDF; same numbers exactly for Postgres and Meilisearch).

## Pitfalls to avoid

1. **Labelling after looking at results.** If you check what Postgres returned for `python async` and *then* decide the expected top-5, you have just labelled the test against itself. Decide expected first; run later.
2. **Tiny corpus.** Below 1 000 documents, every backend nails every easy query, and you cannot distinguish. Build a corpus of at least 5 000 documents.
3. **Misspellings that are still tokens.** `pyhton` is a typo; `pythn` is a typo. `python3` is *not* a typo of `python` — it is a different token. Watch for queries where you expect typo tolerance to fix something that is actually a different word.
4. **Measuring with different limits.** All three backends must be measured at the same `limit` value; otherwise precision-at-5 is meaningless. Use 25 (so each backend has headroom) and compute p@5 on the top-5 of the returned list.

## Stretch

If you finish early, repeat the harness with **mean reciprocal rank (MRR)** instead of precision-at-5:

```python
def mrr(returned: list[int], expected: set[int]) -> float:
    for i, doc_id in enumerate(returned, start=1):
        if doc_id in expected:
            return 1.0 / i
    return 0.0
```

MRR rewards getting *any* relevant document near the top; p@5 rewards getting *several* relevant documents in the top 5. The two correlate but disagree at the edges. The disagreement is often instructive — it tells you whether your corpus rewards "one perfect hit" or "five plausible hits".
