# Week 6 — Resources

All free and publicly accessible. Django 5.x, Celery 5.4.x, Redis 7. Pin Django at `/en/stable/`, which resolves to current 5.x docs. Celery at `/en/stable/` resolves to 5.4 as of this writing.

## Required reading (work through the week)

### Django migrations

- **Django migrations — topic guide** — read end to end; the narrative is short and unusually well-written:
  <https://docs.djangoproject.com/en/stable/topics/migrations/>
- **Migration operations reference** — every `AddField`, `AlterField`, `RunPython`, `RunSQL`, `SeparateDatabaseAndState`:
  <https://docs.djangoproject.com/en/stable/ref/migration-operations/>
- **Data migrations** — the `RunPython` chapter, including why you use `apps.get_model()` instead of importing the model directly:
  <https://docs.djangoproject.com/en/stable/topics/migrations/#data-migrations>
- **Squashing migrations** — when a project has 200 migrations and the first run takes 30 seconds:
  <https://docs.djangoproject.com/en/stable/topics/migrations/#migration-squashing>
- **`django.db.migrations.RunPython`** — API reference, with `noop` and `reverse_code`:
  <https://docs.djangoproject.com/en/stable/ref/migration-operations/#runpython>
- **`django.db.migrations.RunSQL`** — when you need SQL Django cannot express:
  <https://docs.djangoproject.com/en/stable/ref/migration-operations/#runsql>

### Celery

- **Celery — First steps with Django** — the canonical setup guide; the only path through `celery_app.py` you should copy:
  <https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html>
- **Tasks** — the user guide chapter on tasks; covers signatures, retries, time limits, idempotency:
  <https://docs.celeryq.dev/en/stable/userguide/tasks.html>
- **Calling tasks** — `delay`, `apply_async`, `signature`, `chain`, `group`, `chord`:
  <https://docs.celeryq.dev/en/stable/userguide/calling.html>
- **Workers** — concurrency, prefetch, max tasks per child, the `-Q` queue filter:
  <https://docs.celeryq.dev/en/stable/userguide/workers.html>
- **Periodic tasks (beat)** — cron-style schedules, the beat process:
  <https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html>
- **Configuration and defaults** — every Celery setting; skim once, return when something misbehaves:
  <https://docs.celeryq.dev/en/stable/userguide/configuration.html>
- **Routing tasks** — separate queues for slow vs fast work; you will need this in production:
  <https://docs.celeryq.dev/en/stable/userguide/routing.html>

### Redis

- **Redis 7 — Introduction** — what Redis is, the single-threaded event loop, why it is fast:
  <https://redis.io/docs/latest/develop/get-started/>
- **Commands reference** — the canonical command list; you will use `SET`, `GET`, `DEL`, `EXPIRE`, `INCR`, `MGET`, `SETNX`, `EVAL`:
  <https://redis.io/commands/>
- **Key expiration** — TTLs in detail, including the precision guarantees:
  <https://redis.io/docs/latest/develop/use/keyspace/#key-expiration>
- **Persistence** — RDB vs AOF; relevant the day Redis goes down and you ask "is my cache also my database?":
  <https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/>

### Django + Redis

- **Django cache framework** — the full topic guide; `LocMemCache`, `RedisCache`, `DummyCache`:
  <https://docs.djangoproject.com/en/stable/topics/cache/>
- **`django-redis`** — the third-party backend most projects use (Django ships its own as of 4.0, but `django-redis` has more options):
  <https://github.com/jazzband/django-redis>
  <https://django-redis.readthedocs.io/en/latest/>
- **Per-view cache (`@cache_page`)** — the decorator:
  <https://docs.djangoproject.com/en/stable/topics/cache/#the-per-view-cache>
- **Template fragment caching (`{% cache %}`)** — for views that mostly cache cleanly but have a per-user header:
  <https://docs.djangoproject.com/en/stable/topics/cache/#template-fragment-caching>
- **The low-level cache API (`cache.get`, `cache.set`, `cache.get_or_set`)** — the most useful tier; everything else is built on this:
  <https://docs.djangoproject.com/en/stable/topics/cache/#the-low-level-cache-api>

## Django 5 + Celery 5 specifics worth knowing

- **Django 5.0 release notes — Async ORM additions** — `aget`, `acreate`, async query support:
  <https://docs.djangoproject.com/en/stable/releases/5.0/>
- **Django async views** — `async def` views, ASGI, when each is right:
  <https://docs.djangoproject.com/en/stable/topics/async/>
- **Celery 5.4 release notes** — `worker_concurrency` defaults, `task_default_queue`, deprecated settings:
  <https://docs.celeryq.dev/en/stable/changelog.html>

## The references worth bookmarking forever

- **Strong Migrations (Ruby gem, but the README is platform-neutral)** — the canonical list of "migrations that will lock your table". Read the README even if you never touch Ruby:
  <https://github.com/ankane/strong_migrations>
- **PostgreSQL — Lock levels** — what `ACCESS EXCLUSIVE` means, who holds what when you `ALTER TABLE`:
  <https://www.postgresql.org/docs/16/explicit-locking.html>
