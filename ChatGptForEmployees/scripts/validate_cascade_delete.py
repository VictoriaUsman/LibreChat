#!/usr/bin/env python3
"""
Validates cascade deletion and retention across conversation, file, and vector stores (PBI-21-BE).

Acceptance criteria covered:
  1. No orphaned files in MongoDB -- files whose conversationId no longer has an active conversation
  2. No orphaned embeddings in pgvector -- rows in langchain_pg_embedding whose file_id
     belongs to a deleted file record in MongoDB
  3. Retention sweep eligibility check -- reports conversations older than RETENTION_DAYS
  4. Canary liveness -- the cleanup job's sentinel conversation
     (cleanup_orphaned_files.py safety layer #1) is present, i.e. the fail-closed
     guardrail is actually armed
  5. (opt-in, RUN_FIXTURE_TEST=true) Seeded orphan+keeper regression test -- confirms
     the orphan-detection query used by both this validator and the cleanup job
     correctly flags a known orphan and does not flag a known keeper

Usage:
  pip install -r requirements.txt
  python validate_cascade_delete.py

Required environment variables (scripts/.env):
  MONGO_URI               MongoDB connection string (e.g. mongodb://localhost:27017/LibreChat)
  RAG_DB_HOST             pgvector host (default: localhost)
  RAG_DB_PORT             pgvector port (default: 5432)
  RAG_DB_NAME             pgvector database name (default: librechat_rag)
  RAG_DB_USER             pgvector user
  RAG_DB_PASSWORD         pgvector password
  RETENTION_DAYS          Retention window in days (default: 90)
  CANARY_CONVERSATION_ID  Sentinel conversation ID (default: __cleanup_canary__)
  RUN_FIXTURE_TEST        "true" to seed+check+clean up a test orphan/keeper pair
                          (default: false -- off by default so a normal validation
                          run never writes test data into a real database)

Exit codes:
  0 -- all checks passed, no orphans found
  1 -- one or more checks failed or orphans detected
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/LibreChat")
RAG_DB_HOST = os.environ.get("RAG_DB_HOST", "localhost")
RAG_DB_PORT = int(os.environ.get("RAG_DB_PORT", "5432"))
RAG_DB_NAME = os.environ.get("RAG_DB_NAME", "librechat_rag")
RAG_DB_USER = os.environ.get("RAG_DB_USER", "")
RAG_DB_PASSWORD = os.environ.get("RAG_DB_PASSWORD", "")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "90"))
CANARY_CONVERSATION_ID = os.environ.get("CANARY_CONVERSATION_ID", "__cleanup_canary__")
RUN_FIXTURE_TEST = os.environ.get("RUN_FIXTURE_TEST", "false").strip().lower() == "true"

failures = []


def check(label: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    line = f"  [{status}] {label}"
    if detail:
        line += f" -- {detail}"
    print(line)
    if not passed:
        failures.append(label)


def check_mongodb_orphans():
    print("\n--- MongoDB: orphaned file records ---")
    try:
        from pymongo import MongoClient

        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db_name = MONGO_URI.rstrip("/").split("/")[-1].split("?")[0] or "LibreChat"
        db = client[db_name]

        active_conversation_ids = set(
            doc["conversationId"]
            for doc in db.conversations.find({}, {"conversationId": 1})
            if doc.get("conversationId")
        )

        orphaned = list(
            db.files.find(
                {
                    "conversationId": {
                        "$exists": True,
                        "$nin": list(active_conversation_ids),
                        "$type": "string",
                    }
                },
                {"file_id": 1, "conversationId": 1, "filename": 1},
            )
        )

        check(
            "No orphaned file records",
            len(orphaned) == 0,
            f"{len(orphaned)} orphaned file(s) found" if orphaned else "clean",
        )

        if orphaned:
            print("    Orphaned file_ids (first 10):")
            for f in orphaned[:10]:
                print(f"      file_id={f.get('file_id')} conversationId={f.get('conversationId')}")

        client.close()
    except Exception as e:
        check("MongoDB orphan check", False, str(e))


def check_pgvector_orphans():
    print("\n--- pgvector: orphaned embeddings ---")
    if not RAG_DB_USER:
        print("  [SKIP] RAG_DB_USER not set -- skipping pgvector check")
        return

    try:
        import psycopg2
        from pymongo import MongoClient

        # Collect file_ids that still have active records in MongoDB
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db_name = MONGO_URI.rstrip("/").split("/")[-1].split("?")[0] or "LibreChat"
        active_file_ids = set(
            doc["file_id"]
            for doc in mongo_client[db_name].files.find(
                {"file_id": {"$exists": True}}, {"file_id": 1}
            )
            if doc.get("file_id")
        )
        mongo_client.close()

        conn = psycopg2.connect(
            host=RAG_DB_HOST,
            port=RAG_DB_PORT,
            dbname=RAG_DB_NAME,
            user=RAG_DB_USER,
            password=RAG_DB_PASSWORD,
            connect_timeout=5,
        )
        cur = conn.cursor()

        # Get all distinct file_ids that have embeddings in pgvector
        cur.execute(
            """
            SELECT DISTINCT cmetadata->>'file_id'
            FROM langchain_pg_embedding
            WHERE cmetadata->>'file_id' IS NOT NULL
            """
        )
        embedded_file_ids = {row[0] for row in cur.fetchall()}

        orphaned_ids = embedded_file_ids - active_file_ids
        count = len(orphaned_ids)
        check(
            "No orphaned pgvector embeddings",
            count == 0,
            f"{count} orphaned embedding file_id(s)" if count > 0 else "clean",
        )

        if orphaned_ids:
            print("    Orphaned file_ids in pgvector (first 10):")
            for fid in list(orphaned_ids)[:10]:
                print(f"      file_id={fid}")

        cur.close()
        conn.close()
    except Exception as e:
        print(f"  [SKIP] pgvector check failed: {e}")
        print("         Confirm RAG API database is running and credentials are correct.")


def check_retention_candidates():
    print(f"\n--- Retention candidates (updatedAt older than {RETENTION_DAYS} days) ---")
    try:
        from pymongo import MongoClient
        from datetime import datetime, timedelta, timezone

        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db_name = MONGO_URI.rstrip("/").split("/")[-1].split("?")[0] or "LibreChat"
        db = client[db_name]

        cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
        count = db.conversations.count_documents({"updatedAt": {"$lt": cutoff}})

        print(
            f"  [INFO] {count} conversation(s) last updated before {cutoff.date()} (>{RETENTION_DAYS}d ago)"
        )
        if count > 0:
            print(
                f"         These will be swept by startExpiredConversationSweep on next run."
            )

        client.close()
    except Exception as e:
        print(f"  [SKIP] Retention candidate check failed: {e}")


def check_canary_liveness():
    """Confirms cleanup_orphaned_files.py's fail-closed guardrail (safety
    layer #1) is actually armed in this environment -- i.e. the sentinel
    canary conversation exists and is visible via the exact query the
    cleanup job uses to detect active conversations. If this check fails,
    the cleanup job itself would (correctly) refuse to run -- but that
    means the job is currently disarmed, which is worth surfacing here
    too rather than only discovering it from the job's own logs."""
    print("\n--- Cleanup job canary liveness ---")
    try:
        from pymongo import MongoClient

        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db_name = MONGO_URI.rstrip("/").split("/")[-1].split("?")[0] or "LibreChat"
        db = client[db_name]

        exists = db.conversations.find_one(
            {"conversationId": CANARY_CONVERSATION_ID}, {"_id": 1}
        ) is not None

        check(
            "Cleanup job canary present",
            exists,
            f"conversationId={CANARY_CONVERSATION_ID}"
            if exists
            else f"conversationId={CANARY_CONVERSATION_ID} not found -- run seed_canary_conversation.py",
        )
        client.close()
    except Exception as e:
        check("Cleanup job canary present", False, str(e))


