# Week 8 — Resources

All free and publicly accessible. FastAPI 0.115.x, Starlette 0.40.x, Pydantic 2.9.x, ARQ 0.26.x, Celery 5.4.x, RQ 1.16.x, Redis 7.x, Python 3.12+. Pin docs at the unversioned root where each project supports it; otherwise pin to the latest tag.

## Required reading (work through the week)

### WebSocket — the protocol

- **RFC 6455 — The WebSocket Protocol** (IETF, December 2011). The single source of truth for everything every WebSocket library implements.
  <https://datatracker.ietf.org/doc/html/rfc6455>
  - §1.3 Opening Handshake — the `Upgrade: websocket`, `Connection: Upgrade`, `Sec-WebSocket-Key`, `Sec-WebSocket-Version: 13` headers
  - §1.4 Closing Handshake — close codes, the close frame, the half-close semantics
  - §4 Opening Handshake — server-side: the SHA-1 of `Sec-WebSocket-Key + GUID`, base64-encoded into `Sec-WebSocket-Accept`
  - §5 Data Framing — opcode, payload length, masking; the reason client frames are masked
  - §7.4 Status Codes — the reserved `1000`–`2999` range, the application `3000`–`3999`, the private `4000`–`4999`
- **RFC 8441 — Bootstrapping WebSockets with HTTP/2** (2018). Reference only; FastAPI under uvicorn does not use this path.
  <https://datatracker.ietf.org/doc/html/rfc8441>
- **MDN — Writing WebSocket servers**: a readable companion to RFC 6455:
  <https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_servers>
- **MDN — WebSocket on the client**:
  <https://developer.mozilla.org/en-US/docs/Web/API/WebSocket>

### WebSocket — the FastAPI side

- **FastAPI — WebSockets tutorial** — the primary docs page; covers `@app.websocket`, the connection manager pattern, and `WebSocketDisconnect`:
  <https://fastapi.tiangolo.com/advanced/websockets/>
- **Starlette — WebSockets** — what FastAPI inherits; `ws.accept`, `ws.receive_text`, `ws.send_json`, `ws.iter_text`:
  <https://www.starlette.io/websockets/>
- **FastAPI — Testing WebSockets** — `TestClient.websocket_connect`:
  <https://fastapi.tiangolo.com/advanced/testing-websockets/>
- **`websockets`** — the standalone Python WebSocket client and server library; useful for tests and standalone clients:
  <https://websockets.readthedocs.io/>
- **`broadcaster`** — Tom Christie's small library (~400 lines) implementing the Redis Pub/Sub pattern; read its source to see the cleanest version of what we build:
  <https://github.com/encode/broadcaster>

### Server-Sent Events

- **HTML Living Standard — Server-Sent Events** — the normative spec; ~one printed page:
  <https://html.spec.whatwg.org/multipage/server-sent-events.html>
- **MDN — Using Server-Sent Events** — the developer-facing guide:
  <https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events>
- **MDN — `EventSource`** — the browser API reference: `readyState`, `onmessage`, `onerror`, `Last-Event-ID`:
  <https://developer.mozilla.org/en-US/docs/Web/API/EventSource>
- **`sse-starlette`** — a Starlette/FastAPI helper that wraps `StreamingResponse` for SSE; we use it in the mini-project:
  <https://github.com/sysid/sse-starlette>
- **Starlette — Responses → `StreamingResponse`** — the underlying primitive:
  <https://www.starlette.io/responses/#streamingresponse>

### Background jobs — the runners

- **ARQ documentation** — the entire site is short:
  <https://arq-docs.helpmanual.io/>
  - **Usage** — `WorkerSettings`, `@cron`, `await pool.enqueue_job(...)`:
    <https://arq-docs.helpmanual.io/#usage>
  - **Settings reference** — every keyword on `WorkerSettings`:
    <https://arq-docs.helpmanual.io/#arq.worker.Worker>
  - **API reference — `arq.connections`** — `create_pool`, `RedisSettings`:
    <https://arq-docs.helpmanual.io/#arq.connections.RedisSettings>
- **Celery — User Guide** — the canonical, larger framework:
  <https://docs.celeryq.dev/en/stable/userguide/>
  - **Tasks** — definition, retries, acks-late, idempotency:
    <https://docs.celeryq.dev/en/stable/userguide/tasks.html>
  - **Calling Tasks** — `apply_async`, the `eta` / `countdown` options:
    <https://docs.celeryq.dev/en/stable/userguide/calling.html>
  - **Workers** — pooling models (prefork, eventlet, gevent, solo, threads), and why prefork is the default:
    <https://docs.celeryq.dev/en/stable/userguide/workers.html>
  - **Periodic Tasks** — `celery beat`; the headline feature ARQ does not match:
    <https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html>
- **RQ (Redis Queue)** — the third option; sync, Redis-only, minimal:
  <https://python-rq.org/>
  - **Workers**: <https://python-rq.org/docs/workers/>
  - **Job lifecycle**: <https://python-rq.org/docs/jobs/>

### Redis — Pub/Sub and the broker

- **Redis Pub/Sub overview** — the messaging primitive the broadcast pattern uses:
  <https://redis.io/docs/latest/develop/interact/pubsub/>
- **Redis `SUBSCRIBE`** command reference:
  <https://redis.io/commands/subscribe/>
- **Redis `PUBLISH`** command reference:
  <https://redis.io/commands/publish/>
- **`redis-py`** — the async client we use directly:
  <https://redis-py.readthedocs.io/en/stable/>
