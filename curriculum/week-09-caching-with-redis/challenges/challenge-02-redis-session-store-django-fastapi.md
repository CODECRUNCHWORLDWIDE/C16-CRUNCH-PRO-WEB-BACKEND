# Challenge 2 — Redis session store: Django + FastAPI side by side

> Build a Redis-backed session store in both Django and FastAPI for the same user-facing flow (login, profile read, logout, session expiry). Document the surface-area difference in a `COMPARISON.md`. Defend a choice of "if I were starting greenfield, I would pick X" with three concrete reasons.

**Time:** 2 hours. **Deliverables:** Two minimal apps (`django_app/`, `fastapi_app/`) plus a `COMPARISON.md`.

## Why two implementations

The framework you reach for is rarely a question of "which is better" — it is a question of which is right for the team and the constraints. The session-store work is a small enough surface to put both side by side and see what each one gives you and what each one asks of you. By the end, you can defend your default choice in an interview without hand-waving.

## What the two apps must do

The user-facing API is identical between the two implementations:

| Route                     | Method | Behaviour                                                                          |
|---------------------------|--------|-------------------------------------------------------------------------------------|
| `/login`                  | POST   | Body `{"username": "..."}`. Creates a session with `user` and `login_at`. 200.    |
| `/profile`                | GET    | Returns the session contents. 200 if logged in, 401 if not.                        |
| `/logout`                 | POST   | Deletes the session. 200 in both cases (idempotent).                               |
| `/session/touch`          | POST   | Reads and writes the session, sliding the TTL. 200 if logged in, 401 if not.       |
| `/admin/sessions/{user}`  | DELETE | Server-side revoke of a user's session (find by username scan). 200/204.           |

The session lifetime is 5 minutes. Sliding TTL applies on `/session/touch` and `/profile` but not on `/admin/sessions/*` (since that path is intended to operate without disturbing the session).

## Django implementation (~30 minutes)

Use Django 5.1 with `django.contrib.sessions.backends.cache` and the built-in `django.core.cache.backends.redis.RedisCache`.

### Step 1 — Configure `settings.py`

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://localhost:6379/1",
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = 300
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
```

### Step 2 — Views

Four `@require_http_methods` views and one admin view. Login writes `request.session["user"]` and `request.session["login_at"]`; profile reads them; logout calls `request.session.flush()`.

The admin revoke is the interesting part: Django stores session keys with the session ID, not the username. To find a session by username, you either maintain a side index (`user_to_session_id` in Redis) at login time, or scan the cache with `SCAN MATCH ":1:django.contrib.sessions.cache*"` and inspect each value. The side-index approach is correct; the scan is the operational fallback.

### Step 3 — A `tests.py` integration

Use Django's `Client`:

```python
from django.test import TestCase, Client

class SessionStoreTests(TestCase):
    def test_login_profile_logout(self):
        c = Client()
        r = c.post("/login", {"username": "demo"}, content_type="application/json")
        self.assertEqual(r.status_code, 200)
        r = c.get("/profile")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user"], "demo")
        c.post("/logout")
        r = c.get("/profile")
        self.assertEqual(r.status_code, 401)
```

Run with `python manage.py test`.

## FastAPI implementation (~60 minutes)

FastAPI does not ship a session framework. You build one as middleware.

### Step 1 — The `RedisSessionMiddleware`

Use the pattern from Lecture 3 Section 5.2. The middleware reads a session ID cookie, hydrates `request.state.session` from Redis, and writes any changes back on response. Include a `secrets`-generated 32-byte URL-safe session ID. Sign the cookie if you want (the cookie holds only the ID, but signing it lets you reject forged IDs before the Redis lookup).

### Step 2 — Routes

```python
@app.post("/login")
async def login(body: LoginBody, request: Request) -> dict[str, str]:
    request.state.session["user"] = body.username
    request.state.session["login_at"] = time.time()
    return {"status": "ok"}


@app.get("/profile")
async def profile(request: Request) -> dict[str, Any]:
    if "user" not in request.state.session:
        raise HTTPException(status_code=401)
    return dict(request.state.session)
```

The `Pydantic v2` body model for `/login`:

```python
class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
```

### Step 3 — Server-side revoke

Maintain a side index: at login time, `await redis.set(f"user_to_session:{username}", session_id, ex=300)`. At revoke time, `await redis.get` the session ID, then `await redis.delete(f"session:{session_id}")` and `await redis.delete(f"user_to_session:{username}")`. This is the same data shape as Django's would be if you wanted the same revoke capability.

### Step 4 — Tests

Use `httpx.AsyncClient`:

```python
@pytest.mark.asyncio
async def test_session_flow():
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        r = await client.post("/login", json={"username": "demo"})
        assert r.status_code == 200
        cookies = r.cookies
        r = await client.get("/profile", cookies=cookies)
        assert r.status_code == 200
        assert r.json()["user"] == "demo"
