# Lecture 2 — Templates and the Form System

> **Duration:** ~2 hours. **Outcome:** You can write a base template with named blocks, render a list and a detail page off it, and build both a `Form` and a `ModelForm` with field-level and cross-field validation.

Templates render data into HTML. Forms validate data going the other way. They're often discussed separately, but in practice they meet on every screen that has a `<form>` element — which is most of them. This lecture covers both, in the order you actually use them.

## 1. Where templates live

Django looks for templates in two places by default:

1. Each directory listed in `TEMPLATES[0]["DIRS"]` (project-wide).
2. A `templates/` subfolder inside each installed app (per-app, enabled when `APP_DIRS=True`).

Convention: **namespace by app**. The Week-2 app is `writer`, so its templates live under `writer/templates/writer/`. That double-`writer` matters: the inner folder is the namespace, which prevents `article_list.html` from one app shadowing another.

```text
writer/
  templates/
    writer/
      base.html
      article_list.html
      article_detail.html
      article_form.html
      partials/
        article_card.html
```

In a view: `render(request, "writer/article_list.html", context)`.

## 2. The Django Template Language (DTL)

DTL has three constructs: **variables**, **tags**, **filters**.

```django
{# A comment #}

{{ variable }}                        {# variable interpolation #}
{{ article.title }}                   {# attribute / item / method lookup #}
{{ article.title|upper }}             {# filter: uppercase #}
{{ article.body|truncatewords:30 }}   {# filter with argument #}

{% if user.is_authenticated %}        {# tag: conditional #}
  Welcome, {{ user.username }}.
{% else %}
  <a href="{% url 'login' %}">Log in</a>
{% endif %}

{% for article in articles %}         {# tag: loop #}
  <li>{{ article.title }}</li>
{% empty %}
  <li>No articles yet.</li>
{% endfor %}
```

The dot operator in DTL does five lookups in order: dictionary key, attribute, method (called with no args), list index, then fail. So `{{ article.author.name }}` will work whether `name` is an attribute or a property; `{{ articles.0 }}` will work as a list index. This is intentionally permissive; it is also why you sometimes get "the template silently rendered nothing" when an attribute lookup fails — DTL's `string_if_invalid` is empty by default.

### Filters worth knowing on day one

