# Week 6 — Homework

Six problems, ~6h. Build them in your `crunchwriter` repo under `c16-week-06/homework/`.

All problems run against `crunchwriter` on PostgreSQL 16, with Redis 7 and Celery 5.4 wired up. If any of that is missing, run Exercises 1–3 first.

---

## Problem 1 — A rename without downtime (60 min)

**File:** `c16-week-06/homework/01-rename.md`.

Pick a field on one of your `crunchwriter` models that you have always wanted to rename. (Common candidates: `name` → `title` on `Article`, `body` → `content`, `created` → `created_at`.)

Implement the rename as the **three-migration add-then-deprecate sequence** from Lecture 1 section 5:

1. Migration A: add the new field as nullable.
2. Migration B: a `RunPython` data migration that copies the old field's value to the new for every row, with a working reverse.
3. Application code change: write to both fields on save (via a `pre_save` signal or `save()` override) and read from the new field everywhere.
4. Migration C: remove the old field (this can be a separate deploy; for the homework, you can put it in the same commit but document the deploy-ordering as if it were separate).

In `01-rename.md`:

- The before/after `models.py`.
- The three migrations, each with `sqlmigrate` output pasted.
- The signal or `save()` override code.
- A test that demonstrates an `Article` instance has the same value in both fields after `save()`.
- One paragraph: in production with rolling deploys, what is the exact ordering? Database first, then code? Or code first, then database? Be specific.

**Acceptance:** the three migrations apply and reverse cleanly; the test passes; the write-up has the deploy-ordering paragraph.

---

## Problem 2 — A scheduled task with beat (45 min)

**File:** `c16-week-06/homework/02-beat.md`.

Add a Celery beat schedule that refreshes the analytics dashboard cache every 50 seconds (less than the 60-second TTL, so the cache is always warm).

The pieces:

1. A new Celery task `refresh_analytics_cache` in `writer/tasks.py` that calls each of the cache helpers (`get_top_authors`, `get_categories`, `get_most_active`, `get_top_per_category`) but with **a forced refresh**: it should bypass `cache.get` and re-compute, then `cache.set` the result.
2. `CELERY_BEAT_SCHEDULE` in `settings.py` registering the task on a 50-second interval.
3. A separate `celery -A crunchwriter beat -l info` process running alongside the worker.

In `02-beat.md`:

- The task code.
- The `CELERY_BEAT_SCHEDULE` setting.
- A 5-minute `redis-cli MONITOR` capture showing the beat-driven refreshes hitting Redis (`SET` every 50 seconds).
- A 5-minute browser-hit experiment: with beat running, hit the dashboard every 30 seconds for 5 minutes; record how many of those hits were database queries vs Redis hits. (Hint: with `CELERY_TASK_ACKS_LATE` and beat refreshing every 50 seconds, you should see **zero** database hits from your dashboard requests in the 5-minute window.)

**Acceptance:** beat runs the refresh task on schedule; `MONITOR` proves it; the experiment shows the warm-cache property holds.

---

## Problem 3 — Stampede protection with `lock_and_load` (45 min)

**File:** `c16-week-06/homework/03-lock-and-load.md`.

Pick the slowest cache helper in `writer/cache.py` — likely `get_top_per_category` (the window function). Add `lock_and_load` mitigation:

```python
def get_top_per_category(n: int = 3) -> list[dict]:
    key = f"analytics:v1:top_per_cat:n={n}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    lock_key = f"{key}:lock"
    if cache.add(lock_key, "1", timeout=10):
        try:
            value = ...  # compute
            cache.set(key, value, timeout=60)
            return value
        finally:
            cache.delete(lock_key)
    else:
        # Lost the lock — poll for the cache to fill, then return
        for _ in range(20):
            time.sleep(0.05)
            cached = cache.get(key)
            if cached is not None:
                return cached
        # Lock holder is stuck; compute anyway
        return ...  # compute
```

In `03-lock-and-load.md`:

- The full code.
- A load test: send 50 concurrent requests to the dashboard immediately after a cache invalidation. Without `lock_and_load`, all 50 would compute. With `lock_and_load`, one computes and 49 wait. Measure the database query count during the experiment (use `connection.queries` in middleware, or just count by reading the Postgres log).
- One paragraph: when is `lock_and_load` overkill? When is it under-engineered?

