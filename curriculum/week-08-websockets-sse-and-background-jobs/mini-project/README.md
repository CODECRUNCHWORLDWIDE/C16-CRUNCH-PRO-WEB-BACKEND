# Mini-Project — `crunchexports`: FastAPI + ARQ + SSE

> Build a standalone FastAPI service that accepts a CSV-export request, hands the work to an ARQ worker, and streams progress to the browser over Server-Sent Events. The integration is the point: three processes (FastAPI, ARQ worker, Redis) co-operating across two channels (HTTP for the request, Redis Pub/Sub for the progress) to deliver one user-facing primitive — "click a button, watch the progress bar, download the file when it is done".

**Estimated time:** 7 hours, spread Thursday–Saturday. The Friday-on hours are filled by writing tests and tightening the schemas; the Saturday hours go to the operational documentation.

## Why this and not something larger

`crunchexports` is deliberately small. Its job is to make the three new primitives from this week — WebSocket (not used in this project, but exercised in the challenges), SSE, and ARQ — concrete in working code. A larger project would dilute the focus. By the end of Saturday you have one app that, in 1 200-or-so lines of Python, demonstrates the architecture that powers every "long-running export with a progress bar" feature in every SaaS product you have used in the last five years.

This project does not depend on the Week 7 `crunchreader-api` service. It runs standalone. The two can be merged in a later week if you wish, but for grading purposes they are independent.

## What you build

A FastAPI service named `crunchexports` with:

1. **Four HTTP routes:**
   - `POST /exports` — accept a Pydantic-validated body describing what to export; enqueue an ARQ job; return `202 Accepted` with the job ID, the SSE stream URL, and a `Location:` header pointing at the poll URL.
   - `GET /exports/{job_id}` — return the job's current status: `pending`, `running`, `done`, or `failed`. Persist the final result, so a client that polls *after* the SSE stream closed still sees the answer.
   - `GET /exports/{job_id}/download` — serve the rendered CSV file, once the job is done. 404 until it is. 410 (Gone) once the file is older than the configured retention.
   - `GET /health` — process-level health probe; returns `200` if FastAPI is up, the Redis ping succeeds, and the ARQ pool is reachable.

2. **One SSE endpoint:**
   - `GET /sse/exports/{job_id}` — subscribe to the per-job Redis Pub/Sub channel; relay every `progress` and `done` event to the open response. Heartbeat every 15 seconds. Resume from `Last-Event-ID` if the client reconnects.

3. **One ARQ worker:**
   - The task `run_export(ctx, job_id, export_request)` takes the request, opens an output file, iterates the data source (a stubbed in-memory list for the mini-project; a Postgres query in production), writes rows in chunks, publishes one `progress` event per chunk to `job-progress:<job_id>`, finishes by publishing a `done` event and writing the file's metadata to a Redis-stored result.

4. **Pydantic v2 schemas:**
   - `ExportRequest` — the body of `POST /exports`. Required fields: `kind: Literal["users", "orders", "events"]`, `from_date: date`, `to_date: date`. Optional: `format: Literal["csv", "tsv"] = "csv"`, `delimiter: str = ","`, `include_headers: bool = True`.
   - `ExportAccepted` — the 202 response. Fields: `job_id`, `stream_url`, `poll_url`.
   - `ExportStatus` — the `GET /exports/{job_id}` response. Fields: `job_id`, `status`, `progress: float`, `created_at`, `finished_at: datetime | None`, `download_url: str | None`, `error: str | None`.

5. **A short HTML page** (`static/index.html`) demonstrating the end-to-end flow:
   - A form that submits a `POST /exports`.
   - Five lines of JavaScript opening an `EventSource` and updating a progress bar.
   - A "download" link that appears when the `done` event arrives.

6. **An integration test suite:**
   - `tests/test_routes.py` — happy path, 422 on invalid body, 404 on unknown job.
   - `tests/test_sse.py` — `httpx.AsyncClient.stream` test that verifies the framing.
   - `tests/test_worker.py` — `arq.worker.Worker.run_check` runs the task in-process; asserts on the result and on the published progress events.

7. **An operational README** explaining how to run the three processes, what each one logs, and how to observe the system at runtime.

## Repository layout