| Filter | Effect |
|--------|--------|
| `default:"-"` | Fall back to `"-"` if the value is falsy |
| `default_if_none:"-"` | Fall back only if the value is `None` |
| `length` | Length of a list/queryset/string |
| `truncatewords:N` / `truncatechars:N` | Truncate with an ellipsis |
| `date:"Y-m-d"` | Format a datetime; PHP-style format string |
| `linebreaksbr` / `linebreaks` | Convert newlines to `<br>` / `<p>` |
| `safe` | Mark a string as safe HTML (don't escape) — **use sparingly** |
| `escape` | Force HTML-escape (default is auto-escape, so rarely needed) |
| `urlencode` | URL-encode |
| `pluralize` | `1 article{{ count|pluralize }}` → "articles" if count != 1 |
| `floatformat:2` | Render a number with two decimal places |

Filters chain: `{{ article.body|truncatewords:30|linebreaks }}`.

### Tags worth knowing on day one

| Tag | Effect |
|-----|--------|
| `{% url 'name' arg %}` | Reverse a URL by name |
| `{% csrf_token %}` | Insert the hidden CSRF input inside `<form method="post">` |
| `{% if %}` / `{% elif %}` / `{% else %}` / `{% endif %}` | Conditional |
| `{% for x in xs %}` / `{% empty %}` / `{% endfor %}` | Loop, with empty branch |
| `{% extends "base.html" %}` | Inherit from a parent (must be first non-comment line) |
| `{% block name %}…{% endblock %}` | Named override region |
| `{% include "partials/x.html" %}` | Include another template |
| `{% load static %}` then `{% static 'css/site.css' %}` | Static-file URL |
| `{% with var=expr %}…{% endwith %}` | Cache an expensive lookup once |
| `{% spaceless %}…{% endspaceless %}` | Strip whitespace between tags |

## 3. Template inheritance

The most important thing templates give you is **inheritance via named blocks**. Build one `base.html`; every page extends it and overrides specific regions.

```django
{# writer/templates/writer/base.html #}
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{% block title %}crunchwriter{% endblock %}</title>
  {% load static %}
  <link rel="stylesheet" href="{% static 'writer/site.css' %}">
</head>
<body>
  <header>
    <a href="{% url 'writer:article_list' %}">crunchwriter</a>
    {% if user.is_authenticated %}
      <span>{{ user.username }}</span>
      <a href="{% url 'writer:dashboard' %}">Dashboard</a>
      <form action="{% url 'logout' %}" method="post" style="display:inline">
        {% csrf_token %}
        <button type="submit">Log out</button>
      </form>
    {% else %}
      <a href="{% url 'login' %}">Log in</a>
    {% endif %}
  </header>

  <main>
    {% if messages %}
      <ul class="messages">
        {% for message in messages %}
          <li class="{{ message.tags }}">{{ message }}</li>
        {% endfor %}
      </ul>
    {% endif %}

    {% block content %}{% endblock %}
  </main>

  <footer>
    {% block footer %}&copy; crunchwriter{% endblock %}
  </footer>
</body>
</html>
```

```django
{# writer/templates/writer/article_list.html #}
{% extends "writer/base.html" %}

{% block title %}Articles · {{ block.super }}{% endblock %}

{% block content %}
  <h1>Latest articles</h1>
  <ul class="articles">
    {% for article in articles %}
      <li>
        <h2><a href="{% url 'writer:article_detail' slug=article.slug %}">{{ article.title }}</a></h2>
        <p class="meta">by {{ article.author.username }} on {{ article.created_at|date:"Y-m-d" }}</p>
      </li>
    {% empty %}
      <li>No articles yet.</li>
    {% endfor %}
  </ul>

  {% if is_paginated %}
    <nav class="pagination">
      {% if page_obj.has_previous %}
        <a href="?page={{ page_obj.previous_page_number }}">Previous</a>
      {% endif %}
      Page {{ page_obj.number }} of {{ paginator.num_pages }}
      {% if page_obj.has_next %}
        <a href="?page={{ page_obj.next_page_number }}">Next</a>
      {% endif %}
    </nav>
  {% endif %}
{% endblock %}
```

The pattern: **one base template per site**, every page extends it, overrides `title` and `content`, optionally overrides `footer`. The `{{ block.super }}` token splices the parent block's content into the child.

### `{% include %}` for partials

When a snippet appears on three pages, extract a partial:

```django
{# writer/templates/writer/partials/article_card.html #}
<article class="card">
  <h2><a href="{% url 'writer:article_detail' slug=article.slug %}">{{ article.title }}</a></h2>
  <p class="meta">{{ article.author.username }} · {{ article.created_at|date:"Y-m-d" }}</p>
</article>
```

Then in any page:

```django
{% for article in articles %}
  {% include "writer/partials/article_card.html" %}
{% endfor %}
```

`{% include %}` re-uses the current context. If you need to pass an explicit variable: `{% include "x.html" with article=item only %}` — `only` disables context inheritance entirely.

## 4. `{% url %}` — never hardcode a path

Every link, every form `action`, every `redirect()` should go through the named URL.

```django
<a href="{% url 'writer:article_detail' slug=article.slug %}">Read</a>
<form action="{% url 'writer:article_new' %}" method="post">…</form>
```

```python
return redirect("writer:article_list")
return redirect("writer:article_detail", slug=article.slug)
```

The day you change the URL path, every named usage works; every hardcoded `/articles/` quietly 404s. There is no excuse for hardcoding once you've set up `app_name`.

## 5. Static files in development

Templates rarely look right without CSS. The Week-3 setup:

1. Set `STATIC_URL = "/static/"` in `settings.py` (default is fine).
2. Put assets in `writer/static/writer/site.css`.
3. In templates: `{% load static %}` once, then `{% static 'writer/site.css' %}`.

In development with `DEBUG=True` and `INSTALLED_APPS` including `django.contrib.staticfiles`, Django's dev server serves `/static/` automatically. In production we'll use `collectstatic` and a real web server; that is Week 10.

## 6. The form system

Django's `Form` class has one job: **describe fields, validate input, produce `cleaned_data`**.

```python
# forms.py
from django import forms

class ContactForm(forms.Form):
    name = forms.CharField(max_length=120)
    email = forms.EmailField()
    message = forms.CharField(widget=forms.Textarea, max_length=2000)
```

The view:

```python
def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            # form.cleaned_data is a dict of validated values
            send_contact_email(**form.cleaned_data)
            return redirect("contact_thanks")
    else:
        form = ContactForm()
    return render(request, "contact.html", {"form": form})
```

The template:

```django
<form method="post">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">Send</button>
</form>
```

`{{ form.as_p }}` renders each field wrapped in `<p>`. You'll outgrow it almost immediately. The honest output is:

```django
<form method="post">
  {% csrf_token %}
  {% for field in form %}
    <div class="field {% if field.errors %}field--error{% endif %}">
      {{ field.label_tag }}
      {{ field }}
      {% if field.help_text %}<small>{{ field.help_text }}</small>{% endif %}
      {{ field.errors }}
    </div>
  {% endfor %}
  {{ form.non_field_errors }}
  <button type="submit">Send</button>
</form>
```

Now you control the markup. `{{ field }}` renders the widget; `{{ field.errors }}` renders the per-field error list; `{{ form.non_field_errors }}` renders errors raised in `clean()` (cross-field errors).

## 7. The validation lifecycle

When you call `form.is_valid()`, Django runs these steps in order:

1. **Field-level cleaning**: each field's `to_python()` and validators are called. Type-coerce `"3"` to `3`, ensure `EmailField` actually contains an `@`, etc.
2. **`clean_<fieldname>()` methods**: any method named `clean_email` on your form receives the already-coerced value of `self.cleaned_data["email"]` and returns the final cleaned value (or raises `ValidationError`).
3. **`clean()`**: a single method that sees all of `cleaned_data` at once. The only place cross-field validation belongs.
4. If anything raised `ValidationError`, the form is invalid; errors are attached to the appropriate field (or to `__all__`).

```python
from django import forms

class RegistrationForm(forms.Form):
    email = forms.EmailField()
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"]
        if email.endswith("@example.com"):
            raise forms.ValidationError("example.com addresses are not allowed.")
        return email.lower()

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        return cleaned
```

Three rules to internalize:

- **Return the value** from `clean_<field>()`. Forgetting is the most common new-developer bug — silent data loss.
- **Cross-field validation goes in `clean()`**, never in `clean_<field>()` — at the time `clean_password1` runs, you can't trust `password2` exists yet.
- **`add_error("field", "...")`** attaches the error to a specific field. `raise ValidationError("...")` from `clean()` attaches it to `__all__` (`non_field_errors`).

## 8. `ModelForm` — the form that knows its model

Most forms exist to create or edit a model instance. Re-declaring every field would duplicate the model. `ModelForm` reads the fields off the model:

```python
# forms.py
from django import forms
from .models import Article

class ArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ["title", "slug", "body", "categories", "status"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 12}),
        }

    def clean_slug(self):
        slug = self.cleaned_data["slug"]
        qs = Article.objects.filter(slug=slug)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This slug is already taken.")
        return slug
```

Three things `ModelForm` does that a regular `Form` doesn't:

1. **`fields = [...]`** picks which model fields the form exposes. **Always set this explicitly** — never use `fields = "__all__"` in production. Whitelisting prevents a new model field from accidentally becoming editable.
2. **`form.save()`** creates or updates the model instance. `form.save(commit=False)` returns the unsaved instance so you can set extra attributes (`form.instance.author = request.user`) before persisting.
3. **Unique constraints from the model** become form-level validation automatically; the slug check above is for additional logic (case-insensitive, soft-deleted rows, etc.), not the basic uniqueness.

### `commit=False`: the everyday `ModelForm` pattern

```python
def article_create(request):
    if request.method == "POST":
        form = ArticleForm(request.POST)
        if form.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.save()
            form.save_m2m()   # MUST call this when commit=False + the form has M2M fields
            return redirect("writer:article_detail", slug=article.slug)
    else:
        form = ArticleForm()
    return render(request, "writer/article_form.html", {"form": form})
```

The `form.save_m2m()` line catches everyone once. With `commit=False`, the instance is not saved, so M2M relationships (`categories` on `Article`) cannot be persisted yet — they have no `article_id` to join through. `save()` would have called `save_m2m()` for you; with `commit=False`, you have to call it after the instance has a primary key.

## 9. Widgets and `attrs`

A form field has a **widget** — the HTML element it renders to.

| Field | Default widget |
|-------|----------------|
| `CharField` | `TextInput` |
| `CharField(widget=Textarea)` | `Textarea` |
| `IntegerField` | `NumberInput` |
| `EmailField` | `EmailInput` |
| `BooleanField` | `CheckboxInput` |
| `ChoiceField` | `Select` |
| `ModelChoiceField` | `Select` (with the queryset as options) |
| `DateField` | `DateInput` |

You override widgets via `widgets = {...}` in `Meta` (on `ModelForm`) or by passing `widget=...` to the field constructor. The most common reason to override is to add `attrs` for CSS classes or `placeholder` text:

```python
class ArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ["title", "slug", "body"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Title"}),
            "body": forms.Textarea(attrs={"class": "input input--tall", "rows": 14}),
        }
```

## 10. Rendering errors — the part templates always get wrong

Three error containers, three places to render them:

| Source | Where it appears |
|--------|------------------|
| `field.errors` | A `list` of strings; one per failed validator. Per-field. |
| `form.non_field_errors` | Errors raised in `clean()` without a field name. Top of form. |
| Form-level success/failure feedback | Use the `messages` framework, not the form. |

The minimum honest field rendering:

```django
{% for field in form %}
  <div class="field {% if field.errors %}field--error{% endif %}">
    {{ field.label_tag }}
    {{ field }}
    {% if field.help_text %}<small class="help">{{ field.help_text }}</small>{% endif %}
    {% for error in field.errors %}
      <p class="error">{{ error }}</p>
    {% endfor %}
  </div>
{% endfor %}

{% if form.non_field_errors %}
  <div class="errors">
    {% for error in form.non_field_errors %}<p>{{ error }}</p>{% endfor %}
  </div>
{% endif %}
```

## 11. Messages — for one-shot feedback

Django's `contrib.messages` is a flash-message framework that survives one redirect. It's the right place for "Article saved.", "Login failed.", "Your password was changed.":

```python
from django.contrib import messages

def article_create(request):
    # ... after a successful save:
    messages.success(request, "Article saved.")
    return redirect("writer:article_detail", slug=article.slug)
```

In `base.html` (we already wrote this above):

```django
{% if messages %}
  <ul class="messages">
    {% for message in messages %}
      <li class="{{ message.tags }}">{{ message }}</li>
    {% endfor %}
  </ul>
{% endif %}
```

`messages` is configured by default in a fresh `startproject`. If your `MIDDLEWARE` or `INSTALLED_APPS` were trimmed in Week 1, double-check `django.contrib.messages` is in both.

## 12. Common mistakes

1. **Forgetting `{% csrf_token %}`** inside `<form method="post">` — every POST will 403. We dig into the why in Lecture 3.
2. **Returning nothing from `clean_<field>()`** — the field becomes `None`. Always `return value`.
3. **Cross-field validation in `clean_<field>()`** — you can't reliably see other fields there. Use `clean()`.
4. **`fields = "__all__"` in a `ModelForm`** — auto-exposes every new model field to the form. Whitelist.
5. **Forgetting `form.save_m2m()`** after `save(commit=False)` on a form with M2M fields — M2M rows silently don't persist.
6. **Hardcoding URLs** in templates and views — use `{% url %}` / `reverse`.
7. **Putting business logic in the template** — leads to logic that can't be tested and can't be reused.
8. **`{{ form }}` and shipping it** — `as_p` / `as_table` are fine for demos, not for production UI. Loop the fields once and own the markup.
9. **Forgetting that `request.FILES` exists** — if your form has a file field, `form = ArticleForm(request.POST, request.FILES)`. Easy to miss.

## 13. Self-check

- What are the three constructs of the Django Template Language?
- Why do you put templates inside `templates/<app_name>/` and not `templates/`?
- What does `{{ block.super }}` do?
- What is the validation order in a `Form.is_valid()` call?
- Why must cross-field validation live in `clean()` and not `clean_<field>()`?
- When do you need `form.save_m2m()`?
- What does `fields = "__all__"` invite in a `ModelForm`, and what should you use instead?
- Which template tag is mandatory in every `<form method="post">`, and why?

## Further reading

- **Templates — language reference**: <https://docs.djangoproject.com/en/stable/ref/templates/language/>
- **Built-in template tags & filters**: <https://docs.djangoproject.com/en/stable/ref/templates/builtins/>
- **Forms topic guide**: <https://docs.djangoproject.com/en/stable/topics/forms/>
- **`ModelForm` reference**: <https://docs.djangoproject.com/en/stable/topics/forms/modelforms/>
- **Form and field validation** (the lifecycle in detail): <https://docs.djangoproject.com/en/stable/ref/forms/validation/>
- **Messages framework**: <https://docs.djangoproject.com/en/stable/ref/contrib/messages/>
