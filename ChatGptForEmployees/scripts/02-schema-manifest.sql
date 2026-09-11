-- Read-only, deterministic catalog manifest for baseline/target schema
-- comparison (LiteLLM v1.99.0 review, Follow-up 2 P1: "implement complete
-- baseline and target-schema comparison"). This replaces the old four-table/
-- one-index spot checks in REVIEW-AND-CUTOVER.md Step 5 and Step 8a with a
-- full catalog manifest that can be diffed byte-for-byte between two
-- databases.
--
-- SCOPE: ordinary tables (relkind='r') in the schema(s) passed via
-- -v target_schemas only -- this is deliberately vendor-managed-only (LiteLLM's
-- own Prisma-controlled tables live in `public`). Views are NOT included here
-- (see 03-view-inventory.sql / 04-view-execution-check.sql) and no other
-- schema is touched unless explicitly passed -- so `attribution` (a custom,
-- non-Prisma schema) is never diffed against the pinned image's expected
-- schema by this script when it is invoked with target_schemas=public. Run
-- this same file a second time with -v target_schemas=attribution to
-- inventory and preserve it on its own terms instead: capture that output
-- before remediation and again after all migrations, then diff the two
-- captures against EACH OTHER (never against the public-schema/pinned-image
-- reference) -- proving attribution's own tables/constraints/indexes were
-- left untouched by the LiteLLM migration, not that they match LiteLLM's
-- Prisma schema (they never will, and are not supposed to).
--
-- USAGE (read-only; makes no changes):
--   psql -X -v ON_ERROR_STOP=1 -v target_schemas=public -Atf ChatGptForEmployees/scripts/02-schema-manifest.sql > manifest.txt
--
-- Comma-separate target_schemas for more than one schema in one run, e.g.
-- -v target_schemas=public,attribution. Output is one line per catalog fact,
-- each tagged by record type (TABLE/COLUMN/CONSTRAINT/INDEX) and ordered
-- deterministically (by schema.table, then name) -- two runs of this exact
-- file against two different databases produce directly diffable output
-- (`Compare-Object`/`diff`), with no dependency on row arrival order.
--
-- What each record type actually detects:
--   TABLE       -- a table added or removed entirely.
--   COLUMN      -- a column added/removed, or an existing column's type
--                  (including modifiers, e.g. varchar(255) vs varchar(64)),
--                  nullability, or default expression changed. Deliberately
--                  does NOT detect a column's physical ordinal position
--                  changing (see below) -- that is not a schema-equivalence
--                  defect, it is the expected shape of an ADD COLUMN-based
--                  remediation vs. an inline CREATE TABLE reference.
--   CONSTRAINT  -- a PRIMARY KEY/UNIQUE/FOREIGN KEY/CHECK constraint added,
--                  removed, or changed -- pg_get_constraintdef() renders the
--                  exact DDL text Postgres itself would emit (including a
--                  foreign key's ON DELETE/ON UPDATE actions), so an
--                  equivalent constraint always produces byte-identical text
--                  regardless of which database generated it.
--   INDEX       -- an index added, removed, redefined, or left invalid
--                  (indisvalid=false catches a CREATE INDEX CONCURRENTLY that
--                  failed partway, e.g. 20260415120000_health_check_latest_
--                  per_model_index).
--
-- This file makes NO changes and takes no locks beyond ordinary catalog
-- reads. Validated against isolated Docker fixtures, including deliberately
-- mismatched ones (missing column, wrong default, missing unique index,
-- missing foreign key), AND against an append-column-vs-inline-declaration
-- positive fixture (proving a logically-equivalent column added via ALTER
-- TABLE ... ADD COLUMN, at a different physical position than an inline
-- CREATE TABLE reference, now correctly passes) -- see
-- REVIEW-AND-CUTOVER.md, "Follow-up 2: complete baseline and target-schema
-- comparison" and "Working-changes follow-up corrections", for the recorded
-- runs.

\set ON_ERROR_STOP on
SET search_path = pg_catalog;

-- TABLE: one row per ordinary table.
SELECT 'TABLE|' || n.nspname || '.' || c.relname AS manifest_row
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname = ANY(string_to_array(:'target_schemas', ','))
ORDER BY 1;

-- COLUMN: schema.table | column | canonical type (with modifiers) | nullable
-- (true/false) | default expression (or literal <none>).
--
-- Deliberately EXCLUDES physical ordinal position (pg_attribute.attnum) from
-- the equivalence key (corrected per the `89c57d0` working-changes follow-up,
-- Finding 3): the vendor baseline declares a column like `sso_user_id` inline
-- in its CREATE TABLE at whatever position the schema.prisma model puts it,
-- but the real remediation script (01-baseline-remediation.sql) catches an
-- old, pre-Prisma database up to that same schema using `ALTER TABLE ... ADD
-- COLUMN`, which always appends the column physically last -- a different
-- attnum even when the column's name, type, nullability, default, and every
-- constraint/index referencing it are identical. Comparing attnum as part of
-- equivalence would reject that valid, intentional remediation pattern.
-- Columns are still identified and ordered by name (a.attname), which keeps
-- output deterministic without depending on physical position; meaningful
-- column ORDER inside a composite index/constraint is unaffected by this and
-- remains checked below, because pg_get_indexdef()/pg_get_constraintdef()
-- encode that order by column name, not by raw attnum.
SELECT 'COLUMN|' || n.nspname || '.' || c.relname || '|' || a.attname || '|' ||
       format_type(a.atttypid, a.atttypmod) || '|' ||
       (NOT a.attnotnull) || '|' ||
       coalesce(pg_get_expr(d.adbin, d.adrelid), '<none>') AS manifest_row
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE c.relkind = 'r'
  AND n.nspname = ANY(string_to_array(:'target_schemas', ','))
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY 1;

-- CONSTRAINT: schema.table | constraint name | canonical constraint DDL
-- (PRIMARY KEY / UNIQUE / FOREIGN KEY incl. ON DELETE/ON UPDATE / CHECK).
SELECT 'CONSTRAINT|' || n.nspname || '.' || t.relname || '|' || con.conname ||
       '|' || pg_get_constraintdef(con.oid) AS manifest_row
FROM pg_constraint con
JOIN pg_class t ON t.oid = con.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE t.relkind = 'r'
  AND n.nspname = ANY(string_to_array(:'target_schemas', ','))
ORDER BY 1;

-- INDEX: schema.table | index name | canonical index DDL | validity. Includes
-- indexes backing a UNIQUE/PRIMARY KEY constraint (already listed above too,
-- under CONSTRAINT) as well as plain non-constraint indexes -- deliberate
-- redundancy so a constraint-backing index that is separately marked invalid
-- is still caught even if its CONSTRAINT row alone wouldn't show that.
SELECT 'INDEX|' || n.nspname || '.' || t.relname || '|' || ic.relname || '|' ||
       pg_get_indexdef(i.indexrelid) || '|valid=' || i.indisvalid AS manifest_row
FROM pg_index i
JOIN pg_class ic ON ic.oid = i.indexrelid
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE t.relkind = 'r'
  AND n.nspname = ANY(string_to_array(:'target_schemas', ','))
ORDER BY 1;
