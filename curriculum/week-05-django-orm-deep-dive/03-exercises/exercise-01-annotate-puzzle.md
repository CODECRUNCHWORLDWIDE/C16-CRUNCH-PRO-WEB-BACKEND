# Exercise 1 — Annotate Puzzle

**Time:** ~2 hours. **Goal:** Build five annotations of increasing complexity against your `crunchwriter` schema. For each, predict the SQL, verify it with `str(qs.query)`, and run `EXPLAIN ANALYZE` against the seeded data. By the end you should be able to read a Django annotation and know what SQL will fire.

Work in `python manage.py shell_plus --ipython`. Save every queryset and every emitted SQL to `c16-week-05/exercises/01-annotate.md`.

## Setup

Confirm the seed is populated:

```python
from writer.models import Article, Author, Category
Article.objects.count()  # expect >= 10000
Author.objects.count()   # expect >= 100
Category.objects.count() # expect >= 10
```

If any of those is too low, re-seed before starting.

Enable query logging in the shell:

```python
from django.db import connection, reset_queries
from django.conf import settings
settings.DEBUG = True   # if not already
```

## Part A — Five annotations, increasing in difficulty

For each of A1–A5: write the queryset, paste `str(qs.query)` into the write-up, evaluate it, paste the actual SQL from `connection.queries[-1]["sql"]`, and run `EXPLAIN (ANALYZE, BUFFERS)` against `psql crunchwriter`. Include the plan in the write-up. One full paragraph of explanation per annotation: what is being computed, why this shape, where the cost is.

### A1 — `article_count` per author

For every author, attach the number of articles they have written (any status).

```python
from django.db.models import Count

qs = Author.objects.annotate(article_count=Count("articles"))
```

**Expected SQL shape:** `LEFT OUTER JOIN writer_article ... GROUP BY writer_author.id, ...`

**Notes to write:** does the `GROUP BY` include every column of `writer_author`? Why?

### A2 — `published_count` per author, using `Count(..., filter=...)`

For every author, the number of their articles whose `status = 'published'`. **Not** the total count after filtering — every author should appear, including those with zero published articles.

```python
from django.db.models import Count, Q

qs = Author.objects.annotate(
    published_count=Count("articles", filter=Q(articles__status="published"))
)
```

**Expected SQL shape:** `COUNT(...) FILTER (WHERE writer_article.status = 'published')`

**Notes to write:** what does the row for an author with **zero** published articles look like? (Hint: `0`, not `NULL`, because `COUNT` of nothing is `0` — unlike `SUM`, which is `NULL`.)

### A3 — `total_views` per author, with `Coalesce` for the NULL case

For every author, the sum of `view_count` across all their **published** articles. Zero for authors with no published articles.

```python
from django.db.models import Sum, Q, Value
from django.db.models.functions import Coalesce

qs = Author.objects.annotate(
    total_views=Coalesce(
        Sum("articles__view_count", filter=Q(articles__status="published")),
        Value(0),
    )
)
```

**Expected SQL shape:** `COALESCE(SUM(...) FILTER (WHERE ...), 0)`

**Notes to write:** why does `SUM` return `NULL` for empty sets and `COUNT` returns `0`? Reference the SQL standard.

### A4 — The multiplication trap

Add a second annotation to A2 — the count of distinct **categories** the author has written in.

First write the wrong version:

```python
# WRONG
qs = Author.objects.annotate(
    published_count=Count("articles", filter=Q(articles__status="published")),
    category_count=Count("articles__category", distinct=False),
)
```

Pick an author with at least 3 articles. Inspect their `published_count` and `category_count`. They are both inflated.

Now write the correct version:

```python
qs = Author.objects.annotate(
    published_count=Count("articles", filter=Q(articles__status="published"), distinct=True),
    category_count=Count("articles__category", distinct=True),
)
```

**Notes to write:**

- Explain in your own words why the join in the first version produces inflated counts.
- Quote the value of `published_count` for one specific author in **both** the wrong and right versions.
- One sentence on when `Count(..., distinct=True)` is itself the wrong fix and you should reach for `Subquery` (preview of Exercise 2).

