"""Pydantic v2 schemas for the /search endpoint.

The SearchResponse shape is intentionally identical across the three
backends — the calling client should not have to care whether Postgres,
OpenSearch, or Meilisearch produced the hits. The `_source` field on each
hit records which backend served it (useful for the relevance harness;
optional for normal clients).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    BaseModel = object  # type: ignore[assignment, misc]
    Field = lambda *a, **kw: None  # type: ignore[assignment]  # noqa: E731


BackendName = Literal["postgres", "opensearch", "meili"]


class SearchHit(BaseModel):
    """A single search result. Shape stable across backends."""

    id: int
    title: str
    author: str
    published_at: datetime
    score: float = Field(description="Backend-specific relevance score.")
    snippet: str | None = Field(default=None, description="Highlighted body excerpt.")
    backend: BackendName = Field(description="Which backend produced this hit.")


class SearchResponse(BaseModel):
    """The body of GET /search."""

    query: str
    backend: BackendName
    total: int = Field(description="Estimated total matching documents.")
    limit: int
    offset: int
    took_ms: float = Field(description="Backend-side processing time in milliseconds.")
    hits: list[SearchHit]


class ArticleCreate(BaseModel):
    """Input shape for POST /articles. Subset of the full Article model."""

    title: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)
    author: str = Field(min_length=1, max_length=200)
    tags: list[str] = Field(default_factory=list)


class Article(ArticleCreate):
    """Full Article model, returned by GET /articles/{id}."""

    id: int
    published_at: datetime


class IndexEvent(BaseModel):
    """Payload published to articles:changed for the workers to consume."""

    id: int
    op: Literal["upsert", "delete"]
