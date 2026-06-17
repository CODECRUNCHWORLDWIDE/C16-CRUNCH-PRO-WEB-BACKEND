# Week 3 — Homework

Six problems, ~6h. Build them in your `crunchwriter` repo under `c16-week-03/homework/`.

---

## Problem 1 — Read the source of one CBV (45 min)

Pick one: `CreateView`, `UpdateView`, or `DetailView`. Open the Django source (your venv has it; or read it on GitHub at `django/views/generic/edit.py` / `django/views/generic/detail.py`). Trace the MRO. List, in order, every class the chosen view inherits from.

**Acceptance:**

- `c16-week-03/homework/01-cbv-source.md` with:
  - The class name you picked.
  - The MRO as a Python list (use `CreateView.__mro__` or read the source).
  - For each class in the MRO, one sentence: "This class contributes X."
  - One question the source raised that you couldn't answer just by reading it.

---

## Problem 2 — Convert an FBV to a CBV (60 min)

Take your `article_create_fbv` from Exercise 2. Rewrite it as a `CreateView` subclass:

```python
class ArticleCreateView(LoginRequiredMixin, CreateView):
    model = Article
    form_class = ArticleForm
    template_name = "writer/article_form.html"
    success_url = reverse_lazy("writer:dashboard")

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)
```

**Acceptance:**

- `ArticleCreateView` shipped at the same URL.
- All seven of Exercise 2's tests still pass against the new view.
- A new test, `test_create_view_sets_author_to_request_user`, that confirms `form_valid` does its job.
- `c16-week-03/homework/02-fbv-to-cbv.md` with a 4-line summary of which version you would ship and why.

---

## Problem 3 — A real `base.html` plus partials (60 min)

Refactor the templates you've written this week into:

- One `base.html` per Lecture 2's template.
- A `partials/article_card.html` partial used in both `article_list.html` and `dashboard.html`.
- A `partials/messages.html` partial included from `base.html`.

**Acceptance:**

- The three templates use `{% extends %}` + `{% block %}` exclusively; no `<html>` tags duplicated.
- Two `{% include %}` directives, one of each partial.
- `python manage.py test` passes.
- A screenshot showing both pages use the same card markup.

---

## Problem 4 — Tighten the login flow (45 min)

Implement four UX improvements:

1. Set `LOGIN_URL`, `LOGIN_REDIRECT_URL`, `LOGOUT_REDIRECT_URL` if you haven't already.
2. Ensure the `?next=` query string survives a failed login attempt (Django does this; verify with a test that submits a bad password and asserts the `next` is still in the rendered form).
3. Add the `messages.success(request, "Welcome back, {{ user.username }}.")` after a successful login. Hint: subclass `LoginView` and override `form_valid`.
4. Add a "Log out" `<form>` (POST-only) in the header that flashes "Logged out." via the messages framework.

**Acceptance:**

- `c16-week-03/homework/04-login-ux.md` listing each of the four changes with the file + line.
- Two tests: `test_failed_login_preserves_next`, `test_successful_login_flashes_welcome`.

---

## Problem 5 — Owner-only delete with confirmation (60 min)

Add `ArticleDeleteView`:

- Subclass `LoginRequiredMixin` and `DeleteView`.
- `get_queryset()` filters to `author=request.user` (same pattern as Update).
- GET renders `article_confirm_delete.html` (Django's default template name).
- POST deletes the article and redirects to the dashboard with a `messages.success("Article deleted.")`.

URL: `path("dashboard/<int:pk>/delete/", views.ArticleDeleteView.as_view(), name="article_delete")`.

**Acceptance:**

- The view + template + URL.
- Tests:
  - `test_delete_get_renders_confirmation`.
  - `test_delete_post_deletes_and_redirects`.
  - `test_cant_delete_other_users_article` — returns 404.
- A note in `c16-week-03/homework/05-delete.md`: why is the GET a confirmation page rather than the action itself? (Hint: GETs should be idempotent.)

---

## Problem 6 — Reflection (45 min)

`c16-week-03/homework/06-reflection.md`, 300-400 words:

1. Of the four protection tools (`login_required`, `LoginRequiredMixin`, `permission_required`, queryset-filtering), which one are you most likely to overuse? Which are you most likely to forget? Why?
2. The FBV vs CBV debate is partly aesthetic and partly technical. What is **one** technical reason you'd reach for an FBV that has nothing to do with personal taste?
3. CSRF is the most-skipped chapter for beginners because the framework "just works." Explain, in your own words, what would break if `{% csrf_token %}` were optional.
4. What habit do you want to install for Week 4?

---

## Time budget

| Problem | Time |
|--------:|----:|
| 1 — CBV source dive | 45 min |
| 2 — FBV to CBV | 60 min |
| 3 — `base.html` + partials | 60 min |
| 4 — Login UX | 45 min |
| 5 — Delete with confirmation | 60 min |
| 6 — Reflection | 45 min |
| **Total** | **~5 h 55 m** |

After homework, ship the [mini-project](./07-mini-project/00-overview.md) — `crunchwriter v1`.
