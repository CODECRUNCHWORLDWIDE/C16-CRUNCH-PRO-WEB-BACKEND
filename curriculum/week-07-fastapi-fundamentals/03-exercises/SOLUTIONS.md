# Exercises — Worked solutions

These are walk-throughs of the trickier prompts in each exercise. Read after you have tried the prompt yourself; the value is in the contrast between your answer and ours, not in the answer itself.

---

## Exercise 1 — Hello, FastAPI

### Task 3 — The 422 response on empty title

A POST with `{"title": "", "body": "world"}` returns HTTP 422 with this body:

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "title"],
      "msg": "String should have at least 1 character",
      "input": "",
      "ctx": {"min_length": 1}
    }
  ]
}
```

Three things to notice:

- The status code is **422**, not 400. 400 is "your JSON is malformed"; 422 is "your JSON parsed fine but a field is semantically wrong". RFC 9110 §15.5.21.
- The `loc` array is `["body", "title"]` — the path from the response to the failing field. `body` is the request body, `title` is the field. For a query parameter, `loc` would start with `query`. For a path parameter, with `path`.
- The `input` field echoes what the client sent. This is convenient for debugging but exposes the input to anyone who can see the response. For a production API that hides the request body for privacy or PII reasons, you would override the `RequestValidationError` handler and strip `input`.

### Task 6 — Three differences between `ArticleCreate` and `ArticleRead`

From `/openapi.json`, comparing `components.schemas.ArticleCreate` and `components.schemas.ArticleRead`:

1. **`ArticleRead` has `id` and `created_at`; `ArticleCreate` does not.** These are server-assigned; clients cannot set them. Putting them in `ArticleCreate` would allow an attacker to specify the id on a `POST`.
2. **`ArticleRead.required` lists every field**; `ArticleCreate.required` lists only `title` and `body`. The server guarantees every read article has an id, a created_at, and a non-null title and body. The client only has to provide title and body.
3. **`ArticleRead` may, depending on the project, include denormalised fields** (e.g. `author_name`) that `ArticleCreate` cannot meaningfully accept. In this exercise the two schemas share the same shape for title and body, but the principle scales: response shapes carry whatever the consumer needs; request shapes carry only what the producer can supply.

### Task 7 — RFC 9110 on 201 and 204

- **§15.3.2 (201 Created)** — "The 201 (Created) status code indicates that the request has been fulfilled and has resulted in one or more new resources being created. … The primary resource created by the request is identified by either a Location header field in the response or, if no Location header field is received, by the effective request URI." Best practice: include a `Location` header pointing at `/articles/{new_id}`. FastAPI does not do this automatically; you would add `response.headers["Location"] = f"/articles/{new_id}"` or use `response_class=Response` with the header set manually.
- **§15.3.5 (204 No Content)** — "The 204 (No Content) status code indicates that the server has successfully fulfilled the request and that there is no additional content to send in the response content. … A 204 response is terminated by the end of the header section; it cannot contain content or trailers." FastAPI enforces this: returning a value from a `status_code=204` handler results in the body being dropped, with a runtime warning.

---

## Exercise 2 — Pydantic v2 validation

### Task 4 — The model-level validator's `loc`

When `draft_publish_consistency` raises, the 422 body is:

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body"],
      "msg": "Value error, drafts may not have a published_at; clear it or set is_draft=false",
      "input": {"...": "..."}
    }
  ]
}
```

The `loc` is `["body"]` — the *whole body*, not a single field. Model-level validation cannot point to one field because the error is a *relationship* between fields. Clients that try to highlight the failing field in a form need to fall back to a body-level error message in this case.

### Task 9 — Converting `tags_non_empty` to `mode="before"`

The `after` version receives a `list[str]` because Pydantic has already coerced inputs to the declared type. The `before` version receives the raw input, which might be `None`, a string, a dict, or anything else the client sent. A safe `before` version:

```python
@field_validator("tags", mode="before")
@classmethod
def tags_non_empty(cls, value: object) -> object:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("tags must be a list of strings")
    cleaned: list[str] = []
    for t in value:
        if not isinstance(t, str):
            raise ValueError("each tag must be a string")
        stripped = t.strip()
        if stripped == "":
            raise ValueError("each tag must be a non-empty string")
        cleaned.append(stripped.lower())
    return sorted(set(cleaned))
```

When to choose which:

- **`mode="after"`** when you trust Pydantic's type coercion and just want to add a semantic rule on top.
- **`mode="before"`** when the input format is ambiguous (multiple shapes accepted) or when you need to handle types Pydantic does not coerce out of the box.

### Task 10 — `@field_serializer` alternative

Two alternatives:

1. **`@model_serializer`** — replace the entire model's serialisation, not just one field. Useful when the on-wire shape is fundamentally different from the in-memory shape.
2. **`model_dump(mode="json")`** — Pydantic's default JSON-mode serialisation already converts `datetime` to ISO 8601. The reason we customised was to drop the microseconds and force the `Z` suffix; if the default is acceptable, no serialiser is needed at all.

In practice, `@field_serializer` is the right choice for "format one field differently"; `@model_serializer` is for "the whole response is shaped differently than the model fields imply".

---

## Exercise 3 — Dependencies and auth

### Task 7 — The test pattern

The full test, in `tests/test_dependencies.py`:

```python
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    pass  # only type-checking imports here

# Imports from the exercise module — rename the file to a valid Python
# module name (e.g., exercise_03.py) before running the test.
from exercise_03 import app, fake_admin, get_current_user


@pytest_asyncio.fixture
async def admin_client() -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_current_user] = fake_admin
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_admin_can_delete(admin_client: AsyncClient) -> None:
    response = await admin_client.delete("/articles/1")
    assert response.status_code == 204
    assert response.text == ""


async def test_unknown_id_is_404(admin_client: AsyncClient) -> None:
    response = await admin_client.delete("/articles/99999")
    assert response.status_code == 404
```

Three observations:

- The override is installed *before* the client is constructed, and cleared *after* the client goes out of scope. The fixture handles both. Tests that forget the cleanup leak overrides into the next test, which is the most common cause of "the test passes alone and fails in the suite".
- The dependency override replaces `get_current_user`, not `oauth2_scheme`. `oauth2_scheme` is one level deeper; overriding `get_current_user` shortcuts both the header parsing and the token validation in one step. This is the right scope.
- No `pytest.mark.asyncio` is needed if `asyncio_mode = "auto"` is set in `pyproject.toml`.

### Task 8 — Why a 401 without `WWW-Authenticate` is a protocol violation

RFC 9110 §11.6.1: "A server generating a 401 (Unauthorized) response **MUST** send a WWW-Authenticate header field." (Emphasis in original.) The `MUST` in an RFC means non-compliance; clients that follow the spec — curl, well-behaved HTTP libraries, and Swagger UI itself — use this header to know which authentication scheme to retry with. A 401 without it leaves the client guessing.

In practice many servers omit it. The cost is small for browser-driven flows (the user just sees "401" and gives up) but real for programmatic clients that retry automatically against credential stores. Always set the header on 401 responses.

### Task 9 — Exceptions in yield-based dependencies

From <https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/>:

- An exception raised in the **route handler** propagates back through `yield` in the dependency. The `except` block (if present) catches it; the `finally` block runs in any case. After the dependency's cleanup, the exception continues up the stack and FastAPI's error handlers see it.
- An exception raised in the **teardown** (after `yield`) is caught by FastAPI and turned into a 500-level response. The teardown should not raise on normal paths; if it does, the response will reflect the teardown error, not the original success.
- An exception raised in **setup** (before `yield`) prevents the route handler from running. The exception becomes the response error.

The practical implication: write `commit` after `yield` *outside* the `try/except` of the setup, and put `rollback` inside the `except` and `close` inside `finally`. Our `get_session` follows this pattern.
