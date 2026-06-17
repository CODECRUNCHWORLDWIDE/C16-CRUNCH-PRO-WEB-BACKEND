# Week 5 — Resources

All free and publicly accessible. Pin Django 5.x: every official link below points at `/en/stable/`, which resolves to the current 5.x docs. If you want the version explicitly, swap `stable` for `5.1` or `5.2`.

## Required reading (work through the week)

- **Django QuerySet API reference** — the canonical list of every method on a queryset, with examples:
  <https://docs.djangoproject.com/en/stable/ref/models/querysets/>
- **Making queries** — the narrative companion to the reference; read it before the reference:
  <https://docs.djangoproject.com/en/stable/topics/db/queries/>
- **Aggregation** — `annotate`, `aggregate`, the `GROUP BY` semantics, the multiplication trap:
  <https://docs.djangoproject.com/en/stable/topics/db/aggregation/>
- **Database functions** — `Coalesce`, `Greatest`, `Least`, `Concat`, `Trim`, `Lower`, `Now`, `Trunc`, and the rest:
  <https://docs.djangoproject.com/en/stable/ref/models/database-functions/>
- **Conditional expressions** — `Case`, `When`, `Value`, `Exists`:
  <https://docs.djangoproject.com/en/stable/ref/models/conditional-expressions/>
- **Query Expressions** — `F`, `Subquery`, `OuterRef`, `Window`, `RawSQL`:
  <https://docs.djangoproject.com/en/stable/ref/models/expressions/>
- **Managers** — the full chapter, including custom managers, custom querysets, and `Manager.from_queryset()`:
  <https://docs.djangoproject.com/en/stable/topics/db/managers/>
- **Performing raw SQL queries** — `raw()`, `RawSQL`, `connection.cursor()`:
  <https://docs.djangoproject.com/en/stable/topics/db/sql/>
- **Database access optimisation** — Django's own opinionated guide; short and dense:
  <https://docs.djangoproject.com/en/stable/topics/db/optimization/>
- **Multiple databases** (skim) — relevant when you hit it; not core this week:
  <https://docs.djangoproject.com/en/stable/topics/db/multi-db/>

## Django 5 specifics worth knowing

- **Django 5.0 release notes — Database highlights** — `GeneratedField`, `db_default`:
  <https://docs.djangoproject.com/en/stable/releases/5.0/>
- **Django 5.1 release notes** — composite primary keys (preview) and `QuerySet.values()` improvements:
  <https://docs.djangoproject.com/en/stable/releases/5.1/>
- **Django 5.2 release notes** — newer optimisations to scan through if you are on 5.2:
  <https://docs.djangoproject.com/en/stable/releases/5.2/>
- **`Window` expressions in Django** — the full reference, with the frame syntax:
  <https://docs.djangoproject.com/en/stable/ref/models/expressions/#window-functions>

## The references worth bookmarking forever

- **PostgreSQL 16 — Window Functions** — the SQL side of what Django's `Window` emits. The Django docs assume you know this chapter:
  <https://www.postgresql.org/docs/16/tutorial-window.html>
- **PostgreSQL 16 — Functions and Operators** — when the ORM cannot help you, the function name will be here:
  <https://www.postgresql.org/docs/16/functions.html>
- **Django Debug Toolbar — SQL panel** — read the docs once; install it on every project for the rest of your career:
  <https://django-debug-toolbar.readthedocs.io/en/latest/panels.html#sql>

## On the N+1 problem and ORM performance

- **"Django ORM Cookbook"** (free online book, community-maintained) — 60 short recipes covering the situations the official docs leave abstract:
  <https://django-orm-cookbook-ko.readthedocs.io/en/latest/> (and the English mirror, search "Django ORM Cookbook")
- **`nplusone`** — runtime detector that raises an error in tests when an N+1 occurs. Use it in CI:
  <https://github.com/jmcarp/nplusone>
- **`django-perf-rec`** — record and snapshot the SQL of a view; CI fails when the SQL count or shape changes unexpectedly:
  <https://github.com/adamchainz/django-perf-rec>
- **`django-silk`** — heavier than `debug-toolbar`, stores per-request profiles in the database; very good for staging:
  <https://github.com/jazzband/django-silk>

