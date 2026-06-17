# Lecture 1 — The Anatomy of HTTP

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can read a raw HTTP/1.1 request and response and explain every line. You can speak HTTP to a server by hand with `nc` or `telnet`.

If you only remember one thing from this lecture, remember this:

> **HTTP is just plain text.** When your browser visits a website, it opens a TCP connection to port 80 (or 443 for HTTPS) and *types* a request, character by character. The server *types* a response back. Everything in this course is a wrapper around that.

---

## 1. A 30-second history

| Year | Event | Why it matters |
|------|-------|----------------|
| 1969 | ARPANET goes live | Packet-switched networking — the ancestor of TCP/IP |
| 1989 | Tim Berners-Lee invents the Web at CERN | HTTP, HTML, URLs all proposed together |
| 1991 | HTTP/0.9 published | One method: `GET`. One line: `GET /index.html`. No headers. No status codes. |
| 1996 | HTTP/1.0 (RFC 1945) | Adds headers, status codes, content types. Modern HTTP begins. |
| 1999 | HTTP/1.1 (RFC 2068, later 9112) | Persistent connections, host header, chunked encoding. Still the lingua franca in 2026. |
| 2015 | HTTP/2 (RFC 7540, later 9113) | Binary framing, multiplexing, header compression. Transparent to apps. |
| 2022 | HTTP/3 (RFC 9114) | Runs over QUIC (not TCP). UDP-based, faster handshakes, mobile-friendly. |

**Why this matters for us:** in 2026, almost all *application code* still treats HTTP as if it were HTTP/1.1. Your Django view doesn't know or care whether the bytes arrived over HTTP/2 or HTTP/3 — that's the job of the reverse proxy in front of it. So **HTTP/1.1 is what you learn first**, and the rest follows.

---

## 2. The TCP/IP layer cake

When you type `https://example.com` in a browser, here's what happens, from the bottom up:

```
┌───────────────────────────────────────────────────────────────┐
│  Application:  HTTP/1.1  ←  this is the only layer you author  │
├───────────────────────────────────────────────────────────────┤
│  Presentation: TLS (encrypts HTTP into HTTPS)                 │
├───────────────────────────────────────────────────────────────┤
│  Transport:    TCP (reliable, ordered byte stream)            │
├───────────────────────────────────────────────────────────────┤
│  Internet:     IP (routing between machines)                  │
├───────────────────────────────────────────────────────────────┤
│  Link:         Ethernet, Wi-Fi, etc. (the cable / radio)      │
└───────────────────────────────────────────────────────────────┘
```

- **Link** layer: the physical or wireless medium.
- **IP** layer: addresses (`192.0.2.1`, `2001:db8::1`) and routing.
- **TCP** layer: turns the lossy packet world into a reliable, in-order stream of bytes. Handles retransmission, congestion control, ordering.
- **TLS** layer: optional. Wraps the byte stream in encryption and proves the server's identity via certificates.
- **HTTP** layer: structures the byte stream into request/response pairs.

You as the Django developer touch HTTP and (sometimes) TLS configuration. The rest is the kernel's job.

---

## 3. A raw HTTP/1.1 request — byte by byte

Open a terminal. Type this:

```bash
printf 'GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n' | nc example.com 80
```

That command sends literally the following bytes over TCP to `example.com` port 80:

```
GET / HTTP/1.1\r\n
Host: example.com\r\n
Connection: close\r\n
\r\n
```

Let's read it byte by byte. Every line ends with `\r\n` — that's a **CR** (carriage return, `0x0D`) followed by **LF** (line feed, `0x0A`). HTTP is one of the few protocols still alive that uses `\r\n` exclusively. **If you forget the `\r`, many servers will reject the request as malformed**. This bites people often.

### The request-line (line 1)

```
GET / HTTP/1.1
```

Three space-separated tokens:

1. **Method** (`GET`) — what action you want the server to take.
2. **Request target** (`/`) — usually a path. Can also be a full URL for proxies.
3. **HTTP version** (`HTTP/1.1`) — what dialect you speak.

### Headers (lines 2 and 3)

```
Host: example.com
Connection: close
```

Each header is `Name: Value` followed by `\r\n`. Names are case-insensitive; `Host`, `host`, and `HOST` all mean the same thing.

- **`Host`** is the only header that is *required* in HTTP/1.1. Without it, the server cannot tell which virtual host you want. Modern servers will respond `400 Bad Request` if you omit it.
- **`Connection: close`** tells the server "I'm done after this response, drop the connection." Without it, HTTP/1.1 defaults to keep-alive and the connection stays open for more requests.

### The blank line

```
\r\n
```

A single empty line marks the end of headers. After this comes the optional body. For `GET` there is usually no body.

### The body

