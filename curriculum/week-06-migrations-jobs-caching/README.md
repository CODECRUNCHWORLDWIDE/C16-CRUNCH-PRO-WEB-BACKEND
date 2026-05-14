# Week 6 — Migrations, Background Jobs, and Caching

> *Week 5 made the analytics dashboard one query per panel. Week 6 makes the queries you do not need to run vanish. Caching saves the database from work it has already done. Celery saves the request/response cycle from work it should never have started. And the migration that fronts both — the one that adds a non-null column to a 10-million-row table on a Friday afternoon — is the migration most engineers will run badly at least once in their career. This week, we run it on purpose, on a small table, with reversibility intact, so the production one is muscle memory rather than panic.*

Welcome to Week 6 of **C16 · Crunch Pro Web Backend**. The data-tier weeks close here. Week 4 made `crunchwriter` legible to PostgreSQL 16; Week 5 made the ORM emit the SQL you wanted, when you wanted it. This week three pieces of infrastructure land on the project at once:

1. **Real-world migrations.** Adding a non-null column to a populated table. Renaming a field without breaking a deploy. Writing a data migration that backfills. Reversing each one when the deploy fails. The Django auto-generated migration is the easy case. The interesting cases are everything else.
2. **Redis caching.** Configuring Django's cache backend against Redis 7. The cache-aside pattern. Per-view and per-fragment caching. Invalidation on save. Cache stampedes, dog-piling, and `lock_and_load` patterns.
3. **Celery 5.x.** Broker, worker, and beat. Sending tasks from a view. Retries, idempotency, and the at-least-once delivery contract. When an `async def` view is enough and when it is not.

By Sunday `crunchwriter` accepts image uploads. The user uploads a 4 MB JPEG; the request returns in under 100 ms; a Celery worker, behind the scenes, generates three thumbnail sizes, optimises them, and writes them to disk. The author's article list shows the thumbnail the moment it is ready. None of this lives in the request/response cycle. The analytics dashboard from Week 5 is cached in Redis with a 60-second TTL and an invalidation hook on `Article.save()`.

This is the week the application stops being a Django project and starts being a system.

## Learning objectives

By the end of this week, you will be able to:

- **Run** the four common "interesting" migrations safely: add a non-null column with a default, rename a column without breaking running code, split a model into two, write a data migration that backfills computed values across millions of rows. For each, you can name the deployment ordering (database before code, code before database) and write the reverse operation.
- **Write** a Django data migration with `RunPython`, including a reverse operation, batch-iteration over large tables with `iterator()` and `bulk_update`, and a stop-resume strategy when the migration must run for hours.
- **Configure** Redis 7 as Django's cache backend (`django-redis`) and as Celery's broker. Distinguish the two roles, the two databases, the two configuration knobs.
- **Apply** the cache-aside pattern by hand: `get`, on miss `compute and set`, return. Then graduate to the per-view (`@cache_page`) and per-fragment (`{% cache %}`) helpers, and know what each one stores under what key.
- **Identify** the cache stampede: 1 000 concurrent requests miss the cache, all 1 000 compute the same answer, the database melts. Mitigate with a probabilistic refresh, a distributed lock, or `lock_and_load`.
- **Build** a Celery 5.x project: `celery_app.py`, `tasks.py`, the worker command, the beat command, the broker URL, the result backend. You can start a worker, send a task, watch it run, and read its return value.
- **Write** an idempotent task — one that can run twice and produce the same outcome. Distinguish at-most-once, at-least-once, and exactly-once delivery semantics.
- **Configure** Celery retries (`autoretry_for`, `retry_backoff`, `max_retries`), task time limits (`soft_time_limit`, `time_limit`), and rate limits.
- **Schedule** a recurring task with Celery beat: the analytics dashboard's panels refresh every 60 seconds in the background; the cache is always warm.
- **Choose** between Django 5 async views (`async def`) and Celery for offloading work. The first is the right answer for I/O-bound work measured in seconds; the second is the right answer for work that must survive a process restart.
- **Reverse** any of the above when production breaks: roll back a migration, invalidate a cache key, revoke a stuck task, drain a worker queue.

## Prerequisites

