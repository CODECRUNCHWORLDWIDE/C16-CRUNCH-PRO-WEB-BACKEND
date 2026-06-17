# Exercises — Worked solutions

These are walk-throughs of the trickier prompts in each exercise. Read after you have tried the prompt yourself; the value is in the contrast between your answer and ours, not in the answer itself.

---

## Exercise 1 — WebSocket: echo and broadcast

### Task 1 — The handshake on the wire

With the server running, the `curl` invocation from the prompt produces:

```text
HTTP/1.1 101 Switching Protocols
upgrade: websocket
connection: Upgrade
sec-websocket-accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

Verify the accept value by hand:

```bash
echo -n "dGhlIHNhbXBsZSBub25jZQ==258EAFA5-E914-47DA-95CA-C5AB0DC85B11" \
  | openssl dgst -sha1 -binary | base64
# s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

The 22-character base64 strings are identical. Three things to note:

- The `101` status is per RFC 9110 §15.2.2 (the "Switching Protocols" code). It is the only legitimate path to a WebSocket connection over HTTP/1.1.
- The GUID `258EAFA5-E914-47DA-95CA-C5AB0DC85B11` is a constant in RFC 6455 §4.2.2. It is not a secret. It exists so that an HTTP server that *coincidentally* echoes the request key back cannot accidentally pose as a WebSocket server — the server must explicitly know to append the GUID and hash.
- `Sec-WebSocket-Accept` is *not* an authenticator. Any server that has the GUID (which is every server) can compute it. The handshake is a liveness check, not a credential exchange. Authentication happens via the `Authorization` header (Task 4) or via a separate `Sec-WebSocket-Protocol` negotiation.

### Task 2 — Three clients receive the broadcast

The POST to `/broadcast` with three clients connected on `/ws/feed` returns:

```json
{"sent": 3, "total": 3}
```

All three wscat sessions print:

```text
{"event": "broadcast", "text": "everyone hear this"}
```

The connection manager's set has three entries; `manager.broadcast` iterates over a snapshot of the set (acquired under the lock, then released) and calls `send_json` outside the lock. The point of the snapshot-then-release pattern is that one slow client's send call cannot block another client's disconnect from removing itself.

### Task 3 — Empty body returns 422

A POST with `{"text": ""}` returns:

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "text"],
      "msg": "String should have at least 1 character",
      "input": "",
      "ctx": {"min_length": 1}
    }
  ]
}
```

with HTTP status **422 Unprocessable Content**. RFC 9110 §15.5.21: "The 422 (Unprocessable Content) status code indicates that the server understands the content type of the request content … and the syntax of the request content is correct, but it was unable to process the contained instructions." This is the canonical code for "your JSON parsed but a field's value is semantically wrong" — Pydantic's responsibility, surfaced by FastAPI as 422.

A 400 would also be defensible but conflates "JSON is malformed" with "JSON parsed but failed validation". Keeping them distinct is the FastAPI convention.

### Task 4 — Why the browser cannot pass `Authorization`

The browser's WebSocket constructor — `new WebSocket(url)` — accepts a URL and an optional subprotocol list. It does *not* accept a headers dictionary. The handshake request the browser sends is HTTP, but the browser owns the HTTP headers and exposes only a curated subset (`Origin`, the cookies for the URL's domain, the `Sec-WebSocket-*` headers). There is no JavaScript API to set `Authorization` on a WebSocket handshake.

The standard workarounds:

1. **Cookie auth.** The browser sends cookies on the WebSocket handshake automatically. `Set-Cookie: session=...; HttpOnly; Secure; SameSite=Strict` from a normal HTTP response lets the next `new WebSocket(...)` authenticate by cookie.
2. **Query parameter.** `new WebSocket("ws://.../ws/auth?token=...")`. Token in the URL ends up in access logs.
3. **Subprotocol.** `new WebSocket(url, ["bearer.eyJhbGciOiJI..."])`. The server reads the `Sec-WebSocket-Protocol` header. Awkward, but standardised.
4. **A short-lived ticket.** The browser fetches a ticket over HTTPS with the proper `Authorization` header, then opens the WebSocket with `?ticket=...`. The ticket is one-use, server-side, TTL ~60 seconds.

For this exercise we use the `Authorization` header anyway, because `wscat -H` can set it. In the mini-project (where the client is a real browser) we use option 4.

### Task 5 — The integration tests

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# from the exercise module:
# from exercise_01_websocket_echo_and_manager import app


def test_echo_round_trips(app) -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws/echo") as ws:
        ws.send_text("hi")
        assert ws.receive_text() == "echo: hi"


def test_broadcast_reaches_all_feed_clients(app) -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws/feed") as a, client.websocket_connect("/ws/feed") as b:
        # POST in the same TestClient — synchronous in TestClient.
        response = client.post("/broadcast", json={"text": "hello"})
        assert response.status_code == 200
        assert response.json() == {"sent": 2, "total": 2}
        assert a.receive_json() == {"event": "broadcast", "text": "hello"}
        assert b.receive_json() == {"event": "broadcast", "text": "hello"}


def test_auth_required_rejects_missing_token(app) -> None:
    client = TestClient(app)
    with pytest.raises(Exception):  # WebSocketException is wrapped by TestClient
        with client.websocket_connect("/ws/auth"):
            pass
```

