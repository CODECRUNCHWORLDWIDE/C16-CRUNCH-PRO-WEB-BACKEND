"""
crunchexports.main — the FastAPI application entry point.

Run with:

    fastapi dev crunchexports/main.py
    # or
    uvicorn crunchexports.main:app --reload --port 8000

The lifespan context manager:

    - Opens an ARQ pool (`create_pool`) and stows it on `app.state.arq`.
    - Opens an independent redis.asyncio client for the SSE relay.
    - Ensures the export directory exists.

Cited:
    - https://fastapi.tiangolo.com/advanced/events/
    - https://arq-docs.helpmanual.io/
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, status

try:
    from arq import create_pool  # type: ignore[import-not-found]
    from arq.connections import RedisSettings  # type: ignore[import-not-found]

    HAS_ARQ = True
except ImportError:  # pragma: no cover
    create_pool = None  # type: ignore[assignment]
    RedisSettings = None  # type: ignore[assignment,misc]
    HAS_ARQ = False

try:
    import redis.asyncio as redis_async  # type: ignore[import-not-found]

    HAS_REDIS = True
except ImportError:  # pragma: no cover
    redis_async = None  # type: ignore[assignment]
    HAS_REDIS = False

from .schemas import ExportAccepted, ExportRequest, ExportStatus
from .settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Wire up the ARQ pool and the Redis Pub/Sub client; tear them down on exit."""
    settings = get_settings()
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=settings.log_level)

    if HAS_ARQ and create_pool is not None and RedisSettings is not None:
        app.state.arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    else:
        app.state.arq = None

    if HAS_REDIS and redis_async is not None:
        app.state.redis = redis_async.from_url(
            settings.redis_url, decode_responses=True
        )
    else:
        app.state.redis = None

    try:
        yield
    finally:
        if app.state.arq is not None:
            await app.state.arq.aclose()
        if app.state.redis is not None:
            await app.state.redis.aclose()


app = FastAPI(
    title="crunchexports",
    description=(
        "A FastAPI service that exports CSV reports via ARQ and streams "
        "progress to the browser over Server-Sent Events."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    """Process-level health probe.

    Returns 200 if FastAPI is up and the ARQ pool is reachable.
    """
    pool = request.app.state.arq
    if pool is None:
        return {"status": "degraded", "reason": "arq pool unavailable"}
    try:
        await pool.ping()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"redis ping failed: {exc}") from exc
    return {"status": "ok"}


# Route registration: import the routers and include them on the app.
# The starter ships the SSE router only; you implement exports.py and
# downloads.py as part of the mini-project.
try:
    from .routers_sse import router as sse_router  # type: ignore[import-not-found]

    app.include_router(sse_router)
except ImportError:  # pragma: no cover — routers_sse is in the starter
    logger.warning("routers_sse not importable; SSE endpoint missing")


# A placeholder POST /exports to keep the starter runnable. Replace with
# crunchexports.routers.exports as you build out the mini-project.
@app.post(
    "/exports",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ExportAccepted,
)
async def enqueue_export_placeholder(body: ExportRequest, request: Request) -> ExportAccepted:
    """Placeholder enqueue; the real version lives in routers/exports.py."""
    pool = request.app.state.arq
    if pool is None:
        raise HTTPException(status_code=503, detail="arq pool unavailable")
    import uuid

    job_id = str(uuid.uuid4())
    await pool.enqueue_job(
        "run_export",
        job_id,
        body.model_dump(mode="json"),
        _job_id=job_id,
    )
    return ExportAccepted(
        job_id=job_id,
        stream_url=f"/sse/exports/{job_id}",
        poll_url=f"/exports/{job_id}",
    )


@app.get("/exports/{job_id}", response_model=ExportStatus)
async def get_status_placeholder(job_id: str) -> ExportStatus:
    """Placeholder status endpoint; replace with the persisted version.

    The full implementation:
      - Looks up the ARQ result via pool.get_job_result.
      - Reads the latest progress event from Redis.
      - Returns 'done' with a download_url once the file exists.
    """
    return ExportStatus(
        job_id=job_id,
        status="pending",
        progress=0.0,
        created_at=datetime.now(timezone.utc),
    )
