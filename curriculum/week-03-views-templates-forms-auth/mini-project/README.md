# Mini-Project — `crunchwriter` v1

> Add a public reader, a login page, and an author dashboard to the editorial CMS we built in Week 2. By end of Week 3, a non-admin user can sign up, write an article, and have it appear on the public site — and a reader who is not logged in can browse it without ever touching the admin.

**Estimated time:** 7 hours, spread across Thursday–Saturday.

## What you build

Continue in the `writer` app from Week 2. Add views, templates, forms, and the auth wiring so the site has two faces:

- **Public face** at `/` — anyone can read published articles.
- **Author face** at `/dashboard/` — only logged-in users; lists their own articles and lets them create and edit.

You keep the admin from Week 2. The admin is still there for editors; this week is about the front door that everyone else uses.

## URL surface

| URL | Name | Who | What |
|-----|------|-----|------|
| `/` | `writer:article_list` | public | Paginated list of published articles |
| `/articles/<slug>/` | `writer:article_detail` | public | Read one published article |
| `/accounts/login/` | `login` | public | Login form |
| `/accounts/logout/` | `logout` | any | POST logs out |
| `/dashboard/` | `writer:dashboard` | logged in | Your articles, newest first |
| `/dashboard/new/` | `writer:article_new` | logged in | Create article (`ArticleForm`) |
| `/dashboard/<pk>/edit/` | `writer:article_edit` | author of article only | Edit article |
| `/dashboard/<pk>/delete/` | `writer:article_delete` | author of article only | Confirm + delete |
| `/admin/` | (Django admin) | staff | Unchanged from W2 |

## Acceptance criteria

- [ ] All eight URLs above resolve and return the correct status code (200 for happy paths, 302 to login for anon-on-protected, 404 for owner-mismatch).
- [ ] Public list at `/` shows only **published** articles, newest first, paginated 20 per page.
- [ ] Public detail at `/articles/<slug>/` returns **404 for non-published articles** even with a valid slug.
- [ ] Login at `/accounts/login/` works against Django's built-in `LoginView`. The `templates/registration/login.html` extends `writer/base.html`.
- [ ] Dashboard at `/dashboard/` redirects anonymous users to login with `?next=/dashboard/`. After login the user lands on the dashboard.
- [ ] `ArticleForm` is a `ModelForm` with at least:
  - Explicit `fields = [...]` (never `"__all__"`).
  - Two field-level validators (`clean_title`, `clean_slug`).
  - One cross-field validator in `clean()`.
- [ ] `ArticleCreateView` sets `author = request.user` in `form_valid`.
- [ ] `ArticleUpdateView` and `ArticleDeleteView` filter at `get_queryset()` so a user editing or deleting another user's article gets a **404**, not a 403.
- [ ] One `base.html`, two partials (`partials/article_card.html`, `partials/messages.html`), used via `{% extends %}` and `{% include %}`.
- [ ] All forms include `{% csrf_token %}`. Verify by `grep -r "method=\"post\"" writer/templates` then checking each match.
- [ ] `messages.success()` flashed after every successful POST (create, edit, delete, login).
- [ ] `python manage.py test` is green. Minimum tests: the seven `AuthProtectionTests` from Exercise 3, the seven `ArticleFormTests` from Exercise 2, plus a handful of integration tests below.
- [ ] `python manage.py check` clean.
- [ ] Committed and pushed under a `c16-week-03/` directory in your portfolio repo.

## Integration tests to include (~150 LOC)

In `writer/tests.py`, add `EndToEndTests(TestCase)`:

1. **Anon → public list → public detail**: GET `/`, assert 200; click the first article link; assert 200 and the title is in the response.
2. **Anon → blocked dashboard**: GET `/dashboard/`; assert 302 to `/accounts/login/?next=/dashboard/`.
3. **Anon → login → land on dashboard**: POST `/accounts/login/` with `next=/dashboard/new/`; assert redirected to `/dashboard/new/`.
4. **Logged-in → new article → public**: Log in; POST `/dashboard/new/` with `status="published"` and a 300-char body; assert redirect to detail; GET the detail anonymously; assert 200 and content present.
5. **Logged-in → edit own article**: POST `/dashboard/<pk>/edit/` with a new title; assert redirect; assert title persisted.
6. **Logged-in → cannot edit other user's article**: assert 404.

