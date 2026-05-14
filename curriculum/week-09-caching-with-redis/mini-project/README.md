# Mini-Project — `crunchcache`: measure-then-fix on a real endpoint

> Take a deliberately slow FastAPI endpoint that hits SQLite, capture a load-test baseline, add a Redis cache layer with all three patterns from this week (cache-aside, event-driven invalidation, stampede protection), re-run the load test, and produce a `BENCHMARK.md` with the before-and-after numbers. The deliverable is the working service plus the benchmark artefact; the artefact is the proof you understood what the cache is doing.

**Estimated time:** 7 hours, spread Thursday–Saturday. Thursday is the baseline benchmark; Friday is the cache implementation; Saturday is the invalidation map, the tests, and the operational README.

## Why this and not something larger

`crunchcache` is deliberately small. Its job is to make the three pillars of this week — patterns, invalidation, stampede protection — concrete in working code. A larger project would dilute the focus. By the end of Saturday you have one app that, in around 1 000 lines of Python plus tests, demonstrates a cache architecture defensible in a code review at any real engineering organisation.

This project does not depend on the Week 7 or Week 8 services. It runs standalone with SQLite as the source of truth (we want the database to be slow on purpose; SQLite obliges if you do not index things). The Week 7 service can be cache-augmented in a follow-up week if you wish, but for grading this is independent.

## What you build

A FastAPI service named `crunchcache` with:

1. **Five HTTP routes:**
   - `GET /articles` — list articles, with optional `?author_id=X` filter. Without cache, runs a `SELECT` against SQLite that we will arrange to take ~150 ms. Cached. The cache key includes the filter.
   - `GET /articles/{id}` — single article fetch. Cached. The cache key is `v1:article:{id}`.
   - `GET /articles/popular` — top 10 by `views`. Cached. The cache key is `v1:articles:popular:{limit}`.
   - `POST /articles/{id}/view` — increment the view counter; this *write* path must invalidate the cached single article and the cached popular list.
   - `PATCH /articles/{id}` — update an article; this write path must invalidate the cached single article, the popular list, and the filtered `GET /articles?author_id=X` for the author.
   - `GET /health` — process-level health probe; returns `200` if FastAPI is up, SQLite is reachable, and Redis ping succeeds.

2. **One invalidation bus** (Redis Pub/Sub):
   - Channel `crunchcache:invalidate`. Messages are JSON: `{"key": "v1:article:42"}` or `{"tag": "author:7"}`. Subscribers `DEL` the named key or sweep the named tag.
   - The write paths publish to this channel after the database commit.
   - The FastAPI process subscribes on startup (via the `lifespan` context manager) and reacts to events.

3. **A stampede-protected `popular` endpoint:**
   - The `GET /articles/popular` endpoint uses request coalescing (single-flight). 100 concurrent misses must result in exactly 1 database query.
   - Confirm in a test by running 100 `asyncio.gather` calls against the endpoint with the cache empty.

4. **Pydantic v2 schemas:**
   - `ArticleIn` — body for `PATCH /articles/{id}`. Fields: `title: str | None`, `body: str | None`, `author_id: int | None`. `extra="forbid"`.
   - `ArticleOut` — response for `GET /articles/{id}` and the list endpoints. Fields: `id`, `title`, `body`, `author_id`, `views`, `created_at`.
   - `Health` — response for `/health`. Fields: `status`, `redis_ok`, `db_ok`.

5. **A benchmark harness:**
   - A small Python script that runs `ab` and `hey` against the four read endpoints, both with and without the cache enabled (controlled by an environment variable `CACHE_ENABLED`).
   - Captures the numbers into `BENCHMARK.md`.

6. **An integration test suite:**
   - `tests/test_routes.py` — happy paths, 404 on unknown article, 422 on invalid PATCH.
   - `tests/test_cache.py` — cache hit on second read; cache miss after invalidation; cross-endpoint invalidation (popular list refreshes after PATCH).
   - `tests/test_stampede.py` — 100 concurrent misses; assert exactly 1 database call.

7. **An operational README** explaining how to run the service, what the invalidation map is, and how to interpret the `BENCHMARK.md`.

