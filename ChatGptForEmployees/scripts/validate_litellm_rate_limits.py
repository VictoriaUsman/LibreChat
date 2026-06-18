#!/usr/bin/env python3
"""
Validates LiteLLM rate limiting and budget enforcement against Phase 0
acceptance criteria (PBI-06-BE). Corresponds to Section 4C.7 of the Phase 0 plan.

This script depends on PBI-03-BE. Run validate_litellm_routing.py first.

What this script does:
  1. Creates a temporary virtual key with an RPM limit of 1
  2. Sends two back-to-back requests using that key
     - First request: must succeed (HTTP 200)
     - Second request: must be rejected (HTTP 429)
  3. Verifies the 429 response is distinguishable from other error types
  4. ALWAYS deletes the temporary test key after the test (cleanup)
  5. Verifies the master key still routes correctly (regression)

The test key is scoped only to this validation run. It is created and deleted
within this script and will not interfere with other ongoing tests.

Usage:
  pip install -r requirements.txt
  python validate_litellm_rate_limits.py

Required environment variables (same .env as previous scripts):
  LITELLM_URL
  LITELLM_MASTER_KEY
  LITELLM_MODEL_FLAGSHIP   (defaults to "ROMTech AI Standard" if not set)
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

BASE_URL = os.environ.get("LITELLM_URL", "").rstrip("/")
MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
MODEL = os.environ.get("LITELLM_MODEL_FLAGSHIP", "ROMTech AI Standard")

missing = [k for k, v in {
    "LITELLM_URL": BASE_URL,
    "LITELLM_MASTER_KEY": MASTER_KEY,
}.items() if not v]

if missing:
    print("ERROR: Missing required environment variables:")
    for k in missing:
        print(f"  {k}")
    sys.exit(1)

TIMEOUT = 30
MASTER_AUTH = {"Authorization": f"Bearer {MASTER_KEY}", "Content-Type": "application/json"}
TEST_MESSAGE = [{"role": "user", "content": "Reply with the single word: OK"}]
TEST_KEY_ALIAS = "phase0-rate-limit-test"

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


def chat(key):
    return requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": TEST_MESSAGE},
        timeout=TIMEOUT,
    )


def create_test_key():
    r = requests.post(
        f"{BASE_URL}/key/generate",
        headers=MASTER_AUTH,
        json={
            "key_alias": TEST_KEY_ALIAS,
            "models": [MODEL],
            "rpm_limit": 1,        # 1 request per minute — exceeded on the second back-to-back call
            "duration": "1h",      # Auto-expires in 1 hour as a safety net
            "metadata": {"purpose": "phase0-rate-limit-test"},
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Failed to create test key: HTTP {r.status_code} — {r.text[:200]}")
    key_value = r.json().get("key")
    if not key_value:
        raise RuntimeError(f"Key created but no 'key' field in response: {r.text[:200]}")
    return key_value


def delete_test_key(key_value):
    r = requests.post(
        f"{BASE_URL}/key/delete",
        headers=MASTER_AUTH,
        json={"keys": [key_value]},
        timeout=TIMEOUT,
    )
    return r.status_code == 200


# --- Header ---

print()
print("LiteLLM Rate Limiting and Budget Enforcement Validation")
print(f"  LiteLLM URL:  {BASE_URL}")
print(f"  Test model:   {MODEL}")
print(f"  Test key:     {TEST_KEY_ALIAS} (rpm_limit=1, expires in 1h)")
print()

test_key = None

try:
    # --- Setup: create the test key ---

    print("Setup: creating temporary test key with rpm_limit=1...")
    try:
        test_key = create_test_key()
        print(f"  Test key created.")
    except RuntimeError as e:
        print(f"  ERROR: {e}")
        print()
        print("  Cannot proceed without a test key.")
        print("  If /key/generate returns 4xx, LiteLLM may require a database (DATABASE_URL)")
        print("  for virtual key management. See config/rate_limiting_options.md.template.")
        sys.exit(1)

    print()

    # --- Test 1: First request succeeds ---

    print("1. First request with test key succeeds (under the rpm_limit)")
    try:
        r1 = chat(test_key)
        if r1.status_code == 200:
            ok("HTTP 200 — first request accepted")
        else:
            fail(f"HTTP {r1.status_code} on first request (expected 200)", r1.text[:200])
    except requests.exceptions.Timeout:
        fail(f"First request timed out after {TIMEOUT}s")
    except Exception as e:
        fail("Unexpected error on first request", str(e))

    # --- Test 2: Second request is rejected with 429 ---

    print()
    print("2. Second back-to-back request is rejected (exceeds rpm_limit=1)")
    try:
        r2 = chat(test_key)
        if r2.status_code == 429:
            ok("HTTP 429 — rate limit enforced as expected")
        elif r2.status_code == 200:
            fail(
                "HTTP 200 — second request was accepted (limit not enforced)",
                "Possible causes: rpm_limit requires DATABASE_URL, or LiteLLM version "
                "does not enforce in-memory RPM limits. See options doc.",
            )
        else:
            fail(f"HTTP {r2.status_code} (expected 429)", r2.text[:200])
    except requests.exceptions.Timeout:
        fail(f"Second request timed out after {TIMEOUT}s")
    except Exception as e:
        fail("Unexpected error on second request", str(e))

    # --- Test 3: 429 response is distinguishable ---

    print()
    print("3. Rate limit error response is distinguishable from other error types")
    try:
        # Use the same r2 response from test 2 if it was a 429
        if 'r2' in dir() and r2.status_code == 429:
            body_text = r2.text
            body_lower = body_text.lower()
            distinguishable = any(kw in body_lower for kw in [
                "rate limit", "rpm", "tpm", "budget", "limit exceeded",
                "too many", "quota", "429",
            ])
            if distinguishable:
                snippet = body_text.strip()[:120]
                ok(f"Error body contains recognisable rate-limit language: {snippet!r}")
            else:
                # 429 status alone is sufficient per the acceptance criteria
                ok(f"HTTP 429 status is unambiguous. Body: {body_text.strip()[:120]!r}")
        else:
            # If test 2 didn't get a 429, make a fresh call to an intentionally exceeded key
            print("  (Skipped — test 2 did not return 429)")
    except Exception as e:
        fail("Could not inspect 429 response body", str(e))

finally:
    # --- Cleanup: always delete the test key ---

    print()
    print("Cleanup: deleting temporary test key...")
    if test_key:
        try:
            deleted = delete_test_key(test_key)
            if deleted:
                print("  Test key deleted. No interference with subsequent tests.")
            else:
                print("  WARNING: Key deletion returned non-200. Delete manually:")
                print(f"    POST {BASE_URL}/key/delete")
                print(f'    Body: {{"keys": ["{test_key}"]}}')
        except Exception as e:
            print(f"  WARNING: Key deletion failed: {e}")
            print(f"  The key has a 1h auto-expiry as a safety net.")
    else:
        print("  No key to delete.")

# --- Test 4: Regression — master key still routes correctly ---

print()
print("4. Routing regression — master key still works after rate limit test")
try:
    r = requests.post(
        f"{BASE_URL}/chat/completions",
        headers=MASTER_AUTH,
        json={"model": MODEL, "messages": TEST_MESSAGE},
        timeout=TIMEOUT,
    )
    if r.status_code == 200:
        content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        ok(f"Master key routing still working: {content.strip()[:60]!r}")
    else:
        fail(f"HTTP {r.status_code}", r.text[:200])
except Exception as e:
    fail("Regression check failed", str(e))

# --- Summary ---

print()
print("=" * 50)
total = passed + failed
print(f"Results: {passed}/{total} passed", "" if failed == 0 else f"— {failed} FAILED")
print()
print("Next step: fill in config/rate_limiting_options.md.template")
print("with Phase 0 findings and the v1 recommendation.")

sys.exit(0 if failed == 0 else 1)
