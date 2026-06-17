"""
Exercise 3 — Dependency injection, sub-dependencies, and a token-based
auth dependency.

Time:   ~2 hours.
Goal:   Use FastAPI's `Depends` to compose pagination, database session,
        and current-user concerns. Implement an `OAuth2PasswordBearer`-based
        auth dependency that integrates with Swagger UI. Override the auth
        dependency in tests.

Run:
    fastapi dev exercise-03-deps-and-auth-dependency.py

The Swagger UI at /docs will show an "Authorize" button. Click it and use
one of the demo tokens listed below to send authenticated requests
directly from the browser.

Demo tokens (hand-encoded; this is for the exercise only — real token
issuance is C16 Week 9):
    "alice-token"  →  Alice, role=author
    "bob-token"    →  Bob, role=admin
    Anything else  →  401 Unauthorized

Cited:
    - https://fastapi.tiangolo.com/tutorial/dependencies/
    - https://fastapi.tiangolo.com/tutorial/dependencies/sub-dependencies/
    - https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/
    - https://fastapi.tiangolo.com/tutorial/security/first-steps/
    - https://fastapi.tiangolo.com/tutorial/security/get-current-user/
    - https://fastapi.tiangolo.com/advanced/testing-dependencies/
    - RFC 9110 §11.6.1 (WWW-Authenticate)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field

app = FastAPI(
    title="C16 W7 Exercise 3 — Dependencies and auth",
    description=(
        "A small API that demonstrates pagination, session, and auth as "
        "composable dependencies. The auth dependency integrates with "
        "OpenAPI so Swagger UI offers a login form."
    ),
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Part A — A toy "database" session as a yield-based dependency
# ---------------------------------------------------------------------------
#
# Real code uses an async SQLAlchemy session here. The shape is the same:
# yield a resource, then run cleanup after the response. This dependency
# demonstrates the lifecycle without requiring a database.

class FakeSession:
    """In-memory stand-in for a database session."""

    def __init__(self, source: dict[int, dict[str, object]]) -> None:
        self._source = source
        self.closed: bool = False
        self.committed: bool = False
        self.rolled_back: bool = False

    def get(self, key: int) -> dict[str, object] | None:
        return self._source.get(key)

    def all(self) -> list[dict[str, object]]:
        return list(self._source.values())

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


# A single in-process "database table". A real project has one of these per
# entity, populated by SQLAlchemy or SQLModel.
_ARTICLES_TABLE: dict[int, dict[str, object]] = {
    1: {"id": 1, "title": "First", "author_id": 1},
    2: {"id": 2, "title": "Second", "author_id": 1},
    3: {"id": 3, "title": "Third", "author_id": 2},
}


async def get_session() -> AsyncGenerator[FakeSession, None]:
    """
    Yield-based dependency: set up, yield, then tear down.

    On normal completion: commit + close.
    On exception:        rollback + close. The exception is re-raised so
                         FastAPI's error handling still runs.
    """
    session = FakeSession(_ARTICLES_TABLE)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


SessionDep = Annotated[FakeSession, Depends(get_session)]


# ---------------------------------------------------------------------------
# Part B — A pagination dependency, used by every list endpoint
# ---------------------------------------------------------------------------

class Pagination(BaseModel):
    skip: int = Field(ge=0, default=0)
    limit: int = Field(ge=1, le=100, default=20)


async def get_pagination(skip: int = 0, limit: int = 20) -> Pagination:
    # We let Pydantic do the bounds checking; if the values are out of
    # range, Pydantic raises and FastAPI returns 422. (In production we
    # would put `skip` and `limit` directly in Annotated form on each
    # route, but the dependency shape demonstrates the pattern.)
    return Pagination(skip=skip, limit=min(limit, 100))


PaginationDep = Annotated[Pagination, Depends(get_pagination)]


# ---------------------------------------------------------------------------
# Part C — Auth: a token-based dependency and its OpenAPI integration
# ---------------------------------------------------------------------------
#
# OAuth2PasswordBearer is the FastAPI dependency that:
#   (a) parses the "Authorization: Bearer <token>" header,
#   (b) returns the token string,
#   (c) emits the right OpenAPI metadata so Swagger UI offers a login form.
#
# Real token issuance is C16 Week 9. Here, we hand-encode a small lookup
# table; the structure is the same.

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=True)


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: str  # "author" | "admin"


# Demo token table. In production this is a JWT decode plus a DB lookup.
_TOKEN_TABLE: dict[str, User] = {
    "alice-token": User(id=1, username="alice", role="author"),
    "bob-token": User(id=2, username="bob", role="admin"),
}


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    """
    Validate the token. Return the user object on success.
    On failure, return 401 with the RFC-9110-required WWW-Authenticate
    header so clients know the auth scheme to retry.
    """
    user = _TOKEN_TABLE.get(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unknown token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def require_admin(current_user: CurrentUserDep) -> User:
    """Sub-dependency: only admins pass."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user


AdminUserDep = Annotated[User, Depends(require_admin)]


