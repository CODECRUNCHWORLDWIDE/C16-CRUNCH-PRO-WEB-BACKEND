# Exercise 1 — Create and populate

**Time:** ~2 hours. **Goal:** Build a non-trivial schema in raw SQL, load 100 000 rows with `\copy`, and confirm the planner is now ready to make interesting decisions.

You do this in `psql` only. No Django, no ORM, no `manage.py`. The point is to feel the database as a database.

## Setup

```bash
createdb crunchlab
psql crunchlab
```

Inside `psql`, turn timing on for the session:

```sql
\timing on
```

## Part A — The schema (30 min)

In `psql`, create three tables: `authors`, `categories`, `articles`. The shape should match Lecture 1, with these requirements:

- `authors`:
  - `id bigserial PRIMARY KEY`
  - `username varchar(150) NOT NULL UNIQUE`
  - `email varchar(254) NOT NULL UNIQUE`
  - `is_staff boolean NOT NULL DEFAULT false`
  - `created_at timestamptz NOT NULL DEFAULT now()`
- `categories`:
  - `id bigserial PRIMARY KEY`
  - `slug varchar(80) NOT NULL UNIQUE`
  - `name varchar(120) NOT NULL`
- `articles`:
  - `id bigserial PRIMARY KEY`
  - `author_id bigint NOT NULL REFERENCES authors(id) ON DELETE RESTRICT`
  - `category_id bigint REFERENCES categories(id) ON DELETE SET NULL`
  - `title varchar(200) NOT NULL`
  - `slug varchar(200) NOT NULL UNIQUE`
  - `body text NOT NULL`
  - `status varchar(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','review','published','archived'))`
  - `published_at timestamptz`
  - `created_at timestamptz NOT NULL DEFAULT now()`
  - One CHECK: `status <> 'published' OR published_at IS NOT NULL`

Save the DDL to `exercises/01-schema.sql` in your portfolio repo. Run it from `psql` with `\i 01-schema.sql`.

Verify with `\d authors`, `\d categories`, `\d articles`. Every column, every constraint, every foreign key should be where you expect.

**Acceptance:** `\dt` shows three tables. `\d articles` shows the three foreign keys and two CHECK constraints.

## Part B — Generate seed data (30 min)

You will load:

- 1 000 `authors`
- 20 `categories`
- 100 000 `articles`

Write a tiny Python script (`seed.py`) that emits three CSV files (`authors.csv`, `categories.csv`, `articles.csv`). Use the standard library only — no Faker, no Django.

```python
# seed.py
import csv, random, datetime as dt
from pathlib import Path

random.seed(42)

OUT = Path("seed")
OUT.mkdir(exist_ok=True)

# authors
with (OUT / "authors.csv").open("w") as f:
    w = csv.writer(f)
    w.writerow(["username", "email", "is_staff"])
    for i in range(1, 1001):
        w.writerow([f"author_{i}", f"author_{i}@example.com", "true" if i <= 5 else "false"])

# categories
TOPICS = ["python","postgres","django","fastapi","async","testing","sql","ci","docker","linux",
          "vim","git","nginx","redis","celery","oauth","jwt","react","typescript","kubernetes"]
with (OUT / "categories.csv").open("w") as f:
    w = csv.writer(f)
    w.writerow(["slug", "name"])
    for slug in TOPICS:
        w.writerow([slug, slug.title()])

# articles
STATUS_WEIGHTS = [("draft", 75), ("review", 5), ("published", 15), ("archived", 5)]
statuses = [s for s, n in STATUS_WEIGHTS for _ in range(n)]

with (OUT / "articles.csv").open("w") as f:
    w = csv.writer(f)
    w.writerow(["author_id", "category_id", "title", "slug", "body", "status", "published_at", "created_at"])
    base = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    for i in range(1, 100_001):
        status = random.choice(statuses)
        created = base + dt.timedelta(minutes=random.randint(0, 60 * 24 * 500))
        published = (created + dt.timedelta(hours=random.randint(1, 72))) if status == "published" else ""
        w.writerow([
            random.randint(1, 1000),
            random.randint(1, 20),
            f"Article number {i}",
            f"article-{i}",
            "Lorem ipsum " * random.randint(40, 200),
            status,
            published.isoformat() if published else "",
            created.isoformat(),
        ])
```

Run it:

```bash
python seed.py
ls seed/
# authors.csv  categories.csv  articles.csv
wc -l seed/articles.csv
# 100001 seed/articles.csv  (1 header + 100000 rows)
```

**Acceptance:** Three CSV files exist; `articles.csv` has 100 001 lines.

