# Week 1 — Quiz

Ten multiple-choice questions. Take it with your lecture notes closed. Aim for 9/10 before moving to Week 2. Answer key at the bottom — don't peek.

---

**Q1.** Which of the following is the only HTTP/1.1 header that is *required* in every request?

- A) `User-Agent`
- B) `Accept`
- C) `Host`
- D) `Connection`

---

**Q2.** A WSGI application is, at its core:

- A) A class that subclasses `wsgi.Application`.
- B) An async function with `scope`, `receive`, and `send` parameters.
- C) A callable that takes `environ` and `start_response` and returns an iterable of bytes.
- D) Any function decorated with `@wsgi.route`.

---

**Q3.** Which HTTP method should you use to **completely replace** the contents of an existing resource at a known URL?

- A) `POST`
- B) `PUT`
- C) `PATCH`
- D) `UPDATE`

---

**Q4.** Your API returns `401 Unauthorized` when a user submits the wrong password. Which is more correct?

- A) `401` — the user has not authenticated.
- B) `403` — the user is forbidden from logging in.
- C) `400` — the user's request was malformed.
- D) `422` — the credentials failed validation.

---

**Q5.** Which is the most accurate statement about WSGI vs ASGI?

- A) ASGI is faster than WSGI for all workloads.
- B) WSGI cannot handle WebSockets; ASGI can.
- C) Django can only be deployed on WSGI; FastAPI only on ASGI.
- D) ASGI is a replacement for WSGI; new code should never use WSGI.

---

**Q6.** Which sequence of bytes ends every line in an HTTP/1.1 message?

- A) `\n` (LF)
- B) `\r` (CR)
- C) `\r\n` (CR LF)
- D) `\n\r` (LF CR)

---

**Q7.** You're building a public JSON API for a mobile app. 95% of endpoints are read-heavy, you need OpenAPI documentation, and you want automatic input validation. Which framework is the best default choice?

- A) Flask
- B) Django (without DRF)
- C) FastAPI
- D) Tornado

---

**Q8.** Your colleague claims their FastAPI endpoint is "async" because it's defined with `async def`, but inside it they call `time.sleep(2)`. What's wrong with this code?

- A) Nothing — `async def` automatically makes blocking calls non-blocking.
- B) `time.sleep` blocks the entire event loop, freezing every concurrent request.
- C) FastAPI will raise an exception at runtime because sync code in async views is forbidden.
- D) The endpoint will work but use 2× more memory than expected.

---

**Q9.** Which status code does a server typically return when a `GET` request reaches a route that *exists* but the resource (e.g. `/users/9999`) does not?

- A) `400 Bad Request`
- B) `403 Forbidden`
- C) `404 Not Found`
- D) `500 Internal Server Error`

---

**Q10.** Which is true about the `Host` header in HTTP/1.1?

- A) It's optional — servers default to the request's IP address if missing.
- B) It's required — the server uses it to route between virtual hosts on the same IP.
- C) It only appears in HTTPS requests.
- D) It's only required when the client uses a proxy.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **C** — `Host` is the only required HTTP/1.1 request header. Without it, the server can't disambiguate virtual hosts and will typically return `400`.
2. **C** — PEP 3333 defines a WSGI app as a callable with `(environ, start_response)` returning an iterable of bytes.
3. **B** — `PUT` replaces the entire resource. `PATCH` partially updates. `POST` creates or runs an action; not for replacement.
4. **A** — `401` is for "no/invalid authentication credentials." `403` is "authenticated but not allowed."
5. **B** — WSGI is sync-only and cannot support WebSockets. ASGI was designed to handle them and added the event-based protocol model.
6. **C** — CRLF (`\r\n`). Always.
7. **C** — FastAPI is purpose-built for this case: typed, OpenAPI-first, async, Pydantic validation.
8. **B** — `time.sleep` is a synchronous blocking call. It freezes the event loop. Use `await asyncio.sleep(2)` instead.
9. **C** — `404` for "resource doesn't exist." `400` is for malformed requests; `500` is for server errors.
10. **B** — `Host` is required so servers can route between multiple sites hosted on the same IP. Modern HTTPS uses SNI (Server Name Indication) in the TLS handshake for similar reasons.

</details>

---

If you scored under 7, re-read the lectures for the questions you missed. If you scored 9 or 10, you're ready to dive into the [homework](./06-homework.md).
