# Mini-Project — Image upload and async thumbnail generation

> Build the image-upload feature for `crunchwriter`. The author uploads an original; the request returns in under 100 ms; a Celery worker generates three thumbnail sizes; the article list shows the right size the moment it is ready. The migration is reversible. The thumbnail task is idempotent and retries on transient errors. The analytics dashboard from Week 5 caches itself in Redis with a `post_save` invalidation. By Sunday `crunchwriter` is a system, not just a Django project.

**Estimated time:** 7 hours, spread across Thursday–Saturday.

## What you build

A new flow on top of `crunchwriter`:

1. **Image upload.** Authors attach an image to an article via the existing edit form. The upload goes to `media/articles/originals/`. The request returns in under 100 ms; no synchronous thumbnail work happens during the request.
2. **Async thumbnail generation.** A Celery task `generate_thumbnails(article_id)` picks up the article, generates three sizes (small 200×200, medium 600×400, large 1200×800), optimises them as WEBP, writes to disk, and updates the article with the three thumbnail paths plus `thumbnails_generated_at`.
3. **Article list with thumbnails.** The article list template renders the medium thumbnail if available; otherwise renders a placeholder. The list view is covered by `assertNumQueries(2)`.
4. **Cached analytics dashboard.** The Week 5 dashboard panels are wrapped in `cache.get_or_set` with 60-second TTLs. A `post_save` signal on `Article` invalidates the relevant cache keys. A beat-scheduled task refreshes the cache every 50 seconds, keeping it warm.

The full pipeline — upload → 202 → worker → article list shows thumbnail — is demonstrable end-to-end. The user uploads; the server returns 202; the user refreshes 10 seconds later and the thumbnail appears.

## Acceptance criteria

### Migrations

- [ ] Migration A: add `image = ImageField(upload_to=...)`, `thumbnails_generated_at = DateTimeField(null=True, blank=True)`, `thumb_small_path`, `thumb_medium_path`, `thumb_large_path = CharField(max_length=300, null=True, blank=True)`. All nullable.
- [ ] Migration B: nothing required, but if you precompute thumbnails for existing seeded images, write a `RunPython` data migration with both `forwards` and `reverse`.
- [ ] Both migrations apply and reverse cleanly. Pasted `sqlmigrate` output for each.

### Upload flow

- [ ] Article edit/create form accepts an image. The form is `enctype="multipart/form-data"` (else it silently drops the file).
- [ ] On successful upload, the view queues `generate_thumbnails.delay(article.id)` and returns immediately. The user sees a "processing" placeholder until the next page load.
- [ ] The upload view is covered by a test using `CELERY_TASK_ALWAYS_EAGER=True` that asserts the thumbnail files exist on disk after the response.

### Thumbnail task

- [ ] `writer/tasks.py` has `generate_thumbnails(article_id)`.
- [ ] Decorator: `@shared_task(bind=True, autoretry_for=(IOError, OSError), retry_backoff=True, retry_jitter=True, max_retries=3, soft_time_limit=30, time_limit=45)`.
- [ ] Idempotent: returns immediately if `thumbnails_generated_at` is non-null.
- [ ] Generates three WEBP files with `Pillow.Image.thumbnail((w, h), Image.LANCZOS)`.
- [ ] Saves the model with `update_fields=[...]` to scope the SQL UPDATE.
- [ ] Tests in `writer/tests/test_tasks.py` covering: a fresh article round-trips through the task; the second call returns "skipped"; a missing file raises `IOError` and the autoretry mechanism activates.

### Article list

- [ ] The article list template shows the medium thumbnail if `thumb_medium_path` is set; otherwise a placeholder graphic or text.
- [ ] The list view emits exactly 2 queries (`assertNumQueries(2)`: one count for pagination, one page).
- [ ] No N+1 — the thumbnail path is on the same row as the article, so no extra query is needed.

### Cached dashboard

- [ ] The Week 5 analytics dashboard's four panels each go through `cache.get_or_set` with a 60-second TTL.
- [ ] Cache keys follow the lecture's scheme: `analytics:v1:top_authors:n=10`, etc.
- [ ] A `post_save` signal on `Article` invalidates the four keys. The signal narrows on `update_fields` to avoid unnecessary invalidation.
- [ ] A Celery beat task refreshes the cache every 50 seconds.
- [ ] A test confirms: cold dashboard → 4 cache misses + 4 DB queries; warm dashboard → 4 cache hits + 0 DB queries.

