"""Exercise 02 — The literal cross-tenant assertion.

The W11 invariant says tenant A cannot read tenant B's rows even if the
application's SQL forgets the `WHERE tenant_id = ...` filter. This file
is the test that proves it. It is the load-bearing single test in the
capstone: if this test passes, the multi-tenancy is correct; if this
test ever fails, ship nothing until it passes again.

The exercise demonstrates four variants of the same assertion, each
covering a different leak path:

  1. Direct primary-key fetch with the wrong tenant context returns
     zero rows.
  2. A scan query (`SELECT * FROM articles`) with the wrong tenant
     context returns only the requesting tenant's rows.
  3. An INSERT with a mismatched `tenant_id` in the payload is
     rejected by the RLS WITH CHECK clause.
  4. A `UPDATE` against another tenant's row with the wrong context
     updates zero rows.

The real harness runs these against a live Postgres with `FORCE ROW
LEVEL SECURITY` enabled on every tenant-scoped table. This file uses
an in-memory simulator that enforces the same contract so the exercise
compiles and runs without a database.

References:

  - https://www.postgresql.org/docs/current/ddl-rowsecurity.html
  - https://www.postgresql.org/docs/current/sql-set.html
  - https://www.postgresql.org/docs/current/sql-createpolicy.html

Compile:

    python3 -m py_compile exercise-02-rls-cross-tenant-assertion.py

Run:

    python3 exercise-02-rls-cross-tenant-assertion.py
"""

from __future__ import annotations

import asyncio
import contextvars
import sys
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ----------------------------------------------------------------------
# Pydantic v2 schemas for the exercise.
# ----------------------------------------------------------------------


class TenantRow(BaseModel):
    """A row in the tenants table (outside the RLS regime)."""

    id: UUID
    slug: str = Field(..., min_length=2, max_length=32)
    name: str = Field(..., min_length=2, max_length=64)


class ArticleRow(BaseModel):
    """A row in the articles table (inside the RLS regime)."""

    tenant_id: UUID
    id: UUID
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=0, max_length=50_000)


# ----------------------------------------------------------------------
# The session-local tenant context (mirrors `SET LOCAL app.current_tenant`).
# ----------------------------------------------------------------------


_current_tenant: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "current_tenant", default=None
)


def set_tenant_context(tenant_id: UUID | None) -> contextvars.Token[UUID | None]:
    """Equivalent to `SET LOCAL app.current_tenant = '<uuid>'`."""
    return _current_tenant.set(tenant_id)


def reset_tenant_context(token: contextvars.Token[UUID | None]) -> None:
    """Equivalent to the transaction commit/rollback that ends SET LOCAL."""
    _current_tenant.reset(token)


def get_tenant_context() -> UUID:
    """Equivalent to `current_setting('app.current_tenant')::uuid`."""
    tenant_id = _current_tenant.get()
    if tenant_id is None:
        raise RuntimeError(
            "no tenant context set; RLS would either fail open (unsafe) "
            "or fail closed depending on policy. The capstone fails closed."
        )
    return tenant_id


# ----------------------------------------------------------------------
# The simulated RLS-enforced table.
# ----------------------------------------------------------------------


@dataclass
class RlsTable:
    """A minimal in-memory simulator of a Postgres table with FORCE RLS.

    The contract:

      - Reads (`fetch_one`, `fetch_all`) honour the current tenant context.
      - Writes (`insert`, `update`) honour both the USING and WITH CHECK
        predicates of the policy.
      - The policy: `tenant_id = current_setting('app.current_tenant')::uuid`.

    Real Postgres applies the policy in the query plan; the simulator
    applies it at the row-iteration level. The behavioural outcome — what
    the test sees — is identical.
    """

    rows: dict[tuple[UUID, UUID], dict[str, Any]] = field(default_factory=dict)

    def insert(self, row: ArticleRow) -> None:
        """Equivalent to `INSERT INTO articles (...) VALUES (...)`.

        Raises PermissionError if the row's `tenant_id` does not match the
        current tenant context — the WITH CHECK clause's job in real RLS.
        """
        current = get_tenant_context()
        if row.tenant_id != current:
            raise PermissionError(
                "RLS WITH CHECK violation: cannot INSERT a row with "
                f"tenant_id={row.tenant_id} while context={current}"
            )
        self.rows[(row.tenant_id, row.id)] = row.model_dump()

    def fetch_one(self, article_id: UUID) -> ArticleRow | None:
        """Equivalent to `SELECT * FROM articles WHERE id = $1`.

        Note the SQL is *not* tenant-filtered; the RLS policy filters it
        for us. The simulator does the same.
        """
        current = get_tenant_context()
        row = self.rows.get((current, article_id))
        if row is None:
            return None
        return ArticleRow.model_validate(row)

    def fetch_all(self) -> list[ArticleRow]:
        """Equivalent to `SELECT * FROM articles` (no WHERE clause).

        The RLS policy adds the filter. The application sees only the
        current tenant's rows.
        """
        current = get_tenant_context()
        out: list[ArticleRow] = []
        for (tenant_id, _id), row in self.rows.items():
            if tenant_id == current:
                out.append(ArticleRow.model_validate(row))
        return out

    def update_title(self, article_id: UUID, new_title: str) -> int:
        """Equivalent to `UPDATE articles SET title=$1 WHERE id=$2 RETURNING ...`.

        Returns the number of rows affected.
        """
        current = get_tenant_context()
        key = (current, article_id)
        if key not in self.rows:
            return 0
        self.rows[key]["title"] = new_title
        return 1

    def delete(self, article_id: UUID) -> int:
        """Equivalent to `DELETE FROM articles WHERE id = $1`."""
        current = get_tenant_context()
        key = (current, article_id)
        if key not in self.rows:
            return 0
        del self.rows[key]
        return 1


