# Challenge 1 — Recreate a complex SQL as ORM

**Time:** ~3 hours. **Difficulty:** Medium-Hard. **Goal:** Given a hand-written analytics SQL query, reproduce its results in a single Django ORM queryset. Match the emitted SQL within reason; defend every difference.

## Why this exists

In every team you will join, there is a `reports/old_stats.sql` file someone wrote in 2019 because the ORM "couldn't do it". Six years later the data model has changed three times, nobody remembers what the report is for, and the SQL is one nested CTE deep and still wrong. The right repair is to read it carefully, understand the question it answers, and rebuild it in the ORM — where it is reviewable, testable, and refactorable by the next person to touch it.

This challenge is the smallest possible exercise in that skill.

## The SQL

Below is a hand-written report. It runs against your `crunchwriter` schema as it stands after Week 4 — `authors`, `articles`, `categories`, `comments`, plus a `view_count` column on `articles`. Read it carefully. Run it in `psql crunchwriter`. Understand the shape of the answer.

```sql
WITH author_stats AS (
    SELECT
        a.id AS author_id,
        a.username,
        count(*) FILTER (WHERE art.status = 'published') AS published_count,
        coalesce(sum(art.view_count) FILTER (WHERE art.status = 'published'), 0) AS total_views,
        max(art.published_at) FILTER (WHERE art.status = 'published') AS latest_published_at,
        (
            SELECT count(*)
            FROM writer_article art2
            WHERE art2.author_id = a.id
              AND art2.status = 'published'
              AND art2.published_at >= now() - interval '30 days'
        ) AS recent_count
    FROM writer_author a
    LEFT JOIN writer_article art ON art.author_id = a.id
    GROUP BY a.id, a.username
),
ranked AS (
    SELECT
        author_id,
        username,
        published_count,
        total_views,
        latest_published_at,
        recent_count,
        rank() OVER (ORDER BY total_views DESC) AS views_rank,
        rank() OVER (ORDER BY recent_count DESC) AS recent_rank
    FROM author_stats
)
SELECT
    author_id,
    username,
    published_count,
    total_views,
    latest_published_at,
    recent_count,
    views_rank,
    recent_rank,
    CASE
        WHEN total_views >= 10000 THEN 'gold'
        WHEN total_views >= 1000  THEN 'silver'
        WHEN total_views >= 100   THEN 'bronze'
        ELSE 'unranked'
    END AS tier
FROM ranked
WHERE published_count >= 1
ORDER BY total_views DESC
LIMIT 50;
```

The report produces, for each author with at least one published article:

- `published_count` — total published articles.
- `total_views` — sum of `view_count` across published articles.
- `latest_published_at` — most recent published date.
- `recent_count` — published in the last 30 days.
- `views_rank` — rank by `total_views` across all authors.
- `recent_rank` — rank by `recent_count`.
- `tier` — a `gold` / `silver` / `bronze` / `unranked` bucket from `total_views`.

Sorted by `total_views DESC`, limited to 50.

## What you build

A **single queryset** that produces the same rows, in the same order. The queryset goes in `writer/managers.py` as a method on `AuthorQuerySet`:

```python
class AuthorQuerySet(models.QuerySet):
    def with_dashboard_stats(self):
        # build the annotated queryset here
        ...
```

Then the view:

```python
def top_authors(request):
    rows = Author.objects.with_dashboard_stats()[:50]
    return render(request, "writer/top_authors.html", {"rows": rows})
```

## Acceptance criteria

- [ ] `c16-week-05/challenges/01-orm.md` with: your queryset code, the emitted SQL (full, copied from `connection.queries`), the `EXPLAIN ANALYZE` plan, and a side-by-side diff vs the hand-written SQL.
- [ ] The queryset is **one chain**, no Python-side post-processing. (`Coalesce`, `Case`/`When`, `Subquery`, `Window` are all fair; `for row in ...` to compute a field is not.)
- [ ] Every column from the hand-written SQL appears in the queryset's `.values()` or as an annotation.
- [ ] Results match: a script that runs both queries and asserts the IDs are identical and the numeric columns are within rounding tolerance. Save this as `compare.py`.
- [ ] Differences in the emitted SQL are **listed and defended** in the write-up. "Mine has a `LEFT JOIN` where the original has a `Subquery`" is fine — explain why and what the plan-cost difference is.

## Suggested order of operations

### Phase 1 — Read the SQL (30 min)

1. Run the SQL in `psql crunchwriter`. Verify it returns rows.
2. For one specific row in the result, **trace** how each column was computed. Pick author with `username = 'author_42'` (or whichever has interesting numbers in your seed) and reproduce by hand:
   - Count published: `SELECT count(*) FROM writer_article WHERE author_id = X AND status = 'published';`
   - Total views: `SELECT sum(view_count) ...`
   - Recent count: `SELECT count(*) WHERE ... AND published_at >= now() - interval '30 days';`
