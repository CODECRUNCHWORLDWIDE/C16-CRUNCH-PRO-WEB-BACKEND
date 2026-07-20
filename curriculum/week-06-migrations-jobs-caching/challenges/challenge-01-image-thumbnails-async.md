# Challenge 1 — Image thumbnails, asynchronously

**Time:** ~3 hours. **Difficulty:** Medium. **Goal:** Build a Celery task that takes an `Article` instance, opens its uploaded image, generates three thumbnail sizes, optimises them, writes them to disk, and marks the article processed. The task is idempotent, retries on `IOError`, and respects a soft time limit. Then submit 50 articles to the worker concurrently and measure the throughput.

## Why this exists

The mini-project for Week 6 is image upload with async thumbnail generation. The challenge is the **task body** — the piece that turns one row into three images on disk. Everything else (the upload form, the article list, the cache) is incidental; the value is in the worker doing the work right.

A team will reach this challenge in their actual job within their first six months. The shape — "user uploads, server queues, worker processes, status updates" — is the canonical async pipeline. Doing it once cleanly leaves a template you reuse for every variant.

## What you build

A Celery task `generate_thumbnails(article_id: int)` that:

1. Loads `Article.objects.get(pk=article_id)`. If `thumbnails_generated_at` is non-null, returns immediately (idempotency).
2. Opens the file at `article.image.path` with Pillow.
3. Generates three resized variants: `thumb_small` (200×200), `thumb_medium` (600×400), `thumb_large` (1200×800). Use `Image.thumbnail((w, h), Image.LANCZOS)` for high quality.
4. Saves each variant as `<original_path>.<size>.webp` (the article keeps a list of thumbnail paths, one column per size or a single JSON column).
5. Sets `article.thumbnails_generated_at = timezone.now()` and saves the model with `update_fields=[...]`.
6. On `IOError` (file not found, disk full, network mount glitch), retries up to 3 times with exponential backoff and jitter.
7. Respects a soft time limit of 30 seconds; on `SoftTimeLimitExceeded`, logs a warning and re-raises so Celery marks the task as failed.

## Setup

If you have not yet wired Celery from Exercise 2, do it now — the lecture notes and Exercise 2 walk through every step. The challenge assumes you can run a worker and call `task.delay(...)` from the shell.

Install Pillow:

```bash
pip install 'Pillow==10.*'
```

Add an `ImageField` and the timestamp to `Article` (you will write this migration formally in the mini-project; for the challenge, the schema can be loose):

```python
class Article(models.Model):
    ...
    image = models.ImageField(upload_to="articles/originals/", null=True, blank=True)
    thumbnails_generated_at = models.DateTimeField(null=True, blank=True)
    thumb_small_path = models.CharField(max_length=300, null=True, blank=True)
    thumb_medium_path = models.CharField(max_length=300, null=True, blank=True)
    thumb_large_path = models.CharField(max_length=300, null=True, blank=True)
```

```bash
python manage.py makemigrations writer
python manage.py migrate writer
```

In `crunchwriter/settings.py`:

```python
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"
```

In your dev URL config:

```python
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # ...
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

Seed at least one article with an uploaded image. The simplest path: open Django admin, edit any article, attach an image, save. Confirm `article.image.path` exists on disk.

## The task

Create `writer/tasks.py` (or extend the one from Exercise 2):

```python
import logging
import os
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone
from PIL import Image

from writer.models import Article

logger = logging.getLogger(__name__)


SIZES = {
    "small":  (200, 200),
    "medium": (600, 400),
    "large":  (1200, 800),
}


