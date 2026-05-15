-- Exercise 5 — Postgres full-text search schema
--
-- Applies the table + extensions + indexes for Exercises 1 and 2. Idempotent:
-- safe to re-run; uses CREATE EXTENSION IF NOT EXISTS and DROP TABLE IF EXISTS.
--
-- Usage:
--     createdb cc_w10              -- once
--     psql -d cc_w10 -f exercise-05-postgres-fts.sql
--
-- Cited:
--     https://www.postgresql.org/docs/current/textsearch.html
--     https://www.postgresql.org/docs/current/pgtrgm.html

-- ---------------------------------------------------------------------------
-- 0. Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Optional: unaccent strips diacritics (Lætitia -> Laetitia). Not strictly
-- required for the exercises; useful when you want to combine FTS with
-- diacritic-insensitive trigram matching.
CREATE EXTENSION IF NOT EXISTS unaccent;


-- ---------------------------------------------------------------------------
-- 1. Drop and rebuild the table (development-only)
-- ---------------------------------------------------------------------------

DROP TABLE IF EXISTS articles_w10 CASCADE;

CREATE TABLE articles_w10 (
    id           bigserial PRIMARY KEY,
    title        text        NOT NULL,
    body         text        NOT NULL,
    author       text        NOT NULL,
    tags         text[]      NOT NULL DEFAULT '{}'::text[],
    published_at timestamptz NOT NULL DEFAULT now(),
    -- tsvector generated column with weighted title (A) and body (B).
    tsv          tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(body, '')),  'B')
    ) STORED
);


-- ---------------------------------------------------------------------------
-- 2. Indexes
-- ---------------------------------------------------------------------------

-- GIN index on the tsvector column — the main inverted index.
CREATE INDEX articles_w10_tsv_idx
    ON articles_w10
    USING GIN (tsv);

-- Trigram indexes on title (for the fuzzy fallback in Exercise 2).
CREATE INDEX articles_w10_title_trgm_idx
    ON articles_w10
    USING GIN (title gin_trgm_ops);

-- Optional: a trigram index on body if you want fuzzy fallback on body too.
-- Body indexes are larger (a 5 KB body produces ~5 000 trigrams); enable
-- only if your relevance harness shows you need it.
-- CREATE INDEX articles_w10_body_trgm_idx
--     ON articles_w10
--     USING GIN (body gin_trgm_ops);

-- An auxiliary B-tree on published_at for sort-by-recency queries.
CREATE INDEX articles_w10_published_at_idx
    ON articles_w10 (published_at DESC);

-- An auxiliary GIN on tags for tag-filter queries.
CREATE INDEX articles_w10_tags_idx
    ON articles_w10
    USING GIN (tags);


-- ---------------------------------------------------------------------------
-- 3. Sample queries (verify the schema is wired correctly)
-- ---------------------------------------------------------------------------

-- 3.1 - Inspect a sample tsvector.
--      Expected: lexemes 'python', 'async', 'gener' with weight labels.
-- SELECT tsv FROM articles_w10 LIMIT 1;

-- 3.2 - Confirm the GIN index is used.
-- EXPLAIN ANALYZE
-- SELECT id, title
-- FROM articles_w10
-- WHERE tsv @@ websearch_to_tsquery('english', 'python async');
-- Expected plan: "Bitmap Index Scan on articles_w10_tsv_idx".

-- 3.3 - The four query front-doors.
-- SELECT id, title, ts_rank_cd(tsv, websearch_to_tsquery('english', 'python async'), 32) AS score
--   FROM articles_w10
--   WHERE tsv @@ websearch_to_tsquery('english', 'python async')
--   ORDER BY score DESC LIMIT 25;

-- 3.4 - Trigram fuzzy on title.
-- SELECT id, title, similarity(title, 'pythn async') AS score
--   FROM articles_w10
--   WHERE title %% 'pythn async'
--   ORDER BY score DESC LIMIT 25;

-- 3.5 - Highlighted snippet via ts_headline.
-- SELECT id,
--        title,
--        ts_headline('english', body,
--                    websearch_to_tsquery('english', 'python async'),
--                    'StartSel=<em>,StopSel=</em>,MaxFragments=2,FragmentDelimiter=...') AS snippet
--   FROM articles_w10
--   WHERE tsv @@ websearch_to_tsquery('english', 'python async')
--   LIMIT 25;


-- ---------------------------------------------------------------------------
-- 4. Optional: a custom English configuration with the synonym dictionary
-- ---------------------------------------------------------------------------

-- Postgres ships the 'english' text-search configuration. For domain-specific
-- synonyms ('api' -> 'application programming interface'), build a custom
-- configuration. Out of scope for the exercises; left here for reference.
--
-- 1. Create a synonym file at $PGDATA/share/tsearch_data/cc_synonyms.syn:
--      api application programming interface
--      orm object relational mapper
-- 2. Then:
--      CREATE TEXT SEARCH DICTIONARY cc_syn_dict (
--          TEMPLATE = synonym,
--          SYNONYMS = cc_synonyms
--      );
--      CREATE TEXT SEARCH CONFIGURATION cc_english (COPY = english);
--      ALTER TEXT SEARCH CONFIGURATION cc_english
--          ALTER MAPPING FOR asciiword, word
--          WITH cc_syn_dict, english_stem;
-- 3. Use as: to_tsvector('cc_english', body).
--
-- The custom configuration plus a fresh ALTER TABLE ... GENERATED column
-- requires a full reindex. Defer this to a real domain-specific need.


-- ---------------------------------------------------------------------------
-- 5. Maintenance commands worth knowing
-- ---------------------------------------------------------------------------

-- ANALYZE refreshes statistics so the planner picks the GIN index.
ANALYZE articles_w10;

-- VACUUM (ANALYZE) for a busy table; required occasionally as GIN updates
-- leave "pending list" entries that need to be merged into the index.
-- VACUUM (ANALYZE) articles_w10;

-- pg_stat_user_indexes shows index usage. After a workload, query:
--   SELECT indexrelname, idx_scan, idx_tup_read
--   FROM pg_stat_user_indexes
--   WHERE schemaname='public' AND relname='articles_w10';
-- If idx_scan stays 0 for articles_w10_tsv_idx, the query is missing the
-- index (look at EXPLAIN).
