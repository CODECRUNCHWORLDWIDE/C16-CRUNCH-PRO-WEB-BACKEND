# Week 4 — Homework

Six problems, ~6h. Build them in your `crunchwriter` repo under `c16-week-04/homework/`.

Some of these run against `crunchlab` (the bare-Postgres database from the exercises); others run against `crunchwriter` (the Django project on Postgres). Each problem says which.

---

## Problem 1 — Read the schema Django emitted (30 min)

**Database:** `crunchwriter`.

Run `python manage.py sqlmigrate writer 0001` and save the output to `c16-week-04/homework/01-emitted.sql`. Read it.

Answer in `01-django-vs-handwritten.md`:

1. **Three columns** where Django's emitted SQL differs from what you would have written by hand (after Lecture 1). For each, one sentence on whether Django's choice is good, fine, or wrong-for-this-app.
2. **One constraint** Django did not emit that you would have added (CHECK, additional UNIQUE, deferrable FK, etc.). Write the SQL.
3. **The biggest table** in your project today — `SELECT pg_size_pretty(pg_total_relation_size('writer_article'));`. Note it.

**Acceptance:** `01-emitted.sql` + `01-django-vs-handwritten.md`.

---

## Problem 2 — Index your slowest query (60 min)

**Database:** `crunchwriter`.

Enable `pg_stat_statements` in your local Postgres:

```bash
# in postgresql.conf or as a session setting:
shared_preload_libraries = 'pg_stat_statements'
```

Restart Postgres. Then:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

Run your `crunchwriter` site for ~5 minutes — click around the public list, your dashboard, a few article detail pages, log in and out a few times. Then:

```sql
SELECT calls, total_exec_time::int AS total_ms, mean_exec_time::int AS mean_ms, query
FROM pg_stat_statements
WHERE query NOT ILIKE 'SELECT pg_%'
ORDER BY total_exec_time DESC
LIMIT 10;
```

Save the result to `02-top-queries.md`.

Pick **one** query with non-trivial `total_exec_time` (anything above 50 ms median is fair game). `EXPLAIN ANALYZE` it. Add the index you think it needs. Re-run `EXPLAIN ANALYZE`. Write both plans to `02-fix.md`.

**Acceptance:**

- `02-top-queries.md` with the top 10 by total time.
- `02-fix.md` with before/after plans for one query.
- A migration in `writer/migrations/0XXX_add_index.py` using `AddIndex` (or `AddIndexConcurrently`).
- A 4-sentence note: which query, why this index, what was the win.

---

## Problem 3 — `select_for_update` for a real race (60 min)

**Database:** `crunchwriter`.

Add a `view_count` column to `Article`. Increment it on every detail-page view:

```python
def get(self, request, *args, **kwargs):
    response = super().get(request, *args, **kwargs)
    # the wrong way:
    Article.objects.filter(pk=self.object.pk).update(view_count=F("view_count") + 1)
    return response
```

That `F`-expression update is **race-free** at the SQL level — `UPDATE t SET c = c + 1` reads-modifies-writes atomically. Good.

Now imagine a different requirement: "every 100 views, write a row to `ViewMilestone(article, count, hit_at)`." Naively:

```python
Article.objects.filter(pk=...).update(view_count=F("view_count") + 1)
a = Article.objects.get(pk=...)
if a.view_count % 100 == 0:
    ViewMilestone.objects.create(article=a, count=a.view_count, hit_at=timezone.now())
```

This **has a race** under concurrency: two concurrent requests can both observe `view_count = 100` and both insert a milestone, or both observe 99 and miss it.

In `c16-week-04/homework/03-race.md`:

1. **Reproduce the race.** Use a thread pool or `concurrent.futures` to fire 200 concurrent GETs at the detail view. Count `ViewMilestone` rows — likely > 2 (or 0 if the race went the other way).
2. **Fix the race** with `select_for_update` inside `transaction.atomic()`. The fix should make the count check happen on a locked row.
3. **Re-run** — the milestone count should now be exactly 2 (for 200 views).
4. **One paragraph** on what `select_for_update` does vs the bare `UPDATE ... SET c = c+1`.

