# Week 10 — Homework

Six problems. About six hours of work. Submit one PR with the changes; reviewers will look for the numbers in the `BENCHMARK.md` and the `RELEVANCE.md` and the justification in the README.

---

## Problem 1 — Add Postgres FTS to the W7 articles service (1.5 h)

Take the W7 `crunchreader-api` service and add a `GET /articles/search?q=...` endpoint backed by Postgres FTS.

Acceptance:

- The migration adds the `tsv` generated column with weights `A` (title) and `B` (body), plus the `GIN` index. The migration is reversible.
- The endpoint accepts `q` (the query string), `limit` (default 25, max 100), `offset` (default 0).
- The endpoint returns a Pydantic v2 `SearchResponse` with `total: int`, `hits: list[SearchHit]`. `SearchHit` has `id`, `title`, `author`, `published_at`, `score`, `snippet`.
- The `snippet` field uses `ts_headline` with `<em>...</em>` wrapping.
- The endpoint uses `websearch_to_tsquery` (so user input never errors out).
- `EXPLAIN ANALYZE` on the underlying SQL shows `Bitmap Index Scan on articles_tsv_idx` (not `Seq Scan`).

Deliverable: the diff to the W7 service plus a one-paragraph note in the PR description explaining the weight choice (`A` vs `B` on title vs body).

---

## Problem 2 — Add the trigram fuzzy fallback (45 min)

Extend Problem 1: when the FTS query returns fewer than 5 results, fall back to a trigram-similarity search on the title.

Acceptance:

- `CREATE EXTENSION pg_trgm` is in the migration; the migration is idempotent (`CREATE EXTENSION IF NOT EXISTS`).
- A `GIN` index on `title gin_trgm_ops` is added.
- The endpoint composes FTS-then-trigram: if `len(fts_hits) >= 5`, return FTS hits; else, also run the trigram query and merge.
- The `SearchHit.score` field reflects whichever scorer matched (FTS score for FTS hits; trigram similarity for fallback hits). The response includes a `_source: "fts"` or `_source: "trigram"` so the client can distinguish.
- A test queries `pythn` (misspelled) and asserts at least one result is returned.

Deliverable: the diff plus the test.

---

## Problem 3 — Index the corpus into OpenSearch and add a second search endpoint (1.5 h)

Add a `GET /articles/search-os?q=...` endpoint backed by OpenSearch. The same Pydantic v2 `SearchResponse` shape; different backend.

Acceptance:

- An ARQ worker subscribes to a Redis Pub/Sub channel `articles:changed` (from W8). On each event, the worker fetches the article from Postgres and calls `client.index(index="articles", id=str(id), body=payload)`.
- The `POST /articles` and `PUT /articles/{id}` endpoints publish `articles:changed` events; the OpenSearch index is updated within seconds.
- The OpenSearch index uses a custom `crunch_english` analyzer (lowercase + english_stop + english_stemmer).
- The search endpoint uses `multi_match` with `title^3, body` boost and returns highlighting under `SearchHit.snippet`.
- A round-trip test: `POST /articles` a new article; sleep 2 seconds; `GET /articles/search-os?q=...` returns the new article.

Deliverable: the diff plus the round-trip test.

---

## Problem 4 — Index the corpus into Meilisearch and add a third search endpoint (1 h)

Add a `GET /articles/search-meili?q=...` endpoint backed by Meilisearch. The same `SearchResponse` shape.

Acceptance:

- A second ARQ worker (or a second consumer of `articles:changed`) keeps Meilisearch in sync. `await client.index("articles").add_documents([payload])` on upsert; `await client.index("articles").delete_document(article_id)` on delete.
- The Meilisearch index has `searchableAttributes = ["title", "body"]`, `filterableAttributes = ["author", "tags", "published_at"]`, `sortableAttributes = ["published_at", "view_count"]`.
- The endpoint accepts an optional `tag` filter; when present, the query includes `filter=f"tags = '{tag}'"`.
- A round-trip test: `POST /articles` with `tags=["python"]`; sleep 1 second; `GET /articles/search-meili?q=python&tag=python` returns the new article.

Deliverable: the diff plus the test.

---

## Problem 5 — Build the relevance harness, run it against all three backends (1 h)

Pick 20 queries spanning the categories from Challenge 1 (single-term, multi-term, phrase, misspelled, long). Hand-label expected top-5 IDs for each. Implement the harness; produce a `RELEVANCE.md` with the per-backend per-category precision-at-5 table.

Acceptance:

- The 20 queries plus expected results are committed as `queries.json` alongside the harness script.
- The script is one command to run: `python run_relevance_harness.py`.
- The output is `RELEVANCE.md` with the table and a two-paragraph interpretation.
- The summary recommends one backend (or a combination) as the default for the W7 service and defends the choice.

Deliverable: `queries.json`, the harness script, and `RELEVANCE.md`.

---

## Problem 6 — Defend the choice in a 1-page README section (15 min)

Add a section to the W7 service README titled "Search architecture", with:

1. The default backend (Postgres / OpenSearch / Meilisearch) and the reason in two sentences.
2. The non-default backends and when to use them (`?backend=opensearch` query parameter or similar).
3. The indexing pipeline diagram in ASCII or Mermaid: source-of-truth Postgres, the `articles:changed` Pub/Sub channel, the ARQ workers that feed each backend.
4. The reindex procedure (one-line summary of Challenge 2; full procedure linked to `REINDEX.md`).

Acceptance:

- The section is under 400 words.
- A future engineer can read the section and answer "where do I add a new search field?" without asking anyone.

Deliverable: the README diff.

---

## Submission checklist

- [ ] Migration applied and reversible (Problem 1).
- [ ] `pg_trgm` fallback works on misspelled queries (Problem 2).
- [ ] OpenSearch indexing pipeline keeps the index within 5 seconds of Postgres (Problem 3).
- [ ] Meilisearch indexing pipeline keeps the index within 5 seconds of Postgres (Problem 4).
- [ ] `RELEVANCE.md` has the precision-at-5 table and the recommendation (Problem 5).
- [ ] README's "Search architecture" section is checked into the repo (Problem 6).
- [ ] All `.py` files compile (`python3 -m py_compile <file>` returns clean).
- [ ] All endpoints have tests; the suite passes.

If anything blocks you for more than 30 minutes, post in the channel. The goal is to *finish* the homework — partial credit is better than perfect credit you ran out of time to deliver.
