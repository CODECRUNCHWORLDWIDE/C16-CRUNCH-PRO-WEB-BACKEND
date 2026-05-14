# Lecture 1 — `select_related`, `prefetch_related`, `annotate`, `aggregate`

> **Duration:** ~2 hours. **Outcome:** You can read a Django queryset and predict the SQL it will emit. You know when to reach for `select_related` vs `prefetch_related` vs `Prefetch`, and you can distinguish `annotate` from `aggregate` by reflex — including the multiplication trap that bites everyone exactly once.

The four methods in this lecture's title cover roughly 80% of the ORM you will write in your career. The other 20% — subqueries, windows, raw escape hatches — is Lecture 2 and 3. Master these four and the rest reads as elaboration.

## 1. The queryset is lazy — and you should be able to prove it

A `QuerySet` is not a database query. It is a description of one. The SQL fires when the queryset is **evaluated**, which happens on:

- iteration (`for a in qs:`)
- slicing with a step (`qs[::2]`) — though plain `qs[5:10]` is still lazy and becomes `LIMIT ... OFFSET ...`
- `bool(qs)` (e.g. `if qs:`)
- `len(qs)` — and yes, this is different from `qs.count()`
- `list(qs)`, `repr(qs)` (in `print()`)
- pickling, JSON serialisation

Until then, you can chain `.filter()`, `.exclude()`, `.order_by()`, `.annotate()`, `.select_related()` indefinitely without touching the database. The chain becomes one SQL statement when you finally evaluate.

Prove it:

```python
from django.db import connection, reset_queries
from writer.models import Article

reset_queries()
qs = Article.objects.filter(status="published").order_by("-published_at")
print(len(connection.queries))  # 0 — no SQL yet

list(qs[:5])
print(connection.queries[-1]["sql"])
# SELECT ... FROM "writer_article" WHERE "writer_article"."status" = 'published'
# ORDER BY "writer_article"."published_at" DESC LIMIT 5
```

The chain `Article.objects.filter(...).order_by(...)` was free; the cost was `list(qs[:5])`.

### Inspect a queryset's SQL without running it

```python
qs = Article.objects.filter(status="published")
print(str(qs.query))
# SELECT "writer_article"."id", ... FROM "writer_article"
# WHERE "writer_article"."status" = 'published'
```

`str(queryset.query)` is your first debugging tool. Use it constantly. The output is missing the parameter binding (you see `'published'` rather than `%s`), which is good for human reading and slightly bad if the value contains a quote — for the exact SQL Postgres will see, use `connection.queries[-1]["sql"]` after evaluation.

### The two-query rule for any view

For any view that renders a list of objects with related data, the query count should be:

- **One** for the list itself (or two if pagination needs a `COUNT`).
- **One per "to-many" relationship** you traverse in the template.
- **Zero** for any forward `FK` / `O2O` you traverse — `select_related` folds these into the first query.

If the count is higher, you have an N+1. The N+1 is the canonical ORM bug. By the end of this week you should detect one within ten seconds of opening a view.

## 2. `select_related` — the JOIN-based prefetch

`select_related` performs an SQL `JOIN` and pulls the related row into the same query. It works for forward `ForeignKey` and `OneToOneField`. It does **not** work for reverse relationships (the `_set` accessor) or `ManyToManyField`.

### The N+1 it fixes

Without `select_related`:

```python
for a in Article.objects.filter(status="published")[:10]:
    print(a.author.username)
# 1 query for the articles
# + 10 queries, one per article, to fetch the author
# = 11 queries
```

With `select_related`:

```python
qs = Article.objects.select_related("author").filter(status="published")[:10]
for a in qs:
    print(a.author.username)
# 1 query, with a JOIN to writer_author
```

The emitted SQL:

```sql
SELECT writer_article.id, writer_article.title, writer_article.author_id,
       writer_author.id, writer_author.username, writer_author.email
FROM writer_article
INNER JOIN writer_author ON writer_article.author_id = writer_author.id
WHERE writer_article.status = 'published'
LIMIT 10;
```

Django selects every column from both tables. There is no `SELECT id, username` — the ORM does not know which fields the template will touch, so it grabs all of them. This is fine for narrow tables and a real cost for wide ones; the fix is `.only("title", "author__username")` (covered in section 6).

### Chaining `select_related`

