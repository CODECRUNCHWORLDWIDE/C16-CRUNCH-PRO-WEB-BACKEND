# Week 7 — Resources

All free and publicly accessible. FastAPI 0.115.x, Pydantic 2.9.x, Starlette 0.40.x, Python 3.12+. Pin FastAPI docs at the unversioned root (`fastapi.tiangolo.com/`), which always resolves to the latest stable. Pydantic docs pin at `/latest/`.

## Required reading (work through the week)

### FastAPI — the official tutorial, in order

The FastAPI tutorial is the single best entry point. It is short, runnable, and covers the surface this week needs. Work through these sections, in this order, alongside the lectures:

- **First steps** — the minimal `app = FastAPI()`, `@app.get("/")`, what `uvicorn` does:
  <https://fastapi.tiangolo.com/tutorial/first-steps/>
- **Path parameters** — typed segments in the URL; validation, conversion, ordering:
  <https://fastapi.tiangolo.com/tutorial/path-params/>
- **Query parameters** — defaults, optional, required, types:
  <https://fastapi.tiangolo.com/tutorial/query-params/>
- **Request body** — the Pydantic `BaseModel` as a single function parameter:
  <https://fastapi.tiangolo.com/tutorial/body/>
- **Query parameters and string validations** — `Annotated[str, Query(...)]`, the modern form:
  <https://fastapi.tiangolo.com/tutorial/query-params-str-validations/>
- **Path parameters and numeric validations** — `Annotated[int, Path(ge=1)]`:
  <https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/>
- **Body — Fields** — adding `Field(...)` metadata inside the Pydantic model:
  <https://fastapi.tiangolo.com/tutorial/body-fields/>
- **Body — Nested models** — lists, dicts, recursive structures:
  <https://fastapi.tiangolo.com/tutorial/body-nested-models/>
- **Response model — Return type** — the contract on the way out:
  <https://fastapi.tiangolo.com/tutorial/response-model/>
- **Extra models** — separating `UserIn`, `UserOut`, `UserDB` (the canonical example of "two schemas per resource"):
  <https://fastapi.tiangolo.com/tutorial/extra-models/>
- **Response status code** — `status_code=201`, `204`, `202`:
  <https://fastapi.tiangolo.com/tutorial/response-status-code/>
- **Handling errors** — `HTTPException`, custom handlers, `RequestValidationError`:
  <https://fastapi.tiangolo.com/tutorial/handling-errors/>
- **Dependencies** — the full chapter; the most important single chapter this week:
  <https://fastapi.tiangolo.com/tutorial/dependencies/>
- **Sub-dependencies** — dependencies that depend on dependencies:
  <https://fastapi.tiangolo.com/tutorial/dependencies/sub-dependencies/>
- **Dependencies with yield** — setup/teardown for database sessions:
  <https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/>
- **Security — first steps** — `OAuth2PasswordBearer` as a FastAPI dependency:
  <https://fastapi.tiangolo.com/tutorial/security/first-steps/>
- **Get current user** — wiring the token to a user object:
  <https://fastapi.tiangolo.com/tutorial/security/get-current-user/>
- **Testing** — `TestClient` and the async variant:
  <https://fastapi.tiangolo.com/tutorial/testing/>
- **Async tests** — `pytest-asyncio` with `httpx.AsyncClient`:
  <https://fastapi.tiangolo.com/advanced/async-tests/>

### Pydantic v2 — required sections

- **Welcome to Pydantic** — start here for orientation:
  <https://docs.pydantic.dev/latest/>
- **Models** — `BaseModel`, the field types, `model_config`:
  <https://docs.pydantic.dev/latest/concepts/models/>
- **Fields** — `Field(...)` and all its keyword arguments:
  <https://docs.pydantic.dev/latest/concepts/fields/>
- **Validators** — `field_validator`, `model_validator`, the `mode` parameter (`before`, `after`, `wrap`):
  <https://docs.pydantic.dev/latest/concepts/validators/>
- **Serialization** — `model_dump`, `model_dump_json`, `model_serializer`, `field_serializer`:
  <https://docs.pydantic.dev/latest/concepts/serialization/>
