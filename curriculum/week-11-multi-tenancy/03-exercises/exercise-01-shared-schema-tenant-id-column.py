"""
Exercise 1 — Shared-schema multi-tenancy with a tenant_id column.

Time:   ~1 hour.
Goal:   Build the shared-schema multi-tenant model from scratch. Insert
        articles for two different tenants. Run queries that filter by
        tenant_id; run queries that do not, and observe the cross-tenant
        leak. This is the failure mode RLS (Exercise 2) is designed to
        prevent. Seeing the leak first makes the fix make sense.

Run:
    # 1. Postgres reachable on localhost:5432.
    createdb cc_w11

    # 2. Apply the schema (the SQL exercise file builds the tables).
    psql -d cc_w11 -f exercise-05-multi-tenancy.sql

    # 3. Run this Python script.
    python3 exercise-01-shared-schema-tenant-id-column.py

Try:
    Run the script as-is. Notice that the "leak" path returns articles
    for both tenants. Then re-run with the filter; the leak closes.

    The whole point of Exercise 2 is to make the closed-by-default version
    the only one available, via RLS.

Cited:
    - https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/tenant-isolation.html
    - https://docs.citusdata.com/en/stable/use_cases/multi_tenant.html

The TASK comments below mark prompts you should answer in SOLUTIONS.md.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]


logger = logging.getLogger("shared_schema_exercise")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


DSN = os.environ.get(
    "CC_W11_DSN",
    "postgresql://postgres:postgres@localhost:5432/cc_w11",
)


# ---------------------------------------------------------------------------
# Part A — Tenant seed data
# ---------------------------------------------------------------------------


SEED_TENANTS: list[dict[str, str]] = [
    {"slug": "acme", "name": "Acme Corporation"},
    {"slug": "globex", "name": "Globex Industries"},
]


SEED_ARTICLES: dict[str, list[dict[str, Any]]] = {
    "acme": [
        {
            "title": "Acme Q1 launch plan",
            "body": "The internal launch plan for the new acme widget. Confidential.",
            "author": "Alice Acme",
        },
        {
            "title": "Acme team retreat agenda",
            "body": "Logistics, sessions, the canyon hike. Internal only.",
            "author": "Alice Acme",
        },
    ],
    "globex": [
        {
            "title": "Globex pricing strategy",
            "body": "How Globex will price the new container line. Highly confidential.",
            "author": "Bob Globex",
        },
        {
            "title": "Globex board notes — March 2026",
            "body": "Quarterly review, the AI initiative, the budget approval.",
            "author": "Bob Globex",
        },
    ],
}


# ---------------------------------------------------------------------------
# Part B — Seed the corpus
# ---------------------------------------------------------------------------


async def seed_tenants(conn: "asyncpg.Connection") -> dict[str, uuid.UUID]:
    """Insert the seed tenants. Returns a slug -> tenant_id map."""
    slug_to_id: dict[str, uuid.UUID] = {}
    for tenant in SEED_TENANTS:
        row = await conn.fetchrow(
            """
            INSERT INTO tenants (slug, name)
            VALUES ($1, $2)
            ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            tenant["slug"],
            tenant["name"],
        )
        slug_to_id[tenant["slug"]] = row["id"]
        logger.info("seeded tenant slug=%s id=%s", tenant["slug"], row["id"])
    return slug_to_id


async def seed_articles(
    conn: "asyncpg.Connection",
    slug_to_id: dict[str, uuid.UUID],
) -> None:
    """Insert seed articles per tenant. Idempotent on (tenant_id, title)."""
    await conn.execute("TRUNCATE articles RESTART IDENTITY")
    for slug, articles in SEED_ARTICLES.items():
        tenant_id = slug_to_id[slug]
        for article in articles:
            await conn.execute(
                """
                INSERT INTO articles (tenant_id, title, body, author)
                VALUES ($1, $2, $3, $4)
                """,
                tenant_id,
                article["title"],
                article["body"],
                article["author"],
            )
        logger.info("seeded %d articles for tenant %s", len(articles), slug)


