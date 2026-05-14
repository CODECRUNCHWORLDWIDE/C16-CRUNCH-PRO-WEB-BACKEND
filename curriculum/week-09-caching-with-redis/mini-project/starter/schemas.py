"""Pydantic v2 schemas for crunchcache.

ArticleIn   — body accepted by PATCH /articles/{id}.
ArticleOut  — response for the GET routes.
Health      — response for GET /health.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArticleIn(BaseModel):
    """The body of PATCH /articles/{id}.

    All fields are optional; at least one must be provided. The model_validator
    enforces that; extra="forbid" rejects unknown fields with 422.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=50_000)
    author_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ArticleIn":
        if self.title is None and self.body is None and self.author_id is None:
            raise ValueError("PATCH body must contain at least one field")
        return self


class ArticleOut(BaseModel):
    """The response shape for article reads."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    author_id: int
    views: int
    created_at: datetime


class Health(BaseModel):
    """The response shape for GET /health."""

    status: str = Field(description="'ok' if all upstreams reachable.")
    redis_ok: bool
    db_ok: bool


class InvalidationMessage(BaseModel):
    """One message on the Pub/Sub invalidation channel.

    Exactly one of (key, tag, pattern) is set per message.
    """

    model_config = ConfigDict(extra="forbid")

    key: str | None = Field(default=None, description="A single cache key to DEL.")
    tag: str | None = Field(default=None, description="A tag whose set to sweep.")
    pattern: str | None = Field(default=None, description="A SCAN MATCH pattern to sweep.")

    @model_validator(mode="after")
    def exactly_one(self) -> "InvalidationMessage":
        provided = sum(x is not None for x in (self.key, self.tag, self.pattern))
        if provided != 1:
            raise ValueError("Exactly one of key, tag, pattern must be provided")
        return self


def article_to_out(article: dict[str, Any]) -> ArticleOut:
    """Convert a database row (dict) to ArticleOut. Used by the routes."""
    return ArticleOut.model_validate(article)
