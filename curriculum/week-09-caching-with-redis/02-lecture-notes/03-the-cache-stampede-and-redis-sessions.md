# Lecture 3 — The cache stampede and Redis sessions

> **Duration:** ~2 hours. **Outcome:** You can describe the cache-stampede failure mode in one paragraph, write the request-coalescing fix in 30 lines of Python, and implement Vattani et al.'s probabilistic-early-expiration algorithm from memory. You can configure Redis as the session backend for both Django (via the cache framework) and FastAPI (via a custom middleware), and you can describe the differences in framework surface area between the two.

Lectures 1 and 2 covered the steady-state behaviour of a cache: data types, patterns, eviction, invalidation. Lecture 3 covers the two interesting *non*-steady-state moments: the cliff that happens when a popular key expires, and the broader use of Redis as the canonical place for short-lived, shared-across-workers state — which is the session-store conversation.

The unifying theme is that Redis is fast, atomic, and shared. A cache is one use of that combination. A session store is another. A rate limiter (Week 11) is a third. The mechanics — `SET ... EX ...`, `SETNX`, Pub/Sub — are the same; the role the application gives them changes.

## 1. The cache stampede — what fails and why

A cache stampede is the failure mode that happens at the *moment a popular cached key expires*. Consider an endpoint that returns the homepage's top stories, cached with TTL 60 seconds, serving 1 000 requests per second. For 59 of every 60 seconds, the endpoint is a Redis hit at 1 ms. At the 60th second, the key expires. The first request to arrive after expiry misses the cache; while it is rebuilding the value (say, a 200 ms database query), the next 199 requests *also* miss the cache; each of them starts a rebuild of their own. The database receives 200 concurrent identical queries; the database's response time degrades; the rebuild that should have taken 200 ms takes 2 seconds; while it is taking 2 seconds, another 2 000 requests miss the cache and start their own rebuilds. The amplification is geometric. The database is on fire.

The shape of the incident in log lines:

```text
14:32:58.412  GET /home  cache=hit   latency=2ms
14:32:58.418  GET /home  cache=hit   latency=2ms
14:32:58.421  GET /home  cache=hit   latency=2ms
...
14:33:00.001  GET /home  cache=miss  latency=210ms
14:33:00.002  GET /home  cache=miss  latency=240ms
14:33:00.002  GET /home  cache=miss  latency=255ms
14:33:00.003  GET /home  cache=miss  latency=270ms
...
14:33:00.380  GET /home  cache=miss  latency=2150ms
14:33:00.382  GET /home  cache=miss  latency=2210ms
...
14:33:02.500  GET /home  cache=hit   latency=2ms
```

A 2.1-second period of `cache=miss` lines where the latency climbs as the database falls behind. The line that *should* have happened is one `cache=miss latency=210ms`, followed by ten thousand `cache=hit latency=2ms`. The bug is that "the first miss rebuilds the cache; everyone else waits on the first miss" is not the default behaviour. Implementing it is the work of this section.

The phenomenon has several names in different communities: cache stampede, dog-pile, thundering herd, cache miss storm. The Vattani et al. paper at <https://arxiv.org/abs/1504.00922> uses "cache stampede"; we will too.

## 2. Fix 1 — Request coalescing (single-flight)

The first fix is the most obvious: ensure that, of the N concurrent misses for the same key, exactly one of them goes to the source. The other N-1 wait on the result of the first one. In Go, the standard library calls this "singleflight"; in Python, it is one `asyncio.Future` per in-flight key.

```python
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as redis


class CoalescingCache:
    """A cache-aside helper with request coalescing.

    When N concurrent requests miss for the same key, exactly one of them
    invokes the loader; the others await its Future. This bounds the
    rebuild concurrency per key at one, regardless of inbound concurrency.
    """

    def __init__(self, r: redis.Redis) -> None:
        self._r = r
        self._inflight: dict[str, asyncio.Future[Any]] = {}
        self._lock = asyncio.Lock()

    async def get(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        ttl: int,
    ) -> Any:
        cached = await self._r.get(key)
        if cached is not None:
            return json.loads(cached)
        return await self._load_once(key, loader, ttl)

    async def _load_once(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        ttl: int,
    ) -> Any:
        async with self._lock:
            existing = self._inflight.get(key)
            if existing is not None:
                # Another coroutine is loading; await its result.
                future = existing
            else:
                future = asyncio.get_running_loop().create_future()
                self._inflight[key] = future
                asyncio.create_task(self._do_load(key, loader, ttl, future))
        return await future

    async def _do_load(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        ttl: int,
        future: asyncio.Future[Any],
    ) -> None:
        try:
            value = await loader()
            await self._r.set(key, json.dumps(value), ex=ttl)
            future.set_result(value)
        except Exception as exc:  # noqa: BLE001
            future.set_exception(exc)
        finally:
            async with self._lock:
                self._inflight.pop(key, None)
```

