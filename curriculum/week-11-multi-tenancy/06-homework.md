# Week 11 — Homework

Six problems. About six hours of work. Submit one PR with the changes; reviewers will look for the RLS verification, the tenant-isolation test suite, and the per-tenant rate-limit configuration committed alongside the code.

---

## Problem 1 — Convert the W7 articles service to shared-schema multi-tenant (1.5 h)

Take the W7 `crunchreader-api` service. Add a `tenants` table and a `tenant_id` column to every tenant-scoped table. Apply the migration as a reversible Alembic (or Django, depending on the stack you carried forward) migration.

Acceptance:

- The `tenants` table has `(id uuid PK, slug text UNIQUE, name text, tier text CHECK in ('free','paid','enterprise'), created_at timestamptz)`.
- Every tenant-scoped table has a `tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE` column.
- Every tenant-scoped table has a composite primary key with `tenant_id` as the leading column (or, if you prefer the single-column PK approach, a `(tenant_id, ...)` secondary index for every common query).
- The migration is reversible (`alembic downgrade -1` cleanly removes the changes).
- A seed script creates two tenants (`acme` and `globex`) and assigns existing articles to them deterministically (e.g. articles 1–N to acme, N+1 onward to globex).

Deliverable: the migration diff, the seed script, and a one-paragraph note in the PR description explaining how you handled existing data (which tenant did legacy articles get assigned to, and why).

---

## Problem 2 — Apply RLS policies and the application role (1 h)

Enable RLS on every tenant-scoped table. Create the application role. Verify the role has neither `SUPERUSER` nor `BYPASSRLS`.

Acceptance:

- Every tenant-scoped table has `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
- Every tenant-scoped table has a `tenant_isolation` policy with `USING (tenant_id = current_setting('app.current_tenant')::uuid)` and `WITH CHECK (...)` identical to the `USING`.
- A `crunchreader_app` role exists, with `LOGIN`, no `SUPERUSER`, no `BYPASSRLS`.
- The role has `GRANT SELECT, INSERT, UPDATE, DELETE` on every tenant-scoped table, `GRANT SELECT` on `tenants`, and `GRANT USAGE` on every sequence used by `bigserial` columns.
- A SQL verification script (`scripts/verify_rls.sql`) returns no errors when run: it queries `pg_class` to confirm `relrowsecurity` and `relforcerowsecurity` are both `t`; it queries `pg_roles` to confirm `crunchreader_app` has the right attributes; it lists `pg_policies` to confirm the policy exists.

Deliverable: the migration, the verification script, and a screenshot of the script's output.

---

## Problem 3 — Switch the application to the `crunchreader_app` role and add tenant middleware (1.5 h)

Update the application's database connection to use `crunchreader_app`, not the deployment user. Add a FastAPI middleware (or Django middleware, depending) that resolves the tenant from an `X-Tenant-ID` header and sets `app.current_tenant` via `SET LOCAL` at the start of each transaction.

Acceptance:

- The application's DSN uses `crunchreader_app`.
- A middleware (or dependency, in FastAPI) parses `X-Tenant-ID` as a UUID and rejects malformed headers with 400.
- The DB session wrapper opens a transaction before any query and calls `SET LOCAL app.current_tenant = $1`.
- All existing endpoints work without changes (the RLS policy supplies the `WHERE tenant_id` filter that used to be in the SQL).
- A new endpoint `GET /tenants/me` returns the current tenant's row from `tenants`.

Deliverable: the diff plus a `pytest` test that confirms `GET /articles` returns only the current tenant's articles when called with two different `X-Tenant-ID` headers.

---

## Problem 4 — Add per-tenant rate limiting (1 h)

Implement the token-bucket rate limiter from Exercise 4 in the production service. Use the per-tenant `rate_limits` table to drive the policy; fall back to a per-tier default if no row exists.

Acceptance:

- A `rate_limits (tenant_id, endpoint, capacity int, refill_rate float)` table exists.
- A middleware (or dependency) reads the rate limit for the current tenant and endpoint (with a Redis-backed cache, 60-second TTL), then consumes a token via the Lua-scripted token-bucket algorithm.
- Requests over the limit return 429 with a `Retry-After` header.
- A counter metric `rate_limit_rejected_total{tenant_id, endpoint}` increments on rejection.
- A `pytest` test issues 200 requests in a tight loop for one tenant and asserts the rejection count is non-zero.

Deliverable: the diff plus the test plus a short note on how you chose the default per-tier limits.

---

## Problem 5 — Add tenant-prefixed caching (45 min)

Update every Redis cache key in the service to include the tenant ID. The article-detail cache (from W9), the search-result cache (from W10), any session caches.

Acceptance:

- Every cache `SET` and `GET` runs through a `TenantCache` wrapper (or equivalent) that automatically prefixes keys with `tenant:{tenant_id}:`.
- A `pytest` test populates the cache as Tenant A; reads the same key as Tenant B; asserts the read returns `None` (no leak).
- The cache invalidation path (when an article is updated) uses `SCAN MATCH tenant:{tenant_id}:cache:article:*` — never `KEYS`.

Deliverable: the diff plus the test.

---

## Problem 6 — Add a tenant-onboarding endpoint (1 h)

Add a `POST /admin/tenants` endpoint that creates a new tenant atomically. Restrict the endpoint to admin callers (a hard-coded admin secret in `Authorization: Bearer <secret>` is fine for the homework; production would use a proper IAM check).

Acceptance:

- The endpoint accepts `{"slug": "...", "name": "...", "tier": "free|paid|enterprise"}`.
- The endpoint inserts the tenant, populates the `rate_limits` table with default per-tier entries for each endpoint, and returns the new tenant ID.
- Onboarding is atomic — if any step fails, the whole transaction rolls back.
- A `pytest` test creates a tenant; confirms the tenant exists; confirms the rate-limit rows exist; confirms an unrelated tenant's data is unaffected.

Deliverable: the endpoint diff, the test, and a one-paragraph design note explaining what would change if the same endpoint had to support bridge or silo tenancy (hint: the simple `INSERT` is the strength of pool; bridge requires a schema-create step, silo requires database provisioning).

---

## Submission checklist

- [ ] Migration applied and reversible (Problem 1).
- [ ] RLS enabled and FORCED on every tenant-scoped table; verification script passes (Problem 2).
- [ ] Application connects as non-superuser, non-BYPASSRLS role (Problem 2).
- [ ] Tenant middleware sets `app.current_tenant` via `SET LOCAL` inside a transaction (Problem 3).
- [ ] Per-tenant rate limits enforced; over-limit requests return 429 (Problem 4).
- [ ] All cache keys are tenant-prefixed (Problem 5).
- [ ] Tenant-onboarding endpoint creates tenant + default rate-limit rows atomically (Problem 6).
- [ ] All `.py` files compile (`python3 -m py_compile <file>` returns clean).
- [ ] All tests pass; the suite includes the leak-hunt test from Challenge 1.

If anything blocks you for more than 30 minutes, post in the channel. The goal is to *finish* the homework — partial credit is better than perfect credit you ran out of time to deliver.
