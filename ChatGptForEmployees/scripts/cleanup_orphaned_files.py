#!/usr/bin/env python3
"""
Nightly cleanup job for PBI-21-BE (Option A): deletes files from Azure Blob Storage,
pgvector, and MongoDB that have no matching active conversation.

Runs as an ACA scheduled job (cron: 0 2 * * *).

Required environment variables (from ACA secrets / .env):
  MONGO_URI                  MongoDB connection string
  AZURE_STORAGE_CONNECTION_STRING  Azure Blob connection string
  AZURE_CONTAINER_NAME       Blob container (default: files)
  RAG_DB_HOST                pgvector host
  RAG_DB_PORT                pgvector port (default: 5432)
  RAG_DB_NAME                pgvector database name
  RAG_DB_USER                pgvector user
  RAG_DB_PASSWORD            pgvector password

Exit codes:
  0 -- completed (with or without deletions)
  1 -- unrecoverable error
"""

import os
import sys
import logging
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


def get_orphaned_files(db):
    """Return file records in MongoDB whose conversationId has no active conversation."""
    active_ids = set(
        doc["conversationId"]
        for doc in db.conversations.find({}, {"conversationId": 1})
        if doc.get("conversationId")
    )
    return list(
        db.files.find(
            {
                "conversationId": {
                    "$exists": True,
                    "$nin": list(active_ids),
                    "$type": "string",
                }
            }
        )
    )


def delete_from_blob(file):
    """Delete a blob from Azure Blob Storage. Skips silently on 404."""
    if not AZURE_CONN_STR:
        log.warning("AZURE_STORAGE_CONNECTION_STRING not set — skipping blob delete for %s", file.get("file_id"))
        return

    filepath = file.get("filepath", "")
    if not filepath:
        return

    try:
        from azure.storage.blob import BlobServiceClient

        client = BlobServiceClient.from_connection_string(AZURE_CONN_STR)
        container_client = client.get_container_client(AZURE_CONTAINER)

        # filepath is a full blob URL; extract the path after the container name
        marker = f"{AZURE_CONTAINER}/"
        if marker in filepath:
            blob_path = filepath.split(marker, 1)[1]
        else:
            log.warning("Could not parse blob path from filepath=%s", filepath)
            return

        container_client.delete_blob(blob_path)
        log.info("Blob deleted: %s", blob_path)
    except Exception as e:
        status = getattr(e, "status_code", None) or getattr(e, "error_code", None)
        if status == 404 or "BlobNotFound" in str(e):
            log.debug("Blob already gone: %s", filepath)
        else:
            log.error("Failed to delete blob for file_id=%s: %s", file.get("file_id"), e)
            raise


def delete_from_pgvector(file_ids):
    """Delete pgvector embedding rows for the given file_ids."""
    if not RAG_DB_USER or not file_ids:
        return 0

    try:
        import psycopg2

        conn = psycopg2.connect(
            host=RAG_DB_HOST,
            port=RAG_DB_PORT,
            dbname=RAG_DB_NAME,
            user=RAG_DB_USER,
            password=RAG_DB_PASSWORD,
            connect_timeout=10,
        )
        cur = conn.cursor()
        cur.execute(
            """
            DELETE FROM langchain_pg_embedding
            WHERE cmetadata->>'file_id' = ANY(%s)
            """,
            (list(file_ids),),
        )
        count = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return count
    except Exception as e:
        log.error("pgvector delete failed: %s", e)
        return 0


def main():
    log.info("=== Orphaned file cleanup starting ===")

    try:
        from pymongo import MongoClient

        mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        db_name = MONGO_URI.rstrip("/").split("/")[-1].split("?")[0] or "LibreChat"
        db = mongo[db_name]
    except Exception as e:
        log.error("MongoDB connection failed: %s", e)
        sys.exit(1)

    try:
        orphans = get_orphaned_files(db)
    except Exception as e:
        log.error("Failed to query orphaned files: %s", e)
        mongo.close()
        sys.exit(1)

    if not orphans:
        log.info("No orphaned files found. Nothing to do.")
        mongo.close()
        sys.exit(0)

    log.info("Found %d orphaned file(s) to clean up", len(orphans))

    blob_deleted = 0
    blob_failed = 0
    mongo_deleted = 0
    embedded_file_ids = []

    for file in orphans:
        file_id = file.get("file_id", str(file.get("_id")))
        source = file.get("source", "local")

        # Delete from Azure Blob if applicable
        if source == "azure_blob":
            try:
                delete_from_blob(file)
                blob_deleted += 1
            except Exception:
                blob_failed += 1
                log.warning("Skipping MongoDB delete for file_id=%s due to blob error", file_id)
                continue

        # Collect embedded file_ids for batch pgvector delete
        if file.get("embedded") is True:
            embedded_file_ids.append(file_id)

        # Delete MongoDB record
        try:
            db.files.delete_one({"_id": file["_id"]})
            mongo_deleted += 1
            log.info("Deleted file_id=%s source=%s conversationId=%s", file_id, source, file.get("conversationId"))
        except Exception as e:
            log.error("MongoDB delete failed for file_id=%s: %s", file_id, e)

    # Batch delete pgvector embeddings
    vector_rows_deleted = 0
    if embedded_file_ids:
        vector_rows_deleted = delete_from_pgvector(embedded_file_ids)
        log.info("Deleted %d pgvector row(s) for %d embedded file(s)", vector_rows_deleted, len(embedded_file_ids))

    mongo.close()

    log.info(
        "=== Cleanup complete: blob_deleted=%d blob_failed=%d mongo_deleted=%d vector_rows_deleted=%d ===",
        blob_deleted, blob_failed, mongo_deleted, vector_rows_deleted,
    )

    sys.exit(1 if blob_failed > 0 else 0)


if __name__ == "__main__":
    main()