### Documentation

- [ ] `c16-week-06/mini-project/README.md` (your portfolio) — see "The write-up" below.
- [ ] One screenshot of the article list with a thumbnail rendered. One of the dashboard. One of `flower` showing the task runs. (Or paste the equivalent terminal output if you do not want to add image files to the repo.)
- [ ] All artefacts committed: models, migrations, views, templates, tasks, signals, tests, the portfolio README.

## Suggested order of operations

### Phase 1 — Migration and model changes (45 min)

Edit `writer/models.py` to add the five new fields. All nullable so existing rows are unaffected:

```python
class Article(models.Model):
    ...
    image = models.ImageField(upload_to="articles/originals/", null=True, blank=True)
    thumb_small_path = models.CharField(max_length=300, null=True, blank=True)
    thumb_medium_path = models.CharField(max_length=300, null=True, blank=True)
    thumb_large_path = models.CharField(max_length=300, null=True, blank=True)
    thumbnails_generated_at = models.DateTimeField(null=True, blank=True)
```

```bash
python manage.py makemigrations writer
python manage.py sqlmigrate writer 00XX
# read the SQL — five ALTER TABLE ADD COLUMN statements, all nullable, all metadata-only on PG 11+
python manage.py migrate writer
```

Confirm in the shell:

```python
from writer.models import Article
Article.objects.first().image
# <ImageFieldFile: None> — empty, as expected for existing rows
```

### Phase 2 — The Celery task (90 min)

Drop in the task from Challenge 1 if you completed it. Otherwise, write it now — the challenge's brief is the lecture's brief; both produce the same `writer/tasks.py`.

Test the task end-to-end before wiring it to a view:

```python
from writer.models import Article
from writer.tasks import generate_thumbnails

article = Article.objects.create(
    title="test", body="...", author=...,  # whatever your model requires
)
# Manually attach an image
with open("test.jpg", "rb") as f:
    article.image.save("test.jpg", File(f))

result = generate_thumbnails.delay(article.id)
result.get(timeout=60)
# {'status': 'ok', ...}

article.refresh_from_db()
print(article.thumb_medium_path)
# /path/to/media/articles/originals/test.jpg.medium.webp
```

If this works in the shell, you can wire it to the view.

### Phase 3 — The upload view (60 min)

Wire the upload into your existing article create/edit view. The simplest version:

```python
# writer/views/articles.py (or wherever your edit view lives)
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from writer.forms import ArticleForm
from writer.tasks import generate_thumbnails


@login_required
def article_edit(request, pk):
    article = get_object_or_404(Article, pk=pk, author=request.user)
    if request.method == "POST":
        form = ArticleForm(request.POST, request.FILES, instance=article)
        if form.is_valid():
            article = form.save()
            # If the image was changed, reset the timestamp and queue a new generation
            if "image" in form.changed_data and article.image:
                Article.objects.filter(pk=article.pk).update(thumbnails_generated_at=None)
                generate_thumbnails.delay(article.pk)
            return redirect("writer:article_detail", pk=article.pk)
    else:
        form = ArticleForm(instance=article)
    return render(request, "writer/article_edit.html", {"form": form, "article": article})
```

Three details:

1. `request.FILES` — without this argument the form processes the text fields but silently drops the file.
2. **Reset the timestamp** before queueing. Otherwise the idempotency guard returns immediately for any subsequent upload to the same article.
3. **Queue via `delay()`**, not synchronously. The view returns 100 ms after `form.save()`; the user does not wait.

Update the form template:

```django
<form method="post" enctype="multipart/form-data">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">Save</button>
</form>
```

The `enctype` matters. Without it, files do not arrive at the server.

### Phase 4 — The article list template (30 min)

In the list template (`writer/article_list.html` or equivalent):

