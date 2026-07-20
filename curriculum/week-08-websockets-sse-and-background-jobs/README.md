# Week 8 — WebSockets, Server-Sent Events, and Background Jobs

> *Week 7 gave us a FastAPI service that can list, retrieve, create, and validate. It speaks JSON, it generates an OpenAPI document, it returns a response and closes the connection. That last clause is the limit. Every interaction in Week 7 ends with the server hanging up. Week 8 is the week the server stops hanging up. We add three capabilities that the request/response shape cannot express: server-initiated push (Server-Sent Events), bidirectional streaming (WebSocket), and out-of-band work that outlives the request (background jobs). Each is a different answer to the same problem — "this work is longer than one HTTP round-trip" — and each has a defensible niche. The week's discipline is choosing between them on the merits, not on novelty.*

Welcome to Week 8 of **C16 · Crunch Pro Web Backend**. The `crunchreader-api` service from Week 7 keeps its routes and its OpenAPI document. This week it grows three new surfaces:

1. A **WebSocket endpoint** at `/ws/articles` that pushes article-published events to connected editors in real time, with a Redis Pub/Sub broadcaster behind it so multiple FastAPI workers can publish without losing subscribers on the other workers.
2. A **Server-Sent Events endpoint** at `/sse/jobs/{job_id}` that streams progress for a long-running task. The client does nothing but `new EventSource(url)`; the browser handles reconnection.
3. A **background job runner** powered by **ARQ** — a Redis-backed, async-native job queue — that does the actual work behind those SSE streams, so the FastAPI process stays free to serve requests.

We approach each surface the way Week 7 approached FastAPI: read the spec first, write the framework call second. WebSocket is **RFC 6455**, finalised 2011 — short, readable, and the foundation of every WS library in every language. SSE is the HTML5 living standard's [Server-Sent Events section](https://html.spec.whatwg.org/multipage/server-sent-events.html), plus the developer-facing [MDN reference](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events). The job-runner conversation is older than HTTP: it is the message-queue conversation, and Celery, RQ, and ARQ are three Python answers to it. We pick **ARQ** as the headline this week because it is async-native (it lives in the same event loop as FastAPI) and minimal (one Redis dependency, one decorator). We compare it explicitly to Celery, the incumbent, so you know when you would reach for the older, heavier, broker-pluggable framework instead.

By Sunday you will have:

1. A WebSocket endpoint accepting connections, authenticating them, broadcasting to all subscribers via Redis Pub/Sub, and shutting down cleanly on client disconnect.
2. An SSE endpoint emitting `data:` frames over `text/event-stream`, surviving a Cloudflare/Nginx proxy without buffering, and being consumed by a five-line browser client.
3. An ARQ worker pool consuming a `report_export` job: it does the work, publishes progress to a Redis channel, and the FastAPI process reads that channel to relay frames over SSE to the user.
4. A test suite that exercises all three: `httpx.AsyncClient` for SSE (a streaming GET); FastAPI's `TestClient.websocket_connect` for WS; an in-process ARQ runner for jobs.
5. A defensible answer, in writing, to the question: "Why did you pick ARQ over Celery for this service?"

