# Mini-project — `crunchtenant`

> *Take the W7 article service. Make it multi-tenant. Ship it with RLS, per-tenant rate limits, per-tenant cache prefixes, and a tenant-onboarding endpoint. The mini-project for Week 11 is the architectural conversion: the single-tenant assumption that has been baked into the service since Week 7 comes out, and the three-layer isolation contract — RLS at the database, prefixes at the cache, quotas at the entry point — goes in.*

**Time**: ~7.5 hours over the second half of the week.

## What you are building

A FastAPI service (extending the W7 `crunchreader-api`) that supports an unbounded number of tenants on a single shared schema, with:

1. A `tenants` registry and a `tenant_id` column on every tenant-scoped table.
2. Postgres row-level security policies on every tenant-scoped table, `FORCE`d so the table owner is not exempt.
3. A FastAPI dependency that resolves the tenant from the `X-Tenant-ID` header and sets `app.current_tenant` via `SET LOCAL` inside a transaction.
4. A per-tenant token-bucket rate limiter on Redis, fed by a `rate_limits` table.
5. Tenant-prefixed Redis cache keys; every `GET`/`SET`/`DELETE` is per-tenant.
6. A `POST /admin/tenants` endpoint that onboards a new tenant atomically (the tenant row plus default per-tier rate-limit rows).
7. A pytest suite that proves tenant isolation — including the "leak-hunt" tests from Challenge 1.