# ----------------------------------------------------------------------
# The fixture — two tenants, one article each, parked in the table.
# ----------------------------------------------------------------------


@dataclass
class Fixture:
    table: RlsTable
    tenant_a: TenantRow
    tenant_b: TenantRow
    article_a_id: UUID
    article_b_id: UUID


def make_fixture() -> Fixture:
    table = RlsTable()
    tenant_a = TenantRow(id=uuid4(), slug="acme", name="Acme Corp")
    tenant_b = TenantRow(id=uuid4(), slug="globex", name="Globex Industries")
    article_a_id = uuid4()
    article_b_id = uuid4()

    # Seed tenant A's article under A's context.
    token = set_tenant_context(tenant_a.id)
    try:
        table.insert(ArticleRow(
            tenant_id=tenant_a.id,
            id=article_a_id,
            title="Acme manifesto",
            body="Tenant A's confidential content.",
        ))
    finally:
        reset_tenant_context(token)

    # Seed tenant B's article under B's context.
    token = set_tenant_context(tenant_b.id)
    try:
        table.insert(ArticleRow(
            tenant_id=tenant_b.id,
            id=article_b_id,
            title="Globex manifesto",
            body="Tenant B's confidential content.",
        ))
    finally:
        reset_tenant_context(token)

    return Fixture(table=table, tenant_a=tenant_a, tenant_b=tenant_b,
                   article_a_id=article_a_id, article_b_id=article_b_id)


# ----------------------------------------------------------------------
# The four cross-tenant assertions.
# ----------------------------------------------------------------------


def assertion_1_primary_key_fetch_with_wrong_context_returns_none() -> None:
    """Tenant B's context cannot fetch tenant A's article by its ID."""
    fx = make_fixture()
    token = set_tenant_context(fx.tenant_b.id)
    try:
        row = fx.table.fetch_one(fx.article_a_id)
    finally:
        reset_tenant_context(token)
    assert row is None, (
        f"LEAK: tenant B fetched tenant A's article {fx.article_a_id!s}. "
        "Either RLS is not enabled, FORCE is missing, or the policy is wrong."
    )


def assertion_2_scan_query_returns_only_own_rows() -> None:
    """An unfiltered scan returns only the requesting tenant's rows."""
    fx = make_fixture()
    token = set_tenant_context(fx.tenant_a.id)
    try:
        rows = fx.table.fetch_all()
    finally:
        reset_tenant_context(token)
    assert len(rows) == 1
    assert rows[0].tenant_id == fx.tenant_a.id
    assert rows[0].id == fx.article_a_id


def assertion_3_insert_with_mismatched_tenant_id_is_rejected() -> None:
    """The RLS WITH CHECK clause blocks an INSERT with a foreign tenant_id."""
    fx = make_fixture()
    token = set_tenant_context(fx.tenant_a.id)
    try:
        try:
            # Tenant A's context tries to insert a row claiming to be tenant B's.
            fx.table.insert(ArticleRow(
                tenant_id=fx.tenant_b.id,
                id=uuid4(),
                title="forged",
                body="forged body",
            ))
        except PermissionError as exc:
            assert "WITH CHECK violation" in str(exc)
            return
    finally:
        reset_tenant_context(token)
    raise AssertionError("expected PermissionError for cross-tenant INSERT")