- **`django-pgtrigger`** — the modern way to write triggers Django can manage in migrations:
  <https://django-pgtrigger.readthedocs.io/en/latest/>
- **`flower`** — Celery monitoring UI; `pip install flower`, `celery -A app flower`, browse `:5555`:
  <https://flower.readthedocs.io/en/latest/>
- **Real World HTTP caching** — for context when you build the front-end of cached responses:
  <https://httptoolkit.com/blog/cache-control/>

## On cache stampedes and the hard cache problem

- **"Caches are hard"** — a community-collected list of cache pathologies. Read the section on stampedes:
  <https://github.com/charity/cache-papers> (or search "cache stampede mitigation")
- **The `lock_and_load` recipe** — concrete Django + Redis implementation:
  <https://realpython.com/caching-external-api-requests/> (skim; the Lock pattern in the article is reusable)
- **PEP 583 / probabilistic early expiration (XFetch)** — the academic shape of "refresh slightly before TTL with probability proportional to time since last refresh":
  <https://www.cs.bu.edu/~atrachtenberg/papers/sigmod15-vldb.pdf> (optional; the practical version is two lines of Python)

## On Celery idempotency, retries, and at-least-once

- **"Why your Celery tasks should be idempotent"** — the talk that named the pattern. Search for it on YouTube; the slides are public:
  Search: "Celery idempotency talk"
- **Distributed Systems for Fun and Profit — At-least-once delivery** — the textbook chapter (free online):
  <http://book.mixu.net/distsys/single-page.html>
- **"You don't need Kafka"** (blog) — when a Celery queue is already the right tool and you do not need a streaming platform:
  Search the title; written by several different authors over the years; all reach the same conclusion

## Tools to install before Monday

- **`celery[redis]==5.4.*`** — `pip install 'celery[redis]==5.4.*'`. The `[redis]` extra pulls the `redis` Python client.
- **`django-redis==5.4.*`** — `pip install django-redis==5.4.*`. The cache backend.
- **`flower`** — `pip install flower`. Optional but recommended; the Celery dashboard.
- **`redis-cli`** — bundled with `redis-tools`. If you do not have it, `docker compose exec redis redis-cli` works just as well.
- **`Pillow==10.*`** — `pip install Pillow`. Required for the mini-project; thumbnail generation lives in Pillow.

## Glossary

| Term | Definition |
|------|------------|
| **Migration** | An ordered, reversible change to the database schema and/or data, expressed as Python operations |
| **`makemigrations`** | Inspects model changes vs the migration history and writes a new migration file |
| **`migrate`** | Applies pending migrations against the database |
| **`sqlmigrate`** | Prints the SQL a migration will run, without running it |
| **`AddField` / `AlterField` / `RemoveField`** | Schema operations Django generates from model changes |
| **`RunPython`** | Executes arbitrary Python during a migration; the canonical data-migration operation |
| **`RunSQL`** | Executes arbitrary SQL during a migration; the canonical escape hatch |
| **`SeparateDatabaseAndState`** | An operation that changes Django's view of the schema without touching the database — used for two-phase deploys |
| **Data migration** | A migration whose purpose is to mutate data, not schema; almost always `RunPython` |
| **Reversibility** | A migration's `reverse_code` (for `RunPython`) or `reverse_sql` (for `RunSQL`); `migrations.RunPython.noop` is a legitimate reverse |
| **Squash** | Collapse N migrations into one; equivalent on a fresh database, faster to apply |
| **Broker** | The message bus that holds tasks until a worker claims them. Here: Redis 7 |
| **Worker** | A separate process that fetches tasks from the broker and runs them |
| **Beat** | A separate process that schedules periodic tasks; pushes them to the broker on a cron |
| **Result backend** | Storage for task return values and state; here: Redis 7 again, on a different database number |
| **`delay()`** | Convenience: `task.delay(args)` is `task.apply_async(args=(args,))` |
| **`AsyncResult`** | The handle returned by `delay()`; `.get()` blocks, `.ready()` is non-blocking, `.state` is the current state |
| **Idempotent** | Running the operation twice produces the same outcome as running it once |
| **At-least-once** | The contract Celery offers: the task runs **at least** once; it may run twice |
| **Retry** | A task that fails can be re-queued automatically; `autoretry_for=(Exception,)` is the easy setup |
| **Soft time limit** | A signal sent to the task to wrap up; if it does not, the hard limit kills the worker |
| **Cache hit** | The key exists in Redis with non-expired TTL; the value is returned without computing |
| **Cache miss** | The key does not exist or has expired; the value must be computed and stored |
| **TTL** | Time-to-live; how long Redis keeps the key before expiring it |
| **Cache stampede** | Many concurrent requests miss the cache simultaneously and all compute the same value |
| **Cache-aside** | The application reads from cache; on miss, reads from source, writes back, returns |
| **Invalidation** | Explicit `cache.delete(key)` triggered by a `post_save` signal or equivalent |

---

*Broken link? Open an issue. Celery docs occasionally renumber chapters between minor versions — `/en/stable/` is generally safe; `/en/5.4/` is explicit.*