## Part C — `\copy` the data (15 min)

In `psql`:

```sql
\copy authors (username, email, is_staff) FROM 'seed/authors.csv' CSV HEADER;
\copy categories (slug, name)            FROM 'seed/categories.csv' CSV HEADER;
\copy articles  (author_id, category_id, title, slug, body, status, published_at, created_at)
                                          FROM 'seed/articles.csv' CSV HEADER NULL '';
```

Note the `NULL ''` on the third command — empty cells become SQL `NULL` (used for `published_at` on non-published rows).

Check:

```sql
SELECT count(*) FROM authors;     -- 1000
SELECT count(*) FROM categories;  -- 20
SELECT count(*) FROM articles;    -- 100000
```

Each `\copy` should take well under one second. `\copy` is bulk-bound; the bottleneck is your disk, not the network or the SQL parser.

**Acceptance:** Three row counts match: 1000, 20, 100000.

## Part D — `ANALYZE` and look at the stats (15 min)

```sql
ANALYZE;
```

`ANALYZE` re-collects table statistics so the planner has fresh numbers to work with. Autovacuum will eventually do this for you; right after a bulk load you do it yourself.

Look at what the planner now sees:

```sql
SELECT attname, n_distinct, most_common_vals, most_common_freqs
FROM pg_stats
WHERE tablename = 'articles' AND attname IN ('status', 'author_id', 'category_id');
```

You should see:

- `status` — `n_distinct ≈ 4`, `most_common_vals = {draft, published, archived, review}`, frequencies roughly matching the 75/15/5/5 split.
- `author_id` — `n_distinct ≈ 1000`, no single MCV dominates.
- `category_id` — `n_distinct = 20`, frequencies roughly uniform.

Write the three rows to `exercises/01-stats.md` in your portfolio repo. These statistics are what the planner uses to decide whether a Seq Scan or an Index Scan is cheaper.

**Acceptance:** `01-stats.md` exists with the three rows from `pg_stats` quoted verbatim.

## Part E — Indexes that are obviously right (15 min)

Two indexes are obviously right; you'll add a third one in Exercise 3 once you've earned it.

```sql
-- Foreign-key columns get a B-tree (Django would add these automatically).
CREATE INDEX articles_author_id_idx   ON articles (author_id);
CREATE INDEX articles_category_id_idx ON articles (category_id);
```

Verify:

```sql
\di articles*
```

You should see five indexes: the two foreign-key ones you just made, plus `articles_pkey` (the primary key) and `articles_slug_key` (the unique constraint on slug). The CHECK constraints don't create indexes.

**Acceptance:** Five indexes on `articles`.

## Part F — Smoke-test the planner (15 min)

Confirm the planner uses the indexes:

```sql
EXPLAIN SELECT * FROM articles WHERE author_id = 42;
EXPLAIN SELECT * FROM articles WHERE id = 42;
EXPLAIN SELECT * FROM articles WHERE slug = 'article-42';
```

Each plan should mention an `Index Scan`. If a plan picks `Seq Scan`, the planner thinks the table is too small — at 100 k rows, that should not happen for these queries. If it does, you forgot to `ANALYZE`.

Write the three plans to `exercises/01-plans.md`.

**Acceptance:** Three Index Scans recorded.

## Stretch

- Add a `comments` table (`id`, `article_id REFERENCES articles ON DELETE CASCADE`, `author_id`, `body`, `created_at`). Load 500 000 comments. The 500 k comments + 100 k articles mix is what the rest of the week uses.
- Add a `tags text[]` column to `articles` and `\copy` a comma-separated tag list per article. Build a GIN index on it. `EXPLAIN SELECT count(*) FROM articles WHERE tags @> ARRAY['python'];` — Index Scan or Bitmap Index Scan, never Seq Scan.
- Use `EXPLAIN (ANALYZE, BUFFERS)` on one of Part F's queries. Note `shared hit` vs `shared read`. Run the same query again — the second run should be all `hit` (warm cache). Note both numbers in `01-plans.md`.

## Acceptance summary

- [ ] `01-schema.sql` runs cleanly against a fresh `crunchlab`.
- [ ] 1000 authors, 20 categories, 100 000 articles loaded.
- [ ] `ANALYZE` run; `pg_stats` examined.
- [ ] Two foreign-key indexes added (plus the two automatic indexes from PK + UNIQUE).
- [ ] Three smoke-test plans show Index Scans.
- [ ] All artefacts checked in: `01-schema.sql`, `01-stats.md`, `01-plans.md`.

When this is green, you have the dataset Exercises 2 and 3 need.
