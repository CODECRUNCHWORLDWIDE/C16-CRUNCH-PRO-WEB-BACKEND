"""FastAPI app skeleton for crunchcache.

Wires the lifespan, the router, and the global state (Redis client + bus).
Copy this into crunchcache/main.py.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

# Local imports — adjust to your package layout.
# from crunchcache.cache import get_redis, close_redis
# from crunchcache.invalidation import InvalidationBus
# from crunchcache.settings import get_settings
# from crunchcache.routers.articles import router as articles_router


logger = logging.getLogger("crunchcache.main")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------
#
# The Redis client and the invalidation bus are attached to app.state in the
# lifespan. Route handlers read them via FastAPI dependencies (see the
# routers_articles.py starter).


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the Redis client and the invalidation bus on startup; stop on shutdown."""
    # settings = get_settings()
    # app.state.settings = settings
    # app.state.redis = await get_redis(settings.redis_url)
    # app.state.bus = InvalidationBus(app.state.redis, settings.redis_invalidate_channel)
    # await app.state.bus.start()
    logger.info("crunchcache startup complete")
    try:
        yield
    finally:
        # await app.state.bus.stop()
        # await close_redis()
        logger.info("crunchcache shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Factory: returns a fresh FastAPI app.

    The factory shape makes testing easier — each test can build its own app
    with its own dependency overrides.
    """
    app = FastAPI(
        title="crunchcache",
        version="0.1.0",
        description=(
            "C16 Week 9 mini-project. A measure-then-fix cache layer for "
            "a deliberately slow article-list endpoint backed by SQLite."
        ),
        lifespan=lifespan,
    )

    # app.include_router(articles_router)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Process-level health probe.

        TODO: implement properly — ping Redis, query SQLite, return the
        Health Pydantic model.
        """
        return {"status": "ok", "redis_ok": True, "db_ok": True}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)  # noqa: S104
