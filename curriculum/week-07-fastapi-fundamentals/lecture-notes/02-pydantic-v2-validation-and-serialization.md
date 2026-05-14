# Lecture 2 — Pydantic v2: validation and serialisation

> **Duration:** ~2 hours. **Outcome:** You can declare a Pydantic v2 model that validates inbound JSON and serialises outbound JSON. You can use `Field`, `field_validator`, `model_validator`, `Annotated[T, Field(...)]`, and `model_config`. You can separate request and response schemas, discriminate over a union, and produce the JSON Schema FastAPI emits for the OpenAPI document. You can name what changed between Pydantic v1 and v2 and why.

FastAPI's route handlers receive *Python objects*, not raw bytes. The conversion from `application/json` to a typed Python value, and back again, is done by **Pydantic**. Pydantic v2 (`pydantic>=2.0`, released June 2023) is a near-total rewrite: the core validation engine moved from Python to Rust (`pydantic-core`), the API changed in ways that are mostly compatible but occasionally hostile, and the performance regime improved by a factor of five to fifty depending on workload.

This lecture is Pydantic v2 from first principles, with explicit attention to what changed from v1 — because every example you find on Stack Overflow before 2023 is v1, and every paragraph that says "use `dict()`" or "use `Config` as an inner class" is wrong for new code.

## 1. The minimum — declare and validate

```python
from pydantic import BaseModel


class Article(BaseModel):
    title: str
    body: str
    views: int = 0
```

That is a model. To validate JSON into it:

```python
import json
data: dict = json.loads('{"title": "Hello", "body": "world", "views": 3}')
article: Article = Article.model_validate(data)
print(article.title)       # "Hello"
print(article.views)       # 3
print(type(article.views)) # <class 'int'>
```

The `model_validate` call:

1. **Coerces** values to the declared types where Pydantic considers it safe (`"3"` → `3` for `int` is allowed by default; `"three"` → `int` raises).
2. **Validates** every field — required-ness, type, any `Field(...)` constraints.
3. **Raises** `pydantic.ValidationError` if any field fails, with a list of every failure (not just the first).
4. **Constructs** the object only if all fields pass.

Two patterns to learn:

```python
# From a dict
article = Article.model_validate({"title": "...", "body": "...", "views": 3})

# From a JSON string (skips the intermediate dict)
article = Article.model_validate_json('{"title": "...", "body": "...", "views": 3}')
```

`model_validate_json` is faster than `json.loads(...) + model_validate(...)` because it parses and validates in one pass inside `pydantic-core`.

### Migration note from v1

| Pydantic v1 | Pydantic v2 |
|---|---|
| `Article.parse_obj(data)` | `Article.model_validate(data)` |
| `Article.parse_raw(json_bytes)` | `Article.model_validate_json(json_bytes)` |
| `article.dict()` | `article.model_dump()` |
| `article.json()` | `article.model_dump_json()` |
| `class Config: orm_mode = True` | `model_config = ConfigDict(from_attributes=True)` |
| `@validator("field")` | `@field_validator("field")` |
| `@root_validator` | `@model_validator(mode="before"/"after")` |
| `Field(..., regex=r"...")` | `Field(..., pattern=r"...")` |

The old names mostly still exist as deprecated aliases in early v2 releases; by Pydantic 2.9 they emit `DeprecationWarning`; by Pydantic 3.0 (slated 2025) they will be removed. Write new code with the v2 names. See the migration guide: <https://docs.pydantic.dev/latest/migration/>.

## 2. `Field` — adding metadata

Every Pydantic field can carry metadata: defaults, constraints, descriptions, examples, JSON Schema hints, aliases. The canonical way to attach metadata in v2 is `Annotated`:

```python
from typing import Annotated
from pydantic import BaseModel, Field


class Article(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=200, description="The article title.")]
    body: Annotated[str, Field(min_length=1)]
    views: Annotated[int, Field(ge=0, default=0, description="View count; non-negative.")]
    slug: Annotated[str, Field(pattern=r"^[a-z0-9-]+$", examples=["hello-world"])]
```