- **C16 Week 5 mini-project completed** — `crunchwriter` has the four-panel analytics dashboard, each panel emits one SQL query, each panel is covered by `assertNumQueries(1)`. If you skipped the dashboard, the caching exercises will not connect to anything.
- **C16 Week 4** — `EXPLAIN ANALYZE` is reflexive; you can read a Postgres plan. The migration lectures assume you know what `ALTER TABLE ... ADD COLUMN NOT NULL DEFAULT ...` does to a populated table at the lock level.
- **C16 Week 2 migrations basics** — `makemigrations`, `migrate`, `showmigrations`, `sqlmigrate`. If `python manage.py sqlmigrate writer 0007` is unfamiliar, re-read Week 2 Lecture 2 before Monday.
- **Docker installed** — Redis runs in Docker. You should already have `docker compose up redis` working from Week 4. If not, install Docker Desktop or `colima` before Monday.

## Topics covered

- The Django migration framework: `MigrationLoader`, `Operation`, the dependency graph
- `makemigrations` vs `migrate` vs `migrate --plan` vs `migrate --fake`
- Reading the generated migration: `AddField`, `AlterField`, `RemoveField`, `RenameField`, `RunPython`, `RunSQL`
- The "add a non-null column" pattern: nullable first, backfill, then `NOT NULL`
- Rename without downtime: add-then-deprecate the old name; never `RenameField` on a live deploy with running workers
- Splitting a model: `SeparateDatabaseAndState`, two-phase migrations, the read-old/write-both/read-new/write-new dance
- Data migrations with `RunPython` — and why you import models with `apps.get_model()`, never directly
- Batched data migrations with `iterator(chunk_size=...)` and `bulk_update`
- `migrations.RunSQL` for operations Django cannot express (concurrent index creation, custom constraints, PG extensions)
- Reversibility: every `RunPython` has a reverse; every `RunSQL` has a reverse; `migrations.RunPython.noop` is a legitimate choice
- Squashing migrations: when, why, and the gotchas
- Redis 7: data model, single-threaded event loop, basic commands (`SET`, `GET`, `DEL`, `EXPIRE`, `INCR`, `MGET`, `KEYS`)
- Configuring Django's cache framework with `django-redis`
- The cache-aside pattern, written by hand and as `cache.get_or_set`
- `@cache_page` (per-view caching), `{% cache %}` (per-fragment), `cache.set` / `cache.get` (per-anything)
- Cache key design: include version, include user, exclude time, namespace by domain
- The TTL question: 5 s, 60 s, 1 hour, 1 day; how to choose
- The invalidation question: TTL-only vs explicit `cache.delete` on `Article.save()` via `post_save` signal
- The cache stampede: dog-piling at TTL expiry, the `lock_and_load` mitigation, the probabilistic early-refresh
- Celery 5.x architecture: producer (your view), broker (Redis), worker (separate process), result backend (Redis again)
- The Celery app object, task registration, `delay()`, `apply_async()`, the `AsyncResult` handle
- Retries: `autoretry_for=(Exception,)`, `retry_backoff=True`, `retry_jitter=True`, `max_retries=N`
- Idempotency: what it is, why every Celery task should be one, and the three common ways to achieve it
- Task time limits: `soft_time_limit` (raises `SoftTimeLimitExceeded`), `time_limit` (kills the worker)
- Celery beat: cron-style scheduling, the schedule file, beat as a separate process
- Async views (Django 5) vs Celery: when each is right
- Production hygiene: worker concurrency, prefetch multiplier, max tasks per child, monitoring with `flower` or `celery inspect`

## Weekly schedule

| Day       | Focus                                                                      | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Real-world migrations: non-null columns, renames, data migrations          | 2h       | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6h          |
| Tuesday   | Celery: broker, worker, beat; the first task                                | 2h       | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6h          |
| Wednesday | Redis caching patterns: cache-aside, invalidation, stampedes               | 2h       | 2h        | 1h         | 0.5h      | 1h       | 0h           | 0.5h       | 7h          |
| Thursday  | Image upload + Celery task wiring                                          | 0h       | 0.5h      | 1h         | 0.5h      | 1h       | 2h           | 0.5h       | 5.5h        |
| Friday    | Thumbnail generation, retries, idempotency                                 | 0h       | 0h        | 1h         | 0.5h      | 1h       | 2h           | 0h         | 4.5h        |
| Saturday  | Cache the dashboard; invalidate on `Article.save()`; write-up               | 0h       | 0h        | 0h         | 0h        | 1h       | 3h           | 0h         | 4h          |
| Sunday    | Quiz + reflection                                                          | 0h       | 0h        | 0h         | 0.5h      | 0h       | 0h           | 0h         | 0.5h        |
| **Total** |                                                                            | **6h**   | **6.5h**  | **3h**     | **3h**    | **6h**   | **7h**       | **2h**     | **33.5h**   |

