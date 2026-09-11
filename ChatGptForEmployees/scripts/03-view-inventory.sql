-- Read-only, deterministic view-definition inventory (LiteLLM v1.99.0 review,
-- Follow-up 3 P2: "verify view definitions and query execution"). Replaces
-- the schema/name-only view list in REVIEW-AND-CUTOVER.md Step 3.5/8a with
-- captured definitions, so a view that keeps its name but changes its query
-- is detected, not just a missing/added view.
--
-- USAGE (read-only; makes no changes):
--   psql -X -v ON_ERROR_STOP=1 -v target_schemas=public,attribution -Atf ChatGptForEmployees/scripts/03-view-inventory.sql > views.txt
--
-- Each output row is exactly one line: 'VIEW|<schema>.<name>|<definition>',
-- ordered deterministically by schema.name. pg_get_viewdef(oid, true) returns
-- Postgres's own pretty-printed (multi-line) reconstruction of the view's
-- query -- real newlines inside that text are translated to the literal
-- two-character sequence '\n' (via chr(10) replacement) specifically so this
-- file stays one-manifest-row-per-text-line: a naive capture of the raw
-- pretty-printed text would embed real line breaks inside a single logical
-- row, which silently corrupts line-based diffing (Compare-Object/diff) by
-- making one view's definition look like several unrelated lines. This
-- preserves the full definition unambiguously while keeping two runs of this
-- file, against two different databases, directly diffable.
--
-- Compare two captures of this file (pre- and post-migration) with
-- Compare-Object / diff: any difference means a view was added, removed, or
-- had its definition changed and must be reconciled before the release gate.
-- This file only reports definitions; it does not execute any view's query
-- (see 04-view-execution-check.sql for that).

\set ON_ERROR_STOP on
SET search_path = pg_catalog;

SELECT 'VIEW|' || n.nspname || '.' || c.relname || '|' ||
       replace(pg_get_viewdef(c.oid, true), chr(10), '\n') AS manifest_row
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'v'
  AND n.nspname = ANY(string_to_array(:'target_schemas', ','))
ORDER BY 1;