@shared_task(
    bind=True,
    autoretry_for=(IOError, OSError),
    retry_backoff=True,
    retry_backoff_max=30,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=30,
    time_limit=45,
)
def generate_thumbnails(self, article_id: int) -> dict:
    """
    Generate three thumbnails for the uploaded image attached to article_id.
    Idempotent: returns immediately if thumbnails_generated_at is already set.
    Retries on IOError/OSError up to 3 times with exponential backoff.
    """
    try:
        article = Article.objects.get(pk=article_id)
    except Article.DoesNotExist:
        logger.warning("article %s vanished before thumbnail generation", article_id)
        return {"status": "skipped", "reason": "article_not_found"}

    if article.thumbnails_generated_at is not None:
        logger.info("article %s already processed; skipping", article_id)
        return {"status": "skipped", "reason": "already_processed"}

    if not article.image:
        logger.warning("article %s has no image; skipping", article_id)
        return {"status": "skipped", "reason": "no_image"}

    original_path = article.image.path
    if not os.path.exists(original_path):
        # Will trigger autoretry_for=IOError if we raise IOError; the file may appear after a sync
        raise IOError(f"file missing: {original_path}")

    try:
        results = {}
        with Image.open(original_path) as im:
            im.load()
            for name, dims in SIZES.items():
                copy = im.copy()
                copy.thumbnail(dims, Image.LANCZOS)
                out_path = f"{original_path}.{name}.webp"
                copy.save(out_path, format="WEBP", quality=85, method=6)
                results[name] = out_path

        article.thumb_small_path = results["small"]
        article.thumb_medium_path = results["medium"]
        article.thumb_large_path = results["large"]
        article.thumbnails_generated_at = timezone.now()
        article.save(update_fields=[
            "thumb_small_path", "thumb_medium_path", "thumb_large_path",
            "thumbnails_generated_at",
        ])
        return {"status": "ok", "article_id": article_id, "sizes": list(results.keys())}

    except SoftTimeLimitExceeded:
        logger.warning("soft time limit exceeded for article %s", article_id)
        raise
```

Five things to note in the code:

1. **`bind=True`** makes `self.request` available — useful for logging the retry count.
2. **`autoretry_for=(IOError, OSError)`** covers file-system flakiness. `OSError` is Pillow's class for "could not parse the image"; `IOError` is older code's class for "file not found". On Python 3 they are aliases, but the explicit list signals intent.
3. **Idempotency check on `thumbnails_generated_at`** — the task may run twice (retry, duplicate delivery, manual re-queue). The second run sees the timestamp and exits.
4. **`update_fields=[...]`** narrows the SQL `UPDATE` to four columns. Faster, and reduces the risk of overwriting fields a concurrent process modified.
5. **`SoftTimeLimitExceeded` is re-raised**, not swallowed. Celery treats this as a failure; the task is not re-queued (because the cause was a real timeout, not a transient error). The hard limit (45s) is the safety net if the soft handler hangs.

## Submit and watch

Restart the worker so it loads the new task:

```bash
celery -A crunchwriter worker -l info --concurrency=4
```

From the shell:

```python
from writer.models import Article
from writer.tasks import generate_thumbnails

# Pick an article with an image
article = Article.objects.exclude(image="").first()
print(article.id, article.image.path)

