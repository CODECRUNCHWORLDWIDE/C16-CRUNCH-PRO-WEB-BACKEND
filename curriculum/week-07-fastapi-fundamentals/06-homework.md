# Week 7 — Homework

Six problems, approximately **6 hours total**. The point of homework is to practise the patterns; the point of the mini-project is to integrate them. These problems should each have a short Python file or a short Markdown answer; the writing matters as much as the code.

Save each answer to `c16-week-07/homework/` in your `crunchreader-api` repo.

---

## Problem 1 — A minimal ASGI app, by hand (45 min)

Write `homework/01_raw_asgi.py` containing an ASGI application that returns `text/plain` with the body `"hello, ASGI"` for any HTTP path. The app is `async def app(scope, receive, send) -> None`. No FastAPI, no Starlette — only the standard library.

Run with `uvicorn homework.01_raw_asgi:app`.

In `homework/01_raw_asgi.md`, answer:

1. What is the value of `scope["type"]` for the first call your app receives at startup (before any HTTP requests)?
2. What two `send` events did you emit for the HTTP response, in order?
3. If a client sends a request with `Content-Length: 1000000`, what is in the first `http.request` event your app receives via `await receive()`? Specifically: is the full body in the first event, or chunked?

Reference: <https://asgi.readthedocs.io/en/latest/specs/www.html>.

---

## Problem 2 — Two schemas per resource (45 min)

In `homework/02_schemas.py`, declare four Pydantic models for a "Comment" resource:

- `CommentBase` — fields shared by all.
- `CommentCreate` — body of `POST /articles/{id}/comments`.
- `CommentUpdate` — body of `PATCH /articles/{id}/comments/{cid}`; every field optional.
- `CommentRead` — response shape.

Constraints:

- `body` is required, 1-2000 chars, on every model except `CommentUpdate` (where it is optional).
- `is_anonymous: bool = False` on `CommentCreate`; not on `CommentRead`.
- `CommentRead` has `id`, `author_name`, `created_at`, and `article_id` — all server-set.

In `homework/02_schemas.md`, write the answers to:

1. Why is `CommentCreate` not allowed to specify `id` or `created_at`? Give a security argument and a correctness argument.
2. If `CommentRead` carried `is_anonymous: bool`, what would the server have to do on retrieval to honour it? Is that worth the schema complexity?
3. Run `python3 -c "from homework._02_schemas import CommentCreate; print(CommentCreate.model_json_schema())"` and paste the output. Identify the `required` array.

(Note: rename the file to a valid module name like `_02_schemas.py` for the import to work; Python module names cannot start with a digit.)

---

## Problem 3 — Three integration tests (45 min)

Pick three routes from `exercises/exercise-01-hello-fastapi.py`. Write `homework/03_tests.py` containing three `pytest-asyncio` tests:

- One happy-path 200/201.
- One validation failure 422.
- One 404 from an unknown id.

Use `httpx.AsyncClient(transport=ASGITransport(app=app))`. Set `asyncio_mode = "auto"` in a local `pyproject.toml` snippet or use `@pytest.mark.asyncio` per test.

In `homework/03_tests.md`, answer:

1. Why does `ASGITransport` avoid the need for a real HTTP server in tests?
2. What is the difference between this style and `fastapi.testclient.TestClient` (sync wrapper)?
3. What state leaks between tests in this exercise, and how would you isolate it? (Hint: the in-memory `_ARTICLES` dict.)

---

## Problem 4 — Read the FastAPI source (45 min)

Open `fastapi/routing.py` in the FastAPI source: <https://github.com/fastapi/fastapi/blob/master/fastapi/routing.py>.

Find the function `get_request_handler` (or, in newer versions, the `APIRoute.get_route_handler` method that returns `app`).

In `homework/04_source.md`:

1. Quote the four phases of the per-request flow (body, dependencies, endpoint, response). Reference the line numbers.
2. Find where `RequestValidationError` is raised. Why is it raised there and not later, in the endpoint call?
3. Find where the response is serialised. What function is called on the return value of the endpoint?

The goal is not to memorise the source but to demystify it. After 45 minutes you should be able to say: "FastAPI's per-request handler is a small function I have read; everything else is data plumbed through Pydantic and Starlette."

---

## Problem 5 — RFC 9110 §15.3 (status code semantics) (45 min)

Read RFC 9110 §15.3 in full (the 2xx Successful section): <https://datatracker.ietf.org/doc/html/rfc9110#section-15.3>.

In `homework/05_status_codes.md`, write one paragraph for each of these status codes, explaining what the spec says and when you would use it in a FastAPI handler:

- 200 OK
- 201 Created (and the `Location` header expectation)
- 202 Accepted
- 204 No Content
- 206 Partial Content

For each, write the FastAPI decorator argument you would use:

```python
@app.post("/x", status_code=201)
```

Include the import (`from fastapi import status`) and the named constant (`status.HTTP_201_CREATED`) — named constants are easier to grep.

---

## Problem 6 — Compare FastAPI, Flask + flask-pydantic, and Django REST Framework (1.5 h)

In `homework/06_framework_compare.md`, write a structured comparison:

For one canonical endpoint — `POST /articles` with body validation and a typed response — show three implementations:

- FastAPI with Pydantic (your reference)
- Flask 3 with `flask-pydantic`
- Django 5 + Django REST Framework

For each, evaluate on five dimensions:

1. Lines of code for the route + validation.
2. How the OpenAPI document is generated (or not).
3. How a request body is validated (where the validation lives).
4. How the response shape is enforced (or not).
5. The migration cost to add a second route.

Conclude with a one-paragraph defence of your choice for `crunchreader-api` and a one-paragraph honest critique. The defence should not be "FastAPI is fast"; it should be "for a typed JSON-only service over an existing database, FastAPI's coupling of routing-to-Pydantic-to-OpenAPI is uniquely suited because …". The critique should mention at least one Django REST Framework strength FastAPI does not match.

Reference reading:

- `flask-pydantic`: <https://github.com/bauerji/flask-pydantic>
- Django REST Framework: <https://www.django-rest-framework.org/>
- FastAPI's own comparison page (biased but accurate on technical points): <https://fastapi.tiangolo.com/alternatives/>

---

## Submission

All six problems live under `c16-week-07/homework/` in `crunchreader-api`. Commit with a single message like:

```text
c16-w7 homework: ASGI, schemas, tests, source reading, status codes, framework compare
```

The grader looks for: every prompt answered, every code file `py_compile`-clean, every citation linked.