### A5 — Conditional bucketing with `Case` / `When`

Annotate every article with a `popularity_bucket`: `"viral"` if `view_count >= 10000`, `"popular"` if `>= 1000`, `"decent"` if `>= 100`, `"quiet"` otherwise. Then count how many articles fall in each bucket using a second queryset.

```python
from django.db.models import Case, When, Value, CharField

qs = Article.objects.annotate(
    bucket=Case(
        When(view_count__gte=10_000, then=Value("viral")),
        When(view_count__gte=1_000, then=Value("popular")),
        When(view_count__gte=100, then=Value("decent")),
        default=Value("quiet"),
        output_field=CharField(),
    )
)

# Then:
from django.db.models import Count
counts = qs.values("bucket").annotate(c=Count("*")).order_by("-c")
list(counts)
```

**Expected SQL shape:** a `CASE WHEN ... THEN ... ELSE ... END` in the `SELECT`; the second query uses that column in a `GROUP BY`.

**Notes to write:**

- What does the `output_field` argument do? What happens if you remove it?
- Why does `qs.values("bucket").annotate(c=Count("*"))` correctly group by `bucket` even though `bucket` is itself an annotation?

## Part B — Predict, then verify

For each of the five annotations, **before** running it, write down (in the markdown) one sentence predicting:

- Number of SQL queries when `list(qs)` is called.
- Whether a `JOIN` is involved, and which type (`INNER` or `LEFT OUTER`).
- Whether the plan will likely use an index or a Seq Scan, given the seeded data.

Then run it and confirm or correct each prediction. The point of the exercise is not to be right; it is to start forming predictions strong enough to be wrong.

## Part C — One annotation you write yourself

Pick any one annotation from your `crunchwriter` schema that you have not done above. Examples:

- For every category, the average word count of published articles.
- For every author, the slug of their most-recently-updated article (this one you cannot do with `annotate` alone — leads naturally into Exercise 2).
- For every article, a boolean `has_been_published` = `Q(status="published") & Q(published_at__isnull=False)`.

Write the queryset. Add it to the write-up with the SQL and a plan.

## Acceptance criteria

- [ ] `c16-week-05/exercises/01-annotate.md` exists.
- [ ] Five annotations (A1–A5) each with: queryset, predicted SQL shape, actual SQL, `EXPLAIN ANALYZE` plan, one-paragraph explanation.
- [ ] The multiplication trap (A4) is demonstrated with **specific numbers** for one author — wrong vs right.
- [ ] One self-chosen annotation in Part C.
- [ ] Total file length: ~300–500 lines of markdown.

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Predictions match reality | 25% | At least 4/5 predictions confirmed; the ones that didn't are explained |
| SQL reading | 25% | You can describe each plan node in one sentence |
| The trap demonstrated | 20% | A4 includes specific numbers from your data, not generic "this is inflated" |
| Self-chosen annotation | 15% | Non-trivial; not a simple `Count` on a relationship you already used |
| Write-up clarity | 15% | A peer can follow the file top-to-bottom without running the queries |

## Hints

- **`str(qs.query)`** does not show `EXPLAIN`. Run the SQL in `psql` and prepend `EXPLAIN (ANALYZE, BUFFERS)` there.
- **Parameters are missing in `str(qs.query)`** — Django prints them inlined for human reading. The bound parameters in `connection.queries` are the exact ones Postgres receives.
- **`reset_queries()`** clears the in-memory log; otherwise `connection.queries` accumulates across the whole shell session.
- **Wide tables** — your seeded `articles` table has at least a `body text` column. Use `.only("id", "title", "view_count", "status")` if you accidentally pull `body` into a queryset that fetches all rows.

## What this prepares you for

Exercise 2 takes the multiplication trap from A4 and resolves it with `Subquery` + `OuterRef`. Exercise 3 takes A5's bucketing and re-shapes it as a window function. The mini-project pulls all three exercises together into one dashboard view.
