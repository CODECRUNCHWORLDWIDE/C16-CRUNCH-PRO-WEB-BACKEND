# Mini-project — `crunchsearch`

> *Take the W7 article service, plug in three search backends behind a single `/search` endpoint, run the relevance harness, run the latency benchmark, and ship the comparison report. The mini-project for Week 10 is not "build a search engine" — search engines are built. The mini-project is "pick the right one for your corpus, defend the pick with numbers, and wire the indexing pipeline so all three stay in sync with the source of truth."*

**Time**: ~7 hours over the second half of the week.

## What you are building

A FastAPI service (extending the W7 `crunchreader-api`) with:

1. A `POST /articles` and `PUT /articles/{id}` write path that publishes an `articles:changed` event to Redis Pub/Sub on every write.
2. Two ARQ workers that consume those events and keep OpenSearch and Meilisearch in sync with Postgres. (Postgres FTS is kept current automatically by the generated `tsvector` column.)
3. A `GET /search?q=...&backend=postgres|opensearch|meili` endpoint that routes to whichever backend the caller picks (default Postgres FTS).
4. A relevance harness in `harness/` that runs a 30-query set against all three backends and produces `RELEVANCE.md`.
5. A latency benchmark in `bench/` that runs `hey` against each backend's `/search` endpoint and produces `BENCHMARK.md`.

By Sunday evening, your repo has both `RELEVANCE.md` and `BENCHMARK.md` checked in, and the README defends the default backend with the numbers from both.

## The architecture

```text
                   write path                                         search path
                  POST /articles                                  GET /search?q=...
                       |                                                |
                       v                                                v
                  +----------+                                  +----------------+
                  | FastAPI  |                                  | FastAPI router |
                  |  router  |                                  |    /search     |
                  +----+-----+                                  +--------+-------+
                       |                                                 |
                       v                                                 |  routes to one of:
                  +----------+                                           v
                  | Postgres |  <-- source-of-truth -->                  *
                  |   table  |                                /       |        \
                  +----+-----+                       Postgres   OpenSearch   Meili
                       |                              FTS         (BM25)    (typo)
                       v
              +--------+--------+
              | Redis Pub/Sub   |
              | articles:changed|
              +---+----------+--+
                  |          |
                  v          v
              +-------+   +-------+
              | ARQ:  |   | ARQ:  |
              | os-idx|   | mei-id|
              +---+---+   +---+---+
                  |           |
                  v           v
              +-------+   +-------+
              | Open  |   | Meili |
              | Search|   | search|
              +-------+   +-------+
```

Six moving parts:

- **Postgres** holds the source-of-truth `articles` table with the `tsv` generated column and the `GIN` index. Search via `tsv @@ websearch_to_tsquery(...)`.
- **Redis** is the Pub/Sub bus. The article write handlers publish `articles:changed` events (`{"id": 42, "op": "upsert"}` or `{"id": 42, "op": "delete"}`).
- **ARQ worker 1** subscribes; on each event, re-fetches the article from Postgres and upserts (or deletes) it in OpenSearch.
- **ARQ worker 2** subscribes; same thing for Meilisearch.
- **The `/search` endpoint** dispatches based on the `backend` query parameter.
- **The harness** and **benchmark** scripts hit `/search` and write reports.

## Step-by-step plan

### Day 1 — wire the indexing pipeline (Thursday, ~2 h)

1. Apply the migration that adds the `tsv` column and the indexes (from `homework.md` Problem 1).
2. Add the `articles:changed` Pub/Sub publish to the write handlers.
3. Write the two ARQ workers. Each subscribes to `articles:changed`, fetches the article from Postgres, calls `client.index(...)`.
4. Seed the corpus: re-fetch every article from Postgres and reindex into OpenSearch and Meilisearch (a one-off bulk job).

Acceptance: `POST /articles` → wait 2 seconds → `GET /search?backend=opensearch&q=...` returns the new article. Same for `backend=meili`.

### Day 2 — wire the `/search` endpoint (Friday, ~2 h)

1. Define the Pydantic v2 `SearchResponse` and `SearchHit` models in `schemas.py`.
2. Write three backend implementations: `search_postgres`, `search_opensearch`, `search_meili`. Each takes `(query: str, limit: int, offset: int)` and returns `SearchResponse`.
3. Write the `/search` router that dispatches based on the `backend` query parameter (default `"postgres"`).
4. Add a basic test for each backend.

Acceptance: all three `GET /search?backend=...&q=python` return populated `SearchResponse` payloads with consistent shape.

### Day 3 — build and run the harness (Saturday, ~2 h)

1. Pick 30 queries from a real corpus. Hand-label expected top-5 IDs.
2. Implement `harness/run.py`. For each query, run against each backend; compute precision-at-5.
3. Write the output to `RELEVANCE.md` with per-backend per-category breakdown.
4. Interpret the numbers in a two-paragraph summary.

Acceptance: `python harness/run.py` produces `RELEVANCE.md` deterministically (same numbers on re-run).

