# Week 10 — Search: Postgres FTS, OpenSearch, Meilisearch

> *Week 9 made reads cheap. Week 10 makes them findable. The endpoint that returns "the 25 most recently published articles" is one `ORDER BY published_at DESC LIMIT 25` away. The endpoint that returns "the 25 articles most relevant to `python async generators`" is a different beast: it has to tokenise the query, normalise it (case-fold, stem, lemmatise, strip stop words), score every document against it, rank, paginate, and return. That is search, and it lives outside the `B-tree` index world your application database knows how to build. This week we add search to the W8/W9 service three ways — Postgres `tsvector`, OpenSearch, Meilisearch — measure each on the same corpus, and write the report that says when each is right.*

Welcome to Week 10 of **C16 · Crunch Pro Web Backend**. The `crunchreader-api` service now has a fast cache (W9), a clean write path (W7), and a non-blocking event surface (W8). The one thing it cannot do is *find* anything. A user who types "python async" in the search bar gets back articles whose title contains the substring "python async" — fine for short titles, useless for body text, and embarrassing for "python and asynchronous IO" which is the article they actually want. This week we fix that.

The work is *three tiers*, cheap-to-scalable. We do not pick one and stop. We build all three so that by Friday you have the data to defend "we used Postgres FTS because the corpus is 200 000 documents and the team is two engineers" with the same confidence as "we used OpenSearch because we needed custom analyzers and faceted aggregations" or "we used Meilisearch because typo-tolerance was the product requirement and ops budget was zero". The picker is not a flowchart; the picker is the table at the end of Lecture 1.

We approach the topic by reading the spec first. Postgres FTS is documented at <https://www.postgresql.org/docs/current/textsearch.html> — Chapter 12 of the manual, end to end, is the canonical reference for `tsvector`, `tsquery`, the parser, the dictionary chain, `ts_rank` / `ts_rank_cd`, and the `GIN` and `GiST` indexes. OpenSearch is documented at <https://opensearch.org/docs/latest/> — the analyzers, the query DSL, the BM25 scorer, the aggregations. Meilisearch is documented at <https://www.meilisearch.com/docs> — much smaller surface area, deliberately so. The reading load is moderate; the discipline is to read it.

By Sunday you will have:

1. **Postgres full-text search on the article body**, using a generated `tsvector` column over `title` and `body` with weights `A` and `B`, a `GIN` index on the column, and `ts_rank_cd` for relevance ordering. Phrase search via `phraseto_tsquery`. Fuzzy match via `pg_trgm` and the `%` operator for "the user mistyped 'pythn'" cases. Measured latency on a 100 000-document corpus.
2. **OpenSearch indexing of the same corpus**, via the `opensearch-py` client. A custom analyzer chain (standard tokenizer → lowercase → English stemmer → stop-word filter), a mapping with `text` versus `keyword` fields, BM25 scoring with field boosts, highlighting with `<em>` tags, and aggregations (facet by author, by tag, by month).
3. **Meilisearch indexing of the same corpus**, via the `meilisearch-python-sdk` client. Typo tolerance with the default `oneTypo`/`twoTypos` thresholds, custom ranking rules, filterable and facetable attributes, the `attributesToHighlight` and `attributesToCrop` settings.
4. **An indexing pipeline** that keeps all three search backends in sync with the source-of-truth database. The pattern is event-driven: every `INSERT` / `UPDATE` / `DELETE` on the `articles` table publishes a "search-index" event; three subscribers (the Postgres `tsvector` is a generated column so it is automatic; the OpenSearch indexer is an ARQ worker; the Meilisearch indexer is a second ARQ worker) keep their views fresh.
5. **A relevance harness**: 50 hand-labelled queries with the expected top-5 results; a script that runs each query against each backend; a precision-at-5 number per backend. We will *not* claim Meilisearch is "more accurate" than OpenSearch without the harness saying so on our corpus.
6. **A measured latency comparison**, with `hey` against the three search endpoints under identical load, and a `BENCHMARK.md` that reports p50 / p95 / p99 per backend.

