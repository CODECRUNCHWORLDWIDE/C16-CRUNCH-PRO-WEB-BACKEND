# Lecture 3 — Auth, Sessions, CSRF, and `LoginRequiredMixin`

> **Duration:** ~1.5 hours. **Outcome:** You can stand up a real login flow, mark a view as login-only, explain what the session cookie and CSRF token do across a POST request, and pick the right protection decorator/mixin per situation.

Authentication and the session framework are the two halves of how Django answers the question "who is making this request?" CSRF is what stops someone else from making that request on a user's behalf. All three are in `django.contrib` and ship by default — but understanding what each piece does is what separates "I copied the snippet" from "I can debug this when it breaks."

## 1. The auth model that ships

`django.contrib.auth` ships a default `User` model with:

| Field | Type |
|-------|------|
| `username` | unique `CharField` |
| `email` | `EmailField` (not required by default) |
| `first_name` / `last_name` | `CharField` (optional) |
| `password` | hashed `CharField` (Argon2 / PBKDF2 / etc.) |
| `is_staff` | boolean — can access the admin |
| `is_superuser` | boolean — has all permissions |
| `is_active` | boolean — false means login is refused |
| `last_login` / `date_joined` | timestamps |
| `groups` / `user_permissions` | M2M relationships to `Group` and `Permission` |

You access it via `settings.AUTH_USER_MODEL` in models (already a habit from Week 2) and via `django.contrib.auth.get_user_model()` everywhere else.

```python
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.get(username="alice")
```

### Should you customize the user model?

**Yes — but the time to decide is at project start, not later.** If you have any chance of needing extra user fields (a display name, an avatar, a tenant), subclass `AbstractUser` (keeps username) or `AbstractBaseUser` (full control). For Week 3 we use the default user, which is fine for `crunchwriter` v1; we revisit this in Week 9.

## 2. The session framework

HTTP is stateless. Every request lands at the server with no memory of the previous one. Sessions are how Django gives us "the same user across many requests."

How it works in one paragraph:

1. On any view that touches `request.session`, Django creates a `Session` row in the database with a random key (e.g. `sessions_django_session.session_key`).
2. The same key is sent to the browser as a cookie named `sessionid`, signed and HTTP-only.
3. On every subsequent request, the middleware reads the cookie, looks up the session row, and exposes the data as `request.session` (a dict-like).
4. When a user logs in, Django stores `_auth_user_id`, `_auth_user_backend`, and `_auth_user_hash` in `request.session`. On the next request, `AuthenticationMiddleware` reads those, looks up the user, and sets `request.user`.

That's the whole mechanism. Two implications:

- **Logged-in identity lives in the session, not the cookie itself.** If your DB is wiped, every user logs out.
- **`request.user` is always set.** For anonymous traffic it is an `AnonymousUser` instance; `user.is_authenticated` is `False`.

### Configuring sessions

`settings.py` defaults that you should know:

```python
SESSION_ENGINE = "django.contrib.sessions.backends.db"   # default
SESSION_COOKIE_AGE = 1209600   # 2 weeks, in seconds
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False  # set True in production behind HTTPS
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
```

Two settings you flip in production (Week 12):

- `SESSION_COOKIE_SECURE = True` — cookies only sent over HTTPS.
- `SESSION_COOKIE_SAMESITE = "Lax"` is the default and is the right choice 95% of the time. `"Strict"` is more locked down but breaks the OAuth callback pattern.

### Storing data in the session

```python
def add_to_recent(request, article_id):
    recent = request.session.get("recent_articles", [])
    recent = [article_id] + [x for x in recent if x != article_id]
    request.session["recent_articles"] = recent[:10]
    request.session.modified = True
    return redirect("writer:article_detail", slug=...)
```

Set `request.session.modified = True` if you mutate a mutable value in-place (a list, a dict) — Django only auto-detects assignment to a top-level key.

## 3. Authentication, in three calls

```python
from django.contrib.auth import authenticate, login, logout

def manual_login(request):
    user = authenticate(request, username="alice", password="hunter2")
    if user is not None:
        login(request, user)            # writes to session
        return redirect("writer:dashboard")
    return render(request, "registration/login.html", {"error": "Bad credentials"})

def manual_logout(request):
    logout(request)                     # clears session
    return redirect("writer:article_list")
```

`authenticate` walks the backends in `AUTHENTICATION_BACKENDS` (default: `ModelBackend`) and returns a user instance on success, `None` on failure. `login` is the call that writes the auth keys into the session. `logout` flushes.

You almost never write these by hand once you've done it once. Django ships views that do this for you.

## 4. The auth views that ship

Add this line in your project's `urls.py`:

```python
path("accounts/", include("django.contrib.auth.urls")),
```

You now have, for free:

| URL | Name | View |
|-----|------|------|
| `/accounts/login/` | `login` | `LoginView` |
| `/accounts/logout/` | `logout` | `LogoutView` (POST only) |
| `/accounts/password_change/` | `password_change` | `PasswordChangeView` |
| `/accounts/password_change/done/` | `password_change_done` | `PasswordChangeDoneView` |
| `/accounts/password_reset/` | `password_reset` | `PasswordResetView` (sends an email) |
| `/accounts/password_reset/done/` | `password_reset_done` | `PasswordResetDoneView` |
| `/accounts/reset/<uidb64>/<token>/` | `password_reset_confirm` | `PasswordResetConfirmView` |
| `/accounts/reset/done/` | `password_reset_complete` | `PasswordResetCompleteView` |