### Day 4 — benchmark and write up (Saturday/Sunday, ~1 h)

1. Implement `bench/run.sh` (or a `bench/run.py` that shells out to `hey`).
2. Run `hey -n 1000 -c 20` against each backend's `/search` endpoint with a representative query mix.
3. Capture p50, p95, p99, throughput per backend.
4. Write `BENCHMARK.md` with the table.
5. Update the service README's "Search architecture" section with the default backend choice and the numbers.

Acceptance: `RELEVANCE.md` and `BENCHMARK.md` are committed; the README defends the default with both.

## Required deliverables

- [ ] `crunchsearch/` package with `routers_search.py`, `clients/{postgres.py, opensearch.py, meili.py}`, `schemas.py`, `settings.py`, `workers.py`.
- [ ] `migrations/` with the Postgres FTS migration (idempotent).
- [ ] `harness/` with `run.py` and `queries.json`.
- [ ] `bench/` with a script that runs `hey` against all three backends.
- [ ] `RELEVANCE.md` with the precision-at-5 table.
- [ ] `BENCHMARK.md` with the latency table.
- [ ] `README.md` "Search architecture" section.
- [ ] Tests: at least one round-trip per backend, plus the harness reproducibility test.

## What the `BENCHMARK.md` should look like

```text
# Search backend benchmark

## Setup
- Postgres 16.4, OpenSearch 2.17.0, Meilisearch 1.10
- Corpus: 10 000 articles from HN Algolia dump
- Hardware: MacBook Pro M3 16 GB, all services local
- Load tool: hey 0.1.4
- Queries: 30 representative queries from harness/queries.json

## Latency under hey -n 1000 -c 20

| Backend     | p50  | p95   | p99   | RPS  |
|-------------|-----:|------:|------:|-----:|
| Postgres    | 18ms |  42ms |  61ms | 1083 |
| OpenSearch  | 11ms |  29ms |  44ms | 1620 |
| Meilisearch |  3ms |   9ms |  14ms | 3210 |

## Interpretation
[2-3 paragraphs covering: latency winner, why each backend lands where it does,
caveats (cold start, network on production, etc.)]
```

The numbers are illustrative; yours will differ.

## What the `RELEVANCE.md` should look like

```text
# Search backend relevance

## Setup
- 30 queries, hand-labelled top-5
- Corpus: same 10 000 article HN dump
- Categories: single-term (10), multi-term (10), phrase (5), misspelled (5)

## Precision-at-5 by category

| Category    | Postgres | OpenSearch | Meilisearch |
|-------------|---------:|-----------:|------------:|
| single-term |     0.92 |       0.94 |        0.90 |
| multi-term  |     0.75 |       0.81 |        0.78 |
| phrase      |     0.84 |       0.88 |        0.62 |
| misspelled  |     0.10 |       0.22 |        0.84 |
| **overall** | **0.65** |   **0.71** |    **0.79** |

## Interpretation
[Which backend won overall, where each was strong, the recommendation, the
operational considerations that also feed the picker.]
```

## Stretch goals

- **A `?facet=author,tags` query parameter** that, when the backend supports it (OpenSearch and Meilisearch), returns the facet distribution alongside the hits. Postgres falls back to a separate `GROUP BY` query for the same effect.
- **An autocomplete endpoint** (`GET /search/suggest?prefix=pyt`) backed by Meilisearch's prefix-match. Useful UX for search-as-you-type.
- **A reindex script** (Challenge 2). When you change the OpenSearch analyzer, the script does the alias-swap reindex with one command.
- **A `?backend=auto` mode** that picks the backend per query category — short queries to Meilisearch (typo tolerance wins), long queries to OpenSearch (BM25 wins), exact-id-style queries to Postgres (the `B-tree` wins).

## Pitfalls

1. **Forgetting to seed the secondary backends after rebuilding the corpus.** The Postgres `tsv` column is auto-updated; OpenSearch and Meilisearch are not. After every fresh `articles` table seed, run a `crunchsearch bulk-reindex` to refill the secondary backends.
2. **The Pub/Sub bus losing messages on worker restart.** If the worker is down when the event fires, the event is lost. Mitigation: a periodic reconciliation job (a "since `last_indexed_at` reindex") that closes the gap on worker downtime.
3. **Reading the benchmark numbers without warming up.** The first request to OpenSearch is slow (JVM warmup, index cache cold). Run `hey -z 30s` first as a warmup; throw away the numbers; then run the actual benchmark.
4. **Tuning relevance based on the latency table.** Latency does not measure relevance; relevance does not measure latency. Tune separately. The mini-project produces both numbers so they can be considered together — not so one substitutes for the other.

## Up next

Once the mini-project is complete, Week 11 turns its eye to observability. The four numbers you committed to `BENCHMARK.md` become four time-series. The `precision_at_5` cell in `RELEVANCE.md` becomes a CI metric. The "Search architecture" section in the README becomes a Grafana dashboard with the indexing-lag and the query-mix and the per-backend error rate on it. The discipline of measuring what matters carries from this week into the next.
