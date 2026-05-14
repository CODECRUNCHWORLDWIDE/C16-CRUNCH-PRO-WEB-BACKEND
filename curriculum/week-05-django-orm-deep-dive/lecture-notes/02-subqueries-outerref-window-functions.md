# Lecture 2 — Subqueries, `OuterRef`, `Exists`, `Q`, `F`, Window Functions

> **Duration:** ~2 hours. **Outcome:** You can write any correlated subquery the ORM permits, you reach for `Exists` instead of `count() > 0` by reflex, and you know which questions belong to a window function rather than a `GROUP BY`.

Lecture 1 covered the four daily-driver tools. This lecture is the next ring of competence: the tools that let you stop dropping into raw SQL when an `annotate` is the wrong shape. By the end you should be able to translate "the latest article per author" and "the rank of each article within its category by views" into one queryset each.

## 1. `Q` objects — composable boolean logic

`Q` is the wrapper around a single boolean clause. Two `Q`s combine with `&` (AND), `|` (OR), and `~` (NOT). The result is the same kind of object, so it composes indefinitely.

```python
from django.db.models import Q

published = Q(status="published")
featured = Q(is_featured=True)
popular = Q(view_count__gte=1000)

Article.objects.filter(published & (featured | popular))
# WHERE status = 'published' AND (is_featured = true OR view_count >= 1000)
```

Plain kwargs to `.filter()` join with `AND`. The moment you need an `OR` or a `NOT`, you need `Q`. The moment you have a reusable predicate ("an article is public-facing"), define it once:

```python
class ArticleQ:
    public = Q(status="published") & Q(published_at__isnull=False)
    draftable_by_admin = Q(status__in=["draft", "review"])

Article.objects.filter(ArticleQ.public)
```

This pattern moves naturally into a custom manager (Lecture 3), which is where it should live in real code.

### Negation

`~Q(status="published")` becomes `NOT (status = 'published')` in SQL. Watch out: `NOT (a = b)` is **not** the same as `a != b` when nullable columns are involved. `NOT (col = 'x')` returns false when `col` is NULL (because NULL = anything is NULL, and NOT NULL is still NULL). If your filter needs to include NULLs in the negated case, write the `Q` explicitly: `Q(status__isnull=True) | ~Q(status="published")`.

This is a SQL gotcha; Django does not protect you from it.

### `Q` and the lookup operators

Every lookup you can write with kwargs works inside `Q`:

```python
Q(title__icontains="postgres")
Q(published_at__year=2026)
Q(author__username__startswith="alice")
Q(category__slug__in=["python", "django"])
```

The `__` notation traverses relationships exactly as in kwargs. `Q` is a different surface, not a different language.

## 2. `F` expressions — refer to columns inside expressions

`F("column")` is a reference to a column on the same row. It does three things:

### Cross-column comparisons

```python
from django.db.models import F

# Articles whose updated_at is strictly after created_at
Article.objects.filter(updated_at__gt=F("created_at"))

# Articles whose view_count exceeds the author's average
# (not directly expressible — needs a Subquery, covered below)
```

Without `F`, the right-hand side of a filter is treated as a Python literal. With `F`, it becomes "the value of this column on this row".

### Atomic in-database arithmetic

```python
Article.objects.filter(pk=42).update(view_count=F("view_count") + 1)
# UPDATE writer_article SET view_count = view_count + 1 WHERE id = 42;
```

This is race-free at the SQL level: the read and the write happen inside the same statement. By contrast:

```python
a = Article.objects.get(pk=42)
a.view_count += 1   # in Python
a.save()
# RACE: two requests both read 41, both write 42, you lose one count
```

The `F` form is the only correct one for counters. Use it.

### Annotation

```python
Article.objects.annotate(views_plus_one=F("view_count") + 1)
```

Useful when you need an in-DB-computed value for sorting or filtering without round-tripping to Python.

## 3. `Coalesce`, `Greatest`, `Least`, `NullIf` — the small functions

These four close most of the "the ORM cannot express this" complaints from intermediate engineers.

```python
from django.db.models.functions import Coalesce, Greatest, Least, NullIf
from django.db.models import Value, IntegerField

# Treat NULL view_count as 0
Article.objects.annotate(views_or_zero=Coalesce("view_count", Value(0)))

# "Effective published_at" — published_at if set, else created_at
Article.objects.annotate(effective_at=Coalesce("published_at", "created_at"))

# Max of two columns per row
Article.objects.annotate(latest_touch=Greatest("updated_at", "published_at"))

# Treat empty string as NULL
Article.objects.annotate(canonical_title=NullIf("title", Value("")))
```

