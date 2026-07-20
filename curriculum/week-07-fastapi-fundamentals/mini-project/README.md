# Mini-Project — `crunchreader-api`: a typed FastAPI service for "books"

> Build a standalone FastAPI service that exposes a CRUD interface over a `books` table. The service runs on a different port from `crunchwriter`. It validates every inbound body through Pydantic v2; it shapes every response through a Pydantic response model; it enforces auth via a token dependency; it offers paginated listing with optional filtering. By Sunday evening the service has an OpenAPI document at `/openapi.json`, an interactive UI at `/docs`, and an integration test suite that exercises every route through `httpx.AsyncClient`.

**Estimated time:** 7 hours, spread Thursday–Saturday. The Friday-on hours are filled by writing tests and tightening the schemas.

## Why "books" and not "articles"?

`crunchreader-api` proper, the one that reads from `crunchwriter`'s database, is challenge 2. The mini-project is deliberately a *fresh* domain so the focus stays on FastAPI mechanics: routes, schemas, dependencies, tests, OpenAPI. A separate domain also gives you a project you can push to GitHub on its own and demo independently of the larger `crunchwriter` stack. The two converge in Week 8 when the FastAPI service shares the `crunchwriter` database.

## What you build

A FastAPI service named `books-api` with:

1. **Six routes** for the `Book` resource:
   - `GET /books` — paginated list with optional `q` (title/author full-text), `min_year`, `max_year` filters.
   - `GET /books/{book_id}` — single book by id; 404 on miss.
   - `POST /books` — create a new book; 201 with the new resource; admin-only.
   - `PATCH /books/{book_id}` — update; only the fields the client sent; admin-only.
   - `DELETE /books/{book_id}` — 204 on success; admin-only.
   - `GET /books/count` — `{"total": <int>}` for arbitrary clients (no auth).
2. **Three Pydantic schemas:**
   - `BookBase` (shared fields)
   - `BookCreate` (request body for POST)
   - `BookUpdate` (request body for PATCH, every field optional)
   - `BookRead` (response shape)
3. **Three dependencies:**
   - `get_session` (yield-based; SQLModel async session over SQLite for the mini-project)
   - `get_pagination` (returns `{"skip": ..., "limit": ...}` with bounds)
   - `get_current_user` (token-based; admin/author distinction)
4. **Auto-generated OpenAPI** at `/openapi.json`, `/docs`, `/redoc`.
5. **Integration tests** covering: happy path, 404, 422, 401, 403, pagination math, and the OpenAPI document's structure.
6. **A README** explaining how to run, how to authenticate, and what each route does.

## Repository layout

```text
books-api/
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
├── books_api/
│   ├── __init__.py
│   ├── main.py
│   ├── settings.py
│   ├── db.py
│   ├── models.py            (SQLModel — the database row)
│   ├── schemas.py           (Pydantic — the API contracts)
│   ├── deps.py              (Pagination, auth, session aliases)
│   ├── auth.py              (OAuth2PasswordBearer, fake token table)
│   └── routers/
│       ├── __init__.py
│       └── books.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    └── test_books.py
```

Total: 14 files (matching the C9/C17 quality bar).

## Stack

- Python 3.12+
- FastAPI 0.115.x with the `[standard]` extra
- Pydantic 2.9.x
- SQLModel 0.0.22+
- aiosqlite for the database (no Postgres needed for the mini-project; the challenge already wired Postgres)
- pytest 8.x + pytest-asyncio 0.24.x + httpx 0.27.x

Setup:

```bash
mkdir books-api && cd books-api
python3 -m venv .venv && source .venv/bin/activate
pip install 'fastapi[standard]==0.115.*' 'pydantic==2.9.*' \
            'sqlmodel==0.0.22' 'aiosqlite==0.20.*' \
            'pytest==8.3.*' 'pytest-asyncio==0.24.*' 'httpx==0.27.*'
pip freeze > requirements.txt
```

## Acceptance criteria

### Models and schemas

- [ ] `models.py` — `Book(SQLModel, table=True)` with columns: `id`, `title`, `author_name`, `year`, `isbn`, `created_at`, `updated_at`. `id` is autoincrement primary key.
- [ ] `schemas.py` — four Pydantic models (`BookBase`, `BookCreate`, `BookUpdate`, `BookRead`) with the rules below.
- [ ] `title` is required (1-200 chars) in `BookCreate`; optional in `BookUpdate`; present in `BookRead`.
- [ ] `author_name` 1-120 chars, required in `BookCreate`.
- [ ] `year` is an integer; 1000 ≤ year ≤ 2100.
- [ ] `isbn` matches `^(97(8|9))?\d{9}(\d|X)$` (10- or 13-digit ISBN); optional in all schemas.
- [ ] `model_config` uses `extra="forbid"` on `BookCreate` and `BookUpdate`.
- [ ] A `@model_validator(mode="after")` on `BookUpdate` rejects an entirely-empty patch (`model_dump(exclude_unset=True) == {}` → 422).