The async story we parked in Week 7 — what `await` actually does inside a route — pays its bill this week. WebSocket handlers spend most of their lives in `await ws.receive_text()`; SSE handlers spend most of their lives in `async for message in pubsub.listen()`. Neither is conceivable on WSGI. If Week 7 was the *interface* week, Week 8 is the *workload* week.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** the WebSocket handshake at the byte level. Reproduce the opening request and response. State which two HTTP headers (`Upgrade: websocket`, `Connection: Upgrade`) trigger the protocol switch and what the server does with `Sec-WebSocket-Key`. Cite **RFC 6455 §1.3** for the opening handshake and **§5** for the framing.
- **Build** a FastAPI WebSocket endpoint with `@app.websocket("/ws/...")`, accept the connection (`await ws.accept()`), exchange messages (`ws.receive_text` / `ws.send_text` / `ws.receive_json` / `ws.send_json`), and handle disconnects (`WebSocketDisconnect`). Cite the [FastAPI WebSockets tutorial](https://fastapi.tiangolo.com/advanced/websockets/).
- **Distinguish** the four close codes you will actually use: `1000` normal closure, `1001` going away, `1008` policy violation (use this for auth failure), `1011` internal error. Cite **RFC 6455 §7.4**.
- **Implement** a connection manager — a process-local registry of accepted WebSockets — and graduate it to a Redis Pub/Sub broadcaster so messages reach subscribers on *any* worker, not just the local one. Cite the [Starlette `WebSocket` docs](https://www.starlette.io/websockets/).
- **Choose** Server-Sent Events over WebSocket when the traffic is one-way (server-to-client), the message rate is moderate, and proxy/firewall compatibility matters. State the four SSE advantages: (a) it is plain HTTP, so every proxy understands it; (b) auto-reconnect with `Last-Event-ID` is built into the browser's `EventSource`; (c) no framing protocol — just text — so debuggability is `curl --no-buffer`; (d) the client API is five lines.
- **Build** an SSE endpoint that returns a `StreamingResponse` with `media_type="text/event-stream"`, emits framed events (`event: ...`, `data: ...`, `id: ...`, blank line), heartbeats every ~15 seconds with a comment line, and respects the client's `Last-Event-ID` header on reconnect. Cite the [MDN `EventSource` reference](https://developer.mozilla.org/en-US/docs/Web/API/EventSource) and the [HTML living standard SSE section](https://html.spec.whatwg.org/multipage/server-sent-events.html).
- **Choose** among the three Python job runners with reasons you can defend: **ARQ** for new async-native FastAPI services on Redis; **RQ** for sync, classic, Redis-only stacks (Django, Flask) where simplicity matters more than concurrency; **Celery** for multi-broker (RabbitMQ, Redis, SQS), heterogeneous fleets, scheduled tasks (`celery beat`), and the cases where you need its acknowledgement model, routing keys, and ecosystem of monitoring tools (Flower, etc.).
- **Implement** an ARQ worker: define a settings class (`WorkerSettings`), declare async task functions (`async def report_export(ctx, ...) -> dict`), enqueue from FastAPI (`await pool.enqueue_job("report_export", ...)`), and have the task publish progress to a Redis Pub/Sub channel that the SSE endpoint relays. Cite the [ARQ documentation](https://arq-docs.helpmanual.io/).
- **Run** the integration: a `POST /reports` accepts a request, enqueues an ARQ job, returns `202 Accepted` with a `job_id` and a `Location: /sse/jobs/{job_id}` header per RFC 9110 §15.3.3, the browser opens an `EventSource` to that URL, the worker streams progress events into Redis, and the FastAPI process forwards them to the browser. The whole pipeline runs across three processes — FastAPI, ARQ worker, Redis — and survives a worker restart with the job re-queued.
- **Test** all three surfaces: `TestClient.websocket_connect` for the WS endpoint; `httpx.AsyncClient.stream("GET", url)` for the SSE endpoint; `arq.worker.Worker.run_check` for a one-shot, in-process ARQ run that lets you assert against the task's return value.
- **Defend** the trade-off in code review: "We picked ARQ over Celery because the service is small, async-native, and Redis-only. If the operator profile changes — broker pluralism, scheduled tasks, dead-letter queues — Celery's surface area is justified. Until then, ARQ's ~1 500 lines of source are something we can read."

## Prerequisites

- **C16 Week 7** — you have a running FastAPI service with Pydantic v2 schemas, a dependency-injected database session, and an integration test suite over `httpx.AsyncClient`. This week extends that service; it does not replace it.
- **Redis available locally.** Install via `brew install redis` (macOS), `apt install redis-server` (Debian/Ubuntu), or run `docker run -p 6379:6379 redis:7-alpine`. Verify with `redis-cli ping` → `PONG`.
- **`asyncio` literacy.** You know what `async def` declares, what `await` does, and the difference between `await coro` and `asyncio.create_task(coro)`. If those are foggy, re-read the Python docs' [Coroutines and Tasks](https://docs.python.org/3/library/asyncio-task.html) page first.
- **Browser DevTools open to the Network tab.** WebSocket frames and SSE streams are both inspectable. The week's quickest debugging tool is the WS pane (`Network → WS → Messages`) and the EventStream pane on a `text/event-stream` response.
- **`curl` 7.85+** — recent enough to support `--no-buffer` reliably for SSE testing, and `curl -i --include` for WebSocket handshake inspection.

## Topics covered

- WebSocket as a TCP-layer upgrade from HTTP/1.1: the `Upgrade: websocket`, `Connection: Upgrade`, `Sec-WebSocket-Key`, `Sec-WebSocket-Version: 13` request headers; the `101 Switching Protocols` response with `Sec-WebSocket-Accept`
- RFC 6455 framing: opcode, payload length, masking; why client-to-server frames are always masked and server-to-client frames are never masked
- The close-code namespace: 1000-2999 reserved, 3000-3999 application, 4000-4999 private
- FastAPI WebSocket handlers: `@app.websocket("/ws")`, `ws.accept(subprotocol=...)`, `ws.receive_text()`, `ws.send_json()`, `WebSocketDisconnect`
- Authentication on WebSocket: subprotocol header, query token, cookie — the trade-offs of each
- The connection-manager pattern (process-local) and its limit (one worker only)
- The broadcast pattern with Redis Pub/Sub: every worker subscribes to a channel; publish on one worker, receive on all
- The `broadcaster` library as an existing implementation of the same pattern (read its ~400 lines)
- Backpressure on a slow WebSocket consumer: bounded send queue, drop policy, disconnect-on-overflow
- Heartbeats and idle timeouts: why `ws.send_text` does not detect a half-open TCP connection; why TCP keepalive is not enough
- Server-Sent Events: the `text/event-stream` content type, the four event fields (`event`, `data`, `id`, `retry`), the framing rule (one blank line separates events)
- `EventSource` on the browser: the four readyState values, the `error` event, the automatic reconnect with `Last-Event-ID`
- Why SSE beats WebSocket for one-way streams: proxy compatibility, simplicity, debuggability, no separate protocol upgrade
- Why WebSocket beats SSE for bidirectional traffic: half the connection count, lower latency, binary frames if needed
- Background-job theory: the four-part anatomy (broker, worker, result backend, scheduler) and which jobs *belong* on a queue
- ARQ: async-native, Redis-only, ~1 500 lines of source; `WorkerSettings`, `arq.connections.create_pool`, `await pool.enqueue_job(...)`
- ARQ's task lifecycle: enqueued → in-progress → completed/failed; retries with backoff (`max_tries`, `job_try`)
- Job progress reporting: the task publishes to a Redis channel; the SSE endpoint subscribes; messages relay to the browser
- Celery: when its surface area is justified (multi-broker, scheduled tasks, Flower monitoring, mature ecosystem)
- RQ: when its sync simplicity wins (small Flask/Django services where the worker is one `rq worker` command and the queue is one `q.enqueue(fn, ...)` call)
- The "FastAPI BackgroundTasks" trap: it runs *in the request worker*, not on a separate process; fine for "fire-and-forget audit log write", wrong for "60-second PDF render"
- Idempotency for retried jobs: job IDs, the dedupe key in Redis, the "exactly once *side-effect*" myth and what "at-least-once with idempotency" actually means in practice
- Testing patterns: `TestClient.websocket_connect`, `httpx.AsyncClient.stream`, `arq.worker.Worker.run_check`
- 202 Accepted with `Location:` per RFC 9110 §15.3.3 — the canonical contract for "I started the work, poll here"

## Weekly schedule

The schedule below totals approximately **35 hours**. The lecture density is similar to Week 7 because the three topics (WebSocket, SSE, jobs) are independent and each deserves an hour or so on its own.

| Day       | Focus                                                                              | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|------------------------------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | WebSocket: RFC 6455, FastAPI handlers, the connection manager                       | 2h       | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6h          |
| Tuesday   | Server-Sent Events: the spec, `EventSource`, the streaming response                | 2h       | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6h          |
| Wednesday | Background jobs: theory, ARQ, Celery, RQ — pick the right one                       | 2h       | 2h        | 1h         | 0.5h      | 1h       | 0h           | 0.5h       | 7h          |
| Thursday  | Wire SSE + ARQ: a FastAPI app that streams job progress to the browser              | 0h       | 0.5h      | 1h         | 0.5h      | 1h       | 2h           | 0.5h       | 5.5h        |
| Friday    | The Redis Pub/Sub broadcast: WS across multiple workers                            | 0h       | 0h        | 1h         | 0.5h      | 1h       | 2h           | 0h         | 4.5h        |
| Saturday  | Tests, docs, the README explaining the architecture                                 | 0h       | 0h        | 0h         | 0h        | 1h       | 3h           | 0h         | 4h          |
| Sunday    | Quiz, reflection, write the "why ARQ over Celery" defence                          | 0h       | 0h        | 0h         | 0.5h      | 0h       | 0h           | 0h         | 0.5h        |
| **Total** |                                                                                    | **6h**   | **6.5h**  | **3h**     | **3h**    | **6h**   | **7h**       | **2h**     | **33.5h**   |

The week's pacing puts the three primitives on three consecutive days — WebSocket, SSE, jobs — then integrates them Thursday onward. The mini-project is the integration: a small FastAPI service that exports a CSV report, runs the export on ARQ, and streams progress to the browser over SSE.

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview |
| [resources.md](./resources.md) | FastAPI WebSocket docs, MDN SSE, RFC 6455, ARQ docs, Celery docs, RQ docs, the references worth bookmarking |
| [lecture-notes/01-websockets-the-protocol-and-the-handler.md](./lecture-notes/01-websockets-the-protocol-and-the-handler.md) | RFC 6455, the handshake, the framing, FastAPI's `@app.websocket`, the connection manager |
| [lecture-notes/02-server-sent-events-and-when-to-pick-them.md](./lecture-notes/02-server-sent-events-and-when-to-pick-them.md) | The SSE spec, `EventSource`, the `StreamingResponse`, the WS-vs-SSE choice |
| [lecture-notes/03-background-jobs-arq-celery-rq.md](./lecture-notes/03-background-jobs-arq-celery-rq.md) | The job-runner anatomy, ARQ in depth, when Celery, when RQ |
| [exercises/exercise-01-websocket-echo-and-manager.py](./exercises/exercise-01-websocket-echo-and-manager.py) | A minimal WebSocket echo, then a fan-out broadcast via a connection manager |
| [exercises/exercise-02-sse-counter-stream.py](./exercises/exercise-02-sse-counter-stream.py) | An SSE endpoint that emits a counter once per second; client `EventSource` parses it |
| [exercises/exercise-03-arq-task-and-enqueue.py](./exercises/exercise-03-arq-task-and-enqueue.py) | An ARQ worker definition; a FastAPI route that enqueues a job and returns 202 |
| [exercises/SOLUTIONS.md](./exercises/SOLUTIONS.md) | Worked solutions, with explanation of the trickier lines |
| [challenges/challenge-01-redis-pubsub-broadcast.md](./challenges/challenge-01-redis-pubsub-broadcast.md) | Graduate the connection manager to a Redis Pub/Sub broadcaster that works across workers |
| [challenges/challenge-02-celery-vs-arq-on-a-real-task.md](./challenges/challenge-02-celery-vs-arq-on-a-real-task.md) | Re-implement the same task in Celery; compare lines of code, latency, ergonomics |
| [quiz.md](./quiz.md) | 10 multiple-choice questions |
| [homework.md](./homework.md) | Six problems (~6h) |
| [mini-project/README.md](./mini-project/README.md) | Build `crunchexports` — a FastAPI app that exports CSV reports via ARQ and streams progress over SSE |
| [mini-project/starter/](./mini-project/starter/) | Starter files: app skeleton, worker stub, settings, tests |

## Before Monday — verify the environment

Six checks. If any fails, fix it before opening Lecture 1.

```bash
# 1. Python 3.12+
python3 --version
# Python 3.12.x or 3.13.x

# 2. Redis is reachable
redis-cli ping
# PONG

# 3. Week 7's crunchreader-api still runs
cd crunchreader-api && fastapi dev books_api/main.py
# Open http://localhost:8000/docs ; Ctrl+C to stop

# 4. Install this week's dependencies (in the same venv)
pip install 'arq==0.26.*' 'redis[hiredis]==5.0.*' 'websockets==13.1.*' 'sse-starlette==2.1.*'

# 5. Confirm websockets can connect
python3 -c "import websockets; print(websockets.__version__)"
# 13.1.x

# 6. Confirm arq is importable and has the CLI
arq --help
# Usage: arq [OPTIONS] WORKER_SETTINGS
```

If `pip install 'arq==0.26.*'` complains about the `redis` extra, install `redis` separately first (`pip install 'redis[hiredis]==5.0.*'`) — ARQ depends on `redis-py` 5+ since version 0.25.

## The habit to install this week

Four practices, applied to every long-lived endpoint and every background task you write from here on:

1. **Pick the simplest primitive that fits.** SSE before WebSocket for one-way streams; HTTP polling before SSE for sub-minute, infrequent updates; FastAPI's `BackgroundTasks` before ARQ for in-process, fire-and-forget work under 100 ms; ARQ before Celery unless an explicit Celery feature (scheduling, multi-broker, Flower) is on the requirements list. The pattern is "default to less; escalate to more only when the smaller answer is demonstrably wrong".
2. **Acknowledge before you work.** A `POST /reports` that takes 60 seconds is a bug. The correct pattern is: enqueue the job, return `202 Accepted` with a `Location: /sse/jobs/{id}` header, let the client poll or stream the progress. The request handler is the cashier, not the kitchen.
3. **Idempotency by design.** Every background task must accept the same input twice and produce the same outcome. The job runner *will* retry — at-least-once is what the protocol guarantees; exactly-once is what your code guarantees. The cheap way is a dedupe key in Redis with an expiry equal to the longest plausible run time.
4. **Heartbeats on every long-lived connection.** WebSocket: ping/pong every 30 seconds; SSE: an `: comment` line every 15 seconds. Without one, a Cloudflare proxy will close your connection at 100 seconds idle and the client will see "connection closed for no reason".

The first practice prevents over-engineering. The second prevents request-handler starvation. The third prevents data loss on retry. The fourth prevents the silent disconnect that takes a week to diagnose. Together they replace most of the operational pain that real-time and async backends accumulate.

## Stretch goals

- Read **RFC 6455** end-to-end (~90 minutes). It is short, well-written, and the source of every WebSocket library's behaviour. Sections 1, 4, 5, and 7 are the load-bearing ones: <https://datatracker.ietf.org/doc/html/rfc6455>.
- Read the **HTML living standard SSE section** (~30 minutes): <https://html.spec.whatwg.org/multipage/server-sent-events.html>. The browser side of SSE is half a page; the server side is half a page; the example is half a page.
- Read the **ARQ source** (`arq/worker.py`, ~700 lines). Find `Worker.async_run`. Trace one job from `await pool.enqueue_job(...)` through to `result_save`. ARQ is small enough to read in a sitting: <https://github.com/python-arq/arq>.
- Read the **Celery user guide on tasks** (~45 minutes), specifically the sections on retries, acks-late, and idempotency: <https://docs.celeryq.dev/en/stable/userguide/tasks.html>. You do not need to write Celery this week to need to know what the alternative offers.
- Skim the [`broadcaster` library](https://github.com/encode/broadcaster) source (~400 lines). It is the same Redis Pub/Sub pattern we build in Challenge 1, written by the Starlette author. Read it after you have written your own.

## Up next

[Week 9 — Authentication, JWT, OAuth2, and session security](../week-09-auth-jwt-oauth2-and-session-security/) — we have been waving a `Bearer ...` token at the auth dependency since Week 7. Week 9 issues the tokens properly: password hashing, JWT structure, RS256 vs HS256, refresh tokens, OAuth2 authorisation code flow, CSRF, session fixation, and the audit-log entries you owe yourself.
