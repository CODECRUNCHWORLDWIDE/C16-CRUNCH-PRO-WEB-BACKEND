# Challenge 2 — Cross-tenant migration: pool versus bridge versus silo

**Time**: ~3 hours.

**Goal**: Run the same schema migration across three tenancy models — pool (shared schema), bridge (schema-per-tenant), and silo (database-per-tenant) — with 50 simulated tenants. Measure the operational cost of each. Write the runbook that says "for this kind of migration, this is the safe procedure".

The exercise is the operational complement to Lecture 1's design discussion. By the end you will know — by measurement, not by argument — why pool migrations are cheap and silo migrations are slow, and what mitigations bridge offers in the middle.

## The migration

The migration is the same across all three models. It is:

> Add a `read_time_seconds int` column to the `articles` table, backfilled from `length(body) / 250` (a 250-words-per-minute reading-rate estimate), with a `NOT NULL` constraint once the backfill is complete.

This is a realistic migration. It does not change semantics; it adds a computed column for sorting and filtering ("show me articles I can read in under 5 minutes"). The migration follows the four-phase Stripe online-migration pattern:

1. **Phase 1**: `ALTER TABLE articles ADD COLUMN read_time_seconds int;` (nullable, no default).
2. **Phase 2**: `UPDATE articles SET read_time_seconds = ceil(length(body)::float / (250.0 * 60 / 60)) WHERE read_time_seconds IS NULL;` (batched in chunks of 1 000 rows).
3. **Phase 3**: `ALTER TABLE articles ALTER COLUMN read_time_seconds SET NOT NULL;`.
4. **Phase 4**: drop the old approximate sort logic from the application (if any).

For this challenge, focus on phases 1, 2, and 3. Phase 4 is application-level and beyond the migration runner's scope.

## The setup

You need a Postgres instance with three databases:

- `cc_w11_pool` — shared schema with 50 tenants in one `articles` table.
- `cc_w11_bridge` — one database with 50 schemas (`tenant_001` through `tenant_050`), each with their own `articles` table.
- `cc_w11_silo` — 50 databases (`cc_w11_silo_001` through `cc_w11_silo_050`), each with its own `articles` table.

Seed each model with the same total amount of data: 50 000 articles split across 50 tenants (1 000 articles per tenant). Use random body text of varying lengths to make the backfill take meaningful time.

A setup script (`seed.py`) is suggested. The script:

1. Connects to the Postgres superuser.
2. Creates the three databases (with `CASCADE` and `WITH TEMPLATE template0` for cleanliness).
3. Applies the appropriate schema to each.
4. Seeds 1 000 articles × 50 tenants in each model.

The Postgres `CREATE DATABASE` command takes a few seconds per database, so the silo setup is the slowest. Plan for 5–10 minutes total seed time.

## The migration runner

Write a runner for each model. The runner accepts:

- The model (`pool`, `bridge`, `silo`).
- The phase (`1`, `2`, `3`).
- A `dry-run` flag.

For pool: phase 1 runs once; phase 2 batches by `tenant_id` (1 000 rows at a time, one transaction per batch); phase 3 runs once.

For bridge: phase 1 runs for each `tenant_NNN` schema (via `SET search_path = tenant_NNN, public`); phase 2 batches per schema; phase 3 runs per schema.

For silo: phase 1, 2, and 3 each run once per database; the runner connects to each database in turn.

Use Python's `time.monotonic()` to measure wall-clock time for each phase per model.

## The measurements

Capture:

| Metric                                 | Pool | Bridge | Silo |
|----------------------------------------|------|--------|------|
| Phase 1 total time                     |      |        |      |
| Phase 2 total time                     |      |        |      |
| Phase 3 total time                     |      |        |      |
| Total migration time                   |      |        |      |
| Locks taken (per-tenant max duration)  |      |        |      |
| Failure-recovery cost (see below)      |      |        |      |
| Lines of runner code                   |      |        |      |

