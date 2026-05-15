"""
Exercise 3 — FastAPI middleware for tenant context and RLS-aware DB sessions.

Time:   ~1.5 hours.
Goal:   Wire the tenant-resolver dependency, the SET LOCAL pattern, and
        the RLS-protected query into a small FastAPI app. Run two requests
        with different X-Tenant-ID headers and confirm each request sees
        only its tenant's articles, even though the application SQL has
        no `WHERE tenant_id = ...` clause.

Run:
    # Terminal 1: start the app.
    uvicorn exercise_03_fastapi_tenant_middleware:app --reload --port 8011

    # Terminal 2: send requests with different tenant headers.
    # Look up the seeded tenant UUIDs first:
    psql -d cc_w11 -c "SELECT id, slug FROM tenants"

    # Then:
    ACME=<acme-uuid-here>
    GLOBEX=<globex-uuid-here>

    curl -s -H "X-Tenant-ID: $ACME" http://localhost:8011/articles | jq
    curl -s -H "X-Tenant-ID: $GLOBEX" http://localhost:8011/articles | jq

    # Each request returns only the tenant's articles.

Prerequisites:
    - Exercises 1 and 2 have run; RLS is enabled with FORCE.
    - The application role `crunchreader_app` exists.

Cited:
    - https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/
    - https://www.postgresql.org/docs/current/sql-set.html
    - https://magicstack.github.io/asyncpg/current/

The TASK comments below mark prompts you should answer in SOLUTIONS.md.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]

try:
    from fastapi import Depends, FastAPI, Header, HTTPException
except ImportError:  # pragma: no cover
    Depends = None  # type: ignore[assignment]
    FastAPI = None  # type: ignore[assignment, misc]
    Header = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment, misc]

try:
    from pydantic import BaseModel, ConfigDict
except ImportError:  # pragma: no cover
    BaseModel = object  # type: ignore[assignment, misc]
    ConfigDict = dict  # type: ignore[assignment, misc]


logger = logging.getLogger("tenant_middleware_exercise")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


APP_DSN = os.environ.get(
    "CC_W11_APP_DSN",
    "postgresql://crunchreader_app:Crunch_Pro_W11_pw@localhost:5432/cc_w11",
)


# ---------------------------------------------------------------------------
# Pydantic v2 models
# ---------------------------------------------------------------------------


class Article(BaseModel):  # type: ignore[misc]
    """Article as exposed in the API. Note: no tenant_id field.

    The article belongs to *the current tenant*, by construction. Exposing
    tenant_id on the wire would be confusing — the client cannot pick which
    tenant to read; the header decides.
    """

    model_config = ConfigDict(from_attributes=True)  # type: ignore[call-arg]

    id: int
    title: str
    body: str
    author: str
    published_at: str


class ArticleCreate(BaseModel):  # type: ignore[misc]
    """Request body for POST /articles."""

    title: str
    body: str
    author: str


# ---------------------------------------------------------------------------
# Application lifespan: open and close the pool.
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: "FastAPI") -> AsyncIterator[None]:  # type: ignore[name-defined]
    """Open the asyncpg pool on startup; close on shutdown."""
    if asyncpg is None:  # pragma: no cover
        raise RuntimeError("asyncpg not installed")
    pool = await asyncpg.create_pool(dsn=APP_DSN, min_size=2, max_size=10)
    app.state.pool = pool
    logger.info("opened asyncpg pool")
    try:
        yield
    finally:
        await pool.close()
        logger.info("closed asyncpg pool")


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def get_tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> uuid.UUID:  # type: ignore[name-defined]
    """Resolve the tenant from the X-Tenant-ID header.

    In production, this would read a JWT claim or a subdomain. Header
    form is the simplest demo.
    """
    try:
        return uuid.UUID(x_tenant_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="invalid tenant id") from exc  # type: ignore[name-defined]


async def get_db(
    tenant_id: uuid.UUID = Depends(get_tenant_id),  # type: ignore[name-defined]
) -> AsyncIterator["asyncpg.Connection"]:
    """Acquire a connection, open a transaction, SET LOCAL the tenant ID.

    Key invariants:

    1. The transaction is opened BEFORE SET LOCAL — SET LOCAL requires
       an active transaction; outside one, it is a no-op (a silent
       multi-tenancy bug).

    2. We use `SET LOCAL`, not `SET`. The tenant context dies when the
       transaction commits; the next request that picks up this pooled
       connection starts with a fresh, unset state.
    """
    pool: "asyncpg.Pool" = app.state.pool  # noqa: F821 (resolved at runtime)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SET LOCAL app.current_tenant = $1", str(tenant_id)
            )
            yield conn


# TASK 1: rewrite `get_db` so the transaction is NOT opened explicitly
# (i.e. just `pool.acquire()` and `conn.execute("SET LOCAL ...")` without
# the `async with conn.transaction()`). Document in SOLUTIONS.md what
# breaks: the SET LOCAL has no transaction to be local to; the parameter
# is set at session scope; the next request inherits it. (This is the
# bug Lecture 2 §3.1 warned about.)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


app = FastAPI(lifespan=lifespan, title="C16 W11 Multi-Tenant Demo")  # type: ignore[misc]


@app.get("/articles", response_model=list[Article])  # type: ignore[misc]
async def list_articles(
    db: "asyncpg.Connection" = Depends(get_db),  # type: ignore[name-defined]
) -> list[Article]:
    """List articles for the current tenant.

    Notice: no `WHERE tenant_id = ...` in the SQL. The RLS policy
    supplies the filter.
    """
    rows = await db.fetch(
        """
        SELECT id, title, body, author, published_at::text AS published_at
          FROM articles
         ORDER BY published_at DESC, id DESC
         LIMIT 100
        """
    )
    return [Article(**dict(r)) for r in rows]


@app.get("/articles/{article_id}", response_model=Article)  # type: ignore[misc]
async def read_article(
    article_id: int,
    db: "asyncpg.Connection" = Depends(get_db),  # type: ignore[name-defined]
) -> Article:
    """Read a single article by id. The RLS policy enforces tenant scope."""
    row = await db.fetchrow(
        """
        SELECT id, title, body, author, published_at::text AS published_at
          FROM articles
         WHERE id = $1
        """,
        article_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="article not found")  # type: ignore[name-defined]
    return Article(**dict(row))


@app.post("/articles", response_model=Article, status_code=201)  # type: ignore[misc]
async def create_article(
    payload: ArticleCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),  # type: ignore[name-defined]
    db: "asyncpg.Connection" = Depends(get_db),  # type: ignore[name-defined]
) -> Article:
    """Create an article for the current tenant.

    We pass tenant_id explicitly to the INSERT because the column is
    NOT NULL. The RLS WITH CHECK clause validates that the new row's
    tenant_id matches `current_setting('app.current_tenant')` — so an
    attempt to write a row for a different tenant fails-closed.
    """
    row = await db.fetchrow(
        """
        INSERT INTO articles (tenant_id, title, body, author)
        VALUES ($1, $2, $3, $4)
        RETURNING id, title, body, author, published_at::text AS published_at
        """,
        tenant_id,
        payload.title,
        payload.body,
        payload.author,
    )
    assert row is not None  # INSERT...RETURNING always returns a row
    return Article(**dict(row))


# TASK 2: write a test (with httpx) that POSTs to /articles as Tenant A,
# captures the returned article id, then GETs /articles/{id} as Tenant B
# and confirms a 404 is returned. Record the test in SOLUTIONS.md.


# TASK 3: add a `/healthz` endpoint that returns `{"status": "ok"}`.
# Does it require an X-Tenant-ID header? Why or why not? Document
# the reasoning in SOLUTIONS.md. (Hint: the answer is "no" — health
# checks are not tenant-scoped — and the implementation uses a
# different dependency that does not call get_tenant_id.)


if __name__ == "__main__":
    # Allow `python3 exercise-03-...py` to print a hint about how to run.
    print("Run with: uvicorn exercise_03_fastapi_tenant_middleware:app --reload --port 8011")
