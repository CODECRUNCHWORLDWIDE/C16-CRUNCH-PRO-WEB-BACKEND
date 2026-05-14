# Exercise 3 — Cache-aside on the analytics dashboard

**Time:** ~2 hours. **Goal:** Apply cache-aside to each of the four analytics panels from the Week 5 mini-project. Measure the hit-path latency, write an invalidation signal on `Article.save()`, and verify the round-trip in `redis-cli MONITOR`. By the end the dashboard's hit-path is one Redis round-trip per panel; the database is touched only on miss or on invalidation.

Work in your `crunchwriter` repo. Save the write-up to `c16-week-06/exercises/03-cache.md`.

## Setup

Confirm Redis is running and reachable:

```bash
docker compose up -d redis
docker compose exec redis redis-cli PING
# PONG
```

Install `django-redis` (if not already from Exercise 2):

```bash
pip install django-redis==5.4.*
```

Configure the cache backend in `crunchwriter/settings.py`:

```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://localhost:6379/2",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
        },
        "KEY_PREFIX": "crunchwriter",
        "TIMEOUT": 60,
    }
}
DJANGO_REDIS_IGNORE_EXCEPTIONS = True
```

Verify in the shell:

```python
from django.core.cache import cache
cache.set("ping", "pong", timeout=10)
cache.get("ping")
# "pong"
```

Confirm the key exists in Redis:

```bash
docker compose exec redis redis-cli -n 2 KEYS '*'
# 1) ":1:crunchwriter:ping"
```

The Redis key format is `:VERSION:PREFIX:KEY` — Django prepends a version (default 1) and the configured `KEY_PREFIX`. Worth knowing for `MONITOR` reading.

## Part A — Cache one panel by hand

Find the analytics view from Week 5's mini-project. The shape is roughly:

```python
@staff_member_required
def analytics_dashboard(request):
    top_authors = list(Author.objects.top_by_views(n=10))
    categories = list(Category.objects.with_article_counts().with_top_article().with_avg_views())
    most_active = list(Author.objects.most_active(days=30, n=10))
    top_per_cat = Article.objects.top_n_per_category(n=3)
    return render(request, "writer/analytics_dashboard.html", {...})
```

Move each panel's queryset into a small helper, then wrap one in cache-aside. Start with `top_authors`:

```python
# writer/cache.py
from django.core.cache import cache
from writer.models import Author, Category, Article


def get_top_authors(n: int = 10) -> list[dict]:
    key = f"analytics:v1:top_authors:n={n}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    rows = list(
        Author.objects.top_by_views(n=n).values(
            "id", "username", "published_count", "total_views",
            "latest_published_at", "tier",
        )
    )
    cache.set(key, rows, timeout=60)
    return rows
```

The key contains the parameter `n=10`. Two callers with `n=10` share a cache entry; a caller with `n=20` gets a different one. Read the cache key out loud — it should read like a sentence describing what is cached.

Update the view:

```python
from writer.cache import get_top_authors

@staff_member_required
def analytics_dashboard(request):
    top_authors = get_top_authors(n=10)
    # ... other panels unchanged for now
```

## Part B — Watch the cache fill and serve

Open `redis-cli MONITOR` in one terminal:

```bash
docker compose exec redis redis-cli -n 2 MONITOR
```

Hit the dashboard twice in the browser (or via `curl` if you have the right auth):

```
First request:
  "GET" ":1:crunchwriter:analytics:v1:top_authors:n=10"     # miss
  "SET" ":1:crunchwriter:analytics:v1:top_authors:n=10" "..." "EX" "60"

Second request (within 60s):
  "GET" ":1:crunchwriter:analytics:v1:top_authors:n=10"     # hit
```

**Paste both MONITOR snippets into the write-up.** Time the requests:

```bash
time curl -s -o /dev/null http://localhost:8000/dashboard/analytics/
# first: ~200ms (database hit)
# second: ~5ms (Redis hit)
```

State the wall-clock difference. The ratio is the whole point of the exercise.

## Part C — Cache the other three panels

Apply the same pattern to the other three panels:

