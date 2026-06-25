#!/usr/bin/env python3
"""
Validates the LiteLLM telemetry callback against Phase 0 acceptance criteria (PBI-XX-BE).

Tests (automated):
  1. Callback class is importable and instantiates without error
  2. _build_payload() returns all required fields with correct types
  3. Payload contains NO message content fields (department, model only -- no messages/content)
  4. TELEMETRY_ENDPOINT_URL is present in environment (may be blank -- that is valid)
  5. LiteLLM is reachable and routing is unaffected (regression check)
  6. After a live request, stdout shows the [AIUsageCallback] JSON line
     (manual verification -- the script prints what to look for)

Test 6 requires manual inspection of the LiteLLM process stdout.
The automated tests (1-5) can pass without a running LiteLLM instance.

Usage:
  pip install -r requirements.txt
  python validate_telemetry_callback.py

Required environment variables (scripts/.env):
  LITELLM_URL         e.g. http://localhost:4000
  LITELLM_MASTER_KEY  LiteLLM admin key
  LITELLM_MODEL_FLAGSHIP  e.g. "ROMTech AI Standard"

Optional:
  TELEMETRY_ENDPOINT_URL  blank for local mode, URL for live forwarding (PBI-12-BE)
"""

import json
import os
import sys
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

LITELLM_URL = os.environ.get("LITELLM_URL", "").rstrip("/")
MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
MODEL = os.environ.get("LITELLM_MODEL_FLAGSHIP", "ROMTech AI Standard")
TELEMETRY_URL = os.environ.get("TELEMETRY_ENDPOINT_URL", "")

REQUIRED_PAYLOAD_FIELDS = {
    "department": str,
    "model": str,
    "input_tokens": int,
    "output_tokens": int,
    "estimated_cost_usd": float,
    "timestamp": str,
}

BANNED_PAYLOAD_FIELDS = {
    "messages", "content", "prompt", "text", "response",
    "choices", "role", "system", "user_message", "assistant_message",
}

TIMEOUT = 30
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


def note(label):
    print(f"  NOTE  {label}")


# --- Header ---

print()
print("Telemetry Callback Validation -- PBI-XX-BE")
print()

# --- Test 1: Callback class is importable ---

print("1. Callback class is importable and instantiates")
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config"))
    from callbacks.litellm_usage_callback import AIUsageCallback, proxy_handler_instance
    cb = AIUsageCallback()
    ok("AIUsageCallback imported and instantiated from callbacks/litellm_usage_callback.py")
except ImportError as e:
    fail("Could not import AIUsageCallback", str(e))
    print()
    print("  Ensure you are running this script from the project root or that the")
    print("  'callbacks' package directory is on the Python path.")
    sys.exit(1)

# --- Test 2: _build_payload returns all required fields with correct types ---

print()
print("2. _build_payload() returns correct payload shape (mock data)")

# Construct a mock response_obj that mimics litellm.ModelResponse.usage
class _MockUsage:
    prompt_tokens = 25
    completion_tokens = 10

class _MockResponse:
    usage = _MockUsage()

mock_kwargs = {
    "model": "azure/website-chatbot-gpt-4o-mini",
    "metadata": {
        "model_group": "ROMTech AI Standard",
        "user_api_key_team_id": "engineering",
    },
    "response_cost": 0.0000054,
}
mock_end_time = datetime.now(timezone.utc)

try:
    payload = cb._build_payload(mock_kwargs, _MockResponse(), mock_end_time)

    all_good = True
    for field, expected_type in REQUIRED_PAYLOAD_FIELDS.items():
        value = payload.get(field)
        if value is None:
            fail(f"Required field missing from payload: '{field}'")
            all_good = False
        elif not isinstance(value, expected_type):
            fail(
                f"Field '{field}' has wrong type",
                f"Expected {expected_type.__name__}, got {type(value).__name__}: {value!r}",
            )
            all_good = False

    if all_good:
        ok("All required fields present with correct types")
        print(f"        Payload: {json.dumps(payload, separators=(',', ':'))}")

except Exception as e:
    fail("_build_payload raised an exception", str(e))

# --- Test 3: Payload does NOT contain message content ---

