# Mini-Project — `crunchwriter` Analytics Dashboard

> Build a four-panel analytics dashboard for `crunchwriter`. Every panel is fetched in **one query**. Every panel is covered by `assertNumQueries`. Every panel's SQL is verified with `EXPLAIN ANALYZE` and a one-paragraph justification of the plan shape lives in the README.

**Estimated time:** 7 hours, spread across Thursday–Saturday.

## What you build

A new view `/dashboard/analytics/`, accessible to staff users only, rendering four panels:

1. **Top authors by total published views.** Top 10. Columns: rank, username, published article count, total views, latest publication date, gold/silver/bronze tier.
2. **Articles by category.** For each category: total articles, published count, average view count, top-viewed article title.
3. **Most-active authors in the last 30 days.** Top 10. Columns: username, articles published in last 30 days, total views in last 30 days, most-recent title.
4. **Per-category top 3 articles.** For each category, the top 3 published articles by `view_count`. Displayed as a grouped list.

Each panel is **one queryset**, evaluated **once**, emitting **one SQL statement**. The dashboard view itself fires exactly four queries (one per panel) — verified by `assertNumQueries(4)` in a test.

The business logic — every annotation, every subquery, every window — lives on **custom querysets** in `writer/managers.py`. The view is a thin assembler.

## Acceptance criteria

- [ ] `/dashboard/analytics/` exists, returns 200, requires staff login.
- [ ] **Four panels** rendered, each with the columns above. Use a template that a non-engineer would call "a dashboard": tables with headers, sane formatting, no debug output visible.
- [ ] `writer/managers.py` has at least:
  - `AuthorQuerySet` with `.with_published_count()`, `.with_total_views()`, `.with_latest_published_at()`, `.with_recent_stats(days=30)`, `.with_views_tier()`, `.top_by_views(n=10)`, `.most_active(days=30, n=10)`.
  - `CategoryQuerySet` with `.with_article_counts()`, `.with_top_article()`, `.with_avg_views()`.
  - `ArticleQuerySet` with `.published()`, `.in_category()`, `.with_category_rank()`, `.top_n_per_category(n=3)`.
- [ ] Each panel uses **exactly one** queryset method chain in the view. No `for` loops that issue further queries.
- [ ] A test class `AnalyticsDashboardTests` in `writer/tests.py` with:
  - `test_dashboard_query_count` — `assertNumQueries(4)` (or 5 with auth middleware; document the count).
  - `test_dashboard_renders` — page returns 200 for a staff user, redirects for non-staff.
  - `test_top_authors_panel_data` — given a tiny fixture, asserts the top author's username and total-views value.
  - `test_recent_stats_panel_data` — likewise.
  - `test_per_category_top3` — asserts that for at least one category, the top-3 list has the right IDs in the right order.
- [ ] `c16-week-05/mini-project/README.md` (your portfolio) with the narrative — see "The write-up" below.
- [ ] For each of the four panels: the emitted SQL and the `EXPLAIN (ANALYZE, BUFFERS)` plan, with a one-paragraph plan reading. Saved as `panel-1.md`, `panel-2.md`, `panel-3.md`, `panel-4.md`.
- [ ] All artefacts checked in: managers, views, templates, tests, the four panel write-ups, the portfolio README.

## Suggested order of operations

### Phase 1 — The managers (90 min)

Before any view code, design the queryset methods. Open `writer/managers.py` and write them by name first — just the method signatures, with `pass` bodies and docstrings.

```python
# writer/managers.py
from django.db import models
from django.db.models import Q, F, Subquery, OuterRef, Window
from django.db.models.functions import Coalesce, Rank
from django.db.models import Count, Sum, Max, Avg, Value, IntegerField, CharField, Case, When


class AuthorQuerySet(models.QuerySet):
    def with_published_count(self):
        """Annotate each author with the count of their published articles."""
        ...

    def with_total_views(self):
        """Annotate each author with the sum of view_count across their published articles."""
        ...

    def with_latest_published_at(self):
        ...

    def with_recent_stats(self, days=30):
        """Annotate recent_count and recent_views over the last `days` days."""
        ...

    def with_views_tier(self):
        """Annotate a Case-based tier: gold/silver/bronze/unranked."""
        ...

    def top_by_views(self, n=10):
        """Compose with_total_views() + with_published_count() + with_views_tier(), order, slice."""
        ...

    def most_active(self, days=30, n=10):
        """Compose with_recent_stats() + with_latest_published_at(), order by recent_views, slice."""
        ...
```

Now fill them in, **one at a time**, in the shell. After each method works, write its test before moving on.

Use `Subquery` + `OuterRef` for the per-author aggregates. Do not use `annotate(Count("articles"), Sum("articles__view_count"))` chained together — you will hit the multiplication trap (Lecture 1, section 4). The right shape:

```python
def with_published_count(self):
    sq = (
        Article.objects.filter(author=OuterRef("pk"), status="published")
        .values("author")
        .annotate(c=Count("*"))
        .values("c")
    )
    return self.annotate(
        published_count=Coalesce(Subquery(sq, output_field=IntegerField()), Value(0))
    )
```

Then `with_total_views` is the same shape with `Sum("view_count")` instead of `Count("*")`. Then `with_latest_published_at` with `Max("published_at")`.

`top_by_views` chains:

```python
def top_by_views(self, n=10):
    return (
        self.with_published_count()
            .with_total_views()
            .with_latest_published_at()
            .with_views_tier()
            .filter(published_count__gte=1)
            .order_by("-total_views")[:n]
    )
```

One method per concern; composition by chaining. This is the architectural payoff of Week 5.

### Phase 2 — The view (45 min)

```python
# writer/views/analytics.py
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from writer.models import Author, Category, Article


@staff_member_required
def analytics_dashboard(request):
    top_authors = list(Author.objects.top_by_views(n=10))
    categories  = list(Category.objects.with_article_counts().with_top_article().with_avg_views())
    most_active = list(Author.objects.most_active(days=30, n=10))
    top_per_cat = Article.objects.top_n_per_category(n=3)
    return render(request, "writer/analytics_dashboard.html", {
        "top_authors": top_authors,
        "categories": categories,
        "most_active": most_active,
        "top_per_cat": top_per_cat,
    })
```

Four querysets, evaluated once each (`list(...)` forces evaluation). The `staff_member_required` decorator handles auth. The view is **20 lines** including imports.

For `top_n_per_category`, you have two paths from Exercise 3:

- **Path A (window function + Python filter):** annotate `cat_rank` with `Window(RowNumber())`, evaluate, then filter `cat_rank <= 3` in Python. **One** query.
- **Path B (Subquery pulling IDs):** subquery returning IDs of top-3 per category, then `filter(id__in=ids)`. **Two** queries.

Path A is one query but pulls every article into Python; Path B pulls 3 × `n_categories` rows. Pick based on numbers from your seed data and **defend the choice** in the write-up.

For "Path A in Django", since `Window` results cannot be filtered in the same `WHERE`, the implementation is:

```python
def top_n_per_category(self, n=3):
    qs = self.filter(status="published").annotate(
        cat_rank=Window(
            expression=RowNumber(),
            partition_by=[F("category_id")],
            order_by=F("view_count").desc(),
        ),
    )
    # Python-side filter, since the queryset is consumed once anyway:
    return [a for a in qs if a.cat_rank <= n]
```

This is **one** SQL query plus a Python filter — acceptable when the input set is bounded (10 categories × a few thousand articles = 30 000 rows, all of which Python handles in 50 ms).

### Phase 3 — The template (30 min)

`writer/templates/writer/analytics_dashboard.html`. Four `<section>` blocks, each a `<table>` with `<thead>` and `<tbody>`. Render the annotated columns directly: `{{ author.published_count }}`, `{{ author.total_views }}`, `{{ author.tier }}`. No `{% for x in obj.relation.all %}` loops — every value lives on the annotated object.

The template should be **readable**, not pretty. Bootstrap, Pico.css, or no CSS — your choice. The grading is on whether the data is correct and the queries are one each, not on visual polish.

### Phase 4 — The tests (90 min)

```python
# writer/tests/test_analytics.py
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AnalyticsDashboardTests(TestCase):
    fixtures = ["seed_analytics.json"]   # a small seed: 5 authors, 3 cats, 30 articles

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.get(username="admin")
        self.client.force_login(self.staff)

    def test_dashboard_query_count(self):
        with self.assertNumQueries(4):   # one per panel; adjust if your auth/session adds more
            response = self.client.get(reverse("writer:analytics_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_renders(self):
        response = self.client.get(reverse("writer:analytics_dashboard"))
        self.assertContains(response, "Top authors")
        self.assertContains(response, "Most active")

    def test_non_staff_redirected(self):
        User = get_user_model()
        normal = User.objects.create_user("normal", "n@example.com", "pw")
        self.client.force_login(normal)
        response = self.client.get(reverse("writer:analytics_dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_top_authors_panel_data(self):
        # Given the fixture, the top author by total_views should be 'author_1' with 12 345 views
        response = self.client.get(reverse("writer:analytics_dashboard"))
        self.assertContains(response, "author_1")
        # ...assert the numeric value too, parsed from context if you prefer

    def test_per_category_top3(self):
        response = self.client.get(reverse("writer:analytics_dashboard"))
        top_per_cat = response.context["top_per_cat"]
        # Group by category, assert top 3 per category against known fixture IDs
        ...
```

