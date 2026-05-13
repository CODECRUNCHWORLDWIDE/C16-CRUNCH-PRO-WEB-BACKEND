# Exercise 3 — Add an index, measure the win

**Time:** ~2.5 hours. **Goal:** Add the index your Exercise 2 plan proposed, re-run `EXPLAIN ANALYZE`, and write the before/after side-by-side. By the end you can defend each index you ship.

The job is not "make the number smaller." The job is "make the right plan happen, and explain why."

## Setup

Use `crunchlab` from Exercises 1 and 2. The dataset is unchanged.

## Part A — Fix Query A: the public homepage (60 min)

In Exercise 2, Query A scanned the full 100 000-row `articles` table to find 15 000 published rows, sorted them by `published_at`, and took the top 20. The plan was a Seq Scan + Sort + Limit (or a Bitmap Heap Scan if you had any auxiliary index, but you didn't).

The right fix: a **partial index** covering only published rows, ordered by `published_at DESC`.

```sql
CREATE INDEX articles_published_idx
ON articles (published_at DESC)
WHERE status = 'published';
```

Why partial?

- 85% of rows are not published. Indexing them wastes space and write cycles.
- The query always filters on `status = 'published'`. The planner uses the partial index when the query's `WHERE` matches (or implies) the index's predicate.

Add the index. Note how long the build took (`\timing` is on). On 100 k rows it should be under 200 ms.

Then re-run Query A:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT a.id, a.title, a.slug, a.published_at, u.username
FROM articles a
JOIN authors u ON a.author_id = u.id
WHERE a.status = 'published'
ORDER BY a.published_at DESC NULLS LAST
LIMIT 20;
```

Confirm:

1. The `articles` node is now an `Index Scan` (or `Index Scan Backward`) using `articles_published_idx`.
2. There is no separate `Sort` node — the index produces rows in order.
3. The `Execution Time` dropped substantially. Note the before/after times.

Write to `exercises/03-query-a.md`:

- The plan before (copy from Exercise 2's `02-query-a.md`).
- The plan after.
- The two execution times, side by side.
- A 4-sentence explanation of why the partial index won.

**Acceptance:** `03-query-a.md` shows before/after plans and a measurable improvement (typically 10×–100× faster).

## Part B — Fix Query B: the profile page (45 min)

Query B was already using `articles_author_id_idx`, but it had a separate Sort node. The fix: a **multicolumn index** on `(author_id, created_at DESC)`.

Before adding, ask yourself: does the existing single-column index on `author_id` still earn its keep? In most cases, no — the multicolumn index covers everything the single-column did, plus the sort. We will drop the redundant one.

```sql
CREATE INDEX articles_author_created_idx ON articles (author_id, created_at DESC);
DROP INDEX articles_author_id_idx;
```

Re-run Query B:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, title, status, created_at
FROM articles
WHERE author_id = 42
ORDER BY created_at DESC
LIMIT 10;
```

Confirm:

1. The plan uses `articles_author_created_idx`.
2. There is no separate `Sort` node.
3. `Rows: 10` from the index scan (early exit thanks to `LIMIT 10` aligning with the index order).

Write to `exercises/03-query-b.md`:

- The plan before (from `02-query-b.md`).
- The plan after.
- Times before/after.
- A paragraph (~6 sentences) on **whether dropping the single-column index was the right call**, and what query pattern would change that answer (hint: queries that filter on `author_id` but **order by something other than `created_at`** still benefit from a single-column index — but in this app, do any?).

**Acceptance:** `03-query-b.md` shows the change, the measurement, and the reasoning on the drop.

## Part C — Leave Query C alone (15 min)

In Exercise 2 you argued that Query C (the per-status counts) did not warrant an index. Do nothing.

Re-run Query C anyway (so it is using whatever index changes you made in Part B):

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT status, count(*) AS n
FROM articles
WHERE author_id = 42
GROUP BY status;
```

It should now use `articles_author_created_idx` (the new multicolumn) for the `author_id = 42` lookup. Note the time — it should be a small change from Exercise 2's reading.

Write to `exercises/03-query-c.md`:

- The plan after (Part B's index change is in effect).
- One sentence: did the new index help Query C, hurt it, or do nothing measurable? Was that the prediction?

**Acceptance:** `03-query-c.md` exists; your prediction matched (or you noted the surprise).

## Part D — `pg_stat_user_indexes` (15 min)

After running each query a handful of times, look at the actual index usage:

```sql
SELECT relname, indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE relname = 'articles'
ORDER BY idx_scan DESC;
```

This is the canonical view for "is this index being used at all?" In production, indexes with `idx_scan = 0` for weeks are candidates to drop.

Write the table to `exercises/03-index-usage.md`. The new indexes should have non-zero `idx_scan`; the unused ones (`articles_slug_key`, etc.) may show low counts because you haven't queried by slug.

**Acceptance:** `03-index-usage.md` with the table and a 2-sentence note on what `idx_scan = 0` would mean in production.

## Part E — Reflection (15 min)

`exercises/03-reflection.md`, ~250 words:

1. **What is the smallest credible win** an index has to deliver before you ship it? (Time? Plan shape? Both?)
2. **You dropped an index in Part B.** Have you ever seen a code review where dropping an index was the suggestion? Why is the "remove" direction so rarely proposed?
3. **The partial index in Part A** has a sharp edge: if the predicate of the index does not match the query's predicate, the planner cannot use it. Describe a query that *looks* close to Query A but cannot use `articles_published_idx`.
4. Across Exercises 1-3, **how many `EXPLAIN ANALYZE` runs did you do**? Why was that worth doing instead of going straight to `CREATE INDEX`?

## Stretch

- Try the same fix with `CREATE INDEX CONCURRENTLY` (drop the index first to re-run). Note the wall-clock time difference. `CONCURRENTLY` cannot run inside a transaction, so you cannot wrap it in `BEGIN; ... ROLLBACK;` — be deliberate.
- Add a **GIN index on a generated `tsvector`** column from Lecture 3 over `articles.title || ' ' || articles.body`. Write a `to_tsquery`-based search query. Measure: how does it compare to `WHERE title ILIKE '%postgres%'` with no index? With a `pg_trgm` index?
- Without consulting Exercise 2, write the index command for a query you have not seen yet:

```sql
SELECT * FROM articles
WHERE category_id = 5 AND status = 'published'
ORDER BY published_at DESC
LIMIT 20;
```

Defend your answer in `03-stretch.md`. Then build it and measure.

## Acceptance summary

- [ ] `articles_published_idx` partial index added; Query A is 10×+ faster.
- [ ] `articles_author_created_idx` multicolumn index added; `articles_author_id_idx` dropped.
- [ ] Query B's plan no longer has a separate Sort.
- [ ] Query C left alone; reality matched prediction.
- [ ] `03-query-a.md`, `03-query-b.md`, `03-query-c.md`, `03-index-usage.md`, `03-reflection.md` all checked in.
- [ ] Each artefact has both a plan and a sentence of reasoning. Plans without reasoning are not deliverables.

This is the loop you will run in production for the rest of your career: profile, propose, apply, measure, defend. Get used to it.
