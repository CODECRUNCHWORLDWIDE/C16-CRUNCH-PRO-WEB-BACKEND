"""
Exercise 2 — Pydantic v2 validation: validators, Annotated, discriminated unions.

Time:   ~2 hours.
Goal:   Move every meaningful validation rule from the route handler into
        the Pydantic model. By the end, the route handler does no manual
        if/raise on the request body — Pydantic does.

Run:
    fastapi dev exercise-02-pydantic-validation.py

Visit /docs and inspect:
    - ArticleCreate's JSON Schema (the `pattern` for slug, the validators
      do not appear, but the constraints derived from Field(...) do).
    - The Notification body — see the discriminator at work.

Cited:
    - https://docs.pydantic.dev/latest/concepts/models/
    - https://docs.pydantic.dev/latest/concepts/fields/
    - https://docs.pydantic.dev/latest/concepts/validators/
    - https://docs.pydantic.dev/latest/concepts/unions/   (discriminated unions)
    - https://fastapi.tiangolo.com/tutorial/body-fields/
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Literal, Union

from fastapi import FastAPI, HTTPException, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)
from typing_extensions import Self

app = FastAPI(
    title="C16 W7 Exercise 2 — Pydantic validation",
    description=(
        "Every meaningful validation rule lives in the Pydantic model. "
        "Route handlers do business logic; validation is data-layer concern."
    ),
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Part A — A model with Field-level constraints
# ---------------------------------------------------------------------------
#
# Constraints we use here:
#   - min_length / max_length on strings
#   - pattern on slug (must be lowercase letters, digits, hyphens)
#   - ge on numeric fields
#   - default + default_factory
#   - description and examples for the OpenAPI document
#
# We use Annotated[T, Field(...)] throughout — the 2025 idiom.

class AuthorRef(BaseModel):
    """A minimal embedded reference to an author."""

    id: Annotated[int, Field(ge=1)]
    name: Annotated[str, Field(min_length=1, max_length=120)]


class ArticleCreate(BaseModel):
    """Body of POST /articles. Validation is exhaustive."""

    model_config = ConfigDict(
        # Reject unknown fields rather than silently dropping them.
        extra="forbid",
        # Trim leading/trailing whitespace on every str field on input.
        str_strip_whitespace=True,
    )

    title: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200,
            description="The article title. 1-200 characters.",
            examples=["Hello, Pydantic v2"],
        ),
    ]
    slug: Annotated[
        str,
        Field(
            min_length=1,
            max_length=80,
            pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
            description="URL-safe slug; lowercase letters/digits/hyphens.",
            examples=["hello-pydantic-v2"],
        ),
    ]
    body: Annotated[str, Field(min_length=1)]
    tags: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=10,
            description="Up to 10 tags; each non-empty.",
        ),
    ]
    author: AuthorRef
    published_at: Annotated[
        datetime | None,
        Field(default=None, description="UTC publish time; null for drafts."),
    ]
    is_draft: Annotated[bool, Field(default=True)]

    # -----------------------------------------------------------------
    # Field-level validator: each tag must be non-empty after stripping.
    # mode="after" runs after Pydantic has done basic str coercion.
    # -----------------------------------------------------------------
    @field_validator("tags", mode="after")
    @classmethod
    def tags_non_empty(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = [t.strip() for t in value]
        if any(t == "" for t in cleaned):
            raise ValueError("each tag must be a non-empty string")
        # Tags are deduplicated and lower-cased for storage hygiene.
        return sorted({t.lower() for t in cleaned})

    # -----------------------------------------------------------------
    # Cross-field model validator: a draft cannot have a publish time;
    # a non-draft must have one.
    # -----------------------------------------------------------------
    @model_validator(mode="after")
    def draft_publish_consistency(self) -> Self:
        if self.is_draft and self.published_at is not None:
            raise ValueError(
                "drafts may not have a published_at; clear it or set is_draft=false"
            )
        if not self.is_draft and self.published_at is None:
            raise ValueError(
                "non-draft articles require a published_at"
            )
        return self


class ArticleRead(BaseModel):
    """Response shape. Includes server-side fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    body: str
    tags: list[str]
    author: AuthorRef
    published_at: datetime | None
    is_draft: bool
    created_at: datetime

    # A custom serialiser: emit datetimes with an explicit "Z" suffix and
    # second-precision. This is more compact than the default isoformat
    # and is what most JavaScript clients expect.
    @field_serializer("published_at", "created_at")
    def serialize_dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Part B — A "before" validator that normalises raw input
# ---------------------------------------------------------------------------
#
# Sometimes the input is not quite right and you want to fix it before
# Pydantic's coercion runs. Example: accept either an ISO date string or a
# {"year": ..., "month": ..., "day": ...} dict.

class DateInput(BaseModel):
    when: date

    @field_validator("when", mode="before")
    @classmethod
    def parse_year_month_day(cls, value: object) -> object:
        if isinstance(value, dict):
            try:
                return date(
                    year=int(value["year"]),
                    month=int(value["month"]),
                    day=int(value["day"]),
                )
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError("expected year/month/day integers") from exc
        # Otherwise hand off to Pydantic's default ISO date coercion.
        return value


