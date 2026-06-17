# Exercise 2 — `ModelForm` with validation

**Time:** ~2.5 hours. **Goal:** Build an `ArticleForm` that demonstrates the full validation lifecycle — field-level cleaners, cross-field validation, custom widgets, and the `commit=False` save pattern.

## The form

Authors will use this form to create or edit an article. The form must:

1. Expose `title`, `slug`, `body`, `categories`, `status` (in that order).
2. Default `status` to `draft`. Reject `status="published"` unless the article has a non-empty `body` of at least 200 characters.
3. Validate that the slug is unique **across all articles**, case-insensitively (Django's default uniqueness is case-sensitive on most DBs).
4. Reject titles that consist of only whitespace or are shorter than 5 characters after stripping.
5. Render `body` as a `Textarea` with `rows=14` and a CSS class `input input--tall`.

## Part A — Build the form (60 min)

In `writer/forms.py`:

```python
from django import forms
from .models import Article, Category

class ArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ["title", "slug", "body", "categories", "status"]
        widgets = {
            "body": forms.Textarea(attrs={"class": "input input--tall", "rows": 14}),
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Title"}),
            "slug": forms.TextInput(attrs={"class": "input", "placeholder": "url-slug"}),
        }

    # ... clean methods here
```

Implement:

- `clean_title()` — strip whitespace; raise `ValidationError("Title must be at least 5 characters.")` if the stripped value is shorter than 5.
- `clean_slug()` — lowercase the slug; query for an existing article with that slug, **excluding the current instance** if `self.instance.pk` is set. Raise `ValidationError("This slug is already taken.")` on conflict.
- `clean()` — call `super().clean()` first. If `cleaned_data.get("status") == "published"` and `len(cleaned_data.get("body", ""))` is below 200 characters, attach an error to the `body` field via `self.add_error("body", "...")` saying the body must be at least 200 characters before publishing.

## Part B — Wire up a view (45 min)

In `writer/views.py`:

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import ArticleForm

@login_required
def article_create_fbv(request):
    if request.method == "POST":
        form = ArticleForm(request.POST)
        if form.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.save()
            form.save_m2m()
            messages.success(request, "Article saved.")
            return redirect("writer:article_detail", slug=article.slug)
    else:
        form = ArticleForm()
    return render(request, "writer/article_form.html", {"form": form})
```

Route:

```python
path("dashboard/new/", views.article_create_fbv, name="article_new"),
```

In `writer/templates/writer/article_form.html`, write the markup. Loop fields, render `field.errors` per field and `form.non_field_errors` at the top. Do not use `{{ form.as_p }}` in this exercise; you need to see the errors render where you expect.

## Part C — Test each branch (45 min)

In `writer/tests.py`, add `ArticleFormTests(TestCase)` with:

- `test_valid_form_saves` — give the form valid data; assert `form.is_valid()` is `True` and `form.save()` creates an `Article`.
- `test_short_title_rejected` — title `"hi"`; assert `form.is_valid()` is `False` and the error is attached to the `title` field.
- `test_whitespace_title_rejected` — title `"     "`; same expectations.
- `test_duplicate_slug_rejected_case_insensitive` — create an article with `slug="hello"`; attempt to create another with `slug="HELLO"`; assert rejected.
- `test_editing_keeps_own_slug` — load an existing article into the form (`ArticleForm(data, instance=existing)`); assert valid even though the slug exists on `existing`.
- `test_publish_short_body_rejected` — `status="published"` with `body="x" * 100`; assert the form is invalid and the error is on the `body` field.
- `test_publish_long_body_ok` — `status="published"` with `body="x" * 300`; assert valid.

Run `python manage.py test writer.tests.ArticleFormTests`. All seven should pass.

## Part D — Demonstrate manually (20 min)

1. Log in to your dev server (create a user via the admin or `createsuperuser`).
2. Visit `/dashboard/new/`.
3. Try to submit:
   - A 3-character title → see the error inline.
   - A duplicate slug → see the error inline.
   - `status=published` with a 50-character body → see the error inline.
   - All-valid data → redirect to the article detail page; see the success message at the top of the new page.

Take a screenshot of one of the validation-error states; commit it as `c16-week-03/exercises/02-error-state.png`.

## Acceptance

- [ ] `ArticleForm` defined with the four clean methods specified.
- [ ] `article_create_fbv` view + URL + template, login-required.
- [ ] All seven tests in `ArticleFormTests` pass.
- [ ] One screenshot of an inline validation error.
- [ ] `python manage.py check` clean.
- [ ] No `fields = "__all__"` anywhere in the form. Verify by `grep`.

## Stretch

- Convert the FBV to a `CreateView` and an `UpdateView` pair. Keep the form, drop the duplicated bind/save code. The `CreateView`'s `form_valid` should still set `author = request.user` before save.
- Add an `UpdateView` at `/dashboard/<int:pk>/edit/` that loads the existing article into the form and lets the author edit it.