The async story you have refined since Week 7 stays in the foreground. `asyncpg` for the Postgres FTS queries (a single `SELECT ... WHERE tsv @@ websearch_to_tsquery($1) ORDER BY ts_rank_cd(tsv, ...) DESC LIMIT 25`), `opensearch-py` with its `AsyncOpenSearch` client, `meilisearch-python-sdk`'s `AsyncClient`. Three clients, three query DSLs, one Pydantic v2 `SearchResult` model that flattens all three into a stable API contract for the frontend.

## Learning objectives

By the end of this week, you will be able to:

- **Build** a Postgres full-text search column from scratch: `ALTER TABLE articles ADD COLUMN tsv tsvector GENERATED ALWAYS AS (setweight(to_tsvector('english', coalesce(title, '')), 'A') || setweight(to_tsvector('english', coalesce(body, '')), 'B')) STORED;` followed by `CREATE INDEX articles_tsv_idx ON articles USING GIN (tsv);`. Understand what each piece does — the dictionary (`'english'`), the weights (`A` is 1.0, `B` is 0.4 by default; tunable via `set_curcfg`), the `GIN` versus `GiST` choice (`GIN` for read-heavy, `GiST` for write-heavy with updates), the `STORED` versus `VIRTUAL` generated-column trade-off. Cite the [Postgres textsearch chapter](https://www.postgresql.org/docs/current/textsearch.html) — section 12.2 for `tsvector`, 12.3 for parsing, 12.7 for ranking, 12.9 for the `GIN`/`GiST` indexes.
- **Write** the four flavours of Postgres text query and know when each is right: `to_tsquery('python & async')` (the strict boolean operators — punctuation is significant), `plainto_tsquery('python async')` (any-of-these-tokens, the friendly default), `phraseto_tsquery('python async generators')` (the exact phrase, with `<->` positional operator), `websearch_to_tsquery('"python async" -django')` (the Google-style syntax, with quotes for phrase and `-` for negation — the right choice for user-facing search bars). Cite the [Postgres docs §12.3.2](https://www.postgresql.org/docs/current/textsearch-controls.html).
- **Implement** ranking with `ts_rank` and `ts_rank_cd`: the difference (`ts_rank` is term frequency; `ts_rank_cd` is cover-density — it rewards documents where the query terms appear close together), the normalisation flags (`32 / (32 + count_of_doc_terms)` versus `1.0` versus `unique_terms`), the right default for short documents (`ts_rank_cd` with normalisation `32`) versus long ones (`ts_rank` with normalisation `1`). Cite §12.3.3.
- **Add** fuzzy / typo-tolerant matching to Postgres with `pg_trgm`: `CREATE EXTENSION pg_trgm;`, the `%` operator for "trigram similarity above the default threshold of 0.3", the `similarity(a, b)` function, the `GIN` index with `gin_trgm_ops`. The right use: a fallback layer on top of the `tsvector` query — if the `tsvector` returns zero hits, retry the user's terms with `%` against `title` and `body`. Cite the [pg_trgm docs](https://www.postgresql.org/docs/current/pgtrgm.html).
- **Index** the same corpus into **OpenSearch** with a custom analyzer chain. A working `articles` index has: a `mappings.properties` with `title` as `text` (analysed) plus `title.keyword` as `keyword` (exact-match for aggregations); a `settings.analysis.analyzer` declaring `crunch_english` as `standard` tokenizer plus `lowercase` plus `english_stemmer` plus `english_stop`; a `settings.analysis.filter` defining the two custom filters. Index a document with `await client.index(index="articles", id=str(article.id), body=article.dict())`. Cite the [OpenSearch index API](https://opensearch.org/docs/latest/api-reference/index-apis/create-index/) and the [analyzers reference](https://opensearch.org/docs/latest/analyzers/).
- **Query** OpenSearch with the search DSL. `match` for a single field; `multi_match` for several fields with boosts (`fields: ["title^3", "body"]`); `query_string` for the Lucene query syntax; `bool` for combinators (`must`, `should`, `must_not`, `filter`). Score with the default **BM25** (the Okapi BM25 formula, `k1=1.2`, `b=0.75`, tunable per field). Highlight with the `highlight` block. Facet with the `aggs` block (`terms` on `tags.keyword`, `date_histogram` on `published_at`). Cite the [OpenSearch search API](https://opensearch.org/docs/latest/api-reference/search/) and Elastic's BM25 explainer at <https://www.elastic.co/blog/practical-bm25-part-2-the-bm25-algorithm-and-its-variables> (the formula is identical; the explainer applies verbatim because OpenSearch forked Elasticsearch 7.10 and kept the scorer).
- **Index and query** **Meilisearch**. A working `articles` index has: a settings block with `searchableAttributes = ["title", "body"]` (order matters — earlier fields rank higher), `filterableAttributes = ["author", "tags", "published_at"]`, `sortableAttributes = ["published_at"]`. Index with `await client.index("articles").add_documents([...])`. Query with `await client.index("articles").search("python async", opts={"limit": 25, "attributesToHighlight": ["title", "body"]})`. Cite the [Meilisearch documentation](https://www.meilisearch.com/docs/learn/getting_started/quick_start) and the [ranking rules reference](https://www.meilisearch.com/docs/learn/relevancy/ranking_rules).
- **Distinguish** **write-time** from **read-time** analysis. Postgres lets you choose: the `tsvector` column is write-time (the tokens are computed and stored at `INSERT`/`UPDATE` time); the `websearch_to_tsquery('term')` is read-time (the query is tokenised at search time, in the same dictionary). OpenSearch is the same — `analyzer` on the mapping is write-time; `search_analyzer` on the mapping is read-time (defaulting to the write-time analyzer if unspecified). Meilisearch does not expose the distinction; it is fully managed. The implication: changing the analyzer requires re-indexing in Postgres and OpenSearch; in Meilisearch it does not (because Meilisearch stores all tokens up to a fuzzy distance, not a stemmed form).
- **Choose** the right backend for the right workload. The pickers are not "which is fastest" (all three are fast on small corpora). The pickers are: corpus size (Postgres FTS is comfortable through ~10 million rows on a well-indexed `tsvector`; OpenSearch starts paying off above ~50 million; Meilisearch is bounded by RAM and starts straining around 1–10 million depending on document size); relevance ceiling (Meilisearch's typo tolerance is hard to match; OpenSearch's BM25 plus custom scoring is the most tunable; Postgres FTS is the most predictable but the least configurable); operational cost (Postgres FTS is free — you already have Postgres; OpenSearch is a separate service with its own monitoring; Meilisearch is a separate service but smaller).
- **Measure** the precision of each backend on a fixed query set. Write 50 queries with hand-labelled expected results (`{"query": "python async generators", "expected_ids": [42, 117, 203, 891, 944]}`). For each query, run it against each backend; compute precision-at-5 (how many of the top-5 returned IDs are in the expected set). Report per-backend p@5; defend the choice with the numbers.

## Prerequisites

- **C16 Week 8 and Week 9** — you have a FastAPI service with Pydantic v2 schemas, an `asyncpg` or async-SQLAlchemy session, ARQ workers, and a Redis cache. The Pub/Sub plumbing from Week 8 carries over directly to Week 10's index-update pipeline.
- **Postgres 16.x available locally** with the `pg_trgm` extension installable. `brew install postgresql@16`, `apt install postgresql-16 postgresql-16-pg-trgm`, or `docker run -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16`. Verify with `psql -c 'SELECT version();'` and `psql -c 'CREATE EXTENSION IF NOT EXISTS pg_trgm; SELECT extversion FROM pg_extension WHERE extname = '"'"'pg_trgm'"'"';'`.
- **OpenSearch 2.x available locally.** Easiest: `docker run -p 9200:9200 -p 9600:9600 -e "discovery.type=single-node" -e "OPENSEARCH_INITIAL_ADMIN_PASSWORD=Crunch_Pro_W10_pw" opensearchproject/opensearch:2.17.0`. Verify with `curl -ku admin:Crunch_Pro_W10_pw https://localhost:9200/` and read the JSON banner; the cluster name is `docker-cluster` and the version is in the response.
- **Meilisearch 1.x available locally.** Easiest: `docker run -p 7700:7700 -e MEILI_MASTER_KEY=Crunch_Pro_W10_key getmeili/meilisearch:v1.10`. Or `brew install meilisearch && meilisearch --master-key=Crunch_Pro_W10_key`. Verify with `curl -H "Authorization: Bearer Crunch_Pro_W10_key" http://localhost:7700/health`.
- **The W9 stack still imports.** `python3 -c "import fastapi, redis, asyncpg, pydantic; print('ok')"` returns `ok`.
- **A basic understanding of inverted indexes.** You should know, in one sentence, that an inverted index maps "token → list of document IDs containing that token", and that *that* is what makes search fast (versus scanning every document for the substring). If that is foggy, read the first three sections of <https://en.wikipedia.org/wiki/Inverted_index> before opening Lecture 1.

## Topics covered

- The inverted-index data structure: token → posting list (doc IDs, optionally positions, optionally term frequencies)
- Tokenisation, normalisation, stemming, lemmatisation, stop-word filtering: what each step does, in what order, and why the order matters
- `tsvector` and `tsquery` in Postgres: the lexeme array, the positional information, the weight labels (`A`, `B`, `C`, `D`), the `||` operator for combining
- The Postgres text-search configurations: `english`, `simple`, custom configurations; the dictionary chain (`Stop`, `Snowball`, `Synonym`, `Thesaurus`); the parser (the default `default` parser tokenises into types like `asciiword`, `numword`, `email`, `url`)
- `to_tsquery` versus `plainto_tsquery` versus `phraseto_tsquery` versus `websearch_to_tsquery`: the four front-doors, their syntax rules, and which one belongs in the user-facing API
- `ts_rank` and `ts_rank_cd`: the term-frequency and cover-density scorers; the normalisation flag bitmask (`0`, `1`, `2`, `4`, `8`, `16`, `32`)
- `GIN` versus `GiST` indexes on `tsvector` columns: `GIN` is `O(log n)` lookup and slower updates; `GiST` is `O(log n)` lookup with lossy compression and faster updates
- `pg_trgm`: the trigram model, the `%` similarity operator, `similarity()`, `<->` distance, `gin_trgm_ops` indexes; the use as a fuzzy fallback on FTS misses
- The OpenSearch index lifecycle: create index, mapping (`properties`, `text` vs `keyword`, `analyzer`), settings (`number_of_shards`, `number_of_replicas`, `analysis.analyzer`), bulk index, refresh, search, delete
- The OpenSearch analyzer chain: `tokenizer` plus `char_filter` plus `filter`; the built-in analyzers (`standard`, `english`, `keyword`, `whitespace`); the right place to define a custom analyzer per index
- BM25 scoring: the formula `IDF(q_i) * (f(q_i, D) * (k1 + 1)) / (f(q_i, D) + k1 * (1 - b + b * |D| / avgdl))`; what `k1` and `b` do; the per-field tuning hook
- OpenSearch query DSL: `match`, `multi_match`, `query_string`, `bool` (must / should / must_not / filter), `function_score` for custom relevance, `highlight`, `aggs`
- Meilisearch's design philosophy: typo tolerance first, configuration second, latency under 50 ms always; the index-and-query API surface is one page
- Meilisearch's six default ranking rules (in order): `words`, `typo`, `proximity`, `attribute`, `sort`, `exactness`; how to reorder them; when to add a custom rule
- Meilisearch's faceting and filtering: `filterableAttributes`, the `filter` query parameter, the `facets` request parameter, the `facetDistribution` response
- The indexing pipeline: source-of-truth Postgres, generated `tsvector` column for the Postgres path, ARQ workers that consume "article changed" events and call `client.index().add_documents([...])` for OpenSearch and Meilisearch; the failure modes when the worker is behind
- Reindexing strategies: stop-the-world (the simplest — `DELETE INDEX; CREATE INDEX; bulk index all`); alias-swap (the production-standard — index into `articles_v2`, point the `articles` alias at `articles_v2`, delete `articles_v1`); incremental (read a high-water-mark timestamp; reindex only rows changed since)
- Highlighting and snippet generation: how to return the matched substring wrapped in `<em>` tags, with optional ellipsis-truncated context windows
- The relevance evaluation methodology: hand-labelled query sets, precision-at-K, recall-at-K, mean reciprocal rank, the "is this better?" question made answerable

## Weekly schedule

The schedule below totals approximately **35 hours**. The lecture density is similar to Week 9 because the three topics (Postgres FTS, OpenSearch, Meilisearch) are each independent backends and deserve their own session.

| Day       | Focus                                                                              | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|------------------------------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Postgres FTS: tsvector, tsquery, ts_rank, GIN, pg_trgm                              | 2h       | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6h          |
| Tuesday   | OpenSearch: analyzers, BM25, the search DSL, aggregations                           | 2h       | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6h          |
| Wednesday | Meilisearch: typo tolerance, ranking rules, faceting                                | 2h       | 1.5h      | 1h         | 0.5h      | 1h       | 0h           | 0.5h       | 6.5h        |
| Thursday  | The relevance harness; precision-at-5; the comparison report                        | 0h       | 1h        | 1h         | 0.5h      | 1h       | 2h           | 0.5h       | 6h          |
| Friday    | Wire all three into the W7 service behind a `/search` endpoint                       | 0h       | 0h        | 1h         | 0.5h      | 1h       | 2h           | 0h         | 4.5h        |
| Saturday  | Reindexing strategy; the alias-swap; the indexing pipeline tests                    | 0h       | 0h        | 0h         | 0h        | 1h       | 3h           | 0h         | 4h          |
| Sunday    | Quiz; reflection; the "which backend and why" defence                                | 0h       | 0h        | 0h         | 0.5h      | 0h       | 0h           | 0h         | 0.5h        |
| **Total** |                                                                                    | **6h**   | **6.5h**  | **3h**     | **3h**    | **6h**   | **7h**       | **2h**     | **33.5h**   |

The week's pacing puts the three backends on three consecutive days, then integrates them Thursday onward. The mini-project is the same measure-then-fix discipline as Week 9: the same query, three implementations, three latency curves, three precision-at-5 numbers, one defended pick.

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview |
| [resources.md](./resources.md) | Postgres FTS chapter, OpenSearch docs, Meilisearch docs, Elastic's BM25 explainer, the relevance-engineering references worth bookmarking |
| [lecture-notes/01-postgres-full-text-search.md](./lecture-notes/01-postgres-full-text-search.md) | `tsvector`, `tsquery`, weights, `ts_rank` vs `ts_rank_cd`, `GIN` vs `GiST`, `pg_trgm` for fuzzy |
| [lecture-notes/02-opensearch-analyzers-bm25-and-the-dsl.md](./lecture-notes/02-opensearch-analyzers-bm25-and-the-dsl.md) | Analyzer chain, BM25 formula, the `match` / `multi_match` / `bool` DSL, highlighting, aggregations |
| [lecture-notes/03-meilisearch-typo-tolerance-and-picking-a-backend.md](./lecture-notes/03-meilisearch-typo-tolerance-and-picking-a-backend.md) | Ranking rules, faceting, the three-backend picker; reindexing strategies; the relevance harness methodology |
| [exercises/exercise-01-postgres-tsvector-and-tsquery.py](./exercises/exercise-01-postgres-tsvector-and-tsquery.py) | Build the `tsvector` column; run the four query flavours; observe `ts_rank_cd` |
| [exercises/exercise-02-pg-trgm-fuzzy-fallback.py](./exercises/exercise-02-pg-trgm-fuzzy-fallback.py) | Install `pg_trgm`; fuzzy-match on typos; wire the FTS-then-trigram fallback |
| [exercises/exercise-03-opensearch-index-and-search.py](./exercises/exercise-03-opensearch-index-and-search.py) | Create an index with a custom analyzer; bulk index; run `multi_match` with boosts; aggregate |
| [exercises/exercise-04-meilisearch-typo-and-facets.py](./exercises/exercise-04-meilisearch-typo-and-facets.py) | Index documents; tune the ranking rules; faceted search with `filterableAttributes` |
| [exercises/exercise-05-postgres-fts.sql](./exercises/exercise-05-postgres-fts.sql) | The schema migration: generated column, GIN index, pg_trgm extension, sample queries |
| [exercises/SOLUTIONS.md](./exercises/SOLUTIONS.md) | Worked solutions and trickier-line explanations |
| [challenges/challenge-01-three-backend-relevance-harness.md](./challenges/challenge-01-three-backend-relevance-harness.md) | The 50-query hand-labelled set; precision-at-5 against all three backends; the comparison table |
| [challenges/challenge-02-alias-swap-reindex.md](./challenges/challenge-02-alias-swap-reindex.md) | The zero-downtime reindex with an alias swap on OpenSearch and a similar pattern on Meilisearch |
| [quiz.md](./quiz.md) | 10 multiple-choice questions |
| [homework.md](./homework.md) | Six problems (~6 h) |
| [mini-project/README.md](./mini-project/README.md) | Build `crunchsearch` — three search backends behind one `/search` endpoint, with a `BENCHMARK.md` |
| [mini-project/starter/](./mini-project/starter/) | Starter files: search clients, the indexing pipeline, settings, the relevance harness |

## Before Monday — verify the environment

Eight checks. If any fails, fix it before opening Lecture 1.

```bash
# 1. Python 3.12+
python3 --version
# Python 3.12.x or 3.13.x

# 2. Postgres 16 is reachable, pg_trgm installable
psql -h localhost -U postgres -c 'SELECT version();' | head -1
psql -h localhost -U postgres -c "CREATE EXTENSION IF NOT EXISTS pg_trgm; SELECT extversion FROM pg_extension WHERE extname='pg_trgm';"

# 3. OpenSearch is reachable
curl -ks https://localhost:9200/ -u admin:Crunch_Pro_W10_pw | head -20
# JSON banner including "cluster_name", "version.distribution":"opensearch"

# 4. Meilisearch is reachable
curl -s -H "Authorization: Bearer Crunch_Pro_W10_key" http://localhost:7700/health
# {"status":"available"}

# 5. hey installed (we use it for the BENCHMARK.md numbers)
hey -h 2>&1 | head -1

# 6. W7/W8/W9 stack still imports
python3 -c "import fastapi, redis, asyncpg, pydantic; print('ok')"

# 7. Install this week's added dependencies
pip install 'opensearch-py==2.7.*' 'meilisearch-python-sdk==2.10.*' 'asyncpg==0.30.*'

# 8. Confirm the clients import
python3 -c "from opensearchpy import AsyncOpenSearch; from meilisearch_python_sdk import AsyncClient; print('ok')"
# ok
```

If OpenSearch refuses to start under Docker with an `vm.max_map_count` error, run `sudo sysctl -w vm.max_map_count=262144` (Linux) or set it in the Docker Desktop VM (macOS / Windows). If Meilisearch refuses to bind to 7700, another service is using the port — pick 7701 and set `MEILI_HTTP_ADDR=0.0.0.0:7701` on the container.

## The habit to install this week

Four practices, applied to every search endpoint and every indexing job you write from here on:

1. **Measure relevance, not just latency.** A 5 ms search that returns the wrong document is worse than a 50 ms search that returns the right one. Every search backend ships with a default scorer that *probably* works for *most* queries; that "probably" is the bug. Maintain a query set with expected results; run it on every analyzer change. The number you commit alongside the change is precision-at-5, not just the median request time.
2. **Index off the write path.** Synchronous indexing of large documents in the request handler is how the `POST /articles` endpoint becomes a 2-second endpoint. Publish a "search-index" event in the request handler; do the actual indexing in an ARQ worker. The W8 Pub/Sub plumbing is exactly the tool for this.
3. **Reindex with alias swap, never with stop-the-world.** A `DELETE INDEX; CREATE INDEX; bulk index` cycle takes the search offline for the duration. An alias-swap reindex builds the new index in parallel under a versioned name (`articles_v3`), swaps the alias atomically, and deletes the old index. The first time you do this, do it as an exercise; the second time and forever after, it is the only way you reindex.
4. **Pick one default; surface the others under a flag.** A "we use Meilisearch by default, with `?backend=opensearch` as a query parameter for relevance experiments" pattern lets you switch defaults without code surgery once the comparison data is in. The `/search` endpoint in the mini-project takes exactly this shape.

The first practice keeps you honest about what search is for. The second keeps the write path fast. The third keeps the search online during maintenance. The fourth keeps the team's hands free to change its mind.

## Stretch goals

- Read **Robertson and Zaragoza, "The Probabilistic Relevance Framework: BM25 and Beyond" (Foundations and Trends in Information Retrieval, 2009)** — the canonical 100-page survey of the BM25 family, free on the authors' page: <https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf>. Section 3 is the formula; section 4 is the field-weighting extension (BM25F) that OpenSearch implements per-field.
- Read **the Postgres `tsvector` source** — `src/backend/utils/adt/tsvector_op.c` and friends in the Postgres repo (~6 000 lines of C). The function `tsCompareString` is one of the cleanest pieces of compact code you will read.
- Read the **Elasticsearch/OpenSearch BM25 blog series** by Shane Connelly: <https://www.elastic.co/blog/practical-bm25-part-1-how-shards-affect-relevance-scoring-in-elasticsearch>, <https://www.elastic.co/blog/practical-bm25-part-2-the-bm25-algorithm-and-its-variables>, <https://www.elastic.co/blog/practical-bm25-part-3-considerations-for-picking-b-and-k1-in-elasticsearch>. Three short posts; the most accessible BM25 introduction in print.
- Read **the Meilisearch source for the ranking rules** — `crates/milli/src/search/new/ranking_rule_graph/` in the `meilisearch/meilisearch` GitHub repo. Rust, ~3 000 lines, the algorithmic core of the engine.
- Read **Manning, Raghavan, Schütze, "Introduction to Information Retrieval" (Cambridge, 2008)** — the open-access textbook at <https://nlp.stanford.edu/IR-book/>. Chapter 6 is the vector space model; Chapter 11 is the probabilistic retrieval model that BM25 falls out of.

## Up next

[Week 11 — Observability: structured logging, metrics, and distributed tracing](../week-11-observability-logging-metrics-tracing/) — we have spent ten weeks building things that work. Week 11 makes them legible: structured logs (`logger.bind(...)`), Prometheus metrics on every endpoint, OpenTelemetry traces across the FastAPI → Redis → Postgres → OpenSearch → Meilisearch call chain, and the four golden signals — latency, traffic, errors, saturation — on a Grafana dashboard. The precision-at-5 number you tracked this week becomes one of the panels.
