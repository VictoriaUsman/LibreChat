#!/usr/bin/env python3
"""
Seeds a known orphan + keeper dataset for regression-testing the hardened
cleanup_orphaned_files.py and validate_cascade_delete.py (PBI: Harden
Nightly Orphaned-File Cleanup to Fail-Closed, safety layer #11 -- "no
regression: cascade-delete validator passes against seeded orphans+keepers
dataset").

Creates, tagged with _test_fixture=True so they're never mistaken for real
data:
  - one "keeper" conversation + file record (active conversation, recent
    createdAt) that must NOT be flagged as orphaned
  - one "orphan" file record (no matching conversation, createdAt older
    than RETENTION_DAYS) that MUST be flagged as orphaned

Usage:
  python seed_cascade_test_fixtures.py           # create fixtures
  python seed_cascade_test_fixtures.py --cleanup  # remove fixtures

Required environment variables (scripts/.env):
  MONGO_URI    MongoDB connection string
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/LibreChat")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "90"))

KEEPER_CONVERSATION_ID = "__test_fixture_keeper_convo__"
KEEPER_FILE_ID = "__test_fixture_keeper_file__"
ORPHAN_FILE_ID = "__test_fixture_orphan_file__"
ORPHAN_CONVERSATION_ID = "__test_fixture_orphan_convo_does_not_exist__"


def get_db():
    from pymongo import MongoClient

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    db_name = MONGO_URI.rstrip("/").split("/")[-1].split("?")[0] or "LibreChat"
    return client, client[db_name]


def seed(db):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=RETENTION_DAYS + 1)

    db.conversations.update_one(
        {"conversationId": KEEPER_CONVERSATION_ID},
        {
            "$set": {
                "conversationId": KEEPER_CONVERSATION_ID,
                "user": "system-test-fixture",
                "title": "[test fixture] keeper conversation",
                "updatedAt": now,
                "_test_fixture": True,
            },
            "$setOnInsert": {"createdAt": now},
        },
        upsert=True,
    )

    db.files.update_one(
        {"file_id": KEEPER_FILE_ID},
        {
            "$set": {
                "file_id": KEEPER_FILE_ID,
                "conversationId": KEEPER_CONVERSATION_ID,
                "filename": "keeper.txt",
                "filepath": "/uploads/keeper.txt",
                "bytes": 1,
                "object": "file",
                "source": "local",
                "embedded": False,
                "createdAt": now,
                "_test_fixture": True,
            }
        },
        upsert=True,
    )

    db.files.update_one(
        {"file_id": ORPHAN_FILE_ID},
        {
            "$set": {
                "file_id": ORPHAN_FILE_ID,
                "conversationId": ORPHAN_CONVERSATION_ID,
                "filename": "orphan.txt",
                "filepath": "/uploads/orphan.txt",
                "bytes": 1,
                "object": "file",
                "source": "local",
                "embedded": False,
                "createdAt": old,
                "_test_fixture": True,
            }
        },
        upsert=True,
    )

    print("Fixtures seeded:")
    print(f"  keeper: conversationId={KEEPER_CONVERSATION_ID} file_id={KEEPER_FILE_ID}")
    print(f"  orphan: file_id={ORPHAN_FILE_ID} (conversationId={ORPHAN_CONVERSATION_ID} does not exist)")


def cleanup(db):
    db.conversations.delete_many({"_test_fixture": True})
    result = db.files.delete_many({"_test_fixture": True})
    print(f"Fixtures removed ({result.deleted_count} file(s), keeper conversation).")


def main():
    client, db = get_db()
    try:
        if "--cleanup" in sys.argv:
            cleanup(db)
        else:
            seed(db)
    finally:
        client.close()


if __name__ == "__main__":
    main()