- **Types — Standard library types** — what Pydantic handles natively (datetime, UUID, IPv4Address, etc.):
  <https://docs.pydantic.dev/latest/concepts/types/>
- **JSON Schema** — how Pydantic emits the schema FastAPI consumes for `/openapi.json`:
  <https://docs.pydantic.dev/latest/concepts/json_schema/>
- **Performance** — Pydantic v2 is built on `pydantic-core` (Rust); when this matters:
  <https://docs.pydantic.dev/latest/concepts/performance/>
- **Migration guide from v1 to v2** — read once; you will see legacy code:
  <https://docs.pydantic.dev/latest/migration/>

### Starlette — the ASGI toolkit FastAPI builds on

- **Starlette — Introduction**: <https://www.starlette.io/>
- **Requests** — `request.url`, `request.headers`, `request.json()`, `request.body()`:
  <https://www.starlette.io/requests/>
- **Responses** — `JSONResponse`, `HTMLResponse`, `RedirectResponse`, `StreamingResponse`:
  <https://www.starlette.io/responses/>
- **Middleware** — how `BaseHTTPMiddleware` and pure-ASGI middleware differ:
  <https://www.starlette.io/middleware/>
- **Background tasks** — `BackgroundTasks`, how they differ from Celery:
  <https://www.starlette.io/background/>
- **Lifespan** — the `lifespan` context manager for app-scoped resources:
  <https://www.starlette.io/lifespan/>

### ASGI

- **ASGI documentation** — the specification, in plain English:
  <https://asgi.readthedocs.io/en/latest/>
- **The ASGI specification (`main` document)** — `scope`, `receive`, `send`; the three protocol types:
  <https://asgi.readthedocs.io/en/latest/specs/main.html>
- **The HTTP and WebSocket sub-spec** — what `scope["type"]` can be:
  <https://asgi.readthedocs.io/en/latest/specs/www.html>
- **`uvicorn`** — the reference ASGI server we use:
  <https://www.uvicorn.org/>

### HTTP — the specs your API has to honour

- **RFC 9110 — HTTP Semantics** (June 2022; supersedes RFC 7231 for semantics):
  <https://datatracker.ietf.org/doc/html/rfc9110>
  - §9 Methods (GET, POST, PUT, PATCH, DELETE) — what each one *must* do
  - §15 Status Codes — the canonical 2xx/4xx/5xx list
  - §10.1 Authorization header — the prefix the auth dependency parses
- **RFC 7231 — HTTP/1.1 Semantics and Content** (still cited heavily; superseded by RFC 9110 but most online material refers to it):
  <https://datatracker.ietf.org/doc/html/rfc7231>
- **RFC 9112 — HTTP/1.1 syntax** — the wire format (for reference; we do not write this by hand here):
  <https://datatracker.ietf.org/doc/html/rfc9112>

### OpenAPI

- **OpenAPI 3.1.0 specification** — the format of the `/openapi.json` document FastAPI emits:
  <https://spec.openapis.org/oas/v3.1.0>
- **Swagger UI** — the interactive renderer at `/docs`:
  <https://swagger.io/tools/swagger-ui/>
- **ReDoc** — the alternative renderer at `/redoc`:
  <https://redocly.com/redoc/>

## FastAPI — the advanced sections to skim once

These are not week-7-required, but each one will save you an hour later in the program:

- **Path operation configuration** — `tags`, `summary`, `description`, `response_description`, `deprecated`:
  <https://fastapi.tiangolo.com/tutorial/path-operation-configuration/>
- **CORS** — the `CORSMiddleware` and the headers it sets:
  <https://fastapi.tiangolo.com/tutorial/cors/>
- **Bigger applications — multiple files** — `APIRouter` and the `include_router` pattern:
  <https://fastapi.tiangolo.com/tutorial/bigger-applications/>
- **Background tasks** — for tasks that fit in-process; we cover the contrast with Celery:
  <https://fastapi.tiangolo.com/tutorial/background-tasks/>
- **Lifespan events** — for app-scoped resources (database engine, cache pool, ML model):
  <https://fastapi.tiangolo.com/advanced/events/>
- **Middleware** — the FastAPI middleware ordering rules:
  <https://fastapi.tiangolo.com/tutorial/middleware/>