`TestClient.websocket_connect` returns a context manager whose `__enter__` performs the handshake and whose `__exit__` closes the connection. The synchronous `client.post(...)` inside the `with` block works because TestClient runs everything on a single event loop.

---

## Exercise 2 — SSE counter stream

### Task 1 — The first three frames

A `curl --no-buffer http://localhost:8000/sse/counter?limit=10` produces (after the status line and headers):

```text
: opening stream

event: tick
id: 0
data: {"n":0,"ts":"2026-05-14T..."}

event: tick
id: 1
data: {"n":1,"ts":"2026-05-14T..."}

```

Three things to notice:

- The first body bytes are the comment line `: opening stream\n\n`. Comments start with `:` and the browser silently ignores them. Their purpose is to force the response body to start *now*, so any proxy that holds the response open waiting for the first byte is unblocked at connect time.
- Every event ends with **two newlines**. The first newline terminates the last field; the second blank line terminates the event. Forgetting the second newline is the most common SSE bug — the browser will not dispatch the event until it sees the blank line.
- The `id:` field carries the sequence number. The browser saves the most recent `id:` value as the `Last-Event-ID`; on automatic reconnect, it sends that value back as a request header.

### Task 2 — Helper vs hand-rolled

Side-by-side, the two responses are nearly identical. `sse-starlette` adds:

- A `: ping\n\n` comment every `ping` seconds (default 15), which our hand-rolled version also does but on a per-tick basis (`if n % 5 == 0`).
- A more thorough disconnect detector — `EventSourceResponse` listens for the ASGI disconnect message on `receive` in parallel with the generator's `__anext__`, so it can break out the instant the client closes, rather than waiting for the next iteration to check `request.is_disconnected()`.
- Standardised handling of the `data` field being a dict — the helper JSON-encodes it for you; the hand-rolled version asks you to do that yourself.

The hand-rolled version is shown to demystify the helper. In production, prefer the helper: less code to maintain, the disconnect handling is more responsive, and the contributors have fielded the edge cases.

### Task 3 — Why a `done` event matters

When the server-side generator returns and the HTTP response body ends, the browser-side `EventSource` *automatically reconnects*. From the browser's point of view, "the response closed" is indistinguishable from "the network dropped"; both call for a reconnect.

If the server has no more events to emit, the next reconnect will get another empty response and reconnect again, infinitely. The browser will burn battery and the server will see ghost traffic.

The conventional fix is a `done` event that the client handler watches for and uses to call `eventSource.close()` explicitly. After `.close()`, the `EventSource` does not reconnect. The server can also signal "do not reconnect" by responding with an HTTP status other than 200 (e.g. 204 No Content), but the in-band `done` event is more idiomatic because it lets the application know *why* the stream ended.

### Task 4 — The integration test

```python
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

# from the exercise module:
# from exercise_02_sse_counter_stream import app


@pytest.mark.asyncio
async def test_burst_emits_burst_then_done(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("GET", "/sse/burst?count=3") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            chunks: list[str] = []
            async for chunk in response.aiter_text():
                chunks.append(chunk)
            text = "".join(chunks)

    events = [
        line[len("event: "):]
        for line in text.splitlines()
        if line.startswith("event: ")
    ]
    assert events == ["burst", "burst", "burst", "done"]
```

Two notes:

- `client.stream("GET", url)` is an *async context manager*. Inside it, the response body is streamed; outside it, the response is closed and any further iteration raises.
- `aiter_text()` decodes the bytes as UTF-8 and yields chunks as they arrive. For an SSE stream, each chunk is typically one frame, but the test should not depend on that — assert on substrings or splits, not on chunk boundaries.

### Task 5 — Browser smoke test

Open `http://localhost:8000/sse/counter?limit=3` directly in Chrome — modern Chrome handles `text/event-stream` natively and the browser tab will show the framing as it arrives. The DevTools `Network → EventStream` tab parses each event into a row with type, id, and data columns, which is genuinely useful for debugging.

