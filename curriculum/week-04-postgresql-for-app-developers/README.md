# Week 4 — PostgreSQL for Application Developers

> *The ORM hides SQL until it doesn't. The day a page takes nine seconds to render, you open `psql`, paste the query the ORM emitted, prepend `EXPLAIN ANALYZE`, and read. That is the skill this week. Every other Postgres skill — indexes, transactions, JSONB, full-text search — is a tool you reach for once the plan tells you which one to reach for.*

Welcome to Week 4 of **C16 · Crunch Pro Web Backend**. Phase 1 ended with `crunchwriter v1` running on SQLite — the default Django gives you, the right database for `manage.py runserver`, and the wrong database for everything that ships to production. This week you switch to PostgreSQL 16 and learn enough about it that the switch is not a cargo-cult.

By Sunday you will have profiled a real query in `crunchwriter`, located the missing index, added it, and re-run `EXPLAIN ANALYZE` to confirm the planner now picks an Index Scan instead of a Seq Scan. The number you put in your mini-project README — "from 920 ms to 4 ms" — is the number a hiring manager actually wants to see.

This is the week Postgres stops being "the database the ORM talks to" and starts being a tool you reason about directly.

## Learning objectives

By the end of this week, you will be able to:

- **Drive** `psql` confidently: `\dt`, `\d table`, `\di`, `\df`, `\timing`, `\watch`, `\copy`, `\ef`, `\?`.
- **Design** a schema that a senior reviewer would not redline: `NOT NULL` by default, surrogate keys with care, `CHECK` constraints, `FOREIGN KEY` with the right `ON DELETE`, `UNIQUE` where the domain demands it.
- **Choose** between the index types Postgres ships: B-tree (the default), GIN (multi-value, JSONB, full-text), partial (predicate-scoped), expression (function-of-column), and BRIN (large append-only).
- **Read** an `EXPLAIN ANALYZE` plan top-to-bottom: rows estimated vs actual, loops, scan types, sort method, JIT, buffer hits, and the single number that matters (planning + execution time).
- **Diagnose** the four most common slow-query causes: missing index, wrong index, bad row-count estimate, and a join order the planner cannot recover from.
- **Reason** about transactions: `BEGIN` / `COMMIT` / `ROLLBACK`, the four isolation levels, what `READ COMMITTED` actually reads, and when `SERIALIZABLE` saves you from data corruption.
- **Use** JSONB as a typed-but-flexible column: `->`, `->>`, `@>`, `?`, `jsonb_path_query`, GIN-indexed lookups, and the migration path from JSONB back to real columns.
- **Build** full-text search with `tsvector`, `tsquery`, `to_tsvector('english', ...)`, generated columns, GIN indexes on tsvectors, and `ts_rank` for ordering.
- **Identify** when the Django ORM is misleading you — `count()` that scans the full table, `Q(field__icontains=...)` that ignores a GIN index, `prefetch_related` issuing a query per page.

## Prerequisites

- **C16 Week 3 mini-project completed** — `crunchwriter v1` is running locally with seed data; you can hit `/`, log in, and visit `/dashboard/`.
- **C1 Week 10** — SQL fundamentals: `SELECT`, `JOIN`, `GROUP BY`, `HAVING`, subqueries. If a `LEFT JOIN ... ON` is fuzzy, revisit it before Tuesday.
- **A working local Postgres 16+** — `brew install postgresql@16` on macOS, `apt install postgresql-16` on Debian/Ubuntu, or `docker run -p 5432:5432 postgres:16`. We do not use Postgres 17 features in this week; both 16 and 17 are fine, but the lectures pin 16.
- **Basic comfort in the terminal** — you can `psql -d dbname`, `\q`, and `Ctrl-C` out of a runaway query without panic.

## Topics covered

- The `psql` toolkit: meta-commands, `\timing`, `\watch`, `\copy`, output formats
- Database, schema, table, role, tablespace — what each one is, and what most apps actually use
- Schema design beyond toy examples: `NOT NULL`, defaults, generated columns, `CHECK`, `UNIQUE`, composite keys
- `FOREIGN KEY` semantics: `ON DELETE CASCADE` vs `RESTRICT` vs `SET NULL`, and the cost of each
- The four index types you will actually use: B-tree, GIN, partial, expression
- B-tree mechanics: ordered pages, why a B-tree index supports equality, range, `ORDER BY`, and prefix `LIKE`
- GIN indexes for arrays, JSONB, and full-text
- Partial indexes: indexing the subset that matters (e.g. `WHERE status = 'published'`)
- Expression indexes: indexing `lower(email)` so case-insensitive lookups stay fast
- `EXPLAIN`, `EXPLAIN ANALYZE`, `EXPLAIN (ANALYZE, BUFFERS)` — what each adds
- Reading a plan: Seq Scan, Index Scan, Index Only Scan, Bitmap Heap Scan, Nested Loop, Hash Join, Merge Join
- The cost model: page reads, CPU tuples, `random_page_cost`, why SSDs change the math
- Statistics: `pg_stats`, `n_distinct`, `most_common_vals`, when to `ANALYZE` and when to bump `default_statistics_target`
- Transactions and the ACID guarantees Postgres actually provides
- Isolation levels: `READ UNCOMMITTED` (which Postgres treats as `READ COMMITTED`), `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`
- MVCC, `xmin`/`xmax`, dead tuples, `VACUUM`, `pg_stat_user_tables`
- JSONB: storage, operators, indexing, `jsonb_path_query` in Postgres 16
- Full-text search: `tsvector`, `tsquery`, language configurations, `ts_rank`, stored generated tsvector columns
- ORM tells: when Django's queryset will read in a way no index can help
- `pg_stat_statements` — your first profiling tool in production
- `psycopg` 3 connection pooling vs `pgbouncer` — what each solves

