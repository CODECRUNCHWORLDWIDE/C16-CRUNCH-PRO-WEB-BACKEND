# Exercises — Worked solutions

These are walk-throughs of the trickier prompts in each exercise. Read after you have tried the prompt yourself; the value is in the contrast between your answer and ours, not in the answer itself.

---

## Exercise 1 — Cache-aside

### Task 1 — The latency contribution of each line

The cache-aside read has two paths.

**Hit path:**

```python
cached = await r.get(key)        # ~0.5 to 1.0 ms (Redis round-trip)
if cached is not None:
    return json.loads(cached)    # ~0.01 ms for a small JSON value
```

Total: ~1 ms.

**Miss path:**

```python
cached = await r.get(key)        # ~0.5 to 1.0 ms (Redis round-trip, returns None)
if cached is not None:
    return json.loads(cached)
value = await loader()           # The slow part — 200 ms in our demo
await r.set(key, json.dumps(value), ex=ttl)  # ~1 ms (Redis round-trip)
return value
```

Total: ~202 ms. The hit path is 200x faster than the miss path; the cache earns its keep on the second request and every subsequent one within the TTL.

### Task 2 — Why "try cache, fall back on RedisError" rather than "if r is None"

`if r is None` only covers the "Redis client object was never created" case. The interesting failures are dynamic: Redis was reachable at startup but the network dropped mid-request; Redis hit `noeviction` and returned an OOM error; the connection pool exhausted; the connection's TCP socket got reset. None of these turn `r` into `None`; they raise `redis.exceptions.RedisError` (or a subclass) on the call.

The `try/except` wraps the actual operation so any transient failure degrades to "skip the cache, run the loader, do not retry". This is what makes the service resilient to a cache outage. The pattern is the same as for any optional dependency: the service must work, slowly, when the optional dependency is unavailable.

### Task 3 — Per-call latency with `FLUSHDB` between every call

If you `await r.flushdb()` between every `cache_aside_get` call, every call becomes a miss. The cache write happens but is immediately wiped before the next read. The benchmark loop's per-call latency becomes ~202 ms — the same as the uncached benchmark, with the additional cost of two Redis round-trips per call (the `get` returning `None`, then the `set` writing the value that nobody will read, then the `flushdb` wiping it).

The lesson: a cache with a 0% hit ratio is *worse* than no cache. It pays the Redis round-trip cost on every read and gets nothing back. The break-even hit ratio depends on the relative cost of Redis (~1 ms) and the loader (~200 ms): you need a hit ratio above (Redis cost / loader cost) ≈ 0.5% just to break even. Above that, you save in proportion to the hit ratio.

### Task 4 — Per-call latency with cache offline

Calling `await r.aclose()` before the benchmark closes the Redis client. The `cache_aside_get_with_fallback` catches the resulting error and falls through to the loader. Every call runs the loader; per-call latency is ~200 ms (the same as the uncached benchmark), plus a small overhead from the failed Redis attempt and the log line.

The expected output: a `cache read failed` warning per call, followed by the loader running and a `cache write failed` warning. The service still returns valid articles — slowly, but correctly. This is the property we are after: the cache being down is a latency problem, not a correctness problem.

---

## Exercise 2 — Eviction and TTL experiments

### Task 1 — `allkeys-lru` survival pattern

After `scenario_allkeys_lru`, the keys you touched (`get` on `k:0` through `k:499`) had their LRU timestamps updated to "recently used". When the second `fill_until_evictions` writes more keys and Redis needs to evict, the policy picks the keys *not* touched — keys `500` through `1999`. So keys `0..499` survive disproportionately well; the eviction concentrates on `500..1999`.

