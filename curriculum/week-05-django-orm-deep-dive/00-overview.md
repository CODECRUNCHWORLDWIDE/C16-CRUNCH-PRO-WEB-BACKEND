# Week 5 — Django ORM Deep Dive

> *Week 4 taught you to read the SQL Postgres receives. Week 5 teaches you to choose the SQL Django emits. The same dashboard can take 1.2 seconds or 12 milliseconds — same models, same database, same data. The difference is whether the engineer who wrote it knew that `select_related` joins, `prefetch_related` issues a second query, `annotate` adds a column, and `aggregate` collapses to a single row. Anyone who confuses those four ships an N+1 to production.*

Welcome to Week 5 of **C16 · Crunch Pro Web Backend**. Phase 1 built a working Django blog. Week 4 made it run on PostgreSQL 16 and made the planner intelligible. This week the Django ORM stops being a polite wrapper around `SELECT * FROM ...` and becomes the surgical instrument it actually is.

By Sunday you will have rewritten the `crunchwriter` analytics dashboard so each panel — top authors by views, articles by category, recently active authors with their latest article — is fetched in **one query**. Not one query per row. Not one query per panel-with-an-N+1. One query, with `annotate`, `Subquery`, `OuterRef`, `Window`, and the manager you wrote yourself.

This is the week the ORM stops being a tool you fight and becomes a tool you reach for on purpose.

## Learning objectives

By the end of this week, you will be able to:

- **Distinguish** `select_related` (SQL `JOIN`, one query, follows forward `ForeignKey` / `OneToOneField`) from `prefetch_related` (a second `IN (...)` query, follows reverse and `ManyToManyField`, evaluated in Python) and pick the right one for the relationship in front of you.
- **Compose** `annotate()` to add per-row computed columns and `aggregate()` to collapse a queryset to a single dictionary, without confusing the two.
- **Build** correlated subqueries with `Subquery` and `OuterRef` to answer questions a `GROUP BY` cannot — "the latest article per author," "the most-viewed comment per article," "the rank of this row within its group."
- **Reach for** window functions (`Window`, `RowNumber`, `Rank`, `Lag`, `Lead`, `Sum` with `partition_by`) when subqueries are the wrong shape and `GROUP BY` would discard the rows you want.
- **Express** complex boolean logic with `Q` objects: `Q(status="published") & (Q(featured=True) | Q(views__gte=1000))`, and know when `Q` is over-engineering for what a kwargs filter would say.
- **Use** `F` expressions to reference columns inside updates (`F("views") + 1`), comparisons (`F("created_at__lt") = F("updated_at")`), and annotations — and know why `F` exists at all.
- **Write** custom managers and querysets (`MyModel.objects.published().for_author(author)`) that make business logic discoverable through the model layer instead of scattering filter chains across views.
- **Choose** between `update()` (one `UPDATE` statement, skips signals + `save()`), `save()` (per-instance, fires signals), and `bulk_update()` (one statement, many instances) — and know what each one costs.
- **Escape** to raw SQL when the ORM is in the way: `queryset.extra()` (legacy, avoid), `RawSQL`, `Model.objects.raw()`, and `connection.cursor()` — in increasing order of "you're on your own now."
- **Measure** every query you write with `django.db.connection.queries`, `assertNumQueries`, and `django-debug-toolbar` — and refuse to merge any view whose query count grows with the page size.

## Prerequisites

- **C16 Week 4 mini-project completed** — `crunchwriter` is on PostgreSQL 16 with at least 10 000 articles seeded; you have profiled one query end-to-end with `EXPLAIN ANALYZE`.
- **C16 Week 2 ORM basics** — `.filter()`, `.exclude()`, `.get()`, `.all()`, `.order_by()`, `.values()`, `.values_list()` are reflexive. If `MyModel.objects.filter(...).values_list("id", flat=True)` is still surprising, revisit Week 2's Lecture 2 before Tuesday.
- **C1 Week 10 SQL** — `GROUP BY`, `HAVING`, window functions (at least conceptually), correlated subqueries. If `SELECT id, name, (SELECT count(*) FROM b WHERE b.a_id = a.id) FROM a` reads as gibberish, do the SQL revision first.
- **A working `EXPLAIN ANALYZE` reflex** — every example in the lectures has a Postgres plan attached; you should expect to paste each one into `psql` and verify.

