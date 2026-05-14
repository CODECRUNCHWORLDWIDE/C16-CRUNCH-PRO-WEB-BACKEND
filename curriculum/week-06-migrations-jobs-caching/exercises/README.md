# Week 6 — Exercises

Three exercises, ~6 hours total. Do them in order; each lays groundwork for the mini-project.

| # | Exercise | Time |
|---|----------|-----:|
| 1 | [Data migration](./exercise-01-data-migration.md) — backfill a computed column with `RunPython`, reversible, batched | 2h |
| 2 | [First Celery task](./exercise-02-first-celery-task.md) — wire Celery, send a task, watch it run, write a retry | 2h |
| 3 | [Cache-aside](./exercise-03-cache-aside.md) — cache the analytics panels with explicit keys and `post_save` invalidation | 2h |

All three run against your `crunchwriter` Django project on PostgreSQL 16, with at least 10 000 seeded articles and the Week 5 analytics dashboard wired up. If either is missing, fix it before starting Exercise 1.

Work in a terminal with three panes open:

- Pane 1: `python manage.py shell_plus --ipython`
- Pane 2: `celery -A crunchwriter worker -l info` (from Exercise 2 onwards)
- Pane 3: `redis-cli MONITOR` (from Exercise 3 onwards) — every Redis command crossing the wire prints here in real time

For each exercise:

1. Read the brief twice before opening a file.
2. Write the code in small steps; commit between steps.
3. Watch the side effect. The migration changes `django_migrations`; the Celery task moves through `pending → started → success`; the cache key appears in `redis-cli MONITOR`.
4. Save evidence (terminal pastes, `sqlmigrate` output, Redis snapshots) into the exercise's markdown write-up.

Acceptance is the artefact, not the time. A well-documented exercise with three pieces of evidence beats a hastily completed one with no proof.