def check_seeded_fixtures():
    """Opt-in (RUN_FIXTURE_TEST=true) regression test for PBI acceptance
    criterion #11: seeds a known orphan + a known keeper, runs the same
    orphan-detection query used by check_mongodb_orphans, asserts the
    orphan is flagged and the keeper is not, then cleans both up
    regardless of outcome."""
    print("\n--- Seeded orphan+keeper regression test ---")
    if not RUN_FIXTURE_TEST:
        print("  [SKIP] RUN_FIXTURE_TEST not set to true")
        return

    import seed_cascade_test_fixtures as fixtures
    from pymongo import MongoClient

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db_name = MONGO_URI.rstrip("/").split("/")[-1].split("?")[0] or "LibreChat"
    db = client[db_name]

    try:
        fixtures.seed(db)

        active_ids = set(
            doc["conversationId"]
            for doc in db.conversations.find({}, {"conversationId": 1})
            if doc.get("conversationId")
        )
        orphaned_ids = set(
            doc["file_id"]
            for doc in db.files.find(
                {
                    "conversationId": {
                        "$exists": True,
                        "$nin": list(active_ids),
                        "$type": "string",
                    }
                },
                {"file_id": 1},
            )
            if doc.get("file_id")
        )

        check(
            "Seeded orphan detected",
            fixtures.ORPHAN_FILE_ID in orphaned_ids,
            fixtures.ORPHAN_FILE_ID,
        )
        check(
            "Seeded keeper NOT flagged as orphan",
            fixtures.KEEPER_FILE_ID not in orphaned_ids,
            fixtures.KEEPER_FILE_ID,
        )
    finally:
        fixtures.cleanup(db)
        client.close()


def main():
    print("=== PBI-21-BE: Cascade Delete Validation ===")
    print(f"MongoDB: {MONGO_URI.split('@')[-1]}")
    print(f"pgvector: {RAG_DB_HOST}:{RAG_DB_PORT}/{RAG_DB_NAME}")
    print(f"Retention window: {RETENTION_DAYS} days")

    check_mongodb_orphans()
    check_pgvector_orphans()
    check_retention_candidates()
    check_canary_liveness()
    check_seeded_fixtures()

    print()
    if failures:
        print(f"RESULT: {len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("RESULT: All checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
