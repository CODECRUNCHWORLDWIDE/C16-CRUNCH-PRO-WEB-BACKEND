# Challenge 1 — JSONB vs real columns

**Time:** ~3 hours. **Difficulty:** Medium. **Goal:** Run the same workload against two schemas — one that stores attributes in JSONB, one that stores them as real columns — and produce a measurements-backed write-up on when each earns its keep.

## Why this exists

Every team eventually has the JSONB conversation. One engineer wants flexibility: "we'll just store it in a `meta` JSONB column and reshape it later." Another wants discipline: "if we know the field, model it." Both have a point. The way to settle it is not by reading another blog post; it is by running the workload on your own machine and reading the numbers.

This challenge is the smallest possible setup that produces honest numbers.

## The setup

In a new database `crunchbench`, you will:

1. Create **two tables** with the same logical content.
2. Load **500 000 rows** into each.
3. Run **four representative queries** against each.
4. Measure: rows scanned, plan shape, execution time, index size, write throughput.
5. Write a 600–800-word recommendation on which schema you would ship for this workload.

### Table A — real columns

```sql
CREATE TABLE articles_a (
    id            bigserial PRIMARY KEY,
    title         varchar(200) NOT NULL,
    author_id     bigint NOT NULL,
    status        varchar(20) NOT NULL,
    is_featured   boolean NOT NULL DEFAULT false,
    word_count    integer NOT NULL,
    language      varchar(10) NOT NULL DEFAULT 'en',
    published_at  timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
```

### Table B — JSONB

```sql
CREATE TABLE articles_b (
    id           bigserial PRIMARY KEY,
    title        varchar(200) NOT NULL,
    author_id    bigint NOT NULL,
    meta         jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);
```

Where `meta` looks like:

```json
{
  "status": "published",
  "is_featured": true,
  "word_count": 1234,
  "language": "en",
  "published_at": "2026-02-14T09:30:00Z"
}
```

Same data, different shape.

## Load the data (30 min)

Write `seed_bench.py` (Python stdlib only). Generate 500 000 rows of plausible synthetic data, write two `.csv` files, `\copy` each.

Distribution targets:

- `status`: 75% draft / 15% published / 5% review / 5% archived
- `is_featured`: 2% true / 98% false
- `language`: 90% en / 5% fr / 5% es
- `word_count`: log-normal, median ~800
- `author_id`: uniform over 5 000 authors
- `published_at`: NULL for non-published; otherwise within 2024–2026

Use `random.seed(42)` so reruns are reproducible. Use `random.choices(..., weights=[...])` rather than nested `if`s — it's clearer.

For Table B, emit a JSONB literal per row; `\copy` can load it directly.

`ANALYZE articles_a; ANALYZE articles_b;` once loaded.

## Queries to compare (45 min)

Run each query with `EXPLAIN (ANALYZE, BUFFERS)`. Run each three times; record the **median** of the three.

### Q1 — Exact match on a known field

```sql
-- A
SELECT count(*) FROM articles_a WHERE status = 'published' AND is_featured = true;
-- B
SELECT count(*) FROM articles_b WHERE meta @> '{"status":"published","is_featured":true}';
```

### Q2 — Range on a numeric field

```sql
-- A
SELECT count(*) FROM articles_a WHERE word_count > 2000;
-- B
SELECT count(*) FROM articles_b WHERE (meta->>'word_count')::int > 2000;
```

### Q3 — Order by + LIMIT

```sql
-- A
SELECT id, title FROM articles_a WHERE status = 'published' ORDER BY published_at DESC LIMIT 20;
-- B
SELECT id, title FROM articles_b
WHERE meta->>'status' = 'published'
ORDER BY (meta->>'published_at')::timestamptz DESC
LIMIT 20;
```

### Q4 — A new attribute that didn't exist when the schema was designed

Imagine the product team adds `editor_tier` — `"premium"` for a small fraction. For Table A, this would be an `ALTER TABLE ADD COLUMN`. For Table B, you can just put it in `meta`.

```sql
-- Add to existing rows:
UPDATE articles_b SET meta = meta || '{"editor_tier":"premium"}' WHERE id % 50 = 0;

-- Query it:
SELECT count(*) FROM articles_b WHERE meta @> '{"editor_tier":"premium"}';
```

For Table A, you would need a migration. Record the cost of an `ALTER TABLE` on 500 000 rows — even an `ADD COLUMN` with a non-volatile default is fast in Postgres 16, but a backfill is not.

```sql
-- For comparison:
\timing on
ALTER TABLE articles_a ADD COLUMN editor_tier varchar(20);
UPDATE articles_a SET editor_tier = 'premium' WHERE id % 50 = 0;
CREATE INDEX articles_a_editor_idx ON articles_a (editor_tier) WHERE editor_tier IS NOT NULL;
```

## Indexes — add the right ones to each (30 min)

For Table A:

```sql
CREATE INDEX articles_a_status_pub_idx
  ON articles_a (published_at DESC) WHERE status = 'published';
CREATE INDEX articles_a_status_featured_idx
  ON articles_a (status) WHERE is_featured;
CREATE INDEX articles_a_wordcount_idx ON articles_a (word_count);
```

For Table B, the natural choices:

```sql
CREATE INDEX articles_b_meta_gin ON articles_b USING gin (meta jsonb_path_ops);
-- ... and, for Q2, an expression index since the (meta->>'word_count') cast cannot use the GIN:
CREATE INDEX articles_b_wordcount_expr ON articles_b (((meta->>'word_count')::int));
```

Record the size of each index:

```sql
SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid))
FROM pg_stat_user_indexes
WHERE relname IN ('articles_a', 'articles_b')
ORDER BY relname, indexrelname;
```

## Write throughput (30 min)

Build a small loop that inserts 10 000 rows into each table, measure wall-clock time:

```python
import psycopg, time
with psycopg.connect("dbname=crunchbench") as conn:
    with conn.cursor() as cur:
        start = time.perf_counter()
        for i in range(10_000):
            cur.execute(
                "INSERT INTO articles_a (title, author_id, status, is_featured, word_count, language, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, now())",
                (f"row {i}", 1, "draft", False, 800, "en"),
            )
        conn.commit()
        print("A:", time.perf_counter() - start)

        start = time.perf_counter()
        for i in range(10_000):
            cur.execute(
                "INSERT INTO articles_b (title, author_id, meta) VALUES (%s, %s, %s::jsonb)",
                (f"row {i}", 1, '{"status":"draft","is_featured":false,"word_count":800,"language":"en"}'),
            )
        conn.commit()
        print("B:", time.perf_counter() - start)
```

This is not a benchmark (one client, autocommit-ish, single core) but it surfaces the gap. Record both numbers.

## The write-up (45 min)

`challenges/01-jsonb-vs-columns.md`, 600–800 words. Sections:

1. **The numbers.** A markdown table with one row per query, columns: A time, A plan shape, B time, B plan shape, winner. Plus a second table for index sizes and insert throughput.
2. **Where JSONB won.** Q4 — the new attribute — almost certainly favoured B. Quantify how much. Was the win in development time, or in production query performance, or both?
3. **Where real columns won.** Q1–Q3 — quantify the gap. Pay particular attention to Q2: did the expression index close the gap, or did B remain slower?
4. **The honest recommendation.** For *this workload* (mostly known fields, occasional new attribute), which schema would you ship? Argue from the numbers, not from taste.
5. **A workload that would flip the answer.** Describe a workload (real-world or hypothetical) where the recommendation would be the opposite. Be specific — "audit logs with arbitrary payloads" is more useful than "flexible data."

## Acceptance criteria

- [ ] Both tables populated with 500 000 rows, statistics fresh.
- [ ] Four queries × two tables × three runs = 24 `EXPLAIN ANALYZE` runs; medians recorded.
- [ ] Index sizes and write-throughput numbers captured.
- [ ] 600–800-word write-up in `challenges/01-jsonb-vs-columns.md` with the five sections above.
- [ ] The recommendation is defended with numbers, not aesthetics.
- [ ] All SQL scripts (`seed_bench.py`, `bench.sql`) checked in.

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Reproducibility | 25% | Anyone can re-run the experiment from your repo and get the same medians ±10% |
| Measurement honesty | 25% | Three runs, median reported, cache state acknowledged |
| Plan reading | 20% | Each query's bottleneck named, not just timed |
| Recommendation | 20% | A decision, with conditions; not a hedge |
| Counter-case | 10% | The workload that flips the answer is specific and credible |

## Hints

- **`jsonb_path_ops` vs default `gin`** — the default supports `@>`, `?`, `?|`, `?&`; `jsonb_path_ops` supports only `@>`. For this challenge `@>` is enough; use `jsonb_path_ops` and note the size win.
- **Casts defeat indexes** — `(meta->>'word_count')::int` cannot use the GIN on `meta`; that's why the expression index in Q2 is needed.
- **`pg_size_pretty` lies a little for small relations** — pages are 8 kB; an "8 kB" index might be 1 page or 0 pages of real data. Use `pg_relation_size` (bytes) for the smallest indexes.
- **`VACUUM ANALYZE` between sections** — after the bulk `UPDATE` in Q4, statistics are stale. `ANALYZE articles_b;` before re-running.

## Stretch (optional)

- Add a third table `articles_c` that uses Postgres 16's `jsonb_path_query` for one of the queries. Does the `@?` operator change the plan?
- Add a partial **JSONB-expression index** for `WHERE (meta->>'is_featured')::boolean = true` and re-time Q1. Does it beat the GIN?
- Run the benchmark on a `_unlogged_` version of both tables (`CREATE UNLOGGED TABLE`). Insert throughput should rise sharply for both; the JSONB gap should narrow but not close.
