# Week 8 — Quiz

Ten questions. Lectures closed. One correct answer per question; the answer key is at the end.

---

**Q1.** Per RFC 6455 §4.2.2, the value of the `Sec-WebSocket-Accept` response header is:

- A) A random 16-byte nonce generated freshly by the server, base64-encoded.
- B) The SHA-256 hash of the client's `Sec-WebSocket-Key`, base64-encoded.
- C) The base64 encoding of the SHA-1 hash of the client's `Sec-WebSocket-Key` concatenated with the fixed GUID `258EAFA5-E914-47DA-95CA-C5AB0DC85B11`.
- D) An HMAC of the client key signed with the server's TLS private key.

---

**Q2.** All client-to-server WebSocket frames must be XOR-masked with a 4-byte key (RFC 6455 §5.3). The masking exists to:

- A) Provide confidentiality on top of TLS.
- B) Authenticate the client.
- C) Prevent a class of cache-poisoning attacks on legacy intermediaries that did not understand WebSocket framing.
- D) Compress the payload.

---

**Q3.** Inside a FastAPI WebSocket handler, you call `await ws.close(code=1011, reason="bad state")` from a try/except branch. The 1011 close code, per RFC 6455 §7.4, indicates:

- A) Normal closure.
- B) The server is going away (shutdown).
- C) The server encountered an unexpected condition that prevented it from fulfilling the request.
- D) A policy violation — typically an auth failure.

---

**Q4.** A FastAPI app runs under `uvicorn --workers 4`. Each worker keeps its own in-process `ConnectionManager`. A `POST /broadcast` to worker 1 results in a broadcast that reaches:

- A) Every connected client across all four workers.
- B) Only the clients connected to worker 1.
- C) Only one randomly-selected client across the four workers.
- D) No clients — the broadcast fails because the manager is not shared.

---

**Q5.** A Server-Sent Events frame is terminated by:

- A) The carriage-return character (`\r`).
- B) A null byte (`\0`).
- C) A blank line (two consecutive `\n` characters).
- D) Length-prefixed framing with a leading byte count.

---

**Q6.** The browser's `EventSource` reconnects automatically on disconnect. On the reconnect request, it sends a request header carrying the ID of the last event it saw. The header is:

- A) `If-Modified-Since`.
- B) `Last-Event-ID`.
- C) `X-SSE-Resume-From`.
- D) `Sec-EventStream-Cursor`.

---

**Q7.** Compared to WebSocket, Server-Sent Events:

- A) Are faster for any workload because they avoid the upgrade handshake.
- B) Support bidirectional messaging without separate HTTP requests.
- C) Are one-way (server-to-client only), use plain HTTP, and have browser-built-in auto-reconnect with `Last-Event-ID` resume.
- D) Require an HTTP/2 server to function.

---

**Q8.** ARQ is best described as:

- A) A multi-broker job queue with synchronous workers and a separate scheduler process.
- B) An async-native, Redis-only job queue, ~1 500 lines of source, with an in-worker `@cron` decorator.
- C) A FastAPI plugin that runs background work in the same process as the request handler.
- D) A Rust-based job queue with Python bindings.

---

**Q9.** Per RFC 9110 §15.3.3, the 202 (Accepted) status code is the right choice when:

- A) The server has created the requested resource and is returning it.
- B) The server has deleted the requested resource.
- C) The server has accepted the request for processing but has not yet completed it.
- D) The server has redirected the client to a different URL.

---

**Q10.** A FastAPI `BackgroundTasks` callable scheduled via `background.add_task(fn, ...)` runs:

- A) In a separate process maintained by the FastAPI runtime.
- B) On a Celery worker, transparently.
- C) After the HTTP response has been sent, *in the same worker process* as the request handler.
- D) Before the HTTP response is sent, blocking until completion.

---

## Answer key

| Question | Answer | Lecture / reference |
|---:|:---|:---|
| Q1 | C | Lecture 1 §2; RFC 6455 §4.2.2 |
| Q2 | C | Lecture 1 §3; RFC 6455 §5.3 |
| Q3 | C | Lecture 1 §4; RFC 6455 §7.4 |
| Q4 | B | Lecture 1 §5; the limit that motivates the Redis Pub/Sub broadcaster |
| Q5 | C | Lecture 2 §1; HTML living standard SSE section |
| Q6 | B | Lecture 2 §4; MDN `EventSource` reference |
| Q7 | C | Lecture 2 §5 — the decision matrix |
| Q8 | B | Lecture 3 §3; ARQ documentation home page |
| Q9 | C | Lecture 3 §2 and §3.2; RFC 9110 §15.3.3 |
| Q10 | C | Lecture 3 §6 — the FastAPI BackgroundTasks trap |