# ---------------------------------------------------------------------------
# Part C — The leak: queries that ignore tenant_id
# ---------------------------------------------------------------------------


async def leak_all_articles(conn: "asyncpg.Connection") -> list[dict[str, Any]]:
    """The buggy query: no tenant_id filter.

    Returns every article in the table, across every tenant. This is the
    failure mode RLS prevents. Notice that the query reads perfectly fine
    as application code — there is nothing visually wrong with it.
    """
    rows = await conn.fetch(
        "SELECT id, tenant_id, title, author FROM articles ORDER BY tenant_id, id"
    )
    return [dict(r) for r in rows]


# TASK 1: write a SECOND buggy query that joins articles with tenants and
# returns "the article id, title, and tenant name". Without a tenant_id
# filter, the join still leaks across tenants. Run it; record the output
# in SOLUTIONS.md.


# ---------------------------------------------------------------------------
# Part D — The fix: filter by tenant_id explicitly
# ---------------------------------------------------------------------------


async def list_tenant_articles(
    conn: "asyncpg.Connection",
    tenant_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """The correct query: filter by tenant_id."""
    rows = await conn.fetch(
        "SELECT id, title, author FROM articles WHERE tenant_id = $1 ORDER BY id",
        tenant_id,
    )
    return [dict(r) for r in rows]


async def get_tenant_article_by_id(
    conn: "asyncpg.Connection",
    tenant_id: uuid.UUID,
    article_id: int,
) -> dict[str, Any] | None:
    """Single-article lookup with the tenant filter."""
    row = await conn.fetchrow(
        "SELECT id, title, author, body FROM articles WHERE tenant_id = $1 AND id = $2",
        tenant_id,
        article_id,
    )
    return dict(row) if row is not None else None


# TASK 2: rewrite `get_tenant_article_by_id` so it does NOT pass tenant_id
# as a parameter — instead, take only `article_id`. Document in
# SOLUTIONS.md what the right answer would be (hint: RLS, the next exercise).
# Today, without RLS, the answer is "you cannot — every query needs the
# tenant filter".


# ---------------------------------------------------------------------------
# Part E — Explain the plan
# ---------------------------------------------------------------------------


async def explain_query(conn: "asyncpg.Connection", tenant_id: uuid.UUID) -> str:
    """EXPLAIN ANALYZE the per-tenant published-articles query."""
    rows = await conn.fetch(
        """
        EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
        SELECT id, title, author
          FROM articles
         WHERE tenant_id = $1
         ORDER BY published_at DESC
         LIMIT 25
        """,
        tenant_id,
    )
    return "\n".join(r[0] for r in rows)


# TASK 3: read the EXPLAIN output. Confirm that the planner uses the
# articles_by_tenant_published index (composite on tenant_id, published_at
# DESC) — look for "Index Scan using articles_by_tenant_published".
# If you see "Seq Scan", the index is missing or the planner thinks the
# table is too small to bother.


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    if asyncpg is None:
        raise RuntimeError("asyncpg is not installed; pip install asyncpg")
    conn = await asyncpg.connect(DSN)
    try:
        logger.info("=== Part A and B: seeding ===")
        slug_to_id = await seed_tenants(conn)
        await seed_articles(conn, slug_to_id)

        logger.info("=== Part C: the leak ===")
        leaked = await leak_all_articles(conn)
        logger.info("leaked %d articles across all tenants:", len(leaked))
        for row in leaked:
            logger.info(
                "  id=%d tenant=%s title=%s",
                row["id"],
                row["tenant_id"],
                row["title"],
            )

        logger.info("=== Part D: the correct queries ===")
        for slug, tenant_id in slug_to_id.items():
            articles = await list_tenant_articles(conn, tenant_id)
            logger.info("tenant %s has %d articles:", slug, len(articles))
            for a in articles:
                logger.info("  id=%d title=%s", a["id"], a["title"])

        logger.info("=== Part E: EXPLAIN ===")
        acme_id = slug_to_id["acme"]
        plan = await explain_query(conn, acme_id)
        logger.info("plan for acme:\n%s", plan)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
