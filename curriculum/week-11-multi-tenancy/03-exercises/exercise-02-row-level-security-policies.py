"""
Exercise 2 — Row-level security: policies, FORCE, the bypass cases.

Time:   ~1.5 hours.
Goal:   Apply RLS to the articles table. Demonstrate three behaviours:

        (1) With RLS enabled and a policy, but WITHOUT `FORCE ROW LEVEL
            SECURITY`, the table owner sees every row regardless of policy.
            (The gotcha that has shipped to production at every shop
            with a multi-tenant Postgres deployment at least once.)

        (2) With FORCE applied, the owner is constrained by the policy
            like any other role. The leak closes.

        (3) The application role (non-superuser, non-BYPASSRLS) is
            isolated by tenant. Setting `app.current_tenant` via
            `SET LOCAL` switches which rows are visible. Forgetting to
            set it produces an empty result set — fail-closed.

Run:
    python3 exercise-02-row-level-security-policies.py

Prerequisites:
    - Exercise 1 has run (tables and seed data exist).
    - The application role `crunchreader_app` exists (from the README's
      "before Monday" checks).

Cited:
    - https://www.postgresql.org/docs/current/ddl-rowsecurity.html
    - https://www.postgresql.org/docs/current/sql-createpolicy.html
    - https://www.postgresql.org/docs/current/sql-altertable.html
    - https://www.postgresql.org/docs/current/sql-set.html

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


logger = logging.getLogger("rls_exercise")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


OWNER_DSN = os.environ.get(
    "CC_W11_DSN",
    "postgresql://postgres:postgres@localhost:5432/cc_w11",
)
APP_DSN = os.environ.get(
    "CC_W11_APP_DSN",
    "postgresql://crunchreader_app:Crunch_Pro_W11_pw@localhost:5432/cc_w11",
)


# ---------------------------------------------------------------------------
# Part A — Apply the RLS policy (idempotent)
# ---------------------------------------------------------------------------


async def apply_policy(conn: "asyncpg.Connection") -> None:
    """Enable RLS on articles and define the tenant-isolation policy.

    Note: we do NOT apply FORCE yet — that comes in Part C. The whole
    point is to see the owner-bypass failure mode first.
    """
    await conn.execute("ALTER TABLE articles ENABLE ROW LEVEL SECURITY")
    # Drop any existing policy so this is re-runnable.
    await conn.execute("DROP POLICY IF EXISTS tenant_isolation ON articles")
    await conn.execute(
        """
        CREATE POLICY tenant_isolation ON articles
            USING (tenant_id = current_setting('app.current_tenant')::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)
        """
    )
    logger.info("RLS enabled and policy `tenant_isolation` created")


async def grant_application_access(conn: "asyncpg.Connection") -> None:
    """Grant the minimum DML to crunchreader_app. Owner only."""
    await conn.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON articles TO crunchreader_app")
    await conn.execute("GRANT SELECT ON tenants TO crunchreader_app")
    await conn.execute(
        "GRANT USAGE ON SEQUENCE articles_id_seq TO crunchreader_app"
    )
    logger.info("granted DML to crunchreader_app")


# ---------------------------------------------------------------------------
# Part B — Demonstrate the table-owner bypass (without FORCE)
# ---------------------------------------------------------------------------


async def owner_sees_everything(conn: "asyncpg.Connection", tenant_id: uuid.UUID) -> int:
    """Read articles as the OWNER. Without FORCE, the owner bypasses the policy.

    This function intentionally sets `app.current_tenant` to one tenant
    and counts articles. With FORCE off, the count is "all articles
    in the table" — every tenant's. With FORCE on, the count is "this
    tenant's" only.
    """
    async with conn.transaction():
        await conn.execute("SET LOCAL app.current_tenant = $1", str(tenant_id))
        row = await conn.fetchrow("SELECT count(*) AS c FROM articles")
        return int(row["c"])


# TASK 1: run owner_sees_everything as `postgres` (the owner) twice with
# two different tenant IDs. Without FORCE, both calls return the same
# number (the total article count). With FORCE on, the calls return
# different numbers (per-tenant counts). Record both in SOLUTIONS.md.


# ---------------------------------------------------------------------------
# Part C — Apply FORCE
# ---------------------------------------------------------------------------


async def force_policy(conn: "asyncpg.Connection") -> None:
    """Apply FORCE ROW LEVEL SECURITY. After this, the owner cannot bypass."""
    await conn.execute("ALTER TABLE articles FORCE ROW LEVEL SECURITY")
    logger.info("FORCE ROW LEVEL SECURITY applied to articles")


async def verify_rls_state(conn: "asyncpg.Connection") -> dict[str, bool]:
    """Read pg_class to confirm the RLS state."""
    row = await conn.fetchrow(
        """
        SELECT relrowsecurity, relforcerowsecurity
          FROM pg_class
         WHERE relname = 'articles'
        """
    )
    state = {
        "rls_enabled": bool(row["relrowsecurity"]),
        "rls_forced": bool(row["relforcerowsecurity"]),
    }
    logger.info("RLS state: %s", state)
    return state


# ---------------------------------------------------------------------------
# Part D — The application role: per-tenant isolation
# ---------------------------------------------------------------------------


async def application_query(
    app_conn: "asyncpg.Connection",
    tenant_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Read articles as the APPLICATION role, with SET LOCAL.

    The pattern: open a transaction, set app.current_tenant, run the query,
    let the transaction commit. The policy filters automatically; the SQL
    in the application code has no `WHERE tenant_id = ...` clause.
    """
    async with app_conn.transaction():
        await app_conn.execute(
            "SET LOCAL app.current_tenant = $1", str(tenant_id)
        )
        rows = await app_conn.fetch(
            "SELECT id, title, author FROM articles ORDER BY id"
        )
        return [dict(r) for r in rows]