Each test ~20-30 lines. None should require more than five HTTP calls.

## Suggested order of operations

### Phase 1 — Templates and the public reader (90 min)

1. Write `writer/templates/writer/base.html` per Lecture 2.
2. Write `partials/article_card.html` and `partials/messages.html`.
3. Write `article_list.html` (`{% extends %}` base, loops articles using the card partial).
4. Write `article_detail.html`.
5. Add `ArticleListView` and `ArticleDetailView` (CBVs from Lecture 1).
6. Wire URLs. Visit `/` and `/articles/<slug>/`. Both render.

### Phase 2 — Forms and the create view (90 min)

1. Write `writer/forms.py` with `ArticleForm` per Exercise 2.
2. Write `writer/templates/writer/article_form.html` (loops fields, renders errors).
3. Add `ArticleCreateView` per Homework Problem 2.
4. Wire URLs. Log in via the admin first; visit `/dashboard/new/`; create an article.

### Phase 3 — Auth and the dashboard (90 min)

1. Add `path("accounts/", include("django.contrib.auth.urls"))` to the project's URLs.
2. Add `templates/registration/login.html` per Exercise 3.
3. Set `LOGIN_URL`, `LOGIN_REDIRECT_URL`, `LOGOUT_REDIRECT_URL` in `settings.py`.
4. Add `DashboardView` (`LoginRequiredMixin` + `ListView`).
5. Add `ArticleUpdateView` and `ArticleDeleteView` with `get_queryset()` filtering by author.
6. Add the log-out form to the header.

### Phase 4 — Tests (90 min)

1. Move (or copy) the `ArticleFormTests` and `AuthProtectionTests` from the exercises into `writer/tests.py`.
2. Write the six `EndToEndTests`.
3. `python manage.py test`. Fix until green.

### Phase 5 — Polish + documentation (45 min)

1. Run `ruff check .` if installed.
2. Add a `README.md` in `c16-week-03/` explaining how to run the project from scratch (create superuser, runserver, visit `/`).
3. Three screenshots: the public list, the login page, the dashboard with at least one article.
4. A "what I'd refactor" section, 100 words.

### Phase 6 — Final commit + push (15 min)

`git add c16-week-03/ writer/ templates/ project/settings.py project/urls.py` (whatever paths apply) and push.

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| All URLs work | 20% | Eight URLs, correct status codes, content where expected |
| Auth correctness | 20% | Anon → 302, owner-mismatch → 404, never 403, never the wrong one |
| Form validation | 15% | Both layers (`clean_<field>`, `clean()`); friendly errors |
| Templates | 15% | One base, two partials, no duplicated HTML, no `{{ form.as_p }}` |
| Tests | 15% | 20+ assertions, the six integration scenarios pass |
| Code clarity | 10% | No commented-out code; `get_queryset` filtering, not in-view checks |
| README quality | 5% | A fresh clone can run the project from your README |

## What this prepares you for

- **Week 4** moves the DB to PostgreSQL. The view layer is unchanged; this week's work is the front-end that next week's performance work pays off.
- **Week 5** introduces N+1 fixes and annotations. Your dashboard will get list-level counts (article count per category, view count per article) without extra queries.
- **Week 9** swaps the auth flow for OAuth + JWT. The view-protection patterns you internalize this week — `LoginRequiredMixin`, `get_queryset` filtering, CSRF on POST — are unchanged when you switch backends.
- **Week 11** writes tests against this exact code. You'll thank present-you for shipping `EndToEndTests` here.
- **Week 12** ships this to the open internet. Every CSRF protection and every login-required check you wrote this week is what stops a stranger from defacing the site.

## Submission

When done: push, then share the repo URL with a peer for a 30-minute review. Ask them specifically: "Try to reach `/dashboard/new/` without logging in. Try to edit my article from your account. Try to submit a form with bad input." If any of those does the wrong thing, fix and re-submit.

Then continue to [Week 4 — PostgreSQL for Application Developers](../../week-04-postgresql-for-app-developers/) — coming soon.