`GET` has no body. Methods that carry data (`POST`, `PUT`, `PATCH`) include the body here, and they MUST set `Content-Length` (or `Transfer-Encoding: chunked`) so the server knows how many bytes to read.

---

## 4. A raw HTTP/1.1 response

The server might reply:

```
HTTP/1.1 200 OK\r\n
Content-Type: text/html; charset=UTF-8\r\n
Content-Length: 1256\r\n
Date: Mon, 13 May 2026 14:00:00 GMT\r\n
Connection: close\r\n
\r\n
<!doctype html>\n
<html>...
```

### The status-line

```
HTTP/1.1 200 OK
```

Three space-separated tokens:

1. **Version** — same as the request.
2. **Status code** — a three-digit number.
3. **Reason phrase** — human-readable, ignored by code (some servers omit it entirely).

### Response headers

- **`Content-Type`** — what kind of bytes are in the body. `text/html`, `application/json`, `image/png`, `application/octet-stream`...
- **`Content-Length`** — how many bytes of body to read. You can lie here, and bad things will happen.
- **`Date`** — when the response was generated, in [RFC 7231 §7.1.1.1](https://www.rfc-editor.org/rfc/rfc7231) format.

### Body

After the blank line, exactly `Content-Length` bytes of body follow. If `Transfer-Encoding: chunked` is set instead, the body is a series of size-prefixed chunks terminated by a zero-length chunk. You'll read about chunked encoding when you need it — most application code never sees it directly.

---

## 5. HTTP methods you'll use daily

| Method | Safe? | Idempotent? | Has body? | Use case |
|--------|:---:|:---:|:---:|----------|
| `GET` | ✅ | ✅ | ❌ | Read a resource. Never causes side effects. |
| `HEAD` | ✅ | ✅ | ❌ | Like `GET` but the server only returns headers (no body). Useful for "does this exist?" |
| `POST` | ❌ | ❌ | ✅ | Create a resource, or perform a "verb" action (login, charge, etc.). |
| `PUT` | ❌ | ✅ | ✅ | Replace a resource at a known URL with the body. |
| `PATCH` | ❌ | ❌ | ✅ | Partially update a resource. |
| `DELETE` | ❌ | ✅ | usually ❌ | Remove a resource. |
| `OPTIONS` | ✅ | ✅ | ❌ | Ask "what can I do at this URL?" Used by CORS preflight. |

**Definitions you need to know:**

- **Safe** — the method doesn't modify server state. `GET` should never delete a record. (If yours does, it's a bug — search engines pre-fetching links will trigger it.)
- **Idempotent** — calling it N times has the same effect as calling it once. `DELETE /users/42` is idempotent: deleting an already-deleted user just returns 404 or 204 the second time, no new side effect.

**Common mistakes:**

- Using `GET` for actions that modify data. (Search engine crawlers will trigger them.)
- Using `POST` when `PUT` is more semantically correct. (Less harmful, mostly stylistic.)
- Treating `PUT` and `PATCH` interchangeably. They're not — `PUT` replaces the whole resource; `PATCH` modifies a subset.

---

## 6. Status codes — the families

Every HTTP status code is a three-digit number. The first digit tells you the family:

| Family | Meaning | Examples |
|--------|---------|----------|
| **1xx** | Informational, hold on | `100 Continue`, `101 Switching Protocols` |
| **2xx** | Success | `200 OK`, `201 Created`, `204 No Content` |
| **3xx** | Redirect or cache | `301 Moved Permanently`, `302 Found`, `304 Not Modified` |
| **4xx** | Client error | `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `409 Conflict`, `422 Unprocessable Entity`, `429 Too Many Requests` |
| **5xx** | Server error | `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable`, `504 Gateway Timeout` |

### The ones you'll use in your code

| Code | When |
|------|------|
| `200 OK` | Generic success with a body. |
| `201 Created` | After `POST` creates something. Set `Location` header to the new resource. |
| `204 No Content` | Success, no body to send (e.g. after `DELETE`). |
| `301 / 308` | Permanent redirect. Search engines update their index. |
| `302 / 307` | Temporary redirect. |
| `304 Not Modified` | The client's cached copy is still good. Body is empty. |
| `400 Bad Request` | The client's request was malformed (e.g. bad JSON). |
| `401 Unauthorized` | "You need to authenticate." (Confusingly: NOT "you're not allowed.") |
| `403 Forbidden` | "You're authenticated but not allowed to do this." |
| `404 Not Found` | Resource doesn't exist. |
| `409 Conflict` | Concurrent edit, duplicate key, etc. |
| `422 Unprocessable Entity` | The body parsed fine but fails business validation. |
| `429 Too Many Requests` | Rate-limited. Set `Retry-After`. |
| `500 Internal Server Error` | Your code crashed. You should be paged. |
| `502 / 503 / 504` | Something between client and your app failed (proxy, backend, timeout). |

**Mnemonic:** *1xx hold, 2xx done, 3xx go, 4xx you, 5xx me.*

---

## 7. Headers you must know

We'll see more of these all course. For now, learn these:

### General

- **`Host`** — required. The server uses it for virtual hosting.
- **`User-Agent`** — what client is talking to you (curl, browser, bot).
- **`Date`** — when the message was generated.

### Content

- **`Content-Type`** — what's in the body. Always set on responses with a body.
- **`Content-Length`** — exact byte count of the body.
- **`Content-Encoding`** — `gzip`, `br` for compressed responses.
- **`Accept`** — what the client *wants* back. `Accept: application/json` means "send me JSON."
- **`Accept-Language`** — preferred languages, e.g. `en-US,en;q=0.9`.

### Auth & sessions

- **`Authorization`** — credentials. `Bearer <jwt>`, `Basic <base64>`, etc.
- **`Cookie`** — client sends back cookies the server previously `Set-Cookie`'d.
- **`Set-Cookie`** — server-to-client cookie creation. (We'll go deep on auth in Week 9.)

### Caching

- **`Cache-Control`** — `no-store`, `max-age=3600`, `public`, `private`...
- **`ETag`** — opaque version identifier of a resource.
- **`If-None-Match`** — client sends back an `ETag` to ask "is this still current?"

### CORS (cross-origin)

- **`Origin`** — sent by the browser on cross-origin requests.
- **`Access-Control-Allow-Origin`** — server says "yes, this origin can read me."

There are dozens more. You'll learn them as you need them. Don't memorize the IANA registry.

---

## 8. Try it yourself — three exercises

### A. Use `curl --verbose` to inspect a real request

```bash
curl -v https://example.com/
```

The `>` lines are what `curl` sent. The `<` lines are what the server returned. Identify each one of these in the output:

- The request-line (which method? which path? which version?)
- All request headers `curl` set by default
- The response status-line
- The response headers
- The first few bytes of the response body

### B. Use `nc` to speak HTTP manually

```bash
nc example.com 80
```

That opens a raw TCP connection. Now type — exactly, with no typos:

```
GET / HTTP/1.1
Host: example.com
Connection: close

```

(Two empty lines at the end — one ends the last header, one ends the request.)

You should receive a response. If you don't, you likely forgot the `Host` header (it's required) or sent an extra blank line at the start.

### C. Use HTTPie for a friendlier view

```bash
pip install httpie
http GET https://example.com
```

Notice how `http` shows the same information `curl -v` does, just prettier.

---

## 9. What we deliberately skipped

- **HTTP/2 framing** — interesting, not necessary for application development. The reverse proxy speaks HTTP/2 to the browser and HTTP/1.1 to your app. Your code doesn't change.
- **HTTP/3 / QUIC** — same story.
- **Chunked transfer encoding** — Django and FastAPI handle this for you.
- **Cache validators** (`If-Modified-Since`, `Vary`, etc.) — we'll cover in Week 6.
- **CORS deeply** — we'll cover when we build the FastAPI service in Week 7.
- **Cookies and sessions in depth** — Week 3 (Django sessions) and Week 9 (JWT).

---

## 10. Self-check

You should now be able to answer all of these without looking back:

1. What is the difference between TCP and HTTP?
2. What separates the request-line from the headers? What separates headers from the body?
3. Which HTTP method should you use to (a) read a list of articles, (b) create a new article, (c) replace article #5 entirely, (d) update only the title of article #5, (e) remove article #5?
4. What does it mean for a method to be *idempotent*? Give an example of a non-idempotent method and a non-trivial example of an idempotent one.
5. The browser shows a `403`. What did the server mean? Versus a `401`?
6. Why is the `Host` header required in HTTP/1.1?
7. What's the byte sequence that ends every line in HTTP?
8. The server returns `Content-Length: 100`. You read 80 bytes and the connection drops. What should your client do?

If any of those make you pause, re-read the relevant section. Then proceed to [Lecture 2 — WSGI, ASGI, and the Python Web Standards](./02-wsgi-asgi-and-the-python-web-standards.md).

---

## Further reading

- RFC 9110 §9 — HTTP methods: <https://www.rfc-editor.org/rfc/rfc9110#section-9>
- RFC 9110 §15 — Status codes: <https://www.rfc-editor.org/rfc/rfc9110#section-15>
- MDN HTTP — broad reference: <https://developer.mozilla.org/en-US/docs/Web/HTTP>
- *High Performance Browser Networking* — Ch. 9, "Brief History of HTTP": <https://hpbn.co/brief-history-of-http/>
