"""Settings — pydantic-settings configuration.

Read environment variables and a .env file into a typed Settings object.
Used by every module that needs configuration; injected via a FastAPI
dependency where appropriate.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration. Loaded from environment + .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0",
                           description="Redis connection URL for cache and Pub/Sub.")
    redis_invalidate_channel: str = Field(default="crunchcache:invalidate",
                                           description="Pub/Sub channel for invalidation events.")

    # --- SQLite ---
    sqlite_path: str = Field(default="./crunchcache.db",
                             description="Path to the SQLite database file.")

    # --- Cache TTLs (in seconds) ---
    article_ttl: int = Field(default=3600,
                             description="TTL for v1:article:{id} cache entries.")
    popular_ttl: int = Field(default=60,
                             description="TTL for v1:articles:popular:{limit} cache entries.")
    filter_ttl: int = Field(default=300,
                            description="TTL for v1:articles:filter:author:{id} cache entries.")

    # --- Feature flags ---
    cache_enabled: bool = Field(default=True,
                                 description="Master switch for the cache layer; benchmark uses this.")

    # --- Stampede protection ---
    stampede_strategy: str = Field(default="coalesce",
                                    description="One of 'coalesce', 'xfetch', 'none'.")
    xfetch_delta_seconds: float = Field(default=0.2,
                                         description="Expected loader latency for XFetch.")
    xfetch_beta: float = Field(default=1.0,
                                description="XFetch beta parameter; 1.0 is optimal per Vattani 2015.")


def get_settings() -> Settings:
    """Return a fresh Settings instance.

    In production, you would cache this with functools.lru_cache so it loads
    once. For the starter, a fresh call per dependency is fine.
    """
    return Settings()