You can chase multiple FKs, including transitively:

```python
Article.objects.select_related("author", "category")
# JOIN both
Comment.objects.select_related("article__author")
# JOIN article, then JOIN article's author — two JOINs in one query
```

The `__` is the relationship traversal operator, the same one you already use in `filter(author__username="...")`. You can chase as deep as the schema allows, but each level adds a `JOIN`; past three levels, reconsider the query.

### When `select_related` is the **wrong** answer

- The relationship is reverse — `author.articles.all()` is a `_set` accessor; `select_related` cannot fold a one-to-many "outward" without producing duplicate rows for the parent.
- The relationship is `ManyToManyField` — same problem; would multiply rows.
- The related row is enormous and you only need its `id` — a `JOIN` brings every column; if you only want the FK value, you already have it on `article.author_id` without any query.

### Without an argument

`select_related()` with no arguments follows **every** forward `FK` / `O2O` on the model. Tempting; rarely correct. The exact set of `JOIN`s changes when someone adds a `FK`, and you stop being able to predict the SQL. Always pass the names.

## 3. `prefetch_related` — the second-query prefetch

`prefetch_related` handles reverse `FK`, `M2M`, and generic relations. It issues a **separate** query (not a join), then matches the rows in Python. Two queries total, not 1 + N.

```python
qs = Author.objects.prefetch_related("articles")[:10]
for a in qs:
    print(a.username, [art.title for art in a.articles.all()])
# Query 1: SELECT ... FROM writer_author LIMIT 10
# Query 2: SELECT ... FROM writer_article WHERE author_id IN (1, 2, ..., 10)
```

The second query is an `IN (...)` with the FK column matching the IDs from query 1. Django then constructs a Python dict keyed by `author_id` and attaches the right list to each author in memory.

### Why two queries instead of a `LEFT JOIN`

Imagine `Author.objects.select_related("articles")` — that is reverse — and consider 10 authors with 100 articles each. A `LEFT JOIN` would produce **1 000 rows** containing the same author columns 100 times. The savings of one round-trip are dwarfed by 9× the bytes on the wire and 9× the deserialisation work. The two-query shape is correct here.

### `Prefetch()` — shape the inner query

The basic form prefetches all related rows. The `Prefetch` class lets you constrain or sort the inner queryset:

```python
from django.db.models import Prefetch

recent_articles = Prefetch(
    "articles",
    queryset=Article.objects.filter(status="published").order_by("-published_at")[:5],
    to_attr="recent_articles",
)
qs = Author.objects.prefetch_related(recent_articles)

for a in qs:
    for art in a.recent_articles:   # NOT a.articles.all()
        print(art.title)
```

Two important details:

- `queryset=` lets you filter, order, annotate, or `select_related` the inner queryset. Any queryset method is fair game.
- `to_attr="recent_articles"` puts the prefetched list on a new attribute instead of overwriting `a.articles.all()`. Use `to_attr` whenever the prefetch is filtered — otherwise downstream code calling `a.articles.all()` (which would re-query) will silently bypass your filter.

### Common mistakes

- Calling `a.articles.all()` after `prefetch_related("articles")` is correct — Django intercepts the call. Calling `a.articles.filter(...)` is **not** — it bypasses the prefetch and re-queries. If you need a filter, define it in `Prefetch(queryset=...)`.
- Mixing `prefetch_related("author")` (a forward FK) with `select_related` on the same query — `prefetch_related` will work, but issues an extra query for no reason. Use `select_related("author")` for forward.
- Forgetting that `prefetch_related` is Python-side — if your relationship has 10 000 children per parent, you pull 10 000 rows into Python regardless of what you display.

### Chaining `prefetch_related` and `select_related` inside `Prefetch`

The full pattern, common in real code:

```python
qs = Article.objects.filter(status="published") \
    .select_related("author", "category") \
    .prefetch_related(
        Prefetch(
            "comments",
            queryset=Comment.objects.select_related("author").order_by("-created_at"),
        ),
        "tags",
    )
```

Result: one query for articles (with JOINs to author + category), one for comments (with a JOIN to comment authors), one for tags. Three queries, regardless of how many articles you render. If you remove the `select_related("author")` inside the `Prefetch`, you re-introduce an N+1 inside the comments list.

## 4. `annotate` — add a column per row