3. Write a one-paragraph "what this report answers" in your own words, **before** opening the ORM.

### Phase 2 — Build the queryset piece by piece (90 min)

The order to add annotations:

1. `published_count` — `Subquery` of count with `filter`. (Refuse the `Count("articles", filter=...)` form here — it works, but the goal is to write SQL that mirrors the hand-written. Use the `Subquery` pattern.)
2. `total_views` — `Subquery` of `Sum`, wrapped in `Coalesce`.
3. `latest_published_at` — `Subquery` of `Max`.
4. `recent_count` — `Subquery` of `Count` filtered by date.
5. `views_rank` — `Window(Rank(), order_by=F("total_views").desc())`. **Note:** windows reference annotated columns; this is supported in Django 5.
6. `recent_rank` — `Window(Rank(), order_by=F("recent_count").desc())`.
7. `tier` — `Case`/`When` on `F("total_views")`.

Then filter `published_count__gte=1`, order by `total_views`, slice `[:50]`.

After each step, paste `str(qs.query)` into the write-up. The SQL grows incrementally; the final query should be close to the hand-written.

### Phase 3 — Compare emitted SQL (30 min)

`connection.queries[-1]["sql"]` gives you the final SQL. Paste it into the write-up alongside the original. List every difference. Common ones:

- Django will use `INNER JOIN` where the original uses `LEFT JOIN` — or vice versa.
- Django wraps the windowed query in a subquery for the `WHERE published_count__gte=1` filter (because windows are evaluated after `WHERE`, the ORM has to nest).
- Django includes every author column in the outer `SELECT`; the original is hand-narrowed.

For each difference, one sentence on whether it matters for the plan and the result.

### Phase 4 — Measure (30 min)

Run `EXPLAIN (ANALYZE, BUFFERS)` on both. Median of three runs each.

- Hand-written SQL: __ ms
- Your ORM queryset: __ ms

If yours is more than 2× slower, dig in. Often the cause is a missing index on `(author_id, status, published_at)` or `(author_id, view_count)`. Add it. Re-measure.

### Phase 5 — Write-up (30 min)

`c16-week-05/challenges/01-orm.md`. Sections:

1. **What the report answers** — one paragraph in plain English.
2. **The hand-written SQL** — pasted verbatim.
3. **The ORM queryset** — code block.
4. **Emitted SQL** — code block, from `connection.queries`.
5. **Diff** — bulleted list of differences, with one-sentence rationale each.
6. **Plans** — both `EXPLAIN ANALYZE` outputs, both medians.
7. **Verdict** — would you ship the ORM version? In what circumstance would you keep the raw SQL?

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Correctness | 30% | `compare.py` confirms identical IDs and matching numerics across all 50 rows |
| SQL closeness | 25% | The emitted SQL is structurally similar; differences are explained, not hand-waved |
| Plan honesty | 20% | Both plans pasted; the slower one is investigated, not glossed |
| Manager hygiene | 15% | The queryset is a clean method on `AuthorQuerySet`; the view is two lines |
| Write-up | 10% | Sections present; differences defensible |

## Hints

- **`Subquery` references annotated columns** — Django 5 supports `F("annotated_column")` inside a later `Window`, which is the only way the `Rank` annotations work. Older Django versions did not.
- **The `WHERE published_count >= 1` filter** in the original lives outside the CTE that defines `published_count`. In the ORM, `.filter(published_count__gte=1)` after the annotation results in Django wrapping the windowed query in a subquery — that is correct.
- **`Case` with `output_field`** — Django needs help inferring the type of `Value("gold")`; pass `output_field=CharField()` to the `Case` annotation.
- **`now() - interval '30 days'`** — in Python, `from django.utils import timezone; from datetime import timedelta; timezone.now() - timedelta(days=30)`. Pass the value to `OuterRef` or use `Now()` from `django.db.models.functions` for an in-DB version.
- **`Manager.from_queryset`** — once you have `AuthorQuerySet` with `with_dashboard_stats`, the assignment `objects = AuthorQuerySet.as_manager()` on the model is enough.

## Stretch (optional)

- Re-implement the report as `Author.objects.raw(...)` with the original hand-written SQL. Compare the API ergonomics — what is harder, what is easier? Which would you ship in a real codebase?
- Add a unit test that runs the ORM queryset against a small fixture (10 authors, 50 articles) and asserts the result rows by hand. The test is a regression safety-net for the day someone refactors the manager.
- Wire the queryset into `django-debug-toolbar` and confirm the SQL panel shows **one** query for the entire report. If the toolbar shows two, the chain is wrong.
