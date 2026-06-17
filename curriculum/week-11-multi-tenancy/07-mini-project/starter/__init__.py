"""crunchtenant — multi-tenant FastAPI service starter.

Modules:
    settings      — env-driven config.
    schemas       — Pydantic v2 models.
    deps          — FastAPI dependencies (tenant, db, rate limit, admin).
    cache         — tenant-prefixed Redis wrapper.
    rate_limit    — Lua-scripted token-bucket rate limiter.
    routers_articles — the per-tenant article CRUD.
    routers_admin    — the admin onboarding/suspend endpoints.
"""
