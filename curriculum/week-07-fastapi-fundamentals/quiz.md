# Week 7 — Quiz

Ten questions. Lectures closed. One correct answer per question; the answer key is at the end.

---

**Q1.** FastAPI runs on which Python web standard?

- A) WSGI only.
- B) ASGI only.
- C) Both WSGI and ASGI, configurable per app.
- D) Neither — it implements its own protocol on top of `socket`.

---

**Q2.** Inside an `async def` route handler, calling `time.sleep(1.0)` is best described as:

- A) Equivalent to `await asyncio.sleep(1.0)`; the framework converts it.
- B) Slightly slower than `await asyncio.sleep(1.0)`.
- C) A bug: it blocks the event loop for the full second and prevents any other coroutine on this worker from making progress.
- D) Disallowed by FastAPI at import time.

---

**Q3.** You declare a route handler with the signature `def show(article_id: int):` (no `async`). FastAPI:

- A) Refuses to register the route at startup.
- B) Wraps the handler in `async def` automatically.
- C) Runs the handler on the `anyio` thread pool via `to_thread.run_sync`, so the event loop is not blocked.
- D) Runs the handler in the event loop's thread directly, blocking it.

---

**Q4.** Pydantic v2's preferred 2025 syntax for attaching metadata to a field is:

- A) `title: str = Field(min_length=1)` only.
- B) `class Config: min_length = 1` inside the model.
- C) `title: Annotated[str, Field(min_length=1)]`.
- D) `title: constr(min_length=1)`.

---

**Q5.** Calling `Article.model_validate({"title": "x"})` when the model also requires `body`:

- A) Returns an `Article` with `body` defaulting to `""`.
- B) Returns `None`.
- C) Raises `pydantic.ValidationError`, with a list of every missing/invalid field.
- D) Returns a partially-constructed `Article` and warns at runtime.

---

**Q6.** You write `app.dependency_overrides[get_session] = test_get_session` in a test. What changes?

- A) Every request handled by `app` from this point onward calls `test_get_session` instead of `get_session`, until the override is cleared.
- B) Only the next request uses the override; the override is consumed.
- C) The override only affects routes whose handler imports `get_session` directly.
- D) Nothing at runtime; `dependency_overrides` is an OpenAPI hint only.

---

**Q7.** A FastAPI route returns a `RequestValidationError`. The HTTP status code on the response is:

- A) 400 Bad Request.
- B) 409 Conflict.
- C) 422 Unprocessable Content.
- D) 500 Internal Server Error.

---

**Q8.** Per RFC 9110 §11.6.1, a 401 Unauthorized response is required to include:

- A) A `Content-Type: application/json` header.
- B) A `WWW-Authenticate` header field.
- C) A `Retry-After` header with seconds to retry.
- D) A `Location` header pointing at the login page.

---

**Q9.** The OpenAPI document FastAPI generates is served at:

- A) `/swagger.json`.
- B) `/openapi.yaml`.
- C) `/openapi.json`.
- D) `/api/spec`.

---

**Q10.** A yield-based dependency raises an exception inside its setup, before the `yield`. The route handler:

- A) Runs normally; the dependency value is `None`.
- B) Does not run; the setup exception becomes the response error.
- C) Runs in a degraded mode that skips the failed dependency.
- D) Runs with the previous request's cached dependency value.

---

## Answer key

| Question | Answer | Lecture / reference |
|---:|:---|:---|
| Q1 | B | Lecture 1 §1, §2 |
| Q2 | C | Lecture 1 §4 — Claim 3 |
| Q3 | C | Lecture 1 §4 — Starlette's escape hatch |
| Q4 | C | Lecture 2 §2 |
| Q5 | C | Lecture 2 §1 |
| Q6 | A | Lecture 3 §2.4, FastAPI testing-dependencies docs |
| Q7 | C | Lecture 2 §9; RFC 9110 §15.5.21 |
| Q8 | B | Lecture 3 §7; RFC 9110 §11.6.1 |
| Q9 | C | Lecture 3 §6 |
| Q10 | B | Lecture 3 §2.3 and the SOLUTIONS.md Task 9 walk-through |
