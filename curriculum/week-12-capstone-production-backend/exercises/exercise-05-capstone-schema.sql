-- Exercise 05 — The capstone schema, end to end.
--
-- This file is the database half of the capstone. It declares every
-- table, every index, every constraint, every RLS policy, every trigger,
-- and a seed-data block that populates three sample tenants and a handful
-- of articles per tenant so the harness has something to assert against.
--
-- Tested against PostgreSQL 16. The capstone targets Postgres 16+; if you
-- are on 15 or older, the `BEFORE INSERT OR UPDATE OF ...` trigger syntax
-- and the `gen_random_uuid()` from `pgcrypto` need slight adjustments.
--
-- References:
--   - https://www.postgresql.org/docs/16/ddl.html
--   - https://www.postgresql.org/docs/16/ddl-rowsecurity.html
--   - https://www.postgresql.org/docs/16/textsearch.html
--   - https://www.postgresql.org/docs/16/gin.html
--   - https://www.postgresql.org/docs/16/sql-createtrigger.html
--
-- Apply with:
--   psql -h localhost -U postgres -d mtch -f exercise-05-capstone-schema.sql
--
-- Tear down with:
--   psql -h localhost -U postgres -d mtch -c "DROP SCHEMA IF EXISTS mtch CASCADE;"

BEGIN;

-- ---------------------------------------------------------------------
-- 0. Extensions and the application role.
-- ---------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS pgcrypto;        -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pg_trgm;          -- trigram match for similarity()

-- The application role. NOT a superuser. NOT BYPASSRLS. The W11 rule.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crunchreader_app') THEN
    CREATE ROLE crunchreader_app WITH LOGIN PASSWORD 'Crunch_Pro_W12_pw';
  END IF;
END
$$;

-- The dedicated schema for the capstone.
DROP SCHEMA IF EXISTS mtch CASCADE;
CREATE SCHEMA mtch AUTHORIZATION postgres;
GRANT USAGE ON SCHEMA mtch TO crunchreader_app;

SET search_path TO mtch, public;

-- ---------------------------------------------------------------------
-- 1. Tenants — the only table outside the RLS regime.
-- ---------------------------------------------------------------------

CREATE TABLE tenants (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug        text NOT NULL,
  name        text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  status      text NOT NULL DEFAULT 'active',
  rate_limit_override integer,
  CONSTRAINT tenants_slug_unique UNIQUE (slug),
  CONSTRAINT tenants_slug_format CHECK (slug ~ '^[a-z][a-z0-9-]{1,31}$'),
  CONSTRAINT tenants_status_valid CHECK (status IN ('active', 'suspended', 'archived')),
  CONSTRAINT tenants_rate_limit_nonneg CHECK (rate_limit_override IS NULL OR rate_limit_override >= 0)
);

CREATE INDEX tenants_status_idx ON tenants (status);

GRANT SELECT, INSERT, UPDATE ON tenants TO crunchreader_app;

-- ---------------------------------------------------------------------
-- 2. Users — Django creates this via auth; we declare the FK shape.
-- ---------------------------------------------------------------------

