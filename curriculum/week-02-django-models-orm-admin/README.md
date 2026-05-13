# Week 2 — Django Models, the ORM, and the Admin

> *Django's superpower is the data model. Everything else — admin, forms, migrations, serialization, the test client — derives from your model definitions. Get the model right and the rest mostly writes itself.*

Welcome to Week 2 of **C16 · Crunch Pro Web Backend**. Week 1 built a Django project by hand from a blank folder. This week we install the database, write our first models, generate and run migrations, and meet the admin — Django's most distinctive feature and one of the strongest reasons to choose it over Flask/FastAPI for content-heavy apps.

By Sunday you will have the **`crunchwriter` v0** project running: authors, articles, categories, with an admin you can use to edit content as if you were a newspaper editor.

## Learning objectives

By the end of this week, you will be able to:

- **Define** Django models using the typed field classes, choosing the right field per attribute.
- **Reason about** the three main relationship types — `ForeignKey`, `ManyToManyField`, `OneToOneField` — including `on_delete` semantics and `related_name`.
- **Generate** migrations with `makemigrations` and apply them with `migrate`. Read a migration file.
- **Use the ORM**: `objects.all()`, `filter()`, `get()`, `create()`, `update()`, `delete()`. The difference between a `QuerySet` and a list.
- **Spot the N+1 problem** on day one, before it lands in production. Fix it with `select_related` / `prefetch_related`.
- **Register** models with the admin and customize via `ModelAdmin` — list display, filters, search, inline relationships.
- **Create** a superuser, log into the admin, and edit data through it.
- **Write** a model `__str__` that's useful in the admin and shell.

## Prerequisites

- **C16 Week 1 mini-project completed** — a Django project built by hand, running on `python manage.py runserver`.
- **Comfortable Python OOP** (C1 Week 7).
- **SQL fundamentals** (C1 Week 10).

## Topics covered

- Configuring `INSTALLED_APPS` for a real app (no longer empty)
- `DATABASES` setup: SQLite for dev, PostgreSQL preview (full deep-dive Week 4)
- Model fields: `CharField`, `TextField`, `IntegerField`, `DecimalField`, `BooleanField`, `DateField`, `DateTimeField`, `EmailField`, `URLField`, `SlugField`, `JSONField`
- Field options that matter every time: `null`, `blank`, `default`, `unique`, `db_index`, `choices`
- Relationships and their `on_delete` choices (`CASCADE`, `PROTECT`, `SET_NULL`, `RESTRICT`)
- The `Meta` inner class: ordering, indexes, constraints, verbose names
- Migrations: how they're generated, what they contain, how to read them
- The Django shell (`python manage.py shell`) — your day-to-day inspection tool
- `QuerySet` laziness: when SQL is actually executed
- The N+1 problem and `select_related` / `prefetch_related`
- The admin: registration, `ModelAdmin`, list display, filters, search, inlines
- Custom admin actions
- Why `__str__` on every model

## Weekly schedule

| Day       | Focus                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Fields, relationships, the data model | 2h       | 1.5h      | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 5.5h        |
| Tuesday   | Migrations + reading what's generated | 2h       | 2h        | 1h         | 0.5h      | 1h       | 0h           | 0h         | 6.5h        |
| Wednesday | The QuerySet API + the N+1 problem    | 2h       | 2h        | 1h         | 0.5h      | 1h       | 0h           | 0.5h       | 7h          |
| Thursday  | The admin, top to bottom               | 0h       | 1.5h      | 1h         | 0.5h      | 1h       | 2h           | 0.5h       | 6.5h        |
| Friday    | Mini-project deep work                 | 0h       | 0h        | 1h         | 0.5h      | 1h       | 2h           | 0.5h       | 5h          |
| Saturday  | Mini-project deep work + polish        | 0h       | 0h        | 0h         | 0h        | 1h       | 3h           | 0h         | 4h          |
| Sunday    | Quiz + reflection                      | 0h       | 0h        | 0h         | 0.5h      | 0h       | 0h           | 0h         | 0.5h        |
| **Total** |                                        | **6h**   | **7h**    | **4h**     | **3h**    | **6h**   | **7h**       | **2h**     | **35h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview |
| [resources.md](./resources.md) | Django ORM + admin docs + extras |
| [lecture-notes/01-models-and-fields.md](./lecture-notes/01-models-and-fields.md) | The field catalog and design choices |
| [lecture-notes/02-relationships-and-migrations.md](./lecture-notes/02-relationships-and-migrations.md) | FK/M2M/121 + reading migration files |
| [lecture-notes/03-the-queryset-api-and-the-admin.md](./lecture-notes/03-the-queryset-api-and-the-admin.md) | Querying + N+1 + the admin |
| [exercises/README.md](./exercises/README.md) | Index of exercises |
| [exercises/exercise-01-design-the-model.md](./exercises/exercise-01-design-the-model.md) | Translate a real-world domain into models |
| [exercises/exercise-02-shell-queries.md](./exercises/exercise-02-shell-queries.md) | 12 ORM puzzles in the Django shell |
| [exercises/exercise-03-customize-the-admin.md](./exercises/exercise-03-customize-the-admin.md) | Make the admin actually usable |
| [challenges/README.md](./challenges/README.md) | Stretch challenges |
| [challenges/challenge-01-spot-the-n-plus-1.md](./challenges/challenge-01-spot-the-n-plus-1.md) | Find and fix N+1 in a real codebase |
| [challenges/challenge-02-custom-admin-action.md](./challenges/challenge-02-custom-admin-action.md) | Bulk operations done right |
| [quiz.md](./quiz.md) | 10 MCQ |
| [homework.md](./homework.md) | Six problems (~6h) |
| [mini-project/README.md](./mini-project/README.md) | `crunchwriter` v0 — the editorial backbone |

## Stretch goals

- Read the entire **Django Model field reference** once: <https://docs.djangoproject.com/en/stable/ref/models/fields/>
- Try **`django-debug-toolbar`** locally; watch every query happen.
- Read the source of `django.contrib.admin.ModelAdmin` — it's well-written Python and shorter than you'd guess.

## Up next

[Week 3 — Views, Templates, Forms, and Auth](../week-03-views-templates-forms-auth/) — once `crunchwriter v0` runs and you've added at least three articles via the admin.
