# Lecture 1 — The capstone architecture: Django for the admin, FastAPI for the public, Postgres and Redis underneath

> *Every backend you will work on in your first three years has the same shape: a thing that humans use to administer the data, a thing that the public uses to consume the data, a database where the data lives, and a cache that makes the second thing fast. The capstone has that shape. The shape is not novel; the shape is what every shipped backend converges on. What is novel — what is the work of Week 12 — is making the four parts compose without a leak.*

## 1.1 The architecture in one diagram

The capstone has four processes and two stateful services. They live in one repository, deploy to one platform-as-a-service account, and address each other across a single private network the platform gives you for free.

```text
                +--------------------+         +--------------------+
                |  Browser (admin)   |         |  Public API client |
                |  Django session    |         |  Bearer token      |
                +---------+----------+         +---------+----------+
                          |                              |
                          | HTTPS                        | HTTPS / WSS
                          v                              v
                +---------+----------+         +---------+----------+
                |  Django web        |         |  FastAPI web       |
                |  Gunicorn + Uvicorn|         |  Uvicorn           |
                |  Port 8000         |         |  Port 8001         |
                |  /admin            |         |  /api, /ws         |
                +---------+----------+         +---------+----------+
                          |                              |
                          +--------------+---------------+
                                         |
                                         v
                              +---------------------+
                              |  Postgres 16        |
                              |  app role + RLS     |
                              |  tsvector + GIN     |
                              +----------+----------+
                                         ^
                                         |
                              +----------+----------+
                              |  Redis 7            |
                              |  cache + pub/sub    |
                              |  rate limit buckets |
                              +----------+----------+
                                         ^
                                         |
                              +----------+----------+
                              |  ARQ worker         |
                              |  Same image, --worker|
                              +---------------------+
```

Four processes: Django web, FastAPI web, ARQ worker, and the platform's edge proxy (which the platform manages; we do not run it). Two stateful services: Postgres and Redis. One container image, three entry points (the `web` command for Django, the `api` command for FastAPI, the `worker` command for ARQ); the platform decides which process gets which entry point.

The Fly.io path, for example, declares three "process groups" inside one `fly.toml`, each with a different start command, each scaled independently. The Render path declares three "services" in one `render.yaml`. The Railway path declares three "services" in one `railway.json`. Same shape, three syntaxes.

## 1.2 Why two web frameworks

The question every interviewer asks first about the capstone is "why two frameworks; isn't that twice the maintenance?" The honest answer is that it is the right division of labour for the constraints.