## Repository layout

```text
crunchcache/
├── pyproject.toml
├── README.md
├── BENCHMARK.md             (the artefact you produce)
├── .env.example
├── .gitignore
├── crunchcache/
│   ├── __init__.py
│   ├── main.py              (FastAPI app, lifespan, route wiring)
│   ├── settings.py          (Pydantic Settings: Redis URL, SQLite path, cache TTLs)
│   ├── schemas.py           (Pydantic v2 models)
│   ├── db.py                (the SQLAlchemy engine + async session)
│   ├── models.py            (the Article SQLAlchemy model)
│   ├── cache.py             (the cache client, the coalescing helper, the bus)
│   ├── invalidation.py      (the Pub/Sub invalidation bus)
│   └── routers/
│       ├── __init__.py
│       └── articles.py      (all five routes)
├── scripts/
│   ├── seed.py              (seed SQLite with 1 000 articles)
│   └── bench.py             (run ab/hey against the four read endpoints)
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_routes.py
    ├── test_cache.py
    └── test_stampede.py
```

Total: 16 files, matching the quality bar of C1 W1 and the Week 8 mini-project.

## Stack

- Python 3.12+
- FastAPI 0.115.x with the `[standard]` extra
- Pydantic 2.9.x + `pydantic-settings` 2.5.x
- SQLAlchemy 2.0.x + `aiosqlite`
- `redis[hiredis]` 5.0.x
- `fakeredis` 2.25.x for tests
- Pytest 8.x + pytest-asyncio 0.24.x + httpx 0.27.x

Setup:

```bash
mkdir crunchcache && cd crunchcache
python3 -m venv .venv && source .venv/bin/activate
pip install 'fastapi[standard]==0.115.*' 'pydantic==2.9.*' 'pydantic-settings==2.5.*' \
            'sqlalchemy==2.0.*' 'aiosqlite==0.20.*' 'redis[hiredis]==5.0.*' \
            'fakeredis==2.25.*' 'pytest==8.3.*' 'pytest-asyncio==0.24.*' 'httpx==0.27.*'
pip freeze > requirements.txt
```

## Acceptance criteria

### Schemas

- [ ] `schemas.py` declares `ArticleIn`, `ArticleOut`, `Health` with the field shapes above.
- [ ] `ArticleIn.model_config = ConfigDict(extra="forbid")`. Unknown fields return 422.
- [ ] `ArticleIn` has at least one field; an empty PATCH body returns 422 with a clear error.

### Routes — happy paths

- [ ] `GET /articles` returns the full list; `?author_id=X` filters; both are cached under different keys.
- [ ] `GET /articles/{id}` returns the article or 404.
- [ ] `GET /articles/popular?limit=10` returns the top 10 by views.
- [ ] `POST /articles/{id}/view` increments `views` and returns the new count.
- [ ] `PATCH /articles/{id}` accepts `ArticleIn` and applies the changes; returns the updated article.
- [ ] `GET /health` returns `200` with `redis_ok` and `db_ok` booleans.

### Cache implementation

- [ ] The cache key naming follows `v1:article:{id}`, `v1:articles:popular:{limit}`, `v1:articles:filter:author:{id}`.
- [ ] Every cached value has an explicit TTL (no `expire`-less `set` calls). The values are in `settings.py` — `ARTICLE_TTL = 3600`, `POPULAR_TTL = 60`, `FILTER_TTL = 300`.
- [ ] The `GET /articles/popular` endpoint uses request coalescing — 100 concurrent misses results in exactly 1 DB query.
- [ ] The cache reads and writes are wrapped in `try/except redis.RedisError`; a Redis outage degrades to direct DB reads.

### Invalidation bus

- [ ] On `POST /articles/{id}/view`, the write path publishes invalidation messages for `v1:article:{id}` and `v1:articles:popular:*` to the bus channel.
- [ ] On `PATCH /articles/{id}`, the write path publishes invalidation for the single article, the popular list, and the filter key for the article's author.
- [ ] The bus subscriber, started in the FastAPI `lifespan`, reacts to invalidation messages by `DEL`ing the named key (or sweeping the named pattern for the popular list).
- [ ] The Pub/Sub subscription survives a brief Redis disconnect: the subscriber reconnects automatically.