## Topics covered

- The queryset is lazy: when SQL actually runs, when it does not, and how to inspect what was emitted
- `Queryset.query` and `str(queryset.query)` — your first debugging tool
- `select_related` mechanics: forward `FK`/`O2O` only, becomes a `JOIN`, one query, depth-controlled with `__`
- `prefetch_related` mechanics: reverse `FK`, `M2M`, generic relations, second `IN (...)` query, Python-side join
- `Prefetch()` for shaping the inner queryset (filter, order, annotate the prefetch itself)
- `annotate()` vs `aggregate()`: one adds columns, the other collapses; the difference is `GROUP BY`
- The aggregate functions: `Count`, `Sum`, `Avg`, `Min`, `Max`, `StringAgg`, `ArrayAgg`
- `annotate(...).filter(...)` becomes `HAVING`; `annotate(...).filter(...)` order matters
- The "multiple annotations join multiplication" trap and how `distinct=True` and `Subquery` save you
- `Q` objects: `&`, `|`, `~`, parenthesisation, where they are clearer than kwargs and where they are not
- `F` expressions: cross-column comparisons, in-DB arithmetic, atomic updates, race-free counters
- `Case` / `When` / `Value` — SQL `CASE` expressions inside annotations
- `Coalesce`, `Greatest`, `Least`, `NullIf` — the small functions that close 80% of "the ORM cannot express this" gaps
- `Subquery` + `OuterRef`: the correlated subquery, written in Python
- `Exists` and `~Exists`: existence checks without `count()`
- Window functions in Django 5: `Window`, `partition_by`, `order_by`, `frame`; `RowNumber`, `Rank`, `DenseRank`, `Lag`, `Lead`, `Sum(... )` over a partition
- `Manager` vs `QuerySet`: which methods belong on which class; `Manager.from_queryset()` and why it is the default pattern in modern Django
- `update()` vs `save()` vs `bulk_update()` vs `bulk_create()`: signals, validators, returning, atomicity
- `update_or_create` and `get_or_create` — the right shapes, the race they hide, the `defaults=` kwarg
- `select_for_update()` and `select_for_update(skip_locked=True)` — locking in the ORM
- The escape hatches: `RawSQL`, `Model.objects.raw()`, `connection.cursor()`, when each is the right answer
- Profiling: `connection.queries`, `reset_queries()`, `assertNumQueries`, `django-debug-toolbar`'s SQL panel
- `silk` and `django-perf-rec` — the production-grade options
- The N+1 problem in three forms: in the view, in the template, in the serializer
- When the ORM is genuinely the wrong tool — and how to know

## Weekly schedule

| Day       | Focus                                                                      | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | `select_related`, `prefetch_related`, `annotate`, `aggregate`              | 2h       | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6h          |
| Tuesday   | `Subquery`, `OuterRef`, `Exists`, `Q`, `F`, window functions               | 2h       | 2.5h      | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6.5h        |
| Wednesday | Custom managers, querysets, raw SQL escape hatches                         | 2h       | 2h        | 1h         | 0.5h      | 1h       | 0h           | 0.5h       | 7h          |
| Thursday  | Refactor `crunchwriter` views to one-query panels                          | 0h       | 0.5h      | 1h         | 0.5h      | 1h       | 2h           | 0.5h       | 5.5h        |
| Friday    | Build the analytics dashboard                                              | 0h       | 0h        | 1h         | 0.5h      | 1h       | 2h           | 0h         | 4.5h        |
| Saturday  | Dashboard polish + write-up + `EXPLAIN ANALYZE` every panel                 | 0h       | 0h        | 0h         | 0h        | 1h       | 3h           | 0h         | 4h          |
| Sunday    | Quiz + reflection                                                          | 0h       | 0h        | 0h         | 0.5h      | 0h       | 0h           | 0h         | 0.5h        |
| **Total** |                                                                            | **6h**   | **7h**    | **3h**     | **3h**    | **6h**   | **7h**       | **2h**     | **34h**     |

