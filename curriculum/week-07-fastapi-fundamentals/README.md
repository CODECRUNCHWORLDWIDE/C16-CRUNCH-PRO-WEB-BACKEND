# Week 7 — FastAPI Fundamentals

> *Phase 2 ended with a Django application that could write. Phase 3 begins with a parallel service whose only job is to read. Same database, different surface. The Django side keeps its admin, its forms, its server-rendered pages, its Celery wiring, its Redis cache. The new FastAPI side speaks JSON, generates an OpenAPI document for free, validates every request body through Pydantic v2, and runs on ASGI so the next-week conversation about async actually has a place to land. This week is FastAPI the framework: the routing model, the dependency graph, the schema layer, the test client. Next week is the runtime — async, the GIL, the event loop, the database drivers that play with it. We split the two on purpose. FastAPI is small enough to learn in a week; async Python is not.*

Welcome to Week 7 of **C16 · Crunch Pro Web Backend**. Phase 3 opens here. The `crunchwriter` Django project from Phases 1–2 continues to own writes — authors log in, draft, publish, upload images, see analytics. A new service, `crunchreader-api`, joins the system this week as the read surface: a typed JSON API over the same Postgres database, generating its own interactive documentation, validated end-to-end through Pydantic v2.

We approach FastAPI the way Week 1 approached HTTP: by reading the actual specification before we let the framework hide it. FastAPI is built on top of two libraries — **Starlette** (the ASGI toolkit) and **Pydantic** (the validation engine) — and on top of one Python standard, **PEP 484 type hints**. Most of what feels magical about FastAPI is one of those three layers doing exactly what it was designed to do, in the order the framework expects. The lectures spend the week pulling that ordering apart.

By Sunday you will have:

1. A working `crunchreader-api` FastAPI service running on `uvicorn`, listening on a different port from Django.
2. Pydantic v2 schemas for `Article`, `Author`, and `Category`, derived from the same database `crunchwriter` writes to.
3. A dependency-injected database session, a typed pagination dependency, and a token-based auth dependency — all composable, all testable.
4. The auto-generated **OpenAPI 3.1** document at `/openapi.json`, the **Swagger UI** at `/docs`, and the **ReDoc** rendering at `/redoc`.
5. An integration test suite built on `httpx.AsyncClient` and `pytest-asyncio`, exercising the API without spinning up a real server.

The async story — what `async def` actually does to a view, when it helps, when it hurts — is parked until Week 8. We use `async def` this week because FastAPI rewards it, but we will not promise that any of it is fast yet. That is next week's problem.

This is the week the project stops being one application and starts being two services over one database. The conversation about consistency, contracts, and versioning starts here.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** what ASGI is, why FastAPI requires it, and how it differs from the WSGI standard you saw in Week 1. Read the ASGI spec sections on `scope`, `receive`, `send`, and the three protocol types (`http`, `websocket`, `lifespan`).
- **Build** a FastAPI application from scratch: declare a route with `@app.get`, annotate path parameters, query parameters, and request bodies, and let FastAPI parse, validate, and serialise the result. Cite the four parameter sources FastAPI distinguishes (path, query, header, body) and how it tells them apart.
- **Write** Pydantic v2 models that validate inbound JSON and serialise outbound JSON. Use `Field`, `model_validator`, `field_validator`, `Annotated[..., Field(...)]`, and `model_config`. Distinguish `model_dump()` from `model_dump_json()`, and `dict()`/`json()` (v1, deprecated) from the v2 forms.
- **Design** the request/response schema layer so request schemas (`ArticleCreate`) and response schemas (`ArticleRead`) are separate types, never one shared model. State the three reasons (security boundary, version drift, default values).
- **Use** FastAPI's dependency injection (`Depends`) to express shared concerns — database sessions, current user, pagination — as composable, typed functions. Name the four properties that make `Depends` useful (memoisation per-request, overridability in tests, sub-dependencies, yield-based teardown).
- **Implement** a token-based auth dependency using `OAuth2PasswordBearer` for the OpenAPI integration. Distinguish what the dependency *does* (parse the `Authorization` header, validate the token, return a user object) from what is parked until Week 9 (issuing the token, refreshing it, revoking it).
- **Generate** the OpenAPI 3.1 document automatically. Read the spec, find your route, find your schema, find the response codes. Customise titles, descriptions, tags, examples, and the `summary`/`description` per route.
- **Write** integration tests with `httpx.AsyncClient(transport=ASGITransport(app=app))` and `pytest-asyncio`. Override a dependency in a test (`app.dependency_overrides[get_session] = ...`). Test the happy path, the validation failure (422), and the auth failure (401).
- **Choose** between FastAPI and Django REST Framework with reasons you can defend in code review: FastAPI for typed async APIs greenfield, DRF when the API is one surface of a larger Django project. The "and use both, talking to one database" pattern is what we are building.
- **Read** the FastAPI source for a single function (`fastapi.routing.get_request_handler`) and locate, in that one function, the line that calls Pydantic to validate the body and the line that calls Pydantic to serialise the response. The framework is small; reading it once is part of the week.

