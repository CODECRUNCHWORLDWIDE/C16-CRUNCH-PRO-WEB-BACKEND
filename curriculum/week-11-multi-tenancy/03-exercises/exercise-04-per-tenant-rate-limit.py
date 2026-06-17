"""
Exercise 4 — Per-tenant token-bucket rate limiting on Redis.

Time:   ~1.5 hours.
Goal:   Build a token-bucket rate limiter that gives each tenant their own
        bucket. The bucket key is `ratelimit:tenant:{tenant_id}:{endpoint}`;
        the capacity and refill rate come from a per-tenant `rate_limits`
        table. The Lua script is atomic on Redis — concurrent requests
        cannot interleave a check-then-decrement.

        Then run the noisy-neighbour smoke test: Tenant A spams the
        endpoint while Tenant B sends one request per second. Tenant A
        is rate-limited; Tenant B sees no impact. The per-tenant cap
        contains the blast radius.

Run:
    # Terminal 1: Redis up.
    redis-cli ping
    # PONG

    # Terminal 2: run this script.
    python3 exercise-04-per-tenant-rate-limit.py

Cited:
    - https://redis.io/docs/latest/commands/eval/
    - https://blog.cloudflare.com/counting-things-a-lot-of-different-things/
    - https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/noisy-neighbor.html

The TASK comments below mark prompts you should answer in SOLUTIONS.md.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass

try:
    from redis.asyncio import Redis
except ImportError:  # pragma: no cover
    Redis = None  # type: ignore[assignment, misc]


logger = logging.getLogger("rate_limit_exercise")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


REDIS_URL = os.environ.get("CC_W11_REDIS_URL", "redis://localhost:6379/0")


# ---------------------------------------------------------------------------
# The atomic token-bucket Lua script.
#
# Variables:
#   KEYS[1]  = the bucket key (a Redis hash holding tokens and last_refill)
#   ARGV[1]  = capacity (max tokens)
#   ARGV[2]  = refill_rate (tokens per second)
#   ARGV[3]  = now (float, seconds since epoch)
#   ARGV[4]  = cost (tokens to consume)
#
# Returns:
#   1 if allowed, 0 if rejected.
# ---------------------------------------------------------------------------


RATE_LIMIT_LUA = """
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


# ---------------------------------------------------------------------------
# Per-tenant rate-limit configuration.
# ---------------------------------------------------------------------------


@dataclass
class TenantRateLimit:
    """One tenant's rate-limit policy for one endpoint.

    `capacity` is the burst limit (the bucket's maximum). `refill_rate`
    is the sustained-throughput limit in tokens/second.
    """

    capacity: int
    refill_rate: float


# In production this would come from a Postgres `rate_limits` table.
# For the exercise, we hard-code per-tier policies.
TIER_POLICIES: dict[str, TenantRateLimit] = {
    "free": TenantRateLimit(capacity=10, refill_rate=1.0),
    "paid": TenantRateLimit(capacity=100, refill_rate=10.0),
    "enterprise": TenantRateLimit(capacity=1000, refill_rate=100.0),
}


# ---------------------------------------------------------------------------
# Consumer
# ---------------------------------------------------------------------------


async def consume_token(
    redis: "Redis",
    tenant_id: uuid.UUID,
    endpoint: str,
    policy: TenantRateLimit,
    cost: int = 1,
) -> bool:
    """Consume `cost` tokens from the bucket. Return True if allowed."""
    key = f"ratelimit:tenant:{tenant_id}:{endpoint}"
    now = time.time()
    result = await redis.eval(  # type: ignore[no-untyped-call]
        RATE_LIMIT_LUA,
        1,
        key,
        policy.capacity,
        policy.refill_rate,
        now,
        cost,
    )
    return bool(int(result))


# TASK 1: write a function `current_tokens(redis, tenant_id, endpoint)`
# that reads the current token count for a bucket WITHOUT consuming
# anything. Useful for surfacing in a 429 response header (Retry-After
# becomes derivable from "tokens remaining / refill rate"). Implement
# in SOLUTIONS.md.


# ---------------------------------------------------------------------------
# Workloads
# ---------------------------------------------------------------------------


async def burst_workload(
    redis: "Redis",
    tenant_id: uuid.UUID,
    endpoint: str,
    policy: TenantRateLimit,
    total_requests: int,
    label: str,
) -> tuple[int, int]:
    """Send `total_requests` in a tight loop. Returns (allowed, rejected)."""
    allowed = 0
    rejected = 0
    for _ in range(total_requests):
        ok = await consume_token(redis, tenant_id, endpoint, policy)
        if ok:
            allowed += 1
        else:
            rejected += 1
    logger.info(
        "[%s] burst tenant=%s endpoint=%s allowed=%d rejected=%d",
        label,
        tenant_id,
        endpoint,
        allowed,
        rejected,
    )
    return allowed, rejected


