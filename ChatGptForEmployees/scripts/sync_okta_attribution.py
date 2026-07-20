#!/usr/bin/env python3
"""
Syncs Okta -> Postgres attribution tables for the
"Build the Okta->Postgres Attribution Tables & Sync Job" PBI.

LibreChat sends the Mongo user _id (not an email) as the OpenAI-compatible
`user` field on every LiteLLM request (LibreChat/packages/api/src/endpoints/
custom/initialize.ts:169), so LiteLLM_SpendLogs.end_user is keyed by an opaque
ObjectId. Rather than fork LibreChat to change what it sends, this script
populates two small lookup tables in the existing `litellm` Postgres database
so a report can join _id -> email -> department/division with plain SQL:

  dept_map        email (PK) -> department, division, is_active, removed_at.
                  Source: Okta Users API. Full refresh: users no longer
                  returned by Okta are soft-deleted (is_active=false,
                  removed_at=now()), not dropped -- so historical spend rows
                  for a departed employee still resolve to a department.
  user_directory  user_id (PK, Mongo _id as text) -> email.
                  Source: Mongo/Cosmos `users` collection. Upsert-only.

Each table is synced independently, one Postgres transaction per table, only
after its full source fetch has succeeded -- so a failure in Okta (bad token,
API outage) cannot touch user_directory, a failure in Mongo cannot touch
dept_map, and neither failure can partially write its own table.

Deployed as a twice-weekly ACA Job (Tue/Fri, see jobs.bicep); this script is
also safe to run manually / via any external scheduler. Each source's fetch
is retried with exponential backoff (SYNC_RETRY_ATTEMPTS total tries, default
4: initial + 3 retries at ~1/4/16 min) before that source is given up on for
the run. Every run -- success or final failure -- writes exactly one row to
sync_run_log and emits a SYNC_SUMMARY line to stdout, so a run's outcome is
queryable in Postgres and visible in Log Analytics without touching Azure's
job-execution history.

Key Vault secret names for later Bicep wiring (mirrors okta-setup.md's OIDC
secret convention, kv-romtech-<env>):
  ChatGptForEmployeesDev-OktaApiToken
  ChatGptForEmployeesTest-OktaApiToken
  ChatGptForEmployeesProd-OktaApiToken

Usage:
  pip install -r requirements.txt
  python sync_okta_attribution.py

Required environment variables (scripts/.env):
  DATABASE_URL      litellm Postgres connection string (already set)
  OKTA_ORG_URL      e.g. https://romtech.okta.com
  OKTA_API_TOKEN    Okta API token, sent as `Authorization: SSWS {token}`
  MONGO_URI         MongoDB connection string (already set)

Optional:
  DEPT_MAP_MIN_RATIO         default 0.5 -- abort the dept_map sync if the
                              Okta fetch returns fewer than this fraction of
                              the table's current active row count.
  USER_DIRECTORY_MIN_RATIO   default 0.5 -- same guard for user_directory.
  SYNC_RETRY_ATTEMPTS        default 4 -- total tries per source (initial +
                              retries) before that source's fetch is given up
                              on for this run.
  SYNC_RETRY_BASE_DELAY_SECONDS  default 60 -- delay before retry N is
                              base * 4**N seconds (60/240/960s by default,
                              i.e. ~1/4/16 min). Lower this for fast local
                              testing of the retry path.

Exit codes:
  0 -- both sources synced successfully (after retries if needed)
  1 -- at least one source failed after exhausting retries, OR a safety guard
       aborted a write (empty/below-MIN_RATIO fetch -- a deliberately-skipped
       sync is reported as failed so the alert fires); see per-source log lines
       and the sync_run_log.detail column for which. sync_run_log still gets
       exactly one row either way, with status='failed' on any non-success.
"""

import os
import sys
import time
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2
import requests
from pymongo import MongoClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
OKTA_ORG_URL = os.environ.get("OKTA_ORG_URL", "").rstrip("/")
OKTA_API_TOKEN = os.environ.get("OKTA_API_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/LibreChat")

DEPT_MAP_MIN_RATIO = float(os.environ.get("DEPT_MAP_MIN_RATIO", "0.5"))
USER_DIRECTORY_MIN_RATIO = float(os.environ.get("USER_DIRECTORY_MIN_RATIO", "0.5"))

SYNC_RETRY_ATTEMPTS = int(os.environ.get("SYNC_RETRY_ATTEMPTS", "4"))
SYNC_RETRY_BASE_DELAY_SECONDS = float(os.environ.get("SYNC_RETRY_BASE_DELAY_SECONDS", "60"))

