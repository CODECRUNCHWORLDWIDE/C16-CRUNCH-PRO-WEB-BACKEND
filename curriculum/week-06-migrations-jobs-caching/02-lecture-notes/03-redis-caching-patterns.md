# Lecture 3 — Redis caching patterns

> **Duration:** ~1.5–2 hours. **Outcome:** You can configure Django's cache framework against Redis 7 and apply the cache-aside pattern by hand. You know the three caching tiers Django offers (per-view, per-fragment, low-level) and when each is right. You can name the cache stampede and mitigate it.

The analytics dashboard from Week 5 fires four SQL queries on every page load. Each takes 40–80 ms. The page is the same for every staff user; the data changes maybe once a minute. Reading the same dashboard 60 times per minute for ten staff users is 240 ms × 600 = 144 seconds of database time per minute. The right answer is to compute the dashboard once a minute and serve every other request from Redis. That is caching, and it is the cheapest performance win in the codebase.

## 1. What Redis is, briefly

Redis is an in-memory key-value store with a single-threaded event loop. Operations are atomic per-key — `INCR foo` is one indivisible step, regardless of how many clients hit it at once. The data model is richer than "string → string": Redis supports lists, hashes, sets, sorted sets, streams, and bitmaps, each with its own command family. For caching, you will use 95% strings and the occasional sorted set.

Three properties matter for the cache role:

1. **Speed.** A `GET` returns in under 1 ms on a healthy server. Network round-trip dominates.
2. **TTLs.** Every key can carry an expiration. Redis evicts on expiry. The cache "forgets" old data without you writing eviction code.
3. **In-memory.** If Redis is restarted without AOF persistence, the cache is empty. Build for this — never store something in Redis that does not exist elsewhere.

The single-threaded model has one consequence: a slow command (`KEYS *` on a million keys, a 100 MB `GET`) blocks every other client until it finishes. Avoid `KEYS *` in production; prefer `SCAN` with a cursor.

## 2. Configuring Django's cache framework

In `settings.py`:

```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://localhost:6379/2",   # database 2 — separate from Celery
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            "IGNORE_EXCEPTIONS": True,  # treat cache failures as a miss, don't 500
        },
        "KEY_PREFIX": "crunchwriter",
        "TIMEOUT": 300,  # default TTL: 5 minutes
    }
}

DJANGO_REDIS_IGNORE_EXCEPTIONS = True
```

Three settings to set deliberately:

- **`LOCATION` with a database number.** Redis databases are numbered 0–15 by default; use different numbers for Celery broker (0), Celery result backend (1), and Django cache (2). Otherwise a `FLUSHDB` for one accidentally wipes the other.
- **`IGNORE_EXCEPTIONS: True`.** If Redis goes down, the cache calls should return `None` (a miss), not raise. The application should degrade to "uncached but functional", not "500 errors for everyone".
- **`KEY_PREFIX`.** Every key is prefixed with `crunchwriter:`. If two Django projects share a Redis instance (common in dev), the prefix prevents collision.

The Django docs also describe `django.core.cache.backends.redis.RedisCache` (added in Django 4.0). It is a slimmer client; `django-redis` has more options (master/replica, sharding, custom serialisers). Either is fine for Week 6; `django-redis` is the recommended choice because the rest of the curriculum assumes its options.

## 3. The low-level cache API — the foundation

Everything else in this lecture is sugar over four methods:

```python
from django.core.cache import cache

cache.set("foo", "bar", timeout=60)   # SET foo bar EX 60
cache.get("foo")                       # GET foo — returns "bar" or None
cache.delete("foo")                    # DEL foo
cache.get_or_set("foo", lambda: expensive(), timeout=60)
```

The `get_or_set` form encapsulates the cache-aside pattern (section 4). The callable is invoked only on miss; on hit, it is not called. The callable can be a function reference (`lambda: ...`) or any callable; Django evaluates it lazily.

Three more methods worth knowing:

```python
cache.add(key, value, timeout=60)
# Returns False if the key already exists. Equivalent to Redis SETNX. Used for distributed locks.

cache.incr(key, delta=1)
# Atomic increment. Raises ValueError if the key does not exist.

cache.get_many(["k1", "k2", "k3"])
# Returns {"k1": v1, "k2": v2}; missing keys are absent. Equivalent to MGET. One round-trip.
```