async def application_query_no_context(
    app_conn: "asyncpg.Connection",
) -> list[dict[str, Any]] | str:
    """Read articles WITHOUT setting app.current_tenant. Expect an error.

    `current_setting('app.current_tenant')` raises when undefined; the
    cast to uuid in the policy raises too. The right behaviour: the
    request fails closed, not "returns all rows".
    """
    try:
        async with app_conn.transaction():
            rows = await app_conn.fetch("SELECT id, title FROM articles")
            return [dict(r) for r in rows]
    except asyncpg.exceptions.PostgresError as exc:
        return f"failed-closed: {exc.__class__.__name__}: {exc}"


# TASK 2: explain in SOLUTIONS.md why "failing closed" (raising an error)
# is the right behaviour for unset tenant context, versus "returning
# zero rows silently". Hint: silent zero rows can be mistaken for "the
# tenant has no data"; an error is impossible to mistake.


# ---------------------------------------------------------------------------
# Part E — Demonstrate the cross-tenant write rejection
# ---------------------------------------------------------------------------


async def attempt_cross_tenant_insert(
    app_conn: "asyncpg.Connection",
    current_tenant: uuid.UUID,
    foreign_tenant: uuid.UUID,
) -> str:
    """Try to INSERT a row with a different tenant_id than current setting.

    The WITH CHECK clause rejects the INSERT: the new row's tenant_id
    does not match `current_setting('app.current_tenant')`, so the
    policy fails-closed on the WITH CHECK predicate. Returns the error.
    """
    try:
        async with app_conn.transaction():
            await app_conn.execute(
                "SET LOCAL app.current_tenant = $1", str(current_tenant)
            )
            await app_conn.execute(
                """
                INSERT INTO articles (tenant_id, title, body, author)
                VALUES ($1, $2, $3, $4)
                """,
                foreign_tenant,
                "cross-tenant write attempt",
                "this should be rejected",
                "attacker",
            )
        return "INSERT succeeded — RLS is broken"
    except asyncpg.exceptions.PostgresError as exc:
        return f"rejected: {exc.__class__.__name__}: {exc}"


# TASK 3: run attempt_cross_tenant_insert. Confirm the error is a
# "new row violates row-level security policy" error. Record the
# message in SOLUTIONS.md.


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    if asyncpg is None:
        raise RuntimeError("asyncpg is not installed; pip install asyncpg")

    owner = await asyncpg.connect(OWNER_DSN)
    try:
        # Apply policy. Grant access. Look up tenant IDs.
        await apply_policy(owner)
        await grant_application_access(owner)
        rows = await owner.fetch("SELECT id, slug FROM tenants ORDER BY slug")
        slug_to_id = {r["slug"]: r["id"] for r in rows}
        acme = slug_to_id["acme"]
        globex = slug_to_id["globex"]

        # Part B: without FORCE, the owner bypasses the policy.
        logger.info("=== Part B: without FORCE, owner bypasses ===")
        await verify_rls_state(owner)
        count_acme = await owner_sees_everything(owner, acme)
        count_globex = await owner_sees_everything(owner, globex)
        logger.info(
            "owner sees %d articles for acme, %d for globex (these should match — leak)",
            count_acme,
            count_globex,
        )

        # Part C: apply FORCE.
        logger.info("=== Part C: FORCE ROW LEVEL SECURITY ===")
        await force_policy(owner)
        await verify_rls_state(owner)
        count_acme = await owner_sees_everything(owner, acme)
        count_globex = await owner_sees_everything(owner, globex)
        logger.info(
            "owner now sees %d articles for acme, %d for globex (should differ now)",
            count_acme,
            count_globex,
        )

    finally:
        await owner.close()

    # Part D: connect as the application role; demonstrate per-tenant isolation.
    app = await asyncpg.connect(APP_DSN)
    try:
        logger.info("=== Part D: application role with per-tenant SET LOCAL ===")
        acme_articles = await application_query(app, acme)
        globex_articles = await application_query(app, globex)
        logger.info(
            "as app: acme sees %d articles, globex sees %d",
            len(acme_articles),
            len(globex_articles),
        )

        logger.info("=== Part D bis: no context set — should fail-closed ===")
        result = await application_query_no_context(app)
        logger.info("no-context result: %s", result)

        logger.info("=== Part E: cross-tenant INSERT should be rejected ===")
        outcome = await attempt_cross_tenant_insert(app, acme, globex)
        logger.info("outcome: %s", outcome)

    finally:
        await app.close()


if __name__ == "__main__":
    asyncio.run(main())
