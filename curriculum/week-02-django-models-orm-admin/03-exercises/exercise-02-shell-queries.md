# Exercise 2 — Shell Queries

**Time:** ~75 minutes. **Output:** Twelve QuerySet expressions, each producing a documented result against your Week-2 models.

## Setup

Run inside your `crunchwriter` (or this week's exercise project) directory:

```bash
python manage.py shell_plus      # if you installed django-extensions
# or
python manage.py shell
```

If using plain `shell`, import the models manually:

```python
from myapp.models import Article, Category, User    # adjust to your app
```

## Seed data

Run this once at the top of your shell session to populate ~10 articles across 3 authors and 4 categories:

```python
from django.contrib.auth import get_user_model
from myapp.models import Article, Category
import datetime, random
from django.utils import timezone

User = get_user_model()

# users
alice = User.objects.create_user(username="alice", email="alice@example.com")
bob = User.objects.create_user(username="bob", email="bob@example.com")
carol = User.objects.create_user(username="carol", email="carol@example.com")

# categories
python_cat, _ = Category.objects.get_or_create(name="Python", slug="python")
web_cat, _ = Category.objects.get_or_create(name="Web", slug="web")
devops_cat, _ = Category.objects.get_or_create(name="DevOps", slug="devops")
ai_cat, _ = Category.objects.get_or_create(name="AI", slug="ai")

# articles
for i, (author, status) in enumerate([
    (alice, "published"), (alice, "published"), (alice, "draft"),
    (bob, "published"), (bob, "review"), (bob, "published"),
    (carol, "published"), (carol, "draft"), (carol, "published"),
    (alice, "published"),
]):
    article = Article.objects.create(
        title=f"Article {i+1} by {author.username}",
        slug=f"article-{i+1}-by-{author.username}",
        author=author,
        body=f"Body of article {i+1}.",
        status=status,
        published_at=timezone.now() if status == "published" else None,
    )
    # assign 1-2 random categories
    cats = random.sample([python_cat, web_cat, devops_cat, ai_cat], k=random.randint(1, 2))
    article.categories.set(cats)
```

## The 12 queries

For each, write the QuerySet expression. Save your work to `exercise-02-queries.md`. Include each query's text AND the result.

1. **All published articles, most-recent first.**
2. **Count of articles per author**, sorted descending. (Hint: `annotate(Count("articles"))` on `User`.)
3. **All articles by Alice that mention "python" (case-insensitive) in title or body.**
4. **The 5 most-recently published articles**, but only their titles. (Use `values_list("title", flat=True)`.)
5. **Authors with zero published articles.** (Hint: `filter(articles__status="published")` is wrong; you need `exclude` + a subquery, or `~Q(...)`).
6. **Average number of categories per published article.** (Hint: `annotate(Count("categories"))` then `aggregate(Avg(...))`.)
7. **Articles tagged "Python" OR "AI".** (Hint: `Q` objects on `categories__name`.)
8. **Articles in BOTH "Python" AND "Web" categories.** (Trickier — `__in` doesn't work for AND.)
9. **The most prolific author** (highest article count). (Hint: order by annotation, `first()`.)
10. **For each category, the most recently published article in it.** (Hint: a subquery with `OuterRef`. This one is hard.)
11. **Atomically increment view_count on a specific article.** (Use `F` expressions; add a `view_count` field first if your model doesn't have one.)
12. **All articles whose author shares a name prefix with the article slug.** (Filter where `slug__startswith=F("author__username")`. Demonstrate `F` in a filter.)

## Acceptance criteria

- [ ] `exercise-02-queries.md` with all 12 queries + their results.
- [ ] For at least 5 of them, paste the generated SQL using `print(queryset.query)`.
- [ ] Identify which queries would be N+1 in a naive Python loop and demonstrate the fix with `select_related` / `prefetch_related`.

## Stretch

- Take any one of the 12 and rewrite it using raw SQL with `Article.objects.raw(...)`. Notice how much longer/uglier it is.
- Add `assertNumQueries` tests verifying each query executes the expected number of times.

## Submission

Commit `exercise-02-queries.md` to your portfolio.
