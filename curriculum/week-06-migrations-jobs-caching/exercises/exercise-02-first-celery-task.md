# Exercise 2 — Your first Celery task

**Time:** ~2 hours. **Goal:** Wire Celery 5.4 into `crunchwriter`, send a task from a view, watch the worker run it, write a task with retries and a soft time limit. By the end of this exercise the worker process is part of the project's normal development environment, started as routinely as `manage.py runserver`.

Work in your `crunchwriter` repo. Save the write-up to `c16-week-06/exercises/02-celery.md`.

## Setup

Confirm Redis is running:

```bash
docker compose up -d redis
docker compose exec redis redis-cli PING
# PONG
```

Install Celery and the Redis client:

```bash
pip install 'celery[redis]==5.4.*' django-redis==5.4.*
celery --version
# 5.4.x
```

Commit the change to `requirements.txt` (or `pyproject.toml`).

## Part A — Wire the Celery app

Create `crunchwriter/celery_app.py`:

```python
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crunchwriter.settings")

app = Celery("crunchwriter")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
    return "ok"
```

Edit `crunchwriter/__init__.py` to add:

```python
from .celery_app import app as celery_app

__all__ = ("celery_app",)
```

Edit `crunchwriter/settings.py` to add the Celery section (place it near other infrastructure settings, like `DATABASES`):

```python
# Celery
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
```

Start a worker in a second terminal:

```bash
celery -A crunchwriter worker -l info
```

You should see output ending with:

```
[tasks]
  . crunchwriter.celery_app.debug_task

[INFO/MainProcess] Connected to redis://localhost:6379/0
[INFO/MainProcess] celery@hostname ready.
```

If the worker fails to start, three checks: Redis is up (`docker compose ps`), `DJANGO_SETTINGS_MODULE` is set correctly, and the `crunchwriter/__init__.py` import is present (without it, `celery -A crunchwriter` will not find `celery_app`).

**Paste the worker startup output into the write-up.**

## Part B — Send your first task

In a third terminal, open the Django shell:

```bash
python manage.py shell
```

Run:

```python
from crunchwriter.celery_app import debug_task

result = debug_task.delay()
print(result.id)
# UUID string

result.get(timeout=5)
# "ok"
```

In the worker terminal, you should see:

```
[INFO/MainProcess] Task crunchwriter.celery_app.debug_task[uuid] received
[WARNING/ForkPoolWorker-1] Request: <Context: ...>
[INFO/ForkPoolWorker-1] Task crunchwriter.celery_app.debug_task[uuid] succeeded in 0.001s: 'ok'
```

**Paste the shell `delay()` call AND the matching worker log lines into the write-up.** The point is to see the producer (shell) and the worker (worker terminal) exchange the task ID — they are different processes, communicating via Redis.

In a fourth terminal (or temporarily), inspect what Redis saw:

```bash
docker compose exec redis redis-cli MONITOR
# leave this running while you call debug_task.delay() again from the shell
```

You should see Redis commands like `LPUSH celery` and `BRPOP celery` flowing as the producer queues and the worker consumes. **Paste a sample of the MONITOR output.**

## Part C — Write a real task in `writer/tasks.py`

Create `writer/tasks.py`:

```python
import time
from celery import shared_task


@shared_task
def slow_add(x: int, y: int, delay_seconds: float = 1.0) -> int:
    time.sleep(delay_seconds)
    return x + y
```

Restart the worker (it will not pick up new modules until restarted, unless you run with `--reload`).

From the shell:

```python
from writer.tasks import slow_add

# Synchronous baseline
result = slow_add.delay(2, 3, delay_seconds=1.0)
print(result.state)
# "PENDING" or "STARTED"
result.get(timeout=5)
# 5, after ~1 second
```

Now fan out three tasks concurrently:

```python
results = [slow_add.delay(i, i + 1, delay_seconds=2.0) for i in range(3)]
[r.get(timeout=10) for r in results]
# Roughly 2 seconds total wall-clock if you have 3+ worker processes; 6 seconds with 1
```

**Time the difference.** Run with `--concurrency=1` and again with `--concurrency=4`; paste the timings.

```bash
celery -A crunchwriter worker -l info --concurrency=1
# vs
celery -A crunchwriter worker -l info --concurrency=4
```

In the write-up, state: with `--concurrency=N`, up to N tasks run in parallel in separate processes. Each Celery worker is a process pool; the number you set is the pool size.

## Part D — Add a retry

Edit `writer/tasks.py`:

```python
import random
from celery import shared_task


class TransientError(Exception):
    """Pretend this is a network error from a flaky upstream."""


@shared_task(
    autoretry_for=(TransientError,),
    retry_backoff=True,
    retry_backoff_max=30,
    retry_jitter=True,
    max_retries=3,
)
def flaky_task(article_id: int) -> str:
    if random.random() < 0.5:
        raise TransientError(f"flaky failure on article {article_id}")
    return f"article {article_id} processed"
```

Restart the worker. From the shell, call it repeatedly:

```python
from writer.tasks import flaky_task

for i in range(10):
    r = flaky_task.delay(article_id=i)
    print(i, r.get(timeout=30))
```

About half the tasks succeed on the first try; the others retry with exponential backoff. **Paste the worker log lines showing a retry happening.** You should see `Retry in Ns: TransientError(...)` followed eventually by a `succeeded` or `FAILURE`.

In the write-up, explain in your own words:

- What does `autoretry_for=(TransientError,)` do? When would you use it vs `self.retry(exc=...)` explicitly?
- What does `retry_backoff=True` do? What is the default backoff sequence?
- What does `retry_jitter=True` do? When would you set it to `False`?
- After `max_retries=3`, what is the final state of the task? Confirm by calling `r.state` after a task that exhausted its retries.

