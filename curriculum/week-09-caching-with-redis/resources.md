# Week 9 — Resources

All free and publicly accessible. Redis 7.x, redis-py 5.0.x, Django 5.1.x, django-redis 5.4.x, FastAPI 0.115.x, Pydantic 2.9.x, Python 3.12+. Pin docs at the unversioned root where each project supports it; otherwise pin to the latest tag.

## Required reading (work through the week)

### Redis — the manual

- **Redis documentation — root**: <https://redis.io/docs/latest/>. Bookmark; the site is the single canonical reference.
- **Redis data types overview** — the one-page index to string, list, set, hash, sorted set, stream, bitmap, hyperloglog, geo: <https://redis.io/docs/latest/develop/data-types/>
  - **Strings**: <https://redis.io/docs/latest/develop/data-types/strings/>
  - **Hashes**: <https://redis.io/docs/latest/develop/data-types/hashes/>
  - **Lists**: <https://redis.io/docs/latest/develop/data-types/lists/>
  - **Sets**: <https://redis.io/docs/latest/develop/data-types/sets/>
  - **Sorted sets**: <https://redis.io/docs/latest/develop/data-types/sorted-sets/>
  - **Streams**: <https://redis.io/docs/latest/develop/data-types/streams/>
- **Redis commands index** — every command, sorted alphabetically, with time complexity and version note: <https://redis.io/commands/>
  - `SET` with EX/PX/NX/XX flags: <https://redis.io/commands/set/>
  - `GET`: <https://redis.io/commands/get/>
  - `EXPIRE`, `EXPIREAT`, `PEXPIRE`, `TTL`, `PTTL`, `PERSIST`: <https://redis.io/commands/expire/>
  - `DEL`, `UNLINK`: <https://redis.io/commands/del/>, <https://redis.io/commands/unlink/>
  - `MGET`, `MSET`: <https://redis.io/commands/mget/>
  - `HSET`, `HGET`, `HMGET`, `HDEL`, `HGETALL`: <https://redis.io/commands/hset/>
  - `SADD`, `SREM`, `SMEMBERS`, `SISMEMBER`, `SUNION`, `SINTER`: <https://redis.io/commands/sadd/>
  - `ZADD`, `ZRANGE`, `ZRANGEBYSCORE`, `ZRANK`: <https://redis.io/commands/zadd/>
  - `LPUSH`, `RPUSH`, `LPOP`, `BRPOP`, `LRANGE`: <https://redis.io/commands/lpush/>
  - `SCAN` (and the `MATCH` and `COUNT` flags — the right way to enumerate keys; never `KEYS` in production): <https://redis.io/commands/scan/>
  - `INFO`: <https://redis.io/commands/info/>
- **Redis configuration: `maxmemory` and `maxmemory-policy`** — the eviction-policy reference: <https://redis.io/docs/latest/operate/oss_and_stack/management/config/#maxmemory-policy>
- **Redis key-eviction documentation** — the deep dive on `allkeys-lru` versus `allkeys-lfu` and the sampled LRU approximation: <https://redis.io/docs/latest/develop/reference/eviction/>
- **Redis Pub/Sub overview** — carried over from Week 8 for event-driven invalidation: <https://redis.io/docs/latest/develop/interact/pubsub/>
- **Redis client-side caching** — RESP3 tracking, for completeness; we do not use it this week but you should know it exists: <https://redis.io/docs/latest/develop/reference/client-side-caching/>
- **Redis persistence (RDB / AOF)** — to know what a Redis restart costs: <https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/>

### redis-py — the Python client

- **redis-py — root**: <https://redis-py.readthedocs.io/>
- **Connection examples** — `Redis`, `Redis.from_url`, the connection pool: <https://redis-py.readthedocs.io/en/stable/examples/connection_examples.html>
- **Async usage (`redis.asyncio`)** — the `await`-bearing variant we use throughout: <https://redis-py.readthedocs.io/en/stable/examples/asyncio_examples.html>
- **Pipelines** — `r.pipeline()` for batched commands, `transaction=True` for `MULTI/EXEC`: <https://redis-py.readthedocs.io/en/stable/examples/pipeline_examples.html>
- **Pub/Sub usage (async)** — the same pattern as Week 8: <https://redis-py.readthedocs.io/en/stable/advanced_features.html#publish-subscribe>
- **redis-py source** — the `Redis` and `Connection` classes worth reading once: <https://github.com/redis/redis-py>

### Django — the cache framework

- **Django cache framework** — the canonical docs page; covers `caches`, `cache.get`, `cache.set`, the per-view cache decorator, the template fragment caching tag: <https://docs.djangoproject.com/en/5.1/topics/cache/>
  - The Redis backend section: <https://docs.djangoproject.com/en/5.1/topics/cache/#redis>
  - The cache middleware: <https://docs.djangoproject.com/en/5.1/topics/cache/#the-per-site-cache>
  - The per-view cache: <https://docs.djangoproject.com/en/5.1/topics/cache/#the-per-view-cache>
  - The low-level cache API: <https://docs.djangoproject.com/en/5.1/topics/cache/#the-low-level-cache-api>
  - The template fragment cache: <https://docs.djangoproject.com/en/5.1/topics/cache/#template-fragment-caching>