### Routes

- [ ] All six routes registered, each with a `summary`, a `description`, a `tags=["books"]`, and an explicit `response_model`.
- [ ] `GET /books?skip=0&limit=20` returns the first page; `Pagination` dependency enforces `0 ≤ skip` and `1 ≤ limit ≤ 100`.
- [ ] `GET /books?q=fastapi` returns books whose title or author_name contains the substring (case-insensitive).
- [ ] `GET /books?min_year=2020&max_year=2024` returns books in the range, inclusive.
- [ ] `POST /books` returns 201 with the created book's full `BookRead` body. The response includes a `Location: /books/{new_id}` header.
- [ ] `PATCH /books/{book_id}` only updates the fields the client sent (`update.model_dump(exclude_unset=True)`).
- [ ] `DELETE /books/{book_id}` returns 204 with an empty body; 404 if the book does not exist.
- [ ] `GET /books/count` returns `{"total": <int>}` without auth.
- [ ] POST/PATCH/DELETE require admin token; non-admin requests get 403; missing token gets 401 with `WWW-Authenticate: Bearer`.

### OpenAPI

- [ ] The four schemas appear under `components.schemas` in `/openapi.json`.
- [ ] Every route has a non-empty `summary` and `description`.
- [ ] The auth scheme appears under `components.securitySchemes.OAuth2PasswordBearer`.
- [ ] `BookCreate.required` is `["title", "author_name", "year"]`.
- [ ] `BookRead.required` includes `id`, `title`, `author_name`, `year`, `created_at`, `updated_at`.

### Tests

- [ ] `tests/conftest.py` builds an `AsyncClient` over `ASGITransport`, with a per-test database (in-memory SQLite is fine; `sqlite+aiosqlite:///:memory:`).
- [ ] `tests/conftest.py` overrides `get_current_user` with `fake_admin` for the admin client and `fake_author` for the unauthorised client.
- [ ] At least **twelve test cases** spanning:
  - `test_list_books_empty` (200, empty list)
  - `test_list_books_after_seed` (200, three books, correct order)
  - `test_list_books_pagination_math` (skip=1, limit=1 → exactly one item, correct one)
  - `test_list_books_filter_q` (case-insensitive substring match)
  - `test_list_books_filter_year_range`
  - `test_get_book_happy` (200)
  - `test_get_book_not_found` (404)
  - `test_post_book_happy` (201, Location header, body matches input)
  - `test_post_book_validation_failure` (422, invalid year)
  - `test_post_book_unauthorized` (401, WWW-Authenticate header)
  - `test_post_book_forbidden_for_author` (403)
  - `test_patch_empty_body_is_rejected` (422)
  - `test_patch_partial_update` (only sent fields change)
  - `test_delete_book_happy` (204, empty body)
  - `test_count_books_no_auth_required` (200)
  - `test_openapi_document_structure` (assert four schemas present)
- [ ] All tests pass under `pytest`.
- [ ] All `.py` files in `books_api/` and `tests/` pass `python3 -m py_compile`.

### Documentation

- [ ] `README.md` at the project root explaining: install, run, the demo tokens, the route table, the test command.
- [ ] One screenshot of `/docs` rendering (or paste the route list as text).
- [ ] One paste of the response from `curl http://localhost:8000/books/count`.
- [ ] One paste of a failing `POST /books` request (422), showing the `detail` array.

## Suggested order of operations

### Phase 1 — Skeleton (Thursday, 1 hour)

1. Create the directory structure.
2. Implement `settings.py`: env-based `DATABASE_URL`, default `sqlite+aiosqlite:///./books.db`; `SECRET_KEY` (unused this week, will matter Week 9); `SQL_ECHO`.
3. Implement `db.py`: async engine, `async_sessionmaker`, `get_session` yield-based dependency.
4. Implement `models.py`: `Book` SQLModel with the columns listed above.
5. Implement `main.py`: `FastAPI(...)`, `app.include_router(books.router)`, a `lifespan` that creates tables on startup.
6. Verify `fastapi dev books_api/main.py` boots. `/docs` shows no routes yet.

### Phase 2 — Schemas (Thursday, 30 min)

7. Implement `schemas.py` with the four models.
8. Test the schemas in isolation:
   ```python
   from books_api.schemas import BookCreate
   BookCreate(title="x", author_name="y", year=2024)  # ok
   BookCreate(title="", author_name="y", year=2024)   # raises
   ```

### Phase 3 — Auth (Thursday, 30 min)

9. Implement `auth.py` with `OAuth2PasswordBearer`, `User` dataclass, `_TOKEN_TABLE`, `get_current_user`, `require_admin`. Use the same shape as Exercise 3.
10. Implement `deps.py` with `SessionDep`, `PaginationDep`, `CurrentUserDep`, `AdminUserDep` type aliases.

