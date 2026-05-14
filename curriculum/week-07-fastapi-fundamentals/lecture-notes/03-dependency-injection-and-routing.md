# Lecture 3 — Dependency injection, routing, OpenAPI emission, and the test client

> **Duration:** ~2 hours. **Outcome:** You can declare a FastAPI dependency, compose dependencies into sub-dependencies, write a yield-based dependency for setup/teardown, override a dependency in tests, and reason about per-request caching. You can split a project across multiple `APIRouter` files. You can read the generated OpenAPI document and trace a route from declaration to spec entry. You can write an integration test with `httpx.AsyncClient(transport=ASGITransport(...))` and `pytest-asyncio`.

Lectures 1 and 2 gave us ASGI, type hints, Pydantic. We can build single-file FastAPI apps. This lecture is everything else FastAPI brings: the dependency graph, the routing system, the OpenAPI document, and the test client. After this lecture you can ship a small service.

## 1. `Depends` — a function as a parameter

The single most important FastAPI primitive after `BaseModel` is `Depends`. The pattern:

```python
from typing import Annotated
from fastapi import Depends, FastAPI

app = FastAPI()


async def get_pagination(skip: int = 0, limit: int = 20) -> dict[str, int]:
    return {"skip": skip, "limit": min(limit, 100)}


@app.get("/articles")
async def list_articles(
    pagination: Annotated[dict[str, int], Depends(get_pagination)],
) -> dict[str, object]:
    return {"pagination": pagination, "items": []}
```

What happens on every request to `GET /articles?skip=10&limit=20`:

1. FastAPI sees `pagination: Annotated[..., Depends(get_pagination)]`.
2. It calls `get_pagination(skip=10, limit=20)` — same parameter-extraction logic as a route handler. `skip` and `limit` come from the query string because their types are scalars and there is no `Body(...)` / `Path(...)` marker.
3. The return value (`{"skip": 10, "limit": 20}`) becomes the value of `pagination` in `list_articles`.
4. `list_articles` runs with that value.

The dependency is a function. The framework calls it. The return becomes a parameter. That is the whole pattern.

The older, pre-`Annotated` syntax also works and you will see it in older code:

```python
async def list_articles(
    pagination: dict[str, int] = Depends(get_pagination),
) -> dict[str, object]:
    ...
```

Both are equivalent. The `Annotated` form is preferred in 2025 because the type and the dependency marker are visually distinct from the default value. See <https://fastapi.tiangolo.com/tutorial/dependencies/>.

## 2. Why `Depends`? Four properties

The pattern looks like an ordinary function call. The difference is the four properties FastAPI gives it, none of which an ordinary call has:

### 2.1 Per-request caching

```python
async def get_session() -> AsyncSession:
    ...

@app.get("/articles/{article_id}")
async def get_article(
    article_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],  # also depends on get_session
) -> ArticleRead:
    ...
```

`get_current_user` itself probably depends on `get_session`. Without caching, `get_session` would be called twice per request — once directly by the route handler, once transitively through `get_current_user`. With caching (the default, `use_cache=True`), `get_session` is called *once*, the same session is shared by all dependents in this request, and the second usage receives the cached value. Per-request scope.

To opt out: `Depends(get_session, use_cache=False)`. Useful when the dependency is cheap and you genuinely want a fresh value each time, but the default is correct for the database-session case.

### 2.2 Sub-dependencies

A dependency can declare its own parameters, including other `Depends`. They resolve recursively. The graph is a DAG:

```text
list_articles
  └─ get_session
  └─ get_current_user
       └─ get_token   (parses Authorization header)
       └─ get_session (cached — same instance as above)
```

FastAPI solves the graph at request time. You do not write the order. You write the dependencies, and the framework figures out the order. See <https://fastapi.tiangolo.com/tutorial/dependencies/sub-dependencies/>.

### 2.3 Yield-based teardown

The third property is the killer feature for database sessions and any other resource that needs to be released:

```python
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session = async_session_maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
```

The function `yield`s the value instead of returning it. FastAPI:

1. Runs everything before the `yield` (open the session).
2. Yields the value to the dependent.
3. Runs the dependent (the route handler).
4. Resumes after the `yield` — runs the `commit`/`rollback`/`close` block.
5. Then returns the response to the client.

This is the FastAPI equivalent of `@contextmanager`. It guarantees resource cleanup even if the dependent raises. The error path (`except`) lets the session roll back; the success path commits. The session is closed in `finally`, always.

