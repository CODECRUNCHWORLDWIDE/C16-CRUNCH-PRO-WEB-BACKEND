# Challenge 2 — Celery vs ARQ on a real task

> **Time:** 2-3 hours. **Goal:** Re-implement the `slow_report` task from Exercise 3 in Celery; benchmark both against the same workload; write a side-by-side defence of the choice. The goal is *not* to demonstrate that one is faster than the other — both are fast enough — but to make the trade-off visible in code, in lines, and in operational footprint.

The point of this challenge is that "Celery vs ARQ" is the kind of decision a senior backend engineer is expected to defend in writing. By the end you should have written the same task twice, run it both ways, and produced a short written defence that someone reviewing your architecture decision could read and agree (or disagree) with on the merits.

## What you build

Two parallel implementations of the same task, plus a comparison document:

```text
challenge-02-celery-vs-arq/
├── arq_version/
│   ├── worker.py        (from Exercise 3; copy and adapt)
│   ├── enqueue.py       (a small CLI script that enqueues N jobs)
│   └── README.md
├── celery_version/
│   ├── tasks.py         (the Celery task)
│   ├── celery_app.py    (the Celery configuration)
│   ├── enqueue.py       (the CLI script)
│   └── README.md
├── benchmark.py         (a script that runs N jobs through both and times them)
└── COMPARISON.md        (the 1500-word defence)
```

## Step-by-step

### Step 1 — Set up the Celery worker

Install:

```bash
pip install 'celery[redis]==5.4.*'
```

Create `celery_version/celery_app.py`:

```python
from __future__ import annotations

from celery import Celery

app = Celery(
    "challenge02",
    broker="redis://localhost:6379/1",
    backend="redis://localhost:6379/1",
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
```

Create `celery_version/tasks.py`:

```python
from __future__ import annotations

import time
from typing import Any

import redis

from .celery_app import app


_REDIS = redis.from_url("redis://localhost:6379/1", decode_responses=True)


@app.task(bind=True, max_retries=5, default_retry_delay=2, acks_late=True)
def slow_report(self, label: str, delay_seconds: int = 5) -> dict[str, Any]:
    """The Celery twin of Exercise 3's ARQ task.

    Note: Celery tasks are synchronous by default. The publish call is
    blocking. We use the prefork pool with concurrency tuned to the
    expected job count.
    """
    job_id = self.request.id
    channel = f"job-progress:{job_id}"
    total = max(1, delay_seconds)
    for step in range(1, total + 1):
        _REDIS.publish(channel, f'{{"step": {step}, "of": {total}, "label": "{label}"}}')
        time.sleep(1.0)
    _REDIS.publish(channel, '{"done": true}')
    return {"status": "ok", "job_id": job_id, "label": label, "steps": total}
```

Run the worker:

```bash
celery -A celery_version.celery_app worker --loglevel=info --concurrency=4
```

Note the differences from ARQ:

- Two processes are needed: `celery worker` and, if you wanted scheduled tasks, `celery beat`. ARQ folds both into one.
- The task is *synchronous*. Calling `_REDIS.publish` blocks; the worker can run only as many tasks as it has concurrency slots, and each slot is a forked process.
- The decorator carries the retry policy (`max_retries=5, default_retry_delay=2`). ARQ puts it on the `WorkerSettings`.
- The result of the task returns to the caller via `AsyncResult(...).get()` on the producer side; ARQ has `await pool.get_job_result(...)`.

### Step 2 — Set up the enqueue script

`celery_version/enqueue.py`:

```python
from __future__ import annotations

import sys

from .tasks import slow_report


def main(n: int) -> None:
    for i in range(n):
        result = slow_report.delay(f"job-{i}", 2)
        print(f"enqueued {i}: task_id={result.id}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
```

The ARQ equivalent uses `await pool.enqueue_job(...)`. Note that `slow_report.delay(...)` is the Celery convention for "enqueue this task with these args"; the synchronous call returns an `AsyncResult` whose `.id` is the task ID.

### Step 3 — Benchmark

`benchmark.py` should:

1. Enqueue N jobs (say N=50) on each system.
2. Measure (a) wall-clock time to enqueue all N, (b) wall-clock time until all N are done, (c) the per-job enqueue latency (median, p95).
3. Print a table.

The benchmark is not the point — both will be fast enough for any realistic workload. The point is **observing** how much code you wrote for each, how many processes you have to keep running, and how many configuration knobs each forces you to touch.

### Step 4 — COMPARISON.md

