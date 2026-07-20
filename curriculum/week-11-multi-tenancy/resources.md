# Week 11 — Resources

Bookmarkable references for multi-tenancy patterns, PostgreSQL row-level security, and the operational discipline that the SaaS industry has worked out across the last fifteen years. Read the **must-read** rows first; the **deep-cut** rows are for the engineer who wants to read the source.

## PostgreSQL row-level security

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [Postgres docs — 5.9 Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) | The canonical reference. Sections 5.9.1 through 5.9.4 cover policy creation, `FORCE`, the `BYPASSRLS` role attribute, and the per-command policies. Read end-to-end on Wednesday morning. |
| must-read | [`CREATE POLICY`](https://www.postgresql.org/docs/current/sql-createpolicy.html) | The full grammar of `CREATE POLICY` — `FOR SELECT`/`INSERT`/`UPDATE`/`DELETE`/`ALL`, `TO role`, `USING (expr)`, `WITH CHECK (expr)`, `PERMISSIVE` vs `RESTRICTIVE`. The single page you will reference most. |
| must-read | [`ALTER TABLE ... ENABLE/FORCE ROW LEVEL SECURITY`](https://www.postgresql.org/docs/current/sql-altertable.html) | The "enable" versus "force" distinction; the table-owner bypass without `FORCE`. The most common RLS gotcha; the page that explains it. |
| must-read | [`SET` and `SET LOCAL`](https://www.postgresql.org/docs/current/sql-set.html) | The transaction-scoped lifetime of `SET LOCAL`; the connection-scoped lifetime of `SET`; the right pattern for per-request tenant context. The single distinction that, gotten wrong, leaks tenants across requests. |
| must-read | [`current_setting()` and `set_config()`](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADMIN-SET) | The mechanism for passing tenant context from the application into the RLS policy. `current_setting('app.current_tenant', true)` (with the `missing_ok` flag) is the safe call. |
| reference | [`CREATE ROLE` with `BYPASSRLS`](https://www.postgresql.org/docs/current/sql-createrole.html) | The role attribute that exempts a role from all RLS policies. Use for migration tools, replication, and admin scripts — never for the application connection. |
| reference | [`SECURITY DEFINER` functions](https://www.postgresql.org/docs/current/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY) | The escape hatch when a policy must be bypassed in code (e.g. "look up a tenant's settings without the tenant context being set yet"). The function runs with the privileges of its owner, not the caller. |
| deep-cut  | [Postgres source — `src/backend/rewrite/rowsecurity.c`](https://github.com/postgres/postgres/blob/master/src/backend/rewrite/rowsecurity.c) | The implementation. ~1 500 lines of C. `get_row_security_policies` is the load-bearing function — it walks the policy list and rewrites the query plan to include the `USING` predicate. |
| deep-cut  | [Crunchy Data — "A Guide to Postgres Row Level Security" by Craig Kerstiens](https://www.crunchydata.com/blog/postgres-row-level-security-for-multi-tenant-saas) | The production-oriented walkthrough — Craig Kerstiens ran Postgres-as-a-Service for Heroku and now Crunchy Data; this post is the most-cited RLS-for-SaaS reference. Free. |
| video     | [PGCon — "Row-level security and the curious case of the missing tenants" (search YouTube)](https://www.youtube.com/results?search_query=postgres+row+level+security+pgcon) | One-hour conference talk; the demo of "I forgot `FORCE` and my data leaked across tenants" is worth watching once. |

## The AWS SaaS Lens and tenant isolation

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [AWS SaaS Lens — overview](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/saas-lens.html) | The Well-Architected Framework's SaaS-specific guidance. Read the entire document at least once. Free. |
| must-read | [SaaS Lens — Tenant isolation](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/tenant-isolation.html) | The pool / bridge / silo vocabulary and the trade-off table. The 20-page section that defines the industry-standard terminology. |
| must-read | [SaaS Architecture Fundamentals whitepaper](https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/saas-architecture-fundamentals.html) | The longer companion document. The "Tenant isolation strategies" chapter has worked examples in DynamoDB, S3, RDS, and Aurora. Free PDF. |
| must-read | [SaaS Lens — Onboarding](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/onboarding.html) | The patterns for "how does tenant 47 get added to the system?". The shared-schema model makes onboarding a single `INSERT`; the silo model makes it a Terraform run. The trade-off is documented here. |
| reference | [SaaS Lens — Identity and access](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/identity-and-access-management.html) | The JWT-claim and IAM-policy patterns for per-tenant authorisation. Out of scope for W11 (we use `X-Tenant-ID` header for simplicity), but the references are here. |
| reference | [SaaS Lens — Noisy neighbour mitigation](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/noisy-neighbor.html) | The AWS-specific section on rate limits, connection pool limits, and cost attribution. The vocabulary maps directly to our `crunchreader-api` service. |
| deep-cut  | [SaaS Lens — Cost and usage attribution](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/cost-and-usage-attribution.html) | How to attribute infrastructure cost to individual tenants. The "who used 80% of the database CPU this month?" report. |

## Stripe engineering and other production case studies

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [Stripe Engineering — "Online migrations at scale"](https://stripe.com/blog/online-migrations) | The four-stage online-migration pattern (dual-write, backfill, dual-read, decommission) applied at production scale. Multi-tenant migrations multiply the cost; the pattern stays the same. Free. |
| must-read | [Stripe Engineering — "Scaling our database infrastructure"](https://stripe.com/blog/scaling-database-infrastructure) | Stripe runs the most-public multi-tenant Postgres deployment. The post explains the sharding strategy and the operational lessons. Free. |
| reference | [Notion Engineering — "Sharding Postgres at Notion"](https://www.notion.so/blog/sharding-postgres-at-notion) | Notion's pool-to-shard migration, with the painful parts called out. The discussion of "why we did not just use Citus" is worth reading. Free. |
| reference | [Figma Engineering — "How Figma's databases team lived to tell the scale"](https://www.figma.com/blog/how-figmas-databases-team-lived-to-tell-the-scale/) | Figma's horizontal sharding of a multi-tenant Postgres deployment. Free. |
| reference | [GitLab — "Why we spent the last month eliminating PostgreSQL subtransactions"](https://gitlab.com/gitlab-org/gitlab/-/issues/350417) | The GitLab issue tracker on a real RLS-adjacent bug — the multi-tenant lock contention story that one-database-per-tenant designs avoid. Free. |
| deep-cut  | [Heroku — "Heroku Postgres single tenancy"](https://www.heroku.com/postgres) | The original "database-as-a-service for one tenant" product. The pricing model is the industry baseline for what silo-tier isolation costs. |

## Citus and horizontally-sharded multi-tenant Postgres

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [Citus documentation — Multi-tenant applications](https://docs.citusdata.com/en/stable/use_cases/multi_tenant.html) | The production playbook for shared-schema multi-tenancy with `tenant_id` as the distribution column. Free. |
| reference | [Citus — Tenant isolation](https://docs.citusdata.com/en/stable/develop/multi_tenant.html) | The Citus-specific patterns: distribution columns, colocated tables, the per-tenant query plan. |
| reference | [Citus source on GitHub](https://github.com/citusdata/citus) | The Postgres extension itself. ~30 000 lines of C. The `distributed_planner.c` is the load-bearing file. |
| deep-cut  | [Microsoft — "Multi-tenant SaaS database tenancy patterns"](https://learn.microsoft.com/en-us/azure/azure-sql/database/saas-tenancy-app-design-patterns) | Azure's documentation on the same three models, with the Azure SQL Database-specific tooling. Vendor-neutral concepts, vendor-specific deployment. Free. |

## Tenant-aware caching and rate limiting

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [Redis docs — `SCAN`](https://redis.io/docs/latest/commands/scan/) | The cursor-based replacement for `KEYS`. The right way to iterate keys for per-tenant invalidation. |
| must-read | [Redis docs — `CLIENT TRACKING` and the keyspace notifications](https://redis.io/docs/latest/develop/use/keyspace-notifications/) | The mechanism for "when a key is evicted, notify me" — useful when per-tenant cache budgets need enforcement. |
| reference | [Redis docs — `MEMORY USAGE`](https://redis.io/docs/latest/commands/memory-usage/) | Per-key memory accounting; the basis for per-tenant cache-size reports. |
| reference | [Cloudflare — "How we built rate limiting capable of scaling to millions of domains"](https://blog.cloudflare.com/counting-things-a-lot-of-different-things/) | Cloudflare's per-tenant rate-limiting architecture. Different scale, same problem shape. Free. |

## Multi-tenant patterns canon

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [Gregor Hohpe / IBM — "Multi-tenant SaaS patterns"](https://www.ibm.com/cloud/architecture/architectures/saas-multi-tenant) | Vendor-neutral catalogue of the patterns. Read for the vocabulary. Free. |
| reference | [Microsoft — "Multi-tenant SaaS database tenancy patterns" (Azure SQL)](https://learn.microsoft.com/en-us/azure/azure-sql/database/saas-tenancy-app-design-patterns) | The Microsoft enumeration of the same models, with the Azure-specific deployment notes. Free. |
| reference | [Google Cloud — "Architecting multi-tenant SaaS solutions"](https://cloud.google.com/architecture/multitenant-saas-solutions) | The Google Cloud whitepaper. Same models, different vocabulary in places ("isolation level" vs "tenant tier"). Free. |
| reference | [Salesforce — "The architecture of multi-tenancy"](https://developer.salesforce.com/page/Multi_Tenant_Architecture) | The original SaaS company on their architecture. The "force.com" platform is shared-schema multi-tenancy at extreme scale. |
| deep-cut  | [Chong & Carraro, "Architecture Strategies for Catching the Long Tail" (MSDN, 2006)](https://learn.microsoft.com/en-us/previous-versions/dotnet/articles/aa479069(v=msdn.10)) | The Microsoft whitepaper that introduced the "tenant isolation maturity model" — Level 1 (per-tenant infrastructure) to Level 4 (shared everything). The vocabulary that the AWS SaaS Lens descends from. Twenty years old; still load-bearing. |

## Python clients and helpers

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [`asyncpg` documentation](https://magicstack.github.io/asyncpg/current/) | The async Postgres driver. The `Connection` and `Pool` APIs; the `set_session` method for `SET LOCAL` patterns. |
| must-read | [`asyncpg` `Pool` reference](https://magicstack.github.io/asyncpg/current/api/index.html#connection-pools) | Critical for multi-tenancy: connection pooling means a connection from Tenant A's request will be reused for Tenant B's request. The `set_session` and `release` semantics matter. |
| must-read | [FastAPI — Dependencies with yield](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/) | The pattern for "set tenant context before the handler, unset after" — the request-scoped tenant resolver lives here. |
| reference | [FastAPI — Middleware](https://fastapi.tiangolo.com/tutorial/middleware/) | The alternative to `Depends` for tenant resolution. Middleware runs earlier; dependencies are more composable. Use both. |
| reference | [Pydantic v2 — Models and validation](https://docs.pydantic.dev/latest/concepts/models/) | The `Tenant` model; the per-tenant settings model. |

## Tooling for testing and measurement

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| must-read | [`hey` — HTTP load generator](https://github.com/rakyll/hey) | The noisy-neighbour smoke test runs `hey` with two different `X-Tenant-ID` headers concurrently and measures whether Tenant A's load impacts Tenant B's latency. |
| reference | [`pytest-asyncio`](https://pytest-asyncio.readthedocs.io/) | The async test runner. Every RLS test is an async test (because `asyncpg` is async). |
| reference | [`pytest-postgresql`](https://pypi.org/project/pytest-postgresql/) | A `pytest` fixture for an ephemeral Postgres instance. Useful when the RLS tests need a clean state per test. |
| reference | [Postgres `EXPLAIN (ANALYZE, BUFFERS)`](https://www.postgresql.org/docs/current/sql-explain.html) | The query plan with RLS policies attached. Look for the `Filter` rows produced by the policy; surprise plans usually mean a policy on a joined table is more expensive than expected. |

## Worth a long read

| Type      | Link                                                                                       | Why                                                                                    |
|-----------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| deep-cut  | [Bain & Company — "SaaS economics: A primer"](https://www.bain.com/insights/saas-economics-a-primer/) | The business-side view of "why multi-tenancy matters". The unit economics of pool versus silo are the reason this architecture decision is, fundamentally, a finance decision. Free. |
| deep-cut  | [Werner Vogels — "Eventually consistent" (CACM 2009)](https://queue.acm.org/detail.cfm?id=1466448) | The AWS CTO on the consistency models that underpin multi-tenant systems at scale. Free. |
| deep-cut  | [Microsoft Research — "Multi-tenancy in SAP Business ByDesign"](https://www.microsoft.com/en-us/research/publication/multi-tenancy-in-sap-business-bydesign/) | The case study from one of the largest enterprise-SaaS deployments in the world. The trade-offs in metadata-driven tenancy. Free PDF. |