The older form is `field: str = Field(min_length=1, ...)`. Both are valid; the `Annotated` form is preferred in 2025 idioms because the type annotation reads as a single unit. See <https://docs.pydantic.dev/latest/concepts/fields/>.

Constraints worth memorising:

| Type | Constraint |
|---|---|
| `str` | `min_length`, `max_length`, `pattern` |
| `int`, `float`, `Decimal` | `ge`, `gt`, `le`, `lt`, `multiple_of` |
| `list[T]` | `min_length`, `max_length` |
| `Decimal` | `max_digits`, `decimal_places` |
| any | `default`, `default_factory`, `description`, `examples`, `alias`, `frozen` |

A few that matter for API design:

- **`description`** — appears in the OpenAPI document as the field's description. Users read it in `/docs`.
- **`examples`** — appears in the OpenAPI document. Swagger UI fills in the example by default. Worth providing for every required field.
- **`alias`** — the JSON name differs from the Python name. `Field(alias="userId")` lets the JSON key be `userId` while the Python attribute is `user_id`. Used for snake_case-Python / camelCase-JSON boundaries.
- **`default_factory`** — for mutable defaults. `Field(default_factory=list)` is the right way to give a list-typed field an empty default; `default=[]` is the bug from v1 that pinned every instance to the same list.
- **`frozen`** — the field cannot be reassigned after construction. Useful for value-object semantics.

## 3. Validators

The metadata above covers declarative constraints. Validators cover constraints you can only express in code.

### `@field_validator` — one field at a time

```python
from pydantic import BaseModel, field_validator


class Article(BaseModel):
    title: str
    slug: str

    @field_validator("slug")
    @classmethod
    def slug_is_lowercase(cls, v: str) -> str:
        if v != v.lower():
            raise ValueError("slug must be lowercase")
        return v
```

The decorator runs *after* Pydantic has already coerced and basic-validated the field (this is `mode="after"`, the default). The validator receives the value, may raise, may return a transformed value. The return value replaces the field.

If you need to inspect the *raw* input (before coercion), use `mode="before"`:

```python
@field_validator("views", mode="before")
@classmethod
def coerce_string_views(cls, v: object) -> object:
    if isinstance(v, str) and v.strip() == "":
        return 0
    return v
```

`mode="before"` runs *before* type coercion; `mode="after"` runs *after*. You will use both. See <https://docs.pydantic.dev/latest/concepts/validators/>.

### `@model_validator` — across fields

When the validation involves two or more fields:

```python
from pydantic import BaseModel, model_validator
from typing_extensions import Self


class Article(BaseModel):
    title: str
    body: str
    published_at: str | None = None
    is_draft: bool

    @model_validator(mode="after")
    def published_implies_not_draft(self) -> Self:
        if self.published_at is not None and self.is_draft:
            raise ValueError("article cannot be a draft if it has a published_at")
        return self
```

`mode="after"` model validators receive the constructed model (typed `Self`); `mode="before"` receives the raw dict and must return a dict. The before/after distinction is identical to field validators.

## 4. Serialisation — the way out

A model serialises in two shapes:

```python
article.model_dump()       # → dict
article.model_dump_json()  # → str (JSON-encoded)
```

Both accept the same keyword arguments:

| Argument | Effect |
|---|---|
| `include={"title", "body"}` | Only these fields |
| `exclude={"internal"}` | All fields except these |
| `by_alias=True` | Use the alias names instead of attribute names |
| `exclude_none=True` | Drop fields whose value is `None` |
| `exclude_unset=True` | Drop fields the input did not set (different from `None`) |
| `exclude_defaults=True` | Drop fields whose value equals the default |
| `mode="json"` | Coerce datetimes, UUIDs, etc. to JSON-safe forms (`model_dump_json` does this automatically) |

