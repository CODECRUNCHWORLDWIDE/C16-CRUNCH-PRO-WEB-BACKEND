# Exercise 2 — Subquery with `OuterRef`

**Time:** ~2.5 hours. **Goal:** Master the `Subquery` + `OuterRef` pattern. Write four correlated subqueries against `crunchwriter`. Verify the emitted SQL and the plan. By the end you should be able to translate any "for each row in X, give me one value computed from Y" question into a single queryset.

Work in `python manage.py shell_plus --ipython`. Save every queryset and every emitted SQL to `c16-week-05/exercises/02-subquery.md`.

## Setup

Same data as Exercise 1 — at least 10 000 articles, 100 authors, 10 categories. Confirm `Article.objects.count()` is in the right range.

For one of the queries you will need an index. Add it now if missing:

```python
# In a migration, or in psql for the exercise:
# CREATE INDEX IF NOT EXISTS writer_article_author_published_idx
#   ON writer_article (author_id, published_at DESC) WHERE status = 'published';
```

This index supports "the latest published article per author" — without it, the plan is a sort over the entire table per author, and the subquery looks slower than it should.

## Part A — Four correlated subqueries

For each: write the queryset, paste `str(qs.query)`, evaluate, paste the actual SQL, run `EXPLAIN (ANALYZE, BUFFERS)`. One paragraph of explanation per query.

### S1 — Latest published article title per author

```python
from django.db.models import Subquery, OuterRef
from writer.models import Author, Article

latest = Article.objects.filter(
    author=OuterRef("pk"),
    status="published",
).order_by("-published_at").values("title")[:1]

qs = Author.objects.annotate(latest_title=Subquery(latest))
```

**Verify in your write-up:**

- The inner `Article` queryset must end in `.values("title")[:1]`. Remove the `.values()` and rerun — what error does Django raise?
- The plan should show a correlated `SubPlan` or `InitPlan` over `writer_article`. Without the index, what does the plan look like for authors with many articles?

### S2 — Published article count per author, via `Subquery` (avoiding the multiplication trap)

In Exercise 1 A4 you used `Count(..., distinct=True)`. Now redo it as a `Subquery`:

```python
from django.db.models import IntegerField, Value
from django.db.models.functions import Coalesce

published_count_sq = (
    Article.objects.filter(author=OuterRef("pk"), status="published")
    .values("author")
    .annotate(c=Count("*"))
    .values("c")
)

qs = Author.objects.annotate(
    published_count=Coalesce(Subquery(published_count_sq, output_field=IntegerField()), Value(0)),
)
```

**Verify:**

- Compare the plan to A2 from Exercise 1. Is the subquery version slower or faster on your data? By how much (in `EXPLAIN ANALYZE` execution time)?
- One sentence: when would the subquery be **slower** than the `Count(..., distinct=True)` form?

### S3 — `Exists` — authors who have published in 2026

```python
from django.db.models import Exists

published_2026 = Article.objects.filter(
    author=OuterRef("pk"),
    status="published",
    published_at__year=2026,
)

# As an annotation
qs = Author.objects.annotate(has_published_2026=Exists(published_2026))

# As a filter
qs_only = Author.objects.filter(Exists(published_2026))

# Negated — authors who have NOT published in 2026
qs_quiet = Author.objects.filter(~Exists(published_2026))
```

**Verify all three forms.** Paste the SQL for each. Compare the plan for `qs_quiet` (the `NOT EXISTS` form) to `Author.objects.exclude(articles__status="published", articles__published_at__year=2026)`. They are **not equivalent** — explain why in your write-up.

### S4 — Most-viewed article per category

For each category, annotate the title of the most-viewed published article in that category.

```python
top = (
    Article.objects.filter(category=OuterRef("pk"), status="published")
    .order_by("-view_count")
    .values("title")[:1]
)
top_views = (
    Article.objects.filter(category=OuterRef("pk"), status="published")
    .order_by("-view_count")
    .values("view_count")[:1]
)

qs = Category.objects.annotate(
    top_article_title=Subquery(top),
    top_article_views=Subquery(top_views),
)
```