`Coalesce` is the most common; the rest you reach for once a month and remember exists.

## 4. `Case` / `When` / `Value` — SQL `CASE` inside an annotation

```python
from django.db.models import Case, When, Value, IntegerField, CharField

Article.objects.annotate(
    bucket=Case(
        When(view_count__gte=10_000, then=Value("viral")),
        When(view_count__gte=1_000, then=Value("popular")),
        When(view_count__gte=100, then=Value("decent")),
        default=Value("quiet"),
        output_field=CharField(),
    )
)
```

The emitted SQL:

```sql
CASE
    WHEN view_count >= 10000 THEN 'viral'
    WHEN view_count >= 1000  THEN 'popular'
    WHEN view_count >= 100   THEN 'decent'
    ELSE 'quiet'
END AS bucket
```

`output_field` is required when Django cannot infer the type (because `Value` is type-ambiguous in Python). Pass `IntegerField()`, `CharField()`, `BooleanField()`, etc. — an instance, not the class.

The most common use of `Case`: scoring or ranking custom criteria for `ORDER BY`:

```python
Article.objects.annotate(
    score=Case(
        When(is_featured=True, then=Value(100)),
        When(view_count__gte=1000, then=Value(50)),
        default=Value(0),
        output_field=IntegerField(),
    )
).order_by("-score", "-published_at")
```

A `Subquery` (next section) is more flexible but more verbose; `Case` is the right choice when the conditions are small and known.

## 5. `Subquery` and `OuterRef` — the correlated subquery in Python

The single most powerful feature of the Django ORM. With `Subquery` you can express any query a hand-written SQL author would write as a correlated subquery, without dropping into raw SQL.

### The pattern

```python
from django.db.models import Subquery, OuterRef

# For each author, attach the title of their most recent article
latest = Article.objects.filter(author=OuterRef("pk")) \
    .order_by("-published_at") \
    .values("title")[:1]

qs = Author.objects.annotate(latest_article_title=Subquery(latest))
```

Three rules to internalise:

1. **The inner queryset must be sliced to `[:1]`.** A `Subquery` returns one row, one column. If the inner returns more than one row, Postgres raises `more than one row returned by a subquery used as an expression`.
2. **The inner queryset must end in `.values("col")`** so the ORM knows which single column to project. Without `.values()`, the inner selects every model field, which is not valid for a scalar subquery.
3. **`OuterRef("pk")` refers to the outer row's primary key.** `OuterRef("any_field")` refers to any column of the outer model. The reference is resolved at SQL build time.

The emitted SQL:

```sql
SELECT writer_author.*,
       (SELECT writer_article.title FROM writer_article
        WHERE writer_article.author_id = writer_author.id
        ORDER BY writer_article.published_at DESC LIMIT 1) AS latest_article_title
FROM writer_author;
```

One query. One row per author. The subquery runs once per outer row, but Postgres can plan it efficiently with an index on `(author_id, published_at)`.

### Multiple columns from one correlated query

`Subquery` projects one column. For multiple, run two `Subquery`s sharing the same inner shape — Postgres optimises identical subqueries — or use a `OneToMany`-style join with `LATERAL` (not directly expressible in the Django ORM; drops to raw SQL).

Common workaround: store IDs only, then fetch in bulk:

```python
latest_id = Article.objects.filter(author=OuterRef("pk")) \
    .order_by("-published_at") \
    .values("pk")[:1]

authors = Author.objects.annotate(latest_article_id=Subquery(latest_id))

# Then, in Python:
ids = [a.latest_article_id for a in authors if a.latest_article_id]
latest_articles = {a.pk: a for a in Article.objects.filter(pk__in=ids)}
for a in authors:
    a.latest_article = latest_articles.get(a.latest_article_id)
```

Two queries, no `LATERAL`, fully ORM-expressible. The pattern shows up in roughly half of dashboard views.

### Aggregating in a subquery

For "count of comments per article", which the `annotate(Count("comments"))` multi-join multiplication trap makes painful:

