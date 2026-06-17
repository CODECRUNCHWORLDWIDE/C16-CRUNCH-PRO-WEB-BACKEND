# Exercise 3 — Window Functions

**Time:** ~2.5 hours. **Goal:** Use Django 5.x's `Window` expression to compute per-row analytics over partitions. Write five window queries against `crunchwriter`. Compare each to the `Subquery` form from Exercise 2 where applicable.

Work in `python manage.py shell_plus --ipython`. Save every queryset and SQL to `c16-week-05/exercises/03-window.md`.

## Setup

Same dataset. Confirm the Postgres version supports window functions properly:

```python
from django.db import connection
with connection.cursor() as c:
    c.execute("SHOW server_version;")
    print(c.fetchone())
# expect 16.x or later
```

Window functions have been in Postgres since 8.4 (2009) and stable since forever; Django's `Window` wrapper is in `django.db.models`.

## Part A — Five window queries

For each: write the queryset, paste `str(qs.query)`, evaluate it, paste the actual SQL from `connection.queries[-1]["sql"]`, run `EXPLAIN (ANALYZE, BUFFERS)`. One paragraph of explanation per query.

### W1 — Rank each article within its category by views

```python
from django.db.models import F, Window
from django.db.models.functions import Rank
from writer.models import Article

qs = Article.objects.filter(status="published").annotate(
    cat_rank=Window(
        expression=Rank(),
        partition_by=[F("category_id")],
        order_by=F("view_count").desc(),
    ),
)
```

**Verify:**

- The plan should include a `WindowAgg` node.
- For one category, pull the top 3 articles by `cat_rank` and confirm they match the `ORDER BY view_count DESC LIMIT 3` for that category.
- Could you filter `cat_rank <= 3` in the same query? Try it. What error or behaviour do you see, and why?

### W2 — Row number (no ties) vs Rank vs DenseRank

Run all three side by side:

```python
from django.db.models.functions import Rank, DenseRank, RowNumber

qs = Article.objects.filter(status="published").annotate(
    row_n=Window(expression=RowNumber(), partition_by=[F("category_id")], order_by=F("view_count").desc()),
    rank_=Window(expression=Rank(),      partition_by=[F("category_id")], order_by=F("view_count").desc()),
    drank=Window(expression=DenseRank(), partition_by=[F("category_id")], order_by=F("view_count").desc()),
)
```

**Verify:**

- Find a category in which at least two articles share the same `view_count`. Print `(title, view_count, row_n, rank_, drank)` for the top 6 articles in that category.
- Explain in the write-up the difference between the three:
  - `RowNumber`: sequential, ties broken arbitrarily.
  - `Rank`: ties share a number; next rank skips.
  - `DenseRank`: ties share; next rank does not skip.

If you do not have ties in your seeded data, run an `UPDATE writer_article SET view_count = 1000 WHERE id IN (...)` to manufacture some, then re-run.

### W3 — Running total of views per author

For each article, the cumulative `view_count` the author has earned across all their published articles, ordered by `published_at`.

```python
from django.db.models import Sum

qs = Article.objects.filter(status="published").annotate(
    running_views=Window(
        expression=Sum("view_count"),
        partition_by=[F("author_id")],
        order_by=F("published_at").asc(),
    ),
)
```

**Verify:**

- Pick one author. Order their articles by `published_at` and confirm `running_views` is monotonically non-decreasing.
- Discuss the frame clause: by default Postgres uses `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. What does that mean for ties on `published_at`?

### W4 — Lag — delta from previous article

For each article, how many more (or fewer) views it earned than the **previous** article by the same author.

```python
from django.db.models.functions import Lag, Coalesce
from django.db.models import Value, IntegerField

qs = Article.objects.filter(status="published").annotate(
    prev_views=Window(
        expression=Lag("view_count"),
        partition_by=[F("author_id")],
        order_by=F("published_at").asc(),
    ),
).annotate(
    delta=F("view_count") - Coalesce(F("prev_views"), Value(0)),
)
```

**Verify:**

- The first article per author (by date) should have `prev_views = NULL` and therefore `delta = view_count`.
- Compare to a `Subquery` form that fetches the previous article per author. Paste both plans. Which is faster on your data? Why?

### W5 — Top-N per group, the right way

The question "give me the top 3 articles by views per category" is the canonical use of a window function. Combine `RowNumber` with a subquery filter:

```python
from django.db.models import Subquery