# Queue one task
result = generate_thumbnails.delay(article.id)
print(result.id)
result.get(timeout=60)
# {'status': 'ok', 'article_id': 42, 'sizes': ['small', 'medium', 'large']}
```

Verify on disk:

```bash
ls -la media/articles/originals/*.webp
# Three files: <basename>.small.webp, .medium.webp, .large.webp
```

Verify idempotency — call the task again:

```python
result = generate_thumbnails.delay(article.id)
result.get(timeout=10)
# {'status': 'skipped', 'reason': 'already_processed'}
```

**Paste both shell sessions and one `ls -la` of the generated files into the write-up.**

## Concurrent load test

Queue 50 articles at once:

```python
import time
from writer.models import Article
from writer.tasks import generate_thumbnails

# Reset the timestamp so the task does real work
articles = list(Article.objects.exclude(image="")[:50])
Article.objects.filter(id__in=[a.id for a in articles]).update(thumbnails_generated_at=None)

start = time.time()
results = [generate_thumbnails.delay(a.id) for a in articles]
for r in results:
    r.get(timeout=120)
elapsed = time.time() - start
print(f"50 tasks in {elapsed:.1f}s — {50/elapsed:.1f} tasks/sec")
```

Run with `--concurrency=1`, then `--concurrency=4`. **Compare the timings.** With 4 worker processes, expect roughly 3–4× throughput (not 4× — the bottleneck shifts to disk I/O, image decoding, or both).

In the write-up:

- The throughput at each concurrency level.
- Which resource is the bottleneck: CPU (Pillow decoding), disk (writing the WEBP files), or coordination overhead?
- At what concurrency level does throughput stop increasing? Why?

## Inject failure — exercise the retry

Add a fault-injection hook to the task (temporarily, for the test):

```python
import random

@shared_task(..., autoretry_for=(IOError,), ...)
def generate_thumbnails(self, article_id: int) -> dict:
    if random.random() < 0.3 and self.request.retries == 0:
        raise IOError("simulated transient failure")
    # ... rest unchanged
```

Reset and re-queue 50 articles. Most succeed on the first try; about 30% retry once. **Paste the worker log lines** showing a retry happening — you should see `Retry in Ns: IOError(...)` and a subsequent `succeeded`.

Then remove the fault-injection. **Confirm** the production version of the task no longer has random failure injection.

## Write-up

`c16-week-06/challenges/01-thumbnails.md` should contain:

1. The full task code (`writer/tasks.py`).
2. The migration that added the image and timestamp fields.
3. The first successful run (shell + worker log + `ls -la` of generated files).
4. The idempotency demonstration (second `delay` returns immediately).
5. The concurrent load test: timings at `--concurrency=1` and `--concurrency=4`, with the throughput ratio.
6. A one-paragraph analysis of the bottleneck (CPU vs disk).
7. The fault-injection retry demonstration (worker log).
8. A short reflection (~200 words): what would change if the thumbnails were stored in S3 instead of local disk? What would change if there were 10 000 articles in the queue at once?

## Acceptance criteria

- [ ] The task lives in `writer/tasks.py` and is named `generate_thumbnails`.
- [ ] Three sizes are generated: small (200×200), medium (600×400), large (1200×800), as WEBP at quality 85.
- [ ] The task is idempotent — second call with the same `article_id` returns the "already processed" status without re-generating.
- [ ] Retries with `autoretry_for=(IOError, OSError)`, `retry_backoff`, `retry_jitter`, `max_retries=3`.
- [ ] Soft time limit of 30 seconds; hard limit of 45 seconds.
- [ ] The concurrent load test runs 50 articles and reports throughput at two concurrency levels.
- [ ] The retry mechanism is exercised and the worker log is captured.
- [ ] Write-up is 200–350 lines.

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Task correctness | 25% | The three sizes are correct; idempotency works; the file paths are saved on the model |
| Retry semantics | 20% | Retries on `IOError`, backoff is exponential, the log shows a retry happening |
| Idempotency | 15% | The second call returns immediately; this is demonstrated, not just claimed |
| Concurrent throughput | 15% | Real numbers at two concurrency levels, with a bottleneck analysis |
| Time-limit handling | 10% | Soft limit is set, the soft handler is in the code, the hard limit is documented |
| Write-up clarity | 15% | A peer can reproduce the throughput numbers within ±20% |

## Hints

- **`Image.LANCZOS`** is the high-quality resampling filter. The older `Image.ANTIALIAS` is deprecated; `LANCZOS` is the modern alias.
- **`image.thumbnail(dims)`** mutates the image in place. Use `image.copy().thumbnail(dims)` so the original is preserved for the next size.
- **WEBP at quality 85** is the modern default for thumbnails: 30–50% smaller than JPEG, support is universal in modern browsers. Stick with WEBP unless you have a specific compatibility requirement.
- **`article.image.path`** is the filesystem path; `article.image.url` is the public URL Django serves. The task should use `.path`; the template uses `.url`.
- **`time.sleep(N)` in the task body for testing** — to make the soft time limit fire, set `soft_time_limit=2` and add a `time.sleep(5)` inside. Remove before submitting.
- **`celery -A crunchwriter inspect active`** while the 50-task load test is running shows what each worker process is doing. Useful for confirming concurrency is real.

## Stretch (optional)

- **S3 upload.** Replace the local-disk write with `boto3.put_object` to an S3 bucket. The task body shape is the same; the failure modes change (network instead of disk). Use `moto` for tests.
- **A second task after thumbnails.** Chain the thumbnail task into a "notify the author" task using `chain(generate_thumbnails.s(article_id), notify_author.s())`. The second task fires only when the first succeeds.
- **Progress reporting.** Use `self.update_state(state="PROGRESS", meta={"current": 1, "total": 3})` between sizes. The producer (or `flower`) can read the progress.
- **A different image library.** Re-implement using `wand` (ImageMagick) or `vips` (libvips). Compare throughput; libvips is typically 2–5× faster than Pillow for thumbnail generation.

## What this prepares you for

The mini-project is "this challenge, but with the surrounding UI". The upload form, the article list rendering the thumbnail, the test for the upload-to-thumbnail round-trip — all of it sits around the task you wrote here. If the challenge is done cleanly, the mini-project is two hours of view code and a template.

Week 7 introduces FastAPI. The same task — `generate_thumbnails` — is callable from the FastAPI side using `celery_app.send_task("writer.tasks.generate_thumbnails", args=[article_id])`. The two surfaces (Django, FastAPI) share one worker fleet. This is the Phase-3 payoff for doing Phase 2's infrastructure right.