```python
# writer/cache.py
def get_categories():
    key = "analytics:v1:categories"
    cached = cache.get(key)
    if cached is not None:
        return cached
    rows = list(
        Category.objects.with_article_counts().with_top_article().with_avg_views()
        .values("id", "name", "article_count", "published_count", "avg_views", "top_article_title")
    )
    cache.set(key, rows, timeout=60)
    return rows


def get_most_active(days: int = 30, n: int = 10):
    key = f"analytics:v1:most_active:days={days}:n={n}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    rows = list(
        Author.objects.most_active(days=days, n=n).values(
            "id", "username", "recent_count", "recent_views",
        )
    )
    cache.set(key, rows, timeout=60)
    return rows


def get_top_per_category(n: int = 3):
    key = f"analytics:v1:top_per_cat:n={n}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    rows = list(
        Article.objects.top_n_per_category(n=n)   # already returns a list from Week 5
    )
    # Note: if top_n_per_category returns Article instances rather than dicts, materialise:
    serialised = [{"id": a.id, "title": a.title, "category_id": a.category_id, "view_count": a.view_count} for a in rows]
    cache.set(key, serialised, timeout=60)
    return serialised
```

Update the view to use all four helpers:

```python
@staff_member_required
def analytics_dashboard(request):
    return render(request, "writer/analytics_dashboard.html", {
        "top_authors": get_top_authors(n=10),
        "categories": get_categories(),
        "most_active": get_most_active(days=30, n=10),
        "top_per_cat": get_top_per_category(n=3),
    })
```

Restart the dev server. The first hit fills four cache keys; subsequent hits read four `GET`s. **Paste the MONITOR output** showing four sets on the first request and four hits on the second.

## Part D — Invalidate on `Article.save()`

The cache is wrong the moment an article is published. Hook `post_save`:

```python
# writer/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache

from writer.models import Article


CACHE_KEYS = [
    "analytics:v1:top_authors:n=10",
    "analytics:v1:categories",
    "analytics:v1:most_active:days=30:n=10",
    "analytics:v1:top_per_cat:n=3",
]


@receiver(post_save, sender=Article)
def invalidate_analytics_on_article_save(sender, instance, **kwargs):
    cache.delete_many(CACHE_KEYS)
```

Wire it: in `writer/apps.py`:

```python
class WriterConfig(AppConfig):
    name = "writer"

    def ready(self):
        import writer.signals  # noqa: F401
```

Test the invalidation in the shell:

```python
from django.core.cache import cache
from writer.models import Article
from writer.cache import get_top_authors

# Warm the cache
get_top_authors(n=10)
cache.get("analytics:v1:top_authors:n=10")
# returns the list

# Save an article
a = Article.objects.first()
a.save()

# The cache should be cleared
cache.get("analytics:v1:top_authors:n=10")
# None
```

**Paste the shell session showing the cache filled, then cleared by the save.** State in the write-up: this is the simplest invalidation strategy; the cost is that every write defeats the cache. For a write-heavy workload, the alternative is the versioned-key pattern from Lecture 3 section 8.

## Part E — Hardening — only invalidate when relevant fields change

A `post_save` on every `Article` save invalidates even when the change is irrelevant — bumping `updated_at`, changing the slug, adjusting a non-displayed field. Narrow the trigger:

```python
@receiver(post_save, sender=Article)
def invalidate_analytics_on_article_save(sender, instance, created, update_fields=None, **kwargs):
    # Always invalidate on creation
    if created:
        cache.delete_many(CACHE_KEYS)
        return
    # On update, only invalidate if a cache-relevant field changed
    cache_relevant = {"status", "view_count", "published_at", "author_id", "category_id"}
    if update_fields is None or set(update_fields) & cache_relevant:
        cache.delete_many(CACHE_KEYS)
```

The catch: `update_fields=None` (the default for `save()`) means "Django does not know which fields changed". In that case, invalidate conservatively. The optimisation only kicks in when callers do `instance.save(update_fields=["slug"])` — explicit and narrow.

Test:

```python
a = Article.objects.first()

get_top_authors(n=10)
a.save(update_fields=["slug"])
cache.get("analytics:v1:top_authors:n=10")
# Still cached — slug is not in the relevant set

get_top_authors(n=10)
a.save(update_fields=["view_count"])
cache.get("analytics:v1:top_authors:n=10")
# Cleared — view_count is relevant
```

**Paste both shell sessions.**

## Part F — Measure the hit rate