inner = Article.objects.filter(status="published").annotate(
    rn=Window(
        expression=RowNumber(),
        partition_by=[F("category_id")],
        order_by=F("view_count").desc(),
    ),
).values("id", "category_id", "title", "view_count", "rn")

# In modern Django, .filter on the annotated value works in a subquery:
# Wrap as a raw .filter at the outer level by re-querying:
ids = [row["id"] for row in inner if row["rn"] <= 3]
top_per_category = Article.objects.filter(id__in=ids)
```

This is two queries (one to pull the IDs, one to fetch the articles) but the second is cheap. The cleaner pure-SQL form is a `WHERE rn <= 3` wrapped around the windowed query; in the ORM that means either dropping to `RawSQL` for the rank or using a `Subquery` of the windowed queryset.

**Alternative — `RawSQL` for the win:**

```python
from django.db.models.expressions import RawSQL

qs = Article.objects.filter(status="published").extra(
    select={"rn": "ROW_NUMBER() OVER (PARTITION BY category_id ORDER BY view_count DESC)"},
).extra(where=["1=1"]).order_by("category_id", "view_count")
# Note: extra() is legacy; this is an example, not a recommendation. Prefer the two-query form.
```

**Verify:**

- Run the two-query version. Print the result grouped by category.
- Explain in the write-up why `WHERE rn <= 3` cannot live in the same `SELECT` as the window function (hint: window functions are evaluated after `WHERE` but before `ORDER BY`).
- Discuss when this pattern is worth the extra complexity vs running 10 small `LIMIT 3` queries (one per category).

## Part B — Compare a window to a subquery

In Exercise 2 you wrote a `Subquery` to fetch the previous article per author (Part C, optionally). Now redo it with `Lag` (W4 above). Write both queries side by side in the write-up. Compare:

- Lines of code.
- Emitted SQL — which is more concise?
- `EXPLAIN ANALYZE` execution time on your dataset.
- Readability — which would you choose for the dashboard view?

Land on a defensible rule for "when to use a window vs a subquery". Two sentences is enough.

## Part C — One window query of your own

Pick a real question against your `crunchwriter` schema and answer it with a window function. Examples:

- For each comment, the position of that comment within its article's comment thread (`RowNumber` ordered by `created_at`).
- For each category, the rolling 7-day average of articles published, by date.
- For each article, the **percentile** of its `view_count` within its category (`PercentRank()`).

Write the queryset, paste SQL and plan, defend the choice.

## Acceptance criteria

- [ ] `c16-week-05/exercises/03-window.md` exists.
- [ ] Five queries in Part A, each with queryset, SQL, plan, one-paragraph note.
- [ ] Part B has the window-vs-subquery comparison with measurements.
- [ ] Part C has one self-chosen window query.
- [ ] Every plan that includes a `WindowAgg` is named and discussed.
- [ ] Total file length: ~350–500 lines of markdown.

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Window-function correctness | 25% | All five W queries run; results spot-checked against expectations |
| Plan reading | 25% | `WindowAgg` node identified; `partition_by` and `order_by` semantics understood |
| Window vs Subquery comparison | 25% | Numbers, not vibes; a defended rule of thumb at the end |
| Self-chosen query | 15% | Non-trivial; demonstrates a window function not used in Part A |
| Write-up | 10% | A peer can follow |

## Hints

- **`partition_by` must be a list**, even if it has one element. `partition_by=[F("category_id")]`, not `partition_by=F("category_id")`.
- **`order_by` for windows** is a single expression or a tuple. `order_by=F("view_count").desc()` works; so does `order_by=(F("view_count").desc(), F("published_at").desc())` for tie-breaking.
- **`Frame` is rarely needed** — the default `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` is what most queries want. If you do need a custom frame, see the Django docs on `Frame`, `RowRange`, and `ValueRange`.
- **`WHERE rn <= 3` does not work in the same `SELECT`** — window functions are computed after `WHERE`. To filter on a window result you need a subquery wrapping the windowed query.
- **An index helps but is not required** — Postgres can compute a window over an unsorted input; it will sort internally. An index on `(partition_col, order_col)` makes the window free.

## What this prepares you for

The mini-project includes one panel that is naturally a window query — "top 3 articles per category, sorted by views". You will have two implementations to choose from (window with subquery, or pure subquery), and the measurements from this exercise tell you which to pick.
