"""Per-tenant token-bucket rate limiter on Redis.

The Lua script runs atomically: a concurrent request from the same tenant
cannot observe a partially-updated bucket. The bucket key is
`ratelimit:tenant:{tenant_id}:{endpoint}`; the capacity and refill rate
come from a per-tenant `rate_limits` table (or per-tier defaults).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

try:
    from redis.asyncio import Redis
except ImportError:  # pragma: no cover
    Redis = None  # type: ignore[assignment, misc]


# Atomic token-bucket Lua. See Exercise 4 for the line-by-line walk.
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

local elapsed = now - last_refill
if elapsed > 0 then
    tokens = math.min(capacity, tokens + elapsed * refill_rate)
end

local allowed = 0
if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
end

redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
redis.call('EXPIRE', key, 3600)

return allowed
"""


@dataclass
class RateLimit:
    capacity: int
    refill_rate: float


async def try_consume(
    redis: "Redis",
    tenant_id: uuid.UUID,
    endpoint: str,
    limit: RateLimit,
    cost: int = 1,
) -> bool:
    """Attempt to consume `cost` tokens. Return True if allowed.

    The Redis call is atomic via EVAL. Concurrent calls from the same
    tenant cannot interleave check-then-decrement.
    """
    key = f"ratelimit:tenant:{tenant_id}:{endpoint}"
    now = time.time()
    result = await redis.eval(  # type: ignore[no-untyped-call]
        TOKEN_BUCKET_LUA,
        1,
        key,
        limit.capacity,
        limit.refill_rate,
        now,
        cost,
    )
    return bool(int(result))


async def current_tokens(
    redis: "Redis",
    tenant_id: uuid.UUID,
    endpoint: str,
    limit: RateLimit,
) -> float:
    """Inspect the bucket without consuming.

    Useful for the Retry-After header: `(cost - current) / refill_rate`
    is roughly the seconds until enough tokens accumulate.
    """
    key = f"ratelimit:tenant:{tenant_id}:{endpoint}"
    data = await redis.hmget(key, "tokens", "last_refill")
    tokens_raw, last_refill_raw = data
    if tokens_raw is None:
        return float(limit.capacity)
    tokens = float(tokens_raw)
    last_refill = float(last_refill_raw or 0)
    elapsed = time.time() - last_refill
    return min(float(limit.capacity), tokens + elapsed * limit.refill_rate)