The `exclude_unset` distinction matters for `PATCH` endpoints: the client sent `{"title": "x"}`, and you want to update only the fields they sent, not overwrite every other field with the model defaults.

```python
@app.patch("/articles/{article_id}")
async def patch_article(article_id: int, update: ArticleUpdate) -> ArticleRead:
    # Apply only the fields the client actually sent
    changes = update.model_dump(exclude_unset=True)
    db_article = await update_article(article_id, **changes)
    return ArticleRead.model_validate(db_article)
```

### Custom field serialisers

When the on-wire representation differs from the in-memory one:

```python
from datetime import datetime
from pydantic import BaseModel, field_serializer


class Article(BaseModel):
    title: str
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        # ISO 8601 with seconds precision and an explicit "Z" suffix
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
```

The serialiser runs when `model_dump` / `model_dump_json` is called. See <https://docs.pydantic.dev/latest/concepts/serialization/>.

## 5. `model_config` — the per-model knobs

```python
from pydantic import BaseModel, ConfigDict


class Article(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,        # read SQLAlchemy/Django ORM objects
        str_strip_whitespace=True,   # trim whitespace from all str fields on input
        populate_by_name=True,       # accept BOTH alias and attribute name on input
        extra="forbid",              # raise on unexpected fields (default: "ignore")
        frozen=False,                # whole model is mutable (default)
    )
    title: str
    slug: str
```

The knobs you will use:

- **`from_attributes=True`** — formerly `orm_mode`. Lets `Article.model_validate(orm_obj)` read `orm_obj.title` etc. Essential when handing a SQLAlchemy or SQLModel row to a response model.
- **`extra="forbid"`** — reject unknown fields on the input. The default `"ignore"` silently drops them, which is the wrong default for an API: a client that misspells `tite` should get a clear 422, not a silent no-op.
- **`str_strip_whitespace=True`** — trim leading/trailing whitespace on every `str` field. Avoids the bug where `"foo "` and `"foo"` are different keys.
- **`populate_by_name=True`** — needed when you use `alias` and want to accept inputs that use the Python name, not the alias. Defaults to `False` (strict alias-only on input).

See <https://docs.pydantic.dev/latest/api/config/>.

## 6. The two-schemas pattern (and why)

The single most important Pydantic-related decision in a FastAPI codebase: **separate the request schema from the response schema**.

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated


class ArticleBase(BaseModel):
    """Fields shared by all article schemas."""
    title: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str, Field(min_length=1)]


class ArticleCreate(ArticleBase):
    """Body of POST /articles. Excludes server-assigned fields."""
    # no id, no created_at — those come from the server
    pass


class ArticleUpdate(BaseModel):
    """Body of PATCH /articles/{id}. Every field is optional."""
    title: Annotated[str | None, Field(default=None, min_length=1, max_length=200)]
    body: Annotated[str | None, Field(default=None, min_length=1)]