**Verify:**

- The plan should show two correlated subqueries. Could Postgres merge them? (Hint: it can, if their shapes are identical. Look at the plan carefully.)
- Discuss the trade-off vs returning the **ID** of the top article and then re-fetching in bulk. Which would you reach for in a real view? Why?

## Part B — Translate a hand-written SQL into the ORM

Given this SQL:

```sql
SELECT a.id, a.username,
       (SELECT count(*) FROM writer_article art
         WHERE art.author_id = a.id
           AND art.status = 'published'
           AND art.published_at >= now() - interval '30 days') AS recent_count,
       (SELECT max(art.published_at) FROM writer_article art
         WHERE art.author_id = a.id AND art.status = 'published') AS latest_at
FROM writer_author a
ORDER BY recent_count DESC NULLS LAST
LIMIT 20;
```

Reproduce it in the ORM as one queryset. Constraints:

- Use `Subquery` + `OuterRef`, not `annotate(Count(...))`.
- Use `Coalesce` so `recent_count` is `0` for authors with no recent articles.
- Use `now() - interval '30 days'` via `from django.utils import timezone; from datetime import timedelta; cutoff = timezone.now() - timedelta(days=30)`.

Paste your queryset, the emitted SQL, and the plan. Compare side-by-side to the hand-written SQL above. Are the plans identical? Differences?

## Part C — One subquery of your own

Invent one correlated subquery against the `crunchwriter` schema that is **not** in Parts A or B. Examples:

- For each category, the username of the most prolific author in that category.
- For each article, the title of the **previous** article by the same author (by `published_at`). (Hint: this is also expressible as a window function — `Lag`. Do it with `Subquery` first; in Exercise 3 you will do it with `Lag` and compare.)
- For each author, the slug of the most-commented article they have written.

Write the queryset, paste the SQL and plan, defend the choice.

## Acceptance criteria

- [ ] `c16-week-05/exercises/02-subquery.md` exists.
- [ ] Four queries in Part A, each with queryset code, SQL, plan, one-paragraph note.
- [ ] Part B has the ORM translation, side-by-side with the hand-written SQL.
- [ ] Part C has one self-invented subquery.
- [ ] Every plan node above 10 ms is named and discussed.
- [ ] Total file length: ~350–500 lines of markdown.

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Subquery correctness | 25% | Every query runs; results match expectations |
| Plan reading | 25% | Each plan's bottleneck is named, not just timed |
| Part B translation | 20% | The ORM emits SQL very close to the hand-written; differences explained |
| Self-chosen subquery | 15% | Non-trivial; not a copy of one from Part A |
| Write-up | 15% | A peer can read top-to-bottom and follow the reasoning |

## Hints

- **`.values("col")[:1]`** is required for scalar `Subquery`. Forgetting either piece is the most common mistake — slice without `values` gives "expected one column", `values` without slice gives "more than one row".
- **`output_field=`** must be passed when the ORM cannot infer the type. `Subquery(qs, output_field=IntegerField())`. If you forget and get `FieldError`, that is the fix.
- **`OuterRef("pk")`** is the most common form; you can also write `OuterRef("id")` or `OuterRef("any_field")`. Use `pk` for portability — if you change the primary key field name later, `pk` still resolves.
- **`Coalesce` for nullable subqueries** — `SUM(...)` and `MAX(...)` return `NULL` for empty inputs. `COUNT(*)` returns `0`. `Coalesce(Subquery(...), Value(0))` is the right shape for sums.
- **Postgres `EXISTS` short-circuits** — the optimiser stops as soon as one matching row is found. `Exists(...)` is dramatically faster than `Count(...) > 0` on large tables.

## What this prepares you for

Exercise 3 introduces window functions, which solve some of the same problems with different syntax. The mini-project's "top 5 authors by views" panel uses the Part A S2 pattern. The "previous article per author" panel uses S4 or a window function — your choice, defended with measurements.