Use `cache.get_many` when you have a list of keys to look up; one round-trip beats N. Use `cache.add` when you need atomic "first writer wins" semantics — distributed locks, idempotency guards, rate limiters.

## 4. Cache-aside — the canonical pattern

The pattern, written by hand:

```python
from django.core.cache import cache

def get_top_authors(n: int = 10) -> list[dict]:
    key = f"analytics:top_authors:n={n}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    rows = list(Author.objects.top_by_views(n=n).values(
        "username", "published_count", "total_views",
    ))
    cache.set(key, rows, timeout=60)
    return rows
```

Five lines of cache logic wrapping one line of "the real work". The contract:

1. Look up the key.
2. On hit, return.
3. On miss, do the work.
4. Store the result.
5. Return.

The same logic via `get_or_set`:

```python
def get_top_authors(n: int = 10) -> list[dict]:
    key = f"analytics:top_authors:n={n}"
    return cache.get_or_set(
        key,
        lambda: list(Author.objects.top_by_views(n=n).values(...)),
        timeout=60,
    )
```

The shorter form is preferred when the work is one expression. The longer form is preferred when the work has logging, validation, or post-processing — putting them inside a `lambda` reads worse than an `if cached is not None` branch.

### What goes in the cache, what stays out

- **In the cache:** queryset results materialised to lists of dicts, computed aggregates, rendered HTML fragments. Anything pure (same inputs → same outputs) and expensive to recompute.
- **Not in the cache:** anything user-specific without the user in the key. Anything containing a secret. Anything you cannot recompute. Anything that mutates state.

If you cache `request.user.email` under the key `email` (without the user ID), you will leak one user's email to another. The cache key must include every variable the value depends on.

## 5. Cache key design

A good key has four components:

1. **Domain** — `analytics:`, `article:`, `user:`. Namespaces the cache.
2. **Subject** — `top_authors`, `comment_count`. Names what is cached.
3. **Parameters** — `n=10`, `category=python`, `user=42`. Disambiguates between variants.
4. **Version** (optional but recommended) — `v=2`. Bumping the version is the cheapest "invalidate everything" hammer.

Example: `analytics:v2:top_authors:n=10`. This composes well, is greppable, and reads like English in `redis-cli MONITOR`.

Three rules:

- **No spaces.** Redis allows them; humans hate them.
- **No user-supplied strings without sanitisation.** If `category` is a user-supplied slug, an attacker who can set it to `*` plus newlines can poison neighbouring keys via the `KEYS` glob (only if you ever use `KEYS`, which you should not).
- **No timestamps in the key.** A cache keyed by `analytics:2026-05-13T10:30` is a one-shot cache — every minute the key changes, every minute the cache misses. Put the timestamp in the **value** if you need recency information; let the TTL handle expiration.

## 6. Per-view caching — `@cache_page`

For views whose response is identical across all users (or whose users are already partitioned by the URL), Django ships a one-line cache:

```python
from django.views.decorators.cache import cache_page

@cache_page(60)   # 60 seconds
def analytics_dashboard(request):
    return render(request, "writer/analytics_dashboard.html", get_dashboard_context())
```

The decorator caches the **entire HTTP response** — status, headers, body — under a key derived from the URL plus the `Vary` header. The first request runs the view; the next requests within 60 seconds serve from cache without calling the view function at all.

Three caveats:

1. **`@cache_page` ignores cookies by default.** Two users with different sessions get the same cached page. Combine with `@vary_on_cookie` or `@vary_on_headers("Cookie")` if the response varies per user.
2. **`@cache_page` caches 4xx and 5xx responses too** unless you set `CACHE_MIDDLEWARE_KEY_PREFIX` carefully. A transient 500 can pin itself in the cache for 60 seconds.
3. **Per-view cache is all-or-nothing.** You cannot invalidate one page without writing the cache key yourself.

For most projects, `@cache_page` is right for a small set of high-traffic, never-personalised pages (homepage when logged-out, status pages, dashboards behind a generic staff login). For everything else, low-level cache with explicit keys is more controllable.

