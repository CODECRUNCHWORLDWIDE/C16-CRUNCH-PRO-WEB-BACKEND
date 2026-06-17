# Week 9 — Caching with Redis

> *Week 8 made the server stop hanging up. Week 9 makes it stop redoing work it already did. Caching is the cheapest performance lever in any backend — it converts a 200 ms database query into a 1 ms key lookup, a 50 ms templated render into a 0.1 ms string read, an N-plus-one ORM disaster into a single round-trip. The price is correctness. Stale data is a bug; missed-cache cliffs are an outage; a thundering-herd stampede on a popular key is a Friday afternoon you do not want. Week 9 is the discipline of caching: the data types Redis gives you, the four canonical patterns, the eviction policies that govern what stays and what goes, the invalidation strategies that keep the cache honest, and the stampede problem and how to fix it with two lines of code.*

Welcome to Week 9 of **C16 · Crunch Pro Web Backend**. The `crunchreader-api` service from Week 7, extended with WebSocket and ARQ surfaces in Week 8, has one remaining performance liability: every read hits the database. This week we put a Redis cache in front of it. By Sunday the popular endpoints serve from memory at p99 < 5 ms; the database fan-in drops by an order of magnitude; and we have a defensible answer to every question a code reviewer can ask about staleness, invalidation, and what happens when the cache itself goes down.

The work is measure-then-fix, in that order. We do not cache by guessing what is slow. We start with a real `ab` or `hey` run against a hot endpoint, record the baseline p50 / p95 / p99, then add the cache and re-run the same load. The improvement is reported in absolute numbers and the explanation is reported in milliseconds-per-step. "It feels faster" is not an acceptable answer.

We approach the topic by reading the spec first. Redis is documented at <https://redis.io/docs/latest/> with a discipline that puts most software documentation to shame — each command page lists the time complexity, the available flags, and the version it was introduced in. The five data types we use this week (string, hash, list, set, sorted set) plus the one we touch (stream) are each one page in the data-types section. The eviction policies are one page in the configuration section. The Pub/Sub primitive carries over unchanged from Week 8. The reading load is light; the discipline is to read it.

By Sunday you will have:

1. A measured baseline of an expensive view that hits the database, captured with `ab` (Apache Bench) and `hey` (the Golang load tester), with p50 / p95 / p99 latencies and throughput in requests per second.
2. The same view cached with the **cache-aside** pattern via `redis-py`, with the same load test repeated, and a written report on the latency reduction and the database query count drop.
3. A second variant of the same view cached via Django's cache framework (or FastAPI middleware / dependency for the FastAPI track), demonstrating that the framework abstraction and the bare `redis-py` call produce the same shape on the wire.
4. A documented invalidation strategy: which writes invalidate which keys; the trade-offs between event-driven (Pub/Sub on the write), TTL-based (set-and-forget), and tag-based (groups of keys deleted together).
5. A working **request-coalescing** layer that prevents the cache stampede: when one hundred concurrent requests miss the cache for the same key, exactly one of them goes to the database; the other ninety-nine wait on the first one's result. We cite **Vattani, Chierichetti, and Lowenstein, "Optimal Probabilistic Cache Stampede Prevention" (VLDB 2015, arXiv:1504.00922)** as the source of the probabilistic-early-expiration alternative.
6. A Redis-backed session store for both Django and FastAPI, demonstrating the cache's third role (after read-cache and rate-limit) as the canonical place for "small, fast, expirable, shared-across-workers state".

The async story you have been refining since Week 7 stays in the foreground. `redis.asyncio` is the same Python `redis-py` client with `await` on every method, and the cache-aside pattern is the cleanest example yet of "do the slow thing once; await the fast thing afterwards". If Week 8 was the *workload* week, Week 9 is the *latency* week.

## Learning objectives

By the end of this week, you will be able to:

- **Name** Redis's five primary data types and one streaming type, and choose the right one for a given caching shape. The five: **string** (the workhorse — JSON-serialised values, counters, lock tokens); **hash** (a flat map for object-shaped values, where you may want to update one field without rewriting the whole record); **list** (a queue or a recent-items feed); **set** (membership tests, deduplication); **sorted set** (leaderboards, rate limiters, time-ordered indexes). The sixth, **stream** (XADD, XREAD), is the durable log; we touch it once and contrast it to Pub/Sub. Cite the [Redis data types overview](https://redis.io/docs/latest/develop/data-types/).
- **Implement** the four canonical caching patterns in `redis-py`: **cache-aside** (the application reads the cache; on miss, reads the source, writes the cache, returns); **read-through** (a library or framework hides the same logic behind a single `get(key)` call); **write-through** (every write to the source also writes the cache, synchronously); **write-behind** (the application writes to the cache; a background job propagates the write to the source asynchronously). Cite Phil Bernstein's "Principles of Transaction Processing" (Chapter 6, "Caching and Data Consistency") for the formal definitions, and the [`redis-py` documentation](https://redis-py.readthedocs.io/) for the API surface.
- **Configure** Redis's eviction policy to match the workload: **`noeviction`** (the default — Redis returns an error when out of memory; the right choice for queues and lock servers, the wrong choice for caches); **`allkeys-lru`** (evict any key by least-recently-used — the canonical cache policy); **`allkeys-lfu`** (least-frequently-used — better for skewed access patterns where a few keys dominate); **`volatile-ttl`** (among keys with TTL, evict the one closest to expiry — useful when most keys have TTL and you want predictable churn); **`volatile-lru`** and **`volatile-lfu`** (the same as their `allkeys` counterparts, but restricted to TTL-bearing keys). Cite the [Redis eviction documentation](https://redis.io/docs/latest/operate/oss_and_stack/management/config/#maxmemory-policy).
- **Choose** between event-driven, TTL-based, and tag-based invalidation. Event-driven (the write path publishes a `delete:articles:42` message; every cache subscribes and reacts) gives near-zero staleness at the cost of an extra Pub/Sub hop. TTL-based (`SET key value EX 300`) bounds staleness at 5 minutes by physics; no co-ordination needed. Tag-based (every cached page lists the entities it depends on; deleting any entity sweeps all dependent pages) is the most flexible and the most code; we build it in Exercise 3.
- **Diagnose and fix** the cache stampede. When a popular key expires, every concurrent request misses, every one of them rebuilds the value, and the database takes N times the load it should. Two well-known fixes: **request coalescing** (one in-flight rebuild per key; the rest wait on a `Future` or a Redis lock); **probabilistic early expiration** (each requesting process rolls a dice based on the time-to-live remaining; one of them refreshes before the cache actually expires). Cite **Vattani et al., "Optimal Probabilistic Cache Stampede Prevention" (arXiv:1504.00922, VLDB 2015)** — the canonical paper, free on arXiv.
- **Build** a Redis-as-session-store for both **Django** (via `django-redis` or the built-in `django.contrib.sessions.backends.cache` with the Redis backend) and **FastAPI** (via the `redis.asyncio` client behind a middleware or a dependency that hydrates a session dict from a cookie-borne session ID). Cite the [Django sessions framework documentation](https://docs.djangoproject.com/en/5.1/topics/http/sessions/) and the [Django cache framework documentation](https://docs.djangoproject.com/en/5.1/topics/cache/).
- **Measure** the impact. Run `ab -n 1000 -c 50 http://localhost:8000/articles/popular` before and after caching; record p50, p95, p99, and requests-per-second; record the database query count via Django Debug Toolbar (or FastAPI's SQLAlchemy logger). Reproduce the numbers in your homework. We use both **ab** (Apache Bench, ships with Apache httpd's binaries) and **hey** (a Go-based modern equivalent, `brew install hey` or `apt install hey`) because each has quirks the other does not — `ab` reports its percentiles bluntly; `hey` draws a histogram you can read at a glance.
- **Defend** the trade-off in code review: "We cache the article list with TTL 60 s and event-driven invalidation on publish; we cache the per-article render with tag-based invalidation under tags `article:{id}`, `author:{id}`. We use `allkeys-lru` because 90% of our keys are cache and we are happy for the lock keys to be evicted under memory pressure. The stampede mitigation is probabilistic early expiration with `beta=1.0` per Vattani 2015."

## Prerequisites

- **C16 Week 7 and Week 8** — you have a FastAPI service with Pydantic v2 schemas, a SQLAlchemy / async-SQL session, and an ARQ worker pool. The Pub/Sub plumbing from Week 8 carries over directly to Week 9's invalidation work.
- **Redis 7.x available locally.** `brew install redis`, `apt install redis-server`, or `docker run -p 6379:6379 redis:7-alpine`. Verify with `redis-cli ping` → `PONG`. We use 7.x specifically because the eviction-policy names stabilised in 6 and the `CLIENT NO-EVICT` flag we want for the stampede demo is 7-only.
- **`ab` (Apache Bench) and `hey` installed.** `ab` ships with `apache2-utils` on Debian/Ubuntu and with `httpd` on macOS (`brew install httpd`). `hey` is a single Go binary: `brew install hey` or download from <https://github.com/rakyll/hey/releases>. Verify with `ab -V` and `hey -h`.
- **`redis-cli` literacy.** You can `SET`, `GET`, `EXPIRE`, `TTL`, `DEL`, `KEYS` (responsibly), `SUBSCRIBE`, `PUBLISH`, `INFO memory`. If those are foggy, run through the [Redis interactive tutorial](https://redis.io/learn/) before opening Lecture 1.
- **A baseline understanding of "what is slow".** You should be comfortable opening a database query plan (`EXPLAIN ANALYZE`) and reading the milliseconds. If you do not yet know whether your slow endpoint is slow because of the database, the JSON serialisation, or the network — start there before adding a cache.

## Topics covered

- Redis data types: string, hash, list, set, sorted set; the `MSET` / `HSET` / `LPUSH` / `SADD` / `ZADD` command families; the `O(1)` versus `O(log n)` operations and what they mean for cache hot paths
- Redis Streams briefly — XADD, XREAD, consumer groups — and why we still pick Pub/Sub for fire-and-forget cache invalidation
- Key naming conventions: the colon-separated namespace (`articles:42:render:en`), why versioning your prefix (`v2:articles:...`) is the cleanest cache-clear-on-schema-change pattern
- TTL: `EXPIRE`, `EXPIREAT`, `SET key value EX seconds`, `SET key value PX milliseconds`, `PERSIST`; what `TTL key` returns (`-2` no key, `-1` no TTL, `n` seconds remaining)
- The four caching patterns: cache-aside, read-through, write-through, write-behind; the consistency model each provides; when each is right
- The cache-aside transaction: `GET` → on miss, `acquire lock` → `SELECT` → `SETEX` → `release lock`; the lock is what prevents the stampede
- The eviction policies: `noeviction`, `allkeys-lru`, `allkeys-lfu`, `allkeys-random`, `volatile-lru`, `volatile-lfu`, `volatile-random`, `volatile-ttl`; the `INFO memory` and `INFO stats` keys to monitor (`evicted_keys`, `keyspace_hits`, `keyspace_misses`)
- Invalidation strategies: event-driven (Pub/Sub), TTL-based, tag-based; the cache-coherence problem in distributed systems and why "cache invalidation" is one of the two hard problems
- The cache stampede: the failure mode in words, in graphs, and in production logs; two fixes (request coalescing, probabilistic early expiration)
- Vattani et al. 2015 in detail: the XFetch algorithm, the `delta * log(rand())` formula, the `beta` parameter, the proof sketch that the optimal `beta` is 1.0
- Redis-as-session-store: the session-cookie pattern, the session-key naming, sliding TTL ("user is active") versus fixed TTL ("login expires at midnight"), what `SESSION_ENGINE` does in Django
- FastAPI session middleware: the `starlette.middleware.sessions.SessionMiddleware` with the `secret_key`, the cookie-based default versus the Redis-backed extension we write
- Cache observability: hit ratio, miss ratio, eviction count, key count over time; the four numbers worth a Grafana panel
- Failure modes: Redis is down (degrade to source-of-truth); Redis is slow (timeout and degrade); a key is hot (one key serves 90% of traffic, every miss kills the database); the cache is poisoned (a write of bad data persists for the TTL)
- Cost of caching wrongly: the staleness budget; the "two-tier cache" anti-pattern (in-process LRU plus Redis); the cardinality explosion when you cache by every query parameter combination
- Apache Bench (`ab`) and `hey`: the flags worth memorising (`-n` count, `-c` concurrency, `-t` time limit; for `hey`, `-z` duration and `-q` rate limit); how each reports percentiles; the systematic biases each has

## Weekly schedule

The schedule below totals approximately **35 hours**. The lecture density is similar to Week 8 because the three topics (the data types and patterns, invalidation and eviction, the stampede and sessions) are each independent and deserve their own session.

| Day       | Focus                                                                              | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|------------------------------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Redis data types and the four caching patterns                                     | 2h       | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6h          |
| Tuesday   | Eviction policies, invalidation strategies, and the keyspace                       | 2h       | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6h          |
| Wednesday | The cache stampede; sessions in Django and FastAPI                                  | 2h       | 1.5h      | 1h         | 0.5h      | 1h       | 0h           | 0.5h       | 6.5h        |
| Thursday  | Measure-then-fix: `ab`, `hey`, the before-and-after report                          | 0h       | 1h        | 1h         | 0.5h      | 1h       | 2h           | 0.5h       | 6h          |
| Friday    | Build the cache layer on the Week 7 service                                         | 0h       | 0h        | 1h         | 0.5h      | 1h       | 2h           | 0h         | 4.5h        |
| Saturday  | Tests, docs, the README explaining the invalidation map                             | 0h       | 0h        | 0h         | 0h        | 1h       | 3h           | 0h         | 4h          |
| Sunday    | Quiz, reflection, write the "what eviction policy and why" defence                  | 0h       | 0h        | 0h         | 0.5h      | 0h       | 0h           | 0h         | 0.5h        |
| **Total** |                                                                                    | **6h**   | **6.5h**  | **3h**     | **3h**    | **6h**   | **7h**       | **2h**     | **33.5h**   |

The week's pacing puts the three pillars on three consecutive days — data and patterns, eviction and invalidation, stampede and sessions — then integrates them Thursday onward. The mini-project is a measure-then-fix exercise: a deliberately slow endpoint that becomes a fast endpoint, with the numbers reported in a `BENCHMARK.md`.

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview |
| [resources.md](./01-resources.md) | redis.io, redis-py, Django cache framework, FastAPI middleware, the Vattani 2015 stampede paper, Bernstein's TP chapters, the references worth bookmarking |
| [lecture-notes/01-redis-data-types-and-the-four-cache-patterns.md](./02-lecture-notes/01-redis-data-types-and-the-four-cache-patterns.md) | String, hash, list, set, sorted set; cache-aside, read-through, write-through, write-behind; the `redis-py` API |
| [lecture-notes/02-eviction-policies-and-invalidation-strategies.md](./02-lecture-notes/02-eviction-policies-and-invalidation-strategies.md) | TTL, `allkeys-lru` vs `allkeys-lfu` vs `volatile-ttl`, event-driven vs TTL vs tag-based invalidation |
| [lecture-notes/03-the-cache-stampede-and-redis-sessions.md](./02-lecture-notes/03-the-cache-stampede-and-redis-sessions.md) | The stampede problem; request coalescing; probabilistic early expiration (Vattani 2015); Django and FastAPI session stores |
| [exercises/exercise-01-cache-aside-pattern.py](./03-exercises/exercise-01-cache-aside-pattern.py) | Implement cache-aside on a slow function; observe the latency drop |
| [exercises/exercise-02-eviction-and-ttl-experiments.py](./03-exercises/exercise-02-eviction-and-ttl-experiments.py) | Configure `maxmemory` and an eviction policy; watch keys get evicted in real time |
| [exercises/exercise-03-tag-based-invalidation.py](./03-exercises/exercise-03-tag-based-invalidation.py) | Build a tag-based invalidation layer; a write that touches one entity sweeps all pages depending on it |
| [exercises/exercise-04-stampede-with-coalescing.py](./03-exercises/exercise-04-stampede-with-coalescing.py) | Reproduce the stampede; fix it with single-flight request coalescing and with XFetch |
| [exercises/SOLUTIONS.md](./03-exercises/SOLUTIONS.md) | Worked solutions, with explanation of the trickier lines |
| [challenges/challenge-01-cache-vs-no-cache-benchmark.md](./04-challenges/challenge-01-cache-vs-no-cache-benchmark.md) | Take an expensive view; measure with `ab` and `hey`; report p50 / p95 / p99 before and after |
| [challenges/challenge-02-redis-session-store-django-fastapi.md](./04-challenges/challenge-02-redis-session-store-django-fastapi.md) | Implement Redis sessions for both Django and FastAPI; compare the surface area |
| [quiz.md](./05-quiz.md) | 10 multiple-choice questions |
| [homework.md](./06-homework.md) | Six problems (~6 h) |
| [mini-project/README.md](./07-mini-project/00-overview.md) | Build `crunchcache` — a measure-then-fix cache layer on the Week 7 service, with a `BENCHMARK.md` containing the numbers |
| [mini-project/starter/](./07-mini-project/starter/) | Starter files: cache client, invalidation bus, settings, benchmark harness |

## Before Monday — verify the environment

Seven checks. If any fails, fix it before opening Lecture 1.

```bash
# 1. Python 3.12+
python3 --version
# Python 3.12.x or 3.13.x

# 2. Redis 7.x is reachable
redis-cli ping
# PONG
redis-cli INFO server | grep redis_version
# redis_version:7.x.x

# 3. ab (Apache Bench)
ab -V | head -1
# This is ApacheBench, Version 2.3 <$Revision: ...>

# 4. hey
hey -h 2>&1 | head -1
# Usage: hey [options...] <url>

# 5. Week 7/8 stack still imports
python3 -c "import fastapi, redis, redis.asyncio, pydantic; print('ok')"
# ok

# 6. Install this week's added dependencies
pip install 'redis[hiredis]==5.0.*' 'cachetools==5.5.*' 'fakeredis==2.25.*'

# 7. Confirm Django + django-redis (for the challenge and the session-store work)
pip install 'django==5.1.*' 'django-redis==5.4.*'
python3 -c "import django, django_redis; print(django.__version__, django_redis.__version__)"
# 5.1.x 5.4.x
```

If `redis-cli ping` hangs or returns nothing, Redis is not running. `brew services start redis` on macOS; `sudo systemctl start redis-server` on Debian/Ubuntu; `docker start <redis-container-name>` if you ran it under Docker.

## The habit to install this week

Four practices, applied to every endpoint and every database read you write from here on:

1. **Measure first; cache second.** The endpoint that does not have a benchmark does not have a cache. Run `ab -n 500 -c 20 <url>` against the bare endpoint; record p50, p95, p99. Add the cache. Re-run. The two numbers and the difference go into the commit message. "I cached it because we agreed to cache popular endpoints" is not a justification; the millisecond delta is.
2. **Every cached value has an invalidation story.** Before you write `await redis.set(key, value, ex=300)`, write the comment that answers "what makes this key stale, and how do we invalidate it?". If the answer is "the TTL expires", the TTL is the staleness budget — write it in seconds and own it. If the answer is "the related write publishes an event", show where that publish happens. If the answer is "we never invalidate", be very sure you are caching something genuinely immutable.
3. **The cache is allowed to be down.** Every cache read goes through a `try / except redis.exceptions.RedisError` that falls back to the source. The cache is a latency optimisation, not a source of truth. The service must run, slowly, with the cache offline. Test this in CI by pointing the cache client at an unreachable host and asserting the endpoints still return 200.
4. **Single-flight every popular key.** A key that serves 1 000 requests per second and has a TTL of 60 seconds will, on every expiry, attempt 1 000 simultaneous rebuilds. One rebuild is right; 999 of them are a stampede. Either request-coalesce (the cleanest fix; one `asyncio.Future` per in-flight rebuild) or use probabilistic early expiration (the cleanest *no-coordination* fix; per Vattani 2015). Pick one before you ship; do not wait for the production incident.

The first practice keeps you honest about what caching is actually doing. The second keeps the cache from going stale silently. The third keeps the cache from being a single point of failure. The fourth keeps the cache from amplifying load instead of absorbing it. Together they are the difference between "we have a Redis instance" and "we have a working cache layer".

## Stretch goals

- Read **Vattani, Chierichetti, and Lowenstein, "Optimal Probabilistic Cache Stampede Prevention", VLDB 2015** (~12 pages, free on arXiv): <https://arxiv.org/abs/1504.00922>. Sections 2 and 3 are the algorithm and the proof; section 5 is the simulation. The paper is short enough to read in a sitting, and the algorithm is two lines of Python at the end.
- Read **Phil Bernstein and Eric Newcomer, "Principles of Transaction Processing" (Morgan Kaufmann, 2nd ed., 2009), Chapter 6** if you have library access; the sample chapter PDF on the publisher's site covers cache-aside and write-through with the textbook rigour. If you do not have access, the chapter summary at <https://www.cs.umb.edu/~poneil/CIDR07P34.pdf> (a related paper by Bernstein) gives the load-bearing definitions.
- Read the **Redis source for `evict.c`** (~1 200 lines, MIT-licensed C): <https://github.com/redis/redis/blob/unstable/src/evict.c>. Find `evictionPoolPopulate`. The function that picks which key to evict is, surprisingly, *sampled* — it does not maintain a perfect LRU list (that would be expensive); it samples 5 keys and evicts the worst. The whole approximation is in 60 lines.
- Read the **`redis-py` `client.py`** (~3 000 lines): <https://github.com/redis/redis-py>. Find `Redis.execute_command`. The pipeline from `r.set("k", "v")` through to the actual socket write is short and worth a read.
- Skim the **Django cache framework source** (`django/core/cache/backends/redis.py`, ~200 lines): <https://github.com/django/django/blob/main/django/core/cache/backends/redis.py>. The wrapper around `redis-py` is small enough to read in 15 minutes.

## Up next

[Week 10 — Observability: structured logging, metrics, and distributed tracing](../week-10-observability-logging-metrics-tracing/) — we have spent nine weeks building things that work. Week 10 makes them legible: structured logs (JSON with `logger.bind(...)`), Prometheus metrics on every endpoint, OpenTelemetry traces across the FastAPI → Redis → Postgres call chain, and the four golden signals — latency, traffic, errors, saturation — on a Grafana dashboard. The cache hit ratio you start tracking this week becomes one of the panels.
