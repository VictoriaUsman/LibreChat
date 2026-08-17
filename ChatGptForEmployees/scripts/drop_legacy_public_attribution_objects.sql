-- Teardown for the pre-`attribution`-schema attribution objects.
--
-- WHY
-- dept_map, user_directory, sync_run_log and the v_spend_by_dept_* views used
-- to be created in `public`. LiteLLM runs `prisma db push --accept-data-loss`
-- against this same database on every container start, and Prisma drops
-- objects in the schema it manages that aren't in its schema.prisma -- so it
-- was silently deleting them between the sync job's Tue/Fri runs. Confirmed in
-- Prod 2026-08-17: the job logged status=success and exited 0 on all seven
-- runs while Prisma logged "You are about to drop the `user_directory` table,
-- which is not empty (4 rows)" at each container restart.
--
-- They now live in the `attribution` schema, which Prisma does not manage.
--
-- WHY THIS TEARDOWN IS NOT OPTIONAL
-- Prod's `public` copies are already gone (Prisma dropped them 2026-08-15), so
-- this is a no-op there. Dev and Test still hold POPULATED `public` copies, and
-- the default search_path is "$user", public. An unqualified
--     SELECT * FROM v_spend_by_dept_month
-- therefore still resolves in Dev/Test -- to the stale view over stale tables,
-- returning plausible frozen numbers rather than an error. That is strictly
-- worse than failing. Do not wait for Prisma to clean these up: Prisma drops
-- tables, and an orphaned view over a dropped table either blocks the drop or
-- lingers as a broken object.
--
-- ROLLOUT ORDER, per environment (Dev -> Test -> Prod):
--   1. Deploy the updated jobs image.
--   2. Run sync_okta_attribution.py (scheduled Tue/Fri 05:00 UTC, or trigger
--      manually). This creates the `attribution` schema and the three tables.
--      Confirm: SELECT count(*) FROM attribution.user_directory;
--   3. Run setup_dept_spend_views.py. It now refuses to run before step 2
--      rather than failing with a bare UndefinedTable.
--   4. Run THIS script.
--
-- Steps 2 and 3 must not be reordered: the views join against the bridge
-- tables, so CREATE VIEW fails if they don't exist yet.
--
-- Idempotent; safe to re-run. Views are dropped before tables so the drop
-- order can't leave a broken dependent object behind.

BEGIN;

DROP VIEW IF EXISTS public.v_spend_by_dept_week;
DROP VIEW IF EXISTS public.v_spend_by_dept_month;

DROP TABLE IF EXISTS public.dept_map;
DROP TABLE IF EXISTS public.user_directory;
DROP TABLE IF EXISTS public.sync_run_log;

COMMIT;

-- Verify nothing is left behind in `public` and everything is present in
-- `attribution` (pg_tables/pg_views are not privilege-filtered, unlike
-- information_schema):
--
--   SELECT schemaname, tablename FROM pg_tables
--    WHERE tablename IN ('dept_map','user_directory','sync_run_log');
--   SELECT schemaname, viewname  FROM pg_views
--    WHERE viewname LIKE 'v_spend_by_dept%';
--
-- Expected: every row reports schemaname = 'attribution'.