```python
comment_count = Comment.objects.filter(article=OuterRef("pk")) \
    .values("article") \
    .annotate(c=Count("*")) \
    .values("c")

Article.objects.annotate(comment_count=Coalesce(Subquery(comment_count), Value(0)))
```

The `.values("article").annotate(c=Count("*")).values("c")` shape is the canonical "aggregate inside a subquery" pattern. Memorise it. The `Coalesce` is because zero-comment articles return NULL from the subquery; you almost always want 0.

Compared to `Author.objects.annotate(c=Count("articles"))`, this version is correct in the presence of multiple annotations (no multiplication trap) and is the right answer most of the time.

### `OutputField` and the type-inference problem

Subqueries sometimes confuse Django's type inference. If you get `FieldError: Cannot resolve expression type, unknown output_field`, pass `output_field=`:

```python
from django.db.models import IntegerField

Subquery(comment_count, output_field=IntegerField())
```

## 6. `Exists` — existence checks without `count()`

For "does any related row exist?", `Exists` is the right tool:

```python
from django.db.models import Exists, OuterRef

has_comments = Comment.objects.filter(article=OuterRef("pk"))
Article.objects.annotate(has_comments=Exists(has_comments))

# As a filter
Article.objects.filter(Exists(has_comments))

# Negation
Article.objects.filter(~Exists(has_comments))
```

The emitted SQL uses `EXISTS (SELECT 1 FROM ...)` which Postgres can short-circuit on the first matching row. This is dramatically faster than:

```python
Article.objects.annotate(c=Count("comments")).filter(c__gt=0)  # WRONG: counts all rows
```

Use `Exists` whenever you want a boolean, not a count. The difference at scale is "200 ms vs 5 ms".

## 7. Window functions — when `GROUP BY` is the wrong shape

A `GROUP BY` reduces rows. A **window function** computes a value across a partition of rows **without reducing them**. The output has the same row count as the input; each row gets a new column representing its position, rank, sum, or whatever, computed across its window.

The canonical example: "the rank of each article within its category by views".

```python
from django.db.models import Window, F
from django.db.models.functions import Rank

qs = Article.objects.annotate(
    category_rank=Window(
        expression=Rank(),
        partition_by=[F("category_id")],
        order_by=F("view_count").desc(),
    )
)

for a in qs:
    print(a.category, a.title, a.category_rank)
```

The emitted SQL:

```sql
SELECT writer_article.*,
       RANK() OVER (PARTITION BY category_id ORDER BY view_count DESC) AS category_rank
FROM writer_article;
```

Every article appears in the result, each carrying its rank within its category. To filter "top 3 per category", you cannot use `WHERE category_rank <= 3` in the same query — window functions are evaluated after `WHERE` — but you can wrap it in a subquery:

```python
ranked = Article.objects.annotate(
    rank=Window(expression=Rank(), partition_by=[F("category_id")], order_by=F("view_count").desc())
)
# Then in the outer:
top3_ids = [a.pk for a in ranked if a.rank <= 3]
# or use a Subquery FROM the annotated queryset (more complex)
```

For "top 3 per group" in one query, raw SQL with a subquery is the cleaner path. The ORM is willing; the SQL is the same; clarity wins.

### The window function vocabulary

| Function | What it computes |
|----------|------------------|
| `RowNumber` | Sequential number within the partition (no ties) |
| `Rank` | Rank within the partition; ties share a rank; next rank skips |
| `DenseRank` | Like `Rank` but next rank does not skip |
| `Ntile(N)` | Bucket each row into one of `N` buckets |
| `Lag(expr, offset=1)` | The value of `expr` from the previous row in the partition |
| `Lead(expr, offset=1)` | The value from the next row |
| `FirstValue(expr)` | First value in the (ordered) partition |
| `LastValue(expr)` | Last — but watch the frame |
| `Sum`, `Avg`, `Count`, `Min`, `Max` | The aggregate, computed over the window |

All live in `django.db.models.functions` and combine with `Window(expression=..., partition_by=[...], order_by=...)`.

### `partition_by`, `order_by`, `frame`

`Window` takes three optional shape arguments:

- `partition_by=[F("col")]` — the group within which the function operates. Omit for "the whole queryset is one window".
- `order_by=F("col").asc()` (or `.desc()`) — the order within the partition. Required by some functions (`Rank`, `Lag`, `Lead`); optional for most aggregates but usually meaningful.
- `frame=` — the precise slice of the partition the function operates on. For most cases, omit; the SQL default ("`RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`") is what you want.

