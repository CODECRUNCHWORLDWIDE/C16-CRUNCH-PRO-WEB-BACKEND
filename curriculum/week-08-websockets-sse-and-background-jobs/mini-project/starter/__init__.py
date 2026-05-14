"""crunchexports — FastAPI + ARQ + SSE export service.

The starter ships these modules. Copy into your ``crunchexports/`` package
and fill in the TODOs as you build out the mini-project.

    schemas.py        — Pydantic models (complete)
    settings.py       — pydantic-settings config (complete)
    progress.py       — Redis Pub/Sub helpers (complete)
    worker.py         — ARQ task + WorkerSettings (complete)
    main.py           — FastAPI app + lifespan + placeholder routes
    routers_sse.py    — the SSE relay endpoint (complete)

You write:

    routers/exports.py    — the real POST /exports + GET /exports/{id}
    routers/downloads.py  — GET /exports/{id}/download
    data_sources.py       — the row iterator the worker calls
    tests/conftest.py     — fakeredis fixture + TestClient
    tests/test_routes.py  — happy path + 422 + 404
    tests/test_sse.py     — httpx.AsyncClient.stream over the SSE endpoint
    tests/test_worker.py  — arq.worker.Worker.run_check
    static/index.html     — the demo page
    README.md             — operational runbook
"""

__version__ = "0.1.0"