print()
print("3. Payload contains NO message content (data governance check)")
try:
    leaked = BANNED_PAYLOAD_FIELDS & set(payload.keys())
    if leaked:
        fail(
            f"Content fields found in payload: {leaked}",
            "The callback must emit usage metadata only -- no message content.",
        )
    else:
        ok(f"No content fields in payload -- {sorted(payload.keys())} only")
except NameError:
    fail("Payload not available -- Test 2 must pass first")

# --- Test 3b: Verify department extraction logic ---

print()
print("3b. Department derived from virtual key team_id (not from message content)")
try:
    dept = payload.get("department")
    if dept == "engineering":
        ok(f"department = {dept!r} (correctly derived from user_api_key_team_id)")
    else:
        fail(f"Expected department='engineering', got {dept!r}")

    # Test fallback: no team_id in metadata
    fallback_kwargs = {"model": "ROMTech AI Standard", "metadata": {}, "response_cost": 0.0}
    fallback_payload = cb._build_payload(fallback_kwargs, _MockResponse(), mock_end_time)
    if fallback_payload.get("department") == "unknown":
        ok("department = 'unknown' when no team_id present (correct fallback)")
    else:
        fail(f"Expected fallback department='unknown', got {fallback_payload.get('department')!r}")
except Exception as e:
    fail("Department extraction test failed", str(e))

# --- Test 4: TELEMETRY_ENDPOINT_URL is present in environment ---

print()
print("4. TELEMETRY_ENDPOINT_URL present in environment (may be blank)")
if "TELEMETRY_ENDPOINT_URL" in os.environ:
    if TELEMETRY_URL:
        ok(f"TELEMETRY_ENDPOINT_URL is set: {TELEMETRY_URL}")
        note("Live forwarding mode active -- callback will POST to this URL after each request")
    else:
        ok("TELEMETRY_ENDPOINT_URL is present and blank (local stdout-only mode -- expected for Phase 0)")
else:
    fail(
        "TELEMETRY_ENDPOINT_URL is not in environment at all",
        "Add TELEMETRY_ENDPOINT_URL= to scripts/.env (blank is valid for local mode)",
    )

# --- Test 5: LiteLLM routing regression ---

print()
print("5. LiteLLM routing regression -- chat endpoint unaffected by callback registration")
if not LITELLM_URL or not MASTER_KEY:
    note("LITELLM_URL or LITELLM_MASTER_KEY not set -- skipping live regression check")
    note("Set both in scripts/.env to run the full validation suite")
else:
    try:
        r = requests.post(
            f"{LITELLM_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {MASTER_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": "Reply: OK"}],
            },
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            content = (
                r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            ok(f"HTTP 200 -- routing unaffected: {content.strip()[:60]!r}")
        else:
            fail(f"HTTP {r.status_code}", r.text[:200])
    except requests.exceptions.ConnectionError:
        note("LiteLLM is not running -- skipping regression check")
        note("Start LiteLLM from the project root and re-run to complete Test 5")
    except Exception as e:
        fail("Regression check failed", str(e))

# --- Test 6: Manual stdout verification ---

print()
print("6. Callback stdout output -- MANUAL VERIFICATION REQUIRED")
print()
print("  After a live request reaches LiteLLM, the callback logs a JSON line to stdout.")
print("  Look for this pattern in the LiteLLM process terminal:")
print()
print('  [AIUsageCallback] {"department":"...","model":"ROMTech AI Standard",')
print('                     "input_tokens":N,"output_tokens":N,')
print('                     "estimated_cost_usd":N.NNNNNNNN,"timestamp":"...Z"}')
print()
print("  PASS criteria:")
print("    - Line starts with [AIUsageCallback]")
print("    - All 6 fields are present")
print("    - 'department' matches the team_id of the virtual key used")
print("    - 'model' is the user-facing alias (ROMTech AI Standard / Fast)")
print("    - No 'messages', 'content', 'choices', or similar content fields")
print()
print("  To trigger: send any chat request through LiteLLM with the callback registered.")

# --- Summary ---

print()
print("=" * 55)
total = passed + failed
print(f"Automated results: {passed}/{total} passed", "" if failed == 0 else f"-- {failed} FAILED")
print()

if failed == 0:
    print("Automated checks passed. Complete manual Test 6 against a running LiteLLM")
    print("instance to sign off PBI-XX-BE.")
else:
    print("One or more checks failed. Resolve the failures above before proceeding.")

sys.exit(0 if failed == 0 else 1)