### Tests

- [ ] `test_routes.py` covers the happy path for every route, plus 404 on unknown article and 422 on invalid PATCH.
- [ ] `test_cache.py` confirms: (a) second read is a cache hit; (b) PATCH followed by a read returns the new value (cache was invalidated); (c) when `CACHE_ENABLED=false`, no cache writes happen.
- [ ] `test_stampede.py` confirms: 100 concurrent `GET /articles/popular` on a cold cache result in exactly 1 DB query (mock the DB query function and count calls).
- [ ] All tests use `fakeredis` for the Redis layer; they do not require a real Redis to pass.

### Operational documentation

- [ ] `README.md` opens with "How to run" — three steps (seed the DB, start the service, run the benchmark).
- [ ] The README has the invalidation-map table (Lecture 2 §5).
- [ ] The README has a "Failure modes" section listing at least three: Redis down, SQLite slow, Pub/Sub message lost. For each, name the symptom and the recovery.
- [ ] The README closes with the headline benchmark numbers ("p95 380 ms -> 6 ms, 63x improvement") and a link to `BENCHMARK.md` for the details.

### `BENCHMARK.md`

- [ ] Contains the four sections from Challenge 1: setup, numbers (table), explanation, recommendation.
- [ ] Includes raw `ab` and `hey` output as appendices (or in a sibling `bench/` folder).
- [ ] The improvement column shows the order of magnitude clearly (10x to 100x for hit-only workloads; 2x to 5x for mixed-write workloads).

## Architecture diagram (textual)

```text
+----------+   GET /articles/popular   +---------+   GET cache           +-------+
|  Client  | -----------------------> | FastAPI |---------------------->| Redis |
|          | <-- ArticleOut (cached) -|         |<- value or nil ------|       |
|          |                          | request |                       +-------+
|          |                          |  coal.  |     SUBSCRIBE invalidate
|          |   POST /articles/42/view |  layer  |<-----+
|          | -----------------------> |         |       \
|          | <-- {"views": 1001} -----|         |        \   PUBLISH invalidate
|          |                          |   bus   | --------+
|          |                          +---------+         |
|          |                              |               |
|          |                              | SELECT/UPDATE |
|          |                              v               |
|          |                          +---------+         |
|          |                          | SQLite  |         |
|          |                          +---------+         |
+----------+                                              |
                                                          v
                                              every FastAPI worker
                                              subscribed to the same
                                              invalidate channel
```

One FastAPI process; Redis for cache and Pub/Sub; SQLite as the slow source-of-truth. Three caching primitives in play: read cache, write-driven invalidation, stampede protection.

## Step-by-step build

### Day 1 — Thursday (~2 hours): baseline

- Scaffold the repository layout above. `__init__.py` files, empty modules.
- Write `settings.py`, `schemas.py`, `db.py`, `models.py`. Run the SQLAlchemy migration to create the SQLite schema. Run `scripts/seed.py` to insert 1 000 articles.
- Write `routers/articles.py` with the five routes — *without* the cache for now. Run `uvicorn` and confirm the routes return data.
- Run the baseline benchmark: `bash scripts/bench.sh baseline`. Capture `ab` and `hey` output. Write the baseline section of `BENCHMARK.md`.

### Day 2 — Friday (~2 hours): cache + invalidation

- Write `cache.py`: a `redis.asyncio` client, the cache-aside helper, the `CoalescingCache` from Exercise 4.
- Write `invalidation.py`: the Pub/Sub publisher and subscriber. Wire the subscriber into the FastAPI `lifespan`.
- Add cache calls to each `GET` route. Add invalidation publish calls to each write route.
- Run the cached benchmark: `bash scripts/bench.sh cached`. Capture output. Write the cached section of `BENCHMARK.md`.

### Day 3 — Saturday (~3 hours): tests + docs

