# Week 5 — Homework

Six problems, ~6h. Build them in your `crunchwriter` repo under `c16-week-05/homework/`.

All problems run against `crunchwriter` on PostgreSQL 16. If you do not have at least 10 000 articles seeded, do that first.

---

## Problem 1 — Find and fix one N+1 (45 min)

**File:** `c16-week-05/homework/01-nplusone.md`.

1. Pick **one view** in your `crunchwriter` project — the article list, the author dashboard, the article detail, or a homepage. Whichever you suspect.
2. Wrap a test in `assertNumQueries(N)` where `N` is what the view **should** emit (typically 2: one count, one page).
3. Run the test. If it passes, pick another view; you want one that fails.
4. Open `django-debug-toolbar` on the page in the browser. Click the **SQL** panel. Identify the duplicate query shape.
5. Add the right `select_related` or `prefetch_related`. Re-run the test.

In `01-nplusone.md`:

- Name the view and the line of code (URL pattern + view function).
- Paste the **before** SQL panel — count and one example of the duplicate.
- Paste the **after** count.
- One paragraph on why this N+1 happened — typically "the template traverses `{{ obj.related.attr }}` and the view didn't select_related". Be specific.

**Acceptance:** the test now passes; the count drops to your target; the file has the before/after evidence.

---

## Problem 2 — Convert helper functions into a custom queryset (60 min)

**File:** `c16-week-05/homework/02-manager.md`.

Pick your `crunchwriter`'s most-used model (probably `Article`). Find every place in the codebase that does `Article.objects.filter(...)` with a non-trivial predicate. Catalogue them — there are typically 4–8 in a Week-3 project.

Build `writer/managers.py` with `ArticleQuerySet` containing at least **five chainable methods**:

- `.published()` — `status="published"` and `published_at__isnull=False`.
- `.drafts()` — `status="draft"`.
- `.for_author(author)`.
- `.in_category(slug_or_obj)`.
- One method you invented based on your codebase's actual usage.

Wire it: `objects = ArticleQuerySet.as_manager()`.

Refactor every site that previously did `Article.objects.filter(status="published")` to use `Article.objects.published()`.

In `02-manager.md`:

- The new `ArticleQuerySet` code.
- A diff (or before/after snippet) of one view that used the old shape.
- One paragraph: did you find any predicate that was duplicated with subtle differences across views — like one using `status="published"` and another adding `published_at__isnull=False`? This is the bug class custom querysets exist to eliminate.

**Acceptance:** the manager exists; at least three views use it; all tests still pass.

---

## Problem 3 — One aggregate per panel (60 min)

**File:** `c16-week-05/homework/03-aggregate.md`.

In your author dashboard view, find every `count()`, `sum(...)`, `avg(...)` call you make against the database. Combine them into **one** `aggregate(...)` call.

Before (typical Week 3 shape):

```python
total = Article.objects.filter(author=request.user, status="published").count()
total_views = sum(a.view_count for a in Article.objects.filter(...))
latest = Article.objects.filter(...).order_by("-published_at").first()
```

After:

```python
stats = Article.objects.filter(author=request.user, status="published").aggregate(
    total=Count("*"),
    total_views=Coalesce(Sum("view_count"), Value(0)),
    latest_at=Max("published_at"),
)
```

In `03-aggregate.md`:

- Before and after view code.
- The `connection.queries` log for the before — how many queries did the old shape issue?
- The `connection.queries` log for the after — should be 1.
- An `assertNumQueries(1)` test for the panel.

**Acceptance:** one query for the panel; tested.

---

## Problem 4 — Add a `Subquery` annotation (60 min)

**File:** `c16-week-05/homework/04-subquery.md`.

Pick a question your `crunchwriter` schema currently answers with two queries and refactor it into one with `Subquery` + `OuterRef`. Candidate questions:

- For each author on the author-list page, the title of their most recent published article.
- For each article on the article-list page, the count of approved comments.
- For each category on the category-list page, the most-viewed published article in that category.

Write the queryset. Use it in a view. Add an `assertNumQueries(2)` test (1 count, 1 page).

In `04-subquery.md`:

- The original shape (likely an N+1 or a 1+1 across two queries).
- The new shape with `Subquery`.
- The emitted SQL for the new shape.
- The plan from `EXPLAIN ANALYZE` against your seeded data.
- One paragraph on whether the `Subquery` form is faster than the N+1 form on your data. Sometimes it is not — say so honestly.

**Acceptance:** the view runs; the test passes; the write-up has SQL + plan.

---

## Problem 5 — A window function in production code (60 min)

**File:** `c16-week-05/homework/05-window.md`.

Add a window function to one real surface of your project. Two reasonable choices:

- **The article detail page** — show the article's rank within its category by views.
- **The author dashboard** — show each of the author's articles with its position (1st, 2nd, ...) by publication date.

Implement with `Window(Rank())` or `Window(RowNumber())`. Pass the value into the template.

In `05-window.md`:

- The view code.
- The template snippet that displays the rank.
- The emitted SQL.
- The `EXPLAIN ANALYZE` plan. The plan should include `WindowAgg`.
- One paragraph: did the window add visible cost on your dataset? What index would help if it did?

**Acceptance:** the rank is visible on the page; the test passes; the plan is included.

---

## Problem 6 — Reflection (45 min)

`c16-week-05/homework/06-reflection.md`, ~400 words:

1. **`select_related` vs `prefetch_related`** — describe in your own words the exact mechanical difference (number of queries, kind of SQL, what relationship each handles). Then describe when both are wrong and you should `Subquery` instead.
2. **The `assertNumQueries` habit** — did the test add real value, or did it feel like ceremony? Did it catch anything you would have shipped otherwise? Be honest.
3. **Custom querysets, in hindsight** — would you have built `crunchwriter` from Week 2 with a custom queryset on `Article`? What would have been the cost of doing so before you knew you needed it?
4. **One thing you still do not fully understand** — name it. Three sentences. This is the question to bring to Week 6's Q&A.

---

## Time budget

| Problem | Time |
|--------:|----:|
| 1 — N+1 | 45 min |
| 2 — Custom queryset | 60 min |
| 3 — One `aggregate` | 60 min |
| 4 — `Subquery` annotation | 60 min |
| 5 — Window function | 60 min |
| 6 — Reflection | 45 min |
| **Total** | **~5h 30m** |

After homework, ship the [mini-project](./07-mini-project/00-overview.md) — the `crunchwriter` analytics dashboard, every panel in one query.