DDL = """
CREATE TABLE IF NOT EXISTS dept_map (
    email       TEXT PRIMARY KEY,
    department  TEXT,
    division    TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT true,
    removed_at  TIMESTAMPTZ,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS user_directory (
    user_id     TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sync_run_log (
    id                     BIGSERIAL PRIMARY KEY,
    run_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    status                 TEXT NOT NULL,
    dept_map_synced        INTEGER,
    user_directory_synced  INTEGER,
    duration_seconds       NUMERIC(10,3) NOT NULL,
    detail                 TEXT
);
CREATE INDEX IF NOT EXISTS idx_sync_run_log_run_at ON sync_run_log (run_at);
"""


def get_db_name(uri: str) -> str:
    return uri.rstrip("/").split("/")[-1].split("?")[0] or "LibreChat"


def ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()
    log.info("DDL applied: dept_map, user_directory, sync_run_log present.")


class ConfigError(Exception):
    """Raised for missing/invalid required configuration. Not retried --
    retrying a source that's simply unconfigured just delays the same
    failure by ~21 minutes for no benefit."""


class SyncAbort(Exception):
    """Raised when a source fetch SUCCEEDS but a safety guard refuses to write
    (empty result, or fewer rows than MIN_RATIO of the current table). This is
    a deliberately-skipped write, not a healthy no-op: the run is recorded
    status='failed' with a non-zero exit so the twice-weekly failure alert
    fires and the stale table gets investigated -- rather than the old
    behaviour of returning 0 and reporting status='success'."""


def run_with_retries(fn, label: str):
    """Calls fn() with exponential backoff: SYNC_RETRY_ATTEMPTS total tries,
    delay = SYNC_RETRY_BASE_DELAY_SECONDS * 4**n before retry n (default
    60s/240s/960s, i.e. ~1/4/16 min). ConfigError fails fast, no retry.
    Re-raises the final attempt's exception once all attempts are exhausted."""
    last_exc = None
    for attempt in range(SYNC_RETRY_ATTEMPTS):
        try:
            return fn()
        except ConfigError:
            raise
        except Exception as e:
            last_exc = e
            if attempt < SYNC_RETRY_ATTEMPTS - 1:
                delay = SYNC_RETRY_BASE_DELAY_SECONDS * (4 ** attempt)
                log.warning(
                    "%s attempt %d/%d failed: %s -- retrying in %.0fs",
                    label, attempt + 1, SYNC_RETRY_ATTEMPTS, e, delay,
                )
                time.sleep(delay)
    raise last_exc


def fetch_okta_users() -> list:
    """GET all Okta users via the list endpoint, following the Link:
    rel="next" header until exhausted. Raises on any non-200 response --
    the caller treats that as a fetch failure and skips dept_map entirely."""
    if not OKTA_ORG_URL or not OKTA_API_TOKEN:
        raise ConfigError("OKTA_ORG_URL / OKTA_API_TOKEN not set")

    url = f"{OKTA_ORG_URL}/api/v1/users?limit=200"
    headers = {"Authorization": f"SSWS {OKTA_API_TOKEN}", "Accept": "application/json"}
    users = []

    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"Okta API returned HTTP {resp.status_code}: {resp.text[:200]}")

        for record in resp.json():
            profile = record.get("profile", {}) or {}
            email = profile.get("email") or profile.get("login")
            if not email:
                continue
            users.append({
                "email": email,
                "department": profile.get("department"),
                "division": profile.get("division"),
            })

        url = None
        for link in requests.utils.parse_header_links(resp.headers.get("Link", "")):
            if link.get("rel") == "next":
                url = link.get("url")

    return users


def fetch_mongo_users() -> list:
    """Reads (user_id, email) pairs from the Mongo/Cosmos `users` collection."""
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    try:
        db = client[get_db_name(MONGO_URI)]
        users = []
        for doc in db.users.find({}, {"_id": 1, "email": 1}):
            if not doc.get("email"):
                continue
            users.append({"user_id": str(doc["_id"]), "email": doc["email"]})
        return users
    finally:
        client.close()


