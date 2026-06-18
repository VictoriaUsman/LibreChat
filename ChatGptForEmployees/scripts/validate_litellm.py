#!/usr/bin/env python3
"""
Validates the LiteLLM Azure Container Apps deployment against Phase 0
acceptance criteria (PBI-02-BE).

NOTE: This script validates container health only.
Routing to Azure OpenAI and streaming are validated in PBI-03-BE.

Tests:
  1. /health/liveliness returns 200 — container process is alive
  2. /health/readiness  returns 200 — server is accepting requests
  3. Authenticated request accepted (valid master key)
  4. Unauthenticated request rejected (no key → 401 or 403)

Usage:
  pip install -r requirements.txt
  cp ../config/litellm.env.template .env   # fill in LITELLM_URL and LITELLM_MASTER_KEY
  python validate_litellm.py

Required environment variables (or .env file in this directory):
  LITELLM_URL          e.g. https://litellm-nonprod.<id>.eastus.azurecontainerapps.io
  LITELLM_MASTER_KEY   the master key set in the container environment
"""

import os
import sys

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

missing = [k for k, v in {
    "LITELLM_URL": BASE_URL,
    "LITELLM_MASTER_KEY": MASTER_KEY,
}.items() if not v]

if missing:
    print("ERROR: Missing required environment variables:")
    for k in missing:
        print(f"  {k}")
    print("\nCopy config/litellm.env.template to scripts/.env and fill in the values.")
    sys.exit(1)

TIMEOUT = 15  # seconds

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


# --- Header ---

print()
print("LiteLLM Container Health Validation")
print(f"  URL: {BASE_URL}")
print()

# --- Test 1: Liveliness ---

print("1. /health/liveliness — container process is alive")
try:
    r = requests.get(f"{BASE_URL}/health/liveliness", timeout=TIMEOUT)
    if r.status_code == 200:
        ok(f"HTTP 200 — {r.text.strip()[:80]}")
    else:
        fail(f"HTTP {r.status_code}", r.text.strip()[:200])
except requests.exceptions.ConnectionError:
    fail("Connection refused — is the Container App deployed and running?")
except requests.exceptions.Timeout:
    fail(f"Request timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 2: Readiness ---

print("\n2. /health/readiness — server is accepting requests")
try:
    r = requests.get(f"{BASE_URL}/health/readiness", timeout=TIMEOUT)
    if r.status_code == 200:
        ok(f"HTTP 200 — {r.text.strip()[:80]}")
    else:
        fail(f"HTTP {r.status_code}", r.text.strip()[:200])
except requests.exceptions.ConnectionError:
    fail("Connection refused")
except requests.exceptions.Timeout:
    fail(f"Request timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 3: Authenticated request accepted ---

print("\n3. Valid master key is accepted")
try:
    r = requests.get(
        f"{BASE_URL}/health",
        headers={"Authorization": f"Bearer {MASTER_KEY}"},
        timeout=TIMEOUT,
    )
    # /health returns 200 if models are configured, or a non-200 status if no models
    # are set up yet — both are acceptable at this stage (routing is PBI-03-BE).
    # What matters here is that we do NOT get a 401/403.
    if r.status_code in (401, 403):
        fail(f"HTTP {r.status_code} — master key was rejected", r.text.strip()[:200])
    else:
        ok(f"HTTP {r.status_code} — key accepted (model routing status is PBI-03-BE scope)")
except requests.exceptions.ConnectionError:
    fail("Connection refused")
except requests.exceptions.Timeout:
    fail(f"Request timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 4: Unauthenticated request rejected ---

print("\n4. Missing auth header returns 401 or 403 (not silently accepted)")
try:
    r = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
    if r.status_code in (401, 403):
        ok(f"HTTP {r.status_code} — unauthenticated request rejected as expected")
    elif r.status_code == 200:
        fail(
            "HTTP 200 — unauthenticated request was accepted",
            "Verify LITELLM_MASTER_KEY is set in the container environment",
        )
    else:
        fail(f"Unexpected HTTP {r.status_code}", r.text.strip()[:200])
except requests.exceptions.ConnectionError:
    fail("Connection refused")
except requests.exceptions.Timeout:
    fail(f"Request timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Restart note ---

print()
print("NOTE — Clean restart verification (manual step):")
print("  az containerapp revision restart --name litellm-nonprod --resource-group <RG>")
print("  Then re-run this script and confirm all tests still pass.")

# --- Summary ---

print()
print("=" * 42)
total = passed + failed
print(f"Results: {passed}/{total} passed", "" if failed == 0 else f"— {failed} FAILED")
print()

sys.exit(0 if failed == 0 else 1)
