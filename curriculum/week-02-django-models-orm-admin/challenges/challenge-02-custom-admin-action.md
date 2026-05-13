# Challenge 2 — Custom Admin Action with Failure Handling

**Time:** ~90 minutes. **Difficulty:** Medium.

## Problem

Build a custom admin action that does something useful AND handles failure gracefully — partial-success, error logging, transactional safety, and a confirmation screen for irreversible actions.

## What to build

In your `crunchwriter` admin, add an action **"Republish with new slug"** that:

1. Operates on selected articles.
2. For each, regenerates the slug from the current title (using `slugify`).
3. Validates that the new slug is unique. If not, suffixes `-2`, `-3`, etc.
4. Sets `status="published"` and `published_at=now()`.
5. Wraps everything in a database transaction.
6. Logs success/failure per article using the admin's messaging framework.
7. **Confirms before applying** if more than 10 articles are selected, via an interstitial confirmation page.

## Acceptance criteria

- [ ] `admin.py` contains the action `republish_with_new_slug`.
- [ ] Selecting articles + applying the action updates their slug and status atomically.
- [ ] If you select articles where two have the same title, the action assigns distinct slugs (`hello-world`, `hello-world-2`).
- [ ] The admin's success message reports both the count of articles updated AND the names.
- [ ] If you select >10 articles, the action lands on a confirmation page first (Django's built-in `admin/<app>/<model>/confirm.html` pattern).
- [ ] Wrapped in `transaction.atomic()` — if any article fails validation, the whole batch rolls back.
- [ ] Includes a logger entry (`logger.info(...)`) for each article processed.

## Hints

<details>
<summary>Action signature</summary>

```python
from django.contrib import admin, messages
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@admin.action(description="Republish with new slug")
def republish_with_new_slug(modeladmin, request, queryset):
    if queryset.count() > 10 and not request.POST.get("post"):
        return modeladmin.confirm_action(request, queryset, ...)  # see Django docs
    with transaction.atomic():
        updated = []
        for article in queryset:
            base = slugify(article.title)
            slug, n = base, 1
            while Article.objects.filter(slug=slug).exclude(pk=article.pk).exists():
                n += 1
                slug = f"{base}-{n}"
            article.slug = slug
            article.status = "published"
            article.published_at = timezone.now()
            article.save()
            logger.info("Republished article %s -> %s", article.pk, slug)
            updated.append(article.title)
    messages.success(request, f"Republished {len(updated)} articles: {', '.join(updated[:5])}{'...' if len(updated) > 5 else ''}")
```

</details>

<details>
<summary>Confirmation page pattern</summary>

The canonical Django pattern is to render an intermediate template:

```python
from django.template.response import TemplateResponse

if not request.POST.get("post"):
    return TemplateResponse(request, "admin/myapp/article/republish_confirm.html", {
        "queryset": queryset,
        "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
    })
```

And a template `templates/admin/myapp/article/republish_confirm.html` with a hidden `post=yes` field.

</details>

## Stretch

- Add an option in the confirmation page: "Notify authors by email" (boolean).
- Add an undo: a follow-up action that reverts the change (record the old slug in a side table).
- Generalize: make this action reusable across multiple models via a mixin.

## Submission

Commit `admin.py` + the confirmation template + a screenshot of the working action to your portfolio under `c16-week-02/challenge-02/`.

## Why this matters

Most engineers learn admin actions from the docs and ship them without confirmation flows or transactional safety. When the action accidentally republishes 500 draft articles, it's a Sunday-night incident. Doing this challenge once installs the discipline.
