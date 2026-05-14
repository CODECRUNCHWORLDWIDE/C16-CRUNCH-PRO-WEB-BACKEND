# Week 9 — Homework

Six problems. Approximately 6 hours of work; budget one hour per problem, with the last two being longer if you take the stretch goals. Submit each problem as a separate commit on your homework branch; the commit message names the problem (e.g., `HW9.3 tag-based invalidation map`).

The references at the bottom of each problem are the *minimum* required citations. If you use additional sources, cite them too.

---

## Problem 1 — Pick the right data type (45 min)

For each of the following cache workloads, name the Redis data type you would use, the key naming scheme, and (where relevant) the TTL. A single sentence per workload justifying the pick is enough.

1. The user's last login timestamp, fetched on every authenticated request, updated on every successful auth, sliding 1-hour TTL.
2. A leaderboard of the top 100 contributors to a forum, scored by their reputation, queryable as "top 10" and "where does user X rank".
3. The set of article IDs the current user has already up-voted, used to disable the up-vote button on already-voted articles; the set grows over the user's lifetime.
4. A rate-limit window: "has this IP made more than 100 requests in the last minute?".
5. A user profile card cached for display in 15 different places on the site; profile fields can change individually (display name, avatar URL, bio); cache invalidation is on the whole card.
6. A queue of pending email-confirmation tasks: producer pushes, multiple consumers pop, must survive a Redis restart.

For each, also note whether the data type's TTL applies to the whole key or to individual members. Where TTL does not exist at the member level natively, name the workaround.

**Submission:** `hw9/problem-1.md` with six numbered sections. Cite Lecture 1 and the relevant Redis data-type docs.

**References:** <https://redis.io/docs/latest/develop/data-types/>; Lecture 1 §1.

---

## Problem 2 — Write the cache-aside read path, with degradation (45 min)

Implement a function `cache_aside_get(r, key, loader, ttl)` that:

1. Returns the cached value if present.
2. On a miss, runs `loader()`, writes the result to the cache with the given TTL, and returns the value.
3. On any `redis.exceptions.RedisError` during either the read or the write, logs a warning and runs `loader()` directly, returning the value without caching.
4. Times out the Redis operations at 100 ms each; on timeout, treats the operation as a miss and degrades to the loader.

Write three test cases using `fakeredis`:

- Happy-path hit and miss.
- Forced `RedisError` (use a mock or `fakeredis` with `connection.disconnect()`).
- Timeout (use a mock that sleeps 200 ms).

**Submission:** `hw9/problem-2/cache_aside.py` and `hw9/problem-2/test_cache_aside.py`. All tests pass under `pytest`.

**References:** Lecture 1 §5–6; <https://github.com/cunla/fakeredis-py>.

---

## Problem 3 — Build the invalidation map for a service (60 min)

Take your Week 7 service (or any small service you have running). List every read endpoint that hits the database. For each endpoint, fill in a row of the table:

```text
| Endpoint | Cache key pattern | TTL | What writes invalidate it | Strategy |
```

Then list every write endpoint. For each, fill in:

```text
| Endpoint | Entities written | Cache keys to invalidate | Strategy used |
```

The two tables together are your invalidation map. They are *the* document a reviewer reads to understand your caching decisions.

Justify any TTL longer than 5 minutes with one sentence. Justify any TTL shorter than 10 seconds with one sentence. Anything in between is "default; no special reason".

**Submission:** `hw9/problem-3.md`. Lecture 2 §5 has the structure.

**References:** Lecture 2 §4–5; the AWS strategies overview <https://docs.aws.amazon.com/AmazonElastiCache/latest/mem-ug/Strategies.html>.

---

## Problem 4 — Implement and benchmark XFetch (90 min)

Take the XFetch algorithm from Lecture 3 §3. Implement it as a Python function `xfetch_cache_aside(r, key, loader, ttl, delta)`. Confirm it compiles and runs against a local Redis.

Then run a benchmark that compares three strategies:

1. Naive cache-aside (the stampede-prone version).
2. Single-flight coalescing (using the `CoalescingCache` from Exercise 4).
3. XFetch with `beta=1.0`, `delta` set to the loader's measured latency.