def sync_dept_map(conn, users: list) -> int:
    """Full refresh, one transaction: upsert every fetched user active, then
    soft-delete (is_active=false, removed_at=now()) any previously-active row
    not present in this fetch. Aborts without writing if the fetch looks
    suspiciously empty relative to the table's current active row count."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dept_map WHERE is_active")
        current_active = cur.fetchone()[0]

    if not users:
        raise SyncAbort("Okta fetch returned 0 users -- nothing written.")
    if current_active > 0 and len(users) < current_active * DEPT_MAP_MIN_RATIO:
        raise SyncAbort(
            "Okta fetch returned %d users, below %.0f%% of the %d currently active "
            "row(s) -- likely a bad token/org or partial outage, not a genuine mass "
            "departure. Nothing written." % (
                len(users), DEPT_MAP_MIN_RATIO * 100, current_active)
        )

    emails = [u["email"] for u in users]
    try:
        with conn.cursor() as cur:
            for u in users:
                cur.execute(
                    """
                    INSERT INTO dept_map (email, department, division, is_active, removed_at, updated_at)
                    VALUES (%s, %s, %s, true, NULL, now())
                    ON CONFLICT (email) DO UPDATE SET
                        department = EXCLUDED.department,
                        division = EXCLUDED.division,
                        is_active = true,
                        removed_at = NULL,
                        updated_at = now()
                    """,
                    (u["email"], u["department"], u["division"]),
                )
            cur.execute(
                """
                UPDATE dept_map SET is_active = false, removed_at = now()
                WHERE is_active = true AND email <> ALL(%s)
                """,
                (emails,),
            )
            removed = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    log.info("dept_map synced: %d user(s) upserted, %d soft-deleted.", len(users), removed)
    return len(users)


def sync_user_directory(conn, users: list) -> int:
    """Upsert-only, one transaction. Aborts without writing if the fetch
    looks suspiciously empty relative to the table's current row count."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM user_directory")
        current_count = cur.fetchone()[0]

    if not users:
        raise SyncAbort("Mongo fetch returned 0 users -- nothing written.")
    if current_count > 0 and len(users) < current_count * USER_DIRECTORY_MIN_RATIO:
        raise SyncAbort(
            "Mongo fetch returned %d users, below %.0f%% of the %d currently stored "
            "row(s) -- likely a bad connection/wrong database, not a genuine mass "
            "deletion. Nothing written." % (
                len(users), USER_DIRECTORY_MIN_RATIO * 100, current_count)
        )

    try:
        with conn.cursor() as cur:
            for u in users:
                cur.execute(
                    """
                    INSERT INTO user_directory (user_id, email, updated_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (user_id) DO UPDATE SET
                        email = EXCLUDED.email,
                        updated_at = now()
                    """,
                    (u["user_id"], u["email"]),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    log.info("user_directory synced: %d user(s) upserted.", len(users))
    return len(users)


def main() -> int:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set.")
        return 1

    start = time.monotonic()
    status = "failed"
    duration = 0.0
    dept_map_synced = None
    user_directory_synced = None
    detail_parts = []

    # Keepalives: the connection is opened up front (we must be able to write
    # the sync_run_log row even if BOTH fetches fail) but then sits idle across
    # each source's up-to-~21 min retry backoff. TCP keepalives stop an idle
    # NAT/firewall/server timeout from silently dropping it before the writes.
    conn = psycopg2.connect(
        DATABASE_URL,
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
    )
    ok = True
    try:
        ensure_tables(conn)

        log.info("--- Okta -> dept_map ---")
        try:
            okta_users = run_with_retries(fetch_okta_users, "Okta fetch")
            dept_map_synced = sync_dept_map(conn, okta_users)
        except Exception as e:
            log.error("dept_map sync failed (retries exhausted or safety-guard abort), table left untouched: %s", e)
            ok = False
            detail_parts.append(f"dept_map: {e}")

        log.info("--- Mongo -> user_directory ---")
        try:
            mongo_users = run_with_retries(fetch_mongo_users, "Mongo fetch")
            user_directory_synced = sync_user_directory(conn, mongo_users)
        except Exception as e:
            log.error("user_directory sync failed (retries exhausted or safety-guard abort), table left untouched: %s", e)
            ok = False
            detail_parts.append(f"user_directory: {e}")

        duration = time.monotonic() - start
        status = "success" if ok else "failed"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sync_run_log
                    (status, dept_map_synced, user_directory_synced, duration_seconds, detail)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (status, dept_map_synced, user_directory_synced, duration,
                 "; ".join(detail_parts) or None),
            )
        conn.commit()
    finally:
        conn.close()

    log.info(
        "SYNC_SUMMARY status=%s dept_map_synced=%s user_directory_synced=%s duration_s=%.1f",
        status, dept_map_synced, user_directory_synced, duration,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
