# Exercise 2 — `EXPLAIN` a slow query

**Time:** ~2.5 hours. **Goal:** Read three real plans against the 100 k-row dataset, identify the slowest node in each, name the cause, and write the fix you would apply — *before* you actually apply it.

This exercise is reading practice. You will not modify any indexes; you will only run `EXPLAIN ANALYZE` and write down what you see. Exercise 3 is where you fix.

## Setup

Use the `crunchlab` database from Exercise 1. Confirm the dataset:

```sql
SELECT count(*) FROM articles;    -- 100000
SELECT count(*) FROM authors;     -- 1000
```

Turn timing on if it isn't already:

```sql
\timing on
```

## Query A — The public homepage (45 min)

The `crunchwriter` homepage runs roughly this query — the published list, newest first, paginated 20.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT a.id, a.title, a.slug, a.published_at, u.username
FROM articles a
JOIN authors u ON a.author_id = u.id
WHERE a.status = 'published'
ORDER BY a.published_at DESC NULLS LAST
LIMIT 20;
```

Run it. Copy the plan into `exercises/02-query-a.md`.

Answer in that file:

1. **What scan type did the planner pick on `articles`?** (Seq Scan? Index Scan? Bitmap Heap Scan?)
2. **How many rows did the `articles` scan actually return** before `LIMIT` cut it off?
3. **Where did the time go?** Point at one or two nodes that account for the majority of `Execution Time`.
4. **Estimate vs actual** for the `articles` node — are they within 2×, or off by 10×+?
5. **What would you change** to make this faster, and **why?** One sentence. Do not change it yet.

Hints in spoiler form — try without them first.

<details>
<summary>Hint 1</summary>

There is no index on `status`. There is no index on `published_at`. The planner has to choose between a Seq Scan + Sort + Limit, or perhaps a Bitmap heap scan on an auxiliary index it doesn't really have. Look for whether the plan reads the full table.

</details>

<details>
<summary>Hint 2</summary>

`status = 'published'` matches roughly 15% of rows (15 000 out of 100 000) per the `pg_stats` you collected in Exercise 1. The planner knows this. With `LIMIT 20`, would it want to scan only the published rows in published_at order, or scan and sort everything? Which does it actually do?

</details>

**Acceptance:** `02-query-a.md` contains the plan, the five answers, and one sentence proposing the fix.

## Query B — A profile page (45 min)

A user's profile page lists their last 10 articles regardless of status (drafts plus published — it's the author's own page).

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, title, status, created_at
FROM articles
WHERE author_id = 42
ORDER BY created_at DESC
LIMIT 10;
```

Run it. Copy the plan into `exercises/02-query-b.md`.

This query *does* have a useful index — `articles_author_id_idx` from Exercise 1. The planner will use it. Your questions:

1. **What scan type?**
2. **How many rows for `author_id = 42`** — actual?
3. **Is there a separate Sort node** above the scan? Why or why not?
4. **What would make this query faster still?** Think about a multicolumn index. Would `(author_id, created_at DESC)` help? Explain in 2-3 sentences.

<details>
<summary>Hint</summary>

The single-column index on `author_id` returns matching rows in **index order** (by author_id, ties broken arbitrarily), not by `created_at`. So the planner has to sort. A multicolumn index on `(author_id, created_at DESC)` would return the right author's rows already in the right order — the Sort node disappears, the LIMIT can stop early. The cost: an extra index to maintain on every write.

</details>

**Acceptance:** `02-query-b.md` contains the plan, the four answers, and a paragraph on the multicolumn-index tradeoff.

## Query C — A counts page (45 min)

The dashboard's sidebar shows the number of articles in each status, for the current user.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT status, count(*) AS n
FROM articles
WHERE author_id = 42
GROUP BY status;
```

Run it. Copy the plan into `exercises/02-query-c.md`.

Questions:

1. **What scan type?**
2. **How many rows scanned?**
3. **Was there a GroupAggregate or HashAggregate?**
4. **Is this query a candidate for an index at all?** Or is it doing roughly the right thing given the data shape? Defend your answer in 3-4 sentences. Hint: with `n_distinct = 4` for status and on the order of 100 rows per author, the work is small; the planner is doing fine.
5. **If this query were to run a million times a day**, would you bother with an index? What would you do instead?

<details>
<summary>Hint</summary>

The right answer to question 4 is probably "leave it alone." The query reads ~100 rows for the author via the existing index and aggregates four buckets in memory. There is no index that materially beats that. The right answer to question 5 is a counter table — `INSERT/UPDATE` on a `(author_id, status, n)` row in a trigger, then your sidebar reads one row instead of running an aggregate.

</details>

**Acceptance:** `02-query-c.md` with the plan, the five answers, and your reasoning.

## Part D — Reflection (15 min)

In `exercises/02-reflection.md`, ~250 words:

1. Across the three queries, **which had the most surprising plan**? Why?
2. Which of the four "shapes of slow" from Lecture 2 did Query A fall into?
3. You ran `EXPLAIN (ANALYZE, BUFFERS)` on each query twice. Did the second run hit fewer pages? What does that tell you about cache vs index choice?
4. The Django ORM emits roughly these three queries. Which one would you flag in a code review, even before profiling?

## Stretch

- Re-run Query A with `SET enable_seqscan = off;` first. Did the planner pick a different plan? Was it faster or slower? `SET` only affects the session; reset with `RESET enable_seqscan;`.
- Run Query A inside `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` and paste the JSON into [explain.dalibo.com](https://explain.dalibo.com/). Screenshot the tree view, add it to `02-query-a.md`.
- Run all three queries under `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)` — `SETTINGS` adds the non-default planner GUCs in effect. If you have a fresh install, the list will be tiny; that is expected.

## Acceptance summary

- [ ] `02-query-a.md`, `02-query-b.md`, `02-query-c.md` with plan + answers each.
- [ ] `02-reflection.md` with the four reflection questions.
- [ ] You **did not** add any indexes — that's Exercise 3.

The fix is one CREATE INDEX away; resist applying it until the next exercise. The point of this one is to **see clearly** before you act.