**Django owns the admin.** The Django admin is forty engineering hours of free dashboard. `python manage.py startapp content; python manage.py makemigrations; python manage.py migrate; python manage.py createsuperuser` and you have a fully functional, permissions-aware, audit-logged dashboard that lets non-engineers manage the data. Building the equivalent in FastAPI would cost weeks; the closest FastAPI ecosystem offering is [sqladmin](https://aminalaee.dev/sqladmin/), which is competent but not Django-admin-competent. The admin is the lowest-traffic surface in the service and the one that needs the most features per hour of engineering; Django is the right tool.

**FastAPI owns the public API.** The public API has three traits that Django serves less well: async end-to-end (because of the WebSocket and the per-request asyncpg calls), Pydantic v2 for the contracts, and OpenAPI generated from the type hints. Django can do all three — `django-ninja` exists, `daphne` serves async views, `drf-spectacular` generates OpenAPI — but FastAPI does them by default, with less ceremony, on a smaller dependency footprint. The public API is the highest-traffic surface and the one that benefits from the throughput; FastAPI is the right tool.

The objection "two frameworks doubles the code" misreads the boundary. The Django side is models and migrations and the admin; the FastAPI side is async handlers and Pydantic schemas and the WebSocket. They share the database; they do not share the application code. The total line count is *lower* than a single-framework version because each side is doing the thing its framework was designed for. Cite the [FastAPI mention of Django](https://fastapi.tiangolo.com/alternatives/#django) and the [Django Channels documentation](https://channels.readthedocs.io/) — both ecosystems acknowledge the trade-off explicitly.

## 1.3 The boundary between Django and FastAPI

Both processes connect to the same Postgres database. Both see the same tables. Both honour the same RLS policies. The boundary is not at the data layer; the boundary is at the code layer. The contract is:

1. **Django owns DDL.** Migrations live in Django. `python manage.py migrate` is the only tool that changes the schema. The FastAPI side reads the resulting schema; it does not declare its own models. There is no separate Alembic; there is no schema race.
2. **FastAPI uses the schema, not the models.** The FastAPI handlers use asyncpg directly. They do not import Django models. The reason is the async story: Django ORM is mostly-sync (the async support is improving but not at parity yet); asyncpg is fully async. The handlers query the tables Django created; they do not go through Django's ORM to do it.
3. **Pydantic v2 is the FastAPI side's contract.** Every request body is a Pydantic v2 `BaseModel`. Every response body is a Pydantic v2 `BaseModel`. The OpenAPI spec FastAPI generates is the spec the public API ships with.
4. **The auth tokens are issued by Django.** Django Auth issues a session cookie for the admin and a bearer token (JWT) for the public API. The bearer token includes the `tenant_id` claim. The FastAPI side validates the token and reads the claim; it does not re-issue tokens.

The result: one Postgres schema, one set of migrations, one source of truth, two processes that consume it differently. The complexity is real but bounded. The bound is the line of code where one side imports something the other side defined; that line is the architecture violation.

## 1.4 The Postgres substrate

The database is Postgres 16. The schema is the union of W2 (models), W4 (indexes), W10 (tsvectors), and W11 (RLS). The headline characteristics:

- **One app role**: `crunchreader_app`. Not a superuser. Not `BYPASSRLS`. The Django connection uses this role; the FastAPI connection uses this role; the ARQ worker uses this role. The migrations run as `postgres` (superuser, locally) or as the platform's managed-Postgres admin (on Fly.io / Render / Railway); the application processes never connect as the admin.
- **`FORCE ROW LEVEL SECURITY`** on every tenant-scoped table: `articles`, `tags`, `revisions`, `comments`, `subscriptions`. Each table has a policy: `tenant_id = current_setting('app.current_tenant')::uuid`. Each connection sets `app.current_tenant` at the start of every transaction via `SET LOCAL`.
- **A `tsvector` column** on `articles`. A `GIN` index on the column. An `UPDATE` trigger that recomputes the vector on every `INSERT` and `UPDATE` of the `title` or `body` columns. The search endpoint queries `WHERE search_vector @@ websearch_to_tsquery('english', $1) ORDER BY ts_rank(search_vector, websearch_to_tsquery('english', $1)) DESC`. See the [Postgres FTS chapter](https://www.postgresql.org/docs/current/textsearch.html).
- **Composite primary keys** `(tenant_id, id)` on every tenant-scoped table. The `id` alone is unique within the tenant; with the `tenant_id` prefix it is unique across the database. This makes the table's natural physical layout follow the access pattern (tenant-first), which improves cache locality for any tenant-scoped scan. See the [Postgres documentation on primary keys](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-PRIMARY-KEYS).
- **A `tenants` table** outside the RLS regime. The `tenants` row defines a tenant; it is read by the auth flow before the tenant context is set. The `tenants` table has no RLS policy because there is no tenant context yet at the point it is queried.

## 1.5 The Redis layer

Redis 7 is one process, one instance, multiple uses:

1. **Read-through cache** on `GET /api/articles/{id}`. Key shape: `tenant:{tenant_id}:cache:article:{article_id}`. Value: the serialised Pydantic model. TTL: 300 seconds with a small jitter to avoid synchronised expiry storms. The cache miss path reads from Postgres, writes to Redis with `SET ... NX EX 300`, returns the row. The `NX` prevents two concurrent misses from both writing.
2. **Pub/sub** for the WebSocket fan-out. Channel shape: `tenant:{tenant_id}:events`. When an article is inserted or updated, the FastAPI handler publishes an `article.created` or `article.updated` message to the tenant-scoped channel. The WebSocket handler for that tenant subscribes to the channel and forwards each message to its connected clients. See the [Redis pub/sub commands](https://redis.io/docs/latest/commands/?group=pubsub).
3. **Rate-limit buckets**. Key shape: `ratelimit:tenant:{tenant_id}:endpoint:{path}`. The bucket is a token-bucket implemented with `INCR` and `EXPIRE`; the FastAPI dependency consumes a token per request and returns 429 with `Retry-After` when the bucket is empty. The W9 pattern, lifted forward.
4. **ARQ queue**. ARQ is a small library that puts task queues on top of Redis. The capstone uses ARQ for the search-index refresh, the email-on-signup task, and the post-update analytics increment. The W6 / W8 pattern, lifted forward. See the [ARQ documentation](https://arq-docs.helpmanual.io/).

The single Redis process serves all four roles. The keys do not collide because each role has a different prefix.

## 1.6 The ARQ worker

The third process is the ARQ worker. It runs from the same container image; its entry point is `arq app.worker.WorkerSettings`. The settings file declares the tasks (`update_search_index`, `send_signup_email`, `bump_view_count`) and the Redis connection.

Tasks are enqueued from either web process:

```python
from arq.connections import ArqRedis, create_pool, RedisSettings

# In the FastAPI handler for POST /api/articles
async def create_article(...) -> ArticleResponse:
    # ... insert the article into Postgres ...
    redis: ArqRedis = await create_pool(RedisSettings(host="redis"))
    await redis.enqueue_job("update_search_index", article_id, tenant_id)
    return ArticleResponse(...)
```

The task picks it up from the queue, runs to completion, retries on failure with exponential backoff, and dead-letters after three attempts. The worker process is identical in image to the web processes; only the entry point differs. Cite [`arq.connections`](https://arq-docs.helpmanual.io/#arq.connections.RedisSettings) and [the ARQ task lifecycle](https://arq-docs.helpmanual.io/#defining-tasks-and-queues).

## 1.7 The container image

One `Dockerfile`. Multi-stage. The stages are:

```dockerfile
# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS runtime
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY . .
RUN python -m py_compile $(find . -name '*.py' -not -path './.venv/*')
EXPOSE 8000 8001
CMD ["./entrypoint.sh", "web"]
```

The `entrypoint.sh` script reads the first argument and dispatches:

```bash
#!/bin/sh
set -e
case "$1" in
  web)
    exec gunicorn -k uvicorn.workers.UvicornWorker mtch.django_app.asgi:application --bind 0.0.0.0:8000 --workers 2
    ;;
  api)
    exec uvicorn mtch.fastapi_app.main:app --host 0.0.0.0 --port 8001 --workers 2
    ;;
  worker)
    exec arq mtch.worker.WorkerSettings
    ;;
  migrate)
    exec python manage.py migrate --noinput
    ;;
  *)
    echo "Usage: $0 {web|api|worker|migrate}"
    exit 1
    ;;
esac
```

One image, four entry points. The platform calls `web`, `api`, `worker` as long-running processes; `migrate` is a release-time one-shot. The Fly.io path uses [release_command](https://fly.io/docs/reference/configuration/#the-deploy-section) to invoke `migrate` on every deploy.

Cite the [Docker multi-stage build documentation](https://docs.docker.com/build/building/multi-stage/) and the [Gunicorn deployment documentation](https://docs.gunicorn.org/en/stable/deploy.html).

## 1.8 The configuration model

Twelve-Factor: config in environment variables. The capstone reads ten environment variables; they are documented in `docs/configuration.md` and validated at startup by a Pydantic v2 `Settings` model.

```python
from pydantic import Field, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: PostgresDsn = Field(..., description="postgres://app:pass@host:5432/db")
    redis_url: RedisDsn = Field(..., description="redis://host:6379/0")
    secret_key: SecretStr = Field(..., min_length=32)
    debug: bool = Field(default=False)
    allowed_hosts: list[str] = Field(default_factory=lambda: ["*"])
    fastapi_port: int = Field(default=8001, ge=1, le=65535)
    django_port: int = Field(default=8000, ge=1, le=65535)
    sentry_dsn: str = Field(default="")
    log_level: str = Field(default="INFO")
    rate_limit_default: int = Field(default=60, ge=1)


settings = Settings()  # raises ValidationError on missing/invalid env
```

The startup fails fast if any required variable is missing or malformed. The `database_url` and `redis_url` are validated as DSN strings (Pydantic v2 has built-in types for both, see the [Pydantic networking docs](https://docs.pydantic.dev/latest/api/networks/)).

Secrets live in the platform's secret store, not in `.env`. The `.env` file is a development convenience; in production, `fly secrets set DATABASE_URL=...` writes the variable straight to the Fly machine's environment.

## 1.9 The tenant resolution path

Every request starts with the tenant question: who is asking. The capstone supports three answers; the FastAPI dependency picks the first one that resolves.

1. **Subdomain.** `acme.multitenantcontenthub.fly.dev` → tenant `acme`. The platform's DNS routes the request to the same machine; the FastAPI app sees the `Host` header and parses the subdomain.
2. **Header.** `X-Tenant: acme` on the request. The service-to-service path; the calling service knows which tenant it is acting on behalf of.
3. **JWT claim.** `tenant_id` in the bearer-token claims. The end-user path; the token was issued by the Django auth flow and the tenant was bound to the user at login time.

The dependency code:

```python
from typing import Annotated
from fastapi import Depends, Header, HTTPException, Request
from uuid import UUID

async def resolve_tenant(
    request: Request,
    x_tenant: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> UUID:
    # 1. Subdomain
    host = request.headers.get("host", "")
    subdomain = host.split(".")[0] if "." in host else ""
    if subdomain and subdomain not in {"www", "api", "admin"}:
        tenant = await tenant_by_slug(subdomain)
        if tenant is not None:
            return tenant.id
    # 2. Header
    if x_tenant:
        tenant = await tenant_by_slug(x_tenant)
        if tenant is not None:
            return tenant.id
    # 3. JWT
    if authorization and authorization.startswith("Bearer "):
        claims = decode_jwt(authorization.removeprefix("Bearer "))
        if "tenant_id" in claims:
            return UUID(claims["tenant_id"])
    raise HTTPException(status_code=400, detail="Tenant not resolvable")
```

The dependency runs on every public route. The tenant UUID it returns is passed to the database session, which calls `SET LOCAL app.current_tenant = '<uuid>'` at the start of each transaction. From that point on, the RLS policy filters every query for the right tenant automatically.

```mermaid
flowchart TD
  A["Incoming request"] --> B{"Subdomain present and known"}
  B -->|Yes| C["Tenant resolved from subdomain"]
  B -->|No| D{"X-Tenant header present"}
  D -->|Yes| E["Tenant resolved from header"]
  D -->|No| F{"Bearer JWT with tenant id claim"}
  F -->|Yes| G["Tenant resolved from JWT claim"]
  F -->|No| H["400 Tenant not resolvable"]
```
*The FastAPI dependency tries subdomain, then header, then JWT claim, before giving up.*

## 1.10 The auth flow

The Django side handles signup, login, and token issuance. The FastAPI side handles token validation.

- **Signup**: `POST /admin/signup` (Django view). Creates a `Tenant` row, a `User` row bound to the tenant, and the admin's `User` permissions. Returns the login URL.
- **Login**: `POST /admin/login` (Django view). Verifies the password via Django Auth; sets the session cookie; returns the admin dashboard URL.
- **API token**: `POST /admin/api-tokens` (Django view). Issues a JWT signed with `settings.secret_key`. Claims: `sub` (the user ID), `tenant_id` (the tenant the user belongs to), `exp` (24 hours from now), `iat` (now). The user copies the token from the admin and uses it for the public API.
- **API request**: `Authorization: Bearer <token>` on every public-API request. The FastAPI dependency `resolve_tenant` validates the signature, reads the `tenant_id` claim, and proceeds.

The JWT secret is the `SECRET_KEY` Django uses for session signing. One secret, two uses. The token is signed with HS256 (HMAC-SHA-256), which is fine for the symmetric case where Django issues and FastAPI validates with the same key. If a third party needed to validate tokens, we would switch to RS256 (RSA signatures) and ship the public key; the capstone does not need that.

Cite [PyJWT](https://pyjwt.readthedocs.io/) for the encoding/decoding library and [the Django authentication docs](https://docs.djangoproject.com/en/5.1/topics/auth/default/) for the user model.

## 1.11 The WebSocket path

The live-update channel is one WebSocket endpoint per tenant: `wss://api.multitenantcontenthub.fly.dev/ws?token=<jwt>`. The FastAPI WebSocket handler:

1. Accepts the connection.
2. Validates the JWT (passed as a query parameter because browsers cannot set custom headers on WebSocket connections; this is a documented WebSocket-API limitation, see the [WHATWG WebSocket spec](https://websockets.spec.whatwg.org/)).
3. Resolves the tenant from the JWT claim.
4. Subscribes to the Redis channel `tenant:{tenant_id}:events`.
5. Forwards every message from the channel to the WebSocket client.
6. Closes when the client disconnects or when the JWT expires.

```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str) -> None:
    try:
        claims = decode_jwt(token)
    except jwt.PyJWTError:
        await websocket.close(code=1008)
        return
    tenant_id = UUID(claims["tenant_id"])
    await websocket.accept()
    redis = await create_redis_pool()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"tenant:{tenant_id}:events")
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"].decode())
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(f"tenant:{tenant_id}:events")
        await pubsub.close()
```

The publisher side is one line in the article-create handler:

```python
await redis.publish(
    f"tenant:{tenant_id}:events",
    ArticleEvent(type="article.created", id=article_id, title=title).model_dump_json(),
)
```

Cite the [FastAPI WebSockets tutorial](https://fastapi.tiangolo.com/advanced/websockets/) and the [Redis pub/sub documentation](https://redis.io/docs/latest/develop/interact/pubsub/).

## 1.12 The search path

The search path is the W10 work, integrated. Every `articles` row has a `search_vector tsvector` column. A `BEFORE INSERT OR UPDATE` trigger keeps it in sync with the `title` and `body` columns. A `GIN` index on the column makes the lookup fast.

The endpoint:

```python
@app.get("/api/search")
async def search(
    q: str,
    tenant_id: Annotated[UUID, Depends(resolve_tenant)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    limit: int = 20,
) -> list[ArticleSummary]:
    rows = await db.fetch(
        """
        SELECT id, title, ts_rank(search_vector, websearch_to_tsquery('english', $1)) AS rank,
               ts_headline('english', body, websearch_to_tsquery('english', $1)) AS snippet
          FROM articles
         WHERE search_vector @@ websearch_to_tsquery('english', $1)
         ORDER BY rank DESC
         LIMIT $2
        """,
        q,
        limit,
    )
    return [ArticleSummary(id=r["id"], title=r["title"], rank=r["rank"], snippet=r["snippet"]) for r in rows]
```

The `tenant_id` is not in the `WHERE` clause. It does not need to be. The RLS policy on the `articles` table filters the rows for us before the query plan even sees them. This is the W11 invariant in action: the application code is unaware of the multi-tenancy at the query site; the database enforces it.

Cite the [Postgres FTS chapter](https://www.postgresql.org/docs/current/textsearch.html#TEXTSEARCH-INTRO) and the [GIN index documentation](https://www.postgresql.org/docs/current/gin.html).

## 1.13 The cache path

The read-through cache wraps `GET /api/articles/{id}`. The pattern:

```python
@app.get("/api/articles/{article_id}")
async def get_article(
    article_id: UUID,
    tenant_id: Annotated[UUID, Depends(resolve_tenant)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> ArticleResponse:
    key = f"tenant:{tenant_id}:cache:article:{article_id}"
    cached = await redis.get(key)
    if cached:
        return ArticleResponse.model_validate_json(cached)
    row = await db.fetchrow(
        "SELECT id, title, body, created_at FROM articles WHERE id = $1",
        article_id,
    )
    if row is None:
        raise HTTPException(status_code=404)
    response = ArticleResponse(**dict(row))
    # SET NX EX: don't overwrite (avoids cache stampede); 300s TTL.
    await redis.set(key, response.model_dump_json(), nx=True, ex=300)
    return response
```

Three lines for the cache hit; six for the cache miss-and-fill. The `tenant_id` is in the key prefix, so the cache is partitioned by tenant; the RLS policy on the database is the safety net for the (rare) case where the cache layer is bypassed.

The invalidation path is in the write handler: after `INSERT` or `UPDATE`, `DEL tenant:{tenant_id}:cache:article:{article_id}`. After bulk updates (the rare case), `SCAN MATCH tenant:{tenant_id}:cache:article:*` and `DEL` the matched keys.

Cite the [Redis `SET` command](https://redis.io/docs/latest/commands/set/) (note the `NX` and `EX` flags) and the [Redis `SCAN` command](https://redis.io/docs/latest/commands/scan/).

## 1.14 The rate-limit path

The W11 rate limiter, integrated. A FastAPI dependency consumes one token per request:

```python
async def rate_limit(
    request: Request,
    tenant_id: Annotated[UUID, Depends(resolve_tenant)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    endpoint = request.url.path
    key = f"ratelimit:tenant:{tenant_id}:{endpoint}"
    bucket = await redis.incr(key)
    if bucket == 1:
        await redis.expire(key, 60)
    if bucket > settings.rate_limit_default:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )
```

Add `Depends(rate_limit)` to every public-API route. The 429 response is the standard; the `Retry-After` header lets the client back off. Cite [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585.html), which defines 429.

## 1.15 The composition: one request, end to end

Putting the pieces together. A `POST /api/articles` request from a public client:

1. **TLS termination** at the platform edge. The platform proxies to the FastAPI process on its internal network.
2. **FastAPI dependency: `resolve_tenant`**. Reads the bearer token; validates it; extracts `tenant_id`. Time: ~0.5 ms.
3. **FastAPI dependency: `rate_limit`**. `INCR` the tenant's bucket; if over, 429. Time: ~0.5 ms.
4. **FastAPI dependency: `get_db`**. Acquires a connection from the asyncpg pool; opens a transaction; runs `SET LOCAL app.current_tenant = '<uuid>'`. Time: ~1 ms.
5. **Pydantic v2 validation** of the request body. Returns 422 with the validation error if the body is malformed. Time: ~0.2 ms for a small payload.
6. **Handler body**. `INSERT INTO articles (...) VALUES (...) RETURNING id, created_at`. The RLS policy's `WITH CHECK` clause enforces that the inserted `tenant_id` matches the session's `app.current_tenant`. Time: ~3 ms.
7. **ARQ enqueue**. `redis.enqueue_job("update_search_index", article_id, tenant_id)`. Time: ~1 ms.
8. **Pub/sub publish**. `redis.publish("tenant:<uuid>:events", event_json)`. Time: ~0.5 ms.
9. **Response serialisation**. Pydantic `model_dump_json`. Time: ~0.2 ms.
10. **Commit and return**. The transaction commits; the connection returns to the pool. Time: ~1 ms.

```mermaid
sequenceDiagram
  participant Client
  participant FastAPI
  participant Postgres
  participant Redis
  participant Worker as "ARQ worker"
  Client->>FastAPI: Create article request
  FastAPI->>FastAPI: Resolve tenant and check rate limit
  FastAPI->>Postgres: Insert article row
  Postgres-->>FastAPI: Return id and timestamp
  FastAPI->>Redis: Enqueue search index job
  FastAPI->>Redis: Publish article created event
  FastAPI-->>Client: Return 201 response
  Redis-->>Worker: Deliver queued job
  Worker->>Postgres: Update search vector
```
*One create-article request, followed end to end through the web process, the database, the cache bus, and the background worker.*

End-to-end target at the ninety-fifth percentile: under 15 ms on the deployed service for a 1 KB article. The capstone's `docs/sla.md` makes the bound formal.

The same request, observed from the client of a different process: the ARQ worker dequeues `update_search_index`, runs `UPDATE articles SET search_vector = to_tsvector('english', title || ' ' || body) WHERE id = $1`, completes within 30 ms of the request. The WebSocket client subscribed to the tenant's channel receives the `article.created` event within 50 ms of the request. Both numbers are tracked in the test suite's latency assertions.

## 1.16 The cost of every dependency

The capstone runs on three free-tier resources. Each has a ceiling.

- **Postgres on Fly.io free tier**: 3 GB storage, 256 MB RAM, shared CPU. Enough for the capstone's tens of thousands of articles. Past 3 GB or past tens of thousands of QPS, the move is to Fly's paid Postgres (or to an external managed Postgres). Document the move in `docs/scaling.md`; do not make it this week.
- **Redis on Upstash via Fly**: 256 MB cache, 10 000 commands per day on the truly free tier; the paid tier kicks in around $0.20/day for the capstone's likely load. The capstone caches small payloads and rate-limit buckets; the byte count stays well under 256 MB.
- **Python process on Fly free tier**: one machine, 256 MB RAM, shared CPU, 3 GB egress per month. Enough for the capstone. The egress is the only ceiling worth watching; static-asset hosting (which the capstone does not need) would burn it fast.

Document the free-tier limits in `docs/free-tier-limits.md`. The honesty about the ceiling is a craft signal. Cite the [Fly.io pricing page](https://fly.io/docs/about/pricing/) and the [Upstash Redis pricing page](https://upstash.com/pricing).

## 1.17 What W12 lecture 1 leaves you with

By the end of this lecture you should be able to draw the architecture diagram from memory, identify every process and every stateful service, name the boundary between Django and FastAPI, and locate every prior week's contribution in the diagram. Tomorrow's lecture is the deploy: how to take the local diagram and put it on the public internet.

## References

- [FastAPI — Tutorial](https://fastapi.tiangolo.com/tutorial/)
- [FastAPI — Alternatives, Inspiration and Comparisons](https://fastapi.tiangolo.com/alternatives/)
- [FastAPI — WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [Django — Authentication](https://docs.djangoproject.com/en/5.1/topics/auth/)
- [Django — Deployment checklist](https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/)
- [PostgreSQL — Row Level Security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [PostgreSQL — Text Search](https://www.postgresql.org/docs/current/textsearch.html)
- [PostgreSQL — Primary Keys](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-PRIMARY-KEYS)
- [Redis — Commands](https://redis.io/docs/latest/commands/)
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/interact/pubsub/)
- [ARQ — Documentation](https://arq-docs.helpmanual.io/)
- [Pydantic v2 — Networking types](https://docs.pydantic.dev/latest/api/networks/)
- [Docker — Multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Gunicorn — Deployment](https://docs.gunicorn.org/en/stable/deploy.html)
- [Twelve-Factor App](https://12factor.net/)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585.html)
