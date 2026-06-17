# Exercise solutions — Week 11

Worked solutions for the four `.py` exercises and the `.sql` exercise, with explanations for the trickier lines. Read these only after you have made a real attempt at the exercises; the value is in the struggle, not the answer.

---

## Exercise 1 — Shared-schema with `tenant_id` column

### Task 1 — write a second buggy query that joins articles with tenants

```python
async def leak_via_join(conn: "asyncpg.Connection") -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT a.id, a.title, t.name AS tenant_name
          FROM articles a
          JOIN tenants  t ON t.id = a.tenant_id
         ORDER BY t.name, a.id
        """
    )
    return [dict(r) for r in rows]
```

Output (against the seed corpus):

```text
id=1 title="Acme Q1 launch plan"        tenant_name="Acme Corporation"
id=2 title="Acme team retreat agenda"   tenant_name="Acme Corporation"
id=3 title="Globex pricing strategy"    tenant_name="Globex Industries"
id=4 title="Globex board notes — March 2026" tenant_name="Globex Industries"
```

The join is "correct" SQL — every row has a tenant, every tenant has a name. The leak is that *every tenant's article* is in the result. There is no `WHERE a.tenant_id = current_tenant_uuid` clause, and the query happily returns rows from every tenant. A buggy admin dashboard query that just wants "the articles published this week" returns every customer's articles together.

### Task 2 — rewrite `get_tenant_article_by_id` to take only `article_id`

Without RLS: **you cannot**. Every query against a tenant-scoped table needs the tenant filter. There is no shortcut. The "easy" path is the leak path; the "safe" path is verbose:

```python
# Without RLS — the engineer must always pass tenant_id.
async def get_article(conn, tenant_id: uuid.UUID, article_id: int) -> dict | None:
    row = await conn.fetchrow(
        "SELECT * FROM articles WHERE tenant_id = $1 AND id = $2",
        tenant_id,
        article_id,
    )
    return dict(row) if row else None
```

With RLS (Exercise 2 onward), the tenant_id parameter disappears from the application call site because the policy enforces the filter:

```python
# With RLS — tenant context is set by middleware (SET LOCAL).
# The handler takes only article_id.
async def get_article(conn, article_id: int) -> dict | None:
    row = await conn.fetchrow(
        "SELECT * FROM articles WHERE id = $1",  # tenant_id added by RLS
        article_id,
    )
    return dict(row) if row else None
```

The RLS version is the right answer. The point of Exercise 1 is to show the cost of *not* having RLS: every function signature carries the tenant_id, every test must pass it, every refactor must preserve it. RLS removes that burden — and makes the leak path impossible.

### Task 3 — the `EXPLAIN ANALYZE` plan

Expected plan against the seed corpus:

```text
 Limit  (cost=8.45..8.46 rows=2 width=...) (actual time=0.045..0.046 rows=2 loops=1)
   ->  Sort  (cost=8.45..8.46 rows=2 width=...) (actual time=0.044..0.044 rows=2 loops=1)
         Sort Key: published_at DESC
         Sort Method: quicksort  Memory: 25kB
         ->  Index Scan using articles_by_tenant_published on articles
                 (cost=0.15..8.44 rows=2 width=...) (actual time=0.020..0.027 rows=2 loops=1)
               Index Cond: (tenant_id = '...'::uuid)
```

The line to find is `Index Scan using articles_by_tenant_published`. That confirms the composite index is doing the work. If you see `Seq Scan on articles`, the table is so small the planner judged the index not worth using; populate the table with more rows (a `INSERT INTO articles ... SELECT FROM generate_series(...)` against 10 000 rows) and re-run.

---

## Exercise 2 — Row-level security

### Task 1 — counts with and without `FORCE`

Run `owner_sees_everything` as `postgres` (the owner) with two different tenant UUIDs. Expected results:

**Without `FORCE`** (Part B of the exercise):

```text
owner sees 4 articles for acme, 4 for globex (these should match — leak)
```

Both calls return 4 — the total article count, because `postgres` is the table owner and bypasses the policy. The `SET LOCAL` is set, but `postgres` ignores the policy entirely, so the predicate is not applied. The owner sees every row.

**With `FORCE`** (Part C):

```text
owner now sees 2 articles for acme, 2 for globex (should differ now)
```

Each call returns 2 — the per-tenant article count. `FORCE` removes the owner bypass; the policy now applies to `postgres` too. The `SET LOCAL` controls what `postgres` sees.

The single behavioural diff between Part B and Part C is one line: `ALTER TABLE articles FORCE ROW LEVEL SECURITY`. That line is the difference between "policy is theatre" and "policy is the boundary".

### Task 2 — why fail-closed on unset context

Two reasons.

