"""
Exercise 3 — ARQ: a task definition and a FastAPI enqueue endpoint.

Time:   ~2 hours.
Goal:   Define an ARQ worker with one task; build a FastAPI endpoint that
        enqueues the task and returns 202 Accepted with a job ID. Run the
        worker, watch the task progress, retrieve the result, and observe
        what happens when the task raises (the retry policy in action).

Run:
    # 1. Make sure Redis is reachable:
    redis-cli ping
    # PONG

    # 2. Start the ARQ worker:
    arq exercise-03-arq-task-and-enqueue.WorkerSettings

    # 3. In a second terminal, start the FastAPI app:
    fastapi dev exercise-03-arq-task-and-enqueue.py

    # 4. In a third terminal, enqueue a job:
    curl -X POST http://localhost:8000/jobs \
         -H "Content-Type: application/json" \
         -d '{"label": "morning-report", "delay_seconds": 3}'

    # 5. Watch the worker log the task start, the three publish events,
    #    and the completion.

Cited:
    - https://arq-docs.helpmanual.io/
    - https://arq-docs.helpmanual.io/#usage
    - https://docs.celeryq.dev/en/stable/userguide/tasks.html (for contrast)
    - https://datatracker.ietf.org/doc/html/rfc9110#section-15.3.3 (202 Accepted)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

# arq is an optional dependency for the runtime; the import is guarded so
# the file still py_compiles in environments where arq is not installed.
try:
    from arq import create_pool  # type: ignore[import-not-found]
    from arq.connections import ArqRedis, RedisSettings  # type: ignore[import-not-found]

    HAS_ARQ = True
except ImportError:  # pragma: no cover — exercised only when arq is absent
    create_pool = None  # type: ignore[assignment]
    ArqRedis = object  # type: ignore[assignment,misc]
    RedisSettings = None  # type: ignore[assignment,misc]
    HAS_ARQ = False


logger = logging.getLogger("arq_exercise")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


# ---------------------------------------------------------------------------
# Part A — The task
# ---------------------------------------------------------------------------
#
# An ARQ task is a top-level async function whose first argument is `ctx`.
# Anything after `ctx` is the user-provided arguments at enqueue time.


async def slow_report(
    ctx: dict[str, Any],
    label: str,
    delay_seconds: int = 5,
) -> dict[str, Any]:
    """A toy long-running task that publishes progress over Redis Pub/Sub.

    The publish channel is `job-progress:<job_id>`. The mini-project's SSE
    endpoint subscribes to this channel.
    """
    job_id = ctx["job_id"]
    job_try = ctx["job_try"]
    redis = ctx["redis"]  # ArqRedis is also a redis.asyncio.Redis client

    channel = f"job-progress:{job_id}"
    logger.info(
        "slow_report start; job_id=%s try=%d label=%r delay=%ds",
        job_id,
        job_try,
        label,
        delay_seconds,
    )

    total = max(1, delay_seconds)
    for step in range(1, total + 1):
        await redis.publish(
            channel,
            f'{{"step": {step}, "of": {total}, "label": "{label}"}}',
        )
        await asyncio.sleep(1.0)

    result = {
        "status": "ok",
        "job_id": job_id,
        "label": label,
        "steps": total,
    }
    await redis.publish(channel, '{"done": true}')
    logger.info("slow_report done; job_id=%s", job_id)
    return result


async def failing_task(ctx: dict[str, Any], when: int = 1) -> dict[str, Any]:
    """A task that raises on the first try, succeeds on the second.

    TASK 1: With max_tries=5 and the default backoff, how long after the
    first attempt does the second attempt run? Compute it from the ARQ
    docs and verify by watching the worker log. Note in SOLUTIONS.md.
    """
    job_try = ctx["job_try"]
    if job_try < when:
        raise RuntimeError(f"failing on try {job_try}")
    return {"status": "ok", "succeeded_on_try": job_try}


# ---------------------------------------------------------------------------
# Part B — The ARQ WorkerSettings
# ---------------------------------------------------------------------------


def _redis_settings() -> Any:
    """A small factory so the file compiles even without arq installed."""
    if not HAS_ARQ:
        return None
    return RedisSettings(host="localhost", port=6379, database=0)


class WorkerSettings:
    """The class ARQ inspects when you run `arq path.to.WorkerSettings`.

    Reference: https://arq-docs.helpmanual.io/#arq.worker.Worker
    """

    functions = [slow_report, failing_task]
    redis_settings = _redis_settings()
    max_jobs = 10  # how many tasks the worker runs in parallel
    job_timeout = 600  # seconds — kill a job that runs longer
    keep_result = 3600  # seconds — how long the result lives in Redis
    max_tries = 5  # retry count for failures


# ---------------------------------------------------------------------------
# Part C — The FastAPI app
# ---------------------------------------------------------------------------


class JobRequest(BaseModel):
    """The body accepted on POST /jobs."""

    label: str = Field(min_length=1, max_length=100, description="A human label.")
    delay_seconds: int = Field(
        default=5, ge=1, le=60, description="How long the task should run."
    )


class JobAccepted(BaseModel):
    """The 202 response body."""

    job_id: str
    stream_url: str
    poll_url: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open and close the ARQ pool for the FastAPI process's lifetime."""
    if HAS_ARQ:
        pool = await create_pool(_redis_settings())  # type: ignore[misc]
        app.state.arq = pool
        try:
            yield
        finally:
            await pool.aclose()
    else:
        # When arq is unavailable, run with a stub so the app still boots.
        app.state.arq = None
        yield