The `assertNumQueries(4)` test is the single most important assertion in this mini-project. If your count is 5 or 6, you have an N+1 somewhere — find it before moving on. The toolbar's SQL panel is the fastest way to spot it.

### Phase 5 — The panel write-ups (60 min)

For each of the four panels: paste the emitted SQL (from `connection.queries[-1]["sql"]` after running the view in the shell), then the `EXPLAIN (ANALYZE, BUFFERS)` from `psql`, then one paragraph of plan reading.

Example for Panel 1:

```markdown
## Panel 1 — Top authors by total views

### Queryset
`Author.objects.top_by_views(n=10)` — chains `with_published_count`, `with_total_views`,
`with_latest_published_at`, `with_views_tier`, filters `published_count >= 1`, orders.

### Emitted SQL
```sql
SELECT writer_author.id, writer_author.username, ...,
       COALESCE((SELECT COUNT(*) FROM writer_article ... ), 0) AS published_count,
       COALESCE((SELECT SUM(view_count) FROM writer_article ... ), 0) AS total_views,
       (SELECT MAX(published_at) FROM writer_article ... ) AS latest_published_at,
       CASE WHEN ... END AS tier
FROM writer_author
WHERE (SELECT COUNT(*) ...) >= 1
ORDER BY total_views DESC
LIMIT 10;
```

### Plan
```
Limit (cost=... rows=10)
  -> Sort
       Sort Key: total_views DESC
       -> Seq Scan on writer_author
            Filter: (...)
            SubPlan 1 (returns published_count)
            SubPlan 2 (returns total_views)
            SubPlan 3 (returns latest_published_at)
Execution time: 47 ms
```

### Reading
The plan runs three correlated subqueries per author. With 200 authors and an index on
`writer_article (author_id, status)` plus `(author_id, status, view_count)`, each subquery is an
Index Scan returning 5-30 rows on average. Total cost is dominated by the SubPlans; the outer Seq
Scan on `writer_author` is trivial. Adding `(author_id, status, view_count) WHERE status = 'published'`
as a partial index brought time from 320 ms to 47 ms — a 7× win.
```

Do this for all four panels. The combined four-panel write-up is the heart of the mini-project's value.

### Phase 6 — The portfolio README (60 min)

`c16-week-05/mini-project/README.md`. Sections:

- **The build** — what `/dashboard/analytics/` is, who it is for, the four panels. 1 paragraph.
- **The architecture** — `writer/managers.py` is the queries' home. The view is an assembler. Link to the file.
- **The four queries** — one bullet per panel, with the headline number (rows × ms).
- **The decision log** — one paragraph per non-obvious choice. Examples: "Used `Subquery` instead of `Count(..., distinct=True)` because I had three annotations on the same relation, which would multiply." "Used Window + Python filter for the top-3-per-category panel because measured ms was lower than the two-query Subquery alternative; if the data grew 10×, I would revisit."
- **What I would do next** — 1 paragraph. Caching the dashboard for 60 seconds in Redis (Week 6 preview), pagination on the author tables, exporting to CSV.
- **The screenshots** — the dashboard rendered, with `django-debug-toolbar` open showing **4** queries.

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Query counts | 25% | `assertNumQueries(4)` passes; debug toolbar agrees |
| Manager hygiene | 20% | Methods are small, named, chainable; view is < 25 lines |
| Plan reading | 20% | Each panel has a paragraph naming the bottleneck and the index that fixes it |
| Data correctness | 15% | Fixture-based tests assert specific values, not just "200 OK" |
| Decision log | 10% | At least three non-obvious decisions defended |
| Polish | 10% | Templates render cleanly; the staff-required gate works |

## What this prepares you for

- **Week 6** caches the analytics panels in Redis. Per-panel cache keys, invalidation on `Article.save()`, the cache stampede problem. Your one-query-per-panel architecture means **one Redis key per panel** — clean. A view with 200 queries cannot be cached coherently.
- **Week 7** exposes a FastAPI endpoint that returns the same data as JSON for a future React dashboard. The queryset methods you wrote here are reused in the FastAPI side as well — same SQL, different surface.
- **Week 11** asserts the SQL count of the dashboard view in CI with `django-perf-rec`. The day someone changes the view and adds a query, CI fails.
- **Week 12** ships this to production. The first thing a real user does on the dashboard is hit four panels at once; the difference between "4 queries totaling 50 ms" and "200 queries totaling 4 s" is the difference between a usable dashboard and one nobody opens twice.

## Submission

When done: push, then share the repo URL with a peer. Ask them: "Open `/dashboard/analytics/`, then open the SQL panel. Count the queries. Is it 4?" If they get a different number, you did not finish.

Then continue to [Week 6 — Migrations, Background Jobs, and Caching](../../week-06-migrations-jobs-caching/) — where this dashboard learns to cache, refresh in the background, and stay responsive under real traffic.