## Weekly schedule

| Day       | Focus                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|---------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | `psql`, schema design, B-tree + GIN indexes | 2h       | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6h          |
| Tuesday   | `EXPLAIN ANALYZE` + the query planner        | 2h       | 2.5h      | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6.5h        |
| Wednesday | Transactions, isolation, JSONB, full-text   | 2h       | 2h        | 1h         | 0.5h      | 1h       | 0h           | 0.5h       | 7h          |
| Thursday  | ORM tells; profile a `crunchwriter` query   | 0h       | 0.5h      | 1h         | 0.5h      | 1h       | 2h           | 0.5h       | 5.5h        |
| Friday    | Mini-project deep work                       | 0h       | 0h        | 1h         | 0.5h      | 1h       | 2h           | 0h         | 4.5h        |
| Saturday  | Mini-project deep work + write-up           | 0h       | 0h        | 0h         | 0h        | 1h       | 3h           | 0h         | 4h          |
| Sunday    | Quiz + reflection                           | 0h       | 0h        | 0h         | 0.5h      | 0h       | 0h           | 0h         | 0.5h        |
| **Total** |                                             | **6h**   | **7h**    | **3h**     | **3h**    | **6h**   | **7h**       | **2h**     | **34h**     |

The week is slightly lighter than Week 3 on raw hours because the mini-project is narrower in scope — one query, profiled, fixed, measured. The depth lives in the reading.

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview |
| [resources.md](./resources.md) | Postgres 16 docs + the three external references that pay for themselves |
| [lecture-notes/01-psql-schema-and-indexes.md](./lecture-notes/01-psql-schema-and-indexes.md) | `psql`, schema design, B-tree / GIN / partial / expression indexes |
| [lecture-notes/02-explain-analyze-and-the-query-planner.md](./lecture-notes/02-explain-analyze-and-the-query-planner.md) | Reading plans, the cost model, the four shapes of "slow" |
| [lecture-notes/03-transactions-isolation-jsonb-fts.md](./lecture-notes/03-transactions-isolation-jsonb-fts.md) | Transactions, isolation levels, JSONB, full-text search |
| [exercises/README.md](./exercises/README.md) | Index of exercises |
| [exercises/exercise-01-create-and-populate.md](./exercises/exercise-01-create-and-populate.md) | A schema from scratch, 100 k rows, `\copy`, indexes on purpose |
| [exercises/exercise-02-explain-a-slow-query.md](./exercises/exercise-02-explain-a-slow-query.md) | Read three plans, name the bottleneck, propose the fix |
| [exercises/exercise-03-add-an-index-measure-the-win.md](./exercises/exercise-03-add-an-index-measure-the-win.md) | Add the right index. Measure before and after. Defend the choice. |
| [challenges/README.md](./challenges/README.md) | Stretch challenges |
| [challenges/challenge-01-jsonb-vs-real-columns.md](./challenges/challenge-01-jsonb-vs-real-columns.md) | Same workload, two schemas, which one earns its keep |
| [quiz.md](./quiz.md) | 10 MCQ |
| [homework.md](./homework.md) | Six problems (~6h) |
| [mini-project/README.md](./mini-project/README.md) | Profile, fix, measure: one real `crunchwriter` query, end to end |

## Switching the project to PostgreSQL — do this Monday morning

Before Monday's lecture, get `crunchwriter` running on Postgres 16. This is a 20-minute job; do it before you read Lecture 1 so the examples run against your own database.

```bash
# macOS
brew install postgresql@16
brew services start postgresql@16

# Or with Docker, anywhere
docker run --name crunch-pg -e POSTGRES_PASSWORD=dev -p 5432:5432 -d postgres:16
```

Create the database and the role:

```bash
createdb crunchwriter
psql crunchwriter -c "CREATE ROLE crunch WITH LOGIN PASSWORD 'dev';"
psql crunchwriter -c "GRANT ALL ON DATABASE crunchwriter TO crunch;"
```

Point Django at it (`settings.py`):

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "crunchwriter",
        "USER": "crunch",
        "PASSWORD": "dev",
        "HOST": "127.0.0.1",
        "PORT": "5432",
    }
}
```

Install the driver — `psycopg` 3 is the modern choice and what Django 5 recommends:

```bash
pip install "psycopg[binary]>=3.1"
```

Then migrate and seed:

```bash
python manage.py migrate
python manage.py loaddata writer/fixtures/seed.json   # if you wrote a fixture in W2
# or re-run whatever script seeded SQLite
```

Verify by entering `psql crunchwriter` and running `\dt` — you should see the Django tables.

If anything in this paragraph is unclear, the [Django databases reference](https://docs.djangoproject.com/en/stable/ref/databases/) is the single source of truth; do not improvise.

## Stretch goals

- Read the **Postgres 16 release notes** — particularly the planner improvements and the `json_array` / SQL/JSON additions:
  <https://www.postgresql.org/docs/16/release-16.html>
- Install **`pgcli`** (a `psql` replacement with autocompletion) and use it for the week. The autocompletion teaches you table names you would otherwise miss.
- Read the **`pg_stat_statements`** docs and enable the extension locally:
  <https://www.postgresql.org/docs/16/pgstatstatements.html>
- Skim **"Use The Index, Luke"** by Markus Winand (free online book) — at least the B-tree chapters. It is the best single resource on database indexing ever written, and it predates and outlives every framework.

## Up next

[Week 5 — Django ORM Deep Dive](../week-05-django-orm-deep-dive/) — now that you can read the SQL Postgres receives, the ORM tricks you'll learn next week (`select_related`, `prefetch_related`, `annotate`, `Subquery`) are no longer magic. You will know which one to reach for because you will know what each one emits.
