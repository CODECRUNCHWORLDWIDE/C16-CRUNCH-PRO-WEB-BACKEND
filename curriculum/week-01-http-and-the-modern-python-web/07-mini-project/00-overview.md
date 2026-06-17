# Mini-Project — Django By Hand

> Build a working Django project from a completely empty folder, writing every file yourself. No `django-admin startproject`. No template repo. No copying.

This is the only mini-project this course where you'll forbid yourself from using framework scaffolding. The point is to write the boilerplate once, by hand, so the next time you see a generated Django project you understand exactly what every line does and why it's there.

**Estimated time:** 7 hours (split across Thursday, Friday, Saturday in the suggested schedule).

---

## What you will build

A minimal Django project called `byhand` that:

1. Boots successfully on `python manage.py runserver`.
2. Serves a single URL `/` with a view that returns `"Hello, from Django by hand!"`.
3. Serves a second URL `/now` with a view that returns the current UTC time as JSON.
4. Serves a third URL `/echo/<word>` with a view that returns the word reversed.
5. Has a passing test for each view (using Django's test client, not Pytest, to keep dependencies minimal).
6. Has a working `manage.py` you wrote yourself, not a copied template.

By the end you'll have a public GitHub repo of ~150 lines of code that does everything Django's tutorial does in chapter 1, but you'll *understand* every byte.

---

## Rules

- **You may** read the Django docs, the source code on GitHub, this README, and your lecture notes.
- **You may NOT** run `django-admin startproject` or `django-admin startapp`. If you've used those before, pretend you forgot how.
- **You may NOT** copy-paste a `manage.py` or `settings.py` from a template repo. Type them.
- You **must** use a virtual environment.
- Python 3.11+ and Django 5.x.

---

## Acceptance criteria

- [ ] A new public GitHub repo named `c16-week-01-byhand-<yourhandle>`.
- [ ] The repo's root contains: `manage.py`, `byhand/` package, `pyproject.toml` or `requirements.txt`, `.gitignore`, `README.md`.
- [ ] `byhand/` package contains at least `__init__.py`, `settings.py`, `urls.py`, `wsgi.py`, `asgi.py`, `views.py`.
- [ ] `python manage.py runserver` starts the dev server on `localhost:8000` with no warnings (other than the migration warning, which is expected — we haven't connected a DB).
- [ ] `curl http://localhost:8000/` returns `200 OK` with `Hello, from Django by hand!`.
- [ ] `curl http://localhost:8000/now` returns `200 OK` with a JSON object like `{"now": "2026-05-13T14:00:00+00:00"}` and `Content-Type: application/json`.
- [ ] `curl http://localhost:8000/echo/python` returns `200 OK` with `nohtyp`.
- [ ] `python manage.py test` runs and all tests pass.
- [ ] `python manage.py check` reports zero errors.
- [ ] `.gitignore` excludes `__pycache__/`, `.venv/`, `db.sqlite3`, `.env`, `.DS_Store`.
- [ ] Your `README.md` includes:
  - One paragraph describing the project.
  - The exact commands to set it up from a fresh clone.
  - The list of URLs and what each returns.
  - One short section "Things I learned by doing this by hand."

---

## Suggested order of operations

You'll find it easier if you build incrementally rather than trying to write the whole thing at once.

### Phase 1 — Bare skeleton (~1h)

1. `mkdir byhand-project && cd byhand-project`
2. Create and activate a venv. Install Django.
3. Create `pyproject.toml` (or `requirements.txt` if you prefer) pinning Django 5.x.
4. Create the directory `byhand/` (this will be your project package).
5. Create empty files: `byhand/__init__.py`, `byhand/settings.py`, `byhand/urls.py`, `byhand/views.py`, `byhand/wsgi.py`, `byhand/asgi.py`.
6. Create `manage.py` in the root.
7. `git init`, write `.gitignore`, first commit: `Initial skeleton`.

### Phase 2 — Make settings minimal (~1h)

`settings.py` needs the absolute minimum:

- `DEBUG = True` for local dev.
- A `SECRET_KEY` (generate one with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`). Hardcode it for now; we'll discuss secrets in Week 10.
- `ALLOWED_HOSTS = ["*"]` (only for local dev).
- `ROOT_URLCONF = "byhand.urls"`.
- `INSTALLED_APPS` can be an empty list — we're not using any built-in apps yet.
- `MIDDLEWARE = []` — we'll add things only when we need them.
- `WSGI_APPLICATION = "byhand.wsgi.application"`.
- `DATABASES = {}` — no DB this week.
- `STATIC_URL = "static/"` — Django insists on this even though we don't serve static files.
- `DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"`.
- `USE_TZ = True`.
- `TIME_ZONE = "UTC"`.

Then `manage.py` is just:

```python
#!/usr/bin/env python
import os
import sys
from django.core.management import execute_from_command_line

def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "byhand.settings")
    execute_from_command_line(sys.argv)

if __name__ == "__main__":
    main()
```

`chmod +x manage.py` if you're on macOS/Linux.

Test: `python manage.py check`. If it says "no issues," commit: `Minimal settings boot`.

### Phase 3 — Wire `wsgi.py` and `asgi.py` (~30 min)

`wsgi.py`:

```python
import os
from django.core.wsgi import get_wsgi_application
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "byhand.settings")
application = get_wsgi_application()
```

`asgi.py` is the same shape, replace `wsgi`→`asgi`. Test: `python manage.py runserver`. The server should start. Visit `http://localhost:8000/`. You'll see a 404 — there are no URLs yet — and that's correct. Commit: `WSGI/ASGI entry points`.

### Phase 4 — First view + URL (~1h)

`byhand/views.py`:

```python
from django.http import HttpResponse

def hello(request):
    return HttpResponse("Hello, from Django by hand!")
```

`byhand/urls.py`:

```python
from django.urls import path
from byhand import views

urlpatterns = [
    path("", views.hello, name="hello"),
]
```

Test: `curl http://localhost:8000/`. You should see your message. Commit: `Hello view`.

### Phase 5 — JSON view + dynamic URL (~1h)

In `views.py`, add:

```python
import datetime
from django.http import JsonResponse, HttpResponse

def now(request):
    return JsonResponse({"now": datetime.datetime.now(datetime.UTC).isoformat()})

def echo(request, word: str):
    return HttpResponse(word[::-1])
```

In `urls.py`:

```python
urlpatterns = [
    path("", views.hello, name="hello"),
    path("now", views.now, name="now"),
    path("echo/<str:word>", views.echo, name="echo"),
]
```

Test all three URLs. Commit: `JSON and dynamic URL views`.

### Phase 6 — Tests (~1h)

Create `byhand/tests.py`:

```python
from django.test import TestCase, Client


class HelloTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_hello(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"Hello, from Django by hand!")

    def test_now_returns_json(self):
        r = self.client.get("/now")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/json")
        body = r.json()
        self.assertIn("now", body)

    def test_echo_reverses(self):
        r = self.client.get("/echo/python")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"nohtyp")
```

For Django to discover this without `INSTALLED_APPS`, you need to add `"byhand"` as an app. The simplest path: create `byhand/apps.py`:

```python
from django.apps import AppConfig

class ByhandConfig(AppConfig):
    name = "byhand"
    default_auto_field = "django.db.models.BigAutoField"
```

Add `"byhand.apps.ByhandConfig"` to `INSTALLED_APPS` in `settings.py`.

Test: `python manage.py test`. All three tests should pass. Commit: `Test suite`.

### Phase 7 — Polish (~1.5h)

- Write your README.
- Add a `Makefile` or `justfile` with `run`, `test`, `check` recipes.
- Confirm `.gitignore` is complete.
- Push to GitHub.
- Submit the repo URL on the course tracker.

---

## Rubric

| Criterion | Weight | What "great" looks like |
|----------|-------:|-------------------------|
| Runs | 30% | `runserver`, `check`, `test` all clean on a fresh clone |
| Code clarity | 20% | Files are short, each has one job, no dead code |
| README quality | 15% | Someone unfamiliar can clone and run in <5 minutes |
| Test coverage | 15% | All three views have a positive test; one has a negative path |
| Commit history | 10% | Multiple commits with meaningful messages (not just "wip") |
| "Things I learned" | 10% | At least 3 specific, non-trivial learnings |

---

## What this prepares you for

- **Week 2** assumes you know what `INSTALLED_APPS`, `MIDDLEWARE`, and `ROOT_URLCONF` are, because you wrote them. We'll add `django.contrib.admin` and `django.contrib.auth` next week and now you'll see exactly what they bring.
- **Week 3** wires templates and forms on top of what you have. Same `byhand` project, but it grows.
- The capstone (Week 12) will reach back to this skeleton: it ends up looking very much like the project layout you wrote by hand here.

---

## Resources

- The official Django tutorial (compare yours to it after you finish, not before): <https://docs.djangoproject.com/en/stable/intro/tutorial01/>
- Django source — `django/core/management/templates/project_template/` — this is the directory `startproject` copies from. After you've written your own, comparing yours to this is illuminating: <https://github.com/django/django/tree/main/django/conf/project_template>

---

## Submission

When done:

1. Push your repo to GitHub with a public URL.
2. Make sure `README.md` includes the setup commands and the URL list.
3. Make sure `python manage.py test` and `python manage.py check` are both green on a freshly cloned copy.
4. Tweet, post, or share the repo. You did real work; show it.