### Phase 4 — Routes (Friday, 2 hours)

11. Implement `routers/books.py` with the six routes. Reference the Lecture 3 patterns for the dependency chain.
12. Boot the server. Use `/docs` to drive every route manually. Confirm each one renders correctly in Swagger UI.

### Phase 5 — Tests (Saturday, 2 hours)

13. Implement `conftest.py`: the test database (in-memory SQLite, per-test scope), the override fixtures.
14. Implement `test_books.py` with the twelve test cases.
15. Run `pytest -q`; iterate until all pass.

### Phase 6 — Write-up and screenshots (Saturday, 1 hour)

16. Write `README.md`.
17. Take screenshots / paste curl outputs.
18. Commit. The portfolio README at `c16-week-07/mini-project/README.md` is the deliverable.

## Reference snippets

### `main.py`

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import SQLModel

from .db import engine
from .routers import books


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="books-api",
    description="Typed FastAPI service over a `books` table.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(books.router)
```

### `routers/books.py` (extract)

```python
from typing import Annotated
from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlmodel import select

from ..deps import AdminUserDep, PaginationDep, SessionDep
from ..models import Book
from ..schemas import BookCreate, BookRead, BookUpdate

router = APIRouter(prefix="/books", tags=["books"])


@router.get("/", response_model=list[BookRead], summary="List books")
async def list_books(
    session: SessionDep,
    pagination: PaginationDep,
    q: Annotated[str | None, Query(default=None, min_length=1, max_length=80)] = None,
    min_year: Annotated[int | None, Query(default=None, ge=1000, le=2100)] = None,
    max_year: Annotated[int | None, Query(default=None, ge=1000, le=2100)] = None,
) -> list[Book]:
    stmt = select(Book)
    if q is not None:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            (Book.title.ilike(like)) | (Book.author_name.ilike(like))
        )
    if min_year is not None:
        stmt = stmt.where(Book.year >= min_year)
    if max_year is not None:
        stmt = stmt.where(Book.year <= max_year)
    stmt = stmt.offset(pagination.skip).limit(pagination.limit)
    result = await session.exec(stmt)
    return result.all()


@router.post(
    "/",
    response_model=BookRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a book",
    response_description="The newly-created book.",
)
async def create_book(
    payload: BookCreate,
    session: SessionDep,
    admin: AdminUserDep,
    response: Response,
) -> Book:
    _ = admin
    book = Book.model_validate(payload)
    session.add(book)
    await session.flush()
    response.headers["Location"] = f"/books/{book.id}"
    return book
```

### `conftest.py` (extract)

```python
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from books_api.auth import User, get_current_user
from books_api.db import get_session
from books_api.main import app


def _admin() -> User:
    return User(id=1, username="test-admin", role="admin")


def _author() -> User:
    return User(id=2, username="test-author", role="author")


@pytest_asyncio.fixture
async def admin_client() -> AsyncGenerator[AsyncClient, None]:
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    test_session_factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False,
    )

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = _admin

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await test_engine.dispose()
```

## Common pitfalls

- **Forgetting `await session.commit()` after the response.** The yield-based dependency handles this; if you write a manual session you have to commit yourself.
- **Returning the SQLModel instance directly without a `response_model`.** Fine for prototyping; in production every route should declare a `response_model` so the contract is enforced on the way out.
- **Letting the test database leak between tests.** Each test should run against a fresh in-memory database, or at least roll back inside a transaction.
- **Forgetting to clear `app.dependency_overrides` after the test.** The next test will see the leaked override and fail mysteriously.
- **`extra="forbid"` rejecting `id` on POST.** That is the point — but make sure your test inputs do not include `id`.
- **The `Location` header missing on the 201 response.** RFC 9110 §10.2.2 expects it; clients use it for "follow new resource".

## The write-up

In `c16-week-07/mini-project/README.md` (your portfolio entry), include:

- A one-paragraph description of the service.
- The `pip install` and `fastapi dev` command to run it.
- A table of routes, methods, and what each one does.
- A short section on what you got from the auto-generated OpenAPI document.
- Pasted output from `curl` of each route (happy path).
- Pasted output of `pytest -q` showing the test count.
- One reflection paragraph on the FastAPI choice: what felt natural, what felt awkward, what you would do differently.

## What this prepares you for

- **Week 8** — async, the GIL, the event loop. We make every line of this service async-correctly, measure the wins, identify the lies.
- **Week 9** — real auth. The `_TOKEN_TABLE` shortcut becomes a proper JWT issuance flow with refresh tokens, Argon2 password hashing, and OIDC login-with-GitHub.
- **Week 10 onward** — Docker, CI, deploy. `books-api` will ride along as the second container in `crunchwriter`'s docker-compose, then get its own CI job, then its own Vercel/Fly/Render deployment.

Ship it.
