"""The admin router: tenant onboarding, suspension, unsuspension.

Endpoints are gated by `require_admin` (bearer-token check). The admin
endpoints connect to the database WITHOUT setting `app.current_tenant`,
because the operations are cross-tenant by nature. The admin role
(the `crunchreader_app` role, in this starter) has SELECT/INSERT/UPDATE
on `tenants` and `rate_limits` — not the per-tenant article tables.

Real production: use a separate role for the admin connection, possibly
one with BYPASSRLS for the rare cross-tenant query. The simple version
in this starter is sufficient for the homework.
"""

from __future__ import annotations

import uuid
from typing import cast

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]

try:
    from fastapi import APIRouter, Depends, HTTPException, Request
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment, misc]
    Depends = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment, misc]
    Request = None  # type: ignore[assignment, misc]

from .deps import SETTINGS, require_admin
from .schemas import Tenant, TenantCreate, TenantStatusResponse


router = APIRouter(prefix="/admin", tags=["admin"])  # type: ignore[misc]


# Default endpoints to populate rate-limit policies for at onboarding time.
DEFAULT_ENDPOINTS: list[str] = [
    "/articles",
    "/articles/*",
]


@router.post("/tenants", response_model=Tenant, status_code=201)  # type: ignore[misc]
async def create_tenant(
    payload: TenantCreate,
    request: "Request",
    _: None = Depends(require_admin),  # type: ignore[name-defined]
) -> Tenant:
    """Create a tenant + default rate-limit rows, atomically."""
    pool: "asyncpg.Pool" = request.app.state.pool
    capacity, refill_rate = SETTINGS.tier_default(payload.tier)
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO tenants (slug, name, tier)
                    VALUES ($1, $2, $3)
                    RETURNING id, slug, name, tier, suspended_at, created_at
                    """,
                    payload.slug,
                    payload.name,
                    payload.tier,
                )
            except asyncpg.exceptions.UniqueViolationError as exc:
                raise HTTPException(  # type: ignore[name-defined]
                    status_code=409, detail="slug already exists"
                ) from exc

            assert row is not None
            new_id = cast(uuid.UUID, row["id"])

            # Default per-endpoint rate-limit rows. The tenant inherits
            # the tier's defaults; can be overridden later.
            for endpoint in DEFAULT_ENDPOINTS:
                await conn.execute(
                    """
                    INSERT INTO rate_limits (tenant_id, endpoint, capacity, refill_rate)
                    VALUES ($1, $2, $3, $4)
                    """,
                    new_id,
                    endpoint,
                    capacity,
                    refill_rate,
                )

    return Tenant(**dict(row))


@router.post(
    "/tenants/{tenant_id}/suspend",
    response_model=TenantStatusResponse,
)  # type: ignore[misc]
async def suspend_tenant(
    tenant_id: uuid.UUID,
    request: "Request",
    _: None = Depends(require_admin),  # type: ignore[name-defined]
) -> TenantStatusResponse:
    """Set tenants.suspended_at = now()."""
    pool: "asyncpg.Pool" = request.app.state.pool
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE tenants SET suspended_at = now() WHERE id = $1 AND suspended_at IS NULL",
            tenant_id,
        )
    updated = int(result.split()[-1]) if isinstance(result, str) else 0
    if updated == 0:
        raise HTTPException(  # type: ignore[name-defined]
            status_code=404, detail="tenant not found or already suspended"
        )
    return TenantStatusResponse(tenant_id=tenant_id, suspended=True)


@router.post(
    "/tenants/{tenant_id}/unsuspend",
    response_model=TenantStatusResponse,
)  # type: ignore[misc]
async def unsuspend_tenant(
    tenant_id: uuid.UUID,
    request: "Request",
    _: None = Depends(require_admin),  # type: ignore[name-defined]
) -> TenantStatusResponse:
    """Clear tenants.suspended_at."""
    pool: "asyncpg.Pool" = request.app.state.pool
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE tenants SET suspended_at = NULL WHERE id = $1 AND suspended_at IS NOT NULL",
            tenant_id,
        )
    updated = int(result.split()[-1]) if isinstance(result, str) else 0
    if updated == 0:
        raise HTTPException(  # type: ignore[name-defined]
            status_code=404, detail="tenant not found or not suspended"
        )
    return TenantStatusResponse(tenant_id=tenant_id, suspended=False)
