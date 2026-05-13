# Exercise 3 — Login and protected views

**Time:** ~2.5 hours. **Goal:** Stand up a real login flow, protect the dashboard with `LoginRequiredMixin`, and write tests that prove anonymous traffic can't see logged-in pages.

## Part A — Wire up `django.contrib.auth.urls` (30 min)

In your project's `urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("writer.urls")),
]
```

In `settings.py`:

```python
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "writer:dashboard"
LOGOUT_REDIRECT_URL = "writer:article_list"
```

Create the login template at `templates/registration/login.html` (note the path — Django's auth views look for it there). Extend `writer/base.html`. Loop the fields, render `{% csrf_token %}`, include the hidden `next` input.

Visit `/accounts/login/`. The page should render. Try the wrong credentials; see the form error. Log in with a real user; you'll be redirected to `/dashboard/` (which doesn't exist yet — that's Part B).

## Part B — Build the protected dashboard (45 min)

In `writer/views.py`:

```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from .models import Article

class DashboardView(LoginRequiredMixin, ListView):
    template_name = "writer/dashboard.html"
    context_object_name = "articles"
    paginate_by = 20

    def get_queryset(self):
        return (
            Article.objects.filter(author=self.request.user)
            .order_by("-created_at")
        )
```

Route:

```python
path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
```

Template `writer/templates/writer/dashboard.html`:

```django
{% extends "writer/base.html" %}
{% block title %}Dashboard · {{ block.super }}{% endblock %}
{% block content %}
  <h1>Your articles</h1>
  <p><a href="{% url 'writer:article_new' %}">+ New article</a></p>
  <table>
    <thead><tr><th>Title</th><th>Status</th><th>Created</th><th></th></tr></thead>
    <tbody>
      {% for article in articles %}
        <tr>
          <td>{{ article.title }}</td>
          <td>{{ article.get_status_display }}</td>
          <td>{{ article.created_at|date:"Y-m-d" }}</td>
          <td><a href="{% url 'writer:article_edit' pk=article.pk %}">Edit</a></td>
        </tr>
      {% empty %}
        <tr><td colspan="4">No articles yet. <a href="{% url 'writer:article_new' %}">Write one.</a></td></tr>
      {% endfor %}
    </tbody>
  </table>
{% endblock %}
```

## Part C — Owner-only edit (30 min)

Add an `ArticleUpdateView` that **only the article's author can reach**:

```python
from django.views.generic.edit import UpdateView
from django.urls import reverse_lazy
from .forms import ArticleForm

class ArticleUpdateView(LoginRequiredMixin, UpdateView):
    model = Article
    form_class = ArticleForm
    template_name = "writer/article_form.html"

    def get_queryset(self):
        return Article.objects.filter(author=self.request.user)

    def get_success_url(self):
        return reverse_lazy("writer:dashboard")
```

Notice we filter at `get_queryset()`. If user `alice` tries to edit user `bob`'s article via `/dashboard/<bob_article_pk>/edit/`, Django raises a 404 — not a 403. **Do not change this.** A 404 reveals less information than a 403; an attacker doesn't even learn that an article with that ID exists.

Route:

```python
path("dashboard/<int:pk>/edit/", views.ArticleUpdateView.as_view(), name="article_edit"),
```

## Part D — Test the protections (45 min)

In `writer/tests.py`, add `AuthProtectionTests(TestCase)`:

```python
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Article

User = get_user_model()

class AuthProtectionTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="pw")
        self.bob = User.objects.create_user(username="bob", password="pw")
        self.alice_article = Article.objects.create(
            title="alice's article", slug="alices", author=self.alice, body="hi"
        )

    def test_dashboard_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse("writer:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)
        self.assertIn("next=", resp.url)

    def test_dashboard_logged_in_renders(self):
        self.client.login(username="alice", password="pw")
        resp = self.client.get(reverse("writer:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alice's article")

    def test_dashboard_only_shows_own_articles(self):
        Article.objects.create(title="bob's", slug="bobs", author=self.bob, body="hi")
        self.client.login(username="alice", password="pw")
        resp = self.client.get(reverse("writer:dashboard"))
        self.assertContains(resp, "alice's article")
        self.assertNotContains(resp, "bob's")

    def test_edit_other_users_article_returns_404(self):
        self.client.login(username="bob", password="pw")
        resp = self.client.get(
            reverse("writer:article_edit", kwargs={"pk": self.alice_article.pk})
        )
        self.assertEqual(resp.status_code, 404)

    def test_edit_own_article_renders(self):
        self.client.login(username="alice", password="pw")
        resp = self.client.get(
            reverse("writer:article_edit", kwargs={"pk": self.alice_article.pk})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alice's article")
```

Run `python manage.py test writer.tests.AuthProtectionTests`. All five should pass.

## Acceptance

- [ ] `/accounts/login/` renders and authenticates.
- [ ] `/dashboard/` redirects anonymous users to login with `?next=/dashboard/`.
- [ ] `/dashboard/` shows only the logged-in user's articles.
- [ ] Editing another user's article returns 404, not 403.
- [ ] All five tests in `AuthProtectionTests` pass.
- [ ] Logging out and logging back in works; after login, you land on the dashboard.

## Stretch

- Add a "Log out" button to `base.html` as a `<form method="post">` that POSTs to `{% url 'logout' %}`. Confirm a GET to `/accounts/logout/` returns 405 (POST-only since Django 5.0).
- Add `?next=/dashboard/new/` to a "+ New article" link from the public list, then verify that after login an anonymous user lands directly on the new-article page rather than the dashboard.
- Add an integration test that walks the entire flow: GET login → POST login → GET dashboard → POST new article → GET detail page. One test, ~30 lines.