```

## The `COMPARISON.md` artefact

Three sections.

### Section 1 — Lines of code

```text
| File                                | Django | FastAPI |
|-------------------------------------|--------|---------|
| Settings / configuration            | 12     | 8       |
| Middleware                          | (built-in) | 55  |
| Routes / views                      | 48     | 60      |
| Tests                               | 35     | 40      |
| Total                               | 95     | 163     |
```

The exact numbers depend on your style; the order of magnitude (Django wins on lines, FastAPI wins on explicit control) is what should emerge.

### Section 2 — Surface area

A table contrasting the explicit choices each framework makes for you versus the explicit choices you make for it.

| Concern                       | Django                             | FastAPI                           |
|-------------------------------|------------------------------------|-----------------------------------|
| Session ID generation         | Framework (32 hex chars)            | You (`secrets.token_urlsafe(32)`) |
| Cookie security defaults      | Settings (`SESSION_COOKIE_*`)       | You (call `set_cookie(...)`)      |
| Sliding TTL                   | `SESSION_SAVE_EVERY_REQUEST=True`  | You (`await r.expire(...)`)       |
| Server-side serialiser        | Framework (JSON since 4.1)          | You (`json.dumps`)                |
| Server-side revoke            | `request.session.flush()`           | You (`await r.delete(...)`)       |
| Backend swap                  | `SESSION_ENGINE` setting            | Rewrite middleware                |

The pattern: Django bundles many choices into convention; FastAPI requires explicit choices. Both work; the trade-off is "convention I have to learn" versus "explicit code I have to write".

### Section 3 — The greenfield recommendation

Two paragraphs.

1. **If the constraints are "shipping a CRUD app fast, in a team familiar with Django's conventions"**, pick Django. The session store is one of ten things Django brings free; the cumulative savings make it the right default.
2. **If the constraints are "shipping an API service with custom auth, third-party integrations, and an async-heavy workload"**, pick FastAPI. The 60 extra lines for sessions are a small price for the rest of FastAPI's surface area (Pydantic v2, OpenAPI, async-native).

Defend each with one concrete reason. Avoid the "FastAPI is faster" trap — both can saturate a 10 Gbps NIC; the difference is rarely benchmark-decisive. The decision is about *how the code reads*, not how it runs.

## Rubric (15 points)

| Area                                            | Points | Pass bar                                                |
|-------------------------------------------------|-------:|---------------------------------------------------------|
| Django implementation runs and passes tests     | 4      | All five routes; tests green                            |
| FastAPI implementation runs and passes tests    | 4      | All five routes; tests green                            |
| Server-side revoke works in both                | 2      | The admin DELETE removes the session in Redis           |
| `COMPARISON.md` lines table                     | 1      | All four file rows, exact counts                        |
| `COMPARISON.md` surface-area table              | 2      | Six rows; each one a real difference, not a synonym     |
| `COMPARISON.md` recommendation                  | 2      | Two scenarios, each defended with a concrete reason     |

## Stretch goals

- Add a *second* cookie (e.g., `csrf_token`) that the middleware reads and validates on every `POST`. The CSRF token is a per-session secret stored alongside `user` in the session. The point is to see how the two frameworks handle adding a second cross-request piece of state.
- Implement *fixed-TTL* mode for FastAPI (the session expires at the login time + 30 min, regardless of activity). Compare to Django's `SESSION_EXPIRE_AT_BROWSER_CLOSE` and `SESSION_COOKIE_AGE` interaction. Document the corner cases.
- Add `django-redis` (the third-party Redis backend) instead of Django's built-in. Compare its features (pickle vs JSON serialiser; client-side encryption support; explicit `OPTIONS["PARSER_CLASS"]`). Cite <https://github.com/jazzband/django-redis>.

## References

- **Django sessions framework**: <https://docs.djangoproject.com/en/5.1/topics/http/sessions/>
- **Django cache framework Redis backend**: <https://docs.djangoproject.com/en/5.1/topics/cache/#redis>
- **`django-redis` (the third-party alternative)**: <https://github.com/jazzband/django-redis>
- **Starlette `SessionMiddleware`** (the cookie-based default; for contrast): <https://www.starlette.io/middleware/#sessionmiddleware>
- **FastAPI middleware**: <https://fastapi.tiangolo.com/tutorial/middleware/>
- **`secrets.token_urlsafe`** (the Python stdlib randomness for session IDs): <https://docs.python.org/3/library/secrets.html#secrets.token_urlsafe>