The shape is:

1. The first coroutine to ask for a missing key creates a `Future`, registers it under the key, kicks off the load task, and awaits the Future.
2. The next twenty coroutines to ask for the *same* key see the Future already in the in-flight map and await it directly. They do not start their own load.
3. The load task computes the value, writes the cache, sets the Future's result. Every awaiting coroutine wakes up with the value.
4. The `finally` clause removes the in-flight entry, so the *next* miss after this one starts a fresh load.

This is process-local coalescing. It bounds rebuild concurrency at one *per worker*. With four uvicorn workers, the database sees four concurrent rebuilds — much better than 200, not as good as 1. The cross-worker fix is a Redis-level lock:

```python
async def cross_worker_coalesce(r: redis.Redis, key: str,
                                 loader: Callable[[], Awaitable[Any]],
                                 ttl: int) -> Any:
    cached = await r.get(key)
    if cached is not None:
        return json.loads(cached)

    lock_key = f"lock:{key}"
    # SET ... NX EX is the atomic try-acquire.
    got_lock = await r.set(lock_key, "1", nx=True, ex=10)
    if got_lock:
        try:
            value = await loader()
            await r.set(key, json.dumps(value), ex=ttl)
            return value
        finally:
            await r.delete(lock_key)
    # Did not get the lock; wait for the holder to populate the cache.
    for _ in range(50):
        await asyncio.sleep(0.1)
        cached = await r.get(key)
        if cached is not None:
            return json.loads(cached)
    # Lock-holder failed or took too long. Fall back to running the loader.
    return await loader()
```

Three things to notice. The lock has a TTL of 10 seconds — if the lock-holder crashes before releasing, the next requester picks up the lock 10 seconds later. The waiters poll the cache every 100 ms for 5 seconds (50 iterations); if the cache still does not appear, they run the loader themselves and accept the stampede on that one key for that one moment. The polling is the ugliest part — Redis Pub/Sub would let waiters wait *event-driven* on the lock release, but the extra plumbing is more than the polling savings are worth at this scale.

The library `aiocache` has a coalescing pattern of its own; <https://aiocache.readthedocs.io>. The Go standard library's `singleflight` package is the same shape in fewer lines: <https://pkg.go.dev/golang.org/x/sync/singleflight>.

## 3. Fix 2 — Probabilistic early expiration (XFetch, Vattani 2015)

The second fix is more clever and requires no coordination. Vattani, Chierichetti, and Lowenstein's 2015 paper "Optimal Probabilistic Cache Stampede Prevention" (VLDB 2015, free at <https://arxiv.org/abs/1504.00922>) describes the **XFetch** algorithm.

The intuition: instead of every request waiting until the TTL expires to refresh the cache, each request, *while it is reading the cache*, rolls a dice based on how close the cache is to expiry. If the roll says "you are the unlucky one", *that* request goes to the source and refreshes the cache — even though the cache has not actually expired yet. Most requests, most of the time, hit a non-expired cache and the roll says "you are not unlucky". As the TTL approaches expiry, the probability of being unlucky grows, until at the exact expiry it is certain. The expectation is: one request refreshes the cache slightly before it would have expired anyway; every other request keeps reading the cache; the expiry-moment cliff is gone.

The formula, from the paper:

```text
if current_time - delta * beta * log(rand()) >= expiry:
    refresh
```

where:

- `current_time` is now (in seconds since epoch, or any monotonic time).
- `delta` is the expected cost of refreshing the cache (the loader's typical latency, in the same time units).
- `beta` is a tuning parameter; the paper proves that `beta = 1.0` is optimal.
- `rand()` is a uniform `(0, 1)` random number.
- `log` is the natural logarithm. Note: `log(rand())` is negative (since `rand() < 1`), so subtracting it adds a positive amount.
- `expiry` is the cache's expiration timestamp.

When the cache has just been populated, `current_time` is far below `expiry`; the small amount added by `-delta * log(rand())` is unlikely to push it past. As `current_time` approaches `expiry`, the threshold to cross is smaller, and the random push is more likely to clear it. At the exact moment of expiry, *any* random push clears it.

In Python:

```python
import math
import random
import time
from typing import Any


def xfetch_should_refresh(
    expiry_unix: float,
    delta: float,
    beta: float = 1.0,
    now: float | None = None,
) -> bool:
    """Vattani et al. 2015, "Optimal Probabilistic Cache Stampede Prevention".

    Returns True if this caller should refresh the cache early.
    """
    t = now if now is not None else time.time()
    return t - delta * beta * math.log(random.random()) >= expiry_unix
```

The cache-aside read becomes:

```python
async def cache_aside_xfetch(
    r: redis.Redis,
    key: str,
    loader: Callable[[], Awaitable[Any]],
    ttl: int,
    delta: float,
) -> Any:
    pipe = r.pipeline()
    pipe.get(key)
    pipe.ttl(key)
    cached, remaining_ttl = await pipe.execute()
    if cached is None:
        # Cold miss — load and write.
        value = await loader()
        await r.set(key, json.dumps(value), ex=ttl)
        return value

    expiry_unix = time.time() + remaining_ttl
    if xfetch_should_refresh(expiry_unix, delta):
        # Probabilistic early refresh. Background it; return the cached value.
        asyncio.create_task(_refresh_in_background(r, key, loader, ttl))
    return json.loads(cached)


async def _refresh_in_background(
    r: redis.Redis,
    key: str,
    loader: Callable[[], Awaitable[Any]],
    ttl: int,
) -> None:
    try:
        value = await loader()
        await r.set(key, json.dumps(value), ex=ttl)
    except Exception:  # noqa: BLE001
        pass
```

The cached value is returned immediately; the refresh runs in the background, populating the cache for the next reader. The probability of *any* given reader being the one to refresh is small at first (when the TTL is fresh) and approaches 1 as expiry nears. With high read volume, the expected number of refreshes per TTL window approaches one — exactly what we want.

The `delta` parameter is the loader's typical wall-clock latency. If the loader takes 200 ms, set `delta = 0.2`. The paper shows that the algorithm is robust to estimation errors in `delta` — being off by a factor of 2 has minor effect on the stampede prevention. The cited optimal `beta = 1.0` is the value to use unless you have a measurement-driven reason to deviate.

**XFetch versus single-flight coalescing.** Single-flight gives strict at-most-one-rebuild-per-key. XFetch is probabilistic; in the worst case, two readers could refresh nearly simultaneously. The advantage of XFetch is that it requires *no coordination* — no in-flight map, no Redis lock — which is the right answer when the cache layer is sharded and per-key coordination is expensive. Single-flight is the right answer when you have one cache and want determinism.

Most production systems use single-flight for the highest-traffic keys (the ones where you want determinism) and XFetch (or nothing) for the long tail. Knowing both lets you make the trade-off.

## 4. The third fix you do not need — pre-warming

A third strategy worth naming, only to dismiss: pre-warming the cache. The idea is to refresh the cache *before* the TTL expires, on a background schedule, so the cache is never empty. This works for small, predictable key sets (the homepage; the popular-tags list) and it does not work for the long tail (a user-specific cache cannot be pre-warmed without enumerating every user). It is also a separate process — a cron job, an ARQ recurring task — which is operational overhead the XFetch and single-flight fixes do not have.

Pre-warming is correct for the *very* hot, *very* few keys. For everything else, the cache-aside-plus-stampede-fix pattern is enough.

## 5. Redis as a session store

A session is a small, server-side, expirable piece of state keyed by a session ID that the client carries in a cookie. The contents are typically the user's authentication identity, some preferences, a CSRF token. The shape is "shared across workers, must survive a worker restart, must expire on inactivity". The cookie holds only the session ID — never the contents — so that revoking a session is one server-side delete.

Redis is the canonical session store for the same reasons it is a good cache: fast, shared, key-value, TTL-aware. The session ID is the Redis key; the contents are a JSON-serialised dict at that key; the TTL is the session lifetime ("expire in 30 minutes of inactivity" via `SET ... EX 1800` on every access). The `volatile-ttl` eviction policy is occasionally useful for session-store Redis instances.

### 5.1 Django — sessions in the cache framework

Django ships with a session framework that supports four backends: database, file system, cached database (cache plus DB for durability), and cache. The cache backend is what we want for Redis. The configuration is two lines in `settings.py`:

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://localhost:6379/1",
        "OPTIONS": {
            "db": 1,
        },
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = 1800  # 30 minutes
SESSION_SAVE_EVERY_REQUEST = True  # Slide the TTL on every request
```

Three observations:

1. **`django.core.cache.backends.redis.RedisCache`** is the Django 4.0+ built-in backend. Before 4.0 you had to install `django-redis` (still useful, more featureful — see <https://github.com/jazzband/django-redis>).
2. **`db=1`** uses Redis logical database 1 for the cache. Using a separate logical database from your application cache lets `redis-cli FLUSHDB` on db 1 clear sessions without clearing application caches. (Logical databases in Redis are a numeric index from 0 to 15 by default; they share the server but namespace the keyspace.)
3. **`SESSION_SAVE_EVERY_REQUEST = True`** is the *sliding-TTL* discipline. Every request from a logged-in user touches the session key and extends its TTL by `SESSION_COOKIE_AGE`. The user logs in once; as long as they are active, the session stays alive; after 30 minutes of inactivity, the session expires. The alternative — `False` — means the session has a fixed lifetime from login; if the user is active at minute 29, the session still dies at minute 30. Fixed TTL is rarer.

Django stores sessions under keys like `:1:django.contrib.sessions.cache<session_key>`. You can inspect them with `redis-cli -n 1 KEYS '*django*'` (in development; never `KEYS` in production — use `SCAN`). The serialiser is JSON by default in Django 4.1+; older versions use pickle and ship the pickle-versus-JSON trade-off ([the security note in the Django docs](https://docs.djangoproject.com/en/5.1/topics/http/sessions/#session-serialization)).

Cite the full session-framework page: <https://docs.djangoproject.com/en/5.1/topics/http/sessions/>.

### 5.2 FastAPI — sessions via custom middleware

FastAPI does not ship a session framework. Starlette ships a `SessionMiddleware` (<https://www.starlette.io/middleware/#sessionmiddleware>) that stores the entire session in a signed cookie — which works for small payloads but does not scale and does not let you revoke a session server-side. The Redis-backed pattern is something you build.

The shape: a middleware reads the session ID from a cookie, looks up the contents in Redis, attaches them to `request.state.session`, and on response writes any changes back to Redis. The session ID cookie is signed (HMAC) to prevent client tampering — even though the cookie carries only an ID, you want to refuse forged IDs at the middleware layer.

```python
from __future__ import annotations

import json
import secrets
from collections.abc import Awaitable, Callable

import redis.asyncio as redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RedisSessionMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Any,
        redis_client: redis.Redis,
        cookie_name: str = "session_id",
        ttl_seconds: int = 1800,
    ) -> None:
        super().__init__(app)
        self._r = redis_client
        self._cookie_name = cookie_name
        self._ttl = ttl_seconds

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        session_id = request.cookies.get(self._cookie_name)
        session_data: dict[str, Any] = {}
        is_new = False
        if session_id:
            raw = await self._r.get(f"session:{session_id}")
            if raw is not None:
                session_data = json.loads(raw)
            else:
                # Stale cookie — issue a new session ID.
                session_id = secrets.token_urlsafe(32)
                is_new = True
        else:
            session_id = secrets.token_urlsafe(32)
            is_new = True

        request.state.session = session_data
        request.state.session_id = session_id

        response = await call_next(request)

        # Write any session changes back, with TTL refresh.
        if request.state.session:
            await self._r.set(
                f"session:{session_id}",
                json.dumps(request.state.session),
                ex=self._ttl,
            )
        if is_new:
            response.set_cookie(
                self._cookie_name,
                session_id,
                httponly=True,
                samesite="lax",
                max_age=self._ttl,
            )
        return response
