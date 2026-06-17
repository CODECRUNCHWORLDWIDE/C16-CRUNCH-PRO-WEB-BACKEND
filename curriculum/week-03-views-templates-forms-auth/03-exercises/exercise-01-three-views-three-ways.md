# Exercise 1 — Three views, three ways

**Time:** ~2 hours. **Goal:** Internalize the FBV → `View` → generic CBV ladder by writing the same screen three times.

## The screen

A public list of **published** articles, newest first, paginated 10 per page. The template renders the title (linked to a detail page), the author's username, and the creation date.

## Setup

You already have the `Article` model from Week 2:

```python
class Article(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="articles")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    # ...
```

In your `writer/templates/writer/` directory, create `base.html` and `article_list.html` per the templates in Lecture 2. You will reuse the same template for all three view implementations.

## Part A — Function-based view (30 min)

In `writer/views.py`, write `article_list_fbv(request)`:

- Queryset: published articles only, newest first, with `select_related("author")`.
- Manually paginate using `django.core.paginator.Paginator` with `per_page=10`. Read the `page` query string parameter; default to `1`.
- Render `writer/article_list.html` with `articles`, `page_obj`, `paginator`, `is_paginated`.

In `writer/urls.py`:

```python
path("v1/", views.article_list_fbv, name="article_list_v1"),
```

Visit `/v1/` and `/v1/?page=2`. Confirm both render.

## Part B — `View` subclass (30 min)

In `writer/views.py`, write `ArticleListClassic(View)`:

- Implement `get(self, request)` with the same logic as Part A.
- Return the same template + context.

```python
path("v2/", views.ArticleListClassic.as_view(), name="article_list_v2"),
```

Visit `/v2/`. Confirm the output is byte-identical to `/v1/` (use `curl -s http://localhost:8000/v1/ | diff - <(curl -s http://localhost:8000/v2/)` — should print nothing).

## Part C — `ListView` (30 min)

In `writer/views.py`, write `ArticleListGeneric(ListView)`:

- `model = Article`, `template_name = "writer/article_list.html"`, `context_object_name = "articles"`, `paginate_by = 10`.
- Override `get_queryset()` to filter `status="published"` with `select_related("author")` and order by `-created_at`.

```python
path("v3/", views.ArticleListGeneric.as_view(), name="article_list_v3"),
```

Visit `/v3/`. Confirm it matches `/v1/` and `/v2/`.

## Part D — Compare (30 min)

In `c16-week-03/exercises/01-three-ways.md` in your portfolio, answer:

1. **Line count.** Roughly how many lines for each implementation, excluding the template?
2. **What did `ListView` give you for free** that you wrote by hand in Parts A and B?
3. **What did Parts A and B let you express** that `ListView` does not, or does only awkwardly? (Hint: think about the *next* feature request — what if the page also needs the list of categories in the sidebar?)
4. **Which version would you ship?** Why?
5. **Run `assertNumQueries`** on each version via the Django test client; confirm all three issue 2 queries (one for the count, one for the page).

## Acceptance

- [ ] Three URL routes (`/v1/`, `/v2/`, `/v3/`) all render the same article list.
- [ ] All three paginate correctly with `?page=2`.
- [ ] All three issue exactly 2 SQL queries on the first page.
- [ ] `01-three-ways.md` written with the four answers and the query-count comparison.
- [ ] `python manage.py check` is clean.

## Stretch

- Add a fourth route `/v4/` using `ListView` with `get_context_data` that adds `categories = Category.objects.all()` to the context. Render them in a `<aside>` sidebar.
- Now redo Part D's question 3 with the sidebar requirement in mind. Did your answer change?