## Prerequisites

- **C16 Week 1** — you can read HTTP. The OpenAPI document is a description of HTTP traffic; if `Content-Type: application/json` and the `Location` header on a 201 are unfamiliar, re-read Week 1 Lecture 1.
- **C16 Week 2** — you have a working Django ORM model. The FastAPI service reads from the same database, so the model has to exist on the Django side first.
- **C16 Weeks 4 and 5** — you can write a `SELECT` with a join, and you know what `select_related` does. The FastAPI side will use SQLAlchemy 2.x (or SQLModel) directly; the joins do not become idiomatic by themselves.
- **Python 3.12+** — FastAPI 0.110+ requires Python 3.8+, but we use `Annotated`, `from __future__ import annotations`, and the `type` statement, all of which land cleanly on 3.12. Run `python3 --version`; if it is below 3.12, install via `pyenv` or `uv python install 3.12`.
- **PEP 484 type hints fluent** — `list[int]`, `dict[str, str]`, `Optional[T]`, `Annotated[T, Meta]`. FastAPI uses type hints as runtime metadata; you must be comfortable reading them.

## Topics covered

- ASGI: the protocol, the three event types (`http`, `websocket`, `lifespan`), the `scope`/`receive`/`send` triple
- Why ASGI exists: the WSGI sync-only limit, the rise of long-lived connections (SSE, WebSocket), the async story
- `uvicorn` as the reference ASGI server; `hypercorn`, `daphne`, `granian` as alternatives
- Starlette: routing, requests, responses, middleware, the `Request` and `Response` objects
- FastAPI as a Starlette superset: routing decorators, dependency injection, Pydantic integration, OpenAPI emission
- Declaring a route: `@app.get("/")`, `@app.post("/articles", status_code=201)`, the four parameter sources
- Path parameters with types: `@app.get("/articles/{id}")` and `id: int` — FastAPI parses and validates
- Query parameters with `Query(...)`, defaults, descriptions, examples, regex constraints
- Request bodies with Pydantic models — declared as the type of a single parameter
- Response models with `response_model=...` — the contract on the way out, not just the way in
- Status codes: `status_code=201` for create, `204` for delete-with-no-body, `202` for accepted-but-async
- Pydantic v2: `BaseModel`, `Field`, `model_validator`, `field_validator`, validation modes (`before`, `after`, `wrap`)
- `Annotated[T, Field(...)]` — the canonical 2025 way to attach metadata to a type
- `ConfigDict(from_attributes=True)` — how Pydantic reads a SQLAlchemy ORM object as if it were a dict
- `Discriminator` for union types — for endpoints that accept multiple shapes
- The OpenAPI 3.1 document FastAPI generates — schema-by-schema, route-by-route
- Customising OpenAPI: `title`, `description`, `version`, `tags`, `summary`, `description` per route, `examples` per field
- Swagger UI at `/docs`, ReDoc at `/redoc`, and the JSON at `/openapi.json` — three views of the same source
- Dependency injection with `Depends`: a function whose return value becomes a parameter
- Sub-dependencies — `get_current_user` depends on `get_token`, which depends on the `Authorization` header
- Per-request caching of dependencies (`use_cache=True`, the default), and when to set `use_cache=False`
- `yield`-based dependencies for setup/teardown — the FastAPI equivalent of a context manager
- `OAuth2PasswordBearer` — the FastAPI dependency that integrates token auth with OpenAPI
- Overriding dependencies in tests: `app.dependency_overrides[get_session] = lambda: test_session`
- Testing FastAPI: `httpx.AsyncClient` with `ASGITransport`, `pytest-asyncio` with `asyncio_mode = "auto"`
- Two test scopes: the unit-style test on a Pydantic model, the integration-style test on the route
- The `Lifespan` context manager — initialising and tearing down resources for the app's lifetime
- CORS, middleware ordering, and where to put exception handlers
- Reading the FastAPI source: `fastapi/routing.py`, `fastapi/dependencies/utils.py`, `fastapi/openapi/utils.py`

