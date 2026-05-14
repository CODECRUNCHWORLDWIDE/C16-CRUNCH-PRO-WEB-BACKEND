"""
Exercise 1 — Hello, FastAPI: typed routes, query/path/body parameters.

Time:   ~2 hours.
Goal:   Build a minimal FastAPI app that exercises every parameter source
        FastAPI distinguishes: path, query, header, and body. Confirm that
        path/query types are validated automatically, that bodies are parsed
        from JSON into Pydantic models, and that the generated /docs page
        reflects everything declared in the route signature.

Run:
    fastapi dev exercise-01-hello-fastapi.py
    # or:
    uvicorn exercise-01-hello-fastapi:app --reload

Visit:
    http://localhost:8000/docs        — interactive Swagger UI
    http://localhost:8000/redoc       — alternative renderer
    http://localhost:8000/openapi.json — the raw OpenAPI 3.1 document

Curl examples are inside each section.

Cited:
    - https://fastapi.tiangolo.com/tutorial/first-steps/
    - https://fastapi.tiangolo.com/tutorial/path-params/
    - https://fastapi.tiangolo.com/tutorial/query-params/
    - https://fastapi.tiangolo.com/tutorial/body/
    - https://fastapi.tiangolo.com/tutorial/response-status-code/
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Part A — The app itself
# ---------------------------------------------------------------------------
#
# We give the app metadata that lands in the OpenAPI document. Compare the
# title and description at /docs after running the server.

app = FastAPI(
    title="C16 W7 Exercise 1 — Hello FastAPI",
    description=(
        "A minimal FastAPI app that exercises every parameter source: path, "
        "query, header, and body. The handlers are intentionally trivial; "
        "the point is the wiring."
    ),
    version="0.1.0",
)


# In-memory store. Real persistence is the mini-project's problem.
_ARTICLES: dict[int, dict[str, object]] = {}
_NEXT_ID: dict[str, int] = {"v": 1}


# ---------------------------------------------------------------------------
# Part B — Pydantic schemas
# ---------------------------------------------------------------------------
#
# Two schemas per resource: ArticleCreate for the request body, ArticleRead
# for the response. The shared base holds the fields they have in common.

class ArticleBase(BaseModel):
    """Fields shared by both request and response."""

    title: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200,
            description="The article title.",
            examples=["Hello, FastAPI"],
        ),
    ]
    body: Annotated[
        str,
        Field(min_length=1, description="The article body in markdown."),
    ]


class ArticleCreate(ArticleBase):
    """Body of POST /articles. No id, no created_at — those are server-set."""

    pass


class ArticleRead(ArticleBase):
    """Response shape for GET and POST. Includes server-set fields."""

    model_config = ConfigDict(from_attributes=True)
    id: int = Field(description="Server-assigned identifier.")
    created_at: datetime = Field(description="UTC timestamp the article was created.")


# ---------------------------------------------------------------------------
# Part C — Route 1: a path parameter with type validation
# ---------------------------------------------------------------------------
#
#   curl -i http://localhost:8000/articles/1
#   curl -i http://localhost:8000/articles/abc   # → 422, type validation fails
#   curl -i http://localhost:8000/articles/0     # → 422, ge=1 fails
#
# Notes:
#   - `article_id: Annotated[int, Path(ge=1)]` tells FastAPI to:
#       (a) parse the URL segment as int,
#       (b) validate that it is >= 1.
#   - `response_model=ArticleRead` enforces the response shape via Pydantic
#     on the way out, in addition to the inbound validation.
#   - `status_code=status.HTTP_200_OK` is the default for GET; we spell it
#     out so the convention is visible.

@app.get(
    "/articles/{article_id}",
    response_model=ArticleRead,
    status_code=status.HTTP_200_OK,
    summary="Get one article",
    description="Returns the article with the given id, or 404 if not found.",
    tags=["articles"],
)
async def get_article(
    article_id: Annotated[int, Path(ge=1, description="The article id.")],
) -> dict[str, object]:
    article = _ARTICLES.get(article_id)
    if article is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article {article_id} not found",
        )
    return article


# ---------------------------------------------------------------------------
# Part D — Route 2: query parameters with defaults and constraints
# ---------------------------------------------------------------------------
#
#   curl -i 'http://localhost:8000/articles?skip=0&limit=20'
#   curl -i 'http://localhost:8000/articles?limit=500'  # → clamped via le=100
#   curl -i 'http://localhost:8000/articles?q=hello'
#
# Notes:
#   - skip and limit have defaults; FastAPI marks them optional in the
#     OpenAPI document.
#   - q is Annotated[str | None, ...]; passing nothing gives None.
#   - The ordering of parameters in the function signature does not affect
#     the URL; ordering in the @app.get path string does.

@app.get(
    "/articles",
    response_model=list[ArticleRead],
    summary="List articles",
    tags=["articles"],
)
async def list_articles(
    skip: Annotated[int, Query(ge=0, description="Number of items to skip.")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Max items to return.")] = 20,
    q: Annotated[
        str | None,
        Query(min_length=1, max_length=80, description="Optional full-text filter."),
    ] = None,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = list(_ARTICLES.values())
    if q is not None:
        items = [
            a
            for a in items
            if q.lower() in str(a["title"]).lower() or q.lower() in str(a["body"]).lower()
        ]
    return items[skip : skip + limit]


# ---------------------------------------------------------------------------
# Part E — Route 3: a request body parsed from JSON via Pydantic
# ---------------------------------------------------------------------------
#
#   curl -i -X POST http://localhost:8000/articles \
#       -H 'Content-Type: application/json' \
#       -d '{"title": "Hello", "body": "world"}'
#
#   # Validation failure — title is empty:
#   curl -i -X POST http://localhost:8000/articles \
#       -H 'Content-Type: application/json' \
#       -d '{"title": "", "body": "world"}'
#   # → 422 with a detail array listing the failing field
#
# Notes:
#   - `payload: ArticleCreate` is enough for FastAPI to recognise the body.
#     No `Body(...)` marker needed for Pydantic model types.
#   - status_code=201 because we created a resource (RFC 9110 §15.3.2).
#   - We return the freshly-created object so the client gets the assigned
#     id and timestamp without a second round trip.

@app.post(
    "/articles",
    response_model=ArticleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an article",
    response_description="The newly-created article.",
    tags=["articles"],
)
async def create_article(payload: ArticleCreate) -> dict[str, object]:
    new_id: int = _NEXT_ID["v"]
    _NEXT_ID["v"] = new_id + 1
    article: dict[str, object] = {
        "id": new_id,
        "title": payload.title,
        "body": payload.body,
        "created_at": datetime.now(tz=timezone.utc),
    }
    _ARTICLES[new_id] = article
    return article


# ---------------------------------------------------------------------------
# Part F — Route 4: a header parameter
# ---------------------------------------------------------------------------
#
#   curl -i http://localhost:8000/whoami \
#       -H 'X-Request-Id: abc-123' \
#       -H 'User-Agent: curl/8.0'
#
# Notes:
#   - Header parameters use the `Header(...)` marker.
#   - FastAPI converts hyphenated header names to snake_case by default
#     (`x_request_id` → reads `X-Request-Id`). The `alias=` argument lets
#     you override if you do not want the conversion.
#   - Headers are case-insensitive per RFC 9110 §5.1.

@app.get(
    "/whoami",
    summary="Echo back identifying request headers",
    tags=["meta"],
)
async def whoami(
    user_agent: Annotated[str | None, Header()] = None,
    x_request_id: Annotated[str | None, Header()] = None,
) -> dict[str, str | None]:
    return {"user_agent": user_agent, "request_id": x_request_id}


# ---------------------------------------------------------------------------
# Part G — Route 5: explicit 204 No Content for delete
# ---------------------------------------------------------------------------
#
#   curl -i -X DELETE http://localhost:8000/articles/1
#   # 204 with an empty body; nothing to deserialise.
#
# Notes:
#   - 204 explicitly says "no body" (RFC 9110 §15.3.5). FastAPI will not
#     serialise a return value into the response.
#   - We return None (implicitly, by not returning anything) to keep the
#     type annotation honest.

@app.delete(
    "/articles/{article_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an article",
    tags=["articles"],
)
async def delete_article(
    article_id: Annotated[int, Path(ge=1)],
) -> None:
    if article_id not in _ARTICLES:
        raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
    del _ARTICLES[article_id]
    return None


# ---------------------------------------------------------------------------
# Part H — Health check at the root
# ---------------------------------------------------------------------------

@app.get("/", summary="Health check", tags=["meta"])
async def root() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Exercise tasks (do these in order; write answers in a Markdown note)
# ---------------------------------------------------------------------------
#
# 1. Start the server with `fastapi dev exercise-01-hello-fastapi.py`.
#    Open /docs. Locate every route declared above. Confirm:
#       - GET /articles/{article_id} shows article_id as a path parameter
#         with type integer and minimum 1.
#       - GET /articles shows three query parameters with defaults.
#       - POST /articles shows a request body schema named ArticleCreate.
#       - DELETE /articles/{article_id} shows the 204 response code.
#       - GET /whoami shows User-Agent and X-Request-Id as headers.
#    Take a screenshot of /docs OR paste the JSON for one route from
#    /openapi.json into your write-up.
#
# 2. POST one article. Note the assigned id and created_at in the response.
#    GET it back by id; confirm the same values round-trip.
#
# 3. POST a body with `"title": ""`. Confirm the 422 response.
#    Read the `detail` array and find the field that failed.
#
# 4. GET /articles with `limit=500`. Confirm the 422 response.
#    Now GET with `limit=100`; confirm it succeeds.
#
# 5. GET /articles/abc. Confirm the 422 response (type validation, not 404).
#
# 6. Read the /openapi.json document end to end. Find:
#       - components.schemas.ArticleCreate
#       - components.schemas.ArticleRead
#       - paths./articles.post.requestBody
#       - paths./articles.get.parameters
#    Identify three differences between ArticleCreate and ArticleRead in
#    the schema.
#
# 7. Read RFC 9110 §15.3.2 (201 Created) and §15.3.5 (204 No Content).
#    Note what each one says about the response body, and confirm
#    FastAPI's behaviour matches.
#
# Write the answers to all seven prompts as `exercises/01-hello.md` in
# your `crunchreader-api` repo and commit.