First: **silent zero rows are indistinguishable from "tenant has no data"**. A genuine "this tenant has no articles" response is also zero rows. A test that expects zero rows in the empty case passes when the policy is silently bypassed to return zero rows for every tenant. The bug ships to production; the postmortem documents how nobody noticed.

Second: **failing closed is forcing-function for correctness**. The error "current_setting cannot be cast to uuid" surfaces immediately, in development, on the first request that forgets to set the context. The engineer fixes the dependency before merging. The alternative — silent empty results — surfaces in production weeks later, on a tenant who notices their data is missing.

The Postgres `current_setting` two-argument form (`current_setting('app.current_tenant', true)`) is the *forgiving* version that returns an empty string for unset values. The one-argument form raises an error. **Use the one-argument form in the policy.** Use the two-argument form only in helper queries where unset is a legitimate state (e.g. a `/healthz` check that does not need tenant context).

### Task 3 — the cross-tenant `INSERT` error

Expected error from `attempt_cross_tenant_insert`:

```text
rejected: InsufficientPrivilegeError: new row violates row-level security policy "tenant_isolation" for table "articles"
```

The `WITH CHECK` clause of the policy is the gate. The application set `app.current_tenant = acme_uuid`; the `INSERT` tried to write a row with `tenant_id = globex_uuid`; the `WITH CHECK` predicate `tenant_id = current_setting('app.current_tenant')::uuid` evaluates `globex_uuid = acme_uuid`, which is `false`; Postgres rejects the insert with the message above.

**The takeaway**: even if an engineer constructs a malicious `INSERT` payload (or if a client somehow forges a tenant ID), the policy is the gate. The application is no longer the boundary.

---

## Exercise 3 — FastAPI tenant middleware

### Task 1 — what happens without the explicit transaction

If you remove `async with conn.transaction():` and run `SET LOCAL` directly on the connection:

```python
async def get_db_BROKEN(tenant_id):
    async with pool.acquire() as conn:
        await conn.execute("SET LOCAL app.current_tenant = $1", str(tenant_id))
        yield conn
```

Two failure modes appear:

1. **`SET LOCAL` without a transaction is a no-op.** Postgres returns a `WARNING` (not an error) and the setting is not applied. The next query's `current_setting('app.current_tenant')` fails (unset), and the request returns a 500.
2. **If the next query opens an implicit transaction**, the `SET` (without `LOCAL`) ends up in that transaction and persists for the rest of the connection — until another `SET` overrides it. The next pooled request inherits `app.current_tenant` from the previous request. Cross-tenant data leak.

`asyncpg` typically does (1) — the `SET LOCAL` outside a transaction is a `WARNING`. Other drivers (and the synchronous `psycopg2`) behave differently. The point: **always open a transaction first**. The cost is negligible (Postgres opens a lightweight transaction for any `BEGIN`); the safety is unconditional.

### Task 2 — the cross-tenant 404 test

```python
import httpx
import pytest

@pytest.mark.asyncio
async def test_cross_tenant_404() -> None:
    async with httpx.AsyncClient(base_url="http://localhost:8011") as client:
        acme_id = "<acme-uuid>"
        globex_id = "<globex-uuid>"

        # Tenant A creates an article.
        r = await client.post(
            "/articles",
            json={"title": "secret", "body": "...", "author": "alice"},
            headers={"X-Tenant-ID": acme_id},
        )
        assert r.status_code == 201
        article_id = r.json()["id"]

        # Tenant B tries to read it.
        r = await client.get(
            f"/articles/{article_id}",
            headers={"X-Tenant-ID": globex_id},
        )
        assert r.status_code == 404  # B cannot see A's article

        # Tenant A can read it.
        r = await client.get(
            f"/articles/{article_id}",
            headers={"X-Tenant-ID": acme_id},
        )
        assert r.status_code == 200
        assert r.json()["title"] == "secret"
```

Three observations:

- The 404 (not 403) is the right response. A 403 ("forbidden") tells the attacker that the resource *exists* but they cannot access it — which is enumeration assistance. The 404 tells them nothing about existence.
- The test makes three round-trips. Each opens its own transaction; each sets its own `app.current_tenant`; the connection pool is shared. The test is exactly the pattern that the `SET LOCAL` discipline exists to make safe.
- This test should run in CI on every PR. The day it fails is the day a tenant-isolation regression has been introduced.

### Task 3 — the `/healthz` endpoint

