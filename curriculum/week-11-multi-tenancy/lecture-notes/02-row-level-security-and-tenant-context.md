# Lecture 2 — Row-level security and tenant-context propagation

> *Pool's strength is also pool's weakness. One database for everyone means one missed `WHERE tenant_id` clause leaks data across tenants. The application-level fix — "we will be careful and review every query" — does not survive a team of five engineers and a deadline. Postgres has had a database-level fix since version 9.5: row-level security. A policy on the `articles` table says "rows are visible iff `tenant_id = current_setting('app.current_tenant')::uuid`"; every query, every join, every aggregation gets the predicate appended automatically. The application sets the tenant ID at the start of each request and forgets about it. The policy is the safety net. Except — and this is the lecture — the policy has gotchas. Table owners bypass it without `FORCE`. Superusers bypass it always. `SET` without `LOCAL` leaks across pooled connections. The Postgres documentation calls these "considerations"; the postmortem calls them "the bug we shipped to production".*

## 1 — The mechanism: what RLS actually does

Row-level security in Postgres is **automatic query rewriting**. When you write:

```sql
SELECT * FROM articles WHERE id = 42;
```

against a table with an RLS policy `tenant_isolation USING (tenant_id = current_setting('app.current_tenant')::uuid)`, the Postgres rewriter (the `src/backend/rewrite/rowsecurity.c` module) transforms it into:

```sql
SELECT * FROM articles WHERE id = 42 AND tenant_id = current_setting('app.current_tenant')::uuid;
```

before the planner sees it. The transformation is invisible to the application code; the application thinks it asked for "the article with id 42", and Postgres delivers "the article with id 42, *that the current tenant has access to*". If no such article exists for this tenant, the query returns zero rows — exactly as if the article did not exist.

This is the central design property. The application is no longer the boundary; the database is. An engineer who forgets to filter by `tenant_id` does not produce a data leak; they produce a query that Postgres silently filters for them.

The Postgres documentation for RLS is at <https://www.postgresql.org/docs/current/ddl-rowsecurity.html>. Read sections 5.9.1 through 5.9.4 before continuing.

## 2 — Enabling and creating policies

Three statements:

```sql
-- 1. Turn on RLS for the table.
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;

-- 2. Create the policy.
CREATE POLICY tenant_isolation ON articles
    USING (tenant_id = current_setting('app.current_tenant')::uuid);

-- 3. (CRITICAL — see §4) FORCE the policy on the table owner too.
ALTER TABLE articles FORCE ROW LEVEL SECURITY;
```

Take each in turn.

### 2.1 — `ENABLE ROW LEVEL SECURITY`

This statement turns RLS on for the table. Without it, the table has no policies and any policy you `CREATE POLICY` against it is dormant. `ENABLE ROW LEVEL SECURITY` activates the mechanism.

There is a subtlety. With RLS *enabled* but no policies defined, the default is **deny everything** — a user without `BYPASSRLS` who reads the table sees zero rows. This is the "fail closed" default. If you `ENABLE ROW LEVEL SECURITY` and forget to add a policy, your application will report empty result sets, not data leaks. The Postgres team chose the safe default.

### 2.2 — `CREATE POLICY`

The full grammar of `CREATE POLICY` is at <https://www.postgresql.org/docs/current/sql-createpolicy.html>. The minimum form is:

```sql
CREATE POLICY policy_name ON table_name
    USING (boolean_expression);
```

Five details that matter.

First: **the `USING` clause is the visibility predicate**. It returns `true` for rows that should be visible to the current connection, `false` for rows that should be hidden. The expression can reference any column of the table, any function, any session-level setting via `current_setting()`.

Second: **`USING` applies to `SELECT`, `UPDATE`, and `DELETE`**. For `INSERT`, `USING` does not apply (there is no existing row to check); the `WITH CHECK` clause does. For `UPDATE`, both apply: `USING` filters which rows can be targeted; `WITH CHECK` validates the result of the update. If you omit `WITH CHECK`, Postgres uses the `USING` expression for both — which is the right default for tenant isolation (a row that satisfies `USING` is also a row that should satisfy `WITH CHECK` after update).