async def paced_workload(
    redis: "Redis",
    tenant_id: uuid.UUID,
    endpoint: str,
    policy: TenantRateLimit,
    duration_seconds: float,
    requests_per_second: float,
    label: str,
) -> tuple[int, int]:
    """Send requests at a steady rate. Returns (allowed, rejected)."""
    allowed = 0
    rejected = 0
    interval = 1.0 / requests_per_second
    end_time = time.time() + duration_seconds
    while time.time() < end_time:
        ok = await consume_token(redis, tenant_id, endpoint, policy)
        if ok:
            allowed += 1
        else:
            rejected += 1
        await asyncio.sleep(interval)
    logger.info(
        "[%s] paced tenant=%s endpoint=%s allowed=%d rejected=%d",
        label,
        tenant_id,
        endpoint,
        allowed,
        rejected,
    )
    return allowed, rejected


# ---------------------------------------------------------------------------
# Noisy-neighbour smoke test
# ---------------------------------------------------------------------------


async def noisy_neighbour_test(redis: "Redis") -> None:
    """Two tenants. A is bursty; B is paced. With per-tenant buckets,
    A's burst should NOT consume B's budget.

    Without per-tenant separation (i.e. one global rate limit), A would
    consume the entire budget and B's paced requests would all be
    rejected. The exercise here demonstrates that the per-tenant key
    makes the bursts independent.
    """
    tenant_a = uuid.UUID(int=1)
    tenant_b = uuid.UUID(int=2)
    endpoint = "/articles"
    policy = TIER_POLICIES["paid"]  # 100-burst, 10/sec sustained.

    logger.info("=== noisy-neighbour smoke test ===")
    # Reset the buckets to start fresh.
    await redis.delete(f"ratelimit:tenant:{tenant_a}:{endpoint}")
    await redis.delete(f"ratelimit:tenant:{tenant_b}:{endpoint}")

    # Run A's burst (200 requests in a tight loop) concurrently with
    # B's paced load (5 requests/second for 4 seconds = 20 requests).
    a_task = asyncio.create_task(
        burst_workload(redis, tenant_a, endpoint, policy, 200, "tenant_a_burst")
    )
    b_task = asyncio.create_task(
        paced_workload(redis, tenant_b, endpoint, policy, 4.0, 5.0, "tenant_b_paced")
    )
    a_allowed, a_rejected = await a_task
    b_allowed, b_rejected = await b_task

    # Assertions:
    # - A hit its burst limit and lost most of the 200 requests.
    # - B's 20 paced requests should all be allowed (well within its
    #   own 100-token bucket).
    assert a_rejected > 0, "tenant A should have been rate-limited"
    assert b_rejected == 0, (
        f"tenant B should NOT have been rate-limited; "
        f"per-tenant buckets are independent. Got rejected={b_rejected}"
    )
    logger.info(
        "PASS: A rejected=%d (rate-limited), B rejected=%d (not impacted)",
        a_rejected,
        b_rejected,
    )


# TASK 2: change `noisy_neighbour_test` to use a SHARED key (e.g.
# `ratelimit:global:{endpoint}`) instead of a per-tenant key. Run the
# test. Observe that B's requests get rejected because A consumed the
# shared bucket. Record the result in SOLUTIONS.md, with the assertion
# error message.


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    if Redis is None:
        raise RuntimeError("redis is not installed; pip install redis")
    redis = Redis.from_url(REDIS_URL, decode_responses=False)
    try:
        # Quick smoke test: free-tier tenant gets 10 allowed, 5 rejected
        # for a 15-request burst.
        tenant = uuid.UUID(int=42)
        endpoint = "/articles"
        policy = TIER_POLICIES["free"]
        await redis.delete(f"ratelimit:tenant:{tenant}:{endpoint}")
        allowed, rejected = await burst_workload(
            redis, tenant, endpoint, policy, 15, "smoke"
        )
        assert allowed == 10, f"expected 10 allowed (capacity); got {allowed}"
        assert rejected == 5, f"expected 5 rejected (15 - 10); got {rejected}"
        logger.info("smoke test passed: 10 allowed, 5 rejected, as expected")

        # The main event: per-tenant isolation under noisy-neighbour load.
        await noisy_neighbour_test(redis)

    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