## Weekly schedule

The schedule below totals approximately **36 hours**. The lecture/exercise/challenge load is heavier than Week 6 because the surface area is genuinely new; the mini-project compensates by sharing more of its scaffolding with the exercises.

| Day       | Focus                                                                              | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|------------------------------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | ASGI, async views in Python, the FastAPI minimal app                                | 2h       | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6h          |
| Tuesday   | Pydantic v2 in depth — schemas, validation, serialisation                          | 2h       | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6h          |
| Wednesday | Dependency injection, routing, OpenAPI emission                                    | 2h       | 2h        | 1h         | 0.5h      | 1h       | 0h           | 0.5h       | 7h          |
| Thursday  | Auth dependency, OAuth2PasswordBearer, the integration test client                  | 0h       | 0.5h      | 1h         | 0.5h      | 1h       | 2h           | 0.5h       | 5.5h        |
| Friday    | Pagination, filtering, response shaping                                            | 0h       | 0h        | 1h         | 0.5h      | 1h       | 2h           | 0h         | 4.5h        |
| Saturday  | Wire `crunchreader-api` end-to-end; write the integration tests; document          | 0h       | 0h        | 0h         | 0h        | 1h       | 3h           | 0h         | 4h          |
| Sunday    | Quiz, reflection, OpenAPI document review                                          | 0h       | 0h        | 0h         | 0.5h      | 0h       | 0h           | 0h         | 0.5h        |
| **Total** |                                                                                    | **6h**   | **6.5h**  | **3h**     | **3h**    | **6h**   | **7h**       | **2h**     | **33.5h**   |

The week's pacing is deliberate: the lecture material front-loads Monday–Wednesday so Thursday onward is a build week. The mini-project ships a small but complete API surface — list, retrieve, create, paginate, authenticate — that is the foundation for Week 8 (make it async-correctly) and Week 9 (issue the tokens properly).

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview |
| [resources.md](./resources.md) | FastAPI docs, Pydantic docs, Starlette docs, RFC 7231/9110, the references worth bookmarking |
| [lecture-notes/01-asgi-and-async-in-python-web.md](./lecture-notes/01-asgi-and-async-in-python-web.md) | ASGI, the three protocol types, `await` semantics, when async actually helps |
| [lecture-notes/02-pydantic-v2-validation-and-serialization.md](./lecture-notes/02-pydantic-v2-validation-and-serialization.md) | Pydantic v2 from `BaseModel` to discriminated unions; what changed from v1 |
| [lecture-notes/03-dependency-injection-and-routing.md](./lecture-notes/03-dependency-injection-and-routing.md) | `Depends`, sub-dependencies, yield-based teardown, OpenAPI emission, the test client |
| [exercises/exercise-01-hello-fastapi.py](./exercises/exercise-01-hello-fastapi.py) | Typed routes; path, query, body parameters; status codes; the `/docs` page |
| [exercises/exercise-02-pydantic-validation.py](./exercises/exercise-02-pydantic-validation.py) | Validators, `Annotated`, `Field`, discriminated unions, custom error messages |
| [exercises/exercise-03-deps-and-auth-dependency.py](./exercises/exercise-03-deps-and-auth-dependency.py) | `Depends`, sub-dependencies, a token-based auth dependency, dependency overrides |
| [exercises/SOLUTIONS.md](./exercises/SOLUTIONS.md) | Worked solutions, with explanation of the trickier lines |
| [challenges/challenge-01-rate-limit-middleware.md](./challenges/challenge-01-rate-limit-middleware.md) | Token-bucket rate-limit middleware reading from Redis |
| [challenges/challenge-02-async-db-with-sqlmodel.md](./challenges/challenge-02-async-db-with-sqlmodel.md) | Wire `SQLModel` to the same Postgres database `crunchwriter` writes to |
| [quiz.md](./quiz.md) | 10 multiple-choice questions |
| [homework.md](./homework.md) | Six problems (~6h) |
| [mini-project/README.md](./mini-project/README.md) | Build `crunchreader-api` — list, retrieve, create, paginate, authenticate, test |

