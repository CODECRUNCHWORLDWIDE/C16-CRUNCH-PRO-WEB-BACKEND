# Lecture 3 — Custom Managers, Custom QuerySets, and Raw SQL Escape Hatches

> **Duration:** ~2 hours. **Outcome:** You can move business logic out of views and into the model layer with a custom manager + queryset. You know the four ways to escape to raw SQL and which one to reach for. You know what `update()`, `save()`, `bulk_update()`, and `bulk_create()` each cost.

The previous two lectures gave you the expressive tools. This lecture gives you the architectural ones — where the queries live in your codebase, what they are named, and how to keep them clean as the project grows. Plus the four trapdoors out of the ORM when it actually is the wrong tool.

## 1. The manager — what `Model.objects` actually is

`MyModel.objects` is an instance of a `Manager` class. Django installs a default one (`django.db.models.Manager`) on every model unless you override it. The default manager's job is to expose querysets: `MyModel.objects.all()`, `MyModel.objects.filter(...)`, etc.

The methods you call on `MyModel.objects` (`filter`, `exclude`, `annotate`) actually live on the `QuerySet` class. The manager is a thin façade over `QuerySet`. When you call `MyModel.objects.filter(...)`, the manager constructs a fresh `QuerySet`, calls `.filter(...)` on it, and returns the result.

This matters for one reason: when you write a custom manager, you almost never want to subclass `Manager` directly. You want to subclass `QuerySet`, then attach it to the manager.

## 2. The right pattern — custom `QuerySet`, `Manager.from_queryset()`

The pattern that scales:

```python
# writer/models.py
from django.db import models
from django.db.models import Q, Count, F, Sum, Value
from django.db.models.functions import Coalesce


class ArticleQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status="published", published_at__isnull=False)

    def drafts(self):
        return self.filter(status="draft")

    def for_author(self, author):
        return self.filter(author=author)

    def in_category(self, slug):
        return self.filter(category__slug=slug)

    def with_comment_count(self):
        return self.annotate(comment_count=Count("comments", distinct=True))

    def popular(self, threshold=1000):
        return self.filter(view_count__gte=threshold)


class Article(models.Model):
    # ... fields ...
    objects = ArticleQuerySet.as_manager()
```

`QuerySet.as_manager()` is the one-line equivalent of `Manager.from_queryset(ArticleQuerySet)()`. It produces a manager whose methods are exactly the methods of the queryset. Now in views:

```python
qs = Article.objects.published().in_category("python").with_comment_count().popular()
```

Every method is chainable because each returns a queryset. The chain is readable to anyone who knows the domain — *publish status*, *category*, *count*, *popularity threshold* — and the SQL is built lazily, evaluated once.

### Why this is better than helper functions

The naive alternative is module-level helpers:

```python
def published_articles():
    return Article.objects.filter(status="published")

def popular_articles(threshold=1000):
    return Article.objects.filter(view_count__gte=threshold)
```

This works for one or two predicates and falls apart at five. Helpers do not chain — `popular_articles().in_category(...)` is not a method on a queryset. You end up with `popular_articles().filter(category__slug=...)`, scattering filter logic back across views.

The queryset method version keeps every predicate composable and discoverable on the same object. Tab completion shows the available methods. New engineers find them.

### What goes on the queryset and what goes on the manager

A working rule:

- **Chainable predicates and annotations** go on the **queryset** — `.published()`, `.with_comment_count()`, `.popular()`. They take a queryset, return a queryset.
- **Operations on the whole model** (factory methods, bulk operations, raw-SQL operations that do not start from a chain) can go on the **manager** with a separate `Manager` subclass — `Article.objects.create_from_markdown_file(path)` is a manager method.

For the latter, the pattern is:

```python
class ArticleManager(models.Manager):
    def get_queryset(self):
        return ArticleQuerySet(self.model, using=self._db)

    # delegate chainable methods so Article.objects.published() works
    def published(self):
        return self.get_queryset().published()

    def create_from_markdown_file(self, path):
        # ... non-chainable manager-level operation
        ...

class Article(models.Model):
    objects = ArticleManager()
```

The `from_queryset` shortcut delegates every queryset method automatically:

```python
class ArticleManager(ArticleQuerySet.as_manager().__class__):
    def create_from_markdown_file(self, path):
        ...
```

In practice most projects use plain `ArticleQuerySet.as_manager()` and put factory methods elsewhere (a `services.py` module). Pick one convention and stick to it.

## 3. Multiple managers

A model can have more than one manager. Most projects do not need this; when they do, it is usually to hide soft-deleted rows:

```python
class ArticleQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

class Article(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True)
    objects = ArticleQuerySet.as_manager()          # the default
    alive_objects = ArticleQuerySet.alive.as_manager()  # convenience
```

The first manager Django sees is the **default**, and `MyModel._default_manager` is used by relationships and reverse FK accessors. If you replace the default manager and it filters out rows, you break `author.articles.all()` for the filtered rows — those will never appear. This is sometimes what you want and often a footgun. Be deliberate.

The conventional pattern is: keep the default manager unrestricted, add a second manager (e.g. `Article.live`) that filters. Never the other way around.

## 4. `update()` vs `save()` vs `bulk_update()` vs `bulk_create()`

Four ways to write to the database. They are not interchangeable.

### `instance.save()`

Per-instance. Issues an `UPDATE` (or an `INSERT` for new instances). Fires `pre_save` / `post_save` signals. Runs model-level validators if you pass `validate=True` (Django 5.2+), otherwise not. Returns nothing meaningful.

```python
a = Article.objects.get(pk=42)
a.title = "New title"
a.save()
# UPDATE writer_article SET title=..., (every column) WHERE id = 42
```

By default, `save()` writes **every column** on the model. Use `save(update_fields=["title"])` to write only the column(s) you changed — much smaller transaction log, signals still fire.

### `queryset.update(**kwargs)`

One `UPDATE` statement, affects every row in the queryset. **Does not** call `save()`. **Does not** fire signals. Bypasses `auto_now=True` (because that lives in `save()`). Returns the number of affected rows.

```python
Article.objects.filter(status="draft", created_at__lt=cutoff).update(status="archived")
# UPDATE writer_article SET status='archived' WHERE status='draft' AND created_at < ...
# Returns: integer (rows affected)
```

`update()` is the right tool for "change a column on many rows at once". It is dramatically faster than iterating and calling `.save()` on each. The trade-off — no signals — is almost always fine; signals on bulk updates are usually a bug anyway.

### `Model.objects.bulk_update(instances, fields)`

Update many in-memory instances in one statement. Same caveats as `update()` (no signals, no `auto_now`). Use this when you have already mutated Python instances and want to flush them:

```python
articles = list(Article.objects.filter(status="draft")[:1000])
for a in articles:
    a.title = a.title.strip()
Article.objects.bulk_update(articles, ["title"], batch_size=200)
```

Django emits one `UPDATE` per batch using a `CASE` expression to vary the value per row:

```sql
UPDATE writer_article SET title = CASE id
    WHEN 1 THEN '...'
    WHEN 2 THEN '...'
    ...
END WHERE id IN (1, 2, ...);
```

This is fast for hundreds, decent for thousands; for millions, write a raw `UPDATE FROM` with a `VALUES` table.

### `Model.objects.bulk_create(instances)`

One `INSERT` for many instances. The most useful write operation in the entire ORM. Postgres supports `ON CONFLICT` for upserts (`bulk_create(..., update_conflicts=True, ...)`).

```python
to_insert = [Article(title=t, author=author) for t in titles]
Article.objects.bulk_create(to_insert, batch_size=500)
```

Caveats:

- No `pre_save` / `post_save` signals (sometimes wanted, sometimes a problem — for example, full-text search vectors populated in a signal will not be set).
- Does not set the PK back on the in-memory instances **unless** the backend supports `RETURNING` (Postgres does; SQLite did not until 3.35; Django supports it for Postgres since 4.0). So `instance.id` is populated post-call on Postgres.
- For `update_conflicts=True`, you must pass `unique_fields=[...]` and `update_fields=[...]`. Read the docs once.

### Which to reach for

| Situation | Use |
|-----------|-----|
| One row, business logic, signals matter | `instance.save()` |
| Many rows, same change | `queryset.update()` |
| Many rows, different values, you have the instances | `bulk_update()` |
| Many new rows | `bulk_create()` |
| Many new rows with deduplication | `bulk_create(update_conflicts=True)` |

The performance gap between `for a in qs: a.save()` and `qs.update(...)` is roughly 100× for 10 000 rows. Use the bulk forms when the situation allows.

## 5. `get_or_create` and `update_or_create`

Two convenience methods, both with subtle race conditions you should know:

```python
# Get the article if it exists, else create
article, created = Article.objects.get_or_create(
    slug="intro-to-django",
    defaults={"title": "Intro to Django", "author": author, "body": "..."},
)
```

The `defaults={...}` are only used on create. Without them, every kwarg would also be passed to `__init__`, which for `body=` would set the body to an empty string on lookup-only calls. **Always use `defaults`** for fields you only want set on creation.

