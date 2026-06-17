# Mini-Project — `crunchwriter` v0

> Stand up the data model + admin for our capstone project. By end of Week 2, you have an editorial dashboard where a non-engineer could log in and create articles.

**Estimated time:** 7 hours, spread across Thursday–Saturday.

## What you build

In your existing Django project (the one from Week 1), add an app called `writer` containing the **`Author`** (use Django's built-in user), **`Category`**, and **`Article`** models from the Week-2 lecture examples. Wire up the admin so a non-engineer could use it.

This becomes the foundation of `crunchwriter` — the application we'll grow week by week through Week 12.

## Acceptance criteria

- [ ] A new Django app `writer` exists, registered in `INSTALLED_APPS`.
- [ ] Models `Category` and `Article` (and reuse Django's built-in `User`) defined per Week 2's lecture examples.
- [ ] Migrations generated and applied. `python manage.py migrate` is clean.
- [ ] An admin registration for both models with at least:
  - `list_display`, `list_filter`, `search_fields`, `date_hierarchy`, `ordering`.
  - `prepopulated_fields` for slugs.
  - `raw_id_fields` for `author`.
  - `filter_horizontal` for `categories`.
  - The "Mark as published" admin action.
- [ ] A superuser created (`python manage.py createsuperuser`).
- [ ] You logged in to `/admin/` and created at least 3 articles across 2 categories.
- [ ] You ran `assertNumQueries(2)` (or similar) on a list view; passed.
- [ ] `python manage.py test` runs cleanly (at minimum, the test client passes a smoke test of the admin).
- [ ] `python manage.py check` is clean.
- [ ] Committed and pushed to the same `c16-week-01-byhand-<yourhandle>` repo (or a fork named `crunchwriter`), with a `c16-week-02/` subdirectory documenting the changes.

## Suggested order of operations

### Phase 1 — App scaffold (45 min)

1. `python manage.py startapp writer`.
2. Add `"writer"` to `INSTALLED_APPS`.
3. Confirm `python manage.py check` is still clean.

### Phase 2 — Models (90 min)

1. Write `writer/models.py` with `Category` and `Article` per the lecture examples.
2. `python manage.py makemigrations`.
3. **Read the generated migration.** Commit.
4. `python manage.py migrate`. Verify with `python manage.py dbshell` and `.schema article`.

### Phase 3 — Admin (90 min)

1. Write `writer/admin.py` with the customized `ModelAdmin` from Lecture 3 plus the "Mark as published" action.
2. Create a superuser.
3. Log in. Add a few categories and articles by hand.

### Phase 4 — Tests (90 min)

1. Write `writer/tests.py`:
   - Create an article in `setUp`.
   - Test `__str__`.
   - Test `Meta.ordering` (create two articles, verify the queryset order).
   - Test the admin list view loads (`/admin/writer/article/`).
   - Test the "Mark as published" action.
2. Run `python manage.py test writer`.

### Phase 5 — Documentation (45 min)

In your portfolio repo's `c16-week-02/`:

1. A `README.md` describing what you built.
2. Three screenshots: the admin list view, the admin edit view, an article you created.
3. A "what I'd change" section listing 1-2 things you'd refactor with hindsight.

### Phase 6 — Polish + commit (45 min)

1. Run `ruff check .` (if you have ruff installed; otherwise `python -m py_compile $(find . -name '*.py')`).
2. Final commit. Push.

---

## Rubric

| Criterion | Weight | "Great" looks like |
|-----------|------:|--------------------|
| Models compile + migrate | 25% | Clean migrate, no SQL errors |
| Admin actually usable | 25% | Could hand to a non-engineer |
| Tests pass | 20% | Real coverage of `__str__`, ordering, admin |
| README quality | 15% | Someone can run it from scratch |
| Code clarity | 10% | No commented-out code, naming reads |
| Optimization | 5% | Admin queries are O(1)-ish |

---

## What this prepares you for

- **Week 3** wires HTML/forms/auth on top of these models. The models + admin are the foundation; templates and views are the front door.
- **Week 4** moves to PostgreSQL. Your models will mostly work unchanged; the lessons are about indexes and constraints.
- **Week 5** goes deep on the QuerySet API (annotations, subqueries, `OuterRef`). You'll come back to these models.
- **Week 11** writes tests against this model. You'll thank present-you for picking sensible `Meta.ordering` and `__str__` here.

## Submission

When done: push, ensure README + migration + tests are committed, share the repo URL with a peer for a 30-minute review.

Then continue to [Week 3 — Views, Templates, Forms, Auth](../../week-03-views-templates-forms-auth/) — coming soon.