## 7. Template fragment caching — `{% cache %}`

When the page is mostly personalised but a section is shared, cache the section:

```django
{% load cache %}

<div class="header">Hello, {{ user.username }}.</div>

{% cache 60 sidebar_top_authors %}
  <ul>
    {% for author in top_authors %}
      <li>{{ author.username }} — {{ author.total_views }} views</li>
    {% endfor %}
  </ul>
{% endcache %}
```

The block is cached for 60 seconds under the key `template.cache.sidebar_top_authors`. The header is rendered every request; the sidebar comes from Redis 59 times out of 60.

For per-user caching, pass extra args:

```django
{% cache 60 sidebar user.id %}
  ...
{% endcache %}
```

The args become part of the cache key. Two users get two cached fragments; both benefit from caching across their own subsequent requests.

## 8. Invalidation — the second hard problem

> "There are only two hard things in Computer Science: cache invalidation and naming things." — Phil Karlton

The TTL is invalidation by patience: the value is wrong for at most N seconds. For most data, this is acceptable — the user does not notice a 60-second delay in the dashboard.

For data that **must** be fresh after a write — "the article I just published should appear in the list immediately" — TTL is not enough. Invalidate explicitly:

```python
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache


@receiver(post_save, sender=Article)
def invalidate_analytics_cache(sender, instance, **kwargs):
    cache.delete_many([
        f"analytics:top_authors:n=10",
        f"analytics:categories",
        f"analytics:most_active",
    ])
```

The signal fires after every `Article.save()`. The next dashboard request misses, recomputes, sets, and the cache is fresh. The downside: every write invalidates the cache, so a write-heavy workload defeats the cache. The fix is to make the invalidation **narrower** — only on `status="published"` writes, or only when the cache-worthy fields change.

### Versioned keys — the alternative

Instead of deleting, bump a version number stored in Redis:

```python
def get_top_authors(n: int = 10) -> list[dict]:
    version = cache.get("analytics:version", 1)
    key = f"analytics:v{version}:top_authors:n={n}"
    return cache.get_or_set(key, lambda: ..., timeout=60)


@receiver(post_save, sender=Article)
def bump_analytics_version(sender, instance, **kwargs):
    cache.incr("analytics:version")
```

Bumping the version invalidates every cache key that references it without scanning the keyspace. The old keys live their TTL and Redis evicts them; the new keys carry the new version. This is the right shape when you have many keys that share an invalidation event — better than `delete_many` over a long list.

## 9. The cache stampede

The TTL expires. 1 000 requests arrive in the next 50 ms, all miss the cache, all compute the same expensive query, all set the same key. The database is hit 1 000 times for work that should have run once. The cache stampede.

Three mitigations, in order of complexity:

### Mitigation A — `lock_and_load`

The first miss takes a Redis lock; the others wait on the lock; only the first computes:

```python
from django.core.cache import cache
import time

def get_top_authors_locked(n: int = 10) -> list[dict]:
    key = f"analytics:top_authors:n={n}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    lock_key = f"{key}:lock"
    if cache.add(lock_key, "1", timeout=10):
        # We won the lock — compute and set
        try:
            value = list(Author.objects.top_by_views(n=n).values(...))
            cache.set(key, value, timeout=60)
            return value
        finally:
            cache.delete(lock_key)
    else:
        # Someone else is computing; wait briefly and re-read
        for _ in range(10):
            time.sleep(0.05)
            cached = cache.get(key)
            if cached is not None:
                return cached
        # Lock holder is stuck; compute anyway (degrade gracefully)
        return list(Author.objects.top_by_views(n=n).values(...))
```

This is correct but adds latency to the lock-losers (up to 500 ms in the worst case). For a 60-second cache TTL on a four-times-per-second-hit dashboard, the impact is tiny — and avoids the database melt.

### Mitigation B — refresh-ahead

A background task (Celery beat) refreshes the cache every 50 seconds, before the 60-second TTL expires. The cache is always warm; no request ever computes the value synchronously.