- Write `tests/test_routes.py`, `tests/test_cache.py`, `tests/test_stampede.py`. Use `fakeredis` for the Redis fixture.
- Write the operational README. Run through the "how to run" section yourself, in a clean terminal, and fix any step that does not match what you typed.
- Write the invalidation map (Lecture 2 §5 table).
- Fill in the `BENCHMARK.md` explanation and recommendation sections.

## Stretch goals

- [ ] **Replace the SQLite source with Postgres** (via `asyncpg`). Re-run the benchmark; the absolute numbers change but the order of magnitude does not.
- [ ] **Add XFetch as an alternative stampede strategy.** Add a settings flag `STAMPEDE_STRATEGY = "coalesce" | "xfetch" | "none"`. Implement the third option. Run a comparison benchmark and add a section to `BENCHMARK.md`.
- [ ] **Add a tag-based invalidation layer for rendered pages.** A new route `GET /articles/{id}/render?lang=en` returns a rendered HTML representation; it depends on the article, the author, and any linked entities. Use the tag pattern from Exercise 3.
- [ ] **Add Prometheus instrumentation.** Expose `/metrics` with counters for cache hits, cache misses, evictions observed, and DB queries. Use `prometheus-fastapi-instrumentator`. Show the cache-hit ratio over the benchmark window.
- [ ] **Replace fakeredis in tests with a real Redis spun up via `pytest-docker` or `testcontainers`.** Document the trade-offs (test speed vs fidelity to production).

## Rubric (50 points)

| Area                                | Points | Pass bar                                                                  |
|-------------------------------------|-------:|---------------------------------------------------------------------------|
| Schemas + validators                | 4      | All three schemas; `extra="forbid"`; non-empty PATCH validator             |
| Five routes, happy paths            | 6      | Each route returns expected response on a clean DB                        |
| Cache reads (cache-aside)           | 6      | Hit on second read; correct keys; explicit TTLs                            |
| Cache degradation                   | 3      | Redis offline -> service still serves 200 (slowly)                         |
| Request coalescing                  | 6      | 100 concurrent misses -> 1 DB query (asserted in test)                     |
| Invalidation bus                    | 6      | Publish on writes; subscriber DELs; survives a Pub/Sub disconnect          |
| Invalidation map in README          | 3      | Every read/write paired correctly; cited Lecture 2                         |
| `BENCHMARK.md`                      | 6      | All four sections; before/after table; recommendations defended            |
| Tests (routes + cache + stampede)   | 5      | All test files; all pass; cover the failure modes                          |
| Operational README                  | 3      | "How to run", "Failure modes", "Invalidation map"                          |
| Code quality (types, ruff-clean)    | 2      | Every function has type hints; `ruff check` passes                         |

Late submissions: 10% per day, capped at 50%. Code that does not `py_compile` is graded as if the file did not exist; fix and resubmit.

## References

- **FastAPI**: <https://fastapi.tiangolo.com/>
- **`redis-py`**: <https://redis-py.readthedocs.io/>
- **Apache Bench**: <https://httpd.apache.org/docs/2.4/programs/ab.html>
- **`hey`**: <https://github.com/rakyll/hey>
- **`fakeredis`**: <https://github.com/cunla/fakeredis-py>
- **Vattani et al. 2015 (XFetch)**: <https://arxiv.org/abs/1504.00922>
- **AWS caching strategies overview**: <https://docs.aws.amazon.com/AmazonElastiCache/latest/mem-ug/Strategies.html>

## Starter files

The `starter/` directory ships skeletons for the key modules. Each is `py_compile`-clean but contains `TODO` markers where you implement the load-bearing logic. The starter is *not* a finished implementation — fewer than 400 lines total, all the wiring is in place, but every interesting function body raises `NotImplementedError` until you fill it in.

```text
starter/
├── settings.py       (the pydantic-settings config; cache TTLs)
├── schemas.py        (the Pydantic models)
├── cache.py          (the cache client + CoalescingCache skeleton)
├── invalidation.py   (the Pub/Sub bus skeleton)
├── main.py           (the FastAPI app with lifespan and router wiring)
└── routers_articles.py (the five-route skeleton)
```

Copy these into your `crunchcache/` package as you start each day.