The yield-based dependency runs its teardown code *after* the response is sent — or, more precisely, after the route handler returns. Failures inside the teardown do not change the response status. See <https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/>.

### 2.4 Testability

The fourth property: every dependency can be overridden in tests without monkeypatching.

```python
# In production, get_session connects to the real database.
# In tests, override it to connect to an in-memory or test database.

app.dependency_overrides[get_session] = get_test_session
```

Tests pass their own dependency factories; production passes the real ones. The route handler does not need to know — it asks the framework for "a session", and the framework hands it whichever one is currently registered. This is the same pattern as `unittest.mock.patch`, applied at the framework level rather than the import level.

We use this every time in this week's exercises. See <https://fastapi.tiangolo.com/advanced/testing-dependencies/>.

## 3. The four parameter sources

FastAPI distinguishes four sources from which a parameter can be filled:

| Source | Marker | Default for type |
|---|---|---|
| Path | `Path(...)` | Path parameters declared in the URL template (`{article_id}`) |
| Query | `Query(...)` | Scalar types not in the path |
| Header | `Header(...)` | Never default — must use `Header(...)` |
| Body | `Body(...)` or a Pydantic model | Pydantic model types |
| Cookie | `Cookie(...)` | Never default — must use `Cookie(...)` |
| Form / file | `Form(...)`, `File(...)` | Multipart bodies |
| Dependency | `Depends(...)` | Other functions |

The defaults — "scalar types in path → path parameters, scalar types not in path → query parameters, Pydantic model types → body" — cover almost every case. The explicit markers exist for the corner cases (a query parameter whose name has a hyphen and needs an alias; a header you want to extract; a body that is not a single model).

A canonical signature:

```python
@app.get("/articles/{article_id}")
async def get_article(
    article_id: Annotated[int, Path(ge=1, description="The article ID.")],
    include_body: Annotated[bool, Query(default=False, description="Include body in response.")],
    if_none_match: Annotated[str | None, Header(default=None, alias="If-None-Match")],
    session: SessionDep,  # an aliased Depends; see section 4
    current_user: CurrentUserDep,
) -> ArticleRead:
    ...
```

Five parameters, five different mechanisms, all explicit in the signature. The OpenAPI document will list `article_id` under `parameters[in=path]`, `include_body` under `parameters[in=query]`, `if_none_match` under `parameters[in=header]`. The session and user dependencies are *not* OpenAPI parameters — they are server-side concerns, invisible to the client.

## 4. Type-aliased dependencies — the `Annotated` shorthand

A dependency you use on every endpoint becomes verbose if you spell it out each time. Use `Annotated`-based type aliases:

```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
PaginationDep = Annotated[dict[str, int], Depends(get_pagination)]
```

Then in route handlers:

```python
@app.get("/articles")
async def list_articles(
    session: SessionDep,
    pagination: PaginationDep,
    current_user: CurrentUserDep,
) -> list[ArticleRead]:
    ...
```

Pure noise reduction. The dependency wiring lives in one place; the route handler reads as a small contract. This pattern is in the FastAPI tutorial: <https://fastapi.tiangolo.com/tutorial/sql-databases/#create-a-sessiondep-dependency>.

## 5. Routing and `APIRouter`

A real project does not declare every route on the top-level `app`. It splits routes across `APIRouter` instances and includes them:

```python
# routers/articles.py
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("/", response_model=list[ArticleRead])
async def list_articles(session: SessionDep, pagination: PaginationDep) -> list[ArticleRead]:
    ...


@router.get("/{article_id}", response_model=ArticleRead)
async def get_article(article_id: int, session: SessionDep) -> ArticleRead:
    ...
```

```python
# main.py
from fastapi import FastAPI
from routers import articles, authors

app = FastAPI(title="crunchreader-api")

app.include_router(articles.router)
app.include_router(authors.router)
```

The `prefix="/articles"` argument means every route in this router is mounted under `/articles`. The `tags=["articles"]` argument groups the routes under the "articles" heading in `/docs`. Both compose: an `APIRouter` can itself include other `APIRouter`s, with the prefixes concatenating.

See <https://fastapi.tiangolo.com/tutorial/bigger-applications/>.

### `include_router` with dependencies

A common need: every route in a router needs auth, and you do not want to repeat the dependency on every handler.

```python
admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)
```

The `dependencies=[Depends(require_admin)]` runs `require_admin` for *every* route under this router, even if the route handler does not declare a `current_user` parameter. The dependency is invoked for its side effect (raising 401 if not admin), not for its return value.

