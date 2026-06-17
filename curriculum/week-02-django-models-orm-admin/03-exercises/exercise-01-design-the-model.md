# Exercise 1 — Design the Model

**Time:** ~45 minutes. **Output:** Three Django models translated from a domain description, with every field choice justified.

## The domain

A small online bookstore. The relevant rules:

- A **book** has a title (≤200 chars), an ISBN-13 (13 digits, unique), a description (free-form text, optional), a published date (a date, not optional), a current price (in USD, exact to the cent), and a status (`available`, `out_of_stock`, `discontinued`).
- A **book** has **one or more authors** (a writer can co-author with others).
- An **author** has a name (≤200 chars), a date of birth (a date, may be unknown), and a short bio (free-form text, optional).
- A **review** is written by a customer about a book. Reviews have a rating (1–5), a body (free-form text), and a creation timestamp.
- Reviews belong to one book; books have many reviews.
- Authors should never be deletable if they have books. Books should never be deletable if they have reviews.

## Your task

Write a `models.py` file containing **`Author`, `Book`, `Review`** with the right field types, relationships, defaults, indexes, and `Meta` options.

Save it to `c16-week-02/exercise-01-models.py` in your portfolio repo.

## Acceptance criteria

- [ ] Every field has a justification (single-line comment) above it explaining WHY this field type and these options.
- [ ] `Author.date_of_birth` correctly handles "may be unknown" (`null=True, blank=True`).
- [ ] `Book.price` uses `DecimalField`, not `FloatField`. Justified.
- [ ] `Book.isbn` is unique and `db_index=True`.
- [ ] `Book.status` uses `TextChoices`.
- [ ] `Book.authors` is `ManyToManyField` (multiple authors per book; authors write multiple books).
- [ ] `Review.book` is `ForeignKey(on_delete=models.PROTECT)` — reviews block book deletion as specified.
- [ ] `Book` and `Author` deletion rules match the domain spec (PROTECT, not CASCADE).
- [ ] Every model has `__str__` returning a useful representation.
- [ ] Every model has a `Meta` with at least `ordering` set.
- [ ] At least one model has a compound index in `Meta.indexes` (e.g., `Book(status, -published_date)`).

## Hints

<details>
<summary>If you're stuck on the relationship direction</summary>

- "Authors write many books, books have many authors" → `Book.authors = ManyToManyField(Author)`.
- "Reviews belong to one book" → `Review.book = ForeignKey(Book)`.
- The reverse on `Review.book`: `book.reviews.all()` if you set `related_name="reviews"`.

</details>

<details>
<summary>Why `PROTECT` instead of `CASCADE`</summary>

The spec literally says "should never be deletable if they have books" — that's `PROTECT`. `CASCADE` would silently delete every book by that author. `PROTECT` forces the admin to think about it.

</details>

<details>
<summary>If `TextChoices` is unfamiliar</summary>

```python
class Status(models.TextChoices):
    AVAILABLE = "available", "Available"
    OUT_OF_STOCK = "out_of_stock", "Out of stock"
    DISCONTINUED = "discontinued", "Discontinued"

status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
```

The first string is the database value; the second is the human-readable label.

</details>

## Stretch

- Add a `Customer` model and rewrite `Review.author` to point to a customer instead of the book's author.
- Add an `OrderItem` model (`Customer` + `Book` + `quantity` + `unit_price_at_purchase`).
- Add a database constraint that `Review.rating` is between 1 and 5 using `models.CheckConstraint`.

## Submission

Commit `exercise-01-models.py` to your portfolio under `c16-week-02/exercise-01/`. Then in `exercise-02-shell-queries.md` you'll work against these same models.