- **Django sessions framework** — the Redis-backed session-engine docs: <https://docs.djangoproject.com/en/5.1/topics/http/sessions/>
  - The cache-backed session engine: <https://docs.djangoproject.com/en/5.1/topics/http/sessions/#using-cached-sessions>
- **django-redis** — the third-party package that wraps redis-py for Django's cache framework; the most-used Redis backend in the Django ecosystem: <https://github.com/jazzband/django-redis>
  - Configuration: <https://github.com/jazzband/django-redis#configure-as-cache-backend>
  - Pickle vs JSON serialiser trade-off: <https://github.com/jazzband/django-redis#pluggable-clients>

### FastAPI / Starlette — middleware and caching

- **FastAPI middleware** — the `@app.middleware("http")` pattern, plus the Starlette `Middleware` class used in `app = FastAPI(middleware=[...])`: <https://fastapi.tiangolo.com/tutorial/middleware/>
  - Advanced middleware (custom classes via `BaseHTTPMiddleware`): <https://fastapi.tiangolo.com/advanced/middleware/>
- **Starlette middleware reference** — what FastAPI inherits: <https://www.starlette.io/middleware/>
- **Starlette sessions** — the cookie-based default; the seed for the Redis-backed extension we build in Challenge 2: <https://www.starlette.io/middleware/#sessionmiddleware>
- **`fastapi-cache2`** — a community-maintained cache library for FastAPI; we cite it for the read-through pattern: <https://github.com/long2ice/fastapi-cache>

### The cache-stampede paper

- **Vattani, Chierichetti, Lowenstein, "Optimal Probabilistic Cache Stampede Prevention" (VLDB 2015)** — the foundational paper for probabilistic early expiration. Free on arXiv, 12 pages, readable in one sitting: <https://arxiv.org/abs/1504.00922>
  - Section 2 defines the cache stampede formally.
  - Section 3 presents the XFetch algorithm (the `delta * log(rand())` formula).
  - Section 4 proves the optimal `beta` value is 1.0.
  - Section 5 simulates the algorithm against the alternatives.
- **The Wikipedia summary** — useful as a refresher after you have read the paper: <https://en.wikipedia.org/wiki/Cache_stampede>

### Caching and consistency — the textbook view

- **Phil Bernstein and Eric Newcomer, "Principles of Transaction Processing" (Morgan Kaufmann, 2nd ed., 2009)** — Chapter 6 ("Caching and Data Consistency") defines cache-aside, read-through, write-through, write-behind with formal precision. The publisher's sample chapter PDF (if your institution has access) is the canonical reference: <https://www.elsevier.com/books/principles-of-transaction-processing/bernstein/978-1-55860-415-4>
- **Bernstein, "Adapting Microsoft SQL Server for Cloud Computing" (CIDR 2007)** — a related, freely available paper that walks the same definitions: <https://www.cs.umb.edu/~poneil/CIDR07P34.pdf>
- **AWS — caching strategies overview** — the same four patterns, illustrated with cloud examples; useful as a second pass after Bernstein: <https://docs.aws.amazon.com/AmazonElastiCache/latest/mem-ug/Strategies.html>
- **Microsoft Architecture Center — Cache-aside pattern** — the same pattern with explicit pseudocode: <https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside>

### Load testing — the tools we use

- **Apache Bench (`ab`) manual page** — the canonical reference; the flags `-n` (request count), `-c` (concurrency), `-t` (time limit), `-k` (keep-alive), `-T` (content type), `-p` (POST body file): <https://httpd.apache.org/docs/2.4/programs/ab.html>
- **`hey` — README and usage**: <https://github.com/rakyll/hey>. The flags `-n`, `-c`, `-z` (duration), `-q` (rate limit), `-H` (header), `-m` (method), `-d` (body).
- **`wrk` — for the curious; the third common option** (we do not use it this week): <https://github.com/wg/wrk>
- **`k6` — Grafana Labs' load tester, JavaScript-scripted; the modern alternative for complex scenarios** (we cite it for the mini-project's stretch goal): <https://grafana.com/docs/k6/latest/>

### Caching libraries in the Python ecosystem

- **`cachetools`** — in-process LRU / TTL caches; complementary to Redis: <https://cachetools.readthedocs.io/>
- **`aiocache`** — an async cache framework supporting Redis, Memcached, and in-memory backends; cite for the read-through abstraction: <https://aiocache.readthedocs.io/>
- **`fakeredis`** — an in-memory Redis fake for tests; supports `redis.asyncio` since v2: <https://github.com/cunla/fakeredis-py>

