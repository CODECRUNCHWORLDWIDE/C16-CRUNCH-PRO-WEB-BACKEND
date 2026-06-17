"""FastAPI dependencies for the crunchtenant service.

Five dependencies:

    get_tenant_id    — resolve UUID from X-Tenant-ID header.
    get_db           — acquire connection, open transaction, SET LOCAL.
    enforce_rate_limit — consume a token; raise 429 if depleted.
    require_admin    — bearer-token check for admin endpoints.
    get_tenant_cache — construct a TenantCache for the current request.

The dependencies compose in the expected order: rate_limit depends on
tenant_id; db depends on tenant_id; cache depends on tenant_id.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]

try:
    from fastapi import Depends, Header, HTTPException, Request
except ImportError:  # pragma: no cover
    Depends = None  # type: ignore[assignment]
    Header = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment, misc]
    Request = None  # type: ignore[assignment, misc]

from .cache import TenantCache
from .rate_limit import RateLimit, current_tokens, try_consume
from .settings import load_settings


SETTINGS = load_settings()


async def get_tenant_id(
    request: "Request",
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),  # type: ignore[name-defined]
) -> uuid.UUID:
    """Resolve the tenant UUID from the X-Tenant-ID header.

    Stores the tenant_id on `request.state` so downstream middleware
    and the rate limiter can find it without re-parsing.
    """
    try:
        tenant_id = uuid.UUID(x_tenant_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="invalid tenant id") from exc  # type: ignore[name-defined]

    # Look up the tenant; reject suspended tenants here.
    pool: "asyncpg.Pool" = request.app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, suspended_at, tier FROM tenants WHERE id = $1",
            tenant_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="tenant not found")  # type: ignore[name-defined]
    if row["suspended_at"] is not None:
        raise HTTPException(status_code=402, detail="tenant is suspended")  # type: ignore[name-defined]

    request.state.tenant_id = tenant_id
    request.state.tier = row["tier"]
    return tenant_id


async def get_db(
    request: "Request",
    tenant_id: uuid.UUID = Depends(get_tenant_id),  # type: ignore[name-defined]
) -> AsyncIterator["asyncpg.Connection"]:
    """Acquire a connection; open a transaction; SET LOCAL the tenant.

    Critical invariants:

    1. Transaction is opened BEFORE SET LOCAL. SET LOCAL outside a
       transaction is a no-op (Postgres emits a WARNING).
    2. SET LOCAL is used (not SET). When the transaction commits, the
       parameter is gone; the next pooled request starts fresh.
    """
    pool: "asyncpg.Pool" = request.app.state.pool
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SET LOCAL app.current_tenant = $1", str(tenant_id)
            )
            yield conn


async def enforce_rate_limit(
    request: "Request",
    tenant_id: uuid.UUID = Depends(get_tenant_id),  # type: ignore[name-defined]
) -> None:
    """Consume a rate-limit token for the current (tenant, endpoint).

    Raise 429 if the bucket is empty. Adds `Retry-After` header derived
    from `current_tokens` and the refill rate.
    """
    endpoint = request.url.path
    tier: str = request.state.tier
    capacity, refill_rate = SETTINGS.tier_default(tier)
    limit = RateLimit(capacity=capacity, refill_rate=refill_rate)

    redis = request.app.state.redis
    allowed = await try_consume(redis, tenant_id, endpoint, limit)
    if not allowed:
        # Approximate retry time: (1 - current) / refill_rate seconds.
        current = await current_tokens(redis, tenant_id, endpoint, limit)
        retry_after = max(1, int((1.0 - current) / max(refill_rate, 0.001)))
        raise HTTPException(  # type: ignore[name-defined]
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


def get_tenant_cache(
    request: "Request",
    tenant_id: uuid.UUID = Depends(get_tenant_id),  # type: ignore[name-defined]
) -> TenantCache:
    """Construct a TenantCache for the current request."""
    return TenantCache(redis=request.app.state.redis, tenant_id=tenant_id)


def require_admin(
    authorization: str = Header(..., alias="Authorization"),  # type: ignore[name-defined]
) -> None:
    """Bearer-token admin check.

    Production would replace this with an IAM check (JWT claim, etc).
    The hard-coded token is fine for the homework.
    """
    expected = f"Bearer {SETTINGS.admin_token}"
    if authorization != expected:
        raise HTTPException(status_code=403, detail="admin token required")  # type: ignore[name-defined]
