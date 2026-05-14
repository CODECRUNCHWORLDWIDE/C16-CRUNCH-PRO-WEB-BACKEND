# Exercise 1 — Data migration

**Time:** ~2 hours. **Goal:** Add a computed `reading_time_minutes` column to `Article`, backfill it via a `RunPython` data migration with reverse support, then add the `NOT NULL` constraint. Three migrations, three deploys (simulated), every step inspected with `sqlmigrate`.

Work in your `crunchwriter` repo. Save the write-up to `c16-week-06/exercises/01-migration.md`.

## Setup

Verify the project is clean:

```bash
python manage.py showmigrations writer
# every box should be [X]; no pending migrations

python manage.py shell -c "from writer.models import Article; print(Article.objects.count())"
# expect >= 10000

git status
# clean working tree
```

If migrations are dirty (uncommitted model changes), commit or revert before starting. The exercise is about migration discipline; a dirty tree undermines the lesson.

## Part A — Migration 1: Add the column nullable

Edit `writer/models.py`:

```python
class Article(models.Model):
    ...
    reading_time_minutes = models.PositiveIntegerField(null=True, blank=True)
```

Generate the migration:

```bash
python manage.py makemigrations writer
# creates writer/migrations/00XX_article_reading_time_minutes.py
```

Inspect the SQL:

```bash
python manage.py sqlmigrate writer 00XX
```

**Paste the SQL into the write-up.** Confirm:

- It is one `ALTER TABLE writer_article ADD COLUMN reading_time_minutes integer NULL`.
- There is no `DEFAULT` clause (because `null=True` and no `default=`).
- The lock type is implicit; for nullable columns this is metadata-only on Postgres 11+.

Apply:

```bash
python manage.py migrate writer
```

In the shell, confirm:

```python
from writer.models import Article
Article.objects.filter(reading_time_minutes__isnull=True).count()
# == Article.objects.count() — every row is NULL
```

## Part B — Migration 2: Backfill with `RunPython`

Create the migration by hand (do not use `makemigrations` — there is no model change to detect):

```bash
python manage.py makemigrations writer --empty --name backfill_reading_time
# creates writer/migrations/00YY_backfill_reading_time.py
```

Edit the file to contain:

```python
from django.db import migrations


def forwards(apps, schema_editor):
    Article = apps.get_model("writer", "Article")
    qs = Article.objects.filter(reading_time_minutes__isnull=True).only("id", "body")
    batch = []
    for art in qs.iterator(chunk_size=1000):
        words = len((art.body or "").split())
        art.reading_time_minutes = max(1, words // 200)
        batch.append(art)
        if len(batch) >= 1000:
            Article.objects.bulk_update(batch, ["reading_time_minutes"])
            batch.clear()
    if batch:
        Article.objects.bulk_update(batch, ["reading_time_minutes"])


def reverse(apps, schema_editor):
    Article = apps.get_model("writer", "Article")
    Article.objects.update(reading_time_minutes=None)


class Migration(migrations.Migration):
    dependencies = [
        ("writer", "00XX_article_reading_time_minutes"),   # fix the name to match Part A
    ]
    operations = [
        migrations.RunPython(forwards, reverse),
    ]
```

Three things to verify before applying:

1. **`apps.get_model("writer", "Article")`**, not `from writer.models import Article`. Why: the historical model may differ from the current one. State this in the write-up.
2. **`iterator(chunk_size=1000)`**, not `.all()`. Why: `.all()` loads every row into RAM at once. State the memory cost difference for a 1-million-row table.
3. **`bulk_update`** in batches of 1000, not `.save()` per row. Why: one INSERT per 1000 rows is 1000× fewer round-trips. Time the difference if you can.

Apply:

```bash
python manage.py migrate writer
```

Time it:

```bash
time python manage.py migrate writer
# record wall-clock seconds in the write-up
```

Confirm:

```python
Article.objects.filter(reading_time_minutes__isnull=True).count()
# 0

Article.objects.values("reading_time_minutes").distinct().count()
# > 1 — distinct values exist, confirming the backfill actually computed
```

## Part C — Migration 3: Add `NOT NULL`

Edit `writer/models.py`:

```python
class Article(models.Model):
    ...
    reading_time_minutes = models.PositiveIntegerField()   # null=True removed
```

Generate:

```bash
python manage.py makemigrations writer
# creates writer/migrations/00ZZ_alter_article_reading_time_minutes.py
```

Inspect:

