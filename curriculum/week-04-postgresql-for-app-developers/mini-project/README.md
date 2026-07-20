# Mini-Project — Profile a `crunchwriter` query, fix it, measure the win

> Take one real, slow query in your `crunchwriter` Django project. Profile it with `EXPLAIN ANALYZE`. Add the right index (or rewrite the query). Re-measure. Ship the migration. Write the story up so a senior reviewer would approve it.

**Estimated time:** 7 hours, spread across Thursday–Saturday.

## What you build

You will not build a new feature this week. You will instrument and improve the project you already have. The deliverable is **a single pull-request-shaped commit** with:

- A migration that adds (or modifies) one index.
- A before/after `EXPLAIN ANALYZE` write-up.
- A test that asserts the query count and timing budget for the affected view.
- A short narrative explaining the work in language a non-engineer manager could follow.

The work is small in code, deep in reasoning. That is intentional. Every senior backend engineer makes this exact change a few times a quarter; this is the week you do it the first time on purpose.

## Prerequisites

- `crunchwriter v1` from Week 3 is running on **PostgreSQL 16**, not SQLite. See the README's "Switching the project to PostgreSQL" section if not.
- You have seed data large enough to be interesting: at least **10 000 articles**. If your seed is smaller, copy `seed.py` from Exercise 1 (adapted to write through the Django ORM with `bulk_create`) and run it before starting.
- `pg_stat_statements` is enabled locally (Homework Problem 2 walked you through it).

## Acceptance criteria

- [ ] **One identified slow query** in `crunchwriter`, with `pg_stat_statements` evidence: total time, mean time, calls. Document in `before.md`.
- [ ] **`EXPLAIN (ANALYZE, BUFFERS)`** of the query before the fix, copied verbatim into `before.md`. The plan must be at least 50 ms execution time on your dataset — if everything is already 1 ms, seed more data or pick a more involved query.
- [ ] **The bottleneck named** in `before.md`. Not "it's slow"; "the planner picks a Seq Scan + Sort because no index supports `WHERE status = ? ORDER BY published_at DESC`."
- [ ] **A proposed fix**, written **before** you apply it: the SQL `CREATE INDEX` (or query rewrite) and why this is the right shape.
- [ ] **A migration** in `writer/migrations/0XXX_<short_description>.py`. Use `AddIndex` for plain B-tree; use `AddIndexConcurrently` from `django.contrib.postgres.operations` if your fix is a concurrent index; use `RunSQL` with explicit `state_operations` if you need a partial index, expression index, or GIN with a non-default operator class.
- [ ] **`EXPLAIN (ANALYZE, BUFFERS)`** of the query after the fix, in `after.md`. The plan must show the new index in use. The execution time must be measurably lower.
- [ ] **A test** in `writer/tests.py` that hits the affected view and asserts:
  - The number of queries (`assertNumQueries`).
  - The view returns 200.
  - The page contains the expected content.
- [ ] **`README.md`** in `c16-week-04/mini-project/` (your portfolio) with the narrative — see "The write-up" below.
- [ ] **All artefacts checked in**: `before.md`, `after.md`, `README.md`, the migration, the test, any scripts you used to reproduce load.

## Suggested order of operations

### Phase 1 — Find the slow query (90 min)

1. Seed at least 10 000 articles.
2. Reset `pg_stat_statements`: `SELECT pg_stat_statements_reset();`
3. Run the site for ~5 minutes. Visit `/`, `/dashboard/`, several detail pages, log in, log out. Click pagination.
4. Optionally: hit your site with `ab` or `wrk` for one path that feels slow — `ab -n 200 -c 4 http://127.0.0.1:8000/`.
5. Pull the top-10 by `total_exec_time` from `pg_stat_statements`. Pick the one with the highest total time that comes from `writer` (not from `auth`, `sessions`, or `admin`).

