# Exercise 3 — Customize the Admin

**Time:** ~60 minutes. **Output:** A polished admin you'd hand a non-engineer editor.

## Setup

In your `crunchwriter` (or exercise) project:

```bash
python manage.py createsuperuser
python manage.py runserver
```

Open `http://localhost:8000/admin/`.

## What to build

In `myapp/admin.py`, customize the admin to meet ALL of the following:

### `Article` admin

- [ ] `list_display`: title, author, status (colored badge if possible), category list (comma-separated), created_at, published_at.
- [ ] `list_filter`: status, categories, author.
- [ ] `search_fields`: title, body, author's username.
- [ ] `date_hierarchy`: created_at.
- [ ] `ordering`: -created_at.
- [ ] `prepopulated_fields`: slug from title.
- [ ] `raw_id_fields`: author (so the dropdown doesn't blow up when there are 10,000 users).
- [ ] `filter_horizontal`: categories (pretty M2M widget).
- [ ] `readonly_fields`: created_at.
- [ ] `fieldsets`: group fields into "Article", "Categorization", "Dates".
- [ ] An admin action "Mark selected as published" that bulk-sets `status="published"` and `published_at=now()`.

### `Category` admin

- [ ] `list_display`: name, slug, article count (annotated).
- [ ] `prepopulated_fields`: slug from name.

### Optional: an `Article` inline on `User`

- [ ] On the user-admin page (Django's built-in), inline the user's recent articles (latest 5, read-only).

## Acceptance criteria

- [ ] `admin.py` exists with all the above.
- [ ] Visiting `/admin/myapp/article/` shows your custom `list_display` columns.
- [ ] The "Mark selected as published" action works (verify with 2 selected articles, then verify they switched status).
- [ ] The page loads in <500ms on a database with 10 articles (no N+1 — use `list_select_related = ("author",)` and `prefetch_related` for categories).
- [ ] Screenshot the polished list view; commit to `c16-week-02/exercise-03-screenshot.png`.

## Hints

<details>
<summary>Colored status badge</summary>

Override `list_display` with a method:

```python
from django.utils.html import format_html

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "status_badge", "created_at")

    def status_badge(self, obj):
        colors = {"draft": "gray", "review": "orange", "published": "green"}
        return format_html(
            '<span style="background:{};color:white;padding:2px 6px;border-radius:3px;">{}</span>',
            colors.get(obj.status, "black"),
            obj.get_status_display(),
        )
    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"
```

</details>

<details>
<summary>Category list in list_display</summary>

```python
def category_list(self, obj):
    return ", ".join(c.name for c in obj.categories.all())
category_list.short_description = "Categories"
```

Then in `ModelAdmin`, set `list_prefetch_related = ("categories",)` to avoid N+1.

</details>

<details>
<summary>Annotating count on Category</summary>

```python
def get_queryset(self, request):
    qs = super().get_queryset(request)
    return qs.annotate(article_count=models.Count("articles"))

def article_count(self, obj):
    return obj.article_count
article_count.admin_order_field = "article_count"
```

</details>

## Stretch

- Add a "Recent activity" custom admin view (no model) that shows the last 24 hours of admin log entries.
- Override the admin's site header and title (`admin.site.site_header = "CrunchWriter Editorial"`).

## Submission

Commit `admin.py` and the screenshot to your portfolio under `c16-week-02/exercise-03/`.