```

Three observations:

1. **The cookie holds only the session ID.** Never the contents. This is what lets `await r.delete(f"session:{sid}")` revoke a session.
2. **`secrets.token_urlsafe(32)`** generates a 32-byte cryptographically random session ID. The default in Django is 32 hex characters; either works. URL-safe is what `secrets.token_urlsafe` returns.
3. **The TTL refreshes on every request that writes to the session.** If a route reads `request.state.session` but does not modify it, the middleware here does not refresh — which is a slightly different policy from Django's `SESSION_SAVE_EVERY_REQUEST=True`. If you want sliding-TTL on every read, refresh unconditionally (`await r.expire(f"session:{session_id}", self._ttl)`) in the response branch.

Wiring it up:

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI


redis_client = redis.from_url("redis://localhost:6379/2", decode_responses=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await redis_client.aclose()


app = FastAPI(lifespan=lifespan)
app.add_middleware(RedisSessionMiddleware, redis_client=redis_client)


@app.get("/profile")
async def profile(request: Request) -> dict[str, Any]:
    session = request.state.session
    return {"user": session.get("user", "anonymous")}


@app.post("/login")
async def login(request: Request) -> dict[str, str]:
    request.state.session["user"] = "demo"
    return {"status": "logged_in"}
```

The Challenge 2 deliverable is this middleware, finished, with tests.

