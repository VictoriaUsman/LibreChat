#!/usr/bin/env python3
"""
Nightly cleanup job for PBI-21-BE (Option A), hardened to fail-closed per
"Harden Nightly Orphaned-File Cleanup to Fail-Closed". Deletes files from
Azure Blob Storage, pgvector, and MongoDB that have no matching active
conversation.

Runs as an ACA scheduled job (cron: 0 2 * * *).

Two-pass mark-and-sweep, report-only by default:
  Pass 1 (mark):  find files that look orphaned (no active conversation,
                  older than RETENTION_DAYS, not already marked) and stamp
                  them pendingDeletion=True / markedAt=now. Nothing is
                  deleted in this pass.
  Pass 2 (sweep): find files marked more than GRACE_PERIOD_DAYS ago,
                  re-verify each one individually via a targeted
                  per-candidate lookup (not the pass-1 snapshot), then
                  delete embeddings -> blob -> Mongo record, in that order,
                  idempotently. A file whose conversation became active
                  again during the grace window is un-marked instead of
                  deleted.

Both passes run on every invocation; nothing is actually written to Mongo,
Blob, or pgvector unless CLEANUP_ENFORCE=true (see below) -- the default
mode only logs/records what it would do.

Safety layers (see PBI for full rationale):
  1. Canary liveness  -- CANARY_CONVERSATION_ID must appear in the SAME
     active-conversation query used for orphan detection
     (get_active_conversation_ids), or the job aborts without touching
     anything. This turns a broken or misdirected query (DB down, wrong
     database, empty/partial result) into a hard stop instead of "every file
     looks orphaned". The canary is a non-empty-ID Conversation
     (seed_canary_conversation.py); LibreChat's only conversation reaper is
     deleteNullOrEmptyConversations, which targets null/empty/missing-ID
     documents only (packages/data-schemas/src/methods/conversation.ts), so
     the app never sweeps the canary and this job never has to write to it.
  2. Per-candidate existence check -- both passes re-query Mongo for a
     file's specific conversationId individually (conversation_exists)
     instead of trusting a bulk in-memory diff as the final word.
  3. Volume circuit breaker -- CIRCUIT_BREAKER_MAX_ABSOLUTE /
     CIRCUIT_BREAKER_MAX_RATIO abort the mark pass (marking nothing) if too
     many candidates appear at once, since that usually means the
     active-conversation query is broken rather than that many files being
     genuinely orphaned.
  4. Age filter -- RETENTION_DAYS (default 90); only files whose createdAt
     is older are ever eligible for marking.
  5. Two-pass mark-and-sweep with grace window -- see above.
  6. Delete ordering -- embeddings (pgvector) -> blob -> Mongo record last.
     Each step is idempotent/re-runnable (already-gone is success, not
     failure), so a crash mid-item is safely retried on the next run
     without double-deleting or leaving a dangling record.
  7. Recoverability backstop -- Azure Blob soft-delete + versioning
     (ChatGptForEmployees.bicep/storage.bicep), independent of this script.
  8. Report-only by default -- see CLEANUP_ENFORCE below.
  9. Audit log -- one JSON line per marked/unmarked/deleted/failed file,
     written to AUDIT_LOG_PATH. Exits non-zero on ANY per-item failure.
 10. pgvector path -- DELETE ... WHERE cmetadata->>'file_id' = ANY(%s),
     verified against the real rag_api ingestion code (LangChain Document
     metadata attaches a flat `file_id` key, stored in the `cmetadata`
     JSONB column).
 11. Regression coverage -- scripts/validate_cascade_delete.py and
     scripts/seed_cascade_test_fixtures.py exercise this against a seeded
     orphan+keeper dataset.

Required environment variables (from ACA secrets / .env):
  MONGO_URI                  MongoDB connection string
  AZURE_STORAGE_CONNECTION_STRING  Azure Blob connection string
  AZURE_CONTAINER_NAME       Blob container (default: files)
  RAG_DB_HOST                pgvector host
  RAG_DB_PORT                pgvector port (default: 5432)
  RAG_DB_NAME                pgvector database name
  RAG_DB_USER                pgvector user
  RAG_DB_PASSWORD            pgvector password

Config (all optional):
  CLEANUP_ENFORCE                 "true" to actually mark/delete. Anything
                                   else (including unset) = report-only.
                                   Flipping this is the explicit, documented
                                   config change required to go live in a
                                   shared/prod environment -- confirm the
                                   canary exists (seed_canary_conversation.py)
                                   and the circuit breaker thresholds below
                                   fit that environment's file volume first.
  CANARY_CONVERSATION_ID          default: __cleanup_canary__
  RETENTION_DAYS                  default: 90
  GRACE_PERIOD_DAYS               default: 3
  CIRCUIT_BREAKER_MAX_ABSOLUTE     default: 500
  CIRCUIT_BREAKER_MAX_RATIO        default: 0.10 (10% of all file records)
  AUDIT_LOG_PATH                   default: cleanup_audit.log (next to this file)

Exit codes:
  0 -- completed, zero per-item failures (report-only or enforcing)
  1 -- canary missing, circuit breaker tripped, per-item failure, or
       unrecoverable error
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/LibreChat")
AZURE_CONN_STR = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_CONTAINER = os.environ.get("AZURE_CONTAINER_NAME", "files")
RAG_DB_HOST = os.environ.get("RAG_DB_HOST", "localhost")
RAG_DB_PORT = int(os.environ.get("RAG_DB_PORT", "5432"))
RAG_DB_NAME = os.environ.get("RAG_DB_NAME", "librechat_rag")
RAG_DB_USER = os.environ.get("RAG_DB_USER", "")
RAG_DB_PASSWORD = os.environ.get("RAG_DB_PASSWORD", "")

CLEANUP_ENFORCE = os.environ.get("CLEANUP_ENFORCE", "false").strip().lower() == "true"
CANARY_CONVERSATION_ID = os.environ.get("CANARY_CONVERSATION_ID", "__cleanup_canary__")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "90"))
GRACE_PERIOD_DAYS = int(os.environ.get("GRACE_PERIOD_DAYS", "3"))
CIRCUIT_BREAKER_MAX_ABSOLUTE = int(os.environ.get("CIRCUIT_BREAKER_MAX_ABSOLUTE", "500"))
CIRCUIT_BREAKER_MAX_RATIO = float(os.environ.get("CIRCUIT_BREAKER_MAX_RATIO", "0.10"))
AUDIT_LOG_PATH = os.environ.get(
    "AUDIT_LOG_PATH", os.path.join(os.path.dirname(__file__), "cleanup_audit.log")
)


class CircuitBreakerTripped(Exception):
    pass


def audit(entry: dict) -> None:
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    entry["mode"] = "enforcing" if CLEANUP_ENFORCE else "report-only"
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def get_db_name(uri: str) -> str:
    return uri.rstrip("/").split("/")[-1].split("?")[0] or "LibreChat"


def get_active_conversation_ids(db) -> set:
    """The single active-conversation query. Both the canary liveness check
    (safety layer #1) and the mark-pass pre-filter read from THIS result, so a
    broken or partial query is caught by the canary instead of silently making
    every file look orphaned."""
    return set(
        doc["conversationId"]
        for doc in db.conversations.find({}, {"conversationId": 1})
        if doc.get("conversationId")
    )


def check_canary(active_ids) -> bool:
    """Safety layer #1. Aborts unless the sentinel canary conversation is
    present in the active-conversation set -- the SAME set used for orphan
    detection. The canary is a record we know exists; if it's missing, the
    query did not truly reach a healthy database, so we must not delete. No
    write is needed: the canary is a non-empty-ID doc, immune to LibreChat's
    deleteNullOrEmptyConversations sweep (see module docstring, safety #1)."""
    if CANARY_CONVERSATION_ID not in active_ids:
        log.error(
            "CANARY MISSING: conversationId=%s not present in the active-conversation "
            "query result. Aborting without marking or deleting anything. Seed it with "
            "seed_canary_conversation.py, or check MONGO_URI points at the right database.",
            CANARY_CONVERSATION_ID,
        )
        return False
    log.info(
        "Canary check passed: conversationId=%s present in active set.", CANARY_CONVERSATION_ID
    )
    return True


def conversation_exists(db, conversation_id) -> bool:
    """Safety layer #2: a fresh, targeted lookup for this one
    conversationId, not a bulk in-memory diff."""
    if not conversation_id:
        return False
    return db.conversations.find_one({"conversationId": conversation_id}, {"_id": 1}) is not None


def find_mark_candidates(db, active_ids):
    """Pass 1 discovery. The active_ids set (already canary-verified in main)
    is used only as a cheap pre-filter; every candidate it surfaces is then
    re-checked individually before it's trusted -- see safety layer #2."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    prefiltered = list(
        db.files.find(
            {
                "conversationId": {"$exists": True, "$nin": list(active_ids), "$type": "string"},
                "pendingDeletion": {"$ne": True},
                "createdAt": {"$lt": cutoff},
            }
        )
    )

    verified = [c for c in prefiltered if not conversation_exists(db, c["conversationId"])]
    skipped = len(prefiltered) - len(verified)
    if skipped:
        log.warning(
            "%d candidate(s) dropped by per-candidate re-check (conversation reappeared "
            "between the bulk pre-filter and verification)",
            skipped,
        )
    return verified


def mark_pass(db, active_ids) -> int:
    """Pass 1: mark eligible orphan candidates. Never deletes anything."""
    candidates = find_mark_candidates(db, active_ids)
    total_files = db.files.count_documents({})

    if not candidates:
        log.info("Mark pass: no new orphan candidates found.")
        return 0

    ratio = (len(candidates) / total_files) if total_files else 1.0
    if len(candidates) > CIRCUIT_BREAKER_MAX_ABSOLUTE or ratio > CIRCUIT_BREAKER_MAX_RATIO:
        log.error(
            "CIRCUIT BREAKER TRIPPED: %d candidate(s) (%.1f%% of %d total file records) "
            "exceeds threshold (max_absolute=%d, max_ratio=%.2f). Aborting mark pass without "
            "marking anything -- this usually means the active-conversation query is broken, "
            "not that this many files are genuinely orphaned.",
            len(candidates), ratio * 100, total_files,
            CIRCUIT_BREAKER_MAX_ABSOLUTE, CIRCUIT_BREAKER_MAX_RATIO,
        )
        audit({
            "action": "circuit_breaker_tripped",
            "candidate_count": len(candidates),
            "total_files": total_files,
            "ratio": ratio,
        })
        raise CircuitBreakerTripped()

    log.info("Mark pass: %d candidate(s) eligible for marking.", len(candidates))
    now = datetime.now(timezone.utc)
    for f in candidates:
        file_id = f.get("file_id", str(f.get("_id")))
        evidence = (
            f"conversationId={f.get('conversationId')} has no active conversation; "
            f"createdAt older than {RETENTION_DAYS}d"
        )
        if CLEANUP_ENFORCE:
            db.files.update_one(
                {"_id": f["_id"]}, {"$set": {"pendingDeletion": True, "markedAt": now}}
            )
        audit({
            "action": "marked" if CLEANUP_ENFORCE else "would_mark",
            "file_id": file_id,
            "conversationId": f.get("conversationId"),
            "evidence": evidence,
        })
    log.info(
        "Mark pass complete: %d file(s) %s.",
        len(candidates), "marked" if CLEANUP_ENFORCE else "would be marked",
    )
    return len(candidates)


def find_sweep_candidates(db):
    grace_cutoff = datetime.now(timezone.utc) - timedelta(days=GRACE_PERIOD_DAYS)
    return list(db.files.find({"pendingDeletion": True, "markedAt": {"$lt": grace_cutoff}}))


def delete_from_blob(file):
    """Delete a blob from Azure Blob Storage. Skips silently on 404 (idempotent)."""
    if not AZURE_CONN_STR:
        log.warning(
            "AZURE_STORAGE_CONNECTION_STRING not set — skipping blob delete for %s",
            file.get("file_id"),
        )
        return

    filepath = file.get("filepath", "")
    if not filepath:
        return

    from azure.storage.blob import BlobServiceClient

    client = BlobServiceClient.from_connection_string(AZURE_CONN_STR)
    container_client = client.get_container_client(AZURE_CONTAINER)

    marker = f"{AZURE_CONTAINER}/"
    if marker in filepath:
        blob_path = filepath.split(marker, 1)[1]
    else:
        log.warning("Could not parse blob path from filepath=%s", filepath)
        return

    try:
        container_client.delete_blob(blob_path)
        log.info("Blob deleted: %s", blob_path)
    except Exception as e:
        status = getattr(e, "status_code", None) or getattr(e, "error_code", None)
        if status == 404 or "BlobNotFound" in str(e):
            log.debug("Blob already gone: %s", filepath)
        else:
            raise


def delete_from_pgvector(file_ids):
    """Delete pgvector embedding rows for the given file_ids. Verified
    metadata path: rag_api attaches a flat `file_id` key to each LangChain
    Document, stored in the `cmetadata` JSONB column (safety layer #10)."""
    if not RAG_DB_USER or not file_ids:
        return 0

    import psycopg2

    conn = psycopg2.connect(
        host=RAG_DB_HOST,
        port=RAG_DB_PORT,
        dbname=RAG_DB_NAME,
        user=RAG_DB_USER,
        password=RAG_DB_PASSWORD,
        connect_timeout=10,
    )
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM langchain_pg_embedding WHERE cmetadata->>'file_id' = ANY(%s)",
            (list(file_ids),),
        )
        count = cur.rowcount
        conn.commit()
        cur.close()
        return count
    finally:
        conn.close()


def sweep_pass(db):
    """Pass 2: re-verify each previously-marked file individually right
    before deleting, in embeddings -> blob -> Mongo order (safety layer #6).
    Any failure at a given step aborts that file's chain so the record
    survives for retry on the next run; already-gone at any step counts as
    success (idempotent)."""
    candidates = find_sweep_candidates(db)
    if not candidates:
        log.info("Sweep pass: no file(s) past the grace window.")
        return 0, 0

    # Safety layer #3 applied to the sweep too: every marked file already
    # passed the mark-pass breaker, but a backlog accumulated over many nights
    # could still sweep a large batch at once. Abort rather than mass-delete.
    total_files = db.files.count_documents({})
    ratio = (len(candidates) / total_files) if total_files else 1.0
    if len(candidates) > CIRCUIT_BREAKER_MAX_ABSOLUTE or ratio > CIRCUIT_BREAKER_MAX_RATIO:
        log.error(
            "CIRCUIT BREAKER TRIPPED (sweep): %d marked file(s) past grace (%.1f%% of %d "
            "total) exceeds threshold (max_absolute=%d, max_ratio=%.2f). Aborting sweep "
            "without deleting anything.",
            len(candidates), ratio * 100, total_files,
            CIRCUIT_BREAKER_MAX_ABSOLUTE, CIRCUIT_BREAKER_MAX_RATIO,
        )
        audit({
            "action": "circuit_breaker_tripped_sweep",
            "candidate_count": len(candidates),
            "total_files": total_files,
            "ratio": ratio,
        })
        raise CircuitBreakerTripped()

    log.info(
        "Sweep pass: %d file(s) past the %dd grace window, re-verifying individually.",
        len(candidates), GRACE_PERIOD_DAYS,
    )

    deleted = 0
    failed = 0
    for f in candidates:
        file_id = f.get("file_id", str(f.get("_id")))
        conversation_id = f.get("conversationId")

        # Second application of safety layer #2: re-check right before
        # delete, not the mark-pass snapshot.
        if conversation_exists(db, conversation_id):
            log.info(
                "Un-marking file_id=%s: conversationId=%s is active again.",
                file_id, conversation_id,
            )
            if CLEANUP_ENFORCE:
                db.files.update_one(
                    {"_id": f["_id"]}, {"$unset": {"pendingDeletion": "", "markedAt": ""}}
                )
            audit({
                "action": "unmarked",
                "file_id": file_id,
                "conversationId": conversation_id,
                "evidence": "conversation became active again during the grace window",
            })
            continue

        source = f.get("source", "local")
        evidence = (
            f"conversationId={conversation_id} still absent after {GRACE_PERIOD_DAYS}d grace window"
        )

        has_embeddings = f.get("embedded") is True
        try:
            embedded_rows = 0
            if has_embeddings and CLEANUP_ENFORCE:
                embedded_rows = delete_from_pgvector([file_id])

            if source == "azure_blob" and CLEANUP_ENFORCE:
                delete_from_blob(f)

            if CLEANUP_ENFORCE:
                db.files.delete_one({"_id": f["_id"]})

            audit({
                "action": "deleted" if CLEANUP_ENFORCE else "would_delete",
                "file_id": file_id,
                "conversationId": conversation_id,
                "evidence": evidence,
                "source": source,
                "has_embeddings": has_embeddings,
                "embedded_rows_deleted": embedded_rows if CLEANUP_ENFORCE else None,
            })
            log.info(
                "%s file_id=%s source=%s conversationId=%s has_embeddings=%s",
                "Deleted" if CLEANUP_ENFORCE else "Would delete",
                file_id, source, conversation_id, has_embeddings,
            )
            deleted += 1
        except Exception as e:
            failed += 1
            log.error("Sweep failed for file_id=%s: %s", file_id, e)
            audit({
                "action": "failed",
                "file_id": file_id,
                "conversationId": conversation_id,
                "evidence": evidence,
                "error": str(e),
            })

    return deleted, failed


def main():
    mode = "ENFORCING" if CLEANUP_ENFORCE else "REPORT-ONLY"
    log.info("=== Orphaned file cleanup starting (mode=%s) ===", mode)

    try:
        from pymongo import MongoClient

        mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        db = mongo[get_db_name(MONGO_URI)]

        # Single active-conversation query, shared by the canary check and the
        # mark pass so the canary genuinely rides the same query (safety #1).
        active_ids = get_active_conversation_ids(db)
        if not check_canary(active_ids):
            mongo.close()
            sys.exit(1)

        try:
            marked = mark_pass(db, active_ids)
            deleted, failed = sweep_pass(db)
        except CircuitBreakerTripped:
            mongo.close()
            sys.exit(1)

        mongo.close()
    except Exception as e:
        log.error("Unrecoverable error during cleanup: %s", e)
        sys.exit(1)

    log.info(
        "=== Cleanup complete: mode=%s marked=%d deleted=%d failed=%d ===",
        mode, marked, deleted, failed,
    )
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
