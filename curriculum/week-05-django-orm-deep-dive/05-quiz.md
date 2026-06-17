# Week 5 — Quiz

Ten questions. Lectures closed.

---

**Q1.** Which of the following is the correct tool for following a `ForeignKey` from `Article.author` in a list view, with one SQL query total?

- A) `Article.objects.prefetch_related("author")`
- B) `Article.objects.select_related("author")`
- C) `Article.objects.annotate(author=F("author"))`
- D) `Article.objects.values("author")`

---

**Q2.** You write `Author.objects.annotate(article_count=Count("articles"), comment_count=Count("comments"))`. For an author with 3 articles and 4 comments, what does the ORM report?

- A) `article_count = 3`, `comment_count = 4`
- B) `article_count = 12`, `comment_count = 12`
- C) `article_count = 7`, `comment_count = 7`
- D) `article_count = 3`, `comment_count = 4` only if you add `.distinct()`

---

**Q3.** Inside a `Subquery`, the inner queryset **must**:

- A) Have at least one `JOIN`.
- B) End in `.values("col")[:1]` for scalar use.
- C) Be wrapped in `transaction.atomic()`.
- D) Have a `GROUP BY`.

---

**Q4.** `Exists` is preferable to `Count("...") > 0` because:

- A) `Exists` is more readable.
- B) Postgres short-circuits `EXISTS` on the first matching row; `COUNT(*)` reads every row to compute the count.
- C) `Count` is deprecated.
- D) `Exists` returns the matching rows; `Count` returns an integer.

---

**Q5.** A `Window` function with `partition_by=[F("category_id")]` and `order_by=F("view_count").desc()` annotated with `Rank()`:

- A) Reduces the queryset to one row per category.
- B) Adds a column to each article showing its rank within its category.
- C) Filters the queryset to the top-ranked article per category.
- D) Raises an error unless `frame=` is specified.

---

**Q6.** Which one of these statements is **race-free** without an explicit lock?

- A) `a.view_count += 1; a.save()`
- B) `Article.objects.filter(pk=42).update(view_count=F("view_count") + 1)`
- C) `Article.objects.filter(pk=42).update(view_count=42)`
- D) `a = Article.objects.get(pk=42); a.view_count = a.view_count + 1; a.save()`

---

**Q7.** You convert a custom helper function `published_articles()` into a `QuerySet` method `published()` and attach it via `objects = ArticleQuerySet.as_manager()`. The biggest gain is:

- A) Performance — methods on querysets are faster than module-level functions.
- B) Chainability — `Article.objects.published().popular().in_category("python")` works.
- C) Safety — querysets cannot be modified, functions can.
- D) Backward compatibility with Django 2.x.

---

**Q8.** Inside `bulk_create(objects)`:

- A) `pre_save` and `post_save` signals fire for each instance.
- B) Signals do **not** fire. Database-level constraints still apply.
- C) Each instance is saved one at a time in a single transaction.
- D) The function returns nothing and never sets the primary key on the instances.

---

**Q9.** You want a single column `score` per row, computed in SQL as `CASE WHEN status='published' THEN view_count ELSE 0 END`. The right ORM tool is:

- A) `annotate(score=Case(When(status="published", then=F("view_count")), default=Value(0), output_field=IntegerField()))`
- B) `annotate(score=Subquery(...))`
- C) `annotate(score=Window(Sum("view_count")))`
- D) `aggregate(score=Sum("view_count"))`

---

**Q10.** You add `.assertNumQueries(2)` to a test of a list view. The test fails with "expected 2, got 22". The single most likely cause is:

- A) The template references `{{ article.author.username }}` and the view did not `select_related("author")`.
- B) The database is misconfigured.
- C) The test is flaky and you should retry.
- D) `assertNumQueries` itself runs 20 extra queries to count.

---

## Answer key

<details>
<summary>Reveal</summary>

1. **B** — `select_related` is the JOIN-based prefetch for forward `FK` / `O2O`; one query.
2. **B** — Multiplication trap. The join `author × articles × comments` produces 3×4 = 12 rows; each `Count` over-counts by the other side's cardinality. The fix is `distinct=True` or `Subquery`.
3. **B** — Scalar `Subquery` requires `.values("col")[:1]`. Without `.values()`, you cannot project a single column; without `[:1]`, Postgres errors with "more than one row".
4. **B** — `EXISTS` short-circuits at the first matching row; `COUNT(*)` reads every match. On large tables the gap is 100×.
5. **B** — Window functions compute per-row values across a partition without reducing the queryset. Every article in the result carries its rank.
6. **B** — `F("view_count") + 1` translates to `SET view_count = view_count + 1` in SQL, read-modified-written atomically by Postgres. A and D have the read-then-Python-add race.
7. **B** — Chainability. Querysets compose; helpers do not.
8. **B** — `bulk_create` skips per-instance signals. Postgres returns IDs via `RETURNING` (Django 4+), so PKs **are** populated on Postgres — D is wrong on the PK clause.
9. **A** — `Case` / `When` is the right expression for an `IF/THEN/ELSE` column. `Subquery` works but is overkill.
10. **A** — N+1. The template traverses `article.author`, and without `select_related`, each row triggers a query for the author. 20 articles × 1 query for author = 20 extra + 2 original = 22.

</details>

If 9+: ship the homework. 7–8: re-read Lecture 1 sections 2-3 and Lecture 2 section 5. <7: re-read Lectures 1 and 2 from the top before homework.