## 6. The OpenAPI document — what FastAPI generates

Every FastAPI app generates an OpenAPI 3.1.0 document at `/openapi.json` and renders it through:

- **Swagger UI** at `/docs` — interactive, with try-it buttons.
- **ReDoc** at `/redoc` — reference-style, prettier for handing to consumers.

The document is built once, lazily, on the first request to `/openapi.json` (or `/docs` / `/redoc`), and cached on the app instance. Subsequent requests are served from the cache. To regenerate after route changes — for instance, in tests — call `app.openapi_schema = None`.

### What lands in the document

For each route:

- The path (`/articles/{article_id}`).
- The method (`get`, `post`, …).
- The `summary` (from the route's docstring first line) and `description` (rest of the docstring or the `description=` argument).
- The `tags` (from the router or the route decorator).
- The `parameters` array (one entry per path/query/header parameter, with the field's JSON Schema).
- The `requestBody` if the route accepts one (the JSON Schema of the request Pydantic model).
- The `responses` object (status codes the route can return, each with the JSON Schema of its body).

For each schema (each Pydantic model used anywhere):

- The JSON Schema, under `components.schemas.<ModelName>`.

For each security scheme (e.g., `OAuth2PasswordBearer`):

- The security definition, under `components.securitySchemes`.

### Customising

```python
@app.post(
    "/articles",
    response_model=ArticleRead,
    status_code=201,
    summary="Create an article",
    description="Authors can create draft articles. The draft is owned by the current user.",
    response_description="The newly-created article.",
    tags=["articles"],
    responses={
        401: {"description": "Authentication required"},
        422: {"description": "Validation failed"},
    },
)
async def create_article(...) -> ArticleRead:
    """Create a new draft article owned by the current user."""
    ...
```

Every keyword on the decorator lands in the OpenAPI document. Time spent on `summary` and `description` pays back the next time a teammate (or a future you) opens `/docs`.

See <https://fastapi.tiangolo.com/tutorial/path-operation-configuration/>. The OpenAPI 3.1 spec itself: <https://spec.openapis.org/oas/v3.1.0>.

### When to mutate the generated document

Rarely. The FastAPI defaults are correct for 95% of cases. The exceptions:

- Adding a custom security definition the framework does not know about (mutual TLS, an API-key header named outside the standard).
- Adding global examples or response headers that apply to many routes.
- Generating a *static* `openapi.json` at build time for downstream tooling (a TypeScript client generator, for instance).

The escape hatch is `app.openapi = custom_openapi_function`, where `custom_openapi_function` calls the default and mutates the result. See <https://fastapi.tiangolo.com/advanced/extending-openapi/>.

## 7. Auth — `OAuth2PasswordBearer` as a dependency

A complete auth implementation needs token issuance (login), token verification (every request), and revocation (logout). FastAPI's `OAuth2PasswordBearer` is the *verification* half — it parses the `Authorization: Bearer <token>` header and integrates the token-based shape into OpenAPI so Swagger UI offers a login form.

```python
from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt  # PyJWT

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    try:
        payload: dict = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id: int | None = payload.get("sub")
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await load_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user
```

Two things to notice:

- The `WWW-Authenticate: Bearer` header on the 401 response is **required by RFC 9110 §11.6.1**. Curl and the FastAPI Swagger UI both inspect this header to know which auth scheme to retry. Returning a 401 *without* the header is a bug clients have a right to complain about.
- `OAuth2PasswordBearer(tokenUrl="auth/token")` tells the OpenAPI document where the token is issued. Swagger UI builds a login form pointed at that URL. The actual issuance — the `POST /auth/token` endpoint — is Week 9; this week we hand-write a token for testing.

The corresponding test override:

```python
app.dependency_overrides[get_current_user] = lambda: fake_admin_user
```

The test sidesteps token validation entirely. The real dependency runs in production; the fake one runs in tests. See <https://fastapi.tiangolo.com/tutorial/security/first-steps/> and <https://fastapi.tiangolo.com/tutorial/security/get-current-user/>.

## 8. The lifespan context — app-scoped resources

Database engines, cache pools, ML models — anything that should be initialised once per worker process — go in the `lifespan` context manager:

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # startup
    app.state.db_engine = create_async_engine(DATABASE_URL, pool_size=20)
    yield
    # shutdown
    await app.state.db_engine.dispose()


app = FastAPI(lifespan=lifespan)
```

The lifespan runs once per worker, before any requests are served. The `yield` separates startup from shutdown. The shutdown runs when the worker is gracefully stopped (SIGTERM under most process managers). For SIGKILL or a hard crash, the shutdown does not run — design accordingly.

This is the FastAPI equivalent of Django's `AppConfig.ready` plus signal handlers. See <https://fastapi.tiangolo.com/advanced/events/>.

Attach to `app.state` for things you want to read inside dependencies (`request.app.state.db_engine`). Avoid module-level globals — they break test isolation and multi-worker scenarios.

## 9. Middleware — and which kind

Two kinds of middleware in Starlette / FastAPI, and the choice matters:

### Pure ASGI middleware

```python
class TimingMiddleware:
    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.monotonic()
        async def send_wrapper(event: dict) -> None:
            if event["type"] == "http.response.start":
                duration_ms = int((time.monotonic() - start) * 1000)
                event["headers"].append((b"x-process-time-ms", str(duration_ms).encode()))
            await send(event)
        await self.app(scope, receive, send_wrapper)


app.add_middleware(TimingMiddleware)
```

Pure ASGI middleware wraps the entire ASGI callable. It has full access to the streaming pipeline and is the right shape for performance-sensitive concerns (rate limiting, request logging, header injection).

### `BaseHTTPMiddleware`

The `BaseHTTPMiddleware` shape is friendlier but buffers the body into memory and disables streaming:

```python
from starlette.middleware.base import BaseHTTPMiddleware


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        log_event({"path": request.url.path, "status": response.status_code})
        return response


app.add_middleware(LoggingMiddleware)
```

Easier to write; not the right choice for streaming responses or large request bodies. For most application-level needs, use the pure ASGI shape. The Starlette middleware page is the canonical reference: <https://www.starlette.io/middleware/>.

### CORS — the one you will always need

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://crunchwriter.example.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

CORS is the middleware every browser-facing API needs. The wildcard `["*"]` for methods and headers is appropriate; the wildcard `["*"]` for origins is *not* appropriate in production (and is incompatible with `allow_credentials=True`). Read the FastAPI CORS chapter and the MDN article before deploying: <https://fastapi.tiangolo.com/tutorial/cors/>.

## 10. The integration test client

The single best test infrastructure FastAPI offers: `httpx.AsyncClient` with `ASGITransport`. Tests run *in-process* — no real network, no separate server — and exercise the entire ASGI pipeline end to end, including middleware, dependencies, and serialisation.

The setup:

```python
# tests/conftest.py
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

`asyncio_mode = "auto"` makes every async test function an asyncio task without per-test `@pytest.mark.asyncio`. See <https://pytest-asyncio.readthedocs.io/en/latest/concepts.html#auto-mode>.

A test:

```python
async def test_get_article_happy(client: AsyncClient) -> None:
    response = await client.get("/articles/1")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 1
    assert "title" in body


async def test_get_article_not_found(client: AsyncClient) -> None:
    response = await client.get("/articles/99999")
    assert response.status_code == 404


async def test_post_article_validation_failure(client: AsyncClient) -> None:
    response = await client.post("/articles", json={"title": ""})
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any(e["loc"] == ["body", "title"] for e in errors)
```

The same `AsyncClient` you use in production code (to call other services) is what you use in tests. The transport is the only difference. See <https://fastapi.tiangolo.com/advanced/async-tests/>.

### Overriding dependencies in tests

```python
# tests/conftest.py (continued)

@pytest_asyncio.fixture
async def authed_client(client: AsyncClient) -> AsyncClient:
    app.dependency_overrides[get_current_user] = lambda: fake_admin_user
    yield client
    app.dependency_overrides.clear()
```

The fixture installs a fake `get_current_user`, yields the client (now authenticated for every request), and clears the override after the test. The teardown is essential — without it, the override leaks into the next test.

## 11. The full request lifecycle — every step

Putting Lectures 1, 2, and 3 together. A `GET /articles/42` request goes through:

1. **`uvicorn`** parses the HTTP bytes and constructs `scope`, `receive`, `send`.
2. **`uvicorn`** calls `app(scope, receive, send)`.
3. **`app.__call__`** (Starlette) dispatches to the **middleware stack** (outermost first).
4. The middleware stack reaches the **router**. The router matches `/articles/42` against registered routes; the match is `get_article(article_id: int)`.
5. The **route handler entry** (`get_request_handler`, the function we read in Lecture 1) takes over:
   - **(a) Body parsing** — none for GET.
   - **(b) Dependency solving** — solve the DAG. Run `get_session` (yields a session), `get_current_user` (parses the Authorization header, decodes the JWT, loads the user), `get_pagination` (returns `{"skip": 0, "limit": 20}`).
   - **(c) Path/query/header parsing** — convert `article_id="42"` to `int(42)`; validate against `Path(ge=1)`.
   - **(d) Invoke the user's endpoint** — `await get_article(article_id=42, session=..., current_user=..., pagination=...)`.
   - **(e) Response model validation** — the return value is validated against `ArticleRead` (via `response_model=ArticleRead`).
   - **(f) Serialisation** — Pydantic serialises to a dict via `model_dump(mode="json")`. FastAPI wraps it in a `JSONResponse` with `status_code=200`.
6. The response unwinds back through the middleware stack (outermost last).
7. The yield-based dependencies run their teardown blocks — `await session.commit(); await session.close()`.
8. **`uvicorn`** sends the HTTP response back to the client.

Every line of FastAPI you write touches one of these steps. Knowing the order lets you reason about which knobs change behaviour and which do not.

## Lecture summary

- **`Depends`** lets a function be a parameter. Four properties: per-request caching, sub-dependency resolution, yield-based teardown, and test-time overridability.
- **Type aliases with `Annotated`** (`SessionDep = Annotated[AsyncSession, Depends(get_session)]`) keep route signatures terse.
- **`APIRouter`** splits routes across files. `prefix=`, `tags=`, and `dependencies=` parameters compose cleanly with `include_router`.
- **FastAPI generates OpenAPI 3.1** from the registered routes plus the Pydantic schemas. `summary`, `description`, `tags`, `response_description`, `responses` per route customise the document.
- **`OAuth2PasswordBearer`** is the FastAPI dependency that parses `Authorization: Bearer <token>` and integrates with OpenAPI / Swagger UI. The 401 response must carry `WWW-Authenticate: Bearer` (RFC 9110 §11.6.1).
- **`lifespan`** is the `@asynccontextmanager` for app-scoped startup/shutdown. Use `app.state` for resources you want to read in dependencies.
- **Middleware** has two shapes: pure ASGI (recommended for performance) and `BaseHTTPMiddleware` (recommended for ergonomics). CORS is the one every browser-facing API needs.
- **The test client** is `httpx.AsyncClient(transport=ASGITransport(app=app))`, paired with `pytest-asyncio` in `asyncio_mode = "auto"`. Dependency overrides via `app.dependency_overrides[...]` replace test setup for any cross-cutting concern.
- **Every request** goes through middleware → router → body parsing → dependency solving → handler → response model validation → serialisation → middleware unwind → teardown. Knowing the order is the difference between debugging and guessing.

This week's lectures are now complete. Lectures 1–3 give you the building blocks. The exercises and the mini-project assemble them into `crunchreader-api`.

## Further reading

- FastAPI — Dependencies: <https://fastapi.tiangolo.com/tutorial/dependencies/>
- FastAPI — Sub-dependencies: <https://fastapi.tiangolo.com/tutorial/dependencies/sub-dependencies/>
- FastAPI — Dependencies with yield: <https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/>
- FastAPI — Bigger applications (APIRouter): <https://fastapi.tiangolo.com/tutorial/bigger-applications/>
- FastAPI — Path operation configuration: <https://fastapi.tiangolo.com/tutorial/path-operation-configuration/>
- FastAPI — Security first steps: <https://fastapi.tiangolo.com/tutorial/security/first-steps/>
- FastAPI — Get current user: <https://fastapi.tiangolo.com/tutorial/security/get-current-user/>
- FastAPI — Testing dependencies with overrides: <https://fastapi.tiangolo.com/advanced/testing-dependencies/>
- FastAPI — Async tests: <https://fastapi.tiangolo.com/advanced/async-tests/>
- FastAPI — Lifespan events: <https://fastapi.tiangolo.com/advanced/events/>
- FastAPI — CORS: <https://fastapi.tiangolo.com/tutorial/cors/>
- Starlette — Middleware: <https://www.starlette.io/middleware/>
- OpenAPI 3.1 specification: <https://spec.openapis.org/oas/v3.1.0>
- RFC 9110 §11.6.1 — `WWW-Authenticate` header: <https://datatracker.ietf.org/doc/html/rfc9110#section-11.6.1>
