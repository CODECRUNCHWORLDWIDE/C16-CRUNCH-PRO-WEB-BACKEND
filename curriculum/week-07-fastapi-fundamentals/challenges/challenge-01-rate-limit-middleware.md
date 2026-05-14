# Challenge 1 — Token-bucket rate-limit middleware (pure ASGI)

> **Time:** ~1 hour. **Difficulty:** moderate.
> **Goal:** Implement a token-bucket rate limiter as a pure ASGI middleware, backed by the Redis instance you stood up in Week 6. Return `429 Too Many Requests` with the correct `Retry-After` header when a client exceeds its budget.

## Brief

Rate limiting is one of the few cross-cutting concerns that should live as middleware, not as a `Depends`. Two reasons:

1. **It runs on every route, including those the application has not yet registered.** Static assets, the OpenAPI document, `/docs`, `/redoc` — all served by Starlette, all should be subject to the same per-IP throttle. A dependency only fires on routes that declare it.
2. **The decision happens before any application code runs.** The whole point of throttling is to spend zero CPU on requests that are over budget. A `Depends` would happen *after* path matching, dependency resolution, and possibly body parsing. Middleware fires first.

The token bucket algorithm:

- Each client has a **bucket** that holds up to `B` tokens.
- The bucket refills at a constant rate of `R` tokens per second (capped at `B`).
- Every request costs one token. If the bucket is empty, the request is rejected with `429 Too Many Requests`.

We use Redis to share state across worker processes — single-host rate limiting that survives `uvicorn --workers 4`. The implementation uses an EVAL script for atomicity (read tokens, refill, deduct, write — all in one round trip).

## Specification

Implement `rate_limit.py` with a `RateLimitMiddleware` class that:

- Is a **pure ASGI middleware** — `__call__(self, scope, receive, send)`, not `BaseHTTPMiddleware.dispatch`. Reason: we must not read the body, and we want to set headers on the response stream.
- Identifies clients by `scope["client"][0]` (the client IP). For paths under `/auth/`, identify by `Authorization` header instead (so multiple users behind the same NAT each get their own bucket).
- Reads three configuration values from environment:
  - `RATE_LIMIT_BUCKET_SIZE` (default 100)
  - `RATE_LIMIT_REFILL_PER_SECOND` (default 10.0)
  - `REDIS_URL` (default `redis://localhost:6379/2`)
- On every HTTP request:
  - Skips non-HTTP scope types (websocket, lifespan).
  - Skips the `/healthz` path (so health checks never hit Redis).
  - Calls the Lua EVAL script (see below). The script returns `(allowed: int, remaining: float, retry_after_seconds: float)`.
  - If `allowed == 1`, calls the inner app and adds three headers to the response: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
  - If `allowed == 0`, sends a `429` response with `Retry-After: <retry_after_seconds>` and a JSON body `{"detail": "Too Many Requests"}`. Does NOT call the inner app.

## The Lua script (use it verbatim)

```lua
-- KEYS[1] = bucket key
-- ARGV[1] = bucket size (max tokens)
-- ARGV[2] = refill rate per second
-- ARGV[3] = now (unix timestamp, seconds, float)

local key = KEYS[1]
local bucket_size = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call("HMGET", key, "tokens", "ts")
local tokens = tonumber(data[1])
local ts = tonumber(data[2])

if tokens == nil then
    tokens = bucket_size
    ts = now
end

-- Refill since last check
local elapsed = math.max(0, now - ts)
tokens = math.min(bucket_size, tokens + elapsed * refill_rate)

local allowed = 0
local retry_after = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
else
    retry_after = (1 - tokens) / refill_rate
end

redis.call("HMSET", key, "tokens", tokens, "ts", now)
redis.call("EXPIRE", key, math.ceil(bucket_size / refill_rate) + 60)

return {allowed, tokens, retry_after}
```

This is the canonical token-bucket-in-Redis pattern. Reading it once is more useful than re-deriving it.

## Wiring

```python
# main.py
from fastapi import FastAPI
from rate_limit import RateLimitMiddleware

app = FastAPI()
app.add_middleware(RateLimitMiddleware)
```

CORS, if present, should be added BEFORE the rate limiter so that pre-flight OPTIONS requests do not eat a token. Middleware order matters: <https://fastapi.tiangolo.com/tutorial/cors/#cors-and-middleware-order>.

## Acceptance criteria

- [ ] `rate_limit.py` exists; the `RateLimitMiddleware` class is exported.
- [ ] `python3 -m py_compile rate_limit.py` is clean.
- [ ] Every method and function has type hints, including async return types.
- [ ] A burst of 100 requests from one IP succeeds; the 101st returns 429 with `Retry-After`.
- [ ] After the configured refill interval, a fresh request succeeds again.
- [ ] `/healthz` is exempt — 200 requests in a tight loop all succeed.
- [ ] Successful responses carry `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
- [ ] A test in `tests/test_rate_limit.py` exercises (a) the happy path, (b) the burst-to-429, (c) the recovery after sleeping `retry_after` seconds. Use `httpx.AsyncClient` with `ASGITransport`. Mock Redis with `fakeredis.aioredis` so tests do not require a live Redis.

## Why "pure ASGI" and not `BaseHTTPMiddleware`

`BaseHTTPMiddleware` is convenient but it buffers the response body into memory before forwarding it to the client. For a streaming response (`StreamingResponse` or a Server-Sent Events handler) this is a correctness problem, not a performance one — the streaming property is lost. Pure ASGI middleware wraps `send` directly and forwards every event as it arrives. For something that touches every response, pure ASGI is the right choice.

The pattern:

```python
class RateLimitMiddleware:
    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # ... bucket check ...
        if not allowed:
            await self._send_429(send, retry_after)
            return
        # Wrap `send` so we can stamp headers on the response.start event:
        async def send_wrapper(event: dict) -> None:
            if event["type"] == "http.response.start":
                event["headers"] = list(event["headers"])
                event["headers"].append((b"x-ratelimit-limit", str(self.bucket).encode()))
                event["headers"].append((b"x-ratelimit-remaining", str(int(remaining)).encode()))
            await send(event)
        await self.app(scope, receive, send_wrapper)
```

The list copy on `event["headers"]` is intentional: the original tuple list might be shared.

## Stretch goals

- **Per-route override** — read a `request.scope["route"].endpoint.__rate_limit__` attribute, set via a `@rate_limit(bucket=10, refill=1.0)` decorator, and honour it per-route. The decorator stamps the attribute onto the endpoint function; the middleware reads it.
- **Slack** — emit a structured log line (JSON) when a client crosses 80% of its bucket capacity in a 10-second window. This is the early-warning signal for production rate-limit tuning.
- **Sliding-window variant** — implement the same as a sliding-window log instead of a token bucket. Compare the memory profile (the log grows with request rate; the bucket is fixed-size).

## Cited

- Pure ASGI middleware patterns: <https://www.starlette.io/middleware/#pure-asgi-middleware>
- Redis EVAL atomicity: <https://redis.io/docs/latest/commands/eval/>
- RFC 9110 §15.5.29 (429 Too Many Requests): <https://datatracker.ietf.org/doc/html/rfc9110#section-15.5.29>
- RFC 9110 §10.2.3 (Retry-After): <https://datatracker.ietf.org/doc/html/rfc9110#section-10.2.3>
- `fakeredis` (pure-Python in-memory Redis for tests): <https://github.com/cunla/fakeredis-py>
- Token bucket algorithm (Wikipedia): <https://en.wikipedia.org/wiki/Token_bucket>
