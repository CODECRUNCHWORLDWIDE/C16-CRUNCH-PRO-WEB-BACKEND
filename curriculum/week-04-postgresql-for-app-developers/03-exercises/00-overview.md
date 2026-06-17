# Week 4 — Exercises

Three exercises, ~7 hours total. Do them in order; each builds on the previous and the artefacts feed the mini-project.

| # | Exercise | Time |
|---|----------|-----:|
| 1 | [Create and populate](./exercise-01-create-and-populate.md) — schema in `psql` from scratch; 100 k rows via `\copy` | 2h |
| 2 | [`EXPLAIN` a slow query](./exercise-02-explain-a-slow-query.md) — read three plans, name the bottleneck, propose the fix | 2.5h |
| 3 | [Add an index, measure the win](./exercise-03-add-an-index-measure-the-win.md) — add the right index, show before/after | 2.5h |

Work in a **separate database** (`crunchlab`) from your `crunchwriter` Django project — these exercises are intentionally destructive and you should not be reaching for the ORM during them. `psql` only.

Create the lab database before Monday:

```bash
createdb crunchlab
psql crunchlab -c "SELECT version();"
# psql (PostgreSQL) 16.x — good
```

If your Postgres is 15 or older, upgrade before continuing — the lectures reference Postgres 16 specifics. Postgres 17 also works.
