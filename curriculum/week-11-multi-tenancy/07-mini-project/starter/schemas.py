"""Pydantic v2 models for the crunchtenant API.

All models use `model_config = ConfigDict(from_attributes=True)` so they
can be hydrated from asyncpg.Record (which behaves like a Mapping).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

try:
    from pydantic import BaseModel, ConfigDict, Field
except ImportError:  # pragma: no cover
    BaseModel = object  # type: ignore[assignment, misc]
    ConfigDict = dict  # type: ignore[assignment, misc]
    Field = lambda *a, **kw: None  # type: ignore[assignment, misc]


Tier = Literal["free", "paid", "enterprise"]


class Tenant(BaseModel):  # type: ignore[misc]
    """A tenant record (the row in the `tenants` table)."""

    model_config = ConfigDict(from_attributes=True)  # type: ignore[call-arg]

    id: uuid.UUID
    slug: str
    name: str
    tier: Tier
    suspended_at: datetime | None
    created_at: datetime


class TenantCreate(BaseModel):  # type: ignore[misc]
    """Request body for POST /admin/tenants."""

    slug: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9-]*$")  # type: ignore[misc]
    name: str = Field(..., min_length=1, max_length=255)  # type: ignore[misc]
    tier: Tier = "free"


class Article(BaseModel):  # type: ignore[misc]
    """An article as exposed in the API.

    Notice the absence of a `tenant_id` field. The article belongs to the
    *current tenant*; surfacing tenant_id on the wire is confusing.
    """

    model_config = ConfigDict(from_attributes=True)  # type: ignore[call-arg]

    id: int
    title: str
    body: str
    author: str
    published_at: str


class ArticleCreate(BaseModel):  # type: ignore[misc]
    """Request body for POST /articles."""

    title: str = Field(..., min_length=1, max_length=255)  # type: ignore[misc]
    body: str = Field(..., min_length=1)  # type: ignore[misc]
    author: str = Field(..., min_length=1, max_length=255)  # type: ignore[misc]


class RateLimitPolicy(BaseModel):  # type: ignore[misc]
    """A per-(tenant, endpoint) rate-limit policy."""

    model_config = ConfigDict(from_attributes=True)  # type: ignore[call-arg]

    capacity: int
    refill_rate: float


class TenantStatusResponse(BaseModel):  # type: ignore[misc]
    """Response from admin suspend/unsuspend endpoints."""

    tenant_id: uuid.UUID
    suspended: bool