Third: **the policy can be per-command**. `CREATE POLICY ... FOR SELECT USING (...)` applies only to `SELECT`. `CREATE POLICY ... FOR INSERT WITH CHECK (...)` applies only to `INSERT`. `FOR ALL` (the default) applies to all four DML commands. Use `FOR ALL` for the tenant-isolation policy; the visibility predicate is identical across commands.

Fourth: **`PERMISSIVE` versus `RESTRICTIVE`**. By default, policies are `PERMISSIVE` — multiple policies are ORed together (any policy that passes makes the row visible). `RESTRICTIVE` policies are ANDed with the permissive ones (all restrictive policies must pass; at least one permissive must pass). For tenant isolation, the policy is `PERMISSIVE` and there is one policy per table. `RESTRICTIVE` is useful when you have a primary "tenant isolation" policy and want to layer an additional "admin override" policy without weakening the primary.

Fifth: **`TO role`** restricts the policy to a specific role. Without `TO`, the policy applies to all roles (except superusers and `BYPASSRLS` roles, which never have policies applied). For the simple multi-tenant case, omit `TO` and let the policy apply to every non-superuser role.

### 2.3 — `FORCE ROW LEVEL SECURITY`

This is **the** load-bearing line in the policy setup. Without it, the table owner — typically the database user that ran the `CREATE TABLE` statement, which in many setups is the same user the application connects as — bypasses all RLS policies on that table.

Read that again. By default, the table owner sees every row regardless of policy. The Postgres rationale is "the owner is presumed to be administrator-equivalent for this table"; the multi-tenant rationale is "this is the worst possible default, please add `FORCE`".

`ALTER TABLE articles FORCE ROW LEVEL SECURITY;` removes the owner bypass. After this statement, even the owner gets the policy applied. This is the configuration you want for a multi-tenant application.

How do you tell if your table has `FORCE`? Query `pg_class`:

```sql
SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relname = 'articles';
```

`relrowsecurity` is `true` if `ENABLE ROW LEVEL SECURITY` ran. `relforcerowsecurity` is `true` if `FORCE` ran. You want both `true`. The exercises will demonstrate the failure mode in painful detail; for now, internalise: **`ENABLE` without `FORCE` is a security bug**.

## 3 — Passing tenant context: `SET LOCAL` and `current_setting`

The policy `USING (tenant_id = current_setting('app.current_tenant')::uuid)` references a *runtime parameter* called `app.current_tenant`. Postgres lets applications define custom parameters with dotted names (anything not starting with `pg_*` is reserved for applications). The application sets the parameter at the start of each transaction; the policy reads it on every row.

### 3.1 — `SET LOCAL` versus `SET` versus `SET SESSION`

Three statements, three different lifetimes:

- **`SET app.current_tenant = '...'`** (no `LOCAL`, no `SESSION`) — same as `SET SESSION`. Persists for the *entire connection*, until the connection closes or another `SET` overrides it.
- **`SET SESSION app.current_tenant = '...'`** — explicit form of the above. Persists for the connection.
- **`SET LOCAL app.current_tenant = '...'`** — persists only for the current *transaction*. When the transaction commits or rolls back, the setting is gone.

For multi-tenancy under connection pooling, **`SET LOCAL` is the only correct choice**. Consider the failure mode without it:

1. Request A from tenant `acme` acquires connection 7 from the pool.
2. The application runs `SET app.current_tenant = 'acme-uuid'` (without `LOCAL`).
3. Request A's queries run; the policy filters for `acme`'s rows correctly.
4. Request A completes; connection 7 returns to the pool.
5. Request B from tenant `globex` acquires connection 7 from the pool.
6. The application *forgets to set* `app.current_tenant` (or sets it after the first query, or the framework batches the `SET` into a transaction that runs after the first `SELECT`).
7. Request B's first query runs with `app.current_tenant` still set to `acme-uuid`. The policy filters for `acme`'s rows, and tenant `globex` sees tenant `acme`'s data.

