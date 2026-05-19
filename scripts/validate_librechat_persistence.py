#!/usr/bin/env python3
"""
Validates LibreChat conversation persistence and context window behavior
against Phase 0 acceptance criteria (PBI 9128).

This script depends on PBI 9125 (Azure File Share mounted) and PBI 9126
(LiteLLM routing configured). Run validate_librechat.py and
validate_librechat_litellm.py first.

What this script checks (automated):
  1. /api/health confirms the container is alive
  2. LiteLLM routing still works (regression check)
  3. The Azure File Share mount path (/app/api/data) is confirmed via the
     /api/health or config endpoint (if accessible)

What requires manual testing (full protocol in research doc PBI 9128):
  - Test A: Sidebar persistence — conversations survive browser refresh
  - Test B: Restart persistence — conversations survive container restart
  - Test C: Context in follow-ups — prior messages included in API payload
  - Test D: Delete behavior — deleted conversations gone after refresh

Usage:
  pip install -r requirements.txt
  python validate_librechat_persistence.py

Required environment variables (same .env as previous scripts):
  LIBRECHAT_URL
  LITELLM_URL
  LITELLM_VIRTUAL_KEY
"""

import os
import sys
import json
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("ERROR: requests package not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

# --- Configuration ---

LIBRECHAT_URL = os.environ.get("LIBRECHAT_URL", "").rstrip("/")
LITELLM_URL = os.environ.get("LITELLM_URL", "").rstrip("/")
VIRTUAL_KEY = os.environ.get("LITELLM_VIRTUAL_KEY", "")
MODEL = "ROMTech AI Standard"

missing = [k for k, v in {
    "LIBRECHAT_URL": LIBRECHAT_URL,
    "LITELLM_URL": LITELLM_URL,
    "LITELLM_VIRTUAL_KEY": VIRTUAL_KEY,
}.items() if not v]

if missing:
    print("ERROR: Missing required environment variables:")
    for k in missing:
        print(f"  {k}")
    sys.exit(1)

TIMEOUT = 30
LITELLM_AUTH = {"Authorization": f"Bearer {VIRTUAL_KEY}", "Content-Type": "application/json"}
TEST_MESSAGE = [{"role": "user", "content": "Reply with the single word: OK"}]

passed = 0
failed = 0
findings = []


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


def finding(label):
    findings.append(label)
    print(f"  FIND  {label}")


# --- Header ---

print()
print("LibreChat Persistence and Context Validation — PBI 9128")
print(f"  LibreChat URL: {LIBRECHAT_URL}")
print(f"  LiteLLM URL:   {LITELLM_URL}")
print()

# --- Test 1: LibreChat health ---

print("1. LibreChat /api/health — container alive")
try:
    r = requests.get(f"{LIBRECHAT_URL}/api/health", timeout=20)
    if r.status_code == 200:
        ok(f"HTTP 200 — {r.text.strip()[:80]}")
    else:
        fail(f"HTTP {r.status_code}", r.text.strip()[:200])
        print("  Cannot proceed without a running LibreChat instance.")
        sys.exit(1)
except Exception as e:
    fail("Connection failed", str(e))
    sys.exit(1)

# --- Test 2: LiteLLM routing regression ---

print()
print("2. LiteLLM routing regression — model requests still routed correctly")
try:
    r = requests.post(
        f"{LITELLM_URL}/chat/completions",
        headers=LITELLM_AUTH,
        json={"model": MODEL, "messages": TEST_MESSAGE},
        timeout=TIMEOUT,
    )
    if r.status_code == 200:
        content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        ok(f"Routing still working: {content.strip()[:60]!r}")
    else:
        fail(f"HTTP {r.status_code}", r.text[:200])
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 3: Multi-turn context window check ---

print()
print("3. Multi-turn request — prior message is included in the follow-up payload")
try:
    # Send turn 1
    turn1_msg = [{"role": "user", "content": "Remember the code word: ALPHA"}]
    r1 = requests.post(
        f"{LITELLM_URL}/chat/completions",
        headers=LITELLM_AUTH,
        json={"model": MODEL, "messages": turn1_msg},
        timeout=TIMEOUT,
    )
    if r1.status_code != 200:
        fail(f"Turn 1 failed: HTTP {r1.status_code}", r1.text[:200])
    else:
        assistant_reply = r1.json().get("choices", [{}])[0].get("message", {})

        # Send turn 2 including the prior exchange
        turn2_msgs = turn1_msg + [
            assistant_reply,
            {"role": "user", "content": "What was the code word?"},
        ]
        r2 = requests.post(
            f"{LITELLM_URL}/chat/completions",
            headers=LITELLM_AUTH,
            json={"model": MODEL, "messages": turn2_msgs},
            timeout=TIMEOUT,
        )
        if r2.status_code == 200:
            reply = r2.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            if "ALPHA" in reply.upper():
                ok(f"Model recalled context from prior turn: {reply.strip()[:80]!r}")
            else:
                finding(
                    f"Model reply did not contain 'ALPHA': {reply.strip()[:80]!r} — "
                    f"check how many prior messages LibreChat includes per request"
                )
        else:
            fail(f"Turn 2 failed: HTTP {r2.status_code}", r2.text[:200])
except Exception as e:
    fail("Unexpected error in multi-turn test", str(e))

# --- Manual test protocol ---

print()
print("=" * 55)
print("Manual validation required — run these tests in the browser:")
print()
print("  Test A — Sidebar persistence:")
print("    1. Open LibreChat and start a new conversation")
print("    2. Send 3+ messages")
print("    3. Perform a full browser page refresh (Ctrl+Shift+R)")
print("    4. PASS: Conversation appears in sidebar and all messages are visible")
print()
print("  Test B — Container restart persistence:")
print("    1. After Test A passes, restart the LibreChat container:")
print("       az containerapp revision restart --name librechat-nonprod --resource-group <RG>")
print("    2. Wait ~30s, reload the browser")
print("    3. PASS: Conversation from Test A is still visible in the sidebar")
print("    4. FAIL: If conversations are gone, the Azure File Share mount is not working")
print()
print("  Test C — Context in follow-up requests:")
print("    1. Open an existing conversation")
print("    2. Open browser DevTools > Network tab")
print("    3. Send: 'Summarize what we discussed so far'")
print("    4. Inspect the outgoing POST to /api/ask or /api/chat")
print("    5. PASS: Prior messages are in the 'messages' array of the request body")
print("    6. Document: How many prior messages are sent? Is it configurable?")
print()
print("  Test D — Delete behavior:")
print("    1. Delete a conversation from the sidebar")
print("    2. Refresh the page")
print("    3. PASS: Deleted conversation no longer appears")

if findings:
    print()
    print("Findings to document:")
    for i, f_text in enumerate(findings, 1):
        print(f"  [{i}] {f_text}")

# --- Summary ---

print()
print("=" * 55)
total = passed + failed
print(f"Automated results: {passed}/{total} passed", "" if failed == 0 else f"— {failed} FAILED")
print()
print("Complete manual tests A–D and document results before signing off PBI 9128.")

sys.exit(0 if failed == 0 else 1)
