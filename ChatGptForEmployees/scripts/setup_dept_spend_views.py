#!/usr/bin/env python3
"""
Creates department spend reporting views for the "Department Spend Reporting
Views (SQL)" PBI.

LiteLLM_SpendLogs is a line-item table -- one row per request with its own
spend, end_user (the Mongo _id LibreChat sends as the `user` field), and
startTime -- so weekly, monthly, and all-time department cost are the same
rows aggregated differently. This script ships that as two reusable views:

  v_spend_by_dept_week   period (Monday, REPORT_TIMEZONE) x department x
                          division -> total_spend, request_count
  v_spend_by_dept_month  same, period = first-of-month

Join path: LiteLLM_SpendLogs.end_user -> user_directory.user_id -> email ->
dept_map.email -> department/division (see sync_okta_attribution.py for how
those two bridge tables are populated). Both joins are LEFT JOINs and
dept_map is NOT filtered on is_active -- dept_map soft-deletes (not drops) a
user who leaves Okta specifically so their historical spend still resolves
to a department. department/division are COALESCEd to 'Unknown' so any
request whose end_user doesn't resolve through the bridge (unmapped user,
missing Okta profile fields) still shows up in the rollup instead of
silently disappearing under a NULL group.

startTime/endTime are `timestamp without time zone`, populated in UTC
(LiteLLM's internal convention, confirmed locally) -- not timezone-aware, so
naive date_trunc('week'/'month', startTime) would bucket on UTC calendar
days. Both views instead convert to REPORT_TIMEZONE explicitly via
`(startTime AT TIME ZONE 'UTC') AT TIME ZONE REPORT_TIMEZONE` before
date_trunc, so week/month boundaries land on that timezone's calendar days.
This is a single pinned, documented choice -- change REPORT_TIMEZONE below
and re-run (CREATE OR REPLACE VIEW is idempotent) if the reporting timezone
ever needs to change.

An all-time/running-total query (same join, no date_trunc) is documented
below as RUNNING_TOTAL_QUERY rather than shipped as a view, per this PBI's
acceptance criteria -- use it directly for ad-hoc/BI "since the beginning"
totals.

Usage:
  pip install -r requirements.txt
  python setup_dept_spend_views.py

Required environment variables (scripts/.env):
  DATABASE_URL   litellm Postgres connection string (already set)
"""

import os
import sys
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Pinned reporting timezone (see module docstring). Change here and re-run to
# repin -- CREATE OR REPLACE VIEW makes this idempotent.
REPORT_TIMEZONE = "America/New_York"

_JOIN = """
FROM "LiteLLM_SpendLogs" sl
LEFT JOIN user_directory ud ON ud.user_id = sl.end_user
LEFT JOIN dept_map dm ON dm.email = ud.email
"""

_LOCAL_START_TIME = f'(sl."startTime" AT TIME ZONE \'UTC\') AT TIME ZONE \'{REPORT_TIMEZONE}\''

DDL_WEEK_VIEW = f"""
CREATE OR REPLACE VIEW v_spend_by_dept_week AS
SELECT
    date_trunc('week', {_LOCAL_START_TIME}) AS period,
    COALESCE(dm.department, 'Unknown') AS department,
    COALESCE(dm.division, 'Unknown') AS division,
    SUM(sl.spend) AS total_spend,
    COUNT(*) AS request_count
{_JOIN}
GROUP BY 1, 2, 3;
"""

DDL_MONTH_VIEW = f"""
CREATE OR REPLACE VIEW v_spend_by_dept_month AS
SELECT
    date_trunc('month', {_LOCAL_START_TIME}) AS period,
    COALESCE(dm.department, 'Unknown') AS department,
    COALESCE(dm.division, 'Unknown') AS division,
    SUM(sl.spend) AS total_spend,
    COUNT(*) AS request_count
{_JOIN}
GROUP BY 1, 2, 3;
"""

# Documented, not shipped as a view (per PBI acceptance criteria) -- same
# join, no date_trunc, for ad-hoc all-time/running-total department cost.
RUNNING_TOTAL_QUERY = f"""
SELECT
    COALESCE(dm.department, 'Unknown') AS department,
    COALESCE(dm.division, 'Unknown') AS division,
    SUM(sl.spend) AS total_spend,
    COUNT(*) AS request_count
{_JOIN}
GROUP BY 1, 2;
"""


def main() -> int:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set.")
        return 1

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(DDL_WEEK_VIEW)
            cur.execute(DDL_MONTH_VIEW)
        conn.commit()
    finally:
        conn.close()

    log.info("Created/replaced view: v_spend_by_dept_week (period=week, tz=%s)", REPORT_TIMEZONE)
    log.info("Created/replaced view: v_spend_by_dept_month (period=month, tz=%s)", REPORT_TIMEZONE)
    log.info("All-time/running-total query (not a view, for ad-hoc use):\n%s", RUNNING_TOTAL_QUERY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