`annotate()` adds a computed column to every row of the queryset. The shape of the queryset does not change; each row gains one more attribute.

```python
from django.db.models import Count

qs = Author.objects.annotate(article_count=Count("articles"))
for a in qs:
    print(a.username, a.article_count)
```

The emitted SQL:

```sql
SELECT writer_author.id, writer_author.username, ...,
       COUNT(writer_article.id) AS article_count
FROM writer_author
LEFT OUTER JOIN writer_article ON writer_author.id = writer_article.author_id
GROUP BY writer_author.id, writer_author.username, ...;
```

Two things to notice:

- A `LEFT OUTER JOIN` — authors with zero articles still appear, with `article_count = 0`.
- A `GROUP BY` on every selected column from the outer table. Django adds this automatically because the aggregate is paired with non-aggregated columns.

### `filter` before vs after `annotate`

The order matters and changes the meaning:

```python
# Authors who have published anything — count is total per author (including drafts)
Author.objects.filter(articles__status="published") \
    .annotate(article_count=Count("articles"))

# Authors with a count of published articles — count only counts published
Author.objects.annotate(
    article_count=Count("articles", filter=Q(articles__status="published"))
)
```

The first applies the `WHERE` and *then* counts; the second uses Django's `Count(..., filter=...)` to push the predicate into the aggregate itself (`COUNT(...) FILTER (WHERE ...)` in SQL). The second is almost always what you actually wanted.

### `Count(..., distinct=True)` — the multiplication trap

When you annotate two related sets in one query:

```python
Author.objects.annotate(
    article_count=Count("articles"),
    comment_count=Count("comments"),
)
```

This is **wrong**. Each author has N articles and M comments; the join produces N×M rows, and each `COUNT` over-counts by the cardinality of the other side. The fix:

```python
Author.objects.annotate(
    article_count=Count("articles", distinct=True),
    comment_count=Count("comments", distinct=True),
)
```

`distinct=True` produces `COUNT(DISTINCT ...)`. It is correct, and slower. The better fix is often a `Subquery` (Lecture 2) that avoids the multi-join entirely:

```python
article_count_sq = Article.objects.filter(author=OuterRef("pk")) \
    .values("author").annotate(c=Count("*")).values("c")
Author.objects.annotate(article_count=Subquery(article_count_sq))
```

The `Subquery` version is one query and stays correct regardless of how many other annotations you add. We will come back to this Tuesday.

### Other aggregate functions

| Function | What it does |
|----------|--------------|
| `Count` | Count rows; supports `distinct=True` and `filter=Q(...)` |
| `Sum` | Sum a numeric column |
| `Avg` | Mean of a numeric column |
| `Min`, `Max` | Min / max; works on dates and strings too |
| `StringAgg` (Postgres) | Concatenate strings with a delimiter; `from django.contrib.postgres.aggregates import StringAgg` |
| `ArrayAgg` (Postgres) | Aggregate into a Postgres array |

`StringAgg` is the right tool for "tags for this article as a comma-separated string"; `ArrayAgg` for "list of tag IDs as a Python list". Both are Postgres-only and live in `django.contrib.postgres.aggregates`.

### Annotating with non-aggregate expressions

`annotate()` is not restricted to aggregates. Any expression works:

```python
from django.db.models import F, Value, CharField
from django.db.models.functions import Concat, Coalesce, Lower

Article.objects.annotate(
    slug_lower=Lower("slug"),
    title_with_author=Concat("title", Value(" — "), "author__username", output_field=CharField()),
    pretty_status=Coalesce("status", Value("draft")),
)
```

`F("views") + 1` annotates a column with one more than its current value. `Value(...)` wraps a literal. `Coalesce` is the SQL `COALESCE(a, b, c)` — first non-NULL.

## 5. `aggregate` — collapse to a single row

`aggregate()` reduces the entire queryset to **one dict**. It is `annotate()` without the per-row part.

```python
from django.db.models import Avg, Count, Max

stats = Article.objects.filter(status="published").aggregate(
    total=Count("*"),
    avg_views=Avg("view_count"),
    most_recent=Max("published_at"),
)
# {"total": 8421, "avg_views": 312.7, "most_recent": datetime(...)}
```

The emitted SQL is one statement, no `GROUP BY`:

```sql
SELECT COUNT(*) AS total, AVG(view_count) AS avg_views, MAX(published_at) AS most_recent
FROM writer_article WHERE status = 'published';
```

If you ever find yourself writing:

```python
total = qs.count()
avg = qs.aggregate(Avg("view_count"))["view_count__avg"]
latest = qs.aggregate(Max("published_at"))["published_at__max"]
```

That is **three queries**. One `aggregate()` call with all three keys is one query. Always batch.

### `aggregate` vs `annotate`: the rule

- `aggregate(...)` returns a **dict**. The queryset is gone.
- `annotate(...)` returns a **queryset**. Each row gains a column.

If you find yourself doing `qs.annotate(...).aggregate(...)` — fine, common, correct: annotate per row first, then collapse.

## 6. `only` and `defer` — the column selector

By default, every queryset selects every column of the model. For wide tables (`body text NOT NULL` carries the whole article), this is wasteful.

```python
Article.objects.only("id", "title", "slug", "published_at")
# SELECT id, title, slug, published_at FROM writer_article;
# accessing article.body issues a SECOND query for that column

Article.objects.defer("body")
# SELECT every column EXCEPT body;
```

`only` and `defer` are useful when the table is wide and one column is large (think: `tsvector`, `jsonb` blobs, full article text). For ordinary models, the savings are negligible — do not micro-optimise.

The trap: accessing a deferred field issues a query for that single column. In a loop, you re-introduce the N+1. Use `only` / `defer` only when you can guarantee the deferred fields are not accessed in the template.

## 7. Putting it all together — a realistic listing view

The list view of `crunchwriter` displays the latest 20 published articles, each with author, category, and the count of comments. The right shape:

```python
from django.db.models import Count, Q, Prefetch

def article_list(request):
    qs = Article.objects.filter(status="published") \
        .select_related("author", "category") \
        .annotate(
            comment_count=Count(
                "comments",
                filter=Q(comments__is_approved=True),
                distinct=True,
            )
        ) \
        .order_by("-published_at")[:20]
    return render(request, "writer/article_list.html", {"articles": qs})
```

The SQL:

```sql
SELECT writer_article.*, writer_author.*, writer_category.*,
       COUNT(DISTINCT writer_comment.id) FILTER (WHERE writer_comment.is_approved) AS comment_count
FROM writer_article
INNER JOIN writer_author ON ...
LEFT OUTER JOIN writer_category ON ...
LEFT OUTER JOIN writer_comment ON ...
WHERE writer_article.status = 'published'
GROUP BY writer_article.id, writer_author.id, writer_category.id
ORDER BY writer_article.published_at DESC
LIMIT 20;
```

One query. With pagination, two — one count, one page. Open `django-debug-toolbar` and confirm. If the toolbar shows three, four, or twenty queries for this view, something is wrong with the template (typically a `{% for comment in article.comments.all %}` that did not match the prefetch).

## 8. The habit — `assertNumQueries` on every view

The most useful test you can write this week:

```python
from django.test import TestCase
from django.urls import reverse

class ArticleListPerfTests(TestCase):
    fixtures = ["seed_small.json"]

    def test_list_view_query_count(self):
        with self.assertNumQueries(2):  # 1 count + 1 page
            response = self.client.get(reverse("writer:article_list"))
        self.assertEqual(response.status_code, 200)
```

This test is **boring** and **invaluable**. The day someone adds `{{ article.author.profile.bio }}` to the template, this test fails with "expected 2, got 22". You catch the N+1 in code review instead of in production.

## 9. Recap and what comes next

Today's four tools, in one sentence each:

- `select_related` — fold forward FKs into the parent query with a JOIN.
- `prefetch_related` — fetch reverse FKs / M2Ms with a second `IN (...)` query.
- `annotate` — add a computed column per row; pair with `Count`, `Sum`, `F`, `Coalesce`, `Case`/`When`.
- `aggregate` — collapse the whole queryset to one dict of stats.

Tomorrow we go deeper: subqueries with `OuterRef`, existence checks with `Exists`, and window functions when `GROUP BY` is the wrong shape. The dashboard mini-project on Thursday uses all of these in one view.

Before next lecture, work through Exercise 1. It walks you through five annotations against your `crunchwriter` schema, with the emitted SQL inspected at each step. By the end you should be able to predict the SQL Django emits before evaluating the queryset — and verify the prediction in `psql`.
