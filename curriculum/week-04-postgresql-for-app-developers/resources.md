# Week 4 — Resources

All free and publicly accessible. Pin Postgres 16: every official link below points at `/docs/16/`, which resolves to the 16.x manual.

## Required reading (work through the week)

- **Postgres 16 manual — Tutorial, Part I**:
  <https://www.postgresql.org/docs/16/tutorial.html>
- **`psql` reference** — every meta-command, with examples:
  <https://www.postgresql.org/docs/16/app-psql.html>
- **DDL — Data Definition** (tables, constraints, defaults, generated columns):
  <https://www.postgresql.org/docs/16/ddl.html>
- **Indexes** — the entire chapter (B-tree, hash, GiST, SP-GiST, GIN, BRIN, partial, expression, multicolumn):
  <https://www.postgresql.org/docs/16/indexes.html>
- **`EXPLAIN`** — the full reference for the command:
  <https://www.postgresql.org/docs/16/sql-explain.html>
- **Using `EXPLAIN`** — the chapter that interprets a plan:
  <https://www.postgresql.org/docs/16/using-explain.html>
- **Statistics used by the planner**:
  <https://www.postgresql.org/docs/16/planner-stats.html>
- **Concurrency control** — MVCC, isolation, locking:
  <https://www.postgresql.org/docs/16/mvcc.html>
- **Transaction isolation** — the four levels and what each does:
  <https://www.postgresql.org/docs/16/transaction-iso.html>
- **JSON types** — `json` vs `jsonb`, operators, functions:
  <https://www.postgresql.org/docs/16/datatype-json.html>
- **JSON functions and operators** — the full reference, including `jsonb_path_query`:
  <https://www.postgresql.org/docs/16/functions-json.html>
- **Full-text search**:
  <https://www.postgresql.org/docs/16/textsearch.html>
- **Django databases reference** — Postgres-specific notes, connection settings:
  <https://docs.djangoproject.com/en/stable/ref/databases/#postgresql-notes>
- **Django Postgres-specific fields and functions** (JSONField, ArrayField, search vector, trigram):
  <https://docs.djangoproject.com/en/stable/ref/contrib/postgres/>

## Postgres 16 specifics worth knowing

- **Postgres 16 release notes** — read the "Performance" section at minimum:
  <https://www.postgresql.org/docs/16/release-16.html>
- **`pg_stat_io`** — new in 16, the I/O view that replaces a lot of ad-hoc diagnostics:
  <https://www.postgresql.org/docs/16/monitoring-stats.html#MONITORING-PG-STAT-IO-VIEW>
- **SQL/JSON path improvements in 16** — `jsonb_path_query` and friends gained substantial features:
  <https://www.postgresql.org/docs/16/functions-json.html#FUNCTIONS-SQLJSON-PATH>
- **`pg_stat_statements`** — your first profiling tool in production, extension lives in `contrib`:
  <https://www.postgresql.org/docs/16/pgstatstatements.html>

## The three external references that pay for themselves

- **Use The Index, Luke** — Markus Winand. The single best book on indexing. Free online:
  <https://use-the-index-luke.com/>
- **Explain Visualizer** (Dalibo) — paste a plan, get a tree view. The first time you use it on a real plan you will not go back to plain text:
  <https://explain.dalibo.com/>
- **PostgreSQL Wiki — Performance Optimization**:
  <https://wiki.postgresql.org/wiki/Performance_Optimization>

## On transactions and concurrency

- **Jepsen — PostgreSQL** — Aphyr's analysis of Postgres isolation, with examples of what `READ COMMITTED` actually permits:
  <https://jepsen.io/analyses/postgresql-12.3>
- **A Critique of ANSI SQL Isolation Levels** — Berenson et al. (1995). The paper that defined the modern vocabulary. Free PDF online; one Google search away.

## On JSONB and full-text

- **Postgres JSONB cheat sheet** — every operator on one page (community-maintained):
  <https://devhints.io/postgresql-json>
- **Postgres full-text search internals** (talk by Oleg Bartunov, free PDF) — search for "PostgreSQL Full Text Search Oleg Bartunov pdf"; he is the implementor.

## Tools to install before Monday

- **`psql` 16** — comes with Postgres. Verify with `psql --version` (must print `psql (PostgreSQL) 16.x`).
- **`pgcli`** — autocomplete and syntax highlighting in the terminal. `pip install pgcli` or `brew install pgcli`.
- **`psycopg` 3** — the modern Postgres driver for Python; what Django 5 prefers. `pip install "psycopg[binary]>=3.1"`.
- **Optional: Postico 2** or **TablePlus** or **DBeaver** — a GUI for browsing. The terminal is mandatory; the GUI is convenience.

## Glossary

| Term | Definition |
|------|------------|
| **`psql`** | The official Postgres command-line client; runs SQL and `\` meta-commands |
| **Schema (Postgres sense)** | A namespace inside a database; default is `public` |
| **Schema (general sense)** | The shape of your data — tables, columns, constraints |
| **DDL** | Data Definition Language — `CREATE TABLE`, `ALTER`, `DROP` |
| **DML** | Data Manipulation Language — `SELECT`, `INSERT`, `UPDATE`, `DELETE` |
| **B-tree** | The default index type; supports equality, range, `ORDER BY`, prefix `LIKE` |
| **GIN** | Generalized Inverted Index; multi-value (arrays, JSONB, tsvector) |
| **BRIN** | Block Range Index; tiny, for very large append-mostly tables |
| **Partial index** | An index with a `WHERE` predicate; covers a subset of rows only |
| **Expression index** | An index on `expression(column)` rather than the column itself |
| **`EXPLAIN`** | Show the planner's chosen plan, with cost estimates |
| **`EXPLAIN ANALYZE`** | Run the query and show estimates **plus** actual rows and time |
| **Seq Scan** | Full table read; necessary when no useful index exists or the table is small |
| **Index Scan** | Walk the index, then fetch matching heap rows |
| **Index Only Scan** | Walk the index; the index covers every column the query needs |
| **Bitmap Heap Scan** | Build a bitmap from one or more indexes, then read the heap once |
| **MVCC** | Multi-Version Concurrency Control; how Postgres lets readers and writers coexist |
| **`xmin` / `xmax`** | Transaction IDs that mark a row's visibility |
| **`VACUUM`** | Reclaim dead tuples; updates the visibility map; autovacuum runs this for you |
| **JSONB** | Binary JSON, with operators (`->`, `->>`, `@>`, `?`) and GIN indexability |
| **`tsvector`** | A document parsed into searchable lexemes |
| **`tsquery`** | A search expression matched against a `tsvector` |
| **`pg_stat_statements`** | Extension that tracks the slowest and most-frequent statements |
| **N+1** | One query for the parent plus one per child; lethal in lists |

---

*Broken link? Open an issue. Postgres docs sometimes restructure URLs between major versions — if a `/docs/16/` link 404s, drop in `/docs/current/` and re-confirm the page exists in 16.*
