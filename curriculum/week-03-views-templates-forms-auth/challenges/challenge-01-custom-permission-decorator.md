# Challenge 1 — Custom permission decorator

**Time:** ~4 hours. **Difficulty:** Medium. **Goal:** Build a decorator + CBV mixin pair that is safer than `user_passes_test`, supports both FBVs and CBVs, accepts a predicate or a list of permissions, and ships with tests.

## Why this exists

`user_passes_test` is convenient but has two ergonomic and one security flaw:

1. **It does not check `is_authenticated` first.** A bare `lambda u: u.is_staff` raises `AttributeError` on `AnonymousUser` because `is_staff` exists, but only because of the duck-typed `AnonymousUser` shim. A predicate like `lambda u: u.profile.is_verified` will crash on anonymous traffic.
2. **It redirects to the login URL on failure even when the user is authenticated.** A logged-in user who fails the predicate gets bounced to login — a confusing UX. The right behaviour is a 403.
3. **There is no CBV-side equivalent that composes with `LoginRequiredMixin` and `PermissionRequiredMixin`** without writing the dispatch override yourself.

You are going to fix this by writing `require(...)` — a single name that works as both a decorator and a mixin.

## The contract

```python
from writer.access import require

# As a decorator on an FBV:
@require(lambda u: u.is_staff)
def staff_dashboard(request):
    ...

# With a list of permission codenames:
@require(perms=["writer.publish_article"])
def publish_view(request, pk):
    ...

# As a CBV mixin:
class StaffDashboard(require.mixin(lambda u: u.is_staff), TemplateView):
    template_name = "staff/dashboard.html"

# Or with perms on a CBV:
class PublishView(require.mixin(perms=["writer.publish_article"]), UpdateView):
    ...
```

Behaviour:

- Anonymous user → redirect to `LOGIN_URL` with `?next=<current path>`.
- Authenticated user who fails the predicate or lacks the permissions → `HttpResponseForbidden` (status 403), **not** a redirect.
- Authenticated user who passes → the view runs normally.
- The decorator preserves the wrapped function's `__name__`, `__doc__`, and `__wrapped__` (use `functools.wraps`).
- The decorator and mixin paths share the same core check — DRY.

## Acceptance criteria

- [ ] File `writer/access.py` defines `require` (callable + `.mixin` factory).
- [ ] Works on FBVs as `@require(predicate)` and as `@require(perms=[...])`.
- [ ] Works on CBVs as `require.mixin(predicate)` and `require.mixin(perms=[...])`.
- [ ] Anonymous traffic is redirected to `settings.LOGIN_URL` with `?next=` set.
- [ ] Authenticated-but-unauthorized traffic gets a `403` response (not a redirect).
- [ ] Both the decorator and the mixin share the same checking function — no code duplication.
- [ ] Tests cover all four protected outcomes (anon, authed-pass, authed-fail-predicate, authed-fail-perms) for both FBV and CBV uses → 8 tests minimum.
- [ ] `python manage.py check` clean.

## Hints

### Start from the check

Write the core check first, decoupled from views:

```python
def _check(user, predicate=None, perms=None):
    if not user.is_authenticated:
        return "anonymous"
    if predicate is not None and not predicate(user):
        return "denied"
    if perms is not None and not user.has_perms(perms):
        return "denied"
    return "allowed"
```

Three outcomes. Easy to test on its own.

### Then the decorator

```python
from functools import wraps
from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from urllib.parse import quote

def require(predicate=None, *, perms=None):
    def deco(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            outcome = _check(request.user, predicate, perms)
            if outcome == "anonymous":
                return redirect(f"{settings.LOGIN_URL}?next={quote(request.get_full_path())}")
            if outcome == "denied":
                return HttpResponseForbidden("Forbidden.")
            return view_func(request, *args, **kwargs)
        return wrapped
    return deco
```

### Then the mixin factory

```python
def _make_mixin(predicate=None, perms=None):
    class _RequireMixin:
        def dispatch(self, request, *args, **kwargs):
            outcome = _check(request.user, predicate, perms)
            if outcome == "anonymous":
                return redirect(f"{settings.LOGIN_URL}?next={quote(request.get_full_path())}")
            if outcome == "denied":
                return HttpResponseForbidden("Forbidden.")
            return super().dispatch(request, *args, **kwargs)
    return _RequireMixin

require.mixin = _make_mixin
```

`require.mixin = _make_mixin` works because functions in Python are objects and you can hang attributes on them. This is the idiomatic way to expose `.mixin` from the same name.

### Bare argument vs keyword

`@require(lambda u: u.is_staff)` — the predicate is positional.
`@require(perms=["app.code"])` — `perms` is keyword-only.

This is why the signature uses `def require(predicate=None, *, perms=None)`.

## Tests

```python
# writer/tests_access.py
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.views.generic import View
from django.http import HttpResponse

from writer.access import require

User = get_user_model()

# An FBV to protect
@require(lambda u: u.is_staff)
def staff_only_fbv(request):
    return HttpResponse("ok")

# A CBV to protect
class StaffOnlyCBV(require.mixin(lambda u: u.is_staff), View):
    def get(self, request):
        return HttpResponse("ok")

class RequireTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="u", password="p")
        self.staff = User.objects.create_user(username="s", password="p", is_staff=True)

    # ... 8 tests covering anon/pass/fail × FBV/CBV × predicate/perms
```

Hint: `RequestFactory` doesn't auto-attach a user. Set `request.user = self.user` explicitly. For the test client, `self.client.login(...)` does it for you.

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Correctness | 30% | All eight test cases pass first time |
| API ergonomics | 25% | The four call shapes in the contract all work |
| DRY | 20% | Decorator and mixin share one check function |
| Failure modes | 15% | Anon → redirect; authed-fail → 403; never the wrong one |
| Test quality | 10% | Each test has one assertion focus; names describe the case |

## Reflection (~150 words, in `c16-week-03/challenges/01-reflection.md`)

After finishing:

1. When would you reach for `require(...)` over `LoginRequiredMixin` + `PermissionRequiredMixin`?
2. When would you reach for the inverse (use the built-ins)?
3. What would you change about your API after writing eight tests against it?

## Stretch

- Make the 403 response render `403.html` instead of a bare `HttpResponseForbidden("Forbidden.")` — but only if the template exists.
- Add `@require(any_of=[...])` that succeeds if **any** of multiple permissions are held (the default `has_perms` is AND).
- Add a `raise_anonymous=True` flag that returns 403 even for anonymous users — useful for APIs where a redirect is wrong.