### 5.3 Django versus FastAPI session-store comparison

| Aspect                       | Django                                       | FastAPI                                  |
|------------------------------|----------------------------------------------|------------------------------------------|
| Built-in?                    | Yes — `django.contrib.sessions`              | No — Starlette cookie-based only        |
| Redis backend                | `django.core.cache.backends.redis.RedisCache`| Build via custom middleware              |
| Lines of code (yours)        | ~10 in `settings.py`                         | ~50 (the middleware above)               |
| Sliding TTL                  | `SESSION_SAVE_EVERY_REQUEST=True`            | Add `expire` call in middleware          |
| Cookie security              | `SESSION_COOKIE_SECURE`, `_HTTPONLY`, etc.   | `set_cookie(secure=True, httponly=True)` |
| Server-side revoke           | `request.session.flush()`                    | `await r.delete(f"session:{sid}")`        |

Django wins on "lines of code I have to write"; FastAPI wins on "explicit control over what the middleware does". Neither is better; pick the framework for the rest of the service and the session backend follows.

## 6. The trade-off you should be able to defend

By the end of this week, you should be able to walk a code reviewer through the cache architecture in five sentences:

1. "We use Redis 7 with `maxmemory 2gb` and `maxmemory-policy allkeys-lru`. The TTLs are short enough that eviction is rare; LRU is the safe-default that handles the edge cases."
2. "Every cached value has a TTL. The default is 60 seconds; the popular-articles list is 30; the rendered pages are 1 hour with tag-based invalidation."
3. "Invalidation is tag-based for rendered pages, event-driven on entity writes, and TTL on everything else. The map is in `README.md`."
4. "The popular-articles endpoint uses request coalescing — one `asyncio.Future` per in-flight key — to prevent the stampede. Lower-traffic endpoints rely on XFetch with `beta=1.0` and `delta` set to the loader's measured latency."
5. "Sessions are in the same Redis instance, logical db 2, TTL 30 minutes with sliding renewal. We can revoke a session in a single `DEL`."

That paragraph is the artefact of this week. The code is the evidence; the paragraph is the understanding.

## 7. The seven-bullet summary

1. A cache stampede is the moment N concurrent misses for the same just-expired key all start their own rebuilds; the database receives N times the load. The shape is a 1-to-3-second period of elevated latencies that resolves on its own.
2. Request coalescing (single-flight) bounds rebuild concurrency at one per key per worker. Implementation: an `asyncio.Future` registry keyed by the cache key.
3. Cross-worker coalescing uses a Redis lock with `SET lock NX EX 10`. The non-lock-holders poll the cache for a few seconds and fall back to running the loader if it never appears.
4. Probabilistic early expiration (Vattani 2015, XFetch) refreshes the cache *before* expiry with a probability that climbs as expiry approaches. The formula is `t - delta * beta * log(rand()) >= expiry`. Optimal `beta` is 1.0.
5. Redis is the canonical session store. The cookie carries only the session ID; the contents live in Redis under `session:{id}` with TTL equal to the session lifetime.
6. Django: `SESSION_ENGINE = "django.contrib.sessions.backends.cache"` plus a Redis-backed cache alias. `SESSION_SAVE_EVERY_REQUEST=True` for sliding TTL.
7. FastAPI: build a `BaseHTTPMiddleware` that reads the session ID from a cookie, hydrates the dict from Redis, attaches to `request.state.session`, writes changes back on response.

## Reading for the week ahead

- The [Stack Overflow caching post](https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/) by Nick Craver — a real production architecture's caching playbook. Read it now that you have the vocabulary; it will read differently than it would have on Monday.
- The [Facebook "Scaling Memcache at Facebook" paper (NSDI 2013)](https://www.usenix.org/conference/nsdi13/technical-sessions/presentation/nishtala). The "lease" mechanism in section 3.2 is Facebook's answer to the stampede problem — a different shape from XFetch and worth knowing.
- The [`redis-py` connection-pool source](https://github.com/redis/redis-py/blob/master/redis/connection.py). 600 lines. The pool is what your `redis.from_url` returns under the covers.

This is the last lecture of the week. The remainder is exercises, challenges, and the mini-project. The benchmark numbers from Challenge 1 are the artefact that makes the week's work measurable — produce them, and put them in the commit message.
