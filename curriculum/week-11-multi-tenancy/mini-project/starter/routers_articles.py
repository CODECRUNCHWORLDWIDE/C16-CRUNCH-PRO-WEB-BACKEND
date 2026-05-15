"""The tenant-scoped articles router.

Every endpoint depends on `enforce_rate_limit` (consumes a token) and
`get_db` (opens an RLS-protected DB session). The application SQL has no
`WHERE tenant_id = ...` clauses; the policy supplies the filter.
"""

from __future__ import annotations

import uuid
from typing import Any

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]

try:
    from fastapi import APIRouter, Depends, HTTPException
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment, misc]
    Depends = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment, misc]

from .cache import TenantCache
from .deps import enforce_rate_limit, get_db, get_tenant_cache, get_tenant_id
from .schemas import Article, ArticleCreate


router = APIRouter(prefix="/articles", tags=["articles"])  # type: ignore[misc]


@router.get("", response_model=list[Article])  # type: ignore[misc]
async def list_articles(
    _: None = Depends(enforce_rate_limit),  # type: ignore[name-defined]
    db: "asyncpg.Connection" = Depends(get_db),  # type: ignore[name-defined]
) -> list[Article]:
    """List the current tenant's articles. RLS supplies the filter."""
    rows = await db.fetch(
        """
        SELECT id, title, body, author, published_at::text AS published_at
          FROM articles
         ORDER BY published_at DESC, id DESC
         LIMIT 100
        """
    )
    return [Article(**dict(r)) for r in rows]


@router.get("/{article_id}", response_model=Article)  # type: ignore[misc]
async def read_article(
    article_id: int,
    _: None = Depends(enforce_rate_limit),  # type: ignore[name-defined]
    db: "asyncpg.Connection" = Depends(get_db),  # type: ignore[name-defined]
    cache: TenantCache = Depends(get_tenant_cache),  # type: ignore[name-defined]
) -> Article:
    """Read one article. Tenant-prefixed cache for warm reads."""
    cache_key = f"article:{article_id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        # In production, parse the JSON; for the starter, a marker is enough.
        pass  # fall through to DB read; replace with json.loads(cached) etc.

    row = await db.fetchrow(
        """
        SELECT id, title, body, author, published_at::text AS published_at
          FROM articles
         WHERE id = $1
        """,
        article_id,
    )
    if row is None:
        # Could be "article does not exist" OR "belongs to another tenant".
        # The 404 is the right response for both — distinguishing leaks info.
        raise HTTPException(status_code=404, detail="article not found")  # type: ignore[name-defined]

    article = Article(**dict(row))
    await cache.set(cache_key, article.model_dump_json(), ex=60)
    return article


@router.post("", response_model=Article, status_code=201)  # type: ignore[misc]
async def create_article(
    payload: ArticleCreate,
    _: None = Depends(enforce_rate_limit),  # type: ignore[name-defined]
    tenant_id: uuid.UUID = Depends(get_tenant_id),  # type: ignore[name-defined]
    db: "asyncpg.Connection" = Depends(get_db),  # type: ignore[name-defined]
    cache: TenantCache = Depends(get_tenant_cache),  # type: ignore[name-defined]
) -> Article:
    """Create an article for the current tenant.

    The tenant_id parameter is passed explicitly because the column is
    NOT NULL. The RLS WITH CHECK clause validates the value matches the
    current setting — so a forged tenant_id is rejected.
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
    assert row is not None
    article = Article(**dict(row))
    # Invalidate any cached list response (the list moved).
    await cache.invalidate_pattern("article:list:*")
    return article


@router.delete("/{article_id}", status_code=204)  # type: ignore[misc]
async def delete_article(
    article_id: int,
    _: None = Depends(enforce_rate_limit),  # type: ignore[name-defined]
    db: "asyncpg.Connection" = Depends(get_db),  # type: ignore[name-defined]
    cache: TenantCache = Depends(get_tenant_cache),  # type: ignore[name-defined]
) -> None:
    """Delete an article. RLS prevents cross-tenant deletes silently."""
    result: Any = await db.execute("DELETE FROM articles WHERE id = $1", article_id)
    # asyncpg returns a status string like "DELETE 1"; parse the count.
    deleted = int(result.split()[-1]) if isinstance(result, str) else 0
    if deleted == 0:
        raise HTTPException(status_code=404, detail="article not found")  # type: ignore[name-defined]
    await cache.delete(f"article:{article_id}")
    await cache.invalidate_pattern("article:list:*")
