-- Exercise 5 — Multi-tenancy schema, RLS policies, role grants.
--
-- Applies the table + extensions + indexes + RLS policies for Exercises
-- 1 through 4. Idempotent: safe to re-run; uses CREATE ... IF NOT EXISTS
-- and DROP ... IF EXISTS where re-running would otherwise error.
--
-- Usage:
--     createdb cc_w11                          -- once
--     psql -d cc_w11 -f exercise-05-multi-tenancy.sql
--
-- Cited:
--     https://www.postgresql.org/docs/current/ddl-rowsecurity.html
--     https://www.postgresql.org/docs/current/sql-createpolicy.html
--     https://www.postgresql.org/docs/current/sql-set.html

-- ---------------------------------------------------------------------------
-- 0. Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()


-- ---------------------------------------------------------------------------
-- 1. The tenants registry (NOT tenant-scoped)
-- ---------------------------------------------------------------------------
--
-- The list of tenants is shared. Every tenant-scoped table references
-- this table via tenant_id. This is the "pool" admin surface.

DROP TABLE IF EXISTS articles CASCADE;  -- drop dependent first
DROP TABLE IF EXISTS tenants CASCADE;

CREATE TABLE tenants (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        text        NOT NULL UNIQUE,
    name        text        NOT NULL,
    tier        text        NOT NULL DEFAULT 'free'
                CHECK (tier IN ('free', 'paid', 'enterprise')),
    suspended_at timestamptz NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------------
-- 2. The articles table (tenant-scoped, RLS-protected)
-- ---------------------------------------------------------------------------
--
-- Composite primary key (tenant_id, id) is deliberate. It physically
-- clusters tenant-A's rows together on disk (with CLUSTER on the PK
-- index) and makes "look up id N without a tenant filter" impossible:
-- the PK index requires both columns for a lookup.

CREATE TABLE articles (
    id           bigserial,
    tenant_id    uuid        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title        text        NOT NULL,
    body         text        NOT NULL,
    author       text        NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);

-- Secondary index for the common "list this tenant's most recent articles"
-- query. Tenant_id is the leading column.
CREATE INDEX articles_by_tenant_published
    ON articles (tenant_id, published_at DESC);


-- ---------------------------------------------------------------------------
-- 3. Row-level security
-- ---------------------------------------------------------------------------
--
-- Three statements, in order:
--   1. ENABLE ROW LEVEL SECURITY    -- turn on
--   2. CREATE POLICY                -- define the visibility predicate
--   3. FORCE ROW LEVEL SECURITY     -- prevent owner bypass
--
-- Skipping step 3 is the most common production bug. See lecture 2 §4.2.

ALTER TABLE articles ENABLE ROW LEVEL SECURITY;

-- Drop the policy first to make the file re-runnable.
DROP POLICY IF EXISTS tenant_isolation ON articles;

CREATE POLICY tenant_isolation ON articles
    USING (tenant_id = current_setting('app.current_tenant')::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid);

ALTER TABLE articles FORCE ROW LEVEL SECURITY;


-- ---------------------------------------------------------------------------
-- 4. Per-tenant rate-limit policies (used by Exercise 4)
-- ---------------------------------------------------------------------------
--
-- The application reads this table to find the rate limit for the
-- current (tenant, endpoint) pair, then enforces it in Redis.

DROP TABLE IF EXISTS rate_limits;

CREATE TABLE rate_limits (
    tenant_id   uuid        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    endpoint    text        NOT NULL,
    capacity    int         NOT NULL CHECK (capacity > 0),
    refill_rate float       NOT NULL CHECK (refill_rate > 0),
    PRIMARY KEY (tenant_id, endpoint)
);


-- ---------------------------------------------------------------------------
-- 5. The application role
-- ---------------------------------------------------------------------------
--
-- The application connects as `crunchreader_app`. NOT a superuser. NOT
-- BYPASSRLS. The RLS policy applies to this role.
--
-- We use a DO block to make the CREATE ROLE idempotent (CREATE ROLE
-- itself errors on duplicate; the DO block catches the duplicate_object
-- exception).

DO $$
BEGIN
    CREATE ROLE crunchreader_app WITH LOGIN PASSWORD 'Crunch_Pro_W11_pw';
EXCEPTION WHEN duplicate_object THEN
    -- role already exists; that's fine.
    NULL;
END$$;

-- Sanity check: confirm the role does NOT have BYPASSRLS or SUPERUSER.
DO $$
DECLARE
    is_super  boolean;
    is_bypass boolean;
BEGIN
    SELECT rolsuper, rolbypassrls
      INTO is_super, is_bypass
      FROM pg_roles
     WHERE rolname = 'crunchreader_app';
    IF is_super THEN
        RAISE EXCEPTION 'crunchreader_app has SUPERUSER; RLS will be bypassed';
    END IF;
    IF is_bypass THEN
        RAISE EXCEPTION 'crunchreader_app has BYPASSRLS; RLS will be bypassed';
    END IF;
END$$;

GRANT CONNECT  ON DATABASE cc_w11        TO crunchreader_app;
GRANT USAGE    ON SCHEMA   public        TO crunchreader_app;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON articles, rate_limits             TO crunchreader_app;
GRANT SELECT
    ON tenants                           TO crunchreader_app;
GRANT USAGE    ON SEQUENCE articles_id_seq TO crunchreader_app;


-- ---------------------------------------------------------------------------
-- 6. Sanity-check queries
-- ---------------------------------------------------------------------------

-- Confirm the RLS state on articles.
--   relrowsecurity      -- should be `t`
--   relforcerowsecurity -- should be `t`
SELECT relname, relrowsecurity, relforcerowsecurity
  FROM pg_class
 WHERE relname IN ('articles', 'tenants');

-- List the policies on articles. Should show `tenant_isolation`.
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
  FROM pg_policies
 WHERE tablename = 'articles';