# ---------------------------------------------------------------------------
# Part C — Discriminated union for a polymorphic endpoint
# ---------------------------------------------------------------------------
#
# A single endpoint accepts three notification shapes. The `kind` field
# discriminates; Pydantic dispatches to the right schema based on its value.

class EmailNotification(BaseModel):
    kind: Literal["email"]
    to_email: Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
    subject: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str, Field(min_length=1)]


class SMSNotification(BaseModel):
    kind: Literal["sms"]
    to_phone: Annotated[str, Field(pattern=r"^\+?[0-9 \-]{7,20}$")]
    body: Annotated[str, Field(min_length=1, max_length=160)]


class PushNotification(BaseModel):
    kind: Literal["push"]
    device_token: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1, max_length=80)]
    body: Annotated[str, Field(min_length=1, max_length=400)]


Notification = Annotated[
    Union[EmailNotification, SMSNotification, PushNotification],
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

_ARTICLES: dict[int, ArticleRead] = {}
_NEXT_ID: dict[str, int] = {"v": 1}


@app.post(
    "/articles",
    response_model=ArticleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an article",
    tags=["articles"],
)
async def create_article(payload: ArticleCreate) -> ArticleRead:
    # The handler is now boring: no manual validation, just store + respond.
    new_id: int = _NEXT_ID["v"]
    _NEXT_ID["v"] = new_id + 1
    article = ArticleRead(
        id=new_id,
        title=payload.title,
        slug=payload.slug,
        body=payload.body,
        tags=payload.tags,
        author=payload.author,
        published_at=payload.published_at,
        is_draft=payload.is_draft,
        created_at=datetime.now(tz=timezone.utc),
    )
    _ARTICLES[new_id] = article
    return article


@app.get(
    "/articles/{article_id}",
    response_model=ArticleRead,
    summary="Get one article",
    tags=["articles"],
)
async def get_article(article_id: int) -> ArticleRead:
    if article_id not in _ARTICLES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article {article_id} not found",
        )
    return _ARTICLES[article_id]


@app.post(
    "/parse-date",
    summary="Parse a date from either string or year/month/day dict",
    tags=["meta"],
)
async def parse_date(payload: DateInput) -> dict[str, str]:
    return {"parsed": payload.when.isoformat()}


@app.post(
    "/notify",
    summary="Send a notification (email, SMS, or push)",
    description=(
        "Body must include a `kind` field. The discriminator routes the "
        "request to the matching schema. Each schema has its own "
        "validation rules."
    ),
    tags=["meta"],
)
async def notify(notification: Notification) -> dict[str, str]:
    # Pydantic guarantees the input has been validated against the
    # discriminated variant. We can access fields polymorphically.
    return {"sent_kind": notification.kind}


# ---------------------------------------------------------------------------
# Exercise tasks
# ---------------------------------------------------------------------------
#
# 1. POST a fully-valid article. Confirm the response is 201 and the body
#    has an `id` and a `created_at`.
#
# 2. POST with `slug="Hello World"`. Confirm a 422 with a `string_pattern_mismatch`
#    error pointing at `body.slug`.
#
# 3. POST with `tags=["python", "", "django"]`. Confirm a 422 with a
#    message from our `tags_non_empty` validator.
#
# 4. POST with `is_draft=true` and `published_at` set. Confirm a 422 from
#    the `draft_publish_consistency` model validator. Note the error's
#    `loc` is `body` — model-level errors do not point to a single field.
#
# 5. POST with `extra="forbid"` enforced: send `{"title": "...", "slug": "...",
#    "body": "...", "author": {...}, "extras": "nope"}`. Confirm a 422
#    pointing at `body.extras`.
#
# 6. POST to /notify with three different `kind` values:
#       {"kind": "email", "to_email": "a@b.com", "subject": "...", "body": "..."}
#       {"kind": "sms",   "to_phone": "+15551234567", "body": "..."}
#       {"kind": "push",  "device_token": "abc", "title": "...", "body": "..."}
#    All three should succeed. Now POST with `kind: "fax"`. The 422 names
#    the discriminator.
#
# 7. POST to /notify with a body that matches no variant cleanly (e.g.,
#    `{"kind": "sms", "to_email": "a@b.com"}`). Note that the error is
#    specific to the SMS schema, not a fan-out of all three.
#
# 8. Open /openapi.json and search for "ArticleCreate". Note:
#       - The `additionalProperties: false` is the JSON Schema rendering of
#         our `extra="forbid"`.
#       - The `pattern` for slug appears in the schema; the validators do
#         not (validators are runtime, not declarative).
#
# 9. Read https://docs.pydantic.dev/latest/concepts/validators/ on the
#    distinction between `mode="before"` and `mode="after"`. Convert the
#    `tags_non_empty` validator from `after` to `before`. What changes?
#    (Hint: in `before`, the value is still the raw input — possibly a
#    non-list. You will need to type-check.)
#
# 10. Read https://docs.pydantic.dev/latest/concepts/serialization/ and
#     find one alternative to `@field_serializer` for the datetime
#     formatting. Compare which is more flexible.
#
# Write the answers as `exercises/02-pydantic.md` and commit.
