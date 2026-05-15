"""Configuration loaded from environment variables, with sane defaults.

Uses Pydantic v2 BaseSettings (pydantic-settings package). Each service URL
is overridable per-environment; defaults assume local containers from the
README pre-flight checks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Static config for crunchsearch. Read at startup; never mutated."""

    postgres_dsn: str
    redis_url: str
    opensearch_host: str
    opensearch_port: int
    opensearch_user: str
    opensearch_pass: str
    opensearch_index: str
    meili_url: str
    meili_key: str
    meili_index: str
    default_backend: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Read environment; return a frozen Settings instance."""
        return cls(
            postgres_dsn=os.environ.get(
                "CC_W10_DSN",
                "postgresql://postgres:postgres@localhost:5432/cc_w10",
            ),
            redis_url=os.environ.get("CC_W10_REDIS_URL", "redis://localhost:6379/0"),
            opensearch_host=os.environ.get("CC_W10_OS_HOST", "localhost"),
            opensearch_port=int(os.environ.get("CC_W10_OS_PORT", "9200")),
            opensearch_user=os.environ.get("CC_W10_OS_USER", "admin"),
            opensearch_pass=os.environ.get("CC_W10_OS_PASS", "Crunch_Pro_W10_pw"),
            opensearch_index=os.environ.get("CC_W10_OS_INDEX", "cc_w10_articles"),
            meili_url=os.environ.get("CC_W10_MEILI_URL", "http://localhost:7700"),
            meili_key=os.environ.get("CC_W10_MEILI_KEY", "Crunch_Pro_W10_key"),
            meili_index=os.environ.get("CC_W10_MEILI_INDEX", "cc_w10_articles"),
            default_backend=os.environ.get("CC_W10_DEFAULT_BACKEND", "postgres"),
        )


def get_settings() -> Settings:
    """Lazy singleton-style accessor.

    Re-reads the environment if you call it after mutating os.environ — fine
    for tests; do not rely on it in hot paths.
    """
    return Settings.from_env()