## Before Monday — verify the environment

Five checks. If any fails, fix it before opening Lecture 1.

```bash
# 1. Python 3.12+
python3 --version
# Python 3.12.x or 3.13.x

# 2. crunchwriter is runnable from Week 6
cd crunchwriter && python manage.py check && cd ..
# System check identified no issues

# 3. crunchwriter database is reachable
cd crunchwriter && python manage.py dbshell -c "select count(*) from writer_article;" && cd ..
# returns a number, not an error

# 4. Create the FastAPI service skeleton
mkdir -p crunchreader-api && cd crunchreader-api
python3 -m venv .venv && source .venv/bin/activate
pip install 'fastapi[standard]==0.115.*' 'pydantic==2.9.*' 'httpx==0.27.*' 'pytest==8.3.*' 'pytest-asyncio==0.24.*' 'sqlmodel==0.0.22'

# 5. Confirm the FastAPI CLI is available
fastapi --version
# 0.115.x
```

If `pip install 'fastapi[standard]'` is unfamiliar, the `[standard]` extra is the bundle FastAPI recommends as of 0.110+; it pulls `uvicorn[standard]`, `httpx`, `python-multipart`, `email-validator`, and a few more. See <https://fastapi.tiangolo.com/#installation>.

## The habit to install this week

Three practices, applied to every route you write from here on:

1. **Two schemas per resource.** `ArticleCreate` for the body of `POST /articles`; `ArticleRead` for the body of `GET /articles/{id}`. They differ — `ArticleRead` has an `id`, a `created_at`, and possibly a denormalised `author_name`; `ArticleCreate` does not. The shared parent (`ArticleBase`) is fine; the shared single model (`Article`) is the bug that ships the next time someone adds an internal field.
2. **Every route gets a `response_model`.** Without one, FastAPI returns whatever the function returned, unvalidated; with one, the response is validated and serialised through Pydantic on the way out. The validation cost on a typical response is microseconds; the bug it prevents (an internal field leaking into the public JSON) is hours.
3. **Every route gets an integration test.** Not a unit test of the Pydantic model; an integration test that hits the route through `httpx.AsyncClient`. Three cases per route: happy path (200), validation failure (422), auth failure (401). The test file is built once, copied per route. Six routes means eighteen test cases, fifteen minutes of work, never a regression on the contract.

The first practice prevents internal-field leakage. The second prevents drift between docs and implementation. The third prevents silent breakage on refactor. Together they replace most of the human review that API code traditionally needs.

## Stretch goals

- Read the **ASGI spec** end to end (~30 minutes; the spec is short): <https://asgi.readthedocs.io/en/latest/specs/main.html>. The version of `scope` for `http` is the one you will see in middleware.
- Read the **FastAPI tutorial** for the sections we did not cover this week: `Body - Multiple Parameters`, `Cookie Parameters`, `Header Parameters`, `Files`, and `Background Tasks`: <https://fastapi.tiangolo.com/tutorial/>.
- Read the **Pydantic v2 migration guide** — even if you never wrote v1 code, the migration guide is the clearest single document on what v2 changed and why: <https://docs.pydantic.dev/latest/migration/>.
- Install `uvicorn[standard]` and run with `--reload` for development, `--workers 4` for a poor-man's production. Read the docs: <https://www.uvicorn.org/>.
- Read `fastapi/routing.py` (one file, ~700 lines). Find `get_request_handler`. Trace one request from `app(scope, receive, send)` through to the response. You will never be surprised by FastAPI again.

## Up next

[Week 8 — Async, Sync, and the GIL](../week-08-async-sync-and-the-gil/) — the runtime week. We have been writing `async def` since Monday; next week we earn it. The event loop, `asyncio.gather`, the database drivers that block your loop, the ones that do not, and the moment-by-moment account of what `await` does to the call stack.
