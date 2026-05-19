#!/usr/bin/env python3
"""
Validates LiteLLM usage tracking and cost visibility against Phase 0
acceptance criteria (PBI-05-BE). Corresponds to Section 4G of the Phase 0 plan.

This script depends on PBI-03-BE. Run validate_litellm_routing.py first.

What this script checks:
  1. Token usage (prompt + completion tokens) appears in /spend/logs after a request
  2. Usage is attributable to the model used
  3. /spend/models returns a per-model breakdown
  4. A request with a "user" field is attributed in the spend log
  5. /spend/keys returns per-virtual-key usage
  6. Cost estimate fields are present (or absent) in log entries

NOTE — Database dependency:
  LiteLLM's /spend/* API endpoints require a PostgreSQL database
  (DATABASE_URL env var). Without it, spend data is in-memory only and
  the API endpoints may return empty results or 500 errors.
  Container stdout logs ALWAYS contain token usage regardless of database config.
  This script handles missing DB gracefully and reports it as a finding.

Usage:
  pip install -r requirements.txt
  python validate_litellm_usage.py

Required environment variables (same .env as previous scripts):
  LITELLM_URL
  LITELLM_MASTER_KEY
  LITELLM_MODEL_FLAGSHIP   e.g. "ROMTech AI Standard"
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
TEST_USER = "phase0-test-user@romtech.com"

missing = [k for k, v in {
    "LITELLM_URL": BASE_URL,
    "LITELLM_MASTER_KEY": MASTER_KEY,
}.items() if not v]

if missing:
    print("ERROR: Missing required environment variables:")
    for k in missing:
        print(f"  {k}")
    sys.exit(1)

TIMEOUT = 60
AUTH = {"Authorization": f"Bearer {MASTER_KEY}", "Content-Type": "application/json"}

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


def get(path):
    return requests.get(f"{BASE_URL}{path}", headers=AUTH, timeout=TIMEOUT)


def post_chat(extra=None):
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Reply with the single word: OK"}],
    }
    if extra:
        body.update(extra)
    return requests.post(f"{BASE_URL}/chat/completions", headers=AUTH, json=body, timeout=TIMEOUT)


# --- Header ---

print()
print("LiteLLM Usage Tracking and Cost Visibility Assessment")
print(f"  LiteLLM URL: {BASE_URL}")
print(f"  Test model:  {MODEL}")
print(f"  Test user:   {TEST_USER}")
print()

# --- Step 1: Make a baseline request and a user-attributed request ---

print("Sending test requests...")
r1 = post_chat()
r2 = post_chat({"user": TEST_USER})

if r1.status_code != 200 or r2.status_code != 200:
    print(f"  ERROR: Test requests failed (HTTP {r1.status_code}, {r2.status_code}).")
    print("  Run validate_litellm_routing.py first to confirm routing is working.")
    sys.exit(1)

print(f"  Requests sent. Waiting 3s for spend data to be recorded...")
time.sleep(3)
print()

# --- Test 1 & 2: Token usage in spend logs ---

print("1. Token usage (prompt + completion tokens) visible in /spend/logs")
try:
    r = get("/spend/logs")
    if r.status_code == 200:
        logs = r.json()
        if not logs:
            finding("No spend log entries returned — database may not be configured (in-memory only)")
        else:
            sample = logs[0] if isinstance(logs, list) else logs
            prompt_tokens = sample.get("prompt_tokens") or sample.get("usage", {}).get("prompt_tokens")
            completion_tokens = sample.get("completion_tokens") or sample.get("usage", {}).get("completion_tokens")
            if prompt_tokens is not None and completion_tokens is not None:
                ok(f"Token counts present — prompt: {prompt_tokens}, completion: {completion_tokens}")
            else:
                finding(f"Log entry found but token fields missing. Keys present: {list(sample.keys())}")
    elif r.status_code in (500, 501, 503):
        finding("/spend/logs returned server error — PostgreSQL database likely not configured")
    else:
        finding(f"/spend/logs returned HTTP {r.status_code}")
except Exception as e:
    finding(f"/spend/logs request failed: {e}")

# --- Test 3: Per-model breakdown ---

print()
print("2. Usage breakdown by model in /spend/models")
try:
    r = get("/spend/models")
    if r.status_code == 200:
        data = r.json()
        if data:
            models_seen = [entry.get("model") for entry in (data if isinstance(data, list) else [data])]
            ok(f"Per-model data returned. Models: {models_seen}")
        else:
            finding("/spend/models returned empty — database may not be configured")
    elif r.status_code in (500, 501, 503):
        finding("/spend/models returned server error — PostgreSQL database likely not configured")
    else:
        finding(f"/spend/models returned HTTP {r.status_code}")
except Exception as e:
    finding(f"/spend/models request failed: {e}")

# --- Test 4: User attribution ---

print()
print(f'3. User attribution — request sent with "user": "{TEST_USER}"')
try:
    r = get("/spend/logs")
    if r.status_code == 200:
        logs = r.json()
        if isinstance(logs, list):
            user_logs = [l for l in logs if l.get("user") == TEST_USER or TEST_USER in str(l)]
            if user_logs:
                ok(f"Found {len(user_logs)} log entry/entries attributed to test user")
            else:
                finding(f'No log entries attributed to "{TEST_USER}" — user field may not be indexed or DB not configured')
        else:
            finding("Unexpected /spend/logs response format")
    elif r.status_code in (500, 501, 503):
        finding("Cannot verify user attribution — database likely not configured")
    else:
        finding(f"/spend/logs returned HTTP {r.status_code}")
except Exception as e:
    finding(f"User attribution check failed: {e}")

# --- Test 5: Per-key breakdown ---

print()
print("4. Usage breakdown by virtual key in /spend/keys")
try:
    r = get("/spend/keys")
    if r.status_code == 200:
        data = r.json()
        if data:
            ok(f"Per-key data returned ({len(data) if isinstance(data, list) else 1} key(s))")
        else:
            finding("/spend/keys returned empty — database may not be configured")
    elif r.status_code in (500, 501, 503):
        finding("/spend/keys returned server error — PostgreSQL database likely not configured")
    else:
        finding(f"/spend/keys returned HTTP {r.status_code}")
except Exception as e:
    finding(f"/spend/keys request failed: {e}")

# --- Test 6: Cost estimate fields ---

print()
print("5. Cost estimate fields present in spend log entries")
try:
    r = get("/spend/logs")
    if r.status_code == 200:
        logs = r.json()
        if isinstance(logs, list) and logs:
            sample = logs[0]
            cost_field = sample.get("spend") or sample.get("cost") or sample.get("estimated_cost")
            if cost_field is not None:
                ok(f"Cost field present in log entry: {cost_field}")
            else:
                finding(f"No cost/spend field in log entry. Keys: {list(sample.keys())}")
        else:
            finding("No log entries to inspect for cost fields")
    elif r.status_code in (500, 501, 503):
        finding("Cannot inspect cost fields — database likely not configured")
    else:
        finding(f"/spend/logs returned HTTP {r.status_code}")
except Exception as e:
    finding(f"Cost field check failed: {e}")

# --- Regression: Routing still works ---

print()
print("6. Routing regression — confirm routing still works after usage checks")
try:
    r = post_chat()
    if r.status_code == 200:
        content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        ok(f"Routing still working: {content.strip()[:60]!r}")
    else:
        fail(f"HTTP {r.status_code}", r.text[:200])
except Exception as e:
    fail("Routing regression check failed", str(e))

# --- Summary ---

print()
print("=" * 55)
total = passed + failed
print(f"Results: {passed}/{total} passed", "" if failed == 0 else f"— {failed} FAILED")

if findings:
    print()
    print("Findings (record these in usage_tracking_assessment.md):")
    for i, f_text in enumerate(findings, 1):
        print(f"  [{i}] {f_text}")

print()
print("Next step: fill in config/usage_tracking_assessment.md.template")
print("with observations from this run and the LiteLLM dashboard.")

sys.exit(0 if failed == 0 else 1)