The Redis [eviction docs](https://redis.io/docs/latest/develop/reference/eviction/) note that the LRU is sampled (default sample size 5), not exact. With 1 500 candidates and a 5-sample pool, the policy is not perfect; a few "not recently used" keys will survive by chance, and a few "recently used" keys may be picked. Increase `maxmemory-samples` to 10 to tighten the approximation at the cost of more CPU per eviction.

### Task 2 — `allkeys-lfu` versus `allkeys-lru` for skewed access

`scenario_allkeys_lfu` touches keys `0..50` twenty times each — 1 000 reads concentrated on 50 keys. The LFU policy increments per-key frequency counters on each access. When eviction pressure arrives, the 50 hot keys have frequency counters around 20; the cold keys have counters of 1 (the initial write). LFU evicts the cold ones first.

The contrast with `scenario_allkeys_lru`: LRU only remembers *recency*. If you touch a hot key once at the start of the script and then write a thousand other keys, LRU forgets that the hot key was ever hot; LFU still ranks it highly because the access count remembers the history.

LFU is the right choice when access is power-law distributed and you want the few hot keys to dominate. LRU is the right choice when access is temporal and what is hot now is what was hot recently. Most caches are a mix; the default is `allkeys-lru` because the rare LFU edge case (an old hot key staying hot forever despite no recent traffic) is harder to reason about. The Redis LFU implementation decays counters over time to prevent that, but the decay rate is another knob to tune.

### Task 3 — `noeviction` user-facing behaviour

The first error from `scenario_noeviction` is:

```text
OOM command not allowed when used memory > 'maxmemory'.
```

This is returned to every write-bearing command — `SET`, `INCR`, `HSET`, `SADD`, `ZADD`, `LPUSH`. Reads (`GET`, `MGET`) still work. The policy is "stop accepting new data; the existing data stays".

For a cache, this is catastrophic: as time passes, the existing data ages out under TTL, no new entries can replace it, and the cache becomes increasingly empty. Hit ratio drops to zero; eventually every request is a miss.

For a queue, this is exactly right: dropping a job to make room for another would be a data loss. The queue must be sized to accommodate its peak depth, and `noeviction` enforces "do not lose data" at the cost of refusing new arrivals when full. The application is expected to apply back-pressure.

The cardinal rule: `noeviction` for instances holding queues, lock servers, or durable state. `allkeys-lru` for instances holding cache. Never the default `noeviction` for a cache.

---

## Exercise 3 — Tag-based invalidation

### Task 1 — Trace of an invalidation

When `cache.invalidate_tag("author:7")` is called, the following Redis commands are issued (visible in `redis-cli MONITOR`):

```text
SMEMBERS tag:author:7
DEL cache:article:1:render:en
DEL cache:author:7:profile:en
DEL tag:author:7
EXEC
```

The `SMEMBERS` returns `{"article:1:render:en", "author:7:profile:en"}`. The pipeline then queues the deletes; `EXEC` (the implicit pipeline submit) issues them as a single round-trip. Three cache entries deleted, plus the tag set itself. The homepage is untouched because it never declared `author:7` as a tag.

### Task 2 — Why the homepage disappears on `invalidate_tag("article:1")`

The homepage was cached with tags `["article:1", "article:2", "article:3", "homepage"]`. The set `tag:article:1` contains the keys `{"homepage:en", "article:1:render:en"}`. Invalidating `tag:article:1` deletes every member: the homepage *and* the article render. The dependency was declared; the invalidation honoured it.

This is the *point* of tag-based invalidation: the write path knows the entity changed (article 1 was deleted); the cache layer knows which cached entries declared a dependency on that entity (the homepage and the article render); the sweep happens without the write path having to enumerate.

### Task 3 — Failure mode when the tag set's TTL is shorter than the cached values' TTL

If the tag set expires before the cached values it tracks, an invalidation of that tag finds an empty set and returns 0. The cached values stay; the invalidation event was lost.

For a write-driven invalidation pattern, this is broken — the cache stays stale until the values' own TTLs expire. The fix is to set the tag set's TTL to *at least* the cached values' TTL, plus a margin. In the exercise we use `ttl * 2`; in production you might set the tag set to never expire (`PERSIST tag:<name>`) and prune dangling tag sets in a periodic cleanup job.

### Task 4 — Adding `page_d` with `["article:1", "premium"]`

Adding `page_d` makes the tag set `tag:article:1` contain `{"homepage:en", "article:1:render:en", "premium_page"}`. The set `tag:premium` contains just `{"premium_page"}`.

Invalidating `tag:premium` deletes `cache:premium_page` and `tag:premium`. The homepage and the article render survive — they did not declare `premium`. The `tag:article:1` set is now stale (it still contains `premium_page` as a dangling reference), but that is harmless: the next `invalidate_tag("article:1")` will issue a `DEL cache:premium_page` for a non-existent key, which is a no-op in Redis.

The dangling-reference cleanup is the trade-off of tag-based invalidation. The set membership grows over time; the periodic pruning is the operational price.

---

## Exercise 4 — Stampede and coalescing

### Task 1 — Why `scenario_naive` does not report exactly `concurrency`

`asyncio.gather(*tasks)` schedules the 100 tasks. They are not *literally* simultaneous: each task is a coroutine, and the event loop runs them one at a time, interleaving on every `await`. The first task's `await r.get("k")` yields control; the second task starts and also `await r.get("k")` yields control; and so on. The Redis round-trip is short (~1 ms) but not zero. By the time the first task's `set` has completed, some later tasks may have already issued their `get` and seen the miss — but a few of the last tasks may issue their `get` *after* the cache has been populated.

The exact number is run-to-run variable. Expect a number close to 100 but not exactly: 95 to 100 on a slow loader, 70 to 100 on a fast one. The point is that the count is closer to `concurrency` than to 1, which is the failure mode we are fixing.

### Task 2 — How `CoalescingCache.get` coordinates

When the first caller misses, it enters the `_load_once` branch, acquires the `_lock`, finds `_inflight[key]` empty, creates a `Future`, stores it under the key, kicks off `_do_load` as a background task, releases the lock, and `await`s the Future.

When the second caller misses (still before the loader finishes), it enters `_load_once`, acquires the same `_lock`, finds `_inflight[key]` *is* the Future from the first caller, releases the lock, and `await`s that same Future.

Every subsequent caller follows the same path: see the existing Future, await it. When `_do_load` finishes, it calls `future.set_result(value)`. Every awaiting coroutine wakes up with the value at the same moment (more or less — the event loop schedules them sequentially, but the latency is microseconds).

The number of loader calls is exactly 1 because exactly one `_do_load` task was created.

### Task 3 — `scenario_xfetch` non-determinism

Three runs of `scenario_xfetch` might yield call counts of `1`, `2`, `1`. The variation is because XFetch is probabilistic: each reader rolls a dice, and depending on `random.random()`, a refresh may or may not happen. In the steady state, the probability of any given reader refreshing approaches 1/`expected_readers_during_TTL`; the *expected* number of refreshes per TTL window is 1.

With 100 concurrent readers at the edge of expiry, the dice rolls 100 times. The probability that none of them triggers a refresh is small; the probability that exactly one does is the highest individual outcome; two refreshes is possible but unusual; three or more is rare.

The contrast with single-flight: single-flight guarantees exactly 1; XFetch averages 1 but is non-deterministic. For high-traffic keys where determinism matters, prefer single-flight. For lower-traffic keys where the coordination cost is not worth paying, XFetch is the cheaper answer.

### Task 4 — Cross-worker SETNX coalescing

The implementation:

```python
async def setnx_coalesce(r, key, loader, ttl):
    cached = await r.get(key)
    if cached is not None:
        return json.loads(cached)
    lock_key = f"lock:{key}"
    got_lock = await r.set(lock_key, "1", nx=True, ex=10)
    if got_lock:
        try:
            value = await loader()
            await r.set(key, json.dumps(value), ex=ttl)
            return value
        finally:
            await r.delete(lock_key)
    # Did not get the lock; wait for the lock-holder to populate the cache.
    for _ in range(50):
        await asyncio.sleep(0.1)
        cached = await r.get(key)
        if cached is not None:
            return json.loads(cached)
    return await loader()
```

In a single-process test, the SETNX lock approximates the in-memory `asyncio.Future` map but with a Redis round-trip per attempt. The loader_calls count is 1 (one process gets the lock; the others wait for the cache).

The advantage over the process-local CoalescingCache is that the lock works across workers — under `uvicorn --workers 4`, each worker would have its own in-memory coalescing map, allowing one loader call *per worker* (4 total). The SETNX lock makes it one loader call *total*. The trade-off is the polling loop and the lock-key TTL fallback.