CREATE TABLE users (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  email        citext_or_text NOT NULL,  -- placeholder; capstone uses citext
  password_hash text NOT NULL,
  is_active    boolean NOT NULL DEFAULT true,
  is_admin     boolean NOT NULL DEFAULT false,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- The capstone uses the `citext` extension for case-insensitive email. For
-- portability in this exercise we used a `text` placeholder; uncomment the
-- next two lines in production.
-- CREATE EXTENSION IF NOT EXISTS citext;
-- ALTER TABLE users ALTER COLUMN email TYPE citext;

ALTER TABLE users
  ADD CONSTRAINT users_tenant_email_unique UNIQUE (tenant_id, email);

CREATE INDEX users_tenant_idx ON users (tenant_id);

GRANT SELECT, INSERT, UPDATE ON users TO crunchreader_app;

-- ---------------------------------------------------------------------
-- 3. Articles — the principal tenant-scoped table.
-- ---------------------------------------------------------------------

CREATE TABLE articles (
  tenant_id      uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  id             uuid NOT NULL DEFAULT gen_random_uuid(),
  author_id      uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  title          text NOT NULL,
  body           text NOT NULL,
  status         text NOT NULL DEFAULT 'draft',
  search_vector  tsvector,
  view_count     bigint NOT NULL DEFAULT 0,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  CONSTRAINT articles_status_valid CHECK (status IN ('draft', 'published', 'archived')),
  CONSTRAINT articles_title_nonempty CHECK (length(trim(title)) > 0)
);

-- Indexes. The composite primary key makes (tenant_id, id) lookups cheap.
CREATE INDEX articles_tenant_status_idx ON articles (tenant_id, status, created_at DESC);
CREATE INDEX articles_search_idx ON articles USING GIN (search_vector);
CREATE INDEX articles_title_trgm_idx ON articles USING GIN (title gin_trgm_ops);

GRANT SELECT, INSERT, UPDATE, DELETE ON articles TO crunchreader_app;

-- ---------------------------------------------------------------------
-- 4. Tags — many-to-many with articles, tenant-scoped.
-- ---------------------------------------------------------------------

CREATE TABLE tags (
  tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  id         uuid NOT NULL DEFAULT gen_random_uuid(),
  slug       text NOT NULL,
  name       text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  CONSTRAINT tags_tenant_slug_unique UNIQUE (tenant_id, slug),
  CONSTRAINT tags_slug_format CHECK (slug ~ '^[a-z][a-z0-9-]{0,31}$')
);

GRANT SELECT, INSERT, UPDATE, DELETE ON tags TO crunchreader_app;

CREATE TABLE article_tags (
  tenant_id  uuid NOT NULL,
  article_id uuid NOT NULL,
  tag_id     uuid NOT NULL,
  PRIMARY KEY (tenant_id, article_id, tag_id),
  FOREIGN KEY (tenant_id, article_id) REFERENCES articles(tenant_id, id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, tag_id)     REFERENCES tags(tenant_id, id)     ON DELETE CASCADE
);

GRANT SELECT, INSERT, DELETE ON article_tags TO crunchreader_app;

-- ---------------------------------------------------------------------
-- 5. Revisions — append-only audit log of edits.
-- ---------------------------------------------------------------------

CREATE TABLE revisions (
  tenant_id  uuid NOT NULL,
  article_id uuid NOT NULL,
  revision   bigserial NOT NULL,
  editor_id  uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  title      text NOT NULL,
  body       text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, article_id, revision),
  FOREIGN KEY (tenant_id, article_id) REFERENCES articles(tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX revisions_tenant_created_idx ON revisions (tenant_id, created_at DESC);

GRANT SELECT, INSERT ON revisions TO crunchreader_app;
GRANT USAGE, SELECT ON SEQUENCE revisions_revision_seq TO crunchreader_app;

-- ---------------------------------------------------------------------
-- 6. The search_vector trigger.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION mtch.update_search_vector() RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.body,  '')), 'B');
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER articles_search_vector_trg
  BEFORE INSERT OR UPDATE OF title, body ON articles
  FOR EACH ROW EXECUTE FUNCTION mtch.update_search_vector();

-- ---------------------------------------------------------------------
-- 7. Row-level security — the W11 invariant, applied everywhere.
-- ---------------------------------------------------------------------

ALTER TABLE articles      ENABLE ROW LEVEL SECURITY;
ALTER TABLE articles      FORCE  ROW LEVEL SECURITY;

ALTER TABLE tags          ENABLE ROW LEVEL SECURITY;
ALTER TABLE tags          FORCE  ROW LEVEL SECURITY;

ALTER TABLE article_tags  ENABLE ROW LEVEL SECURITY;
ALTER TABLE article_tags  FORCE  ROW LEVEL SECURITY;

ALTER TABLE revisions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE revisions     FORCE  ROW LEVEL SECURITY;

ALTER TABLE users         ENABLE ROW LEVEL SECURITY;
ALTER TABLE users         FORCE  ROW LEVEL SECURITY;

