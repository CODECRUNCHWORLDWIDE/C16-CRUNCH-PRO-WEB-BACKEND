# Lecture 1 — Models and Fields

> **Duration:** ~2 hours. **Outcome:** You can translate a domain description into Django models with the right field types and the right options, and explain every choice.

A Django model is a Python class. Each class attribute is a database column. Together, they describe a table.

```python
from django.db import models

class Article(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField()
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

That's the whole idea. Everything in this lecture is "which field, and which options."

## 1. The standard fields

Django ships ~30 field types. You'll use ~10 daily. Memorize the table.

### Numeric

| Field | Use for | Notes |
|-------|---------|-------|
| `IntegerField()` | 32-bit signed integer | Range ~ ±2.1B |
| `BigIntegerField()` | 64-bit signed integer | When IDs or counts can exceed 2.1B |
| `PositiveIntegerField()` | unsigned 32-bit | When negative makes no sense (counts) |
| `SmallIntegerField()` | 16-bit | Rare, but useful for status enums backed by integers |
| `DecimalField(max_digits, decimal_places)` | Exact decimal (money) | **Always use for currency.** Never `FloatField`. |
| `FloatField()` | IEEE 754 double | Scientific data; **never** money |

The fixed-vs-float distinction is one of the few "always" rules. `1.10 + 1.10 == 2.2` in `Decimal`; in float it's `2.1999999999999997`.

### Text

| Field | Use for | Notes |
|-------|---------|-------|
| `CharField(max_length=N)` | Short text with a known max | Up to a few hundred chars |
| `TextField()` | Unbounded text | Bodies, descriptions, anything with newlines |
| `SlugField()` | URL-safe strings | Auto-validated against the slug regex |
| `EmailField()` | Email | `CharField` + email validator |
| `URLField()` | URLs | `CharField` + URL validator |
| `UUIDField()` | UUIDs | Common for primary keys when avoiding sequential IDs |

`CharField` and `TextField` map to different SQL types — varchar(N) and TEXT respectively. On Postgres, both are fine; on MySQL, the distinction matters for indexing.

### Boolean

- `BooleanField()` — true/false. Set `default=False` or `default=True` explicitly; ambiguous defaults break migrations.

### Date and time

| Field | Use for |
|-------|---------|
| `DateField(auto_now_add=True)` | Sets to today on insert; never updates |
| `DateField(auto_now=True)` | Updates to today every save |
| `DateTimeField()` | Full date+time. Always set `USE_TZ = True` and store UTC. |
| `TimeField()` | Just time of day. Rare. |
| `DurationField()` | A `timedelta`. Stored as a 64-bit microsecond count. |

### Structured

| Field | Use for | Notes |
|-------|---------|-------|
| `JSONField()` | Arbitrary JSON | Works everywhere on Django 4.0+; **prefer real columns when you can** |
| `BinaryField()` | Bytes | Rare; usually you store paths/URLs to S3 instead |
| `FileField(upload_to="...")` | File metadata + storage | Real file storage; the field holds a path |
| `ImageField()` | `FileField` + image-specific validation | Pillow required |

### Relationships (covered in Lecture 2)

| Field | Use for |
|-------|---------|
| `ForeignKey(To, on_delete=...)` | Many-to-one |
| `ManyToManyField(To)` | Many-to-many |
| `OneToOneField(To, on_delete=...)` | One-to-one |

## 2. Field options that matter every time

Every field accepts a long list of optional arguments. Five matter on every project.

### `null` and `blank`

These are the most-confused pair in Django.

| Option | What it means |
|--------|---------------|
| `null=True` | The **database** column allows NULL |
| `blank=True` | The **form/admin** allows the field to be empty |

You almost always want them together for "optional" fields, **except for string fields**, where Django convention is to use empty string `""` instead of NULL — so `blank=True` only.

```python
# Optional text — convention: empty string
description = models.TextField(blank=True)

# Optional foreign key — both
manager = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

# Optional decimal — both
discount = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
```

### `default`

A literal value OR a callable. Use a callable for "now" / "random uuid" / etc.

```python
created_at = models.DateTimeField(default=timezone.now)        # callable, evaluated each save
status = models.CharField(max_length=20, default="draft")     # literal
```

Do NOT use `default=timezone.now()` — that evaluates ONCE at class-definition time and every row gets the same default. Pass the callable, not its result.

### `unique`

Adds a UNIQUE constraint at the database level + an admin validator.

```python
slug = models.SlugField(max_length=200, unique=True)
```

### `db_index`

Adds a database index. Critical for fields you filter by frequently.

```python
status = models.CharField(max_length=20, db_index=True)
```

(Foreign keys are auto-indexed. You don't need to ask.)

### `choices`

Restricts allowed values + populates a dropdown in the admin/forms.

```python
class Status(models.TextChoices):
    DRAFT = "draft", "Draft"
    REVIEW = "review", "Under review"
    PUBLISHED = "published", "Published"