The week is balanced toward depth in the exercises and a mini-project that exercises every tool from the lectures on a single, real surface — the analytics dashboard. Skip the homework if you must; do not skip the mini-project.

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview |
| [resources.md](./01-resources.md) | Django 5.x queryset API + the references worth bookmarking |
| [lecture-notes/01-select-prefetch-annotate-aggregate.md](./02-lecture-notes/01-select-prefetch-annotate-aggregate.md) | The four daily-driver tools, with the SQL each one emits |
| [lecture-notes/02-subqueries-outerref-window-functions.md](./02-lecture-notes/02-subqueries-outerref-window-functions.md) | Correlated subqueries, `OuterRef`, `Exists`, window functions in Django 5 |
| [lecture-notes/03-custom-managers-and-raw-sql-escape-hatches.md](./02-lecture-notes/03-custom-managers-and-raw-sql-escape-hatches.md) | Custom managers, custom querysets, and the four escape hatches |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of exercises |
| [exercises/exercise-01-annotate-puzzle.md](./03-exercises/exercise-01-annotate-puzzle.md) | Build five annotations against `crunchwriter`; verify the emitted SQL |
| [exercises/exercise-02-subquery-with-outerref.md](./03-exercises/exercise-02-subquery-with-outerref.md) | The latest article per author, in one query |
| [exercises/exercise-03-window-functions.md](./03-exercises/exercise-03-window-functions.md) | Per-author article rank by views, in one query |
| [challenges/README.md](./04-challenges/00-overview.md) | Stretch challenges |
| [challenges/challenge-01-recreate-a-complex-sql-as-orm.md](./04-challenges/challenge-01-recreate-a-complex-sql-as-orm.md) | Given a hand-written SQL report, rebuild it in the ORM. Match the emitted SQL within reason. |
| [quiz.md](./05-quiz.md) | 10 MCQ |
| [homework.md](./06-homework.md) | Six problems (~6h) |
| [mini-project/README.md](./07-mini-project/00-overview.md) | The `crunchwriter` analytics dashboard — every panel, one query |

## Before Monday — verify the project is ready

Three checks. If any fails, fix it before reading Lecture 1.

```bash
# 1. crunchwriter runs on Postgres 16
psql crunchwriter -c "SELECT version();"
# psql (PostgreSQL) 16.x

# 2. you have enough data for the ORM to do interesting things
python manage.py shell -c "from writer.models import Article; print(Article.objects.count())"
# expect >= 10000

# 3. django-debug-toolbar is installed and visible
pip install django-debug-toolbar
# add to INSTALLED_APPS, MIDDLEWARE, urls.py; restart; visit /; toolbar should appear
```

If the row count is low, re-run your Week 2 seed (or copy the bulk seed from Exercise 1 of Week 4 and adapt it to write through the ORM). Without enough rows, every query takes 0 ms and you learn nothing.

## The habit to install this week

For every view you write or modify, do the following before opening a PR:

1. Wrap the view in a test that asserts `assertNumQueries(N)` where `N` is what you expect.
2. Run the test. If it fails because the actual count is higher, look at `connection.queries[-N:]` and find the duplicate shape — that is the N+1.
3. Open `django-debug-toolbar` in the browser. Click the **SQL** panel. Sort by duplicates. There should be zero.
4. For each query the panel shows, click **EXPLAIN** (or paste into `psql`). Verify the plan uses an index scan, not a sequential scan.

If you do this for ten views in a row, you stop writing N+1s. It is a behavioural change, not a knowledge change.

## Stretch goals

- Read the **Django 5.x release notes** for ORM additions — particularly `Window` improvements and `GeneratedField`:
  <https://docs.djangoproject.com/en/5.1/releases/5.0/> and the 5.1 / 5.2 notes.
- Read **"Effective Python ORM"** by Eric Florenzano (free talk on YouTube; search title) — the talk that established `select_related` vs `prefetch_related` as a Django-engineer interview question.
- Install **`django-debug-toolbar`** and **`nplusone`** (the latter raises `NPlusOneError` in tests when one is detected). Run your test suite with both on for a week.
- Skim the **Django source** for `django/db/models/query.py` — the `QuerySet` class itself. Most of what feels like magic is one method deep.

## Up next

[Week 6 — Migrations, Background Jobs, and Caching](../week-06-migrations-jobs-caching/) — the data-tier weeks close out with real-world migrations (adding a non-null column to a 10M-row table without downtime), Redis caching of the analytics dashboard panels you build this week, and Celery for jobs that should not run in a request/response cycle.