The race: between the `SELECT` and the `INSERT`, another transaction can insert the same row. Django works around this by catching `IntegrityError` and retrying the `SELECT`. The pattern is correct **if** the lookup fields are uniquely constrained at the database level (`unique=True`, `UniqueConstraint`, or a `unique_together`). Without the constraint, you can get duplicate rows. The constraint is doing the actual work; the method is convenience.

`update_or_create` is the same shape but updates the existing row's `defaults` if found. Same race conditions; same need for a uniqueness constraint.

## 6. `select_for_update` — the ORM locking primitive

Inside a transaction, `select_for_update()` issues `SELECT ... FOR UPDATE`, locking the rows until the transaction ends.

```python
from django.db import transaction

with transaction.atomic():
    article = Article.objects.select_for_update().get(pk=pk)
    # No other transaction can modify this row until we COMMIT or ROLLBACK.
    article.view_count += 1
    article.save()
```

Useful when the logic between the read and the write is not expressible as a single `UPDATE`. For "increment by one", prefer `Article.objects.filter(pk=pk).update(view_count=F("view_count") + 1)` — atomic at the SQL level without an explicit lock.

`select_for_update(skip_locked=True)` skips rows another transaction has locked. Useful for queue-style workloads ("give me the next job nobody else has claimed"). `select_for_update(nowait=True)` raises immediately if any matched row is locked.

`select_for_update` only works inside `transaction.atomic()` — Django raises if you call it without an open transaction.

## 7. The four escape hatches

When the ORM cannot express what you need, you have four exits. They are listed in increasing order of "you are now on your own".

### 7.1 `RawSQL` — inject SQL into a queryset expression

For when one piece of an otherwise ORM-shaped query needs raw SQL:

```python
from django.db.models.expressions import RawSQL

Article.objects.annotate(
    word_count=RawSQL("array_length(string_to_array(body, ' '), 1)", []),
).filter(word_count__gt=2000)
```

The first argument is the SQL fragment; the second is a list of parameters bound with `%s`. Use parameters; never interpolate strings. The fragment is inserted as an expression, so it must produce one column.

Use `RawSQL` for: window-function shapes the ORM does not support, Postgres-specific functions without an ORM wrapper, vendor-specific operators.

### 7.2 `Model.objects.raw(sql, params)` — raw `SELECT` returning model instances

```python
articles = Article.objects.raw(
    "SELECT * FROM writer_article WHERE search_vector @@ websearch_to_tsquery('english', %s) LIMIT 20",
    [search_query],
)
for a in articles:
    print(a.title)
```

The result is a `RawQuerySet`. Each row becomes a model instance. The `SELECT` must return at least the primary key, but you can return any columns; extras are attached as instance attributes.

Limitations:

- `RawQuerySet` is not a `QuerySet`. You cannot chain `.filter()`, `.order_by()`, `.annotate()` on it.
- Counts and slicing work differently — you cannot do `articles[10:20]`; you have to put `LIMIT/OFFSET` in the SQL.

Use `raw()` when the SQL is the right shape and you still want model instances. Skip it when you want a plain dict result — use `connection.cursor()` instead.

### 7.3 `connection.cursor()` — DB-API 2.0 access

```python
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute(
        "SELECT category_id, count(*) FROM writer_article "
        "WHERE status = %s GROUP BY category_id ORDER BY count(*) DESC LIMIT 5",
        ["published"],
    )
    rows = cursor.fetchall()
    # [(3, 421), (1, 312), ...]
```

The cursor is `psycopg`'s. You get tuples, not instances. Pass parameters as a list (or dict for named); never string-interpolate.

Use `connection.cursor()` for: pure analytical queries that do not need to be model instances, multi-statement transactions, `WITH` (CTE) queries that are easier in raw SQL, calls to Postgres-specific functions whose output is not a model.

### 7.4 `psycopg` directly

If you bypass Django entirely:

```python
import psycopg
with psycopg.connect("dbname=crunchwriter") as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM writer_article")
        print(cur.fetchone())
```

Avoid this inside a Django request — you give up connection pooling, transaction integration, and signals. Reserve for management commands and scripts where you do not want to load the Django ORM at all.

### Which escape hatch to reach for

| Need | Use |
|------|-----|
| One ORM-illegal expression inside a queryset | `RawSQL` |
| A whole `SELECT` that should return model instances | `Model.objects.raw()` |
| A `SELECT` that returns dicts/tuples, not models | `connection.cursor()` |
| You are writing a script, not a view | `psycopg` directly |

## 8. `extra()` — legacy, do not use