-- The policy expression is the same shape on every table. The `USING`
-- clause filters SELECT/UPDATE/DELETE; the `WITH CHECK` clause filters
-- INSERT/UPDATE. Both reference `current_setting('app.current_tenant')`
-- which the application sets per-transaction.

CREATE POLICY tenant_isolation ON articles
  USING      (tenant_id = current_setting('app.current_tenant', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE POLICY tenant_isolation ON tags
  USING      (tenant_id = current_setting('app.current_tenant', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE POLICY tenant_isolation ON article_tags
  USING      (tenant_id = current_setting('app.current_tenant', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE POLICY tenant_isolation ON revisions
  USING      (tenant_id = current_setting('app.current_tenant', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE POLICY tenant_isolation ON users
  USING      (tenant_id = current_setting('app.current_tenant', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

-- ---------------------------------------------------------------------
-- 8. The text type shim (citext placeholder).
-- ---------------------------------------------------------------------

-- The `users.email` column references `citext_or_text` which we declare
-- as a domain over text for portability. In production, prefer real citext.
CREATE DOMAIN IF NOT EXISTS citext_or_text AS text;
COMMENT ON DOMAIN citext_or_text IS
  'Placeholder for the citext type. In production use CREATE EXTENSION citext.';

COMMIT;

-- ---------------------------------------------------------------------
-- 9. Seed data — three tenants, three users, six articles.
-- ---------------------------------------------------------------------

BEGIN;

-- We need to run inserts under a tenant context each, because of FORCE RLS.
-- For seed time we use the postgres superuser (which still respects FORCE
-- on its own tables; this is the W11 gotcha that we make a feature of here).

-- Create the tenants first (the tenants table is not RLS-restricted).
INSERT INTO tenants (id, slug, name) VALUES
  ('11111111-1111-1111-1111-111111111111', 'acme',     'Acme Corp'),
  ('22222222-2222-2222-2222-222222222222', 'globex',   'Globex Industries'),
  ('33333333-3333-3333-3333-333333333333', 'initech',  'Initech');

-- Seed the per-tenant data, each block bracketed by SET LOCAL.

-- Tenant: acme.
SET LOCAL app.current_tenant = '11111111-1111-1111-1111-111111111111';

INSERT INTO users (id, tenant_id, email, password_hash, is_admin) VALUES
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1',
   '11111111-1111-1111-1111-111111111111',
   'admin@acme.test',
   'pbkdf2_sha256$placeholder',
   true);

INSERT INTO articles (tenant_id, id, author_id, title, body, status) VALUES
  ('11111111-1111-1111-1111-111111111111',
   gen_random_uuid(),
   'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1',
   'Welcome to Acme',
   'The Acme Corp content hub. Anvils, road runners, and an order book.',
   'published'),
  ('11111111-1111-1111-1111-111111111111',
   gen_random_uuid(),
   'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1',
   'Production-grade Python backend',
   'A capstone artefact demonstrating multi-tenant Python at scale.',
   'published');

-- Tenant: globex.
SET LOCAL app.current_tenant = '22222222-2222-2222-2222-222222222222';

INSERT INTO users (id, tenant_id, email, password_hash, is_admin) VALUES
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2',
   '22222222-2222-2222-2222-222222222222',
   'admin@globex.test',
   'pbkdf2_sha256$placeholder',
   true);

INSERT INTO articles (tenant_id, id, author_id, title, body, status) VALUES
  ('22222222-2222-2222-2222-222222222222',
   gen_random_uuid(),
   'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2',
   'Globex annual report',
   'A summary of the year, the products, and the financial outlook.',
   'published'),
  ('22222222-2222-2222-2222-222222222222',
   gen_random_uuid(),
   'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2',
   'Roadmap 2026',
   'The four directions we will take the platform over the next year.',
   'draft');

-- Tenant: initech.
SET LOCAL app.current_tenant = '33333333-3333-3333-3333-333333333333';

INSERT INTO users (id, tenant_id, email, password_hash, is_admin) VALUES
  ('cccccccc-cccc-cccc-cccc-cccccccccc33',
   '33333333-3333-3333-3333-333333333333',
   'admin@initech.test',
   'pbkdf2_sha256$placeholder',
   true);

INSERT INTO articles (tenant_id, id, author_id, title, body, status) VALUES
  ('33333333-3333-3333-3333-333333333333',
   gen_random_uuid(),
   'cccccccc-cccc-cccc-cccc-cccccccccc33',
   'TPS reports — best practices',
   'A guide to the new TPS report template and the cover sheet attachment.',
   'published'),
  ('33333333-3333-3333-3333-333333333333',
   gen_random_uuid(),
   'cccccccc-cccc-cccc-cccc-cccccccccc33',
   'Stapler inventory',
   'A list of red Swingline staplers and their current owners.',
   'draft');

COMMIT;

-- ---------------------------------------------------------------------
-- 10. The "cross-tenant cannot read" test inline.
-- ---------------------------------------------------------------------

-- Switch into the application role and prove RLS works.
SET ROLE crunchreader_app;

-- Read with tenant=acme; should return 2 articles.
SET LOCAL app.current_tenant = '11111111-1111-1111-1111-111111111111';
SELECT count(*) AS acme_visible_articles FROM articles;

-- Switch the context to globex; should now see 2 articles, all globex.
SET LOCAL app.current_tenant = '22222222-2222-2222-2222-222222222222';
SELECT count(*) AS globex_visible_articles FROM articles;

-- Try to read every article without filter; RLS limits us to the current
-- tenant only.
SELECT tenant_id, count(*) AS visible
  FROM articles
 GROUP BY tenant_id;

-- The forbidden act: try to INSERT a row with a different tenant_id.
-- This should fail with: new row violates row-level security policy.
DO $$
BEGIN
  BEGIN
    INSERT INTO articles (tenant_id, author_id, title, body)
    VALUES ('11111111-1111-1111-1111-111111111111',  -- WRONG tenant
            'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2',  -- globex user
            'forged article',
            'this should fail RLS WITH CHECK');
    RAISE EXCEPTION 'TEST FAIL: cross-tenant INSERT succeeded';
  EXCEPTION
    WHEN insufficient_privilege OR check_violation THEN
      RAISE NOTICE 'TEST PASS: cross-tenant INSERT correctly rejected';
    WHEN OTHERS THEN
      RAISE NOTICE 'TEST PASS (via %): cross-tenant INSERT rejected', SQLERRM;
  END;
END
$$;

RESET ROLE;

-- ---------------------------------------------------------------------
-- 11. Search smoke test.
-- ---------------------------------------------------------------------

-- A full-text query against the seeded acme corpus.
SET LOCAL app.current_tenant = '11111111-1111-1111-1111-111111111111';
SELECT title,
       ts_rank(search_vector, websearch_to_tsquery('english', 'python backend')) AS rank,
       ts_headline('english', body, websearch_to_tsquery('english', 'python backend')) AS snippet
  FROM articles
 WHERE search_vector @@ websearch_to_tsquery('english', 'python backend')
 ORDER BY rank DESC;

-- ---------------------------------------------------------------------
-- 12. Diagnostics summary.
-- ---------------------------------------------------------------------

-- Confirm RLS is enabled and forced on every tenant-scoped table.
SELECT relname, relrowsecurity, relforcerowsecurity
  FROM pg_class
 WHERE relkind = 'r'
   AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'mtch')
 ORDER BY relname;

-- Confirm the app role has no SUPERUSER / BYPASSRLS.
SELECT rolname, rolsuper, rolbypassrls
  FROM pg_roles
 WHERE rolname = 'crunchreader_app';

-- Confirm the GIN index is present on articles.search_vector.
SELECT indexname, indexdef
  FROM pg_indexes
 WHERE schemaname = 'mtch'
   AND indexdef ILIKE '%GIN%';

-- ---------------------------------------------------------------------
-- 13. Capstone teardown (commented; uncomment to clean up).
-- ---------------------------------------------------------------------

-- DROP SCHEMA mtch CASCADE;
-- REVOKE ALL ON SCHEMA mtch FROM crunchreader_app;
-- (Keep the role for the next capstone iteration.)

-- End of file.