The pasted EventSource code from the prompt prints in the console:

```text
tick {"n":0,"ts":"..."}
tick {"n":1,"ts":"..."}
tick {"n":2,"ts":"..."}
done {"final":3}
```

Then the connection closes (via `es.close()`). If you remove the `es.close()` call and watch the network panel, you see the EventSource reconnect after ~3 seconds (the browser's default `retry` interval), then immediately receive a `done` event again, then reconnect again. The `es.close()` is non-optional in real client code.

---

## Exercise 3 — ARQ task and enqueue

### Task 1 — The retry backoff

ARQ's default backoff is `2 ** (job_try - 1)` seconds, capped at 300 seconds. The sequence for the first five tries is:

| `job_try` | Delay (s)         |
|----------:|-------------------|
| 1         | 0 (first attempt) |
| 2         | 1                 |
| 3         | 2                 |
| 4         | 4                 |
| 5         | 8                 |

So if `failing_task` is enqueued and raises on tries 1 and 2, the third try (which succeeds) runs about 1 + 2 = 3 seconds after the original enqueue. Verify by watching the worker log timestamps:

```text
[2026-05-14 09:00:00] failing_task → RuntimeError("failing on try 1")
[2026-05-14 09:00:01] failing_task → RuntimeError("failing on try 2")
[2026-05-14 09:00:03] failing_task → {"status": "ok", "succeeded_on_try": 3}
```

The reference is the `Worker._handle_failed_job` method in `arq/worker.py`. Search for `defer_score` to find where the next-try timestamp is computed.

### Task 2 — 202 vs 201

| Code | Section          | Meaning                                                                   |
|-----:|------------------|---------------------------------------------------------------------------|
| 201  | RFC 9110 §15.3.2 | "The request has been fulfilled and has resulted in one or more new resources being created." |
| 202  | RFC 9110 §15.3.3 | "The request has been accepted for processing, but the processing has not been completed." |

The distinction is **completion**. 201 says "we are done; here is what we made". 202 says "we have not started yet; come back later". For an enqueue that hands work to a worker, 202 is the right answer because:

- The response *cannot* honestly report "the resource was created" — the worker has not run yet.
- The response *can* honestly report "the request was accepted" — Redis acknowledged the enqueue.
- A `Location:` header in either case points at where the client can monitor or retrieve the resource. For 201 it points at the created resource; for 202 it points at a status endpoint or a stream endpoint.

The right pattern: 202 with `Location: /jobs/{job_id}` (the poll URL) plus, optionally, a `stream_url` in the body for SSE consumers. We include both.

### Task 3 — Watching the retry sequence

Enqueue with `?succeed_on_try=3`. The worker log shows:

```text
12:00:00.10 failing_task try=1; RuntimeError("failing on try 1")
12:00:01.10 failing_task try=2; RuntimeError("failing on try 2")
12:00:03.10 failing_task try=3; returning {"status": "ok", "succeeded_on_try": 3}
```

Elapsed between attempts: ~1s, ~2s — matching the table in Task 1. Note that the *job ID* stays the same across retries; only `ctx["job_try"]` increments.

### Task 4 — `keep_result` TTL

ARQ stores task results in Redis under `arq:result:<job_id>`. The TTL on that key is `keep_result` seconds (default 3600 = one hour).

The trade-off:

- **Pro:** Results disappear automatically. No need for a cleanup job. Redis memory is bounded by the rate of jobs times the result size times the TTL.
- **Con:** A client that polls for a result more than `keep_result` after enqueueing gets a cache miss. If the result mattered, it had to be persisted somewhere else (a Postgres table, S3, a file).

The cleanest pattern for results that matter: the worker writes the durable copy (Postgres row, S3 object) before it returns. The ARQ result is then just a "here is the path" pointer, and losing it after an hour costs you a re-query, not the data.

This is the same trade-off Celery has with `result_expires` (default 24 hours). The default values differ by 24× — Celery defaults more generous, ARQ defaults more disciplined — but the design is the same.

### Task 5 — Reading `arq/worker.py`

In the `Worker.async_run` method (or `Worker._run` in older versions), the two load-bearing lines are:

```python
# Pop a job from the queue (BRPOP on the `arq:queue` list)
job_data = await self.pool.brpop_value(...)
...
# Call the user-provided function
result = await function(ctx, *args, **kwargs)
```

The first line is "consume from Redis"; the second line is "call the user code with the worker's context". Everything else in `Worker.async_run` — try/except for retries, JSON deserialisation of the args, the result publish, the metrics — is plumbing around those two operations.

Reading the file once is the difference between "ARQ is magic" and "ARQ is 1 500 lines I can pull up in a tab".
