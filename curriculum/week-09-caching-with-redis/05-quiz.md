# Week 9 — Quiz

Ten questions. Lectures closed. One correct answer per question; the answer key is at the end.

---

**Q1.** Of Redis's primary data types, which is the right choice for caching "the last 10 articles a user viewed", where each `LPUSH` is paired with `LTRIM key 0 9`?

- A) String, serialised as a JSON array.
- B) Hash, with field names `0` through `9`.
- C) List.
- D) Sorted set, with the score being the article ID.

---

**Q2.** The cache-aside pattern, applied to a read, has the steps:

- A) Write the cache; read the source; return.
- B) Read the cache; on miss, read the source, write the cache, return.
- C) Read the source; write the cache; return.
- D) Read the cache; on miss, raise an error.

---

**Q3.** The Redis configuration `maxmemory-policy allkeys-lru`, when memory is full, evicts:

- A) The most recently added key, regardless of access pattern.
- B) Any key, chosen randomly from the keyspace.
- C) The least-recently-used key, chosen from the entire keyspace via a sampled approximation.
- D) Only keys with a TTL set; keys without TTL are never evicted.

---

**Q4.** The default `maxmemory-policy` in Redis 7 is `noeviction`. For a cache instance, this is:

- A) The right choice — it forces the application to handle memory limits.
- B) The wrong choice — `SET` commands return errors when memory is full, leaving the cache stale and shrinking.
- C) Equivalent to `allkeys-lru` for practical purposes.
- D) Only effective when paired with a `volatile-*` variant.

---

**Q5.** Tag-based cache invalidation stores, in Redis:

- A) A single hash mapping every cached key to its tag list.
- B) Per-tag SETs, each containing the keys that declared that tag; deleting the tag iterates the SET and deletes each key.
- C) A sorted set per tag, with the score being the cache key's TTL.
- D) Tags as a Pub/Sub channel name; subscribers delete keys they manage.

---

**Q6.** A cache stampede happens when:

- A) Redis runs out of memory and starts evicting keys randomly.
- B) A popular cached key expires and N concurrent requests each independently rebuild it, multiplying the source load by N.
- C) The cache is full and the application falls back to direct source queries indefinitely.
- D) A Pub/Sub channel receives more invalidation events than its subscribers can process.

---

**Q7.** The Vattani, Chierichetti, and Lowenstein 2015 algorithm (XFetch) prevents the cache stampede by:

- A) Maintaining a per-key lock that serialises all rebuilds.
- B) Probabilistically refreshing the cache *before* it expires, with a probability that climbs as the TTL approaches zero.
- C) Doubling the cache TTL on every miss.
- D) Pre-warming every cached value on a fixed schedule.

---

**Q8.** The XFetch formula `t - delta * beta * log(rand()) >= expiry` uses `beta`. The paper proves the optimal value is:

- A) 0.5.
- B) 1.0.
- C) 2.0.
- D) The natural logarithm of the TTL.

---

**Q9.** In Django, configuring `SESSION_ENGINE = "django.contrib.sessions.backends.cache"` with a Redis-backed cache:

- A) Stores the full session data in the client cookie.
- B) Stores the session data in Redis, with the cookie carrying only a session ID; deleting the Redis key revokes the session.
- C) Stores sessions in the database with Redis as a write-through cache.
- D) Disables sessions entirely.

---

**Q10.** Running `ab -n 1000 -c 50 http://localhost:8000/articles/popular` against a cached endpoint shows p95 of 14 ms; the uncached baseline shows p95 of 720 ms. The improvement is:

- A) About 2x.
- B) About 10x.
- C) About 50x.
- D) About 500x.

---

## Answer key

| Question | Answer | Lecture / reference |
|---:|:---|:---|
| Q1 | C | Lecture 1 §1.3 — the list as a recent-items feed                       |
| Q2 | B | Lecture 1 §4.1 — the cache-aside read path                              |
| Q3 | C | Lecture 2 §2.2 — `allkeys-lru` and the sampled approximation           |
| Q4 | B | Lecture 2 §2.1 — why `noeviction` is wrong for caches                  |
| Q5 | B | Lecture 2 §4.3 — the tag-as-SET structure                              |
| Q6 | B | Lecture 3 §1 — the stampede failure mode                               |
| Q7 | B | Lecture 3 §3 — XFetch, probabilistic early expiration                  |
| Q8 | B | Lecture 3 §3 — Vattani et al. 2015, the optimal `beta` proof           |
| Q9 | B | Lecture 3 §5.1 — Django cache-backed session engine                    |
| Q10 | C | Challenge 1 — 720 / 14 ≈ 51, which is the 50x order of magnitude        |