```text
crunchexports/
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
├── crunchexports/
│   ├── __init__.py
│   ├── main.py                 (FastAPI app, lifespan, route wiring)
│   ├── settings.py             (Pydantic Settings: Redis URL, export dir, retention)
│   ├── schemas.py              (Pydantic v2 models)
│   ├── deps.py                 (ARQ pool dependency, settings dependency)
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── exports.py          (POST /exports, GET /exports/{id})
│   │   ├── downloads.py        (GET /exports/{id}/download)
│   │   └── sse.py              (GET /sse/exports/{id})
│   ├── worker.py               (ARQ task + WorkerSettings)
│   ├── data_sources.py         (the stubbed "get rows for kind/date-range" iterator)
│   └── progress.py             (the Redis Pub/Sub helper used by both task and SSE)
├── static/
│   └── index.html              (the demo page)
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_routes.py
    ├── test_sse.py
    └── test_worker.py
```

Total: 16 files (matching the quality bar in C1 W1 and C16 W7).

## Stack

- Python 3.12+
- FastAPI 0.115.x with the `[standard]` extra
- Pydantic 2.9.x + `pydantic-settings` 2.5.x
- ARQ 0.26.x
- `redis[hiredis]` 5.0.x
- `sse-starlette` 2.1.x
- Pytest 8.x + pytest-asyncio 0.24.x + httpx 0.27.x

Setup:

```bash
mkdir crunchexports && cd crunchexports
python3 -m venv .venv && source .venv/bin/activate
pip install 'fastapi[standard]==0.115.*' 'pydantic==2.9.*' 'pydantic-settings==2.5.*' \
            'arq==0.26.*' 'redis[hiredis]==5.0.*' 'sse-starlette==2.1.*' \
            'pytest==8.3.*' 'pytest-asyncio==0.24.*' 'httpx==0.27.*'
pip freeze > requirements.txt
```

## Acceptance criteria

### Schemas

- [ ] `schemas.py` declares `ExportRequest`, `ExportAccepted`, `ExportStatus` with the field shape above.
- [ ] `ExportRequest` rejects `from_date > to_date` via a `@model_validator(mode="after")`.
- [ ] `ExportRequest` rejects ranges wider than 365 days. The validator's message names the offending field span explicitly.
- [ ] `ExportRequest.model_config = ConfigDict(extra="forbid")`. Unknown fields return 422.

### Routes

- [ ] `POST /exports` returns `202 Accepted` with body `ExportAccepted` and a `Location: /exports/{job_id}` header (RFC 9110 §15.3.3).
- [ ] The enqueue uses `await pool.enqueue_job("run_export", job_id, request.model_dump(mode="json"), _job_id=job_id)`. The ARQ job ID and the application job ID are the same string.
- [ ] `GET /exports/{job_id}` returns the persisted status. While the job is running, the response includes a `progress` field (0.0 to 1.0). Once done, it includes a `download_url`.
- [ ] `GET /exports/{job_id}/download` serves the file with `Content-Type: text/csv` (or `text/tab-separated-values` for TSV); on miss, 404; on too-old, 410 Gone.
- [ ] `GET /health` returns `{"status": "ok"}` when all upstreams are reachable.

### SSE endpoint

- [ ] `GET /sse/exports/{job_id}` returns a `text/event-stream` response.
- [ ] The response contains `Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no` headers.
- [ ] Events have `event:`, `id:`, and `data:` fields. `id:` is the sequence number (monotonic per job).
- [ ] On reconnect with `Last-Event-ID`, the endpoint resumes from the next event the client has not seen. (For the mini-project, resume can be best-effort — we do not require a durable event log.)
- [ ] A `: heartbeat` comment is emitted every 15 seconds.
- [ ] The endpoint detects client disconnect via `await request.is_disconnected()` and cleans up the Redis subscription.

### Worker

