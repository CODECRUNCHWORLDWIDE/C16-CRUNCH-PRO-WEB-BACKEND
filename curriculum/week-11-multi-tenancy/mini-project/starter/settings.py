"""Environment-driven settings for the crunchtenant service."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Service configuration.

    All values are populated from environment variables with sensible
    defaults for local development. In production, override every value.
    """

    # Database: the application connects as crunchreader_app (non-superuser,
    # non-BYPASSRLS). Never use the postgres superuser here.
    db_dsn: str = os.environ.get(
        "CC_W11_APP_DSN",
        "postgresql://crunchreader_app:Crunch_Pro_W11_pw@localhost:5432/cc_w11",
    )
    db_pool_min_size: int = int(os.environ.get("CC_W11_POOL_MIN", "2"))
    db_pool_max_size: int = int(os.environ.get("CC_W11_POOL_MAX", "10"))

    # Redis: shared cache + rate-limit store. Tenant ID is in every key.
    redis_url: str = os.environ.get("CC_W11_REDIS_URL", "redis://localhost:6379/0")

    # Admin: a bearer token for the admin endpoints. In production, replace
    # with a proper IAM check (JWT with `role: admin` claim, IAM role, etc).
    admin_token: str = os.environ.get("CC_W11_ADMIN_TOKEN", "change-me-in-production")

    # Per-tenant rate-limit defaults by tier. The rate_limits table can
    # override these per (tenant, endpoint).
    default_rate_limits: dict[str, tuple[int, float]] | None = None

    def tier_default(self, tier: str) -> tuple[int, float]:
        """Return (capacity, refill_rate) for a tier."""
        defaults: dict[str, tuple[int, float]] = {
            "free": (10, 1.0),
            "paid": (100, 10.0),
            "enterprise": (1000, 100.0),
        }
        return defaults.get(tier, defaults["free"])


def load_settings() -> Settings:
    return Settings()