Then run a **failure-recovery test**: deliberately fail the migration partway through (e.g. kill the runner process at 50% completion) and measure how long it takes to recover. Pool: a small `UPDATE` rolls back the in-progress batch; the next run picks up from where it left off. Bridge: a partially-migrated set of schemas means some are on the new schema and some are on the old; the runner must know which. Silo: same as bridge but multiplied — each database is a separate failure surface.

## The runbook

After the measurements, write a one-page `MIGRATION-RUNBOOK.md` covering:

1. **Pre-migration checks** for each model. E.g. for pool: "no long-running queries on `articles`"; for bridge: "all tenant schemas are in the expected state"; for silo: "every tenant database is reachable".
2. **The deployment order** for each model. For all three, the order is "add column nullable → deploy app code that handles both states → backfill → deploy app code that requires the column → set not null". For silo, you also pick a tenant ordering (smallest first, by row count).
3. **The rollback procedure** for each model. Phase 1 is reversible (`ALTER TABLE ... DROP COLUMN`); phase 3 is harder to reverse cleanly (you have to set the column nullable again, which is a metadata-only change but rules out applications that depend on the constraint).
4. **The communication plan**. Who needs to know the migration is running? For pool: the database team. For bridge: the database team and possibly the per-tenant ops team. For silo: every tenant's account manager if the migration window risks exceeding their SLA.

## The interpretation

The numbers will, predictably, show:

- **Pool is fastest by a factor of 5–20** for total wall-clock time. One `ALTER TABLE` is one `ALTER TABLE`; the backfill is a single tight loop.
- **Bridge is in the middle**, maybe 2–3× slower than pool. The N schemas multiply the per-schema overhead (each `SET search_path` is a system catalog read; each `ALTER TABLE` is a separate ACL check).
- **Silo is slowest**, maybe 5–10× slower than bridge. Per-database connection setup, per-database WAL flushing, per-database planning.

The *interesting* numbers are the failure-recovery costs and the lines-of-code metrics. Pool's runner is the simplest (50 lines or so). Bridge's runner is medium (100–150 lines, mostly schema iteration and idempotency). Silo's runner is the longest (200+ lines, plus the per-database connection management). The cost of silo is not just runtime — it is also the per-database operational machinery.

The two-paragraph summary at the bottom of `MIGRATION-RUNBOOK.md` says:

1. Which model you would recommend for the W7 service's actual production migration profile (likely pool, with the caveats from Lecture 1).
2. The conditions that would change the recommendation (regulatory, multi-region, per-tenant DDL needs).

## Stretch goal: zero-downtime deploys

Once the basic runner works, add a **zero-downtime** variant: the migration runs against the database while the application is still serving requests. The four-phase pattern allows this: phase 1 is metadata-only and is invisible to the application; phase 2 is read-write-safe because both the old and new application code can read and write rows (the new column is nullable; the old code does not read it; the new code handles `None`); phase 3 is the only phase that requires a brief constraint check.

Measure the impact of the migration on application latency. Run `hey -n 1000 -c 10` against the article endpoint *during* the migration and capture the p99 latency. Without care, phase 3's `ALTER TABLE ... SET NOT NULL` can hold a heavy lock briefly; the Postgres-12+ `NOT VALID` and `VALIDATE CONSTRAINT` pattern avoids the lock. Document which pattern you used and the latency cost.

## Cited

- Stripe Engineering — "Online migrations at scale": <https://stripe.com/blog/online-migrations>
- Postgres docs — `ALTER TABLE`: <https://www.postgresql.org/docs/current/sql-altertable.html>
- Postgres wiki — "Online schema migration": <https://wiki.postgresql.org/wiki/Online_Schema_Migration>
- AWS SaaS Lens — Operational excellence: <https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/operational-excellence.html>
- Microsoft Azure — Multi-tenant database patterns: <https://learn.microsoft.com/en-us/azure/azure-sql/database/saas-tenancy-app-design-patterns>