## On subqueries, window functions, and SQL fluency

- **Markus Winand — "Modern SQL"** — the same author as *Use The Index, Luke*; a series of free articles on what SQL learned after 1992 (window functions, CTEs, `LATERAL`):
  <https://modern-sql.com/>
- **Postgres docs — Window Functions reference** — the syntactic ground truth for `OVER (PARTITION BY ... ORDER BY ... ROWS BETWEEN ...)`:
  <https://www.postgresql.org/docs/16/sql-expressions.html#SYNTAX-WINDOW-FUNCTIONS>
- **"Use The Index, Luke" — chapter on Top-N queries** — directly applies to your "top 10 authors" panel:
  <https://use-the-index-luke.com/sql/partial-results/top-n-queries>

## On raw SQL — when and how

- **Django docs — Performing raw SQL queries** (linked above), plus:
- **PEP 249** — Python's DB-API 2.0, the spec `connection.cursor()` implements. Worth reading once:
  <https://peps.python.org/pep-0249/>
- **`psycopg` 3 — basic usage** — the modern Postgres driver under Django 5:
  <https://www.psycopg.org/psycopg3/docs/basic/usage.html>

## Tools to install before Monday

- **`django-debug-toolbar`** — `pip install django-debug-toolbar`; the **single most useful tool** for this week. Add to `INSTALLED_APPS`, `MIDDLEWARE`, and `urls.py` per the install guide.
- **`ipython`** + **`django-extensions`** — `pip install ipython django-extensions`; then `python manage.py shell_plus --ipython` auto-imports every model and gives you tab completion. Far better than the default shell.
- **`nplusone`** (optional but recommended) — `pip install nplusone`; configure in `settings.py` to raise on N+1 in test mode.
- **`pgcli`** — already installed if you did Week 4 properly; this week you will live in it.

## Glossary

| Term | Definition |
|------|------------|
| **QuerySet** | A lazy, chainable description of a database query; SQL emitted only on iteration/evaluation |
| **`select_related`** | A `JOIN`-based prefetch for forward `FK` / `O2O`; one query, more columns |
| **`prefetch_related`** | A second `IN (...)` query for reverse `FK` / `M2M`; Python-side join |
| **`Prefetch()`** | A wrapper that lets you shape the inner queryset of a `prefetch_related` |
| **`annotate`** | Adds a computed column to each row of the queryset |
| **`aggregate`** | Collapses the queryset to a single dictionary of computed values |
| **`GROUP BY` (Django)** | Implied by `annotate()` after `.values()`; the columns of `.values()` become the grouping keys |
| **`Subquery`** | A correlated subquery written in Python; produces a single column |
| **`OuterRef`** | Refers to the outer query inside a `Subquery` |
| **`Exists`** | A subquery that returns boolean; faster than `count() > 0` |
| **`Q` object** | A reusable, composable boolean expression: `Q(a=1) | Q(b=2)` |
| **`F` expression** | A reference to a column on the same row; lets you do in-DB arithmetic and avoid races |
| **`Case` / `When`** | SQL `CASE` inside an `annotate` |
| **`Window`** | A window-function expression: `Window(expression, partition_by, order_by, frame)` |
| **Manager** | The class behind `MyModel.objects`; you can write your own |
| **`Manager.from_queryset(QuerySet)`** | The standard pattern to turn a custom queryset into a custom manager |
| **`update()` (queryset)** | A single `UPDATE` statement; skips `save()` and signals; very fast |
| **`bulk_update()`** | One statement for many in-memory instances; same caveats as `update()` |
| **`bulk_create()`** | One `INSERT` for many instances; supports `update_conflicts` (Postgres `ON CONFLICT`) |
| **`select_for_update`** | Issues `SELECT ... FOR UPDATE`; rows are locked until the transaction ends |
| **N+1** | One query for the parent, one per child; the canonical ORM bug |
| **`assertNumQueries(N)`** | Test assertion that exactly `N` queries ran inside the block |

---

*Broken link? Open an issue. Django docs sometimes move pages between minor versions — if `/en/stable/` 404s, swap to `/en/5.1/` and re-confirm.*