## Part E — Add a soft time limit

Edit the task again:

```python
from celery.exceptions import SoftTimeLimitExceeded

@shared_task(
    soft_time_limit=3,
    time_limit=5,
)
def slow_task(seconds: float) -> str:
    try:
        time.sleep(seconds)
        return f"slept {seconds}s"
    except SoftTimeLimitExceeded:
        return f"interrupted after the soft limit"
```

Call it with various durations:

```python
slow_task.delay(1).get(timeout=10)
# "slept 1s"

slow_task.delay(4).get(timeout=10)
# "interrupted after the soft limit" — the soft limit raised at 3s

# slow_task.delay(10) — would be killed at the 5s hard limit, AsyncResult.state -> FAILURE
```

**Paste the worker logs** showing the soft-limit signal arriving and the task handling it gracefully.

In the write-up: under what circumstance is `time_limit` (hard limit) the correct fallback? Under what circumstance is it never reached because the soft limit suffices?

## Part F — Run a task synchronously in tests

For tests, you want tasks to run **inline** in the same process, no broker required. Add to a test settings file or use `override_settings`:

```python
# crunchwriter/test_settings.py (or settings_test.py — whichever your project uses)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
```

`ALWAYS_EAGER = True` makes `task.delay(...)` run synchronously and return a completed `AsyncResult`. `EAGER_PROPAGATES = True` re-raises exceptions in the calling process (otherwise the test does not see the failure).

Write a test in `writer/tests/test_tasks.py`:

```python
from django.test import TestCase, override_settings
from writer.tasks import slow_add


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class SlowAddTests(TestCase):
    def test_slow_add_returns_sum(self):
        result = slow_add.delay(2, 3, delay_seconds=0)
        self.assertEqual(result.get(), 5)
```

Run:

```bash
python manage.py test writer.tests.test_tasks
```

The test should pass without a worker running. **Paste the test output.**

In the write-up: why is `ALWAYS_EAGER` only for tests? What are the two things eager mode misses (clue: serialisation, prefetch behaviour)?

## Part G — Write-up

`c16-week-06/exercises/02-celery.md` should contain:

1. The worker startup output.
2. The `delay()` call + matching worker log for `debug_task`.
3. The Redis `MONITOR` snippet showing the broker traffic.
4. The concurrency comparison (1 vs 4 process timings).
5. The retry log showing a `TransientError` retried with backoff, including the final state of a task that exhausted retries.
6. The soft-time-limit log showing graceful handling at 3 seconds.
7. The test in `test_tasks.py` and the test output.
8. Three paragraphs of reflection — see the questions in Parts D, E, and F above.

## Acceptance criteria

- [ ] `crunchwriter/celery_app.py`, `crunchwriter/__init__.py` updated, settings configured.
- [ ] A worker starts, registers tasks, and processes `debug_task` end-to-end.
- [ ] `writer/tasks.py` exists with at least `slow_add`, `flaky_task`, `slow_task`.
- [ ] `flaky_task` demonstrates a retry-with-backoff in the worker log.
- [ ] `slow_task` demonstrates `SoftTimeLimitExceeded` handling.
- [ ] A test using `CELERY_TASK_ALWAYS_EAGER=True` passes.
- [ ] Write-up is 200–400 lines, includes all required pastes.

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Wiring correctness | 25% | Worker starts cleanly; tasks register; `delay` round-trips |
| Retry semantics | 25% | The retry log is captured and explained; final state of exhausted task is shown |
| Time limits | 15% | Soft limit raises and is handled; hard limit's role is explained |
| Eager tests | 15% | Test passes; the two omissions of eager mode are named |
| Write-up | 20% | Includes the Redis `MONITOR` snippet; concurrency comparison has actual timings |

## Hints

- **The worker does not auto-reload.** After editing `tasks.py`, kill the worker with Ctrl-C and start it again. Some teams use `watchmedo` or `celery --autoreload` for development; the lecture's `celery -A app worker -l info` is the canonical command.
- **`result.state`** transitions through `PENDING → STARTED → SUCCESS` (or `RETRY` → `STARTED` again → `SUCCESS`/`FAILURE`). `PENDING` does not mean the task is enqueued; it means **the result backend has no record of it**. A typo in the task name returns `PENDING` forever — the worker never received the message because it does not match a registered task name.
- **`celery -A crunchwriter inspect registered`** lists every task the worker knows about. Run it when "the task is queued but never runs" — almost always the name is wrong.
- **`result.get(timeout=5)`** raises `TimeoutError` if the task does not complete in 5 seconds. Useful in tests; do not use in production code (a timeout in production means the worker is overloaded — handle it explicitly).
- **`docker compose exec redis redis-cli FLUSHDB`** clears one database; `FLUSHALL` clears every database. Use carefully — wiping db 1 wipes your Celery result backend.

## What this prepares you for

Exercise 3 caches the analytics dashboard in Redis. The cache backend uses database 2; the Celery broker is database 0; the result backend is database 1. The three are deliberately separate.

The mini-project uses Celery for the thumbnail generation task. The task takes an `Article` instance, opens the uploaded image with Pillow, generates three sizes, writes them to disk, and sets `article.thumbnails_generated_at = now()`. The task is idempotent: if `thumbnails_generated_at` is non-null, it returns immediately. The retry policy is `autoretry_for=(IOError,)` with `max_retries=3` and `retry_backoff=True`. Every piece is in this exercise's components — Friday's work is composing them.