```bash
python manage.py sqlmigrate writer 00ZZ
```

**Paste the SQL.** Confirm it is `ALTER TABLE writer_article ALTER COLUMN reading_time_minutes SET NOT NULL`. State in the write-up: this is fast on Postgres 12+ because every row already has a value (Part B guaranteed it).

Apply. Confirm the column is non-nullable:

```python
Article.objects.filter(reading_time_minutes__isnull=True).count()
# 0

# Attempt to insert NULL — should fail
from django.db import IntegrityError
try:
    Article.objects.create(title="x", body="y", reading_time_minutes=None)
except IntegrityError as e:
    print("blocked as expected:", e)
```

## Part D — Reverse all three migrations

Now reverse, in order, ending back at the pre-exercise state:

```bash
python manage.py migrate writer 00XX_article_reading_time_minutes
# reverses Migration 3 (constraint), then Migration 2 (backfill); leaves the nullable column

python manage.py showmigrations writer | tail -5
# 00XX should still be [X]; 00YY and 00ZZ should be [ ]
```

Confirm:

```python
Article.objects.filter(reading_time_minutes__isnull=True).count()
# == Article.objects.count() — the reverse migration set them back to NULL
```

Then reverse the column itself:

```bash
python manage.py migrate writer <one-before-00XX>
# reverses Migration 1; the column no longer exists
```

Confirm:

```bash
python manage.py dbshell -c "\\d writer_article" | grep reading_time
# no output — column is gone
```

Finally re-apply all three:

```bash
python manage.py migrate writer
```

The system should end in the same state as Part C. The reversibility round-trip is the whole point of the exercise.

## Part E — Write-up

`c16-week-06/exercises/01-migration.md` should contain:

1. **The three migrations**, each with:
   - The migration file contents (or a link to the file in your repo).
   - The `sqlmigrate` output.
   - The `time` to apply, on your seeded data.
   - One paragraph explaining what it does and why this shape rather than a one-shot `AddField(null=False, default=...)`.
2. **The reverse round-trip** — terminal paste showing the migrations going `[X][X][X] → [X][X][ ] → [X][ ][ ] → [ ][ ][ ] → [X][X][X]`.
3. **The two rules** — `apps.get_model` vs direct import; `iterator + bulk_update` vs `.all() + save()`. One paragraph each, in your own words.
4. **One thing you would do differently in production** — likely: split deploy A and deploy C across days; run the backfill as a management command rather than a migration if the table has 100M+ rows.

## Acceptance criteria

- [ ] Three migration files committed.
- [ ] Each `sqlmigrate` output pasted into the write-up.
- [ ] The backfill uses `apps.get_model`, `iterator(chunk_size=1000)`, and `bulk_update`.
- [ ] The reverse migration is **not** `RunPython.noop` — it sets the column back to `NULL`. (Even if `noop` would be defensible here, the exercise is about writing a real reverse.)
- [ ] The reverse round-trip is demonstrated, end to end.
- [ ] Write-up is 200–400 lines.

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Migration shape | 30% | Three separate migrations; each `sqlmigrate` clean |
| Reversibility | 25% | Reverse round-trip demonstrated; both `forwards` and `reverse` correct |
| Production hygiene | 20% | `apps.get_model`, `iterator`, `bulk_update` all used and explained |
| Write-up clarity | 15% | A peer can follow the file top-to-bottom and reproduce |
| The "different in production" insight | 10% | Specific and defensible |

## Hints

- **`makemigrations --empty`** creates a migration with no operations. Edit the file by hand.
- **`makemigrations --name backfill_reading_time`** gives the migration a meaningful filename.
- **`migrate writer <migration_name>`** without trailing arguments rolls back to (and including) that migration. The migration named is the **last applied** in the resulting state.
- **`migrate writer zero`** rolls back every migration in the app. Useful for the very-first migration's reverse test; do not run on a project you care about.
- **`bulk_update` does not call `save()`**. If you have signals on `Article.save`, the backfill does not fire them. State this in the write-up.

## What this prepares you for

The mini-project adds two new fields to `Article`: `image` (an `ImageField`) and `thumbnails_generated_at` (a `DateTimeField`, nullable). The latter is the idempotency flag from Lecture 2 section 5. You will use the same migration shape — add nullable, no backfill needed because new rows start `NULL`, and the flag is set by the Celery task.

Exercise 2 starts the Celery worker. Exercise 3 caches the dashboard. By Friday, the mini-project pulls all three into one feature.
