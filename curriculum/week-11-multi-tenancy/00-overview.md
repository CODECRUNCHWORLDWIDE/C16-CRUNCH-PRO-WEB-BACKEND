# Week 11 — Multi-tenancy: shared schema, schema-per-tenant, database-per-tenant, and PostgreSQL row-level security

> *Week 10 made the W7 service findable. Week 11 makes it sellable to more than one customer at a time. The single-tenant service you have been carrying since Week 7 has one set of articles, one set of authors, one Redis namespace, one rate-limit budget. The moment a second customer shows up, you discover that "multi-tenant" is not a checkbox on a deployment dashboard. It is a decision about how rows from Customer A and Customer B share — or do not share — a table, a schema, a database, a cache, and a request handler. Pick the wrong model on day one and you spend the next two years migrating your way out of it. Pick the right one and the cost of onboarding tenant number 47 is a single `INSERT` into a `tenants` table.*

Welcome to Week 11 of **C16 · Crunch Pro Web Backend**. The `crunchreader-api` service is now a small competent application: it serves articles, searches them three ways, caches the hot ones, indexes off the write path, and emits events on every change. What it cannot do is serve a *second* organisation's articles without those articles becoming visible to the first. The single-tenant assumption is baked into every SQL query in the service — every `SELECT * FROM articles WHERE id = $1` returns *the* article with that ID, with no consideration of which customer the requester belongs to. This week we tear that assumption out.

The work is *three architectures*, ranked from cheapest to most isolating: **shared schema with a `tenant_id` column** (one table, many tenants, the application is the boundary), **schema-per-tenant** (one Postgres schema per tenant, the `search_path` is the boundary), and **database-per-tenant** (one full database per tenant, the connection string is the boundary). Each costs more to operate; each isolates harder. The shared-schema model is the SaaS industry standard for small-to-medium tenants because it is the only one where onboarding a new tenant is an `INSERT`. Schema-per-tenant is the compromise. Database-per-tenant is the answer for healthcare, defence, and the regulated-enterprise tier where data-residency contracts say one company's bytes never touch another's. We build all three this week, and we leave with the picker that says which to use when.

On top of the architecture, we add **row-level security**: a Postgres-native enforcement layer that lives below the application. When the shared-schema model fails, it fails because an engineer forgot to write `WHERE tenant_id = $current_tenant` in some query. Row-level security makes that forgetting harmless. The `articles` table gets a policy: "rows are visible if and only if `tenant_id = current_setting('app.current_tenant')::uuid`". Every connection sets `app.current_tenant` at the start of its request. Every query — every one, including the one the engineer forgot to filter — is automatically filtered by the policy. The application is no longer the boundary; the database is. The Postgres documentation calls this "row-level security" or RLS; we will cite [Chapter 5.9](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) end-to-end.

We approach the topic with the AWS SaaS Lens whitepaper open. The Lens (a free PDF at <https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/saas-lens.html>) is the most-cited industry reference for SaaS architectural decisions; its "isolation models" section is the canonical taxonomy we will use. We also read the Stripe engineering blog post "[Online migrations at scale](https://stripe.com/blog/online-migrations)" and "[Scaling postgres with Citus](https://stripe.com/blog/scaling-database-infrastructure)" — Stripe runs the largest multi-tenant Postgres deployment in public documentation, and the lessons from their migration history are not theory.

By Sunday you will have:

1. **A shared-schema multi-tenant FastAPI service**, with a `tenant_id uuid` column on every tenant-scoped table, a FastAPI middleware that resolves the tenant from a `X-Tenant-ID` header (or a JWT claim, or a subdomain), and a Postgres connection wrapper that sets `app.current_tenant` per request.
2. **Row-level security policies** on every tenant-scoped table, with `FORCE ROW LEVEL SECURITY` on each so even the table owner cannot bypass. A test suite that demonstrates "tenant A cannot see tenant B's rows even when the SQL `WHERE` clause is missing".
3. **A schema-per-tenant variant** of the same service, with a per-tenant `search_path` set on every connection and a migration runner that applies the same DDL to every tenant schema.
4. **A database-per-tenant variant**, with a tenant-to-connection-string map, an `asyncpg` connection pool per tenant, and the cold-start cost measured.
5. **Tenant-aware caching**: Redis keys prefixed with the tenant ID, eviction strategies that respect tenant boundaries, the "tenant A evicted tenant B's hot keys" failure mode and its fix.
6. **Per-tenant rate limits and connection-pool quotas**: a token-bucket rate limiter that gives each tenant their own bucket, a connection pool that caps connections per tenant at `min(max_pool_size, per_tenant_quota)`, and the noisy-neighbour test that proves the cap holds.
7. **A migration strategy across tenants**: a runbook for the three models, with the shared-schema migration being a single `ALTER TABLE`, the schema-per-tenant migration being a `for tenant in tenants: psql -c '...' postgres://.../tenant_schema`, and the database-per-tenant migration being the most expensive of the three.

