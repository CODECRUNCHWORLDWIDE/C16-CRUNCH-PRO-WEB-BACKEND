# Week 10 — Resources

Bookmarkable references for the three search backends. Read the **must-read** rows first; the **deep-cut** rows are for the engineer who wants to know the formula behind the formula.

## Postgres full-text search

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [Postgres docs — Chapter 12: Full Text Search](https://www.postgresql.org/docs/current/textsearch.html) | The canonical reference. Sections 12.1–12.4 cover `tsvector`, `tsquery`, parsing, ranking, and the four query front-doors. Read end-to-end on Monday morning. |
| must-read | [12.2 — Tables and indexes](https://www.postgresql.org/docs/current/textsearch-tables.html) | The generated-column pattern and the `GIN` / `GiST` index trade-off. The only section you must memorise. |
| must-read | [12.3 — Controlling text search](https://www.postgresql.org/docs/current/textsearch-controls.html) | `to_tsquery`, `plainto_tsquery`, `phraseto_tsquery`, `websearch_to_tsquery`, `ts_rank`, `ts_rank_cd`. |
| must-read | [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html) | The trigram extension; the `%` operator; `similarity()`; the `gin_trgm_ops` index. The fuzzy fallback for misspelled queries. |
| reference | [12.6 — Dictionaries](https://www.postgresql.org/docs/current/textsearch-dictionaries.html) | Stop words, Snowball stemmers, synonyms, thesauri, ispell. When the default `english` configuration is wrong, this is where the next-step lives. |
| reference | [12.7 — Configuration examples](https://www.postgresql.org/docs/current/textsearch-configuration.html) | How to build a custom text-search configuration from scratch. |
| deep-cut  | [12.10 — Limitations](https://www.postgresql.org/docs/current/textsearch-limitations.html) | The list of things Postgres FTS does *not* do (no built-in BM25, no per-shard scoring, no out-of-the-box "did you mean", no character-set normalisation beyond what the dictionary provides). The honest part of the manual. |
| deep-cut  | [Postgres `tsvector` source — `tsvector_op.c`](https://github.com/postgres/postgres/blob/master/src/backend/utils/adt/tsvector_op.c) | The actual implementation. ~3 000 lines of C. `match_tsquery` and `calc_rank_cd` are the load-bearing functions. |
| video     | [POSETTE 2024 — "Full-text search in Postgres" by Lætitia Avrot](https://www.youtube.com/results?search_query=postgres+full+text+search+laetitia+avrot) | One-hour conference talk; covers the same ground as Chapter 12 with the demos worth seeing once. |

## OpenSearch

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [OpenSearch documentation — root](https://opensearch.org/docs/latest/)                     | The full docs. Browse the left-hand sidebar: "Search-and-data-prep" and "Search" sections are the W10 surface. |
| must-read | [Index API](https://opensearch.org/docs/latest/api-reference/index-apis/index/) | Create-index, update-mapping, delete-index, get-index. |
| must-read | [Search API](https://opensearch.org/docs/latest/api-reference/search/)                     | The `_search` endpoint; request body, response shape, highlighting, aggregations. |
| must-read | [Query DSL — match family](https://opensearch.org/docs/latest/query-dsl/full-text/match/) | `match`, `multi_match`, `match_phrase`, `match_phrase_prefix`. The 90% case. |
| must-read | [Query DSL — bool query](https://opensearch.org/docs/latest/query-dsl/compound/bool/)     | `must`, `should`, `must_not`, `filter`. The combinator that everything else nests inside. |
| must-read | [Analyzers reference](https://opensearch.org/docs/latest/analyzers/)                       | Tokenizers, char filters, token filters; the chain that produces the searchable terms. |
| reference | [BM25 similarity in OpenSearch](https://opensearch.org/docs/latest/search-plugins/searching-data/scoring/) | The default scorer. The `k1` and `b` parameters; per-field similarity overrides. |
| reference | [Highlighting](https://opensearch.org/docs/latest/search-plugins/searching-data/highlight/) | The `highlight` block; `pre_tags` / `post_tags`; `fragment_size`. |
| reference | [Aggregations](https://opensearch.org/docs/latest/aggregations/)                           | Buckets, metrics, pipeline aggregations. The faceting story. |
| reference | [`opensearch-py` documentation](https://opensearch-project.github.io/opensearch-py/) | The Python client. The async variant `AsyncOpenSearch` is what we use. |
| deep-cut  | [Elastic — "Practical BM25 Part 1"](https://www.elastic.co/blog/practical-bm25-part-1-how-shards-affect-relevance-scoring-in-elasticsearch) | Why score reproducibility depends on shard count. (OpenSearch forked Elasticsearch 7.10; the scorer is identical.) |
| deep-cut  | [Elastic — "Practical BM25 Part 2"](https://www.elastic.co/blog/practical-bm25-part-2-the-bm25-algorithm-and-its-variables) | The BM25 formula with worked examples. The single best explainer in print. |
| deep-cut  | [Elastic — "Practical BM25 Part 3"](https://www.elastic.co/blog/practical-bm25-part-3-considerations-for-picking-b-and-k1-in-elasticsearch) | How to pick `k1` and `b` for your corpus. The "default 1.2 / 0.75 are fine" justification, with the cases where they are not. |
| deep-cut  | [Robertson and Zaragoza, "The Probabilistic Relevance Framework: BM25 and Beyond" (FnT IR, 2009)](https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf) | The 100-page canonical survey. Section 3 is the formula; section 4 is BM25F (per-field weighting). Free PDF. |

## Meilisearch

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [Meilisearch documentation — quick start](https://www.meilisearch.com/docs/learn/getting_started/quick_start) | The index-and-search 15-minute walkthrough. |
| must-read | [Ranking rules](https://www.meilisearch.com/docs/learn/relevancy/ranking_rules) | The six default rules (`words`, `typo`, `proximity`, `attribute`, `sort`, `exactness`) and how to reorder them. |
| must-read | [Searchable attributes](https://www.meilisearch.com/docs/reference/api/settings#searchable-attributes) | The `searchableAttributes` setting; the ordering matters. |
| must-read | [Filterable and facetable attributes](https://www.meilisearch.com/docs/learn/filtering_and_sorting/filter_search_results) | `filterableAttributes`; the `filter` query parameter; the `facets` parameter and the `facetDistribution` response. |
| reference | [Typo tolerance](https://www.meilisearch.com/docs/learn/relevancy/typo_tolerance_settings) | `oneTypo` and `twoTypos` thresholds; per-attribute disabling. |
| reference | [Search parameters](https://www.meilisearch.com/docs/reference/api/search) | `limit`, `offset`, `attributesToHighlight`, `attributesToCrop`, `cropLength`, `matchingStrategy`. |
| reference | [`meilisearch-python-sdk` repository](https://github.com/sanders41/meilisearch-python-sdk) | The async-first Python client. Type hints throughout. |
| reference | [Update vs add documents](https://www.meilisearch.com/docs/reference/api/documents) | The indexing API; the partial-update semantics; the bulk-indexing pattern. |
| deep-cut  | [Meilisearch architecture overview](https://www.meilisearch.com/docs/learn/engine/architecture) | The LMDB-backed storage; the in-memory query graph; the design rationale for "no SQL-like queries". |
| deep-cut  | [Meilisearch source — `crates/milli/src/search/new/`](https://github.com/meilisearch/meilisearch/tree/main/crates/milli/src/search/new) | The Rust ranking-rule implementation. ~3 000 lines of focused code. |

## The information-retrieval canon

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [Manning, Raghavan, Schütze, *Introduction to Information Retrieval* (Cambridge, 2008)](https://nlp.stanford.edu/IR-book/) | The standard textbook, open-access. Chapter 1 (Boolean retrieval), Chapter 2 (the inverted index), Chapter 6 (scoring and the vector space model), Chapter 8 (evaluation). |
| reference | [Wikipedia — Inverted index](https://en.wikipedia.org/wiki/Inverted_index) | The one-page primer. Read first if you are new to search. |
| reference | [Wikipedia — Okapi BM25](https://en.wikipedia.org/wiki/Okapi_BM25) | The formula and its history, with the variant table. |
| reference | [Wikipedia — Stemming](https://en.wikipedia.org/wiki/Stemming) | The Porter stemmer, the Snowball family, lemmatisation versus stemming. |
| reference | [Wikipedia — Trigram (and the n-gram model)](https://en.wikipedia.org/wiki/N-gram) | The `pg_trgm` justification in one page. |
| deep-cut  | [Croft, Metzler, Strohman, *Search Engines: Information Retrieval in Practice*](https://ciir.cs.umass.edu/irbook/) | The implementor-oriented companion to Manning et al. Includes per-language tokenisation, query suggestion, and the relevance-evaluation methodology in depth. |

## Python clients

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [`asyncpg` documentation](https://magicstack.github.io/asyncpg/current/)                   | The async Postgres driver. Faster than `psycopg` for raw query throughput; the right pick for the FTS read path. |
| must-read | [`opensearch-py` AsyncClient](https://opensearch-project.github.io/opensearch-py/api-ref/clients/async_client.html) | The async OpenSearch client. The signature is identical to the synchronous one, with `await` on every method. |
| must-read | [`meilisearch-python-sdk` AsyncClient](https://github.com/sanders41/meilisearch-python-sdk#asynchronous-client) | The async Meilisearch client. Type hints throughout; Pydantic v2 models for the response shapes. |
| reference | [`SQLAlchemy` text-search expression integration](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#full-text-search) | If you prefer the ORM path over raw SQL. The `func.to_tsquery` and `Column.match` patterns. |

## Tooling for measurement

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [`hey` — HTTP load generator](https://github.com/rakyll/hey)                               | The Go-based modern equivalent of `ab`. Single binary, clean histogram output. We use it for the BENCHMARK.md numbers. |
| reference | [`pytest-benchmark`](https://pytest-benchmark.readthedocs.io/)                             | Microbenchmarks for individual search functions. The right tool for "how long does `to_tsquery` take?" questions. |
| reference | [Postgres `EXPLAIN (ANALYZE, BUFFERS)`](https://www.postgresql.org/docs/current/sql-explain.html) | The query plan for an FTS query. Look for `Bitmap Index Scan on articles_tsv_idx`; if you see `Seq Scan`, the index is not being used. |

## Worth a long read

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| deep-cut  | [Stripe Engineering — "Online migrations at scale"](https://stripe.com/blog/online-migrations) | The alias-swap reindex pattern, applied at production scale. Not search-specific, but the methodology is the same. |
| deep-cut  | [Etsy Code as Craft — "Tuning Solr for relevance"](https://www.etsy.com/codeascraft/) | Etsy's iterative relevance-tuning posts. The discipline of "label a query set; measure; tune; measure again". |
| deep-cut  | [Doug Turnbull and John Berryman, *Relevant Search* (Manning, 2016)](https://www.manning.com/books/relevant-search) | The book-length treatment of relevance engineering on Lucene-family search engines. Chapters 1–4 are free preview; the full book is the next step after this week. |
