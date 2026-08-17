#!/usr/bin/env python3
"""
Validates v_spend_by_dept_week / v_spend_by_dept_month against the
"Department Spend Reporting Views (SQL)" PBI.

This script depends on setup_dept_spend_views.py -- run it first.

What this script checks:
  1. Both views exist.
  2. Seeded spend rows for a known test user, in two different calendar
     months, land in the correct v_spend_by_dept_month period bucket with
     the correct summed spend (the PBI's "seed across two months, confirm
     each lands in the correct bucket" criterion).
  3. One of those rows lands in the correct v_spend_by_dept_week bucket
     (the Monday of its week, in REPORT_TIMEZONE).
  4. A spend row whose end_user matches no user_directory row still shows up
     in the rollup under department='Unknown' (proves the LEFT JOIN/COALESCE
     path, not a silent drop).

All test data is tagged with a `__test_fixture_dept_view_*__` sentinel
prefix (matching seed_cascade_test_fixtures.py's convention) and is deleted
at the end, success or failure, so the database is left as found.

Usage:
  pip install -r requirements.txt
  python validate_dept_spend_views.py

Required environment variables (same .env as setup_dept_spend_views.py):
  DATABASE_URL
"""

import os
import re
import sys
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import psycopg2
except ImportError:
    print("ERROR: psycopg2 package not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

# Single source of truth for the reporting timezone: reuse the same constant the
# views are built with, so this validator can't drift from setup_dept_spend_views
# and fail spuriously if the pinned zone changes.
try:
    from setup_dept_spend_views import REPORT_TIMEZONE
except ImportError:
    REPORT_TIMEZONE = "America/New_York"  # fallback; keep in sync with setup_dept_spend_views.py

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Must match sync_okta_attribution.py / setup_dept_spend_views.py. The bridge
# tables and the reporting views live outside `public` so LiteLLM's Prisma push
# can't drop them; "LiteLLM_SpendLogs" stays in `public` because it is Prisma's.
def _resolve_attribution_schema() -> str:
    """Normalize and validate the target schema. Must match
    sync_okta_attribution.py's copy -- see there for the full rationale. The
    lowercasing matters here specifically: the information_schema lookups below
    compare this string against catalog values, which Postgres stores
    down-folded."""
    name = os.environ.get("ATTRIBUTION_SCHEMA", "attribution").strip().lower()
    if name == "public" or not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise ValueError(
            f"ATTRIBUTION_SCHEMA={name!r} is invalid: must be a simple identifier "
            "and must not be `public` -- LiteLLM's Prisma push drops unrecognized "
            "objects in `public` on every container restart."
        )
    return name


ATTRIBUTION_SCHEMA = _resolve_attribution_schema()

if not DATABASE_URL:
    print("ERROR: Missing required environment variable: DATABASE_URL")
    sys.exit(1)

TEST_EMAIL = "__test_fixture_dept_view__@romtech.test"
TEST_USER_ID = "__test_fixture_dept_view_user__"
TEST_DEPARTMENT = "Engineering"
TEST_DIVISION = "Product"

# Mid-month, noon UTC -- safely away from week/month/DST boundaries in any
# timezone this view might ever be pinned to. Naive (no tzinfo): startTime is
# a `timestamp without time zone` column populated with naive-but-UTC wall
# clock values, and we want the exact value stored to be unambiguous rather
# than depend on the Postgres session's TimeZone setting during an implicit
# tz-aware-to-naive cast.
ROW_1_ID = "__test_fixture_dept_view_row_1__"
ROW_1_TIME = datetime(2026, 3, 15, 12, 0, 0)
ROW_1_SPEND = 1.230000

ROW_2_ID = "__test_fixture_dept_view_row_2__"
ROW_2_TIME = datetime(2026, 4, 15, 12, 0, 0)
ROW_2_SPEND = 4.560000

UNMAPPED_ROW_ID = "__test_fixture_dept_view_unmapped_row__"
UNMAPPED_END_USER = "__test_fixture_dept_view_unmapped_user__"
UNMAPPED_TIME = ROW_1_TIME
UNMAPPED_SPEND = 0.010000

FIXTURE_ROW_IDS = (ROW_1_ID, ROW_2_ID, UNMAPPED_ROW_ID)

passed = 0
failed = 0


def ok(label):
    global passed
    passed += 1
    print(f"  PASS  {label}")


def fail(label, detail=""):
    global failed
    failed += 1
    print(f"  FAIL  {label}")
    if detail:
        print(f"        {detail}")


def insert_spend_row(cur, request_id, end_user, spend, start_time):
    cur.execute(
        """
        INSERT INTO public."LiteLLM_SpendLogs"
            (request_id, call_type, spend, total_tokens, prompt_tokens,
             completion_tokens, model, "startTime", "endTime", end_user)
        VALUES (%s, 'completion', %s, 10, 7, 3, 'test-fixture-model', %s, %s, %s)
        ON CONFLICT (request_id) DO NOTHING
        """,
        (request_id, spend, start_time, start_time, end_user),
    )


def seed(conn):
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO {ATTRIBUTION_SCHEMA}.dept_map (email, department, division, is_active, updated_at)
            VALUES (%s, %s, %s, true, now())
            ON CONFLICT (email) DO UPDATE SET
                department = EXCLUDED.department,
                division = EXCLUDED.division,
                is_active = true,
                removed_at = NULL,
                updated_at = now()
            """,
            (TEST_EMAIL, TEST_DEPARTMENT, TEST_DIVISION),
        )
        cur.execute(
            f"""
            INSERT INTO {ATTRIBUTION_SCHEMA}.user_directory (user_id, email, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (user_id) DO UPDATE SET email = EXCLUDED.email, updated_at = now()
            """,
            (TEST_USER_ID, TEST_EMAIL),
        )
        insert_spend_row(cur, ROW_1_ID, TEST_USER_ID, ROW_1_SPEND, ROW_1_TIME)
        insert_spend_row(cur, ROW_2_ID, TEST_USER_ID, ROW_2_SPEND, ROW_2_TIME)
        insert_spend_row(cur, UNMAPPED_ROW_ID, UNMAPPED_END_USER, UNMAPPED_SPEND, UNMAPPED_TIME)
    conn.commit()


def cleanup(conn):
    # seed() commits its fixture rows, so they outlive any later failure. If a
    # test raised mid-transaction (e.g. the views don't exist yet), the
    # connection is in INFAILEDSQLTRANSACTION and every DELETE below would
    # raise InFailedSqlTransaction -- masking the real error AND skipping the
    # cleanup, leaving fixture rows in "LiteLLM_SpendLogs" permanently, where
    # they show up in the real department='Unknown' rollup. Roll back first so
    # cleanup always runs on a usable connection.
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            'DELETE FROM public."LiteLLM_SpendLogs" WHERE request_id = ANY(%s)',
            (list(FIXTURE_ROW_IDS),),
        )
        cur.execute(
            f"DELETE FROM {ATTRIBUTION_SCHEMA}.user_directory WHERE user_id = %s",
            (TEST_USER_ID,),
        )
        cur.execute(
            f"DELETE FROM {ATTRIBUTION_SCHEMA}.dept_map WHERE email = %s",
            (TEST_EMAIL,),
        )
    conn.commit()


print()
print("Department Spend Reporting Views Assessment")
print(f"  Test department/division: {TEST_DEPARTMENT} / {TEST_DIVISION}")
print()

conn = psycopg2.connect(DATABASE_URL)

try:
    # --- Test 1: views exist ---

    print("1. Views exist")
    with conn.cursor() as cur:
        for view in ("v_spend_by_dept_week", "v_spend_by_dept_month"):
            cur.execute(
                "SELECT 1 FROM information_schema.views "
                "WHERE table_schema = %s AND table_name = %s",
                (ATTRIBUTION_SCHEMA, view),
            )
            if cur.fetchone():
                ok(f'"{view}" exists')
            else:
                fail(f'"{view}" does not exist — run setup_dept_spend_views.py first')

    print()
    print("Seeding fixture rows (dept_map, user_directory, LiteLLM_SpendLogs)...")
    seed(conn)

    # --- Test 2: two-month bucketing ---

    print()
    print("2. Seeded rows across two months land in the correct v_spend_by_dept_month bucket")
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT period, total_spend FROM {ATTRIBUTION_SCHEMA}.v_spend_by_dept_month
            WHERE department = %s AND division = %s
            ORDER BY period
            """,
            (TEST_DEPARTMENT, TEST_DIVISION),
        )
        rows = cur.fetchall()

    if len(rows) != 2:
        fail(f"Expected 2 monthly period rows, got {len(rows)}", str(rows))
    else:
        (p1, s1), (p2, s2) = rows
        if p1.month != p2.month or p1.year != p2.year:
            if abs(s1 - ROW_1_SPEND) < 1e-9 or abs(s1 - ROW_2_SPEND) < 1e-9:
                ok(f"Two distinct month periods found: {p1} (spend={s1}), {p2} (spend={s2})")
            else:
                fail("Two distinct month periods found but spend doesn't match seeded values",
                     f"expected {ROW_1_SPEND} and {ROW_2_SPEND}, got {s1} and {s2}")
        else:
            fail("Both seeded rows landed in the same month bucket", str(rows))

    # --- Test 3: week bucketing ---

    print()
    print("3. Seeded row lands in the correct v_spend_by_dept_week bucket")
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT period, total_spend FROM {ATTRIBUTION_SCHEMA}.v_spend_by_dept_week
            WHERE department = %s AND division = %s
            ORDER BY period
            """,
            (TEST_DEPARTMENT, TEST_DIVISION),
        )
        week_rows = cur.fetchall()

    if len(week_rows) != 2:
        fail(f"Expected 2 weekly period rows (one per seeded row), got {len(week_rows)}", str(week_rows))
    else:
        period, spend = week_rows[0]
        if period.weekday() == 0:
            ok(f"Week period {period} correctly starts on a Monday (spend={spend})")
        else:
            fail(f"Week period {period} does not start on a Monday", f"weekday={period.weekday()}")

    # --- Test 4: unmapped user falls back to 'Unknown' ---

    print()
    print("4. Unmapped end_user shows up under department='Unknown' (no silent drop)")
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT total_spend FROM {ATTRIBUTION_SCHEMA}.v_spend_by_dept_month
            WHERE department = 'Unknown'
              AND period = date_trunc('month', (%s::timestamp AT TIME ZONE 'UTC') AT TIME ZONE '{REPORT_TIMEZONE}')
            """,
            (UNMAPPED_TIME,),
        )
        unknown_row = cur.fetchone()

    if unknown_row and unknown_row[0] is not None and unknown_row[0] >= UNMAPPED_SPEND - 1e-9:
        ok(f"Unmapped row surfaced under department='Unknown' (total_spend={unknown_row[0]})")
    else:
        fail("Unmapped row did not surface under department='Unknown'", str(unknown_row))

finally:
    print()
    print("Cleaning up fixture rows...")
    cleanup(conn)
    conn.close()

# --- Summary ---

print()
print("=" * 55)
total = passed + failed
print(f"Results: {passed}/{total} passed", "" if failed == 0 else f"— {failed} FAILED")

sys.exit(0 if failed == 0 else 1)