- [ ] `worker.py` defines `WorkerSettings` with `functions = [run_export]`, `max_jobs = 5`, `keep_result = 3600`, `max_tries = 3`.
- [ ] `run_export(ctx, job_id, request_dict)` validates the dict back into an `ExportRequest`, opens an output file at `settings.export_dir / f"{job_id}.csv"`, writes rows in 100-row chunks, publishes one `progress` event per chunk.
- [ ] The progress events are JSON: `{"step": int, "of": int, "label": str}`. The done event is `{"done": true, "rows": int, "file": str}`.
- [ ] The task is idempotent: a second invocation with the same `job_id` (a retry) recognises the existing in-progress lock and returns `{"status": "skipped", "reason": "duplicate"}` rather than re-writing the file.
- [ ] On failure, the task publishes `{"error": str, "step": int}` before re-raising; the SSE endpoint relays this as a `failed` event.

### Tests

- [ ] `test_routes.py` exercises the happy path (202, then a poll that returns `pending` while the job runs).
- [ ] `test_routes.py` exercises 422 on `from_date > to_date`, 422 on `extra="forbid"` violation, 404 on unknown `job_id`.
- [ ] `test_sse.py` uses `httpx.AsyncClient.stream("GET", "/sse/exports/{id}")` with a fakeredis fixture providing the progress channel. Asserts at least three `progress` events and one `done` event arrive.
- [ ] `test_worker.py` uses `arq.worker.Worker.run_check` to run the task in-process; asserts on the returned dict and on the number of `redis.publish` calls observed.

### Operational documentation

- [ ] `README.md` opens with "How to run" — three terminals (FastAPI, ARQ worker, Redis) and the curl that POSTs an export.
- [ ] The README has a "What each process logs" section: one bulleted line per process explaining the key log line you watch for during a successful run.
- [ ] The README has a section "Failure modes" listing at least three: Redis down, ARQ worker crashed, export disk full. For each, name the symptom (HTTP status, log line) and the recovery.
- [ ] The README closes with a "Why ARQ and not Celery" paragraph — a shortened version of Challenge 2's `COMPARISON.md`.

## Architecture diagram (textual)

```text
+----------+   POST /exports        +---------+   enqueue_job          +-------+
|  Client  | ---------------------> | FastAPI | ---------------------> | Redis |
| (browser)|                        | process |                         | queue |
|          | <--- 202 + stream_url --|         |                         +-------+
|          |                        |         |                              |
|          |   GET /sse/exports/id  |         |                              | BLPOP
|          | ---------------------> |         |                              v
|          |                        |         |                         +---------+
|          | <-- text/event-stream--| Pub/Sub |   PUBLISH progress      |   ARQ   |
|          |                        |  relay  | <---------------------- | worker  |
|          |                        +---------+                         +---------+
|          |
|          |   GET /exports/id/download
|          | -------------------------------------------------------> [filesystem]
|          | <------ text/csv ---------------------------------------|
+----------+
```

Three processes; two Redis-mediated channels (the job queue and the Pub/Sub progress channel); the file system for the durable export artefact; HTTP/SSE between FastAPI and the client.

## Step-by-step build

### Day 1 — Thursday (~2 hours)

- Scaffold the repository layout above. `__init__.py` files, empty modules.
- Write `settings.py` with `pydantic-settings`-based config (Redis URL, export dir, retention seconds).
- Write `schemas.py`. Verify all three schemas via `python3 -c "from crunchexports.schemas import ExportRequest; ExportRequest.model_validate_json('{\"kind\": \"users\", \"from_date\": \"2026-01-01\", \"to_date\": \"2026-01-31\"}')"`.
- Write `progress.py`: a thin helper around `redis.asyncio` for the publish channel naming and the subscribe-loop helper.

### Day 2 — Friday (~2 hours)

- Write `worker.py`. Implement `run_export` with the chunked write, the progress publish, and the idempotency lock.
- Run the worker against an empty Redis and verify the `arq` CLI starts cleanly.
- Write `routers/exports.py`. Implement `POST /exports` and `GET /exports/{id}`. Use `app.state.arq` for the pool.
- Implement `routers/downloads.py`. Use `FileResponse` from Starlette.

### Day 3 — Saturday (~3 hours)

- Write `routers/sse.py`. Use `sse-starlette.EventSourceResponse`. Implement the subscribe loop with disconnect detection and `Last-Event-ID` handling.
- Write `static/index.html`. Keep it minimal — one form, one progress bar, one download link.
- Write the three test files. Use `fakeredis` for the Pub/Sub fixture so tests do not require a running Redis.
- Write the README. Run through the "how to run" section yourself, in a clean terminal, and fix any step that does not match what you typed.