- **Custom OpenAPI** — when you need to mutate the generated document:
  <https://fastapi.tiangolo.com/advanced/extending-openapi/>

## Async and testing tools

- **`httpx`** — the modern, sync-and-async HTTP client; what we use to test FastAPI in-process:
  <https://www.python-httpx.org/>
- **`httpx.ASGITransport`** — call your ASGI app without a real network socket:
  <https://www.python-httpx.org/async/#calling-into-python-web-apps>
- **`pytest-asyncio`** — the async test runner; pin `asyncio_mode = "auto"` in `pyproject.toml`:
  <https://pytest-asyncio.readthedocs.io/en/latest/>
- **Python `asyncio` overview** — the standard library async primitives (skim, then return Week 8):
  <https://docs.python.org/3/library/asyncio.html>
- **`anyio`** — the structured-concurrency layer Starlette uses; `anyio.to_thread.run_sync` is the escape hatch for sync code in async handlers:
  <https://anyio.readthedocs.io/>

## Database layer (used lightly this week, deeply Week 8)

- **SQLAlchemy 2.0 — `async` extension** — what an async session looks like:
  <https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html>
- **`SQLModel`** — Pydantic-flavoured SQLAlchemy; the entrypoint for this week's challenge:
  <https://sqlmodel.tiangolo.com/>
- **`asyncpg`** — the fastest Postgres driver for async Python (referenced; not required this week):
  <https://magicstack.github.io/asyncpg/current/>

## The references worth bookmarking forever

- **The FastAPI source** — small, readable, you can pin it open in a tab:
  <https://github.com/fastapi/fastapi/tree/master/fastapi>
  Especially `routing.py`, `dependencies/utils.py`, `openapi/utils.py`.
- **The Starlette source** — even smaller:
  <https://github.com/encode/starlette/tree/master/starlette>
- **`uv`** — fast Python package and project manager from Astral; we use it in the mini-project:
  <https://docs.astral.sh/uv/>
- **`ruff`** — Python linter and formatter; FastAPI projects standardise on it:
  <https://docs.astral.sh/ruff/>
- **`mypy`** — strict-mode type checker; recommended for any FastAPI project that aims to ship:
  <https://mypy.readthedocs.io/>

## On the FastAPI / DRF choice

- **"Why I'm not using Django REST Framework anymore"** (and the inverse "why I came back") — search both. The honest answer is "use both, talking to one database, and choose per-endpoint", which is what this week builds toward.
- **FastAPI vs Flask vs Django comparison** (FastAPI's own page) — biased but accurate on the technical points:
  <https://fastapi.tiangolo.com/alternatives/>

## On performance and reality

- **TechEmpower benchmarks** — the framework speed charts; read with caution (microbenchmarks rarely predict your production):
  <https://www.techempower.com/benchmarks/>
- **"FastAPI is fast — what does that mean?"** — search; the honest answer is "Starlette and Pydantic core are fast in Rust; your database query is the same speed it was before".

## Cited in the lectures

These URLs appear by name in the lecture notes:

- **`fastapi.tiangolo.com/tutorial/first-steps/`** — Lecture 1
- **`fastapi.tiangolo.com/tutorial/path-params/`** — Lecture 1, Lecture 3
- **`fastapi.tiangolo.com/tutorial/dependencies/`** — Lecture 3
- **`fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/`** — Lecture 3
- **`fastapi.tiangolo.com/advanced/async-tests/`** — Lecture 3, mini-project
- **`docs.pydantic.dev/latest/concepts/models/`** — Lecture 2
- **`docs.pydantic.dev/latest/concepts/validators/`** — Lecture 2
- **`docs.pydantic.dev/latest/concepts/serialization/`** — Lecture 2
- **`docs.pydantic.dev/latest/migration/`** — Lecture 2
- **`asgi.readthedocs.io/en/latest/specs/main.html`** — Lecture 1
- **`datatracker.ietf.org/doc/html/rfc9110`** — Lecture 1, Lecture 3, homework
- **`datatracker.ietf.org/doc/html/rfc7231`** — Lecture 1, homework
- **`www.starlette.io/middleware/`** — Lecture 3, challenge 1
- **`spec.openapis.org/oas/v3.1.0`** — Lecture 3
