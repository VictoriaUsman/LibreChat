#!/usr/bin/env python3
"""
Seeds (idempotently) the sentinel "canary" conversation used by
cleanup_orphaned_files.py and validate_cascade_delete.py to detect a broken
or misdirected active-conversation query before any deletion runs (PBI:
Harden Nightly Orphaned-File Cleanup to Fail-Closed, safety layer #1).

The canary is a real Conversation document with a reserved, non-empty
conversationId. Because deleteNullOrEmptyConversations only reaps documents
with a null/empty/missing conversationId (see
packages/data-schemas/src/methods/conversation.ts), this record is immune to
LibreChat's own conversation-retention sweep and will only disappear if
someone/something deletes it directly or points the cleanup job at the wrong
database -- which is exactly the failure mode this is meant to catch.

Run once per environment before enabling the cleanup job. Safe to re-run
(upsert by conversationId).

Required environment variables (scripts/.env):
  MONGO_URI              MongoDB connection string
  CANARY_CONVERSATION_ID Reserved sentinel ID (default: __cleanup_canary__)

Exit codes:
  0 -- canary present (created or already existed)
  1 -- unrecoverable error
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/LibreChat")
CANARY_CONVERSATION_ID = os.environ.get("CANARY_CONVERSATION_ID", "__cleanup_canary__")
CANARY_USER = "system-cleanup-canary"


def main():
    try:
        from pymongo import MongoClient
        from datetime import datetime, timezone

        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        db_name = MONGO_URI.rstrip("/").split("/")[-1].split("?")[0] or "LibreChat"
        db = client[db_name]

        now = datetime.now(timezone.utc)
        result = db.conversations.update_one(
            {"conversationId": CANARY_CONVERSATION_ID},
            {
                "$setOnInsert": {
                    "conversationId": CANARY_CONVERSATION_ID,
                    "user": CANARY_USER,
                    "title": "[system] cleanup job canary -- do not delete",
                    "createdAt": now,
                    "updatedAt": now,
                }
            },
            upsert=True,
        )

        if result.upserted_id is not None:
            print(f"Canary created: conversationId={CANARY_CONVERSATION_ID}")
        else:
            print(f"Canary already present: conversationId={CANARY_CONVERSATION_ID}")

        client.close()
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: failed to seed canary conversation: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