Hit the dashboard 100 times (the simplest: a `for i in range(100): time.sleep(0.5)` loop in a shell, or `ab -n 100 -c 4 http://localhost:8000/dashboard/analytics/` if you have Apache Bench):

```bash
ab -n 100 -c 4 -C "sessionid=YOUR_STAFF_SESSION" http://localhost:8000/dashboard/analytics/
```

Then inspect Redis:

```bash
docker compose exec redis redis-cli -n 2 INFO stats | grep -E "keyspace_hits|keyspace_misses"
# keyspace_hits:392
# keyspace_misses:8
```

Hit rate = 392 / (392 + 8) = 98%. The cache TTL is 60 seconds; with 100 requests over 50 seconds, only one full miss-and-set cycle per panel is expected. **Paste the INFO output and compute the hit rate.**

In the write-up: under what circumstance would the hit rate be 50%? (Answer: the TTL is shorter than the inter-request gap, or the cache key includes a frequently-changing parameter, or invalidation is firing on every save.)

## Part G — Write-up

`c16-week-06/exercises/03-cache.md` should contain:

1. The cache backend configuration in `settings.py`.
2. The `writer/cache.py` module with all four helpers.
3. The `MONITOR` snippet showing the first request (4 sets) and the second (4 hits).
4. The wall-clock latency comparison: cold vs warm dashboard, in milliseconds.
5. The `post_save` signal code.
6. The shell session demonstrating cache fill → save → cache cleared.
7. The narrowed signal with `update_fields` filtering, with two shell sessions showing the narrowing in action.
8. The Redis hit-rate measurement (`INFO stats`), with the percentage computed.
9. Three short paragraphs of reflection — see questions inside each section.

## Acceptance criteria

- [ ] `CACHES` setting is configured with `django-redis`, separate Redis database 2.
- [ ] `writer/cache.py` has four helpers, each with a clear cache key and a 60-second TTL.
- [ ] `writer/signals.py` has the `post_save` invalidator, with the `update_fields` narrowing.
- [ ] The `MONITOR` evidence is included for both fill and hit.
- [ ] The latency comparison is in the write-up with actual numbers.
- [ ] The hit-rate measurement is in the write-up with `INFO stats` output.
- [ ] Write-up is 250–450 lines.

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Cache-aside correctness | 25% | All four helpers cache; keys are well-named; TTLs are deliberate |
| Invalidation hygiene | 25% | `post_save` fires only on relevant fields; the narrow case is demonstrated |
| Measurement | 20% | Latency and hit-rate numbers are real, with the commands that produced them |
| MONITOR evidence | 15% | Both fill and hit MONITOR snippets are pasted |
| Reflection | 15% | Specific answers to the three questions, not generic ones |

## Hints

- **`cache.delete_many(keys)`** is one Redis `DEL` command, regardless of list length. The cost is constant in the network round-trip; one `DEL` of 4 keys is essentially the same as `DEL` of 1.
- **`cache.set` returns nothing**; do not check its return value. To verify the set worked, `cache.get` after.
- **`IGNORE_EXCEPTIONS: True`** treats Redis failures as cache misses. To exercise this, stop Redis (`docker compose stop redis`), hit the dashboard, and confirm the page still renders (just slowly, because every panel misses). Then restart Redis.
- **`KEY_PREFIX`** is applied automatically; do not include it in your code. `cache.get("analytics:v1:top_authors:n=10")` retrieves the key `crunchwriter:analytics:v1:top_authors:n=10` from Redis.
- **`apps.py`'s `ready()`** is called once per process. Importing signals there registers them. Do not register signals at the top of `models.py` — that runs early and can cause import-order pain.
- **`Apache Bench`** (`ab`) is the simplest load generator. Alternatives: `wrk`, `siege`, `hey`. Pick one and use it consistently.

## What this prepares you for

The mini-project (Friday–Saturday) ties the three exercises together:

- A migration adds `image` and `thumbnails_generated_at` to `Article`.
- A view accepts the upload, queues a Celery task, returns 202.
- The Celery task generates three thumbnail sizes idempotently.
- The article list view caches its rendered fragment for 60 seconds; saving an article invalidates the cache; the thumbnail-generation task's completion bumps a version that re-warms the article's cache entry.

By Saturday the dashboard caches itself, the article list is fast, the upload is non-blocking, and a worker quietly processes every image without a single user noticing.
