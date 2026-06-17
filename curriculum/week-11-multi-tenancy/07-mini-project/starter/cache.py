"""Tenant-prefixed Redis cache wrapper.

Every cache key is automatically prefixed with `tenant:{tenant_id}:`. There
is no path through this class that touches another tenant's keys; the
discipline is by construction.
"""

from __future__ import annotations

import uuid
from typing import Any

try:
    from redis.asyncio import Redis
except ImportError:  # pragma: no cover
    Redis = None  # type: ignore[assignment, misc]


class TenantCache:
    """Per-request wrapper around a shared Redis client.

    Construct with the current tenant_id. Every get/set/delete operation
    routes through `_key`, which adds the tenant prefix.
    """

    def __init__(self, redis: "Redis", tenant_id: uuid.UUID) -> None:
        self._redis = redis
        self._tenant_id = tenant_id

    def _key(self, key: str) -> str:
        return f"tenant:{self._tenant_id}:{key}"

    async def get(self, key: str) -> str | None:
        value: Any = await self._redis.get(self._key(key))
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        await self._redis.set(self._key(key), value, ex=ex)

    async def delete(self, key: str) -> int:
        return int(await self._redis.delete(self._key(key)))

    async def scan_keys(self, pattern: str = "*") -> list[str]:
        """Return all keys for the current tenant matching `pattern`.

        Uses SCAN (cursor-based, non-blocking), not KEYS. The returned
        list has the tenant prefix removed for caller convenience.
        """
        prefix = f"tenant:{self._tenant_id}:"
        full_pattern = f"{prefix}{pattern}"
        keys: list[str] = []
        cursor = 0
        while True:
            cursor, batch = await self._redis.scan(
                cursor=cursor, match=full_pattern, count=100
            )
            for k in batch:
                if isinstance(k, bytes):
                    decoded = k.decode("utf-8")
                else:
                    decoded = str(k)
                keys.append(decoded.removeprefix(prefix))
            if cursor == 0:
                break
        return keys

    async def invalidate_pattern(self, pattern: str) -> int:
        """Delete every key for this tenant matching `pattern`.

        Returns the number of keys deleted.
        """
        keys = await self.scan_keys(pattern)
        if not keys:
            return 0
        full_keys = [self._key(k) for k in keys]
        deleted: int = await self._redis.delete(*full_keys)
        return deleted