Templates are not shipped. You write them. The convention is `templates/registration/login.html`, etc. The minimal login template:

```django
{% extends "writer/base.html" %}
{% block title %}Log in · {{ block.super }}{% endblock %}
{% block content %}
  <h1>Log in</h1>
  <form method="post">
    {% csrf_token %}
    {% for field in form %}
      <div class="field {% if field.errors %}field--error{% endif %}">
        {{ field.label_tag }}
        {{ field }}
        {% for e in field.errors %}<p class="error">{{ e }}</p>{% endfor %}
      </div>
    {% endfor %}
    {% if form.non_field_errors %}
      {% for e in form.non_field_errors %}<p class="error">{{ e }}</p>{% endfor %}
    {% endif %}
    <button type="submit">Log in</button>
    <input type="hidden" name="next" value="{{ next }}">
  </form>
{% endblock %}
```

Two things to point out:

1. **`{% csrf_token %}` is mandatory.** Without it, every login attempt 403s.
2. **`next` is a hidden field** carrying the post-login redirect target. Django populates it from the `?next=` query string.

### Required settings for the auth views

```python
LOGIN_URL = "login"                          # where login_required sends anonymous users
LOGIN_REDIRECT_URL = "writer:dashboard"      # default redirect after login (overridden by ?next=)
LOGOUT_REDIRECT_URL = "writer:article_list"  # where logout sends you
```

These are URL names (or paths). `LOGIN_URL` defaults to `/accounts/login/`; the others have no default. Set all three explicitly so the behavior is obvious from `settings.py`.

## 5. Protecting views — four tools, four shapes

You have four common ways to restrict access. Pick by view shape and check type.

### `@login_required` — FBV, "must be logged in"

```python
from django.contrib.auth.decorators import login_required

@login_required
def dashboard(request):
    articles = Article.objects.filter(author=request.user)
    return render(request, "writer/dashboard.html", {"articles": articles})
```

Anonymous traffic gets redirected to `LOGIN_URL` with `?next=` set to the original path.

### `LoginRequiredMixin` — CBV, "must be logged in"

```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

class DashboardView(LoginRequiredMixin, ListView):
    template_name = "writer/dashboard.html"
    context_object_name = "articles"

    def get_queryset(self):
        return Article.objects.filter(author=self.request.user)
```

**`LoginRequiredMixin` must appear first in the bases.** Mixin order matters because of MRO: the mixin overrides `dispatch()` to perform the auth check; if it ends up after the generic, the generic's `dispatch` runs first and the check never fires for some code paths.

### `@permission_required` / `PermissionRequiredMixin` — "must have a specific permission"

```python
from django.contrib.auth.decorators import permission_required

@permission_required("writer.publish_article", raise_exception=True)
def publish(request, pk):
    ...
```

Pair with `raise_exception=True` to get a 403 instead of a redirect-to-login loop. Permissions are auto-generated per model (`add_article`, `change_article`, `delete_article`, `view_article`); custom permissions go in `Meta.permissions`.

### `@user_passes_test` / `UserPassesTestMixin` — "must satisfy a predicate"

```python
from django.contrib.auth.decorators import user_passes_test

@user_passes_test(lambda u: u.is_authenticated and u.is_staff)
def staff_only(request):
    ...
```

Flexible, but the test runs against `request.user` directly — if you forget `is_authenticated`, an anonymous user causes an `AttributeError` instead of a redirect. We build a safer version in this week's challenge.

### Which one to reach for

| You want… | Use |
|-----------|-----|
| "Logged in or bounce to login" | `login_required` / `LoginRequiredMixin` |
| "Has specific permission codename" | `permission_required` / `PermissionRequiredMixin` |
| "Custom predicate, well-defined" | `user_passes_test` / `UserPassesTestMixin` |
| "Owner-of-this-object only" | Custom check in `get_queryset()` (preferred — filters at the DB) |

The last one is worth repeating: if a view should only show objects the current user owns, **filter at `get_queryset()`**, not with a `user_passes_test`. The queryset filter is one SQL clause, applies to listing and detail and delete, and can't be bypassed by guessing a URL.

```python
class ArticleUpdateView(LoginRequiredMixin, UpdateView):
    model = Article
    form_class = ArticleForm

    def get_queryset(self):
        return Article.objects.filter(author=self.request.user)
```

This single `get_queryset` override means: an anonymous user is redirected; a logged-in user editing someone else's article gets a 404 (not a 403 — Django doesn't reveal that the article exists at all).

## 6. CSRF — what the attack is, and what Django does

**The attack.** You are logged into `bank.example.com`. Your browser holds the session cookie. You then visit `evil.example.com`. That page contains:

```html
<form action="https://bank.example.com/transfer/" method="post">
  <input type="hidden" name="to" value="attacker">
  <input type="hidden" name="amount" value="9999">
</form>
<script>document.forms[0].submit();</script>
```

The browser dutifully sends the POST to `bank.example.com` **with your session cookie attached** — because that's what browsers do for top-level form submissions. If `/transfer/` has no other protection, the transfer goes through.

**Django's defence.** Two pieces:

1. A **CSRF cookie** (`csrftoken`) is set on first visit, containing a random secret.
2. A `{% csrf_token %}` inside every POST form renders a hidden `<input>` with the same secret.
3. On POST, `CsrfViewMiddleware` requires that the form's hidden value matches the cookie's value.

The attacker can make your browser send the cookie (browsers do that automatically), but they **cannot read the cookie** (it's `SameSite=Lax` and they're on a different origin) so they can't put the matching value in their form.

### What you have to do

- Put `{% csrf_token %}` inside every `<form method="post">`. **Every one.**
- Trust `CsrfViewMiddleware` to be in `MIDDLEWARE`. It is by default.
- For AJAX POSTs from JavaScript, read the cookie and put its value in the `X-CSRFToken` header. The Django docs have the JS snippet.

### When to `@csrf_exempt` — almost never

The exemption decorator exists for webhooks and APIs that authenticate via a different mechanism (HMAC, JWT). For human-facing forms it is never the right answer. If a form is 403-ing on you, the bug is almost always that `{% csrf_token %}` is missing or the page was loaded via a different origin.

## 7. End-to-end: a logged-in form POST

Walk through what happens when a logged-in user submits a new article:

1. **Browser sends GET `/dashboard/new/`** with the `sessionid` and `csrftoken` cookies.
2. **`SessionMiddleware`** reads `sessionid`, loads the session row, attaches `request.session`.
3. **`AuthenticationMiddleware`** reads `_auth_user_id` from the session, loads the user, sets `request.user`.
4. **`CsrfViewMiddleware`** ensures a `csrftoken` cookie exists (issues one if not).
5. **`LoginRequiredMixin`** in `ArticleCreateView.dispatch()` checks `request.user.is_authenticated`. Pass.
6. **`CreateView.get()`** instantiates an empty `ArticleForm`, calls `render()`.
7. **The template renders.** `{% csrf_token %}` writes a `<input type="hidden" name="csrfmiddlewaretoken" value="…">` whose value is derived from the cookie.
8. **Browser sends POST `/dashboard/new/`** with form data, both cookies, and the hidden token.
9. **Middlewares run again.** `CsrfViewMiddleware` now does the real check: hidden value matches cookie. Pass.
10. **`LoginRequiredMixin`** check. Pass.
11. **`CreateView.post()`** binds the form. `form.is_valid()` runs the validation lifecycle.
12. **`form_valid(form)`** assigns `form.instance.author = request.user`, calls `form.save()`, returns `HttpResponseRedirect` to `success_url`.
13. **Browser follows the redirect** with a GET to the detail page.

That is the entire request cycle for a Django form POST. Every step is documented; every step is debuggable. The day a POST 403s on you, this list is the checklist.

## 8. Common mistakes

1. **Missing `{% csrf_token %}`** — every POST 403s. Always inside the `<form>`.
2. **`LoginRequiredMixin` after the generic in the MRO** — `class V(ListView, LoginRequiredMixin)`. Reverse it.
3. **`user_passes_test` without checking `is_authenticated`** — anonymous user → `AttributeError` instead of a clean redirect.
4. **`LOGIN_URL` not set** — anonymous traffic redirects to `/accounts/login/` even if you put login elsewhere.
5. **Storing sensitive data in the session** — sessions are server-side, but their durability is the database. Don't store secrets there.
6. **Owner-only views protected by `if request.user == obj.user`** in the view body — works for some paths, not others. Filter at `get_queryset()`.
7. **`@csrf_exempt` on a regular form** — opens a CSRF hole. Never do this to "make it work."
8. **Logging in with `request.user = user`** — that doesn't log anyone in. You must call `login(request, user)` so the session is written.

## 9. Self-check

- What is the difference between `authenticate()` and `login()`?
- What does the `sessionid` cookie actually contain?
- Where does Django store the logged-in user ID? In the cookie or in the database?
- What is the difference between `login_required` and `LoginRequiredMixin`?
- Why must `LoginRequiredMixin` come first in the CBV's base classes?
- What is the attack that `{% csrf_token %}` defends against?
- Why is `get_queryset` filtering safer than a `user_passes_test` for "owner-only" pages?
- In production, which two `SESSION_COOKIE_*` settings change?

## Further reading

- **Using the Django authentication system** (the topic page that covers all of this): <https://docs.djangoproject.com/en/stable/topics/auth/default/>
- **`LoginView` and the auth views**: <https://docs.djangoproject.com/en/stable/topics/auth/default/#all-authentication-views>
- **CSRF protection in depth**: <https://docs.djangoproject.com/en/stable/ref/csrf/>
- **Sessions topic guide**: <https://docs.djangoproject.com/en/stable/topics/http/sessions/>
- **OWASP — CSRF**: <https://owasp.org/www-community/attacks/csrf>
