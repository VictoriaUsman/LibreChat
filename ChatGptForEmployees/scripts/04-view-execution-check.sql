-- Read-only view EXECUTION check (LiteLLM v1.99.0 review, Follow-up 3 P2:
-- "verify view definitions and query execution"). 03-view-inventory.sql
-- proves a view's definition is unchanged; it does not prove the view's
-- query still actually runs (a definition can be byte-identical and still
-- fail at execution time, e.g. if an underlying column it references was
-- retyped incompatibly by an unrelated migration). This file closes that gap
-- by actually running each view.
--
-- USAGE (read-only; makes no changes -- explicit READ ONLY transaction and a
-- statement timeout so a runaway view query cannot hang the maintenance
-- window or write anything):
--   psql -X -v ON_ERROR_STOP=1 -v target_schemas=public,attribution -f ChatGptForEmployees/scripts/04-view-execution-check.sql
--
-- ⚠️ A bare `SELECT count(*) FROM <view>` is NOT sufficient here and was
-- rejected after it was actually tried and shown to be wrong, not merely
-- assumed unsafe: Postgres inlines a view's definition into the outer query
-- and, because count(*) references none of the view's projected columns,
-- the planner proves those columns are unused and PRUNES their expressions
-- entirely -- confirmed with EXPLAIN VERBOSE against a view whose SELECT list
-- contained a cast that always fails (`CAST(email AS integer)` against
-- free-text email data): `count(*) FROM view` returned a row count
-- successfully, with no cast operation anywhere in the plan, silently
-- passing a broken view. This is a sharper version of the same mistake
-- Follow-up 3 already named for catalog enumeration/LIMIT 0 -- it is not
-- enough to select FROM the view; each projected expression must actually be
-- consumed by the outer query so the planner cannot prove it unnecessary to
-- evaluate.
--
-- The query below instead hashes the whole row (`string_agg(v::text, '')`,
-- the same md5-fingerprint technique already used for historical-data
-- comparison elsewhere in this program) so every output expression for every
-- row must be evaluated to produce the aggregate's result -- verified to
-- correctly fail (nonzero exit, no row content ever printed or logged) on
-- the same always-fails-cast fixture that the count(*)-only form silently
-- passed, and to correctly succeed, with a stable non-error hash, on an
-- unmodified view with zero rows and with populated rows.
--
-- Uses format('%I.%I', ...) (PostgreSQL identifier quoting) to build each
-- query safely regardless of case or special characters in schema/view
-- names, then \gexec to actually execute each generated statement. Because
-- \set ON_ERROR_STOP is on and \gexec runs inside the READ ONLY transaction
-- opened below, a failing or timed-out view query aborts the whole script
-- with a nonzero exit and rolls back cleanly -- exactly the "failures/
-- timeouts prevent release" behavior Follow-up 3 requires. Only a row count
-- and an opaque hash are ever selected or printed -- never the view's actual
-- row content -- so this cannot expose employee conversation content.

\set ON_ERROR_STOP on
BEGIN;
SET LOCAL search_path = pg_catalog;
SET LOCAL statement_timeout = '10s';
SET TRANSACTION READ ONLY;

SELECT format(
  'SELECT %L AS view_name, count(*) AS row_count, md5(coalesce(string_agg(v::text, ''''), ''__EMPTY__'')) AS row_hash FROM %I.%I v;',
  n.nspname || '.' || c.relname, n.nspname, c.relname
)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'v'
  AND n.nspname = ANY(string_to_array(:'target_schemas', ','))
ORDER BY 1
\gexec

COMMIT;
