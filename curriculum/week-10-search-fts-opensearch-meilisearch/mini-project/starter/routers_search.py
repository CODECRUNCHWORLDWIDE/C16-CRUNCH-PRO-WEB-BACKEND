"""GET /search router.

Dispatches based on the `backend` query parameter; falls back to the default
backend configured in settings. Each backend implementation returns a
SearchResponse-shaped dict; this router wraps it in the Pydantic model.
"""

from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, Depends, HTTPException, Query
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment, misc]
    Depends = lambda f: f  # type: ignore[assignment]  # noqa: E731
    HTTPException = Exception  # type: ignore[assignment, misc]
    Query = lambda *a, **kw: None  # type: ignore[assignment]  # noqa: E731

from .clients import search_meili, search_opensearch, search_postgres
from .schemas import BackendName, SearchHit, SearchResponse
from .settings import Settings, get_settings


if APIRouter is not None:  # pragma: no branch
    router = APIRouter(prefix="/search", tags=["search"])
else:  # pragma: no cover
    router = None  # type: ignore[assignment]


async def search_dispatch(
    query: str,
    backend: BackendName,
    limit: int,
    offset: int,
    pg_pool: Any,
    os_client: Any,
    meili_client: Any,
    settings: Settings,
) -> SearchResponse:
    """Route to the chosen backend; package the response."""
    if backend == "postgres":
        raw = await search_postgres(pg_pool, query, limit, offset)
    elif backend == "opensearch":
        raw = await search_opensearch(os_client, settings.opensearch_index, query, limit, offset)
    elif backend == "meili":
        raw = await search_meili(meili_client, settings.meili_index, query, limit, offset)
    else:  # pragma: no cover - Literal type narrows this
        raise HTTPException(status_code=400, detail=f"unknown backend: {backend}")

    hits = [SearchHit(**h) for h in raw["hits"]]
    return SearchResponse(
        query=query,
        backend=backend,
        total=raw["total"],
        limit=limit,
        offset=offset,
        took_ms=raw["took_ms"],
        hits=hits,
    )


# ---------------------------------------------------------------------------
# The actual FastAPI route
# ---------------------------------------------------------------------------


if router is not None:  # pragma: no branch

    @router.get("", response_model=SearchResponse)
    async def search_endpoint(
        q: str = Query(min_length=1, max_length=500, description="The search query."),
        backend: BackendName | None = Query(default=None, description="Override the default backend."),
        limit: int = Query(default=25, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=10_000),
        settings: Settings = Depends(get_settings),
    ) -> SearchResponse:
        """Run a search.

        TODO(student): wire the dependency-provided pg_pool, os_client, and
        meili_client. For the starter, this endpoint will not run without
        those dependencies provided via Depends() in your main app wiring.
        """
        chosen = backend or settings.default_backend  # type: ignore[assignment]
        # The actual clients are injected by the application's startup.
        # This starter raises until you wire them in.
        raise NotImplementedError(
            "Wire pg_pool, os_client, and meili_client via FastAPI Depends in main.py, "
            "then call search_dispatch from here."
        )
