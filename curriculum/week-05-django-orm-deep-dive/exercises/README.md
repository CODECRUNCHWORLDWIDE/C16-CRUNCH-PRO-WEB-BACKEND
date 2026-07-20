# Week 5 — Exercises

Three exercises, ~7 hours total. Do them in order; each builds on the previous, and all three feed directly into the mini-project.

| # | Exercise | Time |
|---|----------|-----:|
| 1 | [Annotate puzzle](./exercise-01-annotate-puzzle.md) — five annotations against `crunchwriter`, verify the emitted SQL | 2h |
| 2 | [Subquery with `OuterRef`](./exercise-02-subquery-with-outerref.md) — the latest article per author, in one query | 2.5h |
| 3 | [Window functions](./exercise-03-window-functions.md) — per-author article rank by views, in one query | 2.5h |

All three run against your `crunchwriter` Django project on PostgreSQL 16, with at least 10 000 seeded articles. If you do not have that much data yet, copy the bulk seed from Week 4 Exercise 1 (adapted to write through the ORM with `bulk_create`) and run it before starting Exercise 1.

Work in `python manage.py shell_plus --ipython` (from `django-extensions`) — it auto-imports your models and makes the iteration loop tight. Open `django-debug-toolbar` in a browser tab for any view-shaped exercise; you will paste plans into the write-up.

For each exercise:

1. Write the queryset.
2. Print `str(qs.query)` and **read** the SQL — does it look like what you expected?
3. Evaluate the queryset; copy the SQL from `connection.queries[-1]["sql"]`.
4. Paste into `psql crunchwriter` and run `EXPLAIN (ANALYZE, BUFFERS)`.
5. Save the queryset code, the emitted SQL, and the plan into the exercise's markdown file.

Acceptance is the artefact, not the time spent. A well-documented exercise with three queries and three plans beats a hastily completed one with no evidence.
