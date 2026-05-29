#!/usr/bin/env python3
"""
validate_librechat_persistence.py  –  PBI 9561 acceptance check (conversation persistence)

Two-phase test: create a conversation before a restart, verify it survives the restart.

Usage:
  Phase 1 — create conversation and save its ID:
    python scripts/validate_librechat_persistence.py --create

  Restart LibreChat (stop the process and start it again), then:

  Phase 2 — verify the conversation is still accessible:
    python scripts/validate_librechat_persistence.py --verify

  Single-pass (no restart, storage-only test):
    python scripts/validate_librechat_persistence.py --auto

Prerequisites:
  - LibreChat running at LIBRECHAT_URL
  - LIBRECHAT_TEST_USER_EMAIL / LIBRECHAT_TEST_USER_PASSWORD in scripts/.env

Run from the project root.

Requirements:
  pip install requests pymongo
  (pymongo is optional — adds a direct MongoDB read to the verify phase)
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed.  Run: pip install requests")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
ENV_FILE = SCRIPT_DIR / ".env"
STATE_FILE = SCRIPT_DIR / ".test_conversation_id"

# ── Load scripts/.env ─────────────────────────────────────────────────────────
if not ENV_FILE.exists():
    print(f"FATAL: scripts/.env not found at {ENV_FILE}")
    sys.exit(1)

env: dict[str, str] = {}
with open(ENV_FILE) as fh:
    for raw in fh:
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()

LIBRECHAT_URL = env.get("LIBRECHAT_URL", "http://localhost:3080")
TEST_EMAIL = env.get("LIBRECHAT_TEST_USER_EMAIL", "")
TEST_PASSWORD = env.get("LIBRECHAT_TEST_USER_PASSWORD", "")
MONGO_URI = env.get("MONGO_URI", "mongodb://localhost:27017/LibreChat")

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    line = f"  {tag}  {label}"
    if not ok and detail:
        line += f"  ({detail})"
    print(line)
    if not ok:
        failures.append(label)


def login() -> str:
    if not TEST_EMAIL or not TEST_PASSWORD:
        print("FATAL: LIBRECHAT_TEST_USER_EMAIL / LIBRECHAT_TEST_USER_PASSWORD not set.")
        print("       Create a test user:  cd <LibreChat-repo> && npm run create-user")
        sys.exit(1)
    r = requests.post(
        f"{LIBRECHAT_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=10,
    )
    if r.status_code != 200:
        print(f"FATAL: Login failed (HTTP {r.status_code})")
        sys.exit(1)
    token = r.json().get("token")
    if not token:
        print("FATAL: Auth token missing from login response.")
        sys.exit(1)
    return token


# ── Phase 1: create conversation ─────────────────────────────────────────────
def phase_create(token: str) -> None:
    print("\n[Phase 1] Creating test conversation in LibreChat...")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    r = requests.post(
        f"{LIBRECHAT_URL}/api/ask/custom",
        headers=headers,
        json={
            "text": "Persistence validation message. Reply with: PERSISTENCE_OK",
            "endpoint": "custom",
            "model": "ROMTech AI Standard",
            "conversationId": "new",
            "parentMessageId": "00000000-0000-0000-0000-000000000000",
        },
        stream=True,
        timeout=30,
    )
    check("Message accepted (HTTP 200)", r.status_code == 200, f"HTTP {r.status_code}")
    if r.status_code != 200:
        return

    conversation_id: str | None = None
    for raw in r.iter_lines(chunk_size=4096):
        if not raw:
            continue
        chunk = raw.decode("utf-8", errors="replace")
        if chunk.startswith("data: "):
            chunk = chunk[6:]
        try:
            data = json.loads(chunk)
            if "conversationId" in data and data["conversationId"] != "new":
                conversation_id = data["conversationId"]
                break
        except json.JSONDecodeError:
            pass

    # Fallback: pull from the conversations list
    if not conversation_id:
        time.sleep(2)
        r2 = requests.get(
            f"{LIBRECHAT_URL}/api/conversations?pageNumber=1",
            headers=headers,
            timeout=10,
        )
        if r2.status_code == 200:
            convos = r2.json().get("conversations", [])
            if convos:
                conversation_id = convos[0].get("conversationId")

    check("Conversation ID captured from response", bool(conversation_id),
          "could not extract conversationId — check LibreChat logs")

    if conversation_id:
        STATE_FILE.write_text(conversation_id, encoding="utf-8")
        print(f"\n  Conversation ID : {conversation_id}")
        print(f"  Saved to        : {STATE_FILE}")
        print()
        print("  >> Restart LibreChat now (stop the process, start it again),")
        print("     then run:  python scripts/validate_librechat_persistence.py --verify")


# ── Phase 2: verify conversation survives restart ─────────────────────────────
def phase_verify(token: str) -> None:
    print("\n[Phase 2] Verifying conversation persists after restart...")

    if not STATE_FILE.exists():
        print(f"FATAL: {STATE_FILE} not found.  Run --create first.")
        sys.exit(1)

    conversation_id = STATE_FILE.read_text(encoding="utf-8").strip()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Check via LibreChat API
    r = requests.get(
        f"{LIBRECHAT_URL}/api/conversations?pageNumber=1",
        headers=headers,
        timeout=10,
    )
    check("Conversations API responds", r.status_code == 200, f"HTTP {r.status_code}")

    if r.status_code == 200:
        ids = [c.get("conversationId") for c in r.json().get("conversations", [])]
        check(
            f"Conversation {conversation_id[:8]}… found in conversation list",
            conversation_id in ids,
            f"not in first page: {[i[:8] for i in ids[:5]]}",
        )

    # Fetch the messages for the conversation
    r2 = requests.get(
        f"{LIBRECHAT_URL}/api/messages/{conversation_id}",
        headers=headers,
        timeout=10,
    )
    check("Messages endpoint responds", r2.status_code == 200, f"HTTP {r2.status_code}")
    if r2.status_code == 200:
        messages = r2.json() if isinstance(r2.json(), list) else r2.json().get("messages", [])
        check("Messages list is non-empty after restart",
              isinstance(messages, list) and len(messages) > 0,
              f"got {len(messages) if isinstance(messages, list) else '?'} messages")

    # Optional: direct MongoDB read
    try:
        import pymongo  # type: ignore

        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        db = client.get_default_database()
        count = db["messages"].count_documents({"conversationId": conversation_id})
        check(f"MongoDB contains messages for conversation {conversation_id[:8]}…",
              count > 0, f"found {count} documents")
        client.close()
    except ImportError:
        print("  SKIP  MongoDB direct read — pymongo not installed (pip install pymongo)")
    except Exception as exc:
        check("MongoDB direct read", False, str(exc))

    if not failures:
        STATE_FILE.unlink(missing_ok=True)
        print("  (state file cleaned up)")


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate LibreChat conversation persistence"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--create", action="store_true",
                       help="Phase 1: send message and save conversation ID")
    group.add_argument("--verify", action="store_true",
                       help="Phase 2: confirm conversation survives after restart")
    group.add_argument("--auto", action="store_true",
                       help="Both phases without a restart (validates storage only)")
    args = parser.parse_args()

    token = login()

    if args.create:
        phase_create(token)
    elif args.verify:
        phase_verify(token)
    elif args.auto:
        phase_create(token)
        if not failures:
            print("\n  [auto mode — verifying immediately without a restart]\n")
            time.sleep(3)
            token = login()
            phase_verify(token)

    print(f"\n{'=' * 52}")
    if failures:
        print(f"RESULT: {len(failures)} failure(s)")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("RESULT: All checks passed  (0 failures)")
        sys.exit(0)


if __name__ == "__main__":
    main()