## Stretch goals

- [ ] **Cancellable jobs.** Add `DELETE /exports/{job_id}`; the worker checks a cancellation key in Redis between chunks and exits gracefully if set. The SSE stream receives a `cancelled` event.
- [ ] **Multi-tenant.** Add an authenticated user context (re-use the Week 7 token dependency). Each user can only see their own jobs; the `download` endpoint enforces ownership.
- [ ] **Replace fakeredis in tests with a real Redis spun up via `pytest-docker` or `testcontainers`.** Document the trade-offs (test speed vs fidelity to production).
- [ ] **Replace the file storage with S3** (use `minio` locally). The download URL becomes a pre-signed S3 URL. The retention policy moves to the S3 lifecycle rules.
- [ ] **Add Prometheus metrics.** Expose `/metrics` with counters for jobs enqueued, jobs completed, jobs failed, and a histogram of job duration. Use `prometheus-fastapi-instrumentator`.

## Rubric (50 points)

| Area                                | Points | Pass bar                                                                  |
|-------------------------------------|-------:|---------------------------------------------------------------------------|
| Schemas + validators                | 6      | All three schemas; `extra="forbid"`; `from_date <= to_date` check         |
| `POST /exports` and `202` response  | 5      | Correct status code, `Location:` header, body matches `ExportAccepted`    |
| `GET /exports/{id}` poll            | 4      | Returns the four statuses with progress and download URL                  |
| `GET /exports/{id}/download`        | 4      | Correct content type; 404 on miss; 410 on too-old                         |
| SSE endpoint framing                | 6      | Correct content type; headers; heartbeats; disconnect handling             |
| SSE `Last-Event-ID` resume          | 3      | Reconnect from a later event ID skips earlier ones                        |
| ARQ task implementation             | 5      | Chunked write; progress publish; correct done event                       |
| ARQ task idempotency                | 4      | Retry of the same `job_id` is a no-op, lock + TTL                         |
| Tests (routes + SSE + worker)       | 6      | Three test files; all pass; cover happy path + 3 failure modes            |
| README operational sections         | 5      | "How to run", "What logs to watch", "Failure modes", "Why ARQ not Celery" |
| Code quality (types, ruff-clean)    | 2      | Every function has type hints; `ruff check` passes                        |

Late submissions: 10% per day, capped at 50%. Code that does not `py_compile` is graded as if the file did not exist; fix and resubmit.

## References

- **FastAPI**:
  - <https://fastapi.tiangolo.com/>
  - <https://fastapi.tiangolo.com/tutorial/background-tasks/>
- **Starlette `StreamingResponse`**: <https://www.starlette.io/responses/#streamingresponse>
- **`sse-starlette`**: <https://github.com/sysid/sse-starlette>
- **ARQ documentation**: <https://arq-docs.helpmanual.io/>
- **MDN `EventSource`**: <https://developer.mozilla.org/en-US/docs/Web/API/EventSource>
- **HTML living standard SSE section**: <https://html.spec.whatwg.org/multipage/server-sent-events.html>
- **RFC 9110 §15.3.3 (202 Accepted)**: <https://datatracker.ietf.org/doc/html/rfc9110#section-15.3.3>
- **`pydantic-settings`**: <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>
- **`fakeredis`**: <https://github.com/cunla/fakeredis-py>

## Starter files

The `starter/` directory ships skeletons for the key modules. Each is `py_compile`-clean but contains `TODO` markers where you implement the load-bearing logic. The starter is *not* a finished implementation — fewer than 300 lines total, all the wiring is in place, but every interesting function body raises `NotImplementedError` until you fill it in.

```text
starter/
├── schemas.py        (the three Pydantic models, with the validators stubbed)
├── settings.py       (the pydantic-settings config)
├── worker.py         (the ARQ WorkerSettings and the task signature)
├── main.py           (the FastAPI app with lifespan and router wiring)
├── routers_sse.py    (the SSE endpoint skeleton)
└── progress.py       (the Redis Pub/Sub helper)
```

Copy these into your `crunchexports/` package as you start each day.