status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
```

`TextChoices` (and `IntegerChoices`) are the modern way — they give you both the database value and a human label.

## 3. The `Meta` inner class

Options that apply to the whole model, not a single field.

```python
class Article(models.Model):
    # fields...

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "article"
        verbose_name_plural = "articles"
        indexes = [
            models.Index(fields=["status", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["author", "slug"], name="unique_author_slug"),
        ]
```

The most-used `Meta` options:

| Option | Effect |
|--------|--------|
| `ordering` | Default `ORDER BY` for queries on this model |
| `verbose_name` / `verbose_name_plural` | What the admin calls this model in UI |
| `indexes` | Extra indexes (beyond unique + FK) |
| `constraints` | Multi-column unique constraints, CHECK constraints |
| `abstract = True` | This model is a mixin, not a real table |
| `app_label = "..."` | Manually set the app this model belongs to (rare) |
| `db_table = "..."` | Override the auto-generated table name (rare) |

## 4. The primary key

By default, Django adds an `id` column — an auto-incrementing `BigAutoField` (in modern Django). You almost never set this yourself.

If you want a different primary key, declare a field with `primary_key=True`:

```python
class User(models.Model):
    email = models.EmailField(primary_key=True)
```

**UUID primary keys** are popular for "we'll never expose sequential IDs to the URL":

```python
import uuid

class Article(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
```

Tradeoffs: UUIDs are 16 bytes vs 8 bytes for `BigAutoField`. They don't sort by creation order (UUID v4 is random). They make join performance slightly worse. Use them when you specifically need opaque IDs in public URLs.

## 5. `__str__` — non-optional

Every model needs `__str__`. Without it, the admin shows `Article object (1)` for every row. With it, the admin is usable.

```python
class Article(models.Model):
    title = models.CharField(max_length=200)

    def __str__(self):
        return self.title
```

Rule of thumb: `__str__` returns whatever you'd want to see in a dropdown or in the admin's list view. Almost always a single field; sometimes a small composite ("Alice — Article 42").

## 6. Designing the model

For our running `crunchwriter` project, the Week-2 domain is:

> A small publishing site. Authors write articles. Each article belongs to one author and zero or more categories. Each article has a title, body, status (draft / review / published), creation date, and publication date.

Translation to Django:

```python
from django.conf import settings
from django.db import models
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Article(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "Under review"
        PUBLISHED = "published", "Published"

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="articles",
    )
    categories = models.ManyToManyField(Category, related_name="articles", blank=True)
    body = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return self.title
```

Choices to notice and defend (verbally, to yourself):

1. **`settings.AUTH_USER_MODEL`** instead of `User` — Django best practice. Lets the project swap user model later without breaking migrations.
2. **`on_delete=PROTECT` on `author`** — we never want to delete an author and silently lose all their articles. `PROTECT` raises an error; the human resolving it can decide.
3. **`related_name="articles"`** — lets us write `author.articles.all()` instead of the default `author.article_set.all()`.
4. **`slug` is unique** at the column level — guarantees URL uniqueness without app-level checks.
5. **`db_index=True` on `status` and `created_at`** — the most-filtered, most-sorted fields. The compound index in `Meta` accelerates "all published articles sorted by date."
6. **`published_at` is optional** (null/blank) — drafts have no published date.

Run `makemigrations` and inspect what Django generates. The file will be ~80 lines; we read it in Lecture 2.

## 7. Common mistakes

1. **Forgetting `__str__`** — admin becomes unusable.
2. **`default=timezone.now()`** with parentheses — every row gets the SAME timestamp.
3. **`max_length` on `TextField`** — `TextField` is unbounded; `max_length` is silently ignored.
4. **`null=True` on `CharField`** — convention is empty string for "missing text," not NULL.
5. **`unique=True` without thinking about migrations** — adding `unique=True` to a populated field will fail the migration if duplicates exist. Plan: data-cleaning migration first, then add the constraint.
6. **Using `FloatField` for money** — at some point a rounding error costs you a customer.
7. **Forgetting `on_delete`** in modern Django — it's required; the error is clear; don't autopilot through it.
8. **Storing JSON in `JSONField` when you could have a real column** — querying nested JSON is slower and harder than querying a real indexed column.

## 8. Self-check

- A user has a date of birth that may or may not be known. Which field type and which options?
- A blog post has a body that might be empty initially. Which field type and which options?
- You need exact currency for an invoice item. Which field type? Why not `FloatField`?
- A model needs to be listed in the admin alphabetically by name. Where do you set that?
- Why is `default=timezone.now` correct and `default=timezone.now()` wrong?
- Without `__str__`, what does the admin display for each row?

## Further reading

- **Django model fields reference** (the comprehensive table): <https://docs.djangoproject.com/en/stable/ref/models/fields/>
- **Database indexes** in the Django docs: <https://docs.djangoproject.com/en/stable/ref/models/indexes/>
- **The `Meta` options** in full: <https://docs.djangoproject.com/en/stable/ref/models/options/>