The deliverable. ~1500 words. Five sections, each with a clear claim:

#### Section 1 — Lines of code

Count the lines in each implementation. For the ARQ version, count `worker.py`, the relevant lines of the FastAPI `app.py` that interact with ARQ, and the enqueue script. For the Celery version, count `tasks.py`, `celery_app.py`, and the enqueue script.

Expect ARQ to come in around 30-40 lines lower. Write the actual numbers from your code.

#### Section 2 — Operational footprint

Number of processes required to run each system, in production:

- ARQ: FastAPI (1+ workers) + ARQ worker (1+). Total = 2+.
- Celery: FastAPI (1+ workers) + Celery worker (1+) + optional `celery beat` (1) + optional Flower (1). Total = 2+ baseline, 4 with the full toolkit.

Memory footprint per worker: empirically measure with `ps aux | grep celery` and `ps aux | grep arq`. Celery's prefork model uses more memory because each subprocess holds a full Python interpreter; ARQ's async model uses one interpreter total.

#### Section 3 — Configuration surface

Open `celery/app/defaults.py` and count the configurable settings (around 200). Open `arq/worker.py` and count the keyword arguments on `Worker.__init__` (around 20). The ratio is roughly 10:1.

This is not a strict negative for Celery — many of the settings are vestigial or for specialised use cases. But the *expected* configuration surface for a new project is what matters, and there ARQ is much smaller.

#### Section 4 — Async support

ARQ is async-native. The task runs in the worker's event loop. Inside the task you can `await asyncpg`, `await httpx.AsyncClient`, `await redis.publish` — all concurrent with other in-flight tasks on the same worker.

Celery's task is synchronous by default. To run async code inside a Celery task you either `asyncio.run(...)` (which spins up a new loop per task — fine for the simple case, problematic if the task needs to share resources across calls) or you switch to the `gevent`/`eventlet` pool (which monkey-patches the stdlib's blocking calls into cooperative coroutines — works, but is its own kind of trap).

#### Section 5 — When Celery wins

Be specific. The four conditions Lecture 3 §4 names:

1. You need RabbitMQ or SQS as a broker (e.g. corporate compliance requires AMQP).
2. You need scheduled tasks (`celery beat`).
3. You need mature monitoring (Flower).
4. The team already knows Celery.

For each, write one sentence on whether `crunchexports` (the mini-project) hits the condition. None of them apply. Conclusion: ARQ is the right pick for this service. State the condition under which you would re-evaluate (e.g. "if we add 20 scheduled report types, we revisit Celery").

### Step 5 — Submit

The `COMPARISON.md` is graded. Acceptable answers contain:

- The actual line counts.
- The actual memory footprint numbers.
- A concrete claim about which broker each project's deployment uses.
- A concrete claim about whether scheduled tasks are on the roadmap.
- A defence of the choice that someone disagreeing with you could read and disagree on the *merits*, not on the writing.

Unacceptable answers:

- "ARQ is fast." — Both are fast.
- "Celery is overengineered." — It depends on the workload.
- "ARQ has a smaller community." — True, irrelevant.
- "Celery has the better docs." — Also true, also irrelevant to a one-task service.

## Acceptance criteria

- [ ] `arq_version/` is a working ARQ worker that runs the task.
- [ ] `celery_version/` is a working Celery worker that runs the same task.
- [ ] Both publish to the same `job-progress:<id>` Redis channel format, so the same FastAPI SSE endpoint could consume from either.
- [ ] `benchmark.py` runs and prints a comparison table.
- [ ] `COMPARISON.md` is ~1500 words, contains the five sections, cites the relevant URLs, and ends with a defence.
- [ ] All Python files `py_compile` clean.

## References

- **ARQ documentation**: <https://arq-docs.helpmanual.io/>
- **Celery user guide**: <https://docs.celeryq.dev/en/stable/userguide/>
- **Celery tasks**: <https://docs.celeryq.dev/en/stable/userguide/tasks.html>
- **Celery calling tasks**: <https://docs.celeryq.dev/en/stable/userguide/calling.html>
- **Celery workers**: <https://docs.celeryq.dev/en/stable/userguide/workers.html>
- **Celery configuration reference**: <https://docs.celeryq.dev/en/stable/userguide/configuration.html>
- **`celery beat`**: <https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html>
- **Flower** (Celery monitoring): <https://flower.readthedocs.io/>
- **RFC 9110 §15.3.3 (202 Accepted)**: <https://datatracker.ietf.org/doc/html/rfc9110#section-15.3.3>