```django
{% for article in articles %}
  <article class="card">
    {% if article.thumb_medium_path %}
      <img src="{{ MEDIA_URL }}{{ article.thumb_medium_path|cut:MEDIA_ROOT }}" alt="" width="600" height="400">
    {% elif article.image %}
      <div class="placeholder">processing thumbnail…</div>
    {% else %}
      <div class="placeholder">no image</div>
    {% endif %}
    <h2><a href="{{ article.get_absolute_url }}">{{ article.title }}</a></h2>
    <p>{{ article.body|truncatewords:30 }}</p>
  </article>
{% endfor %}
```

The path-to-URL conversion is fiddly; the cleanest fix is to store the **URL** on the model, not the absolute filesystem path. If you store the path, write a small `get_thumb_medium_url()` method on the model and call it in the template.

Confirm `assertNumQueries(2)`:

```python
class ArticleListTests(TestCase):
    def test_list_query_count(self):
        with self.assertNumQueries(2):
            response = self.client.get(reverse("writer:article_list"))
        self.assertEqual(response.status_code, 200)
```

If the count is 3 or higher, you have an N+1 somewhere — most likely the template traverses `article.author.username` without `select_related("author")` in the view. Fix and re-test.

### Phase 5 — Cache the dashboard (60 min)

From Exercise 3, you already have `writer/cache.py` with four helpers and `writer/signals.py` with the `post_save` invalidator. Verify both still work after the model changes from Phase 1:

```bash
python manage.py shell
```

```python
from writer.cache import get_top_authors
get_top_authors(n=10)  # warm
from writer.models import Article
Article.objects.first().save()  # should invalidate
from django.core.cache import cache
cache.get("analytics:v1:top_authors:n=10")  # None
```

Then add a beat schedule:

```python
# settings.py
CELERY_BEAT_SCHEDULE = {
    "refresh-analytics-cache-every-50s": {
        "task": "writer.tasks.refresh_analytics_cache",
        "schedule": 50.0,
    },
}
```

```python
# writer/tasks.py
from celery import shared_task
from writer.cache import get_top_authors, get_categories, get_most_active, get_top_per_category


@shared_task
def refresh_analytics_cache():
    # Force a recomputation by deleting first, then calling the helpers
    from django.core.cache import cache
    cache.delete_many([
        "analytics:v1:top_authors:n=10",
        "analytics:v1:categories",
        "analytics:v1:most_active:days=30:n=10",
        "analytics:v1:top_per_cat:n=3",
    ])
    get_top_authors(n=10)
    get_categories()
    get_most_active(days=30, n=10)
    get_top_per_category(n=3)
```

Run the beat process:

```bash
celery -A crunchwriter beat -l info
```

Watch the worker (already running). Every 50 seconds you should see the worker pick up `refresh_analytics_cache` and the four cache helpers run sequentially.

### Phase 6 — Tests (60 min)

Three test classes to add (or extend from Exercises 2 and 3):

```python
# writer/tests/test_image_upload.py

class ImageUploadTests(TestCase):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    def test_upload_generates_thumbnails(self):
        self.client.force_login(self.author)
        with open("writer/tests/fixtures/test_image.jpg", "rb") as f:
            response = self.client.post(
                reverse("writer:article_edit", args=[self.article.pk]),
                {"title": "x", "body": "y", "image": f},
                follow=True,
            )
        self.article.refresh_from_db()
        self.assertIsNotNone(self.article.thumbnails_generated_at)
        self.assertTrue(os.path.exists(self.article.thumb_small_path))
        self.assertTrue(os.path.exists(self.article.thumb_medium_path))
        self.assertTrue(os.path.exists(self.article.thumb_large_path))


class ThumbnailIdempotencyTests(TestCase):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    def test_second_call_returns_skipped(self):
        # ... attach image, call once
        result = generate_thumbnails.delay(self.article.pk).get()
        self.assertEqual(result["status"], "ok")
        # call again
        result = generate_thumbnails.delay(self.article.pk).get()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "already_processed")


class DashboardCacheTests(TestCase):
    def test_dashboard_cold_then_warm(self):
        cache.clear()
        with self.assertNumQueries(4):    # four panels each emit one SQL
            self.client.get(reverse("writer:analytics_dashboard"))
        with self.assertNumQueries(0):    # warm hits cache
            self.client.get(reverse("writer:analytics_dashboard"))

    def test_save_invalidates_cache(self):
        self.client.get(reverse("writer:analytics_dashboard"))  # warm
        self.assertIsNotNone(cache.get("analytics:v1:top_authors:n=10"))
        Article.objects.first().save()
        self.assertIsNone(cache.get("analytics:v1:top_authors:n=10"))
```