def assertion_4_update_with_wrong_context_affects_zero_rows() -> None:
    """An UPDATE against another tenant's row affects zero rows."""
    fx = make_fixture()
    token = set_tenant_context(fx.tenant_b.id)
    try:
        affected = fx.table.update_title(fx.article_a_id, "BOGUS")
    finally:
        reset_tenant_context(token)
    assert affected == 0, (
        f"LEAK: tenant B updated tenant A's article (affected={affected}). "
        "RLS is not protecting UPDATEs."
    )
    # Verify A's row is unchanged.
    token = set_tenant_context(fx.tenant_a.id)
    try:
        row = fx.table.fetch_one(fx.article_a_id)
    finally:
        reset_tenant_context(token)
    assert row is not None and row.title == "Acme manifesto"


def assertion_5_delete_with_wrong_context_affects_zero_rows() -> None:
    """A DELETE against another tenant's row affects zero rows."""
    fx = make_fixture()
    token = set_tenant_context(fx.tenant_b.id)
    try:
        affected = fx.table.delete(fx.article_a_id)
    finally:
        reset_tenant_context(token)
    assert affected == 0


def assertion_6_missing_context_raises() -> None:
    """Querying without a tenant context fails closed."""
    fx = make_fixture()
    try:
        fx.table.fetch_all()
    except RuntimeError as exc:
        assert "no tenant context" in str(exc)
        return
    raise AssertionError("expected RuntimeError when context is unset")


def assertion_7_insert_under_each_context_succeeds_under_its_own() -> None:
    """Each tenant CAN write to its own bucket (sanity test)."""
    fx = make_fixture()
    # A inserts under A's context.
    token = set_tenant_context(fx.tenant_a.id)
    try:
        fx.table.insert(ArticleRow(
            tenant_id=fx.tenant_a.id,
            id=uuid4(),
            title="another A article",
            body="body",
        ))
    finally:
        reset_tenant_context(token)

    # B inserts under B's context.
    token = set_tenant_context(fx.tenant_b.id)
    try:
        fx.table.insert(ArticleRow(
            tenant_id=fx.tenant_b.id,
            id=uuid4(),
            title="another B article",
            body="body",
        ))
    finally:
        reset_tenant_context(token)


# ----------------------------------------------------------------------
# Async test wrapper to demonstrate the assertion pattern inside a FastAPI
# test using httpx.AsyncClient. The body is the same; the wrapper shape is
# what the real capstone test file looks like.
# ----------------------------------------------------------------------


async def async_test_cross_tenant_via_httpx_skeleton() -> None:
    """Skeleton: real version uses httpx.AsyncClient against the FastAPI app.

    The skeleton documents the shape:

        async with httpx.AsyncClient(app=fastapi_app, base_url="...") as client:
            tenant_a = (await client.post("/admin/signup", json={...})).json()
            tenant_b = (await client.post("/admin/signup", json={...})).json()
            article_a = (await client.post(
                "/api/articles",
                json={"title": "A", "body": "body"},
                headers={"Authorization": f"Bearer {tenant_a['api_token']}"},
            )).json()
            wrong_fetch = await client.get(
                f"/api/articles/{article_a['id']}",
                headers={"Authorization": f"Bearer {tenant_b['api_token']}"},
            )
            assert wrong_fetch.status_code == 404

    See the mini-project starter for the working version.
    """
    # Run a synchronous assertion to keep the demo end-to-end.
    assertion_1_primary_key_fetch_with_wrong_context_returns_none()


def main(argv: list[str]) -> int:
    print(f"Running {sys.argv[0]} — the W12 cross-tenant assertion suite")
    suite = [
        assertion_1_primary_key_fetch_with_wrong_context_returns_none,
        assertion_2_scan_query_returns_only_own_rows,
        assertion_3_insert_with_mismatched_tenant_id_is_rejected,
        assertion_4_update_with_wrong_context_affects_zero_rows,
        assertion_5_delete_with_wrong_context_affects_zero_rows,
        assertion_6_missing_context_raises,
        assertion_7_insert_under_each_context_succeeds_under_its_own,
    ]
    failures = 0
    for fn in suite:
        try:
            fn()
        except AssertionError as exc:
            print(f"FAIL: {fn.__name__}: {exc}")
            failures += 1
        except Exception as exc:  # pragma: no cover
            print(f"ERROR: {fn.__name__}: {type(exc).__name__}: {exc}")
            failures += 1
        else:
            print(f"OK:   {fn.__name__}")

    try:
        asyncio.run(async_test_cross_tenant_via_httpx_skeleton())
    except AssertionError as exc:
        print(f"FAIL: async_test_cross_tenant_via_httpx_skeleton: {exc}")
        failures += 1
    else:
        print("OK:   async_test_cross_tenant_via_httpx_skeleton")

    if failures:
        print(f"\n{failures} assertion(s) failed.")
        return 1
    print("\nAll cross-tenant assertions passed.")
    print("In production, run the same suite against a live Postgres with")
    print("FORCE ROW LEVEL SECURITY enabled. The assertions are identical;")
    print("only the simulator becomes asyncpg.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
