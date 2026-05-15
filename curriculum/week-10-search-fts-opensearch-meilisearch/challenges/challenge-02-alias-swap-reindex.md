# Challenge 2 — Zero-downtime reindex with alias swap

**Time**: ~2 hours.

**Goal**: Reindex the article corpus into OpenSearch and Meilisearch with the application live, with zero search downtime, and with the new index reachable under the existing index name once the swap completes. Document the process in `REINDEX.md`.

## Why this matters

Sooner or later, you will change your analyzer chain, your mapping, your ranking rules, or the underlying schema of the documents you index. None of those changes can be applied to an existing OpenSearch index in place — they require a full reindex. If the reindex takes 30 minutes and the search is offline for those 30 minutes, that is an outage. The alias-swap pattern reindexes into a separate index with a different name, then atomically points the alias at the new index. Zero search downtime, no application-code changes, full rollback path.

For Meilisearch, the equivalent is the `swap_indexes` API (since Meilisearch 1.0).

## Prerequisites

- Exercises 3 and 4 working.
- A corpus of at least 1 000 documents in both backends (rebuild from your Challenge 1 corpus if you have it).
- An application that searches the index — for this challenge, the `search_opensearch` and `search_meilisearch` functions from Challenge 1 will do.

## Step 1 — OpenSearch: set up the alias

OpenSearch indexes can have aliases. The application queries the alias; the alias points at a concrete index. The setup:

```python
from __future__ import annotations

from typing import Any


async def setup_alias(client: Any) -> None:
    """Create articles_v1 with the current mapping, attach the 'articles' alias."""
    await client.indices.create(index="articles_v1", body=INDEX_BODY_V1)
    await client.indices.put_alias(index="articles_v1", name="articles")

    # Optional: confirm.
    aliases = await client.indices.get_alias(name="articles")
    print(aliases)  # {"articles_v1": {"aliases": {"articles": {}}}}
```

Now reindex any existing data:

```python
async def initial_bulk_index(client: Any, docs: list[dict[str, Any]]) -> None:
    """Bulk-index into articles_v1 — the alias target."""
    from opensearchpy.helpers import async_bulk

    async def gen() -> Any:
        for doc in docs:
            yield {"_index": "articles_v1", "_id": str(doc["id"]), "_source": doc}

    await async_bulk(client, gen(), chunk_size=500)
    await client.indices.refresh(index="articles_v1")
```

Verify: the application's `search_opensearch(client, "python")` returns results, with the application code using `index="articles"` (the alias), not `index="articles_v1"` (the concrete index).

## Step 2 — OpenSearch: build the new index

Define a new mapping with the change you want to apply. For this challenge, change the analyzer:

```python
INDEX_BODY_V2 = {
    **INDEX_BODY_V1,
    "settings": {
        **INDEX_BODY_V1["settings"],
        "analysis": {
            "analyzer": {
                "crunch_english_v2": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "asciifolding",   # NEW: strip diacritics
                        "english_stop",
                        "english_stemmer",
                    ],
                }
            },
            "filter": INDEX_BODY_V1["settings"]["analysis"]["filter"],
        },
    },
}
# Point the title and body at the v2 analyzer.
INDEX_BODY_V2["mappings"]["properties"]["title"]["analyzer"] = "crunch_english_v2"
INDEX_BODY_V2["mappings"]["properties"]["body"]["analyzer"]  = "crunch_english_v2"
```

Create `articles_v2`:

```python
async def create_v2(client: Any) -> None:
    """Create the v2 index. Alias still points at v1; application is undisturbed."""
    await client.indices.create(index="articles_v2", body=INDEX_BODY_V2)
```

## Step 3 — OpenSearch: bulk-reindex into v2

Two options:

### Option A — re-fetch from source-of-truth Postgres

The cleanest pattern. Source-of-truth data lives in Postgres; OpenSearch is a view. Re-fetch and re-index:

```python
async def reindex_from_postgres(client: Any, pg_pool: Any) -> None:
    from opensearchpy.helpers import async_bulk

    async def gen() -> Any:
        async with pg_pool.acquire() as conn:
            async for row in conn.cursor("SELECT id, title, body, author, tags, published_at FROM articles_w10;"):
                yield {
                    "_index": "articles_v2",
                    "_id":    str(row["id"]),
                    "_source": dict(row),
                }

    await async_bulk(client, gen(), chunk_size=500)
    await client.indices.refresh(index="articles_v2")
```

### Option B — use the OpenSearch `_reindex` API

```python
async def reindex_v1_to_v2(client: Any) -> None:
    await client.reindex(
        body={
            "source": {"index": "articles_v1"},
            "dest":   {"index": "articles_v2"},
        },
        wait_for_completion=False,  # returns a task ID; check status separately
    )
```

The `_reindex` API runs server-side in OpenSearch, which is faster than streaming the documents through Python. Use it when the corpus is huge or when re-fetching from Postgres is expensive.

## Step 4 — OpenSearch: dual-write during the reindex

If the application is also writing to the index during the reindex (creating new articles, updating existing ones), those writes need to land in both `articles_v1` and `articles_v2`. Otherwise, when you swap the alias, the new index is missing writes that happened during the reindex.

Two approaches:

1. **Dual-write in the indexing worker**: every write goes to both `articles_v1` and `articles_v2`. Cleanest; requires a feature flag to enable/disable.
2. **Catch-up phase**: after the bulk reindex completes, query the source-of-truth for all rows with `updated_at > <start_of_reindex>` and reindex just those into `articles_v2`. Repeat until the catch-up window is empty.

For this challenge, use the dual-write approach. Modify your indexing worker to write to both `articles_v1` and `articles_v2` for the duration; remove the dual-write after the swap.

## Step 5 — OpenSearch: the atomic swap

The actual swap is one API call:

```python
async def swap_alias(client: Any) -> None:
    await client.indices.update_aliases(
        body={
            "actions": [
                {"remove": {"index": "articles_v1", "alias": "articles"}},
                {"add":    {"index": "articles_v2", "alias": "articles"}},
            ]
        }
    )
```

The `update_aliases` call applies all actions atomically. Between the `remove` and the `add` there is no observable state where `articles` points at neither index. The application's `search(index="articles", ...)` queries `articles_v1` one moment, `articles_v2` the next, with no in-between zero-result window.

## Step 6 — OpenSearch: clean up

After a soak period (24 hours, or whatever your rollback window is), delete the old index:

```python
async def cleanup(client: Any) -> None:
    await client.indices.delete(index="articles_v1")
```

If anything goes wrong with `articles_v2` during the soak (relevance regression, mapping error, missing documents), the rollback is symmetric:

```python
async def rollback(client: Any) -> None:
    await client.indices.update_aliases(
        body={
            "actions": [
                {"remove": {"index": "articles_v2", "alias": "articles"}},
                {"add":    {"index": "articles_v1", "alias": "articles"}},
            ]
        }
    )
```

The rollback works *only if you have not deleted `articles_v1` yet*. The soak period is the window during which rollback is possible. Do not delete until you are confident.

## Step 7 — Meilisearch: index swap

Meilisearch as of v1.10 does not have first-class aliases; the equivalent is `swap_indexes`. The full flow:

```python
async def reindex_meili(client: Any, docs: list[dict[str, Any]]) -> None:
    # Build the new index with new settings.
    await client.create_index("articles_v2", primary_key="id")
    await client.index("articles_v2").update_settings(NEW_SETTINGS)
    task = await client.index("articles_v2").add_documents(docs)
    await client.wait_for_task(task.task_uid)

    # Atomic swap: the contents of the two indexes are exchanged.
    # After this call, "articles" contains what "articles_v2" contained,
    # and vice versa.
    await client.swap_indexes([("articles", "articles_v2")])

    # Delete what is now the old version (currently held under articles_v2).
    await client.delete_index("articles_v2")
```

The `swap_indexes` call is the Meilisearch equivalent of `update_aliases`. Both atomically reroute the application's traffic from the old index to the new.

## Step 8 — Document in `REINDEX.md`

Write up the process. Include:

1. **The motivation**: what schema/analyzer/setting change required the reindex.
2. **The pre-reindex plan**: the steps you intend to take, in order, with the rollback path.
3. **The actual timeline**: when each step ran, how long each took, whether anything surprising happened.
4. **The post-reindex verification**: which queries you re-ran to confirm relevance did not regress; whether the precision-at-5 numbers from Challenge 1 still hold.
5. **A retro**: what would you do differently next time. (For most teams, the answer is "more dual-write soak time" or "smaller reindex batches".)

## Acceptance criteria

- [ ] The OpenSearch alias swap works without dropping any queries.
- [ ] The Meilisearch index swap works without dropping any queries.
- [ ] During the reindex, any new writes to the application are visible in both the old and new index (you can verify by querying both directly with `index="articles_v1"` and `index="articles_v2"`).
- [ ] After the swap, the application code is unchanged — it still queries `index="articles"`.
- [ ] The rollback path is documented and you have done at least one dry run of rolling back.
- [ ] `REINDEX.md` covers the seven points above.

## Pitfalls

1. **Forgetting the dual-write**. Writes that land only in `articles_v1` during the reindex are lost when the swap happens. The reindex from source-of-truth Postgres mitigates this (because Postgres has all writes), but the catch-up phase must cover the gap.
2. **Refresh timing**. The new index must be refreshed before the swap, or the first query after the swap may return stale results (zero or fewer hits than expected). Call `await client.indices.refresh(index="articles_v2")` before the swap.
3. **Mapping conflicts**. If `articles_v1` has a field as `keyword` and `articles_v2` has the same field as `text`, queries that worked on v1 may error on v2. Test the application's queries against `articles_v2` directly (using the concrete index name) before the swap.
4. **Deleting too soon**. Wait at least 24 hours before deleting `articles_v1`; longer if your team has a longer rollback window expectation. Storage is cheap; lost rollback capability is expensive.

## Stretch

If you finish early, automate the reindex into a single script with command-line arguments:

```text
python reindex.py --backend opensearch --from articles_v1 --to articles_v2 --apply-settings settings.json
python reindex.py --backend meilisearch --from articles --to articles_v2 --apply-settings settings.json
```

The script should:

1. Validate the new settings file.
2. Create the new index with the new settings.
3. Run the bulk reindex.
4. Verify document counts match.
5. Run a smoke-test query set (a 10-query subset of Challenge 1's set) and assert no zero-result queries.
6. Prompt for confirmation, then swap.

The first time you reindex, do it by hand to learn the steps. After that, automate.