app = FastAPI(
    title="C16 W8 Exercise 3 — ARQ task and FastAPI enqueue",
    description=(
        "POST /jobs enqueues an ARQ task. GET /jobs/{id} returns the result "
        "if available. The 202 response includes a 'stream_url' that the "
        "mini-project's SSE endpoint will consume."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/jobs", status_code=status.HTTP_202_ACCEPTED, response_model=JobAccepted)
async def enqueue_job(body: JobRequest) -> JobAccepted:
    """Enqueue a slow_report job; return 202 with the job's stream URL.

    TASK 2: Compare the 202 Accepted shape to a 201 Created shape. Cite
    the RFC 9110 sections (15.3.2 vs 15.3.3) and explain in SOLUTIONS.md
    why 202 is the right code for a long-running enqueue.
    """
    if app.state.arq is None:
        raise HTTPException(
            status_code=503,
            detail="arq pool unavailable; install arq and ensure Redis is running",
        )

    job_id = str(uuid.uuid4())
    pool: Any = app.state.arq
    await pool.enqueue_job(
        "slow_report",
        body.label,
        body.delay_seconds,
        _job_id=job_id,
    )
    return JobAccepted(
        job_id=job_id,
        stream_url=f"/sse/jobs/{job_id}",
        poll_url=f"/jobs/{job_id}",
    )


@app.post("/jobs/failing", status_code=status.HTTP_202_ACCEPTED, response_model=JobAccepted)
async def enqueue_failing(succeed_on_try: int = 2) -> JobAccepted:
    """Enqueue a task that fails for the first N-1 tries, then succeeds.

    TASK 3: Run this with succeed_on_try=3. Watch the worker log show
    two failures and one success. Record the elapsed time between
    attempts and compare to the ARQ docs' documented backoff schedule.
    """
    if app.state.arq is None:
        raise HTTPException(status_code=503, detail="arq pool unavailable")

    job_id = str(uuid.uuid4())
    pool: Any = app.state.arq
    await pool.enqueue_job(
        "failing_task",
        succeed_on_try,
        _job_id=job_id,
    )
    return JobAccepted(
        job_id=job_id,
        stream_url=f"/sse/jobs/{job_id}",
        poll_url=f"/jobs/{job_id}",
    )


@app.get("/jobs/{job_id}")
async def get_job_result(job_id: str) -> dict[str, Any]:
    """Return the persisted result for a finished job, or a 'pending' status.

    TASK 4: Why does ARQ keep results in Redis with a TTL (keep_result on
    WorkerSettings) rather than persisting them forever? What is the trade-off?
    """
    if app.state.arq is None:
        raise HTTPException(status_code=503, detail="arq pool unavailable")

    pool: Any = app.state.arq
    info = await pool.get_job_result(job_id, poll_delay=0.1, timeout=0.5)
    if info is None:
        return {"job_id": job_id, "status": "pending"}
    return {"job_id": job_id, "status": "done", "result": info}


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {"status": "ok", "arq_available": HAS_ARQ}


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------
#
# Run `python3 -m py_compile exercise-03-arq-task-and-enqueue.py`. It must
# succeed silently, with or without arq installed.
#
# TASK 5: Read arq/worker.py from
# https://github.com/python-arq/arq/blob/main/arq/worker.py. Find the
# `async_run` method on Worker. In SOLUTIONS.md, quote the line where the
# worker pops a job off the queue and the line where it calls the user
# function. The body of those two lines is the entire ARQ runtime in two
# sentences.