```python
@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

No `Depends(get_tenant_id)`. No `Depends(get_db)`. No database access at all. The endpoint returns instantly with no tenant context.

Why: health checks come from load balancers, monitoring systems, and uptime probes. They do not have a tenant identity. Requiring `X-Tenant-ID` on `/healthz` would either force the LB to pick a random tenant (bad — that tenant's metrics get polluted) or require LB configuration changes whenever a tenant is added. The clean answer is "health checks are not tenant-scoped".

A more advanced variant is a `/healthz/db` that opens a connection and runs `SELECT 1`. This is still not tenant-scoped — it does not set `app.current_tenant` — but it does verify the database is reachable. Use it sparingly; it can mask tenant-specific issues (the database is up but tenant X's quota is exhausted).

---

## Exercise 4 — Per-tenant rate limiting

### Task 1 — `current_tokens` without consuming

```python
async def current_tokens(
    redis: "Redis",
    tenant_id: uuid.UUID,
    endpoint: str,
    policy: TenantRateLimit,
) -> float:
    """Read the current bucket level without consuming."""
    key = f"ratelimit:tenant:{tenant_id}:{endpoint}"
    data = await redis.hmget(key, "tokens", "last_refill")
    tokens_raw, last_refill_raw = data
    if tokens_raw is None:
        return float(policy.capacity)  # never seen this tenant; full bucket
    tokens = float(tokens_raw)
    last_refill = float(last_refill_raw or 0)
    elapsed = time.time() - last_refill
    return min(float(policy.capacity), tokens + elapsed * policy.refill_rate)
```

The function returns the *current* token count, accounting for refill since `last_refill`. Two uses:

1. **Surface in the 429 response.** The `Retry-After` header can be derived from `(cost - current_tokens) / refill_rate` — seconds until the bucket has enough tokens for one request.
2. **Health checks.** A "tenants near their limit" alert reads `current_tokens` for every active tenant and emits a metric.

Note: this function does *not* update the bucket. It does not call `HMSET`. If you want a read-modify-write that observes the refilled value and writes it back, use the Lua script with `cost=0`.

### Task 2 — the shared bucket failure mode

If you change `noisy_neighbour_test` to use `key = f"ratelimit:global:{endpoint}"` (no tenant prefix), the test fails:

```text
AssertionError: tenant B should NOT have been rate-limited; per-tenant buckets are independent. Got rejected=18
```

Tenant A's 200-request burst consumes the entire 100-token capacity within the first few iterations. Tenant B's paced requests then arrive at a refilled-but-mostly-empty bucket; the 10 tokens/second refill is slower than B's 5 requests/second consumption *plus* A's continuing pressure. B's requests get rejected.

The takeaway: **a shared rate limit is not a rate limit per tenant**. It is a rate limit *for the service as a whole*, which is fine if "the service" has one tenant or if all tenants are happy to share the budget. As soon as one tenant is "noisier" than the rest, the shared-budget model becomes a denial-of-service-on-the-good-tenants vector.

The per-tenant key is six bytes longer. The isolation it buys is unconditional.

---

## Exercise 5 — The SQL schema

### Task 1 — why `ON DELETE CASCADE` on `articles.tenant_id`

Two reasons:

1. **Tenant offboarding is one statement.** `DELETE FROM tenants WHERE id = $1` cascades to every tenant-scoped table. The application code for offboarding is one line; the integrity is enforced by Postgres.
2. **It is faster than a manual delete loop.** Postgres's `CASCADE` walks the foreign-key graph in a single transaction. A manual delete loop (`DELETE FROM articles WHERE tenant_id = $1; DELETE FROM ...; DELETE FROM tenants WHERE id = $1;`) is many round-trips and can fail partway through.

The trade-off: for tenants with very large data volumes, the cascade can hold long locks. The mitigation is soft-delete (set `suspended_at` first, then a background job deletes in batches) for the largest tenants. For the W11 service, the cascade is the right starting point.

### Task 2 — why the composite primary key `(tenant_id, id)`

Three reasons:

1. **Locality.** The PK index physically clusters rows by `tenant_id`. After a `CLUSTER articles USING articles_pkey`, all of Tenant A's rows are contiguous on disk. Cache locality follows; sequential I/O is faster than random.
2. **Safety.** A query like `SELECT * FROM articles WHERE id = 42` cannot use the PK index — it does not have a `tenant_id` to seek on. The query falls back to a sequential scan, which is slow enough that the engineer notices and fixes the query. A non-composite PK would let the bad query succeed silently.
3. **Citus compatibility.** Citus (the Postgres extension Stripe uses for horizontal sharding) requires the distribution column to be in every primary key. Composite PK with `tenant_id` as the leading column is the Citus-ready shape.

### Task 3 — why grant `USAGE` on `articles_id_seq`

`bigserial` is shorthand for `bigint NOT NULL DEFAULT nextval('articles_id_seq')`. Inserting into the table calls `nextval(...)` on the sequence; `nextval` requires `USAGE` privilege on the sequence (not just on the table).

Without `GRANT USAGE ON SEQUENCE articles_id_seq TO crunchreader_app`, `INSERT INTO articles ...` fails with:

```text
ERROR: permission denied for sequence articles_id_seq
```

The fix is the explicit grant. It is the single most common "I granted DML on the table but inserts still fail" cause in Postgres multi-tenant setups.