# ---------------------------------------------------------------------------
# Part D — Routes that consume the dependencies
# ---------------------------------------------------------------------------

@app.get("/whoami", tags=["meta"])
async def whoami(current_user: CurrentUserDep) -> dict[str, object]:
    """The simplest auth-protected route: returns the caller's identity."""
    return {"id": current_user.id, "username": current_user.username, "role": current_user.role}


@app.get("/articles", tags=["articles"])
async def list_articles(
    session: SessionDep,
    pagination: PaginationDep,
    current_user: CurrentUserDep,
) -> dict[str, object]:
    items: list[dict[str, object]] = session.all()
    page: list[dict[str, object]] = items[pagination.skip : pagination.skip + pagination.limit]
    return {
        "viewer": current_user.username,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": len(items),
        "items": page,
    }


@app.get("/articles/{article_id}", tags=["articles"])
async def get_article(
    article_id: int,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> dict[str, object]:
    article = session.get(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
    return {"viewer": current_user.username, "article": article}


@app.delete(
    "/articles/{article_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["articles"],
)
async def delete_article(
    article_id: int,
    session: SessionDep,
    admin: AdminUserDep,  # only admins
) -> None:
    if article_id not in _ARTICLES_TABLE:
        raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
    # We do not actually mutate the shared table in this exercise; the
    # point is that the dependency chain enforced admin-only access.
    _ = admin
    return None


# ---------------------------------------------------------------------------
# Part E — Test seam: dependency overrides
# ---------------------------------------------------------------------------
#
# The functions below are NOT routes. They are reference implementations of
# the overrides we will use in tests. The mini-project's conftest.py wires
# them up.
#
# The pattern:
#
#     app.dependency_overrides[get_current_user] = lambda: fake_admin
#
# In a test, this replaces the real auth dependency with a function that
# returns a known user. No HTTP header parsing, no token validation —
# every protected route is callable with a fake identity.

def fake_admin() -> User:
    return User(id=99, username="test-admin", role="admin")


def fake_author() -> User:
    return User(id=98, username="test-author", role="author")


def fake_session_factory() -> FakeSession:
    """Return a fresh FakeSession. Useful in tests that mutate state."""
    return FakeSession({1: {"id": 1, "title": "Test fixture", "author_id": 99}})


# ---------------------------------------------------------------------------
# Exercise tasks
# ---------------------------------------------------------------------------
#
# 1. Start the server. Open /docs. Find the "Authorize" button (top right).
#    Click it. Enter username/password — both can be empty for this demo,
#    BUT the token field is what matters for our scheme. Actually:
#       OAuth2PasswordBearer wires the password flow into Swagger. Since
#       we have not built the /auth/token endpoint, the Authorize button's
#       login will fail. Instead, send tokens via curl:
#
#       curl -H 'Authorization: Bearer alice-token' http://localhost:8000/whoami
#       curl -H 'Authorization: Bearer bob-token'   http://localhost:8000/whoami
#       curl -H 'Authorization: Bearer wrong'       http://localhost:8000/whoami
#       # The last one returns 401 with WWW-Authenticate: Bearer
#
# 2. GET /articles without an Authorization header. Note the 401 and
#    confirm the response includes the WWW-Authenticate header.
#
# 3. GET /articles with the Alice token. Confirm 200; note that
#    `viewer: "alice"` is in the response, proving the dependency
#    resolved and the user was made available to the handler.
#
# 4. DELETE /articles/1 with Alice's token (author). Confirm 403.
#    DELETE /articles/1 with Bob's token (admin). Confirm 204.
#
# 5. GET /articles?skip=0&limit=200 with any valid token. Confirm 422 —
#    Pydantic rejects limit > 100. Inspect the error's `loc` array.
#
# 6. Read /openapi.json. Find:
#       - components.securitySchemes.OAuth2PasswordBearer
#       - paths./articles.get.security
#    Note that each protected route declares its security in the spec.
#    The unsigned /docs cannot see the demo tokens; the OpenAPI document
#    accurately says "this endpoint requires the OAuth2 password flow".
#
# 7. Write a small unit test (in a separate file) that uses
#    app.dependency_overrides to swap get_current_user for fake_admin,
#    then asserts that DELETE /articles/1 returns 204 with no header.
#    The pattern:
#
#       app.dependency_overrides[get_current_user] = fake_admin
#       async with AsyncClient(transport=ASGITransport(app=app),
#                              base_url="http://test") as ac:
#           response = await ac.delete("/articles/1")
#           assert response.status_code == 204
#       app.dependency_overrides.clear()
#
# 8. Read RFC 9110 §11.6.1 on the WWW-Authenticate header. State, in your
#    own words, why a 401 response that lacks this header is technically
#    a protocol violation.
#
# 9. Read https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/
#    Find the section on "yield with except". Compare to our get_session
#    implementation. What does FastAPI guarantee about exceptions raised
#    inside the route handler vs exceptions raised by sub-dependencies?
#
# Write the answers as `exercises/03-deps.md` and commit.