**Acceptance:** the code runs; the load test shows the database query count is bounded by 1, not 50.

---

## Problem 4 — A non-idempotent task — and the fix (45 min)

**File:** `c16-week-06/homework/04-idempotency.md`.

Write a deliberately non-idempotent Celery task: increment an `Article.view_count` by 1 every time the task runs.

```python
@shared_task
def increment_views_naive(article_id: int) -> int:
    article = Article.objects.get(pk=article_id)
    article.view_count += 1
    article.save(update_fields=["view_count"])
    return article.view_count
```

Now queue the same task ID 10 times for the same article. With at-least-once delivery and a single retry simulated mid-flight (force one to retry by raising once), the view count ends up wrong — possibly 11 or 12 instead of 10.

Then write the **idempotent** version using either:

- A unique idempotency key per call (UUID stored in a `ViewIncrementLog` table with a unique constraint).
- An atomic `F("view_count") + 1` (this is already race-free but does **not** make the task idempotent; the second call still increments).
- A `Redis INCR` keyed by `(article_id, idempotency_key)` with a TTL.

Pick one strategy. Document why your choice fits.

In `04-idempotency.md`:

- The naive task and the experiment showing the wrong count.
- The idempotent version.
- A second experiment showing 10 calls with the same idempotency key result in exactly one increment.
- One paragraph: which of the three strategies (DB unique constraint, atomic `F`, Redis `SETNX`) is right for **counting views**, and why? (Hint: views can legitimately be incremented twice from the same user-session — idempotency is at the **task** level, not the business level. Get this distinction right in your answer.)

**Acceptance:** the experiment numbers are in the write-up; the idempotent version actually deduplicates.

---

## Problem 5 — Cache invalidation precision (45 min)

**File:** `c16-week-06/homework/05-invalidation.md`.

From Exercise 3, you have a `post_save` signal that invalidates all four panel keys on any `Article.save()`. Tighten it:

1. Only invalidate the relevant subset for a given save. If `status` changes, invalidate the panels that show published-article stats. If only `view_count` changes, invalidate `top_authors` but not `categories`.
2. Use `update_fields` to determine which panels need invalidation.
3. Add a test that confirms saving an irrelevant field (e.g. `slug`) does **not** invalidate any panel.

In `05-invalidation.md`:

- The narrow `post_save` signal.
- A truth-table mapping each `update_field` to the cache keys it invalidates.
- The test (with `assertEqual` on `cache.get(key)` before and after the save).
- One paragraph: there is a category of bugs this narrowing creates — a developer saves an article without `update_fields` and the conservative branch fires; the cache invalidates unnecessarily. Is that worse than the alternative? Why or why not?

**Acceptance:** the truth-table is in the write-up; the test passes; the trade-off is named.

---

## Problem 6 — Reflection (45 min)

`c16-week-06/homework/06-reflection.md`, ~400 words:

1. **Migrations in your career so far** — describe one migration you (or someone on your team) ran that took longer or did more damage than expected. What would you do differently with the lecture's framework? If you have no prior experience, describe the one you most fear.
2. **The async-vs-Celery decision** — when have you written async code that should have been a queue, or queued code that should have been async? Three sentences.
3. **Cache invalidation, in hindsight** — re-read your Exercise 3 write-up. Is the 60-second TTL the right choice for your data? Would you go shorter or longer? What would you measure to decide?
4. **One thing you still do not fully understand** — name it. Three sentences. This is the question to bring to Week 7's Q&A.

---

## Time budget

| Problem | Time |
|--------:|----:|
| 1 — Rename | 60 min |
| 2 — Beat refresh | 45 min |
| 3 — `lock_and_load` | 45 min |
| 4 — Idempotency | 45 min |
| 5 — Invalidation precision | 45 min |
| 6 — Reflection | 45 min |
| **Total** | **~5h 30m** |

After homework, ship the [mini-project](./mini-project/README.md) — `crunchwriter` image upload with async thumbnail generation.