`SET LOCAL` makes this impossible. The setting dies when the transaction ends; the next transaction starts with an unset parameter, and `current_setting('app.current_tenant', true)` returns an empty string. The policy `USING (tenant_id = ''::uuid)` errors out (an empty string is not a valid UUID), and the request fails closed — which is correct.

The Postgres `SET` documentation is at <https://www.postgresql.org/docs/current/sql-set.html>. The single sentence to remember: *`SET LOCAL` is scoped to the current transaction; the others are scoped to the session*.

### 3.2 — The `current_setting(name, missing_ok)` form

The two-argument form of `current_setting` is forgiving. `current_setting('app.current_tenant', true)` returns `''` (empty string) if the setting is not defined, instead of raising an error. The one-argument form `current_setting('app.current_tenant')` raises an error if undefined.

For the policy, use the one-argument form. You *want* an error when tenant context is not set — silently returning all rows would be worse. For helper queries that need to be tolerant of unset state (e.g. a health check), use the two-argument form.

### 3.3 — The FastAPI dependency pattern

In a FastAPI service, the pattern is a dependency that wraps every tenant-scoped database call:

```python
from typing import AsyncIterator
import uuid

import asyncpg
from fastapi import Depends, Header, HTTPException

async def get_tenant_id(x_tenant_id: str = Header(...)) -> uuid.UUID:
    """Resolve the tenant ID from the X-Tenant-ID header.

    In production, this would parse a JWT claim or a subdomain. The header
    form is the simplest demo.
    """
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid tenant id") from exc


async def get_db(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
) -> AsyncIterator[asyncpg.Connection]:
    """Acquire a connection and set tenant context for the request.

    The connection is released back to the pool when the request ends.
    """
    async with app.state.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SET LOCAL app.current_tenant = $1", str(tenant_id)
            )
            yield conn
```

Three pieces.

First: `get_tenant_id` resolves the tenant from the request. We use a header here; in production, you would use a JWT claim or a subdomain. The resolver returns a `uuid.UUID` Pydantic v2 happily validates.

Second: `get_db` acquires a connection from the pool, opens a transaction (because `SET LOCAL` requires a transaction context), sets the tenant parameter, and yields the connection. FastAPI's `Depends(...)` mechanism will run the post-yield code (closing the transaction, releasing the connection) when the request handler returns.

Third: every handler that touches the database depends on `get_db`:

```python
@router.get("/articles/{article_id}")
async def read_article(
    article_id: int,
    db: asyncpg.Connection = Depends(get_db),
) -> Article:
    row = await db.fetchrow("SELECT * FROM articles WHERE id = $1", article_id)
    if row is None:
        raise HTTPException(status_code=404)
    return Article(**dict(row))
```

The handler does not filter by `tenant_id`. The RLS policy filters for it. The query `SELECT * FROM articles WHERE id = $1` is rewritten to `SELECT * FROM articles WHERE id = $1 AND tenant_id = current_setting('app.current_tenant')::uuid`. If the article exists but belongs to a different tenant, the query returns no rows and the handler returns 404 — which is the right behaviour (a 404 leaks less information than a 403).

## 4 — The four RLS gotchas

Four ways RLS fails to isolate when you thought it did. Memorise them; the exercises will demonstrate them; production will eventually test you on them.

### 4.1 — Gotcha 1: the superuser bypass

A role with `SUPERUSER` (or `BYPASSRLS`) ignores every RLS policy. No exceptions. No "but the policy was tested in development" — `SUPERUSER` bypasses RLS in development too; the test passed because the test user was implicitly the table owner without `FORCE`, not because the policy worked.

The implication: **the application must not connect as a superuser**. Create a dedicated application role:

```sql
CREATE ROLE crunchreader_app WITH LOGIN PASSWORD 'Crunch_Pro_W11_pw';
-- NOT SUPERUSER, NOT BYPASSRLS.

GRANT CONNECT ON DATABASE crunchreader TO crunchreader_app;
GRANT USAGE ON SCHEMA public TO crunchreader_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO crunchreader_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO crunchreader_app;
```

