# Week 2 — Homework

Six problems, ~6h.

---

## Problem 1 — Inspect a generated migration (45 min)

In your `crunchwriter` project (or this week's exercise project), run `makemigrations` after the Week-2 models are in place. Open the resulting migration file in `myapp/migrations/`.

**Acceptance:**

- `migration-walkthrough.md` in your portfolio with:
  - The full migration file content.
  - A line-by-line explanation of what each operation does.
  - The SQL equivalent (use `python manage.py sqlmigrate myapp 0001` to see Django's translation).
  - One observation: which operation surprised you?

---

## Problem 2 — Add a CheckConstraint (45 min)

Add a check constraint to `Article` ensuring `published_at IS NOT NULL` whenever `status="published"`.

**Acceptance:**

- The constraint added in `Meta.constraints`.
- A migration generated and applied.
- A test that demonstrates the constraint works: try creating an article with `status="published"` and `published_at=None` — it should raise an `IntegrityError`.

---

## Problem 3 — Reverse a relationship (45 min)

For each of these forward queries, write the equivalent reverse query (or explain why it doesn't apply):

- `article.author` → ?
- `article.categories` → ?
- `user.articles` → ?
- `category.articles` → ?
- `article.author.articles.exclude(pk=article.pk)` (sibling articles) → ?

**Acceptance:**

- `relationships.md` with all five answered, plus generated SQL via `print(qs.query)` for each.

---

## Problem 4 — Add a model method that uses the ORM (60 min)

Add a method to `Article`: `def reading_time_minutes(self) -> int` that computes reading time as `max(1, word_count // 200)`. Then add `def author_recent_articles(self, n=3)` that returns the author's last `n` articles excluding the current one.

**Acceptance:**

- Methods defined on the model.
- A test for each.
- A demonstration in the Django shell where you call them on a real article.

---

## Problem 5 — Optimize a slow admin page (45 min)

Open your admin's article list view. Use `django-debug-toolbar` (or `connection.queries`) to count the SQL. With 100 articles, the default config likely runs 100+ queries because of categories and author lookups in `list_display`.

Get it to ≤ 3 queries.

**Acceptance:**

- `optimization.md` with: query count before, after, and the specific `ModelAdmin` changes you made (`list_select_related`, `list_prefetch_related`, or `get_queryset` override).
- Screenshot showing the query panel before and after.

---

## Problem 6 — Reflection (45 min)

`reflection.md`, 300-400 words:

1. Which `on_delete` choice felt least intuitive to you, and why?
2. What was the hardest of the 12 shell-query exercises?
3. The admin: useful enough to be a CMS, or developer-only? Defend.
4. What habit do you want to install for Week 3?

---

## Time budget

| Problem | Time |
|--------:|----:|
| 1 — Migration walkthrough | 45 min |
| 2 — CheckConstraint | 45 min |
| 3 — Reverse relations | 45 min |
| 4 — Model methods | 60 min |
| 5 — Optimize admin | 45 min |
| 6 — Reflection | 45 min |
| **Total** | **~5 h 45 m** |

After homework, ship the [mini-project](./mini-project/README.md) — `crunchwriter v0`.
