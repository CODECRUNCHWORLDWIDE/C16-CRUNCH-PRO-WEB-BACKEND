# Challenge 1 — Spot the N+1

**Time:** ~90 minutes. **Difficulty:** Medium.

## Problem

Find a real, open-source Django project. Clone it. Set it up locally. Use `django-debug-toolbar` (or simply `connection.queries` counting) to find an N+1 query in real code. Fix it. Write up the before/after.

## Recommended targets

These are popular, well-documented, runnable open-source Django apps:

- **`django-allauth`** — auth library used widely. <https://github.com/pennersr/django-allauth>
- **`Saleor`** — e-commerce framework. <https://github.com/saleor/saleor>
- **`Pootle`** / **`Weblate`** — translation platforms.
- **Your own** Week-1 `crunchwriter` project — perfectly valid. Add a "list view" that loops over articles and accesses each article's author and categories. You'll find your own N+1 in 5 minutes.

## Acceptance criteria

- [ ] You picked a repo (or your own project) and can run it locally.
- [ ] You installed `django-debug-toolbar` (or wrote a small script using `connection.queries`).
- [ ] You navigated to a page that exhibits N+1.
- [ ] You captured the SQL panel showing the bad query count (screenshot).
- [ ] You fixed it with `select_related` or `prefetch_related`.
- [ ] You captured the SQL panel showing the improved count.
- [ ] You wrote a 200-word write-up explaining: where the N+1 was, why it happened, and the fix.
- [ ] Bonus: opened a PR (if it's an open-source project that accepts contributions). Definitely not required, but career-shaping if you do.

## Hints

<details>
<summary>How to count queries quickly</summary>

```python
from django.db import connection
print("Before view: ", len(connection.queries))
# ... do the thing ...
print("After view: ", len(connection.queries))
```

Or wrap with `assertNumQueries` in a test:

```python
with self.assertNumQueries(2):
    response = self.client.get("/articles/")
```

</details>

<details>
<summary>Common N+1 patterns to look for</summary>

- Templates that iterate a queryset and access a foreign key inside the loop.
- Serializers that serialize related models without a prefetch.
- List views that include a "count" field that hits the DB for each row.

</details>

## Submission

Commit `challenge-01-n+1-fix.md` (the write-up + screenshots) to your portfolio under `c16-week-02/challenge-01/`.

## Why this matters

If you've never spotted an N+1 in real code, you don't yet have the reflex that catches it before it lands in production. This challenge installs the reflex.