By Sunday evening, your repo has the `crunchtenant` service running as a single-tenant from one perspective (each request has a single tenant; the application code is unchanged) and a many-tenant from another (the database holds rows for 50+ tenants without any of them seeing another's data).

## The architecture

```text
                  GET /articles                       POST /admin/tenants
                       |                                       |
                       v                                       v
                  +--------+                              +----------+
                  | FastAPI|                              | FastAPI  |
                  | router |                              |  admin   |
                  +---+----+                              +-----+----+
                      |                                         |
                      v                                         v
              +-------+--------+                       +--------+--------+
              | get_tenant_id  |                       | admin auth check|
              | (X-Tenant-ID)  |                       +--------+--------+
              +-------+--------+                                |
                      |                                         |
                      v                                         v
              +-------+--------+                        +-------+--------+
              | rate-limit     |                        | tenant create   |
              | (Lua bucket)   |                        | (insert + RLS   |
              +-------+--------+                        |  rate-limit DEF)|
                      |                                 +-------+--------+
                      v                                         |
              +-------+--------+                                v
              | get_db         |                          +-----+-----+
              | SET LOCAL ...  |                          | response  |
              +-------+--------+                          +-----------+
                      |
                      v
              +-------+--------+
              | RLS-protected  |
              | Postgres query |
              +----------------+
                      |
                      v
              +-------+--------+
              | tenant-prefixed|
              | Redis cache    |
              +----------------+
```

Five moving parts:

- **Postgres** holds the source-of-truth tables with RLS policies. The application connects as `crunchreader_app` (non-superuser, non-BYPASSRLS); RLS is enforced.
- **Redis** is the cache + rate-limit store. Every key is tenant-prefixed; the rate limiter uses one Lua-scripted bucket per `(tenant, endpoint)` pair.
- **The tenant resolver** parses `X-Tenant-ID` and returns the tenant UUID; this happens before any DB access.
- **The DB dependency** opens a transaction and sets `app.current_tenant` via `SET LOCAL`; every query inside the dependency runs under the policy.
- **The admin endpoint** is a separate router with its own auth (a bearer token in the homework; a real IAM identity in production).

## Step-by-step plan

### Day 1 — wire the isolation primitives (Friday, ~2 h)

1. Apply the migration that adds `tenants`, `tenant_id` columns, RLS policies, the application role, and the `rate_limits` table (from `homework.md` Problems 1 and 2).
2. Update the application's connection string to use `crunchreader_app`.
3. Write the tenant-resolver dependency and the DB session dependency.
4. Verify with two `curl` calls (different `X-Tenant-ID` headers) that the same endpoint returns different data.

Acceptance: `GET /articles` with `X-Tenant-ID: <acme-uuid>` returns Acme's articles; with `<globex-uuid>` returns Globex's; with no header or an invalid header returns 400.

### Day 2 — wire the cache and rate-limit layers (Friday/Saturday, ~2 h)

1. Implement `TenantCache` — the per-tenant wrapper around Redis. Update every cache call site to use it.
2. Implement the Lua-scripted rate limiter from Exercise 4. Add the middleware that reads the per-tenant policy and consumes a token before the request handler runs.
3. Add the `Retry-After` header and the `rate_limit_rejected_total` metric counter.
4. Run `hey -n 1000 -c 10 -H "X-Tenant-ID: <uuid>"` against `/articles` and observe the 429s when the bucket is depleted.

Acceptance: a burst of 200 requests for one tenant produces 429s after the bucket is empty; the next tenant's requests are unaffected.

### Day 3 — wire the admin endpoint and the tenant lifecycle (Saturday, ~2 h)

1. Implement `POST /admin/tenants` with bearer-token auth.
2. The endpoint inserts the tenant, inserts the default per-tier rate-limit rows, returns the new tenant ID. All in one transaction.
3. Add `POST /admin/tenants/{tenant_id}/suspend` and `POST /admin/tenants/{tenant_id}/unsuspend` to manage tenant lifecycle.
4. Add a check in the tenant-resolver dependency that returns 402 if the tenant is suspended.

Acceptance: a new tenant can be created via the API; the new tenant immediately receives default rate limits; suspending a tenant rejects their next request with 402.

### Day 4 — leak-hunt and write up (Sunday, ~1.5 h)

1. Run the leak-hunt tests from Challenge 1. Confirm none of the three bugs are present in your service.
2. Write `ISOLATION.md` documenting the three layers of isolation (database, cache, rate limit) and how to add a new tenant-scoped table or cache key.
3. Update the service README with a "Multi-tenancy" section that lists the contract (every Redis key prefixed, every query through `get_db`, every endpoint subject to per-tenant rate limits).

Acceptance: a future engineer can read `ISOLATION.md` and answer "where do I add a new tenant-scoped table?" without asking anyone.

## The deliverables

A repo (a branch of the W7 service) with:

- The migrations from `homework.md` Problems 1, 2, 3 applied.
- The middleware, dependencies, and routes from `homework.md` Problems 3, 4, 5, 6 implemented.
- A `tests/` directory with:
  - `test_rls_isolation.py` — the per-tenant data-isolation tests.
  - `test_rate_limit.py` — the per-tenant rate-limit tests.
  - `test_cache_isolation.py` — the per-tenant cache tests.
  - `test_admin_onboarding.py` — the tenant-onboarding test.
- An `ISOLATION.md` documenting the contract.
- A `BENCHMARK.md` (optional but encouraged) with `hey`-measured latencies for cold-cache and warm-cache requests, per tier.

## The starter

`starter/` contains scaffolding for the conversion. The files are:

- `settings.py` — environment-driven config.
- `schemas.py` — Pydantic v2 models for `Tenant`, `Article`, `RateLimitPolicy`.
- `deps.py` — the FastAPI dependencies (`get_tenant_id`, `get_db`, `enforce_rate_limit`, `require_admin`).
- `routers_admin.py` — the admin router (tenant onboarding, suspension).
- `routers_articles.py` — the article router (the per-tenant CRUD).
- `cache.py` — the `TenantCache` wrapper.
- `rate_limit.py` — the Lua-scripted rate-limit consumer.
- `migrations/001_multi_tenancy.sql` — the migration that adds tenants, `tenant_id`, RLS, the application role, the rate-limits table.

Each file has TODOs in the implementation; the comments explain what each piece does.

## The acceptance criteria — one page

Your service passes the mini-project if:

1. **Tenant isolation is enforced at the database**. The leak-hunt tests pass. Tenant A's `GET /articles/{id}` returns 404 for Tenant B's article IDs.
2. **The application connects as a non-superuser, non-BYPASSRLS role**. Verifiable via `psql -c "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'crunchreader_app'"`.
3. **The `FORCE ROW LEVEL SECURITY` is on every tenant-scoped table**. Verifiable via `psql -c "SELECT relname, relforcerowsecurity FROM pg_class WHERE relname IN ('articles', ...)"`.
4. **Per-tenant rate limits are enforced**. A 200-request burst on `/articles` for one tenant produces 429s. The same request rate from another tenant is unaffected.
5. **Cache keys are tenant-prefixed**. Verifiable via `redis-cli KEYS "tenant:*" | head` showing tenant-prefixed keys; verifiable via the `test_cache_isolation` test.
6. **Tenant onboarding is one API call**. `POST /admin/tenants` creates the row and the default rate-limit rows atomically.
7. **The `ISOLATION.md` exists and explains where to add the next tenant-scoped resource**.

The numbers (latency, throughput, p99) are in `BENCHMARK.md` if you ran the optional benchmark. The mini-project does not require it; the architectural conversion is the deliverable.

## Cited

- AWS SaaS Lens — Tenant isolation: <https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/tenant-isolation.html>
- Postgres docs — Row Security Policies: <https://www.postgresql.org/docs/current/ddl-rowsecurity.html>
- Stripe Engineering — Online migrations: <https://stripe.com/blog/online-migrations>
- Cloudflare — Rate limiting at scale: <https://blog.cloudflare.com/counting-things-a-lot-of-different-things/>
- Crunchy Data — Postgres RLS for SaaS: <https://www.crunchydata.com/blog/postgres-row-level-security-for-multi-tenant-saas>
