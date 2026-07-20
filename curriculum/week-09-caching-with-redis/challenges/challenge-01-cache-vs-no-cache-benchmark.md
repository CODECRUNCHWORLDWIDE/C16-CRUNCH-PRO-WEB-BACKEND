# Challenge 1 — Cache vs. no-cache benchmark on a real endpoint

> Take an expensive view from a real service. Run a load test with `ab` and `hey` to capture a baseline. Add a Redis cache. Re-run the same load test. Produce a `BENCHMARK.md` with the before-and-after numbers, the explanation of each delta, and a recommendation for the TTL.

**Time:** 2 hours. **Deliverable:** A `BENCHMARK.md` in your repo containing the four sections below, with real numbers from your machine.

## The setup

Pick one of the following endpoints to benchmark. The one you choose drives the work — the answers are the same shape, the implementation details differ.

1. **Easy mode.** A FastAPI endpoint that queries SQLite for a `SELECT * FROM articles ORDER BY views DESC LIMIT 10`. The endpoint reads from a database file with at least 10 000 rows (seed the DB if you need to). The baseline p95 should be in the 20–100 ms range.
2. **Medium mode.** A Django view that renders a template aggregating data from three models — `User`, `Article`, `Comment`. The baseline p95 will be in the 50–200 ms range depending on your queryset's N-plus-one shape.
3. **Hard mode.** Your Week 7 `crunchreader-api` `/articles/popular` endpoint, or an equivalent in your current project. Use real Postgres if you have it; SQLite otherwise.

Whichever you pick, the workload is identical: 1 000 requests at 50 concurrency, repeated three times, with the median of the three reported.

## Step 1 — Run the baseline

Start your service. Confirm it returns 200 on the chosen endpoint.

```bash
ab -n 1000 -c 50 -k http://localhost:8000/articles/popular > baseline_ab.txt
```

The flags: `-n 1000` total requests, `-c 50` concurrent, `-k` keep-alive (the HTTP/1.1 default in real browsers; ab defaults to off). The output includes percentiles in the "Percentage of the requests served within a certain time" section.

Then `hey` for cross-reference:

```bash
hey -n 1000 -c 50 http://localhost:8000/articles/popular > baseline_hey.txt
```

`hey` prints a latency histogram at the bottom, which is easier to read than `ab`'s percentile table.

Record these numbers in your `BENCHMARK.md`:

- Requests per second (`ab` line "Requests per second:")
- Time per request (mean, ms) (`ab` line "Time per request: ... [ms] (mean)")
- Time per request (across all concurrent requests, ms)
- 50th, 90th, 95th, 99th percentile latency (from `ab`'s percentiles table)
- Failed requests (should be 0)

## Step 2 — Capture the database query count

`ab` measures wall-clock latency. To know *why* the endpoint is slow, you need to count database queries.

**FastAPI / SQLAlchemy.** Enable the SQL logger:

```python
import logging
logging.basicConfig()
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
```

Run a single request via `curl`. Count the `SELECT` statements in the logs. Record the per-request query count.

**Django.** Use Django Debug Toolbar or the lower-level `django.db.connection.queries` after a `DEBUG=True` request:

```python
from django.db import connection
# ... make request ...
print(len(connection.queries))
```

Record the per-request query count.

The query count is the lower bound on what the cache will save. If a request makes 25 queries, the cached version will make 0 (everything served from Redis) on a hit and 25 on a miss. The cache-hit ratio determines how the workload is split.

## Step 3 — Add the cache

Implement the cache-aside pattern (Lecture 1, Section 5) on the chosen endpoint. The Redis key should be specific enough that different query parameters get different cache entries. The TTL should be defensible — start with 60 seconds.

The shape, for the FastAPI case:

```python
@router.get("/articles/popular")
async def popular_articles(
    limit: int = 10,
    r: redis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    key = f"v1:articles:popular:{limit}"
    cached = await r.get(key)
    if cached is not None:
        return json.loads(cached)
    rows = await _query_popular(db, limit)
    await r.set(key, json.dumps(rows), ex=60)
    return rows
```

For Django, use the framework's per-view cache or the low-level `cache.get / cache.set`:

```python
from django.views.decorators.cache import cache_page

@cache_page(60)
def popular_articles(request):
    ...
```

Either is fine. The point is to compare the bare endpoint to the cached endpoint, not to evaluate the cache implementation.

## Step 4 — Re-run the benchmark

Restart the service. Warm the cache with one `curl` to the endpoint (the first hit will be a miss; we want the steady-state hit measurement, not the cold-start).

Then run `ab` and `hey` again with the same parameters:

```bash
ab -n 1000 -c 50 -k http://localhost:8000/articles/popular > cached_ab.txt
hey -n 1000 -c 50 http://localhost:8000/articles/popular > cached_hey.txt
```

Record the same numbers as in Step 1.

## Step 5 — The `BENCHMARK.md` artefact

Your `BENCHMARK.md` contains four sections.

### Section 1 — The setup

One paragraph describing: which endpoint, what database, what hardware (model, RAM), what Python and Redis versions. The numbers below are meaningless without this context.

### Section 2 — The numbers

A table:

```text
| Metric                          | Baseline (no cache) | Cached      | Improvement   |
|---------------------------------|---------------------|-------------|---------------|
| Requests per second             | 87                  | 4 215        | 48x           |
| Latency p50 (ms)                | 412                 | 8           | 51x lower     |
| Latency p95 (ms)                | 720                 | 14          | 51x lower     |
| Latency p99 (ms)                | 1 240                | 28          | 44x lower     |
| Database queries per request    | 12                  | 0 (hit)     | -             |
| CPU on the database container   | 95%                 | 8%          | 11x lower     |
```

The exact numbers will differ on your machine. The order of magnitude (10x to 100x improvement) is what you should see.

### Section 3 — The explanation

For each row in the table, one or two sentences explaining *why* the number is what it is.

- Why is the p99 less improved than the p50? (Tail latency includes cache misses on the rare key — `limit=11` instead of `limit=10` — and the lock-free Redis client variance.)
- Why is the database CPU 11x lower, not 48x? (The benchmark's read rate is now Redis-limited; the database only sees the small fraction of misses, plus background work like vacuum.)
- Why does requests-per-second jump 48x but latency only drop 50x? (They are not the same number; throughput is `concurrency / latency`, and you can verify the math.)

### Section 4 — The recommendation

A two-paragraph recommendation:

1. **TTL recommendation.** Why 60 seconds? What is the staleness budget? What writes invalidate this key, and what is the strategy (event-driven, TTL, or tag-based)? What happens if the TTL is set to 600 seconds — does the hit ratio improve enough to matter? What happens at 6 seconds — does the latency win disappear?
2. **Eviction policy recommendation.** Given the cache key cardinality (e.g., 50 popular articles times 10 limit values = 500 keys) and the value size (e.g., 2 KB each = 1 MB total), what `maxmemory` and `maxmemory-policy` would you configure on the Redis instance hosting this cache? Cite Lecture 2 for the policy choice.

## Submission

Commit `BENCHMARK.md`, `baseline_ab.txt`, `baseline_hey.txt`, `cached_ab.txt`, `cached_hey.txt`, and the code diff that added the cache. The commit message should include the headline improvement: "Cache popular-articles endpoint; p95 720 ms -> 14 ms (51x)".

## Rubric (15 points)

| Area                          | Points | Pass bar                                                  |
|-------------------------------|-------:|-----------------------------------------------------------|
| Baseline run captured          | 3      | All five `ab` numbers; histogram from `hey`; query count  |
| Cached run captured            | 3      | Same five numbers post-cache; cache-hit confirmation       |
| `BENCHMARK.md` table           | 3      | All six rows; correct math on the improvement column      |
| `BENCHMARK.md` explanation     | 3      | One+ sentence per row; covers the p50/p99 difference      |
| TTL and eviction recommendation| 3      | Defends the number; cites the staleness budget             |

## Stretch goals

- Run the benchmark at three concurrency levels (10, 50, 200) and plot requests-per-second versus concurrency for both the baseline and the cached endpoint. The shape of the cached curve should saturate higher.
- Add a `Cache-Control: max-age=60` HTTP header to the cached response. Re-run the benchmark from a browser; observe that subsequent requests hit the browser cache and never touch your server. Reconcile this with your Redis cache (RFC 9111 §5.2.2 is the reference; HTTP-level caching is orthogonal to your application cache).
- Add Prometheus instrumentation (the `prometheus-fastapi-instrumentator` package, or `django-prometheus`). Capture the `cache_hit_total` and `cache_miss_total` counters over the benchmark run. Compute the hit ratio from the counters and confirm it agrees with the `INFO stats` numbers from Redis.

## References

- **Apache Bench manual**: <https://httpd.apache.org/docs/2.4/programs/ab.html>
- **`hey` README**: <https://github.com/rakyll/hey>
- **Stack Overflow caching architecture** (a real production system's benchmarks): <https://nickcraver.com/blog/2019/08/06/stack-overflow-how-we-do-app-caching/>
- **AWS ElastiCache strategies overview**: <https://docs.aws.amazon.com/AmazonElastiCache/latest/mem-ug/Strategies.html>
- **`fastapi-cache2`** (the read-through library; cite if you compare implementations): <https://github.com/long2ice/fastapi-cache>