```python
# writer/tasks.py
@shared_task
def refresh_analytics_cache():
    rows = list(Author.objects.top_by_views(n=10).values(...))
    cache.set("analytics:top_authors:n=10", rows, timeout=120)


# settings.py — beat schedule
CELERY_BEAT_SCHEDULE = {
    "refresh-analytics": {"task": "writer.tasks.refresh_analytics_cache", "schedule": 50.0},
}
```

The TTL (120 seconds) is set longer than the refresh interval (50 seconds) so even a missed refresh keeps the cache populated. The view never recomputes — it always hits.

This is the shape used in production for any read-heavy dashboard. The Week 6 mini-project does not require it; the homework references it.

### Mitigation C — probabilistic early expiration (XFetch)

When the TTL is near expiry, occasionally **pretend** it has expired and recompute. The probability rises as the TTL approaches zero. Across many requests, exactly one recomputes; the rest hit the (slightly stale) cache:

```python
import random
import math

def get_with_xfetch(key, compute, ttl=60, beta=1.0):
    # Pretend the entry expired with probability beta * delta * log(rand)
    # where delta = average compute time
    value, expires_at, delta = cache.get(key, (None, 0, 0))
    now = time.time()
    if value is None or now - beta * delta * math.log(random.random()) >= expires_at:
        start = time.time()
        value = compute()
        delta = time.time() - start
        cache.set(key, (value, now + ttl, delta), timeout=ttl)
    return value
```

Academically elegant; rarely worth it in practice. `lock_and_load` plus a beat-based refresh covers 95% of stampede situations.

## 10. The cache invalidation matrix

| Data | Freshness need | Strategy |
|------|----------------|----------|
| Homepage (logged-out) | 5 min stale fine | `@cache_page(300)` |
| Analytics dashboard | 1 min stale fine | low-level cache + beat refresh |
| Article list | seconds-fresh after publish | low-level cache + `post_save` invalidation |
| User's own draft list | always fresh | do not cache |
| Per-article view count | eventually consistent | Redis `INCR` directly, batch-flush to DB every minute |
| API token validation | seconds-fresh | low-level cache + `post_save` invalidation, TTL 30s as safety |

The rule of thumb: **the longer the TTL you can tolerate, the less invalidation complexity you need**. Push for longer TTLs; argue for staleness; let the user wait one minute. Invalidation logic is the thing you wake up at 3am to fix; TTLs are not.

## 11. Measuring the cache — hits, misses, latency

Three measurements to take, after every cache change:

1. **Hit rate.** Redis tracks `keyspace_hits` and `keyspace_misses`; `redis-cli INFO stats | grep keyspace`. Aim for 90%+ on read-heavy caches; below 50% means your TTLs are too short or the key is too narrowly scoped.
2. **Latency.** Before caching: how long did the view take? After: how long does the cache-hit path take? The win should be 5–50×. If the win is 1.2×, the cache is not helping.
3. **The cost of a miss.** The cache only helps the hits. The misses still cost full database time, plus the cache set. If misses are rare, the worst-case latency is unchanged.

`django-debug-toolbar` has a Cache panel that shows hit/miss counts per request. Open it on every cached view at least once.

## 12. The week's plan — caching the dashboard

By Saturday's mini-project session:

- The analytics dashboard view reads from a `get_dashboard_context()` helper.
- The helper reads each panel from `cache.get_or_set(...)` with a 60-second TTL.
- Cache keys: `analytics:v1:top_authors:n=10`, `analytics:v1:categories`, `analytics:v1:most_active`, `analytics:v1:top_per_cat`.
- A `post_save` signal on `Article` bumps `analytics:version`, invalidating all panels.
- A Celery beat task refreshes the cache every 50 seconds, so the post-save invalidation is a safety net rather than the only freshness mechanism.

The dashboard's wall-clock latency drops from ~200 ms (four queries) to ~5 ms (four Redis `GET`s). The database load goes from 240 queries per minute (for ten staff users) to roughly 1.2 queries per minute (beat refresh). The change is invisible to the user except as faster pages — and visible to the operations team as a smaller, calmer database.

The next two days are exercises and homework. The pieces land in the mini-project on Thursday through Saturday. By Sunday `crunchwriter` is a system: migrations are reversible, the dashboard caches itself, and thumbnails generate asynchronously without ever blocking the user.