Verify with:

```sql
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'crunchreader_app';
-- rolsuper | f, rolbypassrls | f
```

Both must be `false`. If `rolbypassrls` is `true`, the policy is theatre — your application bypasses every policy on every table without an error or a warning.

The "before Monday" check in the README has this verification at step 5. It is the most important of the eight checks.

### 4.2 — Gotcha 2: the table-owner bypass without `FORCE`

Covered in §2.3. Without `ALTER TABLE ... FORCE ROW LEVEL SECURITY`, the table owner ignores the policy. If the application connects as the owner — common, because `CREATE TABLE` typically runs from the application's deployment user — the policy is dormant.

The verification:

```sql
SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relname IN ('articles', 'authors', 'tags');
-- Both columns must be `t`.
```

Some shops standardise on having a *separate* role create the tables (a `migrator` role with no `LOGIN`) and the application connect as a different role with no ownership rights. This dodges the issue: the application is never the owner. The trade-off is that the migration runner has to be a separate process with separate credentials. Both approaches work; pick one and apply it consistently.

### 4.3 — Gotcha 3: `SECURITY DEFINER` functions

A function declared `SECURITY DEFINER` runs with the *privileges of its owner*, not the caller. If the owner is a superuser or has `BYPASSRLS`, calls through the function bypass RLS — even when the calling session would not.

This is occasionally the right tool: a helper function that reads cross-tenant aggregate statistics (`SELECT count(*) FROM articles GROUP BY tenant_id`) deliberately needs to bypass policies. Declare it `SECURITY DEFINER`, own it as a `BYPASSRLS` role, and accept the implications. The Postgres documentation has a warning at <https://www.postgresql.org/docs/current/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY>: "Because a `SECURITY DEFINER` function is executed with the privileges of the user that owns it, care is needed to ensure that the function cannot be misused."

The "care" includes:

- **Set `search_path` explicitly** at the start of the function (otherwise an attacker who can change the caller's `search_path` can substitute their own table).
- **Validate every input** — a `SECURITY DEFINER` function with SQL injection is a tenant-isolation bypass.
- **Limit the function's interface** — return only the rows the function intends to expose, never `SELECT *`.

Use `SECURITY DEFINER` sparingly. Each one is a hole in the RLS fence; each hole needs to be justified.

### 4.4 — Gotcha 4: policies on joined queries can produce surprising plans

An RLS policy adds a `WHERE` clause to every query against the table. For a single-table query, this is fast — the planner pushes the predicate to the index scan and the cost is negligible. For a multi-table join, the predicate appears on each table independently; the planner has to satisfy the policy on every table involved in the join.

A 10-table join with policies on each is 10 additional `WHERE` clauses. The planner usually handles this gracefully (a `tenant_id = X` predicate is highly selective; the indexes do the work). Occasionally — particularly on subqueries and lateral joins — the policy produces a plan that materialises a per-tenant subset before joining, where without the policy the planner would have joined first and filtered afterwards. The result is correct; the cost is sometimes higher than the non-RLS equivalent.

The mitigation:

- **Run `EXPLAIN ANALYZE` on every tenant-scoped multi-table query before shipping it.** Look for surprisingly large `rows estimated` numbers or `Materialize` nodes that did not exist without RLS.
- **Add per-tenant indexes** that match the policy predicate. `CREATE INDEX articles_tenant_id_idx ON articles (tenant_id)` (or, better, `CREATE INDEX articles_tenant_published_at ON articles (tenant_id, published_at DESC)` for the common ordering case). With the index, the policy predicate becomes a clean `Index Scan` instead of a `Filter`.
- **For aggregate queries that span tenants** (admin reports, billing rollups), use `SECURITY DEFINER` functions owned by a `BYPASSRLS` role. The policy is intentionally bypassed; the function's interface defines what data the caller can see.

## 5 — Worked example: a tenant-isolated `articles` table

The exercises will build this from scratch; here is the end-state for reference.

```sql
-- The shared admin table; not tenant-scoped.
CREATE TABLE tenants (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        text NOT NULL UNIQUE,
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- The tenant-scoped articles table.
CREATE TABLE articles (
    id           bigserial,
    tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title        text NOT NULL,
    body         text NOT NULL,
    author       text NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);

CREATE INDEX articles_by_tenant_published
    ON articles (tenant_id, published_at DESC);

-- Enable RLS.
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;

-- The visibility policy.
CREATE POLICY tenant_isolation ON articles
    USING (tenant_id = current_setting('app.current_tenant')::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid);

-- Force RLS on the table owner.
ALTER TABLE articles FORCE ROW LEVEL SECURITY;

-- Create the application role.
CREATE ROLE crunchreader_app WITH LOGIN PASSWORD 'Crunch_Pro_W11_pw';
GRANT CONNECT ON DATABASE crunchreader TO crunchreader_app;
GRANT USAGE ON SCHEMA public TO crunchreader_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON articles, tenants TO crunchreader_app;
GRANT USAGE ON SEQUENCE articles_id_seq TO crunchreader_app;
```

Five things to internalise from this listing:

1. **`tenants` is not RLS-policy-protected**. The admin table that *lists* tenants is shared; you want it readable to look up tenants by slug, count them, etc. Tenant-scoped tables get policies; the registry does not.
2. **The policy has `WITH CHECK`** that mirrors `USING`. Without it, an `UPDATE` that changes the `tenant_id` column could move a row from one tenant to another. With it, the new row's `tenant_id` must also match the current setting — so cross-tenant updates fail closed.
3. **`FORCE` is on a separate line**, after the policy. This is the convention: enable RLS, define the policy, force on the owner. Three statements in that order.
4. **The application role is created last** and granted only the minimum it needs. No `CREATE` privileges, no `DROP`, no `ALTER`. Just DML on the application tables.
5. **`articles_id_seq` is granted explicitly**. `GRANT INSERT ON articles` does not include the sequence used by `bigserial`. Without `GRANT USAGE ON SEQUENCE`, `INSERT` fails with a permission error.

## 6 — The application-side connection pattern

Putting the dependency from §3.3 together with the schema from §5 gives the end-to-end pattern. Here is the full handler, ready to ship:

```python
from typing import AsyncIterator
import uuid

import asyncpg
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

app = FastAPI()


class Article(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    body: str
    author: str
    published_at: str


@app.on_event("startup")
async def startup() -> None:
    app.state.pool = await asyncpg.create_pool(
        dsn="postgresql://crunchreader_app:Crunch_Pro_W11_pw@localhost/crunchreader",
        min_size=2,
        max_size=10,
    )


async def get_tenant_id(x_tenant_id: str = Header(...)) -> uuid.UUID:
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid tenant id") from exc


async def get_db(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
) -> AsyncIterator[asyncpg.Connection]:
    async with app.state.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL app.current_tenant = $1", str(tenant_id))
            yield conn


@app.get("/articles/{article_id}", response_model=Article)
async def read_article(
    article_id: int,
    db: asyncpg.Connection = Depends(get_db),
) -> Article:
    row = await db.fetchrow(
        "SELECT id, title, body, author, published_at::text FROM articles WHERE id = $1",
        article_id,
    )
    if row is None:
        raise HTTPException(status_code=404)
    return Article(**dict(row))
```

Notice: the handler reads "the article with id N". It does not mention `tenant_id`. The policy supplies the filter. The handler is correct without the engineer thinking about tenants; the database refuses to return rows that do not match the current tenant.

Send a request with `X-Tenant-ID: <acme-uuid>` and you get acme's article 42 or a 404. Send a request with `X-Tenant-ID: <globex-uuid>` and you get globex's article 42 or a 404 — *even if acme has an article 42* and globex does not. The IDs are tenant-scoped because the policy makes them so.

## 7 — Testing RLS: the leak-hunt test

Every multi-tenant service should ship with a test that proves the isolation. The shape:

```python
import asyncio
import uuid

import asyncpg
import pytest


@pytest.mark.asyncio
async def test_rls_isolates_tenants() -> None:
    pool = await asyncpg.create_pool(
        dsn="postgresql://crunchreader_app:Crunch_Pro_W11_pw@localhost/crunchreader",
    )
    acme = uuid.UUID(int=1)
    globex = uuid.UUID(int=2)

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL app.current_tenant = $1", str(acme))
            await conn.execute(
                "INSERT INTO articles (tenant_id, title, body, author) "
                "VALUES ($1, 'acme-secret', 'top secret', 'alice')",
                acme,
            )

        async with conn.transaction():
            await conn.execute("SET LOCAL app.current_tenant = $1", str(globex))
            rows = await conn.fetch("SELECT * FROM articles WHERE title = 'acme-secret'")
            assert rows == []  # globex cannot see acme's article.

        async with conn.transaction():
            await conn.execute("SET LOCAL app.current_tenant = $1", str(acme))
            rows = await conn.fetch("SELECT * FROM articles WHERE title = 'acme-secret'")
            assert len(rows) == 1  # acme can.
```

Three observations.

First: the test inserts a row as `acme`, then queries as `globex`, then queries as `acme` again. The middle query *must* return zero rows. The third query *must* return one row.

Second: the same connection is used throughout. The tenant switch happens inside transactions via `SET LOCAL`. This is exactly the production pattern under connection pooling — the test exercises the failure mode that `SET LOCAL` exists to prevent.

Third: if you run this test with `crunchreader_app` granted `BYPASSRLS`, *both* queries return the row. The test passes when the policy works, fails when the policy is bypassed. It catches every one of the four gotchas.

Ship this test. Run it on every CI build. The day it fails is the day you have a tenant-isolation regression — and you want to find that *before* it ships.

## 8 — Practitioner summary

Five things to remember out of Lecture 2:

1. **`ENABLE` + `CREATE POLICY` + `FORCE`**. Three statements. Missing any one is a bug. The default of "owner bypass without `FORCE`" is, charitably, surprising; uncharitably, dangerous. `FORCE` is non-negotiable.
2. **The application connects as a non-superuser, non-`BYPASSRLS` role**. Verify with `pg_roles`. The single most common production RLS failure is "we connected as `postgres` in development by accident; the test passed; we shipped".
3. **`SET LOCAL`, never `SET`**. Transaction-scoped tenant context. Pooled connections inherit nothing from the previous request. Always `LOCAL`.
4. **The leak-hunt test runs on every CI build**. Insert as A; read as B; expect zero rows. Read as A again; expect one row. This is the contract.
5. **`SECURITY DEFINER` is a deliberate hole in the fence**. Use it for admin functions; document each use; review them on a schedule.

Lecture 3 turns to the operational layer: tenant-aware caching, per-tenant rate limits, and the cross-tenant migration runbook. The isolation problem at the database layer is solved; the next question is how to keep one tenant's request volume from drowning another's.

---

### References cited in this lecture

- Postgres docs — Row Security Policies: <https://www.postgresql.org/docs/current/ddl-rowsecurity.html>
- Postgres docs — `CREATE POLICY`: <https://www.postgresql.org/docs/current/sql-createpolicy.html>
- Postgres docs — `ALTER TABLE`: <https://www.postgresql.org/docs/current/sql-altertable.html>
- Postgres docs — `SET` and `SET LOCAL`: <https://www.postgresql.org/docs/current/sql-set.html>
- Postgres docs — `CREATE FUNCTION` (`SECURITY DEFINER`): <https://www.postgresql.org/docs/current/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY>
- Postgres docs — `current_setting`: <https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADMIN-SET>
- Crunchy Data — "A Guide to Postgres Row Level Security": <https://www.crunchydata.com/blog/postgres-row-level-security-for-multi-tenant-saas>
- FastAPI — Dependencies with yield: <https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/>