### Operational and infrastructure references

- **Redis Sentinel** — high-availability documentation (master + replicas + failover); cite only, we do not run it this week: <https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/>
- **Redis Cluster** — sharded Redis for capacity beyond a single node: <https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/>
- **AWS ElastiCache for Redis** — the managed Redis service most teams use in production: <https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/WhatIs.html>
- **Google Cloud Memorystore for Redis**: <https://cloud.google.com/memorystore/docs/redis>

### HTTP — the specs the cache still honours

- **RFC 9110 — HTTP Semantics** — the status codes we still use: <https://datatracker.ietf.org/doc/html/rfc9110>
  - §15.3.1 — 200 OK (the cached response is still a 200)
  - §15.4.5 — 304 Not Modified (the HTTP-level cache validator; orthogonal to the application cache, but worth the comparison)
- **RFC 9111 — HTTP Caching** — the spec for HTTP-level caching (`Cache-Control`, `ETag`, `If-None-Match`); the application cache and HTTP cache often co-exist: <https://datatracker.ietf.org/doc/html/rfc9111>
  - §5.2 — `Cache-Control` directives
  - §8.8 — `ETag` and conditional requests
- **MDN — HTTP caching** — the developer-facing companion to RFC 9111: <https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching>

## Cache-stampede related reading

These are the secondary readings cited in Lecture 3:

- **Nick Craver, "Stack Overflow: How We Do App Caching"** — a working architecture's caching playbook, from a high-traffic production system: <https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/>
- **Facebook's "Scaling Memcache at Facebook" (NSDI 2013)** — the canonical large-scale caching paper; covers the lease / serialise-the-rebuild pattern (their answer to the stampede): <https://www.usenix.org/conference/nsdi13/technical-sessions/presentation/nishtala>
- **"Caching at scale with Redis" — Redis Labs whitepaper** (free download with email): <https://redis.io/blog/caching-at-scale-with-redis/>

## Testing tools

- **`fakeredis` for unit tests**: <https://github.com/cunla/fakeredis-py>
- **`pytest-asyncio`**: <https://pytest-asyncio.readthedocs.io/>
- **Django `TestCase` and the `override_settings` decorator** — for swapping the cache backend in tests: <https://docs.djangoproject.com/en/5.1/topics/testing/tools/#django.test.override_settings>
- **`httpx.AsyncClient` for FastAPI integration tests**: <https://www.python-httpx.org/async/>

## Browser-side and observability references

- **Grafana — Redis dashboard** (a starting point for the four-panel hit-ratio / eviction / memory / op-rate view): <https://grafana.com/grafana/dashboards/763-redis-dashboard-for-prometheus-redis-exporter-1-x/>
- **`redis-exporter`** — Prometheus exporter for Redis; cite for Week 10's observability work: <https://github.com/oliver006/redis_exporter>

## The references worth bookmarking forever

- **`redis/redis` source** — the entire Redis server; the `src/evict.c` is the file to read for eviction-policy implementation: <https://github.com/redis/redis>
- **`redis/redis-py`** — the Python client: <https://github.com/redis/redis-py>
- **`django/django`** — the cache backends are in `django/core/cache/backends/`: <https://github.com/django/django/tree/main/django/core/cache/backends>
- **`encode/starlette`** — the middleware module: <https://github.com/encode/starlette/blob/master/starlette/middleware>
- **The Redis Glossary** — short, opinionated definitions of every Redis concept: <https://redis.io/docs/latest/develop/reference/glossary/>

## Cited in the lectures

These URLs appear by name in the lecture notes:

- **`redis.io/docs/latest/develop/data-types/`** — Lecture 1 (the data-type overview)
- **`redis-py.readthedocs.io/`** — Lecture 1 (the API surface)
- **`redis.io/docs/latest/develop/reference/eviction/`** — Lecture 2 (the eviction reference)
- **`redis.io/docs/latest/operate/oss_and_stack/management/config/`** — Lecture 2 (the `maxmemory-policy` configuration)
- **`docs.djangoproject.com/en/5.1/topics/cache/`** — Lectures 1 and 3 (the Django cache framework)
- **`docs.djangoproject.com/en/5.1/topics/http/sessions/`** — Lecture 3 (the Django sessions framework)
- **`fastapi.tiangolo.com/tutorial/middleware/`** — Lecture 3 (the FastAPI middleware reference)
- **`arxiv.org/abs/1504.00922`** — Lecture 3 (Vattani et al. 2015, the cache-stampede paper)
- **`learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside`** — Lecture 1 (the cache-aside pattern)
- **`docs.aws.amazon.com/AmazonElastiCache/latest/mem-ug/Strategies.html`** — Lecture 1 (the four-pattern overview)
- **`httpd.apache.org/docs/2.4/programs/ab.html`** — Challenge 1, mini-project
- **`github.com/rakyll/hey`** — Challenge 1, mini-project