The benchmark: 200 concurrent requests for the same key right at the moment the cache is expected to expire. Report:

- Loader call count (the smoking gun).
- p50 / p95 / p99 latency for the calling coroutines.
- Standard deviation of the loader call count across 10 runs (XFetch is non-deterministic).

Plot the results if you have matplotlib; otherwise a table is fine.

**Submission:** `hw9/problem-4/bench.py` and `hw9/problem-4/RESULTS.md`. The `RESULTS.md` includes a one-paragraph recommendation: for this loader latency (`delta`) and this concurrency, which strategy do you pick?

**References:** Vattani et al. 2015 <https://arxiv.org/abs/1504.00922>; Lecture 3 §3.

---

## Problem 5 — Sliding versus fixed TTL for sessions (45 min)

Implement two FastAPI session middlewares, identical in shape except for the TTL behaviour:

1. **`SlidingSessionMiddleware`** — TTL refreshes on every request that touches the session.
2. **`FixedSessionMiddleware`** — TTL is set at login time and does not change; the session expires at `login_at + max_age`.

Write a test that demonstrates the difference: a user who logs in and makes a request every minute for 31 minutes. Under sliding, the session is still alive; under fixed (with `max_age = 30 * 60`), it expired at minute 30.

Discuss the security trade-off in 3-4 sentences: sliding TTL is friendlier (active users stay logged in) but extends the attack window if a session ID is stolen; fixed TTL caps the damage but logs out active users on a hard ceiling. Which would you pick for a banking app? Which for a social media app?

**Submission:** `hw9/problem-5/middleware.py`, `hw9/problem-5/test_middleware.py`, `hw9/problem-5/DISCUSSION.md`.

**References:** Lecture 3 §5; <https://docs.djangoproject.com/en/5.1/topics/http/sessions/>; <https://fastapi.tiangolo.com/tutorial/middleware/>.

---

## Problem 6 — A Redis observability dashboard (60 min)

Configure your local Redis with `maxmemory 256mb` and `maxmemory-policy allkeys-lru`. Run a small load generator that:

- Writes 1 000 keys with 200 KB values each (200 MB total — well under the ceiling).
- Reads 100 random keys per second for 5 minutes.
- Writes 50 new keys per second for 5 minutes (which will push past the ceiling and force evictions).

Watch the four numbers from Lecture 2 §6:

1. `used_memory` over time.
2. `evicted_keys` per second.
3. Hit ratio (`keyspace_hits / (keyspace_hits + keyspace_misses)`).
4. `instantaneous_ops_per_sec`.

Capture the numbers every 5 seconds via a Python script that calls `INFO` and writes a CSV. Plot the four series over the 5-minute window (a simple `matplotlib` line plot is fine).

Write a one-paragraph interpretation: at what minute did evictions start? How did the hit ratio change as evictions kicked in? Is the eviction rate sustainable, or is the cache thrashing?

**Submission:** `hw9/problem-6/monitor.py`, `hw9/problem-6/observations.csv`, `hw9/problem-6/PLOT.png` (or the raw matplotlib `.py`), `hw9/problem-6/INTERPRETATION.md`.

**References:** Lecture 2 §3 and §6; <https://redis.io/commands/info/>; the Grafana Redis dashboard <https://grafana.com/grafana/dashboards/763> for inspiration on what to plot.

---

## Grading

Each problem is graded out of 10 points: 6 for correctness (the code or numbers match what was asked), 2 for clarity (the README or DISCUSSION reads cleanly), 2 for the citations (the references are concrete; "Redis docs" is not a citation, "redis.io/commands/expire" is).

Late submissions: 10% per day, capped at 50%. Code that does not `py_compile` is graded as if the file did not exist; fix and resubmit.

---

## Submission checklist

- [ ] All six problem folders / files present under `hw9/`.
- [ ] Every `.py` file passes `python3 -m py_compile`.
- [ ] Every `.md` file uses the project voice — declarative, no emojis, citations as URLs.
- [ ] Pytest passes for problems 2 and 5.
- [ ] The bench scripts for problems 4 and 6 run end-to-end on a clean Redis.
- [ ] Each commit message names the problem (e.g., `HW9.4 xfetch benchmark — 50x stampede reduction at 200 concurrency`).