class ArticleRead(ArticleBase):
    """Body of GET /articles/{id} and items of GET /articles."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    author_name: str          # denormalised from the join
```

Three reasons this separation is non-negotiable:

1. **The security boundary.** `ArticleCreate` does not contain `id` or `author_id`; an attacker cannot send `{"id": 999, "title": "..."}` and have the server obediently create an article with that id. The schema rejects it. If `Article` is the only model and is used for both directions, the boundary collapses and mass-assignment vulnerabilities follow.
2. **Default-value drift.** `ArticleCreate` declares `title` as required. `ArticleRead` declares `title` as present (it always is — the database guarantees it). A shared model has to declare it with a default of `None` to serve both, and now you cannot tell whether a 200 response with `title: null` is a real null or a missing value.
3. **Version drift.** When the API evolves — adding `excerpt`, deprecating `body_html` — the request and response schemas evolve on different schedules. Request schemas change when clients change. Response schemas change when consumers change. Coupling them slows both.

This is the canonical FastAPI example, given at <https://fastapi.tiangolo.com/tutorial/extra-models/>. The example uses `UserIn`, `UserOut`, `UserInDB` — the same pattern with different names.

### From SQLAlchemy/SQLModel ORM object to `ArticleRead`

```python
@app.get("/articles/{article_id}", response_model=ArticleRead)
async def get_article(article_id: int, session: SessionDep) -> ArticleRead:
    stmt = select(Article).where(Article.id == article_id)
    result = await session.execute(stmt)
    article_row = result.scalar_one_or_none()
    if article_row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleRead.model_validate(article_row)
```

Because `ArticleRead.model_config.from_attributes = True`, `model_validate` reads attributes off `article_row` (`article_row.id`, `article_row.title`, etc.) as if it were a dict. The `response_model=ArticleRead` on the decorator then *re-validates* the function's return value against `ArticleRead` before serialisation — the contract is enforced on the way out.

## 7. Discriminated unions

When an endpoint accepts more than one body shape — for instance, a notification system that can send `EmailNotification`, `SMSNotification`, or `PushNotification` — use a **discriminated union**:

```python
from typing import Annotated, Literal
from pydantic import BaseModel, Field


class EmailNotification(BaseModel):
    kind: Literal["email"]
    to_email: str
    subject: str


class SMSNotification(BaseModel):
    kind: Literal["sms"]
    to_phone: str
    body: str


class PushNotification(BaseModel):
    kind: Literal["push"]
    device_token: str
    title: str
    body: str


Notification = Annotated[
    EmailNotification | SMSNotification | PushNotification,
    Field(discriminator="kind"),
]


@app.post("/notify")
async def notify(notification: Notification) -> dict[str, str]:
    return {"sent_to_kind": notification.kind}
```

Pydantic sees the `discriminator="kind"` and dispatches validation based on the value of `kind` in the input. If `kind="email"`, only `EmailNotification`'s validators run. If `kind` is missing or unrecognised, the response is a 422 with a clear error. The OpenAPI document FastAPI emits encodes the discriminator correctly, so Swagger UI offers the right form for each variant.

Without the discriminator, Pydantic tries each variant in turn and returns the first that succeeds — slower, and the error messages on failure are confusing.

See <https://docs.pydantic.dev/latest/concepts/unions/>.

## 8. JSON Schema generation

Pydantic produces JSON Schema for every model:

```python
print(json.dumps(Article.model_json_schema(), indent=2))
```

The output is the schema FastAPI embeds in `/openapi.json` under `components.schemas.Article`. You rarely need to look at the schema directly, but knowing it exists — and that every `Field(description=..., examples=...)` lands inside it — is the connection between "I added an `examples=` argument" and "Swagger UI now shows the example".

A small example:

```python
class Article(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=200, description="The title.")]
    views: Annotated[int, Field(ge=0, default=0)]
```

`model_json_schema()` returns:

```json
{
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "minLength": 1,
      "maxLength": 200,
      "description": "The title.",
      "title": "Title"
    },
    "views": {
      "type": "integer",
      "minimum": 0,
      "default": 0,
      "title": "Views"
    }
  },
  "required": ["title"]
}
```

OpenAPI 3.1 *is* JSON Schema 2020-12 — Pydantic emits the dialect FastAPI needs without any glue. This is the technical reason the OpenAPI document is "free": Pydantic was already doing the work for `model_validate`, and FastAPI just collects the schemas across routes.

See <https://docs.pydantic.dev/latest/concepts/json_schema/>.

## 9. Validation errors — the 422 response

When a request body fails validation, FastAPI returns **HTTP 422 Unprocessable Content** with a body that lists every failing field:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "title"],
      "msg": "Field required",
      "input": {"body": "hello"}
    },
    {
      "type": "string_too_short",
      "loc": ["body", "slug"],
      "msg": "String should have at least 1 character",
      "input": ""
    }
  ]
}
```

The status code is 422 (RFC 9110 §15.5.21, originally RFC 4918 §11.2; semantically: "the server understands the content type and the syntax, but the content is semantically wrong"). FastAPI uses 422 to distinguish "your JSON is fine, but the fields don't validate" from 400 "your JSON itself is malformed".

A common request: collapse the verbose Pydantic error structure into a flatter, custom shape. Override the handler:

```python
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"errors": errors},
    )
```

This is in the FastAPI handling-errors chapter: <https://fastapi.tiangolo.com/tutorial/handling-errors/>.

## 10. Performance — what Pydantic v2 actually delivers

Pydantic v2 is built on `pydantic-core`, written in Rust. The validator and serialiser are compiled, not interpreted. Three honest numbers:

- **Validating** a 10-field model from JSON: ~5–10× faster than v1.
- **Serialising** the same model to JSON: ~10–20× faster than v1 in the typical case.
- **Constructing** a model from already-validated data (`model_construct`): essentially free; allocated as fast as a dataclass.

In a FastAPI handler that does one database query and serialises the result, Pydantic validation is now microseconds and the database query is milliseconds. The bottleneck is no longer Pydantic. This was not true in v1, where serialising a list of 1 000 nested models was a measurable contributor to p95 latency.

See <https://docs.pydantic.dev/latest/concepts/performance/>.

## Lecture summary

- **Pydantic v2** is a Rust-backed validation engine. Models are subclasses of `BaseModel`. Validation is `Model.model_validate(...)`; serialisation is `instance.model_dump(...)` or `instance.model_dump_json(...)`.
- **`Annotated[T, Field(...)]`** is the canonical 2025 syntax for adding metadata to a field. Common constraints: `min_length`, `max_length`, `pattern`, `ge`, `le`, `description`, `examples`, `alias`.
- **`field_validator`** runs per-field; **`model_validator`** runs across fields. Both have `mode="before"` and `mode="after"`.
- **`model_config = ConfigDict(...)`** replaces v1's inner `Config` class. The four most useful knobs: `from_attributes`, `extra`, `str_strip_whitespace`, `populate_by_name`.
- **The two-schemas pattern** — `ArticleCreate` for the request, `ArticleRead` for the response — is non-negotiable for security, default-handling, and version drift.
- **Discriminated unions** with `Annotated[T1 | T2, Field(discriminator="kind")]` express endpoints that accept multiple body shapes.
- **JSON Schema** is what Pydantic emits and what FastAPI embeds in `/openapi.json`. Every `Field(description=..., examples=...)` lands in the public OpenAPI document.
- **HTTP 422** is the validation-failure response. The body lists every failing field; the format is customisable via an exception handler.
- **Performance**: Pydantic v2's Rust core makes validation and serialisation microseconds, not milliseconds. The framework cost is no longer a real factor in API latency.

Next lecture: dependency injection and the FastAPI routing model — how `Depends` turns auth, sessions, and pagination into composable, testable functions, and how the OpenAPI document is generated from all of it.

## Further reading

- Pydantic concepts — models: <https://docs.pydantic.dev/latest/concepts/models/>
- Pydantic concepts — fields: <https://docs.pydantic.dev/latest/concepts/fields/>
- Pydantic concepts — validators: <https://docs.pydantic.dev/latest/concepts/validators/>
- Pydantic concepts — serialization: <https://docs.pydantic.dev/latest/concepts/serialization/>
- Pydantic v1 → v2 migration guide: <https://docs.pydantic.dev/latest/migration/>
- FastAPI — Body — Fields: <https://fastapi.tiangolo.com/tutorial/body-fields/>
- FastAPI — Extra models: <https://fastapi.tiangolo.com/tutorial/extra-models/>
- FastAPI — Handling errors: <https://fastapi.tiangolo.com/tutorial/handling-errors/>
- RFC 9110 §15.5.21 — 422 Unprocessable Content: <https://datatracker.ietf.org/doc/html/rfc9110#section-15.5.21>
