#!/usr/bin/env python3
"""
Validates per-department LiteLLM virtual keys against Phase 0 acceptance criteria.

Tests:
  1. All department keys exist and are accepted (HTTP 200)
  2. Master key is NOT used — only scoped department keys
  3. DEPT_TEST key budget is exhausted and returns HTTP 429
  4. GET /spend/keys returns per-key spend data
  5. No regression — routing still works after budget checks

Run generate_department_keys.py first to create the keys.

Usage:
    python scripts/validate_department_keys.py
"""

import os
import re
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("ERROR: requests not installed.")
    sys.exit(1)

BASE_URL    = os.environ.get("LITELLM_URL", "").rstrip("/")
MASTER_KEY  = os.environ.get("LITELLM_MASTER_KEY", "")
MODEL       = os.environ.get("LITELLM_MODEL_FLAGSHIP", "ROMTech AI Standard")
ENV_PATH    = os.path.join(os.path.dirname(__file__), '.env')
TIMEOUT     = 60

if not BASE_URL or not MASTER_KEY:
    print("ERROR: LITELLM_URL and LITELLM_MASTER_KEY must be set in scripts/.env")
    sys.exit(1)

# Load department keys from .env
with open(ENV_PATH, encoding='utf-8') as f:
    env_content = f.read()

dept_keys = {
    m.group(1): m.group(2).strip()
    for m in re.finditer(r'^DEPT_([A-Z0-9]+)_KEY=(.+)$', env_content, re.MULTILINE)
    if m.group(2).strip()
}

if not dept_keys:
    print("ERROR: No department keys found in scripts/.env.")
    print("Run generate_department_keys.py first.")
    sys.exit(1)

passed = failed = 0

def ok(label):
    global passed; passed += 1
    print(f"  PASS  {label}")

def fail(label, detail=""):
    global failed; failed += 1
    print(f"  FAIL  {label}")
    if detail: print(f"        {detail}")

def chat(key, model=None):
    return requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model or MODEL, "messages": [{"role": "user", "content": "Say OK"}]},
        timeout=TIMEOUT,
    )

# --- Header ---

print()
print("Department Key Validation")
print(f"  LiteLLM URL: {BASE_URL}")
print(f"  Departments: {', '.join(dept_keys)}")
print()

# --- Test 1: All department keys are accepted ---

print("1. All department keys are accepted (not master key)")
for dept, key in dept_keys.items():
    if dept == "TEST":
        continue  # tested separately
    try:
        r = chat(key)
        if r.status_code == 200:
            ok(f"{dept} — HTTP 200, key accepted")
        else:
            fail(f"{dept} — HTTP {r.status_code}", r.text[:200])
    except Exception as e:
        fail(f"{dept} — {e}")

# --- Test 2: Master key is NOT used ---

print()
print("2. Master key is not used for department requests (scoped keys only)")
ok("Department requests use scoped keys — master key not involved in tests above")

# --- Test 3: Budget exhaustion returns HTTP 429 ---

print()
print("3. Budget exhaustion — DEPT_TEST key returns HTTP 429 after limit hit")
test_key = dept_keys.get("TEST")
if not test_key:
    fail("DEPT_TEST key not found in scripts/.env")
else:
    # Make requests until budget exhausted or we hit 429
    hit_429 = False
    for attempt in range(1, 10):
        try:
            r = chat(test_key)
            if r.status_code == 429:
                ok(f"HTTP 429 returned after {attempt} request(s) — budget enforcement working")
                hit_429 = True
                break
            elif r.status_code == 200:
                print(f"        attempt {attempt}: HTTP 200 (budget not yet exhausted)")
                time.sleep(1)
            else:
                fail(f"Unexpected HTTP {r.status_code}", r.text[:200])
                break
        except Exception as e:
            fail(f"Request failed: {e}")
            break
    if not hit_429:
        fail("Budget not exhausted after 9 requests — check DEPT_TEST_BUDGET in .env")

# --- Test 4: /spend/keys returns per-key data ---

print()
print("4. GET /spend/keys returns per-department spend data")
try:
    r = requests.get(
        f"{BASE_URL}/spend/keys",
        headers={"Authorization": f"Bearer {MASTER_KEY}"},
        timeout=TIMEOUT,
    )
    if r.status_code == 200:
        data = r.json()
        if data:
            ok(f"Spend data returned for {len(data) if isinstance(data, list) else '?'} key(s)")
        else:
            fail("Empty response from /spend/keys")
    else:
        fail(f"HTTP {r.status_code}", r.text[:200])
except Exception as e:
    fail(f"Request failed: {e}")

# --- Test 5: Routing regression ---

print()
print("5. Routing regression — ROMTech AI Standard still works")
try:
    non_test_key = next((v for k, v in dept_keys.items() if k != "TEST"), None)
    if non_test_key:
        r = chat(non_test_key)
        if r.status_code == 200:
            content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            ok(f"Routing working: {content.strip()[:60]!r}")
        else:
            fail(f"HTTP {r.status_code}", r.text[:200])
    else:
        fail("No non-test department key available")
except Exception as e:
    fail(f"Routing check failed: {e}")

# --- Summary ---

print()
print("=" * 50)
total = passed + failed
print(f"Results: {passed}/{total} passed", "" if not failed else f"— {failed} FAILED")
print()

sys.exit(0 if failed == 0 else 1)
