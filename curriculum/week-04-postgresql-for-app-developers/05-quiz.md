# Week 4 — Quiz

Ten questions. Lectures closed.

---

**Q1.** A B-tree index on `articles(slug)` will accelerate which of the following?

- A) `WHERE slug LIKE '%intro%'`
- B) `WHERE slug LIKE 'intro%'`
- C) `WHERE lower(slug) = 'intro-to-postgres'`
- D) `WHERE slug ILIKE 'intro%'`

---

**Q2.** A **partial** index on `articles(published_at DESC) WHERE status = 'published'` can be used by which query?

- A) `SELECT * FROM articles ORDER BY published_at DESC LIMIT 10;`
- B) `SELECT * FROM articles WHERE status = 'draft' ORDER BY published_at DESC LIMIT 10;`
- C) `SELECT * FROM articles WHERE status = 'published' ORDER BY published_at DESC LIMIT 10;`
- D) `SELECT * FROM articles WHERE status IN ('published','review') ORDER BY published_at DESC LIMIT 10;`

---

**Q3.** In an `EXPLAIN ANALYZE` plan, what is the difference between `(cost=0..1000 rows=10)` and `(actual time=0..50 rows=10000 loops=1)`?

- A) Cost is in milliseconds; actual time is in seconds.
- B) Cost is the planner's estimate (arbitrary units, rows estimated); actual is what really happened when the query ran.
- C) Cost is the upper bound; actual is the lower bound.
- D) They are the same numbers in different formats.

---

**Q4.** A query has `(estimated rows=10) (actual rows=200000)` on a node that is the inner side of a Nested Loop. What is the **most likely** root cause?

- A) The query is fundamentally too expensive — add a `LIMIT`.
- B) Statistics are stale or the planner is missing correlation info; `ANALYZE` or `CREATE STATISTICS`.
- C) Postgres needs more RAM.
- D) Replace the Nested Loop with `SET enable_nestloop = off` permanently.

---

**Q5.** Which Postgres isolation level does **not** exist as a distinct level (the request is silently upgraded)?

- A) `READ COMMITTED`
- B) `READ UNCOMMITTED`
- C) `REPEATABLE READ`
- D) `SERIALIZABLE`

---

**Q6.** Inside a `REPEATABLE READ` transaction, two `SELECT`s of the same row will:

- A) Always return the same values, even if another transaction committed an update in between.
- B) Always return the latest values.
- C) Return the same values, but only if no other transaction is running.
- D) Raise an error.

---

**Q7.** For a JSONB column where the only filter ever used is `meta @> '{...}'`, which GIN variant is the right default?

- A) `gin_trgm_ops`
- B) The default `gin` operator class
- C) `jsonb_path_ops` — smaller and faster for `@>`-only workloads
- D) A B-tree on the whole `meta` column

---

**Q8.** A `tsvector` column is most useful when:

- A) It is computed on every query via `to_tsvector(...)`.
- B) It is stored as a `STORED` generated column and indexed with GIN.
- C) It is stored in JSON and indexed.
- D) It replaces the body column entirely.

---

**Q9.** In production, you find an index with `idx_scan = 0` after a month of traffic. What does this tell you, and what would you do?

- A) The index is dead weight — every write pays for it, no read uses it. Consider dropping after one more month's confirmation.
- B) The index is critical and is being skipped due to a bug.
- C) The index is being used internally by autovacuum; leave it alone.
- D) The metric is unreliable; ignore it.

---

**Q10.** Which command should you wrap a destructive `EXPLAIN ANALYZE DELETE ...` in to avoid permanent change?

- A) `SET local enable_destructive = off`
- B) `EXPLAIN (ANALYZE, DRYRUN)`
- C) `BEGIN; EXPLAIN ANALYZE DELETE ...; ROLLBACK;`
- D) `EXPLAIN ANALYZE` does not run destructive statements; only `SELECT`.

---

## Answer key

<details>
<summary>Reveal</summary>

1. **B** — B-tree supports prefix `LIKE` only when the leading characters are literal. `%intro%`, `ILIKE`, and `lower(slug) = ...` all defeat the B-tree on `slug`.
2. **C** — Partial indexes are usable when the query's predicate matches (or implies) the index's predicate. Option D is **sometimes** usable depending on planner reasoning, but C is the unambiguous correct answer.
3. **B** — Cost is the planner's relative estimate; actual is the real measurement.
4. **B** — A 10× estimate-vs-actual mismatch points at statistics. The fix is upstream of the plan: `ANALYZE` or extended statistics.
5. **B** — Postgres silently upgrades `READ UNCOMMITTED` to `READ COMMITTED`. The four real levels are READ COMMITTED, REPEATABLE READ, and SERIALIZABLE — plus the upgraded UNCOMMITTED.
6. **A** — REPEATABLE READ snapshots at transaction start; two reads of the same row see the same values regardless of other transactions' commits.
7. **C** — `jsonb_path_ops` supports `@>` only and is significantly smaller than the default GIN; it is the right default when `@>` is the only operator.
8. **B** — Generated `STORED` + GIN is the canonical setup for full-text search; computing per-query is wasted work.
9. **A** — Unused indexes are pure write-tax. Verify (use enough of the production query mix; look at it for at least a month), then drop.
10. **C** — `EXPLAIN ANALYZE` runs the query. Wrap destructive statements in a transaction with `ROLLBACK`.

</details>

If 9+: ship the homework. 7-8: re-read the relevant lecture. <7: re-read Lectures 1 and 2 from the top, then come back to this quiz before homework.
