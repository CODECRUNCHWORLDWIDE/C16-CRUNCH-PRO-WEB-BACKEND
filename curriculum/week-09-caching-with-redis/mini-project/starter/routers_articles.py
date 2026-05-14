"""Router skeleton for /articles routes.

Copy into crunchcache/routers/articles.py. The five routes are stubbed;
fill in the bodies. Each route has comments naming the cache key it uses,
the TTL it applies, and the invalidation it publishes (for write routes).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

# from crunchcache.schemas import ArticleIn, ArticleOut

logger = logging.getLogger("crunchcache.routers.articles")

router = APIRouter(prefix="/articles", tags=["articles"])


# ---------------------------------------------------------------------------
# Helpers — dependency-injected access to app state
# ---------------------------------------------------------------------------


async def get_redis_from_state(request: Request) -> Any:
    """Pull the Redis client off app.state."""
    return request.app.state.redis


async def get_bus_from_state(request: Request) -> Any:
    """Pull the InvalidationBus off app.state."""
    return request.app.state.bus


async def get_settings_from_state(request: Request) -> Any:
    """Pull the Settings off app.state."""
    return request.app.state.settings


# ---------------------------------------------------------------------------
# GET /articles
# ---------------------------------------------------------------------------


@router.get("")
async def list_articles(
    author_id: int | None = None,
    r: Any = Depends(get_redis_from_state),
    settings: Any = Depends(get_settings_from_state),
) -> list[dict[str, Any]]:
    """List articles, optionally filtered by author_id.

    Cache key:  v1:articles:filter:author:{id}  (or v1:articles:all if no filter)
    TTL:        settings.filter_ttl
    Strategy:   cache-aside with degradation

    TODO: implement the cache-aside read; the loader runs the SQL query.
    """
    raise NotImplementedError("list_articles is a TODO")


# ---------------------------------------------------------------------------
# GET /articles/{id}
# ---------------------------------------------------------------------------


@router.get("/{article_id}")
async def get_article(
    article_id: int,
    r: Any = Depends(get_redis_from_state),
    settings: Any = Depends(get_settings_from_state),
) -> dict[str, Any]:
    """Get a single article.

    Cache key:  v1:article:{id}
    TTL:        settings.article_ttl
    Strategy:   cache-aside with degradation
    404:        when the database returns no row

    TODO: implement.
    """
    raise NotImplementedError("get_article is a TODO")


# ---------------------------------------------------------------------------
# GET /articles/popular
# ---------------------------------------------------------------------------


@router.get("/popular")
async def popular_articles(
    request: Request,
    limit: int = 10,
    r: Any = Depends(get_redis_from_state),
    settings: Any = Depends(get_settings_from_state),
) -> list[dict[str, Any]]:
    """Top N articles by views.

    Cache key:  v1:articles:popular:{limit}
    TTL:        settings.popular_ttl
    Strategy:   cache-aside + request coalescing (CoalescingCache)
                100 concurrent misses -> 1 DB query

    TODO: use the CoalescingCache instance attached to app.state
    (you'll instantiate it in lifespan and store it on app.state.coalescing).
    """
    raise NotImplementedError("popular_articles is a TODO")


# ---------------------------------------------------------------------------
# POST /articles/{id}/view  — write path, publishes invalidation
# ---------------------------------------------------------------------------


@router.post("/{article_id}/view")
async def record_view(
    article_id: int,
    r: Any = Depends(get_redis_from_state),
    bus: Any = Depends(get_bus_from_state),
) -> dict[str, int]:
    """Increment view counter; invalidate related caches.

    DB: UPDATE articles SET views = views + 1 WHERE id = ?
    Returns: {"views": new_count}

    Invalidations to publish:
        - key:     v1:article:{id}
        - pattern: v1:articles:popular:*

    TODO: implement the UPDATE, then publish the two invalidations.
    Do not block on the publishes — publish-and-continue.
    """
    raise NotImplementedError("record_view is a TODO")


# ---------------------------------------------------------------------------
# PATCH /articles/{id}  — write path, publishes invalidation
# ---------------------------------------------------------------------------


@router.patch("/{article_id}")
async def update_article(
    article_id: int,
    # body: ArticleIn,
    body: dict[str, Any],  # placeholder until you wire ArticleIn
    r: Any = Depends(get_redis_from_state),
    bus: Any = Depends(get_bus_from_state),
) -> dict[str, Any]:
    """Update an article.

    DB: UPDATE articles SET ... WHERE id = ?
    Returns: the updated article (re-fetched from the DB).

    Invalidations to publish:
        - key:     v1:article:{id}
        - pattern: v1:articles:popular:*
        - key:     v1:articles:filter:author:{author_id}  (both old and new
                   if the author_id changed)

    TODO: implement. Note the dual-publish on author change — failing to
    invalidate the old author's filter is a stale-cache bug.
    """
    raise NotImplementedError("update_article is a TODO")
