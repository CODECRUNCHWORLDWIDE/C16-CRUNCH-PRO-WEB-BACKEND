"""
crunchexports.schemas — Pydantic v2 schemas for the export service.

The three load-bearing models:

    ExportRequest   — body of POST /exports
    ExportAccepted  — 202 response from POST /exports
    ExportStatus    — body of GET /exports/{job_id}

Validators on ExportRequest enforce:
    - from_date <= to_date
    - to_date - from_date <= 365 days
    - extra="forbid" on the model_config

Cited:
    - https://docs.pydantic.dev/latest/concepts/models/
    - https://docs.pydantic.dev/latest/concepts/validators/
    - https://datatracker.ietf.org/doc/html/rfc9110#section-15.3.3
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ExportKind = Literal["users", "orders", "events"]
ExportFormat = Literal["csv", "tsv"]
ExportStatusLiteral = Literal["pending", "running", "done", "failed", "cancelled"]


class ExportRequest(BaseModel):
    """The body of POST /exports."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: ExportKind = Field(description="What to export.")
    from_date: date = Field(description="Inclusive lower bound of the date range.")
    to_date: date = Field(description="Inclusive upper bound of the date range.")
    format: ExportFormat = Field(default="csv", description="Output format.")
    delimiter: str = Field(default=",", min_length=1, max_length=1)
    include_headers: bool = Field(default=True, description="Emit a header row.")

    @model_validator(mode="after")
    def _validate_range(self) -> "ExportRequest":
        """Enforce from_date <= to_date and a 365-day maximum span."""
        if self.from_date > self.to_date:
            raise ValueError(
                "from_date must be on or before to_date; "
                f"got from_date={self.from_date}, to_date={self.to_date}"
            )
        span = (self.to_date - self.from_date).days
        if span > 365:
            raise ValueError(
                "the date range may not exceed 365 days; "
                f"got {span} days between {self.from_date} and {self.to_date}"
            )
        return self


class ExportAccepted(BaseModel):
    """The 202 response body returned by POST /exports."""

    job_id: str = Field(description="UUID v4. Used for both polling and SSE.")
    stream_url: str = Field(description="The SSE URL to consume with EventSource.")
    poll_url: str = Field(description="The status URL for periodic GETs.")


class ExportStatus(BaseModel):
    """The body of GET /exports/{job_id}."""

    job_id: str
    status: ExportStatusLiteral
    progress: float = Field(ge=0.0, le=1.0, description="0.0 to 1.0; 1.0 once done.")
    created_at: datetime
    finished_at: datetime | None = None
    download_url: str | None = Field(
        default=None,
        description="Set when status == 'done'; cleared after retention.",
    )
    error: str | None = Field(
        default=None,
        description="Set when status == 'failed'.",
    )