`QuerySet.extra(select=..., where=..., tables=...)` is the predecessor to `RawSQL`, `RawQuerySet`, and the modern expression API. Django's docs deprecate it. It still works; do not write new code with it. If you inherit a codebase using `extra`, port to `annotate(RawSQL(...))` when you touch it.

## 9. Profiling — `connection.queries`, `assertNumQueries`, the toolbar

Three tools you should use in this order: the toolbar in development, `assertNumQueries` in tests, `connection.queries` for one-off shell debugging.

### `connection.queries`

In `DEBUG = True`, every query is recorded:

```python
from django.db import connection, reset_queries

reset_queries()
list(Article.objects.published()[:10])
for q in connection.queries:
    print(q["time"], q["sql"][:120])
```

Each entry has `sql` and `time` (in seconds, as a string). Useful inside `python manage.py shell` when you want to see what one queryset emits.

`connection.queries` is **off** in `DEBUG = False`, and grows without bound in `DEBUG = True` — call `reset_queries()` between checks.

### `assertNumQueries`

In tests:

```python
from django.test import TestCase

class DashboardTests(TestCase):
    def test_dashboard_one_query_per_panel(self):
        with self.assertNumQueries(4):  # 4 panels, 1 query each
            response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
```

The test fails with a helpful diff if the count is off, listing the queries that ran. This is the test you should add to every view this week.

`assertNumQueries` is brittle by design — adding one query in a refactor breaks the test, and you re-examine whether the new query is justified. That is the right behaviour, not a flaw.

### `django-debug-toolbar`

Install, add to `INSTALLED_APPS`, configure the internal IPs, hit any page. The toolbar appears on the right. Click **SQL** to see every query the view emitted, sorted by time, with **duplicates** flagged. The single most useful tool for spotting N+1s without writing a test.

Install once on every project. The five seconds of setup pays back the first time it catches a 200-query view.

## 10. A worked refactor

Before:

```python
def author_dashboard(request):
    author = request.user
    articles = Article.objects.filter(author=author, status="published")

    stats = {
        "count": articles.count(),
        "total_views": sum(a.view_count for a in articles),  # N+1-shaped
        "avg_views": (
            sum(a.view_count for a in articles) / articles.count()
            if articles.count() else 0
        ),
        "latest": articles.order_by("-published_at").first(),
    }
    return render(request, "writer/dashboard.html", {"stats": stats})
```

Problems:

- `articles.count()` runs three times — three round-trips.
- `sum(a.view_count for a in articles)` iterates the queryset, fetching every column of every row, to add up one integer column.
- `articles.order_by(...).first()` re-issues the query.
- Business logic ("an author's dashboard stats") lives in the view.

After:

```python
# writer/models.py
class ArticleQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status="published")

    def for_author(self, author):
        return self.filter(author=author)

    def dashboard_stats(self):
        return self.aggregate(
            count=Count("*"),
            total_views=Coalesce(Sum("view_count"), Value(0)),
            avg_views=Coalesce(Avg("view_count"), Value(0.0)),
            latest_at=Max("published_at"),
        )


# writer/views.py
def author_dashboard(request):
    stats = Article.objects.for_author(request.user).published().dashboard_stats()
    return render(request, "writer/dashboard.html", {"stats": stats})
```

One query for the stats. The view is three lines. The business logic — "what an author's dashboard shows" — lives on the model, where the next person to touch the dashboard finds it on the first try.

This is the shape every view in the mini-project should land in.

## 11. Recap

- **Custom querysets** are the right home for chainable predicates and annotations.
- **`Manager.from_queryset()`** (or `.as_manager()`) is the one-liner that wires queryset methods onto the manager.
- **`update()` vs `save()` vs `bulk_update()` vs `bulk_create()`** — pick by row count and whether signals matter.
- **The four escape hatches** — `RawSQL`, `raw()`, `cursor()`, `psycopg` — in increasing order of "you're on your own."
- **Profile everything.** The toolbar in dev, `assertNumQueries` in tests, `connection.queries` in the shell.

## 12. What you will do next

Thursday and Friday you build the analytics dashboard mini-project. Every panel is one query. The query lives on a custom queryset method (`Author.objects.with_total_views().top_n(5)`). Every panel is covered by an `assertNumQueries` test. Every query is verified with `EXPLAIN ANALYZE` against your seeded data.

If you can do that for four panels in two days, you have internalised Week 5. The Wednesday challenge ("recreate a complex SQL as ORM") is a useful warm-up — it forces you to read SQL critically and reproduce it in the Django expression API, which is the exact skill the dashboard demands.
