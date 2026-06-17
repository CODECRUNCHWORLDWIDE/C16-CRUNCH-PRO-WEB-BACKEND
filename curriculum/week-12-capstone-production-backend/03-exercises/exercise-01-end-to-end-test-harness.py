"""Exercise 01 — End-to-end integration test harness for the capstone.

This module is the harness the capstone test suite uses to prove the W1
through W12 stack composes. The harness wires:

  - A live Postgres instance (the W4 / W10 / W11 substrate).
  - A live Redis instance (the W9 cache / pub-sub / rate-limit backplane).
  - The Django process under the test server (the W2 / W3 admin).
  - The FastAPI process under httpx.AsyncClient (the W7 / W8 public API).
  - The ARQ worker in-process (the W6 / W8 background-job runner).

The harness is opinionated: it tears down between tests, it uses real
Postgres and real Redis (no mocks; see `testcontainers` style fixtures),
and it asserts both the HTTP-level outcome (status code, JSON body) and
the database-level outcome (the row exists with the right `tenant_id`).

References:

  - https://docs.pytest.org/en/stable/
  - https://pytest-asyncio.readthedocs.io/en/latest/
  - https://www.python-httpx.org/
  - https://fastapi.tiangolo.com/advanced/testing-websockets/
  - https://pytest-django.readthedocs.io/en/latest/

Run the file directly:

    python3 exercise-01-end-to-end-test-harness.py

It executes the demo harness against an in-memory stub of the capstone
(real services are wired in the mini-project). Compile with:

    python3 -m py_compile exercise-01-end-to-end-test-harness.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger("capstone.harness")


# ----------------------------------------------------------------------
# Pydantic v2 models — the contracts the harness asserts against.
# ----------------------------------------------------------------------


class TenantSignupRequest(BaseModel):
    """The signup payload the Django /admin/signup endpoint expects."""

    slug: str = Field(..., min_length=2, max_length=32, pattern=r"^[a-z][a-z0-9-]*$")
    tenant_name: str = Field(..., min_length=2, max_length=64)
    admin_email: str = Field(..., min_length=5, max_length=254)
    admin_password: str = Field(..., min_length=12, max_length=128)


class TenantSignupResponse(BaseModel):
    """The signup response Django returns."""

    tenant_id: UUID
    api_token: str
    admin_url: str


class ArticleCreateRequest(BaseModel):
    """The article-create payload the FastAPI /api/articles endpoint expects."""

    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=50_000)
    tags: list[str] = Field(default_factory=list, max_length=10)


class ArticleResponse(BaseModel):
    """The article representation returned by the FastAPI API."""

    id: UUID
    tenant_id: UUID
    title: str
    body: str
    created_at: float
    updated_at: float
    tags: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """A single search result item."""

    id: UUID
    title: str
    rank: float
    snippet: str


class WebSocketEvent(BaseModel):
    """The shape of every event pushed over the WebSocket."""

    type: str = Field(..., pattern=r"^[a-z]+\.[a-z]+$")
    article_id: UUID
    title: str
    timestamp: float


# ----------------------------------------------------------------------
# The stub stack — substituted for real services in this exercise file.
# ----------------------------------------------------------------------


@dataclass
class StubDatabase:
    """An in-memory stand-in for Postgres + RLS.

    Real harness uses asyncpg against a `testcontainers` Postgres. This
    stub captures the *behaviour* under test: rows are partitioned by
    `tenant_id`, and a query with the wrong tenant returns zero rows.
    """

    rows: dict[tuple[UUID, UUID], dict[str, Any]] = field(default_factory=dict)

    async def insert_article(
        self, tenant_id: UUID, payload: ArticleCreateRequest
    ) -> ArticleResponse:
        article_id = uuid4()
        now = time.time()
        row = {
            "id": article_id,
            "tenant_id": tenant_id,
            "title": payload.title,
            "body": payload.body,
            "tags": list(payload.tags),
            "created_at": now,
            "updated_at": now,
        }
        self.rows[(tenant_id, article_id)] = row
        return ArticleResponse(**row)

    async def fetch_article(
        self, tenant_id: UUID, article_id: UUID
    ) -> ArticleResponse | None:
        row = self.rows.get((tenant_id, article_id))
        if row is None:
            return None
        return ArticleResponse(**row)

    async def search(self, tenant_id: UUID, query: str) -> list[SearchResult]:
        """A trivial substring search — the W10 lecture's `tsvector` is the
        production version. Filters by tenant; mimics the RLS contract.
        """
        results: list[SearchResult] = []
        needle = query.lower()
        for (row_tenant, row_id), row in self.rows.items():
            if row_tenant != tenant_id:
                continue
            text = (row["title"] + " " + row["body"]).lower()
            if needle in text:
                # Crude rank: more occurrences = higher rank.
                rank = float(text.count(needle))
                snippet = self._make_snippet(row["body"], needle)
                results.append(
                    SearchResult(
                        id=row_id,
                        title=row["title"],
                        rank=rank,
                        snippet=snippet,
                    )
                )
        results.sort(key=lambda r: r.rank, reverse=True)
        return results

    @staticmethod
    def _make_snippet(body: str, needle: str) -> str:
        idx = body.lower().find(needle)
        if idx < 0:
            return body[:80]
        start = max(idx - 30, 0)
        end = min(idx + len(needle) + 30, len(body))
        return ("..." if start > 0 else "") + body[start:end] + ("..." if end < len(body) else "")


@dataclass
class StubRedis:
    """Simulates the Redis surfaces the capstone uses: cache, pub/sub, rate limit."""

    cache: dict[str, tuple[str, float]] = field(default_factory=dict)
    rate_limit: dict[str, int] = field(default_factory=dict)
    subscribers: dict[str, list[asyncio.Queue[str]]] = field(default_factory=dict)

    async def get_cached(self, key: str) -> str | None:
        entry = self.cache.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at < time.time():
            self.cache.pop(key, None)
            return None
        return value

    async def set_cached(self, key: str, value: str, ttl_seconds: int) -> None:
        self.cache[key] = (value, time.time() + ttl_seconds)

    async def incr_rate(self, key: str, ceiling: int, window: int) -> bool:
        """Token-bucket: True if request is allowed; False if over the limit."""
        current = self.rate_limit.get(key, 0)
        if current >= ceiling:
            return False
        self.rate_limit[key] = current + 1
        if current == 0:
            asyncio.get_event_loop().call_later(window, self._reset, key)
        return True

    def _reset(self, key: str) -> None:
        self.rate_limit.pop(key, None)

    async def publish(self, channel: str, message: str) -> int:
        queues = self.subscribers.get(channel, [])
        for q in queues:
            await q.put(message)
        return len(queues)

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[asyncio.Queue[str]]:
        q: asyncio.Queue[str] = asyncio.Queue()
        self.subscribers.setdefault(channel, []).append(q)
        try:
            yield q
        finally:
            self.subscribers[channel].remove(q)


# ----------------------------------------------------------------------
# The harness — wires the stubs and exposes pytest-friendly helpers.
# ----------------------------------------------------------------------


@dataclass
class Harness:
    """The end-to-end test harness.

    In real use this is built by a pytest fixture that brings up
    Postgres and Redis containers, runs migrations, and instantiates
    the FastAPI app via httpx.AsyncClient. This stand-in keeps the
    interface stable so the exercise compiles and demonstrates the
    test patterns.
    """

    db: StubDatabase = field(default_factory=StubDatabase)
    redis: StubRedis = field(default_factory=StubRedis)
    tenants: dict[str, TenantSignupResponse] = field(default_factory=dict)

    async def signup_tenant(self, slug: str) -> TenantSignupResponse:
        """Simulates POST /admin/signup."""
        payload = TenantSignupRequest(
            slug=slug,
            tenant_name=slug.title(),
            admin_email=f"admin@{slug}.test",
            admin_password=secrets.token_urlsafe(16),
        )
        response = TenantSignupResponse(
            tenant_id=uuid4(),
            api_token=secrets.token_urlsafe(32),
            admin_url=f"/admin/{payload.slug}/",
        )
        self.tenants[slug] = response
        return response

    async def create_article(
        self,
        tenant_slug: str,
        title: str,
        body: str,
        tags: list[str] | None = None,
    ) -> ArticleResponse:
        """Simulates POST /api/articles with the tenant resolved from header."""
        tenant = self.tenants[tenant_slug]
        # Rate-limit check (the W9 pattern).
        key = f"ratelimit:tenant:{tenant.tenant_id}:/api/articles"
        allowed = await self.redis.incr_rate(key, ceiling=60, window=60)
        if not allowed:
            raise RuntimeError("rate-limited")
        # Insert the article (the W11 RLS would scope this in real Postgres).
        payload = ArticleCreateRequest(title=title, body=body, tags=tags or [])
        article = await self.db.insert_article(tenant.tenant_id, payload)
        # Cache invalidation (the W9 read-through cache).
        cache_key = f"tenant:{tenant.tenant_id}:cache:article:{article.id}"
        self.redis.cache.pop(cache_key, None)
        # Publish event to the WebSocket channel.
        event = WebSocketEvent(
            type="article.created",
            article_id=article.id,
            title=article.title,
            timestamp=time.time(),
        )
        await self.redis.publish(
            f"tenant:{tenant.tenant_id}:events",
            event.model_dump_json(),
        )
        return article

    async def get_article(
        self, tenant_slug: str, article_id: UUID
    ) -> ArticleResponse | None:
        """Simulates GET /api/articles/{id} with the W9 read-through cache."""
        tenant = self.tenants[tenant_slug]
        cache_key = f"tenant:{tenant.tenant_id}:cache:article:{article_id}"
        cached = await self.redis.get_cached(cache_key)
        if cached:
            return ArticleResponse.model_validate_json(cached)
        article = await self.db.fetch_article(tenant.tenant_id, article_id)
        if article is None:
            return None
        await self.redis.set_cached(cache_key, article.model_dump_json(), ttl_seconds=300)
        return article

    async def search(self, tenant_slug: str, query: str) -> list[SearchResult]:
        """Simulates GET /api/search?q=..."""
        tenant = self.tenants[tenant_slug]
        return await self.db.search(tenant.tenant_id, query)

    async def stream_events(
        self,
        tenant_slug: str,
        callback: Callable[[WebSocketEvent], Awaitable[None]],
        timeout_seconds: float = 2.0,
    ) -> int:
        """Simulates a WebSocket subscription; returns event count received."""
        tenant = self.tenants[tenant_slug]
        channel = f"tenant:{tenant.tenant_id}:events"
        received = 0
        async with self.redis.subscribe(channel) as q:
            deadline = time.time() + timeout_seconds
            while time.time() < deadline:
                try:
                    remaining = max(deadline - time.time(), 0.05)
                    raw = await asyncio.wait_for(q.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                event = WebSocketEvent.model_validate_json(raw)
                await callback(event)
                received += 1
        return received


# ----------------------------------------------------------------------
# The demonstration tests — what pytest cases look like.
# ----------------------------------------------------------------------


async def test_signup_creates_tenant() -> None:
    """A tenant signup produces a tenant_id and an api_token."""
    h = Harness()
    response = await h.signup_tenant("acme")
    assert response.tenant_id is not None
    assert len(response.api_token) >= 32
    assert response.admin_url == "/admin/acme/"


async def test_article_round_trip() -> None:
    """An inserted article is fetchable through the W9 read-through cache."""
    h = Harness()
    await h.signup_tenant("acme")
    article = await h.create_article("acme", "Hello", "World, this is a test body.")
    assert article.title == "Hello"
    # Fetch goes through Postgres (cache miss).
    fetched = await h.get_article("acme", article.id)
    assert fetched is not None
    assert fetched.title == article.title
    # Second fetch hits the cache.
    cached = await h.get_article("acme", article.id)
    assert cached is not None
    assert cached.id == article.id


async def test_search_finds_inserted_article() -> None:
    """The search endpoint returns a result for the inserted article."""
    h = Harness()
    await h.signup_tenant("acme")
    await h.create_article(
        "acme",
        "Production-grade Python backend",
        "We ship a complete backend exercising every prior week of the curriculum.",
    )
    results = await h.search("acme", "backend")
    assert len(results) >= 1
    assert "backend" in results[0].title.lower() or "backend" in results[0].snippet.lower()


async def test_cross_tenant_isolation() -> None:
    """Tenant A's article is invisible to tenant B's search and fetch."""
    h = Harness()
    await h.signup_tenant("acme")
    await h.signup_tenant("globex")
    article_a = await h.create_article("acme", "Only Acme sees this", "Body.")
    # Tenant B searches for the same term: zero results.
    results_b = await h.search("globex", "Only Acme")
    assert results_b == []
    # Tenant B fetches the article by ID: 404 (None from the harness).
    fetched_b = await h.get_article("globex", article_a.id)
    assert fetched_b is None


async def test_websocket_receives_article_created_event() -> None:
    """A subscriber to the tenant channel receives the article.created event."""
    h = Harness()
    await h.signup_tenant("acme")
    received: list[WebSocketEvent] = []

    async def collector(event: WebSocketEvent) -> None:
        received.append(event)

    # Start the subscriber, then publish.
    async def workload() -> None:
        await asyncio.sleep(0.05)
        await h.create_article("acme", "Live event test", "Body.")

    streamer = asyncio.create_task(h.stream_events("acme", collector, timeout_seconds=1.0))
    publisher = asyncio.create_task(workload())
    await asyncio.gather(streamer, publisher)

    assert len(received) >= 1
    assert received[0].type == "article.created"
    assert received[0].title == "Live event test"


async def test_rate_limit_blocks_after_ceiling() -> None:
    """The 61st request from one tenant inside the window is rate-limited."""
    h = Harness()
    await h.signup_tenant("acme")
    # The harness ceiling is 60 in 60 seconds.
    for i in range(60):
        await h.create_article("acme", f"item {i}", "body")
    try:
        await h.create_article("acme", "the breaker", "body")
    except RuntimeError as exc:
        assert "rate-limited" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for rate-limit breach")


# ----------------------------------------------------------------------
# Test runner — the file is executable.
# ----------------------------------------------------------------------


async def run_all() -> int:
    """Run the demonstration tests in order; return the number of failures."""
    tests: list[Callable[[], Awaitable[None]]] = [
        test_signup_creates_tenant,
        test_article_round_trip,
        test_search_finds_inserted_article,
        test_cross_tenant_isolation,
        test_websocket_receives_article_created_event,
        test_rate_limit_blocks_after_ceiling,
    ]
    failures = 0
    for test in tests:
        name = test.__name__
        try:
            await test()
        except AssertionError as exc:
            print(f"FAIL: {name}: {exc}")
            failures += 1
        except Exception as exc:  # pragma: no cover
            print(f"ERROR: {name}: {type(exc).__name__}: {exc}")
            failures += 1
        else:
            print(f"OK:   {name}")
    return failures


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(f"Running {sys.argv[0]} — the W12 end-to-end harness demo")
    failures = asyncio.run(run_all())
    if failures:
        print(f"\n{failures} test(s) failed.")
        return 1
    print("\nAll harness demonstrations passed.")
    print("In the capstone, replace the stubs with real Postgres + Redis fixtures.")
    print("See the mini-project starter for the production wiring.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