The async story from Weeks 7 through 10 carries forward. `asyncpg` for the database, a `RequestContext` that holds the tenant ID through the request, an `AsyncContextManager` that sets `app.current_tenant` at the start of each query and unsets it at the end. Pydantic v2 models for `Tenant` and the per-tenant settings. No new framework dependencies — multi-tenancy is a *pattern*, not a library.

## Learning objectives

By the end of this week, you will be able to:

- **Distinguish** the three isolation models with the AWS SaaS Lens vocabulary: **silo** (one database per tenant; the strongest isolation, the highest per-tenant cost), **pool** (shared schema, `tenant_id` column; the cheapest, the hardest to get right), and **bridge** (schema-per-tenant; the compromise). Cite the [AWS SaaS Lens whitepaper](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/general-design-principles.html), the [Multi-tenant SaaS architecture fundamentals](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/saas-lens-architecture-overview.html), and the [Tenant isolation strategies](https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/tenant-isolation.html) sections in particular.
- **Design** a shared-schema schema. Every tenant-scoped table gets a `tenant_id uuid NOT NULL` column; every primary key is composite `(tenant_id, id)` or has a `(tenant_id, ...)` index; every foreign key carries the tenant ID through; every query filters by `tenant_id` or relies on RLS to filter for it. Articulate why "just add a `tenant_id` column" is the easy part and "make sure every query filters by it, every join, every aggregation, every Redis cache key, every search index" is the hard part.
- **Implement** PostgreSQL row-level security from scratch. `ALTER TABLE articles ENABLE ROW LEVEL SECURITY;` enables the feature. `CREATE POLICY tenant_isolation ON articles USING (tenant_id = current_setting('app.current_tenant')::uuid);` defines the visibility predicate. `ALTER TABLE articles FORCE ROW LEVEL SECURITY;` is the gotcha — without `FORCE`, the table *owner* (typically the database user the application connects as) bypasses RLS entirely, and the policy is theatre. Cite the [Postgres RLS chapter](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — sections 5.9.1 through 5.9.4 cover policies, `FORCE`, `BYPASSRLS`, and the interactions with `INSERT`, `UPDATE`, `DELETE`.
- **Articulate** the RLS gotchas: the **superuser bypass** (any user with `SUPERUSER` or `BYPASSRLS` ignores all policies, no exceptions), the **table-owner bypass** without `FORCE ROW LEVEL SECURITY`, the **`USING` versus `WITH CHECK` distinction** (`USING` is the predicate for `SELECT`/`UPDATE`/`DELETE`; `WITH CHECK` is the predicate for `INSERT`/`UPDATE`; if you omit `WITH CHECK`, the `USING` clause is used for both), the **cost of policies on joins** (each policy adds a `WHERE` clause to every query; a 10-table join with policies on each can produce surprising plans), and the **`SECURITY DEFINER` function escape hatch** for the rare case where a policy must be bypassed in code.
- **Wire** tenant context propagation through FastAPI. A `Depends(get_current_tenant)` resolver reads the tenant from the request — typically an `X-Tenant-ID` header for service-to-service calls, a `tenant_id` JWT claim for end-user calls, or a subdomain (`acme.crunchreader.com`) for browser flows. The resolver returns a `Tenant` Pydantic v2 model. A second dependency wraps every DB session so that `SET LOCAL app.current_tenant = '<uuid>'` runs at the start of each transaction. Demonstrate the `SET LOCAL` versus `SET` distinction (the former is transaction-scoped and is the right one for request-scoped tenant context).
- **Build** a schema-per-tenant variant. Each tenant gets a Postgres schema named `tenant_<short_id>`; the application sets `SET search_path TO tenant_<short_id>, public;` on every connection. The same DDL applies to every schema; a migration runner iterates. Articulate the trade-off: schema-per-tenant gives you per-tenant `pg_dump` and per-tenant restore for free; it adds connection-time cost (the `search_path` set); it bloats the system catalog when the tenant count climbs (1 000 tenants × 50 tables per tenant = 50 000 rows in `pg_class`, which Postgres handles but plan caches get bigger).
- **Build** a database-per-tenant variant. Each tenant gets a Postgres database (or, equivalently, a managed-Postgres instance); the application holds a `dict[uuid, asyncpg.Pool]` of per-tenant pools. Articulate the trade-off: the strongest isolation (a runaway tenant cannot exhaust the connection pool of another tenant), the highest operational cost (every tenant is a separate backup, a separate `pg_dump`, a separate monitoring target), the cold-start cost of opening the first connection to a tenant's database after process restart.
- **Implement** tenant-aware caching in Redis. Every cache key is prefixed with the tenant ID: `tenant:{tenant_id}:article:{article_id}`. The cache invalidation pattern walks `SCAN MATCH "tenant:{tenant_id}:*"` (with the cursor pagination, never `KEYS`, which blocks the server). The eviction concern: when one tenant's working set is hot and another's is cold, LRU eviction will evict the cold tenant's keys first — which is correct behaviour but can manifest as "tenant B has terrible cache hit rates" when the cause is "tenant A is hogging the cache". The fix: per-tenant Redis databases, per-tenant cache size budgets, or a separate Redis instance per tenant for the largest customers.
- **Implement** per-tenant rate limits. A token-bucket rate limiter (the W9 pattern, refreshed) where the bucket key is `ratelimit:tenant:{tenant_id}:{endpoint}` and the bucket capacity is read from a per-tenant `rate_limits` table. Articulate the noisy-neighbour problem: without per-tenant limits, one tenant can consume the entire service's throughput, and every other tenant sees latency spikes. With per-tenant limits, each tenant's worst behaviour is bounded; the service-level limit is the sum of the per-tenant limits (or lower, when oversubscription is a deliberate choice).
- **Articulate** the migration strategy across tenants. The shared-schema migration is the simplest: one `ALTER TABLE` runs against the one schema; all tenants pick up the change instantly. The schema-per-tenant migration is the hardest: the same DDL must run against every tenant schema, in order, idempotently, with rollback. The database-per-tenant migration is the most expensive: every tenant database is a separate migration run, with its own lock acquisition and its own potential rollback. Cite [Stripe's "Online migrations at scale"](https://stripe.com/blog/online-migrations) — the pattern of "add column nullable, backfill, set not-null, deploy" is identical across the three models; what differs is the multiplier on how many times you run the pattern.
- **Articulate** the noisy-neighbour mitigation toolkit: per-tenant connection-pool quotas (the `max_connections` Postgres setting divided by the tenant count, with headroom; per-tenant `pgbouncer` user limits), per-tenant rate limits (the token-bucket per tenant per endpoint), per-tenant cost-budget tracking (count CPU-seconds per tenant; alert when one tenant exceeds 30% of total), per-tenant work prioritisation (separate ARQ queues for free-tier versus paid-tier tenants).
- **Pick** the right isolation model for the right tenant tier. The picker is not "always pool" or "always silo"; the picker is a matrix of tenant size, regulatory requirement, and operational budget. Free-tier tenants get pool. Mid-tier paying tenants get pool, with the option to migrate to bridge under contractual obligation. Enterprise tenants with a "data residency" or "single-tenant deployment" clause in their contract get silo. Cite the [AWS SaaS Lens tenant-tier guidance](https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/tenant-isolation.html).

## Prerequisites

- **C16 Weeks 7 through 10** — you have the FastAPI service with Pydantic v2 schemas, an `asyncpg` async DB session, Redis caching, an indexing pipeline, and a working search backend. The W11 work *replaces* the single-tenant assumption inside that service; it does not start from scratch.
- **Postgres 16.x with the `pgcrypto` extension** for `gen_random_uuid()`. Verify with `psql -c "CREATE EXTENSION IF NOT EXISTS pgcrypto; SELECT gen_random_uuid();"`. The W10 stack already has Postgres; W11 adds one extension.
- **A second Postgres role** for the application connections — not the `postgres` superuser. Critical: RLS policies are bypassed by superusers without exception. `CREATE ROLE crunchreader_app WITH LOGIN PASSWORD 'Crunch_Pro_W11_pw';` (and `GRANT` the appropriate privileges). The exercises will show you exactly what to grant.
- **`asyncpg` 0.30+** (already installed from W7/W10). Verify with `python3 -c "import asyncpg; print(asyncpg.__version__)"`.
- **A basic understanding of database transactions** — you should know what `BEGIN`, `COMMIT`, `ROLLBACK`, and `SET LOCAL` mean. If `SET LOCAL` is unfamiliar, read [the Postgres `SET` documentation](https://www.postgresql.org/docs/current/sql-set.html) before opening Lecture 2.
- **The AWS SaaS Lens whitepaper bookmarked**. Download once (it is updated quarterly; the May 2026 revision is the one we read this week) and keep the PDF open while reading Lecture 1.

## Topics covered

- The three isolation models: pool (shared schema), bridge (schema-per-tenant), silo (database-per-tenant); the AWS SaaS Lens vocabulary; the cost and isolation curves
- The shared-schema `tenant_id` column pattern: data model, indexing strategy, the composite primary key versus the separate index, the cascade rules for tenant deletion
- PostgreSQL row-level security: `ENABLE ROW LEVEL SECURITY`, `CREATE POLICY ... USING (...)`, `CREATE POLICY ... WITH CHECK (...)`, `FORCE ROW LEVEL SECURITY`, `BYPASSRLS`, the per-command policies (`FOR SELECT`, `FOR INSERT`, `FOR UPDATE`, `FOR DELETE`, `FOR ALL`), `PERMISSIVE` versus `RESTRICTIVE`
- The RLS gotchas: superuser bypass, the table-owner bypass without `FORCE`, `SECURITY DEFINER` functions, the cost of policies in joined queries, the `current_setting` pattern for passing tenant context
- The `SET LOCAL` versus `SET` versus `SET SESSION` distinction; the transaction-scoped lifetime of `SET LOCAL`; the right pattern for per-request tenant context
- The schema-per-tenant pattern: `CREATE SCHEMA tenant_<id>`, `SET search_path`, the per-tenant migration runner, the catalog-bloat consideration
- The database-per-tenant pattern: per-tenant connection strings, `dict[tenant_id, asyncpg.Pool]`, the cold-start cost, the per-tenant backup and restore
- FastAPI middleware for tenant resolution: header-based, JWT-based, subdomain-based; the `Depends(get_current_tenant)` resolver; the request-scoped tenant context
- Tenant-aware Redis caching: the key-prefix pattern, the `SCAN MATCH` invalidation, per-tenant Redis databases, the eviction-fairness problem
- Tenant-aware rate limiting: token bucket per tenant per endpoint; the per-tenant quota table; the noisy-neighbour mitigation
- Per-tenant connection-pool quotas: `pgbouncer` user limits, the application-level enforcement, the "tenant A starves tenant B" failure mode
- Cross-tenant migrations: the shared-schema simplicity, the schema-per-tenant iteration, the database-per-tenant cost; the Stripe online-migrations pattern applied to each
- Tenant-tier-based picking: free vs paid vs enterprise; when to graduate a tenant from pool to bridge to silo
- Observability through the tenant lens: per-tenant latency, per-tenant error rate, per-tenant request volume; the cardinality cost of "tenant ID" as a metric label

## Weekly schedule

The schedule below totals approximately **34 hours**. The architecture topic warrants two days (Monday and Tuesday); RLS warrants its own day (Wednesday) because the gotchas are surprising; the integration into the W7/W8/W9 service is the rest of the week.

| Day       | Focus                                                                                | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | The three isolation models: shared schema, schema-per-tenant, database-per-tenant      | 2h       | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 6h          |
| Tuesday   | Tenant context propagation: middleware, dependencies, `SET LOCAL`                       | 1.5h     | 2h        | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 5.5h        |
| Wednesday | PostgreSQL row-level security: policies, `FORCE`, the gotchas                          | 2h       | 2h        | 1h         | 0.5h      | 1h       | 0h           | 0.5h       | 7h          |
| Thursday  | Tenant-aware caching and per-tenant rate limits                                        | 0h       | 1h        | 1h         | 0.5h      | 1h       | 2h           | 0.5h       | 6h          |
| Friday    | Wire the W7 service: middleware, RLS policies, the per-tenant pool                     | 0h       | 0h        | 0h         | 0.5h      | 1h       | 2h           | 0h         | 3.5h        |
| Saturday  | Cross-tenant migrations; the runbook; the per-tenant observability                     | 0h       | 0h        | 0h         | 0h        | 1h       | 3h           | 0h         | 4h          |
| Sunday    | Quiz; reflection; the "which model and why" defence                                    | 0h       | 0h        | 0h         | 0.5h      | 0h       | 0.5h         | 0h         | 1h          |
| **Total** |                                                                                      | **5.5h** | **7h**    | **2h**     | **3h**    | **6h**   | **7.5h**     | **2h**     | **33h**     |

The pacing front-loads the architectural decision (Monday and Tuesday) because the choice constrains every downstream piece. Wednesday is the deepest single day of the week — RLS is foundational and its gotchas are not obvious. Friday and Saturday are the integration days; Sunday is the defence.

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview |
| [resources.md](./01-resources.md) | The Postgres RLS chapter, the AWS SaaS Lens whitepaper, Stripe engineering posts, the multi-tenant patterns canon |
| [lecture-notes/01-isolation-models-pool-bridge-silo.md](./02-lecture-notes/01-isolation-models-pool-bridge-silo.md) | The three models with the AWS SaaS Lens vocabulary; the cost-vs-isolation matrix; the decision tree |
| [lecture-notes/02-row-level-security-and-tenant-context.md](./02-lecture-notes/02-row-level-security-and-tenant-context.md) | RLS from scratch; the `FORCE` gotcha; `SET LOCAL`; the FastAPI middleware pattern |
| [lecture-notes/03-caching-rate-limits-and-cross-tenant-migrations.md](./02-lecture-notes/03-caching-rate-limits-and-cross-tenant-migrations.md) | The tenant-prefixed cache, the per-tenant rate limit, the migration runbook for each isolation model |
| [exercises/exercise-01-shared-schema-tenant-id-column.py](./03-exercises/exercise-01-shared-schema-tenant-id-column.py) | Build the shared-schema model; insert rows for two tenants; query with and without the `WHERE tenant_id = ...` filter |
| [exercises/exercise-02-row-level-security-policies.py](./03-exercises/exercise-02-row-level-security-policies.py) | Apply RLS policies; demonstrate `FORCE`; show the table-owner bypass; show the superuser bypass |
| [exercises/exercise-03-fastapi-tenant-middleware.py](./03-exercises/exercise-03-fastapi-tenant-middleware.py) | A FastAPI app with header-based tenant resolution; `SET LOCAL app.current_tenant`; integration with RLS |
| [exercises/exercise-04-per-tenant-rate-limit.py](./03-exercises/exercise-04-per-tenant-rate-limit.py) | A token-bucket per-tenant rate limiter on Redis; the noisy-neighbour smoke test |
| [exercises/exercise-05-multi-tenancy.sql](./03-exercises/exercise-05-multi-tenancy.sql) | The schema, the RLS policies, the per-tenant role grants, the test queries |
| [exercises/SOLUTIONS.md](./03-exercises/SOLUTIONS.md) | Worked solutions and trickier-line explanations |
| [challenges/challenge-01-rls-leak-hunt.md](./04-challenges/challenge-01-rls-leak-hunt.md) | Audit a small service for tenant-isolation bugs; demonstrate the bypass; write the fix |
| [challenges/challenge-02-cross-tenant-migration.md](./04-challenges/challenge-02-cross-tenant-migration.md) | Run the same DDL change across pool, bridge, and silo models; measure the cost and risk of each |
| [quiz.md](./05-quiz.md) | 10 multiple-choice questions |
| [homework.md](./06-homework.md) | Six problems (~6 h) |
| [mini-project/README.md](./07-mini-project/00-overview.md) | Build `crunchtenant` — a multi-tenant article service with RLS, per-tenant rate limits, and a tenant-onboarding endpoint |
| [mini-project/starter/](./07-mini-project/starter/) | Starter files: tenant middleware, RLS migration, per-tenant pool factory, rate limiter |

## Before Monday — verify the environment

Eight checks. If any fails, fix it before opening Lecture 1.

```bash
# 1. Python 3.12+
python3 --version
# Python 3.12.x or 3.13.x

# 2. Postgres 16 is reachable
psql -h localhost -U postgres -c 'SELECT version();' | head -1

# 3. pgcrypto is installable (for gen_random_uuid)
psql -h localhost -U postgres -c "CREATE EXTENSION IF NOT EXISTS pgcrypto; SELECT gen_random_uuid();"

# 4. A non-superuser application role exists (or can be created)
psql -h localhost -U postgres -c "CREATE ROLE crunchreader_app WITH LOGIN PASSWORD 'Crunch_Pro_W11_pw';" 2>&1 | head -1
# CREATE ROLE  (or "role already exists" which is fine)

# 5. Verify the role does NOT have BYPASSRLS or SUPERUSER
psql -h localhost -U postgres -c "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname='crunchreader_app';"
# rolsuper | f, rolbypassrls | f -- both false

# 6. Redis is reachable (from W9)
redis-cli ping
# PONG

# 7. The W10 stack still imports
python3 -c "import fastapi, redis, asyncpg, pydantic; print('ok')"

# 8. hey is installed (we use it for the noisy-neighbour smoke test)
hey -h 2>&1 | head -1
```

If `crunchreader_app` somehow ends up with `BYPASSRLS=t` or `SUPERUSER=t`, the RLS exercises will silently succeed when they should fail. The check at step 5 is the most important of the eight; do not skip it.

## The habit to install this week

Four practices, applied to every new endpoint and every new query from here forward:

1. **The tenant ID is non-optional on every tenant-scoped query.** No exceptions, no "this query is admin-only so it does not need it", no "we will add it later". Every `SELECT`, every `UPDATE`, every `DELETE` that touches a tenant-scoped table either filters by `tenant_id` explicitly or relies on an RLS policy that filters for it. The "we will add it later" version is how data leaks happen. RLS is the safety net; explicit filters are still cheaper to reason about; do both.
2. **`SET LOCAL`, never `SET`.** Tenant context is request-scoped. `SET app.current_tenant = '...'` (without `LOCAL`) persists for the whole *connection* — which, if the connection is pooled (and it should be), means the next request that picks up that connection inherits the tenant context of the previous request. That is exactly the data-leak bug RLS was supposed to prevent. `SET LOCAL` scopes to the transaction; when the transaction commits or rolls back, the setting is gone. Always `LOCAL`.
3. **Every Redis key has the tenant ID in the prefix.** `tenant:{tenant_id}:cache:article:{article_id}`. Not optional. The day you forget is the day you ship a feature where Tenant A's hot article gets cached under a key that Tenant B's request reads. The cost of the prefix is six bytes per key; the cost of the bug is a postmortem.
4. **Every per-tenant resource has a quota.** Rate limits per tenant. Connection-pool slots per tenant. CPU-seconds per tenant (tracked). Memory budget per tenant (tracked). The day a tenant's quota is "unbounded" is the day a runaway tenant takes down the service. The quotas can be generous; they cannot be infinite.

The first practice keeps the data isolated. The second keeps the isolation correct under connection pooling. The third extends isolation to the cache layer. The fourth keeps any one tenant from starving every other one. Together they are the W11 contract.

## Stretch goals

- Read **the full [AWS SaaS Lens whitepaper](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/saas-lens.html)** end to end. The PDF is ~80 pages; the "Multi-tenant Architecture" section is the load-bearing 20. Free.
- Read **the [Tenant isolation strategies whitepaper](https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/tenant-isolation.html)** — the AWS deep-dive on the pool / bridge / silo trade-offs with worked examples in DynamoDB, S3, and RDS. Free.
- Read **the Postgres source for RLS** — `src/backend/rewrite/rowsecurity.c` (~1 500 lines of C). The `get_row_security_policies` function is where policies are merged into the query plan; it is one of the cleanest pieces of rewrite-layer code in the tree.
- Read **the Citus documentation** at <https://docs.citusdata.com/> — Citus is the Postgres extension Stripe uses to shard their multi-tenant Postgres deployment horizontally. The "[Distributed PostgreSQL for Multi-Tenant Applications](https://docs.citusdata.com/en/stable/use_cases/multi_tenant.html)" guide is the production-scale playbook.
- Read **Gregor Hohpe's "Multi-Tenant SaaS Patterns"** — the IBM Cloud architecture team's catalogue at <https://www.ibm.com/cloud/architecture/architectures/saas-multi-tenant>. Free, vendor-neutral.

## Up next

[Week 12 — Observability: structured logging, metrics, and distributed tracing](../week-12-observability-logging-metrics-tracing/) — multi-tenant systems are observability-hungry by nature. You cannot debug a tenant-specific bug without per-tenant request traces, per-tenant error counters, and per-tenant latency histograms. Week 12 instruments the multi-tenant service from this week with structured logs (`logger.bind(tenant_id=...)`), Prometheus metrics tagged by tenant, and OpenTelemetry traces with the tenant ID as a span attribute. The cardinality cost of "tenant" as a metric label is the design constraint; we will resolve it.