For a running total of views per author by published date:

```python
from django.db.models import Sum
from django.db.models.functions import Lag

Article.objects.annotate(
    running_views=Window(
        expression=Sum("view_count"),
        partition_by=[F("author_id")],
        order_by=F("published_at").asc(),
    )
)
```

Each article carries the cumulative views the author had earned up to and including that article. This kind of analytic query is what window functions exist for.

### `Lag` and `Lead` for delta calculations

"How much did this article's view count change vs the author's previous article?"

```python
Article.objects.annotate(
    prev_views=Window(
        expression=Lag("view_count"),
        partition_by=[F("author_id")],
        order_by=F("published_at").asc(),
    )
).annotate(
    delta=F("view_count") - Coalesce(F("prev_views"), Value(0)),
)
```

You can chain `annotate` calls; the second one can refer to the first. Useful for any "row N+1 minus row N" computation that would be a pain in straight Python.

### When the ORM cannot help — `RawSQL` for window functions

The ORM's window-function support covers most common cases. If you hit one it does not, `RawSQL` lets you drop in a literal expression:

```python
from django.db.models.expressions import RawSQL

Article.objects.annotate(
    custom_rank=RawSQL(
        "RANK() OVER (PARTITION BY category_id ORDER BY view_count DESC, published_at DESC)",
        [],
    )
)
```

This is the bridge from ORM to raw SQL when you need exactly one piece of SQL the ORM does not support — without giving up the rest of the queryset. Use it when you have to; prefer the pure-ORM expression when possible. We come back to `RawSQL` and the other escape hatches in Lecture 3.

## 8. Putting it together — three real questions

### Q1: top 5 authors by total views

```python
top_authors = Author.objects.annotate(
    total_views=Coalesce(
        Subquery(
            Article.objects.filter(author=OuterRef("pk"), status="published")
                .values("author").annotate(s=Sum("view_count")).values("s"),
            output_field=IntegerField(),
        ),
        Value(0),
    )
).order_by("-total_views")[:5]
```

One query. No N+1. No multiplication trap. The `Subquery` aggregates per author; `Coalesce` handles authors with zero published articles.

### Q2: each article's rank within its category by views

```python
ranked = Article.objects.filter(status="published").annotate(
    cat_rank=Window(
        expression=Rank(),
        partition_by=[F("category_id")],
        order_by=F("view_count").desc(),
    )
)
```

One query. Every article in the result has its rank attached.

### Q3: authors who have **never** published an article in 2026

```python
published_2026 = Article.objects.filter(
    author=OuterRef("pk"),
    status="published",
    published_at__year=2026,
)
quiet_authors = Author.objects.filter(~Exists(published_2026))
```

One query, with a `NOT EXISTS (...)` clause. Much faster than `Author.objects.exclude(articles__published_at__year=2026)` because the latter does a `LEFT OUTER JOIN` and a `WHERE NULL`, which the planner sometimes mishandles.

## 9. The mental model

A way to think about today's tools:

| You want… | Reach for |
|-----------|-----------|
| One column per row, computed from joined rows | `annotate(Count/Sum/...)` |
| One column per row, computed from a separate query | `Subquery` + `OuterRef` |
| A boolean per row from existence | `Exists` |
| A value across a window of related rows, *keeping all rows* | `Window` |
| Boolean composition | `Q` |
| In-row arithmetic, race-free updates | `F` |
| `IF/THEN/ELSE` per row | `Case` / `When` |
| NULL handling | `Coalesce`, `NullIf`, `Greatest`, `Least` |

Cross-reference this table to whichever problem you are solving. If two rows of the table look like they apply, the answer is probably both — `annotate(Subquery(...))` is the most common composition.

## 10. What comes next

Tomorrow: custom managers and querysets, the four raw-SQL escape hatches (`RawSQL`, `Model.objects.raw()`, `connection.cursor()`, `update()` with raw expressions), and the difference between `update()`, `save()`, `bulk_update()`, and `bulk_create()`. By Wednesday evening you should have the vocabulary to look at any business-logic-laden filter chain in your codebase and refactor it into a single named method on a manager.

Before Lecture 3, work through Exercise 2 (subquery with `OuterRef`) and Exercise 3 (window functions). The dashboard mini-project relies on both.