The week is balanced toward infrastructure ergonomics. The lectures are short; the exercises drive everything. The mini-project pulls migrations, Celery, and Redis into one coherent feature — image upload with async thumbnail generation — that you can demo end-to-end.

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview |
| [resources.md](./resources.md) | Django migrations, Celery 5.x, Redis 7 — the references worth bookmarking |
| [lecture-notes/01-real-world-migrations.md](./lecture-notes/01-real-world-migrations.md) | Non-null columns, renames, data migrations, reversibility, the deployment ordering |
| [lecture-notes/02-celery-broker-worker-beat.md](./lecture-notes/02-celery-broker-worker-beat.md) | Celery architecture, your first task, retries, idempotency, beat |
| [lecture-notes/03-redis-caching-patterns.md](./lecture-notes/03-redis-caching-patterns.md) | Cache-aside, per-view and per-fragment, invalidation, stampedes |
| [exercises/README.md](./exercises/README.md) | Index of exercises |
| [exercises/exercise-01-data-migration.md](./exercises/exercise-01-data-migration.md) | Backfill a computed column on `crunchwriter` with `RunPython` |
| [exercises/exercise-02-first-celery-task.md](./exercises/exercise-02-first-celery-task.md) | Wire Celery, send your first task, watch it run, write a retry |
| [exercises/exercise-03-cache-aside.md](./exercises/exercise-03-cache-aside.md) | Cache the analytics dashboard panels, invalidate on save, measure the win |
| [challenges/README.md](./challenges/README.md) | Stretch challenge |
| [challenges/challenge-01-image-thumbnails-async.md](./challenges/challenge-01-image-thumbnails-async.md) | Generate three sizes asynchronously, with retries and idempotency |
| [quiz.md](./quiz.md) | 10 MCQ |
| [homework.md](./homework.md) | Six problems (~6h) |
| [mini-project/README.md](./mini-project/README.md) | Image upload + async thumbnail generation in `crunchwriter` |

## Before Monday — verify the project is ready

Four checks. If any fails, fix it before reading Lecture 1.

```bash
# 1. crunchwriter migrations are clean
python manage.py showmigrations writer
# every box should be [X]; no pending migrations

# 2. you have docker compose with redis available
docker compose up -d redis
docker compose ps
# redis should be 'running'

# 3. redis is reachable from your shell
docker compose exec redis redis-cli PING
# PONG

# 4. celery is installed
pip install 'celery[redis]==5.4.*' django-redis==5.4.*
celery --version
# 5.4.x
```

If `docker compose` is unfamiliar, copy this minimal `docker-compose.yml` into the project root:

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --save 60 1 --loglevel warning

volumes:
  redis-data:
```

Then `docker compose up -d redis`. We will add the worker service on Tuesday.

## The habit to install this week

Two practices, applied to every change you ship from here on:

1. **Every migration gets a `sqlmigrate` review.** Before merging, run `python manage.py sqlmigrate writer 0012` and read the SQL Django will run. If the SQL contains `ALTER TABLE ... NOT NULL` on a populated table without a default, the deployment will block on the table-level `ACCESS EXCLUSIVE` lock long enough for the load balancer to give up. Split the migration.
2. **Every Celery task gets an idempotency guard.** The task may run twice; the at-least-once contract guarantees it. The guard can be a database flag (`if obj.processed: return`), a Redis `SETNX` (`if cache.add(key, 1, timeout=3600):`), or a unique-constraint INSERT that fails on the second run. Pick one before writing the task body.

If you do this for every change, the production day where someone "just runs the migration" no longer has consequences worse than a slow rollout.

## Stretch goals

- Read the **Django migrations operations reference** end to end, especially `SeparateDatabaseAndState` and `RunPython.noop`:
  <https://docs.djangoproject.com/en/stable/ref/migration-operations/>
- Read the **Celery user guide on tasks**, especially "Task semipredicates" and "Avoid running tasks that take too long":
  <https://docs.celeryq.dev/en/stable/userguide/tasks.html>
- Install **`flower`** (`pip install flower`) and run `celery -A crunchwriter flower`; visit `http://localhost:5555`. The dashboard shows every task as it runs.
- Read **"Cache me if you can"** by Andrew Godwin (or the equivalent: search "cache stampede mitigation"); the pattern names you learn there will be your shorthand for the rest of your career.

## Up next

[Week 7 — FastAPI Fundamentals](../week-07-fastapi-fundamentals/) — Phase 3 begins. The Django app from Phase 2 keeps writing; a new FastAPI service `crunchreader-api` reads from the same database, returns JSON, generates an OpenAPI spec for free. The Celery tasks and Redis cache you build this week will be reused by the FastAPI side — same broker, same cache keys, two surfaces over one infrastructure.