Run:

```bash
python manage.py test writer.tests
```

All tests should pass.

### Phase 7 — The portfolio README (45 min)

`c16-week-06/mini-project/README.md`. Sections:

- **The build** — what the upload flow does, who it is for, the four pieces (migration, upload view, worker task, cached dashboard). 1 paragraph.
- **The architecture diagram** — text-art is fine:

  ```
  Browser → Django view → 202 + queue task →    [Redis broker]
                                                       │
                                                       ▼
                                                 [Celery worker]
                                                       │
                                                       ▼
                                                 Pillow + disk
                                                       │
                                                       ▼
                                                 Article.save(update_fields=...)
                                                       │
                                                       ▼
                                                 post_save → cache.delete(...)
  ```

- **The four queries** — one bullet per dashboard panel, with the cache key and the 60s TTL.
- **The thumbnail task** — link to `writer/tasks.py`; one paragraph on retry policy and idempotency mechanism.
- **The decision log** — three non-obvious decisions defended. Examples:
  - "Stored the thumbnail paths on the `Article` model rather than a separate `Thumbnail` model, because the relationship is strict 1:1 and the join would have been pointless overhead. The trade-off is that adding a fourth size requires a migration; for a 3-size system this is fine."
  - "Used `post_save` signal-based invalidation rather than a TTL-only strategy because dashboard freshness after publishing a new article is part of the product."
  - "Set `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` because the thumbnail task takes 1–3 seconds and we want fast workers to keep picking up new tasks, not sit on a queue of four."
- **What I would do next** — 1 paragraph. Move thumbnails to S3, add a CDN URL, add a `tsvector` index on article body for full-text search.
- **Screenshots / terminal pastes** — see the acceptance criteria.

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Migration hygiene | 15% | Nullable additions; `sqlmigrate` clean; reverses work |
| Upload flow | 15% | Form has `enctype`; view queues, returns 100ms; timestamp resets on new upload |
| Task quality | 20% | Idempotent, retries on `IOError`, soft+hard time limits, `update_fields` on save |
| Caching | 20% | Four panels cached; `post_save` invalidation works; beat refreshes every 50s |
| Test coverage | 15% | All three test classes pass; `assertNumQueries` is used on each surface |
| Polish | 15% | Article list renders thumbnails; placeholder works; the decision log has 3 specific entries |

## What this prepares you for

- **Week 7** introduces FastAPI. The same `generate_thumbnails` task is callable from FastAPI via `celery_app.send_task(...)`. The two surfaces share one worker fleet. Your Phase 2 infrastructure is now Phase 3 leverage.
- **Week 10** runs the whole stack in Docker Compose. The `worker` and `beat` services join `web`, `db`, and `redis` in one `docker compose up`. You will copy the patterns from this week's mini-project verbatim.
- **Week 11** adds CI. The test class `AsynchronousThumbnailTests` runs in GitHub Actions with `CELERY_TASK_ALWAYS_EAGER=True` and a Redis service container. The day a refactor breaks the upload pipeline, CI catches it.
- **Week 12** ships this to production. The image upload is the most exercised feature of a content site. If it is slow (synchronous thumbnails) or unreliable (no retry), users notice within minutes. The architecture you built this week is the reason they will not.

## Submission

When done: push, then walk through the demo with a peer. Steps:

1. Upload an image via the edit form. Time the request — it should return in well under 1 second.
2. In a second tab, open the analytics dashboard. The page loads in under 10 ms (cache hit).
3. In a third terminal, `celery -A crunchwriter inspect active` — the thumbnail task should be running or just finished.
4. Reload the article list. The thumbnail appears.

If your peer says "I cannot tell whether the thumbnail generation is async or sync from watching the page", that is the right answer. The user does not notice the asynchronous handoff. That is the point.

Then continue to [Week 7 — FastAPI Fundamentals](../../week-07-fastapi-fundamentals/) — where a new service starts reading from the same database and queueing tasks against the same broker.
