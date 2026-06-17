"""
crunchexports.settings — runtime configuration via pydantic-settings.

Read once at process start; injected via FastAPI's Depends or accessed as
a module-level singleton. The .env file (in dev) and process environment
(in prod) populate the fields.

Cited:
    - https://docs.pydantic.dev/latest/concepts/pydantic_settings/
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the environment or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CRUNCHEXPORTS_",
        extra="ignore",
    )

    # Connectivity
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Storage
    export_dir: Path = Field(
        default=Path("/tmp/crunchexports"),
        description="Where rendered exports are written. Must exist and be writable.",
    )
    retention_seconds: int = Field(
        default=86_400,
        ge=60,
        description="Exports older than this are 410 Gone on download.",
    )

    # Channel naming
    progress_channel_prefix: str = Field(default="job-progress")

    # Logging
    log_level: str = Field(default="INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """A cached factory so callers can ``Depends(get_settings)`` cheaply."""
    return Settings()