- **`redis-py` PubSub usage** — async pattern:
  <https://redis-py.readthedocs.io/en/stable/advanced_features.html#publish-subscribe>

### HTTP — the specs the new surfaces still honour

- **RFC 9110 — HTTP Semantics** — the status codes we use this week:
  <https://datatracker.ietf.org/doc/html/rfc9110>
  - §15.3.3 — 202 Accepted (the "I started the work" response)
  - §15.5.21 — 422 Unprocessable Content (validation failure on the enqueue body)
  - §10 — Authentication; the `Authorization` header still carries the token, even on a WS handshake
- **RFC 7540 / 9113 — HTTP/2** — relevant only to the WS-over-HTTP/2 (RFC 8441) note. Skim:
  <https://datatracker.ietf.org/doc/html/rfc9113>

### Async Python — the runtime the lectures lean on

- **Python — `asyncio` overview**:
  <https://docs.python.org/3/library/asyncio.html>
- **Python — Coroutines and Tasks**: `create_task`, `gather`, `wait_for`:
  <https://docs.python.org/3/library/asyncio-task.html>
- **Python — Streams** — `StreamReader`, `StreamWriter`; the layer below `websockets`:
  <https://docs.python.org/3/library/asyncio-stream.html>
- **`anyio`** — Starlette's structured-concurrency layer; useful for fan-out and timeouts:
  <https://anyio.readthedocs.io/>

## Background-job decision guides

These are the comparison articles we cite in Lecture 3. Read at least two:

- **ARQ — README on GitHub** — the author's stated motivation (asyncio-native, minimal, no acks-late):
  <https://github.com/python-arq/arq#readme>
- **"Choosing between Celery, RQ, and Dramatiq" (search)** — there are several good blog posts under this title; any one is acceptable. The honest comparison is: Celery is the most powerful and the most fragile, RQ is the most boring and the most reliable, ARQ is the most modern and the youngest, Dramatiq is the dark-horse alternative we do not cover this week but is worth knowing about.
- **Dramatiq** — for context only; we do not use it this week:
  <https://dramatiq.io/>

## Testing tools

- **FastAPI — Testing WebSockets**: <https://fastapi.tiangolo.com/advanced/testing-websockets/>
- **`httpx` — Streaming responses**: <https://www.python-httpx.org/async/#streaming-responses>
- **`pytest-asyncio`**: <https://pytest-asyncio.readthedocs.io/en/latest/>
- **`arq.worker.Worker.run_check`** — the in-process, one-shot worker for tests:
  <https://arq-docs.helpmanual.io/#testing-with-arq>

## Browser-side references

- **`EventSource` interface**: <https://developer.mozilla.org/en-US/docs/Web/API/EventSource>
- **`WebSocket` interface**: <https://developer.mozilla.org/en-US/docs/Web/API/WebSocket>
- **Chrome DevTools — Inspect network activity / WebSocket frames**:
  <https://developer.chrome.com/docs/devtools/network/reference/#frames>

## Operations and infrastructure

- **Cloudflare — How long-lived connections work behind the proxy** (search the Cloudflare docs for "WebSocket" and "100 second timeout"). The headline number to remember: idle connections close after 100 seconds; a heartbeat must keep them alive.
  <https://developers.cloudflare.com/network/websockets/>
- **Nginx — Proxying WebSocket** — the `proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";` recipe:
  <https://nginx.org/en/docs/http/websocket.html>
- **Nginx — Buffering for SSE** — set `proxy_buffering off; proxy_cache off; X-Accel-Buffering: no` to keep the stream flowing:
  <https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering>

## The references worth bookmarking forever

- **The ARQ source** — `arq/worker.py`, `arq/connections.py`; about 1 500 lines:
  <https://github.com/python-arq/arq>
- **The Celery source** — much larger; the `celery/app/task.py` is the canonical entry point:
  <https://github.com/celery/celery>
- **The Starlette source — `starlette/websockets.py`** — the `WebSocket` class FastAPI inherits:
  <https://github.com/encode/starlette/blob/master/starlette/websockets.py>
- **The Starlette source — `starlette/responses.py`** — the `StreamingResponse` SSE leans on:
  <https://github.com/encode/starlette/blob/master/starlette/responses.py>
- **The `websockets` library source** — pure-Python WebSocket client and server:
  <https://github.com/python-websockets/websockets>

## Cited in the lectures

These URLs appear by name in the lecture notes:

- **`datatracker.ietf.org/doc/html/rfc6455`** — Lecture 1 (§§ 1.3, 4, 5, 7.4)
- **`fastapi.tiangolo.com/advanced/websockets/`** — Lecture 1, mini-project
- **`www.starlette.io/websockets/`** — Lecture 1
- **`html.spec.whatwg.org/multipage/server-sent-events.html`** — Lecture 2
- **`developer.mozilla.org/en-US/docs/Web/API/EventSource`** — Lecture 2, mini-project
- **`developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events`** — Lecture 2
- **`www.starlette.io/responses/`** — Lecture 2 (the `StreamingResponse` discussion)
- **`arq-docs.helpmanual.io/`** — Lecture 3, mini-project
- **`docs.celeryq.dev/en/stable/userguide/tasks.html`** — Lecture 3, challenge 2
- **`python-rq.org/`** — Lecture 3
- **`redis.io/docs/latest/develop/interact/pubsub/`** — Lecture 1, challenge 1
- **`datatracker.ietf.org/doc/html/rfc9110`** — Lecture 3 (§15.3.3 on 202 Accepted)
