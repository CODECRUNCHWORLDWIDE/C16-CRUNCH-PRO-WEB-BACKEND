# Week 11 — Quiz

Ten questions. Lectures closed. One correct answer per question; the answer key is at the end.

---

**Q1.** In the AWS SaaS Lens vocabulary, the model where every tenant has their own database is called:

- A) Pool.
- B) Bridge.
- C) Silo.
- D) Shard.

---

**Q2.** A Postgres table has `ENABLE ROW LEVEL SECURITY` and a `tenant_isolation` policy. The application connects as the table's owner. Without `FORCE ROW LEVEL SECURITY`, the owner:

- A) Sees only rows where the policy's `USING` clause evaluates true.
- B) Sees every row in the table, bypassing the policy entirely.
- C) Cannot read the table at all without the `BYPASSRLS` role attribute.
- D) Sees rows in arbitrary order; the policy is non-deterministic without `FORCE`.

---

**Q3.** The Postgres statement `SET LOCAL app.current_tenant = '...'` differs from `SET app.current_tenant = '...'` in that:

- A) `SET LOCAL` persists for the connection; `SET` persists for the transaction.
- B) `SET LOCAL` persists for the transaction; `SET` persists for the connection.
- C) `SET LOCAL` writes to disk; `SET` writes to memory.
- D) `SET LOCAL` is faster; `SET` is for one-time application use.

---

**Q4.** The composite primary key `(tenant_id, id)` on the shared-schema `articles` table is preferred over a single-column `id` plus a `tenant_id` secondary index because:

- A) Composite primary keys are faster to look up by definition.
- B) The composite key prevents the planner from using the index without a `tenant_id` filter — bad queries surface as slow queries.
- C) Postgres requires the primary key to include every non-null column.
- D) The composite key reduces storage overhead by 50%.

---

**Q5.** In a pooled-connection environment with RLS, the bug that "tenant A's data leaks to tenant B's next request" arises most commonly because:

- A) The `ENABLE ROW LEVEL SECURITY` statement was never run.
- B) The `FORCE` clause was omitted.
- C) The application used `SET` instead of `SET LOCAL`, so the tenant context persisted across pooled requests.
- D) The application role was created with `BYPASSRLS`.

---

**Q6.** A FastAPI dependency that sets `app.current_tenant` should:

- A) Run before any DB query is issued, inside an explicit transaction, using `SET LOCAL`.
- B) Run after the first DB query so the connection is "warmed up".
- C) Set the tenant ID via the connection's `set_session` method at pool acquisition time.
- D) Be combined with the user-authentication dependency so they share state.

---

**Q7.** In a multi-tenant Redis cache, the right key pattern for a cached article is:

- A) `article:{article_id}` — the article ID is unique across tenants.
- B) `tenant:{tenant_id}:article:{article_id}` — the tenant ID is part of the key.
- C) `article-{tenant_slug}-{article_id}` — using slugs for readability.
- D) The key does not matter; tenant isolation happens at the Redis-database level (`SELECT 0` through `SELECT 15`).

---

**Q8.** To iterate all of a tenant's keys in Redis for invalidation, the correct command is:

- A) `KEYS tenant:{tenant_id}:*` — blocking but accurate.
- B) `SCAN cursor MATCH tenant:{tenant_id}:*` — cursor-based, non-blocking.
- C) `MGET *` — get every key in one round trip.
- D) `MONITOR` — stream all commands and filter.

---

**Q9.** The "noisy neighbour" problem in pool tenancy is mitigated by:

- A) Switching from pool to silo immediately when the first noisy neighbour appears.
- B) Per-tenant rate limits and per-tenant connection-pool quotas.
- C) Adding more shared resources (a bigger connection pool, more Redis memory).
- D) Removing tenant isolation; if all tenants share, none can be a "neighbour".

---

**Q10.** Stripe's "Online migrations at scale" pattern recommends, for adding a `NOT NULL` column to a heavily-used table:

- A) `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT ...` in one statement.
- B) Add the column nullable, backfill in batches, then set `NOT NULL`.
- C) Pause writes, run the migration, resume writes.
- D) Create a new table with the new column, copy data, drop the old table.

---

## Answer key

| Question | Answer | Lecture / reference |
|---:|:---|:---|
| Q1 | C | Lecture 1 §1 — Silo is the AWS SaaS Lens name for database-per-tenant. |
| Q2 | B | Lecture 2 §2.3 — Without `FORCE`, the table owner bypasses RLS. The most common production gotcha. |
| Q3 | B | Lecture 2 §3.1 — `SET LOCAL` is transaction-scoped; `SET` is connection-scoped. |
| Q4 | B | Lecture 1 §2.1 — The composite PK forces every lookup to include `tenant_id`. |
| Q5 | C | Lecture 2 §3.1 — `SET` without `LOCAL` persists across pooled requests; this is the canonical multi-tenant leak. |
| Q6 | A | Lecture 2 §3.3 — Dependency sets `SET LOCAL` inside a transaction before any query. |
| Q7 | B | Lecture 3 §1.1 — Tenant-prefixed keys. |
| Q8 | B | Lecture 3 §1.2 — `SCAN` is the cursor-based, non-blocking iteration. `KEYS` blocks Redis. |
| Q9 | B | Lecture 3 §2 and §3 — Per-tenant rate limits and per-tenant pool quotas. |
| Q10 | B | Lecture 3 §5.1 — Add nullable, backfill, then constrain. |