If the top is "select 1" (Django's connection check) or something from `django_session`, ignore it and pick the next.

### Phase 2 — Profile (60 min)

1. Get the exact SQL Django emits. Two ways:
   - In Python: `print(connection.queries[-1]["sql"])` after running the view manually with `DEBUG = True`.
   - Or use `django-debug-toolbar`'s SQL panel — every query is visible with parameters bound.
2. Paste the SQL into `psql crunchwriter` and run `EXPLAIN (ANALYZE, BUFFERS)`.
3. Read it. Name the slow node and the cause.

### Phase 3 — Propose and apply the fix (90 min)

1. Write the proposed fix into `before.md` **before applying**.
2. Run the index DDL in `psql` first to confirm the plan changes. Re-run `EXPLAIN (ANALYZE, BUFFERS)`.
3. If the plan now uses the index and the time drops: write the migration. If not: drop the index, propose a different one.
4. Apply the migration to your dev DB: `python manage.py migrate`.

### Phase 4 — Test (60 min)

1. Write the view test. The shape:

```python
from django.test import TestCase
from django.urls import reverse

class ArticleListPerfTests(TestCase):
    fixtures = ["seed_10k.json"]

    def test_list_view_query_count(self):
        with self.assertNumQueries(2):  # one for count, one for page
            response = self.client.get(reverse("writer:article_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<article")
```

2. Run it. It should pass. If it doesn't, your index isn't doing what you think.

### Phase 5 — Write it up (60 min)

`c16-week-04/mini-project/README.md`. Sections:

- **The problem** — 2-3 sentences. Which page felt slow, when, to whom.
- **Evidence** — the `pg_stat_statements` row and the before-plan in a code block.
- **The cause** — 3-4 sentences, plain English. "The planner scanned the entire articles table because no index covered the `WHERE status = 'published' ORDER BY published_at DESC` pattern."
- **The fix** — the migration's SQL in a code block, with one paragraph on why this shape (partial vs full, multicolumn vs single, B-tree vs GIN).
- **The result** — the after-plan in a code block, and the headline numbers: "before 920 ms, after 4 ms, 230× faster."
- **The test** — link to the test file + a 2-line note on what it asserts.
- **What I'd do next** — one paragraph. Honest limitations: maybe the fix only helps the first page; maybe the count query is still slow.

### Phase 6 — Final commit + push (30 min)

Stage: the migration, the test, the README + before/after `.md` files. Push.

Open a pull request **against your own main**. Treat the PR description like a real review request — paste the headline numbers in the description, link to the write-up. Ask a classmate to review the reasoning, not the code.

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Query selection | 15% | A real query, with traffic-shaped evidence (`pg_stat_statements`), not a synthetic one |
| Before-plan reading | 20% | Bottleneck named, not just timed; the right "shape of slow" identified |
| Fix appropriateness | 25% | The index matches the query; you can defend its operator class and predicate |
| After-plan + measurement | 15% | New plan shape confirmed; numbers are honest (median of 3) |
| Test | 10% | `assertNumQueries` plus a content assertion; it would fail if the index were dropped |
| Migration quality | 10% | Reversible; uses `AddIndexConcurrently` if appropriate; named meaningfully |
| Write-up | 5% | A non-engineer manager could read it and understand what changed and why |

## What this prepares you for

- **Week 5** is the Django ORM deep dive. Every `select_related` / `prefetch_related` / `annotate` you write next week will be one you `EXPLAIN ANALYZE` before merging. The habit installed here is the habit you'll use weekly.
- **Week 6** writes real-world migrations. Your "add an index" migration this week is the simplest of the genus; next week's "add a non-null column to a 10 M-row table" is the same skill scaled.
- **Week 11** wires `pg_stat_statements` plus structured logging plus Prometheus into a single observability stack. The local-profiling instinct you build this week is what makes the production version actionable.
- **Week 12** ships this to the public internet. The query you fixed this week may be the difference between your site staying up under traffic and falling over.

## Submission

When done: push, then share the repo URL with a peer. Ask them: "Read the write-up. If you were the senior reviewer on this team, would you merge? If not, what would you ask for?" If they have any technical question you cannot answer in two sentences, you have not finished the write-up.

Then continue to [Week 5 — Django ORM Deep Dive](../../week-05-django-orm-deep-dive/) — where this week's habits get a much bigger surface to act on.
