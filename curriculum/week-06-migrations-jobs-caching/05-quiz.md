# Week 6 — Quiz

Ten questions. Lectures closed.

---

**Q1.** You add `reading_time_minutes = models.PositiveIntegerField()` (non-nullable, no default) to `Article` and run `migrate` against a populated table. What happens?

- A) The column is added; existing rows get `0`.
- B) The migration fails because existing rows have `NULL` and the column is `NOT NULL`.
- C) The column is added as nullable; Django silently relaxes the constraint.
- D) Django auto-generates a backfill migration.

---

**Q2.** Inside a `RunPython` callback, why do you write `apps.get_model("writer", "Article")` instead of `from writer.models import Article`?

- A) Direct imports are slower.
- B) The historical model reflects the schema **at this migration's point in history**; the direct import reflects the **current** `models.py`, which may differ.
- C) Direct imports break tests.
- D) Django will warn you in development but allow it in production.

---

**Q3.** `CELERY_TASK_ACKS_LATE = True` means:

- A) The worker acknowledges the task to the broker only after the task completes successfully.
- B) The worker waits before picking up the next task.
- C) The result is written to the result backend after a delay.
- D) Tasks are retried later if they fail.

---

**Q4.** Celery's delivery contract is:

- A) At-most-once.
- B) Exactly-once.
- C) At-least-once.
- D) Best-effort.

---

**Q5.** You have a task that takes 5 seconds and runs once per article. You queue 100 tasks. With `--concurrency=4`, expected wall-clock time is approximately:

- A) 5 seconds.
- B) 125 seconds (100 × 5 / 4).
- C) 500 seconds (100 × 5).
- D) Unpredictable.

---

**Q6.** `cache.add(key, value, timeout=60)` differs from `cache.set(key, value, timeout=60)` in that:

- A) `add` is atomic and `set` is not.
- B) `add` only sets the key if it does not already exist; `set` always overwrites.
- C) `add` does not support a timeout.
- D) There is no difference; they are aliases.

---

**Q7.** The cache stampede happens when:

- A) Redis runs out of memory.
- B) Many requests miss the cache simultaneously and all compute the same expensive value.
- C) The TTL is set too long.
- D) `cache.delete` is called from a signal.

---

**Q8.** You want the dashboard to be fresh after `Article.save()`. The simplest, most robust approach is:

- A) Set the cache TTL to 1 second.
- B) Never cache; always read from the database.
- C) Use a `post_save` signal to `cache.delete` the relevant keys.
- D) Restart the worker after each save.

---

**Q9.** You implement a Celery task `generate_thumbnails(article_id)`. To make it idempotent, the simplest mechanism is:

- A) Set a `thumbnails_generated_at` timestamp on the article; check it at task start and return early if non-null.
- B) Disable retries.
- C) Set `CELERY_TASK_ALWAYS_EAGER = True`.
- D) Use a different broker for each call.

---

**Q10.** A Django 5 `async def` view is the right choice instead of Celery when:

- A) The work takes 30 seconds and must complete even if the user closes the tab.
- B) The work is short, I/O-bound, and the user is waiting for the result inline.
- C) The work must retry on failure.
- D) The work runs on a schedule.

---

## Answer key

<details>
<summary>Reveal</summary>

1. **B** — The `ALTER TABLE ... NOT NULL` fails on existing rows that have no value. The correct shape is the three-migration pattern: add nullable, backfill, then `SET NOT NULL`.
2. **B** — `apps.get_model` returns the model as it existed at this migration's point. The historical model has only the fields and the default manager; it does not have custom methods or managers. Direct imports break when migrations are re-run on a database that no longer matches the current `models.py`.
3. **A** — `ACKS_LATE` defers the acknowledgement to the broker until after the task completes. Combined with idempotent tasks, this survives worker crashes mid-execution at the cost of possible duplicate runs.
4. **C** — At-least-once. Celery may deliver the same task twice (worker crash, retry, broker glitch). This is why idempotency is non-negotiable.
5. **B** — 100 tasks × 5 seconds each, divided by 4 workers running in parallel, is 125 seconds. The actual number will be slightly higher due to broker round-trip and result-write costs.
6. **B** — `add` is Redis `SETNX` semantics: only set if not already present. The atomicity property is the same as `set`; the difference is the "do not overwrite" guarantee. Useful for distributed locks.
7. **B** — The stampede: 1 000 concurrent requests all miss, all compute, the database melts. Mitigations: a distributed lock so only one computes (lock-and-load), a beat task that refreshes the cache before expiry (refresh-ahead), or probabilistic early expiration.
8. **C** — `post_save` invalidation is direct and easy to reason about. The alternatives (TTL=1s, versioned keys, refresh-ahead) all have their place but are more complex to implement.
9. **A** — A timestamp on the article is the cheapest and most durable idempotency guard. The check is one SQL column read; the set is one column write. Alternatives (Redis `SETNX` for the duration of the task, unique-constraint INSERT on a side table) exist but are appropriate for different scenarios.
10. **B** — Short, I/O-bound, inline. Async is right for parallelising 3 HTTP calls in the same request. Celery is right when the work must outlive the request, survive a process restart, or retry on failure.

</details>

If 9+: ship the homework. 7–8: re-read Lecture 1 section 3 and Lecture 2 section 5. <7: re-read all three lectures from the top before homework.
