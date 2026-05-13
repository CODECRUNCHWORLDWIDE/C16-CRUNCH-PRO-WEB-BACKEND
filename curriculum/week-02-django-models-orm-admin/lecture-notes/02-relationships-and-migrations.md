# Lecture 2 — Relationships and Migrations

> **Duration:** ~2 hours. **Outcome:** You can model any common relationship correctly, understand what a generated migration contains, and read a migration file without trusting it blindly.

## 1. The three relationships

Django ships three:

| Relationship | Field | Real-world example |
|-------------|-------|---------------------|
| Many-to-one | `ForeignKey` | An article has one author; an author has many articles |
| Many-to-many | `ManyToManyField` | An article has many categories; a category has many articles |
| One-to-one | `OneToOneField` | A user has one profile |

### ForeignKey

Looks like:

```python
author = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.PROTECT,
    related_name="articles",
)
```

**Two mandatory things:** what it points to, and `on_delete`.

`on_delete` decides what happens when the referenced row is deleted:

| Option | Behavior |
|--------|----------|
| `CASCADE` | Delete this row too. Default-feeling but DANGEROUS. |
| `PROTECT` | Refuse to delete the parent if any children reference it. |
| `SET_NULL` | Set this FK to NULL (requires `null=True`). |
| `SET_DEFAULT` | Set to the field's default. |
| `SET(callable)` | Set to whatever the callable returns. |
| `RESTRICT` | Like PROTECT, but unlike PROTECT, doesn't block cascading deletes from grandparents. |
| `DO_NOTHING` | Bypass Django entirely. Almost never correct. |

**Rule of thumb:** `PROTECT` is safer than `CASCADE`. The errors you get during development are cheap; the data you accidentally delete in production is not. Use `CASCADE` only when the child row literally has no meaning without the parent (an `OrderItem` without an `Order`, an `Email` without a `Mailbox`).

### `related_name`

Lets you control the reverse accessor.

```python
# Default
author.article_set.all()

# With related_name="articles"
author.articles.all()
```

Always set `related_name`. The default `<model>_set` is ugly and stops working when you have multiple FKs to the same target.

### `related_query_name`

Used in `filter()` queries that reach through the relationship:

```python
User.objects.filter(articles__status="published")  # if related_name is "articles"
```

By default `related_query_name` mirrors `related_name`.

### ManyToManyField

```python
categories = models.ManyToManyField(Category, related_name="articles", blank=True)
```

Django creates an implicit junction table. Same conventions on `related_name`. **No `on_delete`** — M2M doesn't need it because removing one side just removes the junction row, not the related model.

When you need extra columns on the join (e.g., a `joined_at` timestamp on a `Membership`), use `through`:

```python
class Membership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)
    role = models.CharField(max_length=20, choices=Role.choices)

class Group(models.Model):
    members = models.ManyToManyField(User, through="Membership")
```

### OneToOneField

```python
profile = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
```

Like `ForeignKey(unique=True)`. Use it for canonical "extension" objects (a `UserProfile`, a `WorkOrder.Invoice`). When `related_name` is set, the reverse access is single-object, not a `QuerySet`: `user.profile` returns the `Profile` instance directly.

## 2. The reverse-relation gotcha

```python
class Article(models.Model):
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="articles")
```

- Forward: `article.author` → returns a `User`
- Reverse: `user.articles` → returns a `QuerySet[Article]`

Forward is cached on the article instance after first access. Reverse is NOT — every access re-queries. This matters in templates. Use `select_related("author")` upstream to make repeated `article.author` cheap; use `prefetch_related("articles")` to bulk-fetch the reverse side.

## 3. Self-referential relationships

A user has a manager who is also a user.

```python
class User(models.Model):
    name = models.CharField(max_length=200)
    manager = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
```

`"self"` is the string version of the current class. You can also use the class name as a string before it's defined: `models.ForeignKey("Article", ...)`.

## 4. Migrations: what they are

A **migration** is a Python file Django generates to record a schema change.

When you change a model:

```bash
python manage.py makemigrations
```

Django diffs your model definitions against the migration history and generates a new file like `0002_article_categories.py`:

```python
class Migration(migrations.Migration):
    dependencies = [
        ('myapp', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='categories',
            field=models.ManyToManyField(blank=True, related_name='articles', to='myapp.category'),
        ),
    ]
```

Then to apply:

```bash
python manage.py migrate
```

Django runs the `operations` against your database in order.

## 5. Reading a migration

A migration has two parts: **dependencies** (which migrations must run before this one) and **operations** (what to do).

Common operations:

| Operation | Effect |
|-----------|--------|
| `CreateModel` | Create a new table |
| `DeleteModel` | Drop a table |
| `AddField` | Add a column |
| `RemoveField` | Drop a column |
| `AlterField` | Change column type / constraints |
| `RenameField` | Rename a column |
| `RenameModel` | Rename a table |
| `AddIndex` / `RemoveIndex` | Database indexes |
| `AddConstraint` / `RemoveConstraint` | Database constraints |
| `RunPython` | Run arbitrary Python (for data migrations) |
| `RunSQL` | Run raw SQL |

**Always read the generated migration before applying.** Django's diffs are usually correct, but ambiguous cases — like a rename — sometimes need human intervention.

For renames: Django asks at `makemigrations` time, "Did you rename `name` to `full_name`?" Answer `y` to get a `RenameField`. Answer `N` to get `RemoveField` + `AddField` (which DROPS the column data).

## 6. Data migrations

Schema migrations change the table. Data migrations change the data. Often you need both, in one migration:

```python
def assign_default_status(apps, schema_editor):
    Article = apps.get_model("myapp", "Article")
    Article.objects.filter(status="").update(status="draft")

class Migration(migrations.Migration):
    dependencies = [...]
    operations = [
        migrations.AddField(model_name="article", name="status", field=...),
        migrations.RunPython(assign_default_status, reverse_code=migrations.RunPython.noop),
    ]
```

**Important:** use `apps.get_model()` to get the historical model class, not `from myapp.models import Article`. The latter is the *current* model definition; the former is the model as it existed at this migration point. This matters when you later add fields — the data migration must work against the schema as of its own moment.

## 7. The migration cycle in real teams

In production:

1. Develop locally: change model, `makemigrations`, `migrate`, run tests.
2. Commit both the model change AND the migration file.
3. CI runs `migrate --check` to catch missing migrations.
4. On deploy: `migrate` runs as part of the release.
5. Database schema is always one step ahead of the code (apply migration, then deploy new code that uses it).

For non-trivial changes (renaming a column on a 50M-row table, adding a non-null column without a default), the workflow is more involved — full coverage in Week 6.

## 8. Squashing migrations

After 50 migrations in `myapp/migrations/`, things get unwieldy. Django offers:

```bash
python manage.py squashmigrations myapp 0050
```

This produces a single replacement migration. Tradeoffs: history is collapsed, but the squashed migration must be applied before any "live" migrations dependent on the old ones. Most teams squash only at major release boundaries.

## 9. Common mistakes

1. **Editing a migration after it's been applied** to other developers' machines. Once published, treat migrations as immutable.
2. **Forgetting to commit the migration file** — works on your machine, fails on everyone else's.
3. **Using `from myapp.models import Foo`** inside a `RunPython` — see §6.
4. **Adding a non-null column without a default** — `makemigrations` will ask you for a one-off default. Better: add nullable first, populate, then make non-null.
5. **Renaming a model without using the prompt** — destroys data unless you tell Django explicitly.
6. **Squashing too early** — wait for a stable release.

## 10. Self-check

- Three relationship field types — name them.
- When the parent of a `ForeignKey` is deleted, what does `on_delete=PROTECT` do?
- You set `related_name="articles"` on `Article.author`. Write the reverse accessor.
- A migration file has `dependencies = [("myapp", "0001_initial")]`. What does that mean?
- A migration has `RunPython` calling `from myapp.models import Article` — what's wrong with that?

## Further reading

- **Migrations documentation**: <https://docs.djangoproject.com/en/stable/topics/migrations/>
- **Migration operations reference**: <https://docs.djangoproject.com/en/stable/ref/migration-operations/>
- **`on_delete` options reference**: <https://docs.djangoproject.com/en/stable/ref/models/fields/#django.db.models.ForeignKey.on_delete>
