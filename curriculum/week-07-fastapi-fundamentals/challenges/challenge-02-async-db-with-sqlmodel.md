# Challenge 2 — Async database access with SQLModel + asyncpg

> **Time:** ~1 hour. **Difficulty:** moderate.
> **Goal:** Connect `crunchreader-api` to the same Postgres database `crunchwriter` writes to, using `SQLModel` over `asyncpg`. Implement a yield-based session dependency, write three read endpoints (list, get, count), and prove that the queries actually run async by inspecting `EXPLAIN ANALYZE` plus the SQLAlchemy echo log.

This challenge is the first half of the mini-project. Finishing it early gives you a working data layer before Thursday and turns the mini-project into "just add the schemas and tests".

## Why SQLModel (and not SQLAlchemy directly, and not Django ORM)

Three reasons to pick SQLModel for this challenge:

1. **It is Pydantic-aware.** SQLModel classes *are* Pydantic models. A single class can be both the database row and the response schema, when that is appropriate (it often is not — separate schemas are still the better pattern; see Lecture 2 §6). For lookups where the database column shape *is* the API shape, you save a translation layer.
2. **Async support is first-class.** SQLAlchemy 2.0's async extension is mature; SQLModel layers on top. The same model class works under sync and async sessions.
3. **It is by the same author as FastAPI.** The docs, the patterns, the version pinning all line up. There is no "FastAPI says A, but the SQLModel docs say B" friction.

Django's ORM has async support since Django 4.1, but it is awkward in a FastAPI app — it requires `sync_to_async` shims, and the ORM is tightly coupled to the Django app loading dance. The right architecture for `crunchwriter` is: Django keeps its ORM for the writer surface; the reader surface uses SQLModel against the same tables.

## Specification

### Files to produce

```text
crunchreader-api/
├── pyproject.toml
├── alembic.ini                   (optional; only if you generate migrations)
├── crunchreader/
│   ├── __init__.py
│   ├── main.py                   FastAPI entry; mounts the routers
│   ├── settings.py               DATABASE_URL via env
│   ├── db.py                     engine, sessionmaker, get_session
│   ├── models.py                 SQLModel definitions (read-only views)
│   ├── schemas.py                Pydantic Read schemas (separate from models)
│   └── routers/
│       ├── __init__.py
│       └── articles.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    └── test_articles.py
```

### `db.py`

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from .settings import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

_async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=SQLModelAsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[SQLModelAsyncSession, None]:
    session: SQLModelAsyncSession = _async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
```

### `models.py`

```python
from datetime import datetime
from sqlmodel import Field, SQLModel


class WriterArticle(SQLModel, table=True):
    __tablename__ = "writer_article"  # match Django's auto-generated name

    id: int | None = Field(default=None, primary_key=True)
    title: str
    body: str
    slug: str
    author_id: int = Field(foreign_key="auth_user.id")
    created_at: datetime
    published_at: datetime | None = None
    is_draft: bool = True
    # ...add the columns you need; ignore the rest
```

Read-only access means we do not need every column.

### `routers/articles.py`

Three endpoints, all `async def`:

- `GET /articles` — paginated list, default `skip=0&limit=20&limit_max=100`, returns `list[ArticleRead]`.
- `GET /articles/{article_id}` — one article by id; 404 if absent. Returns `ArticleRead`.
- `GET /articles/count` — `{"total": <int>}`. Read-only, no body.

Every query uses `await session.exec(select(...))` (the SQLModel pattern) or `await session.execute(select(...))` (the SQLAlchemy pattern). Both yield a result; `.all()` / `.first()` materialise.

## Verification

### Local Postgres

The Django side already has the table. The FastAPI side connects to the same database:

```bash
# .env
DATABASE_URL=postgresql+asyncpg://crunchwriter_user:dev_password@localhost:5432/crunchwriter
SQL_ECHO=true
```

The `+asyncpg` selects the asyncpg driver. Confirm `asyncpg` is in your `requirements.txt`.

### The "is it actually async" test

Set `SQL_ECHO=true` (or `echo=True` on the engine) so SQLAlchemy logs every query. Run the server. Issue concurrent requests:

```bash
# Hit two endpoints "at once" — actually one ms apart, but that is enough
curl http://localhost:8000/articles &
curl http://localhost:8000/articles/count &
wait
```

In the server log, the two queries should be **interleaved** — request A starts, request A awaits the database, request B starts before request A's response is sent. If you see request A fully complete before request B begins, you have accidentally re-introduced sync behaviour somewhere (most commonly: using `psycopg2` instead of `asyncpg`, or a missing `await` in the route handler).

### EXPLAIN ANALYZE

Pick one of your endpoints. Inside `psql`, run:

```sql
EXPLAIN ANALYZE
SELECT id, title, slug, author_id, created_at FROM writer_article
ORDER BY created_at DESC
LIMIT 20;
```

Confirm the plan uses the index on `created_at` (if you do not have one, add one — this is part of "real" performance work and Week 4 already taught you how to read the plan).

## Acceptance criteria

- [ ] `crunchreader-api/crunchreader/` package exists with the file layout above.
- [ ] `python3 -m py_compile crunchreader/**/*.py` is clean.
- [ ] Type hints on every function, including async return types and yield-based dependency signatures (`AsyncGenerator[T, None]`).
- [ ] `GET /articles` returns a JSON array of articles from the live Postgres database. Confirm by inserting one row in `crunchwriter` and seeing it in the FastAPI response.
- [ ] `GET /articles/{id}` returns 200 for an existing id and 404 for a missing one. The 404 detail says "Article {id} not found".
- [ ] `GET /articles/count` returns `{"total": <int>}` matching `SELECT count(*) FROM writer_article`.
- [ ] At least one request in the SQL echo log shows `BEGIN; SELECT ... ; COMMIT;` framing — proving the yield-based session committed.
- [ ] A test in `tests/test_articles.py` exercises all three endpoints. The test uses a separate Postgres schema or test database (or `SQLite` for speed, with an `aiosqlite` driver).

## Stretch goals

- **`select_related` equivalent.** Use `selectinload(WriterArticle.author)` to eager-load the author in one query rather than N. Read the SQLAlchemy docs on `selectinload` vs `joinedload`: <https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html>.
- **Cursor pagination.** Replace `skip/limit` with `after=<id>` cursor pagination. Discuss in the write-up why cursor pagination is the correct choice for an API that mutates the underlying list while consumers paginate.
- **Connection pooling under `--workers 4`.** Each `uvicorn` worker has its own engine, its own pool. Compute the total Postgres connection count and compare to your Postgres `max_connections`. Document the calculation.

## Cited

- SQLModel: <https://sqlmodel.tiangolo.com/>
- SQLAlchemy 2.0 async: <https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html>
- FastAPI SQL databases tutorial: <https://fastapi.tiangolo.com/tutorial/sql-databases/>
- `asyncpg`: <https://magicstack.github.io/asyncpg/current/>
- `aiosqlite` (for tests): <https://github.com/omnilib/aiosqlite>