**Acceptance:** `03-race.md` with the before/after counts, the diff of the fix, and the paragraph.

---

## Problem 4 — JSONB the right way (60 min)

**Database:** `crunchwriter`.

Add a `meta JSONFelt` field to `Article` for arbitrary editor-supplied metadata (think: open-graph image, custom CSS class, social-card tagline). This field should:

- Default to `{}`.
- Be filterable via `Article.objects.filter(meta__contains={"featured": True})` — Django's JSONField `__contains` translates to `@>`.
- Have a **GIN index** with `jsonb_path_ops` (write the migration in `RunSQL` form — Django's `Index` does not yet support choosing the operator class directly).
- Be settable from a form in the admin (any form will do).

Write three queries you'd realistically run from a view, and confirm with `EXPLAIN ANALYZE` they use the GIN.

**Acceptance:**

- Model field + migration (with the `jsonb_path_ops` GIN as `RunSQL` if needed).
- `04-jsonb.md` with the three EXPLAINs and a 3-sentence rationale: when would you migrate `meta->>'featured'` from JSONB to a real column?

---

## Problem 5 — Full-text search wired to the site (60 min)

**Database:** `crunchwriter`.

Add a search box to the public list page. Wire it to `django.contrib.postgres.search`:

1. Add `search_vector` as a `SearchVectorField` on `Article`.
2. In the migration, populate it as a `GENERATED ALWAYS AS (setweight(to_tsvector('english', title), 'A') || setweight(to_tsvector('english', coalesce(body, '')), 'B')) STORED` via `RunSQL`.
3. Add a GIN index on `search_vector`.
4. Add a `q` query string parameter handled by `ListView.get_queryset`:

```python
from django.contrib.postgres.search import SearchQuery, SearchRank

def get_queryset(self):
    qs = super().get_queryset().filter(status="published")
    q = self.request.GET.get("q")
    if q:
        sq = SearchQuery(q, search_type="websearch", config="english")
        qs = qs.annotate(rank=SearchRank("search_vector", sq)).filter(search_vector=sq).order_by("-rank")
    return qs
```

5. In `05-fts.md`, paste the `EXPLAIN ANALYZE` of `/?q=postgres` and the same query without `?q=`. Confirm the GIN index is used.

**Acceptance:**

- Migrations + view code + template input.
- `05-fts.md` with both EXPLAINs.
- A 2-sentence note: when would you outgrow Postgres FTS and reach for Elasticsearch / OpenSearch / Meilisearch?

---

## Problem 6 — Reflection (45 min)

`c16-week-04/homework/06-reflection.md`, ~400 words:

1. **The Django ORM is convenient** for the 90% case and misleading for the 10%. Which 10% bit you this week? What is the smallest abstraction you'd want around `EXPLAIN ANALYZE` in your project?
2. **You added two new indexes this week** (Problem 2 + Problem 5's GIN). What is your rule for *when not* to add another?
3. **Transactions and isolation** rarely make beginner curricula. Why does this one include them in Week 4 rather than Week 9?
4. **What habit do you want to install for Week 5?** (Suggestion: run `EXPLAIN ANALYZE` against the SQL Django emits for every new view, before merging.)

---

## Time budget

| Problem | Time |
|--------:|----:|
| 1 — Emitted schema | 30 min |
| 2 — Slowest query | 60 min |
| 3 — `select_for_update` | 60 min |
| 4 — JSONB | 60 min |
| 5 — Full-text search | 60 min |
| 6 — Reflection | 45 min |
| **Total** | **~5 h 55 m** |

After homework, ship the [mini-project](./mini-project/README.md) — profile, fix, measure one real query in `crunchwriter`.
