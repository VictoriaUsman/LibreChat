#!/usr/bin/env python3
"""
Validates LibreChat routing through LiteLLM and end-to-end streaming against
Phase 0 acceptance criteria (PBI 9126 and PBI 9127).

This script depends on PBI 9125 (LibreChat container running) and
PBI-03-BE / PBI-04-BE (LiteLLM routing configured). Run validate_librechat.py
and validate_litellm_allowlist.py first.

Tests:
  1. LibreChat /api/health confirms it is alive after the LiteLLM switch
  2. LibreChat forwards chat requests to LiteLLM (via the LiteLLM API directly)
  3. Streaming response arrives as SSE chunks, not a single payload
  4. Error from LiteLLM propagates as a non-200 response (not a silent failure)
  5. Model picker returns only LiteLLM-configured models (no direct Azure names)
  6. AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT are no longer set (cleanup check)

NOTE:
  Tests 2–5 call the LiteLLM API directly (using the virtual key) to confirm
  the endpoint LibreChat is configured to use is reachable and behaves correctly.
  Full browser-level streaming validation requires manual Test A in the
  validation protocol (see research doc PBI 9127).

Usage:
  pip install -r requirements.txt
  python validate_librechat_litellm.py

Required environment variables (extend existing .env):
  LIBRECHAT_URL           LibreChat Container App base URL
  LITELLM_URL             LiteLLM gateway base URL
  LITELLM_VIRTUAL_KEY     Scoped virtual key issued by Dev 1 (not the master key)
"""

import os
import sys
import json

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

MODEL_STANDARD = "ROMTech AI Standard"
MODEL_FAST = "ROMTech AI Fast"
NONEXISTENT_MODEL = "azure/model-that-does-not-exist"

missing = [k for k, v in {
    "LIBRECHAT_URL": LIBRECHAT_URL,
    "LITELLM_URL": LITELLM_URL,
    "LITELLM_VIRTUAL_KEY": VIRTUAL_KEY,
}.items() if not v]

if missing:
    print("ERROR: Missing required environment variables:")
    for k in missing:
        print(f"  {k}")
    print("\nExtend scripts/.env with the values above.")
    sys.exit(1)

TIMEOUT = 60
AUTH = {"Authorization": f"Bearer {VIRTUAL_KEY}", "Content-Type": "application/json"}
TEST_MESSAGE = [{"role": "user", "content": "Reply with the single word: OK"}]

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


def warn(label):
    print(f"  WARN  {label}")


def chat(model, stream=False):
    return requests.post(
        f"{LITELLM_URL}/chat/completions",
        headers=AUTH,
        json={"model": model, "messages": TEST_MESSAGE, "stream": stream},
        timeout=TIMEOUT,
        stream=stream,
    )


# --- Header ---

print()
print("LibreChat → LiteLLM Routing and Streaming Validation — PBI 9126 / PBI 9127")
print(f"  LibreChat URL:      {LIBRECHAT_URL}")
print(f"  LiteLLM URL:        {LITELLM_URL}")
print(f"  Virtual key prefix: {VIRTUAL_KEY[:8]}...")
print()

# --- Test 1: LibreChat still healthy after the LiteLLM switch ---

print("1. LibreChat /api/health — still alive after LiteLLM endpoint switch")
try:
    r = requests.get(f"{LIBRECHAT_URL}/api/health", timeout=20)
    if r.status_code == 200:
        ok(f"HTTP 200 — {r.text.strip()[:80]}")
    else:
        fail(f"HTTP {r.status_code}", r.text.strip()[:200])
except requests.exceptions.ConnectionError:
    fail("Connection refused — LibreChat container is not reachable")
except requests.exceptions.Timeout:
    fail("Request timed out")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 2: Virtual key routes to flagship model via LiteLLM ---

print()
print(f'2. LiteLLM virtual key routes correctly — "{MODEL_STANDARD}"')
try:
    r = chat(MODEL_STANDARD)
    if r.status_code == 200:
        content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if content:
            ok(f"Response received: {content.strip()[:80]!r}")
        else:
            fail("HTTP 200 but response content was empty", r.text[:200])
    else:
        fail(f"HTTP {r.status_code}", r.text[:200])
except requests.exceptions.Timeout:
    fail(f"Request timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 3: Streaming response arrives as SSE chunks ---

print()
print(f'3. Streaming response — "{MODEL_STANDARD}" (SSE chunks, not single payload)')
try:
    r = chat(MODEL_STANDARD, stream=True)
    if r.status_code != 200:
        fail(f"HTTP {r.status_code}", r.text[:200])
    else:
        chunks = []
        for line in r.iter_lines():
            if not line or line == b"data: [DONE]":
                continue
            if line.startswith(b"data: "):
                try:
                    delta = json.loads(line[6:]).get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        chunks.append(delta)
                except json.JSONDecodeError:
                    pass

        if not chunks:
            fail("Stream completed but returned no content chunks")
        elif len(chunks) == 1:
            # Single chunk could mean LiteLLM buffered the response
            warn(
                f"Only 1 chunk received — stream may be buffered. "
                f"Content: {''.join(chunks).strip()[:60]!r}. "
                f"Verify in browser Network tab that Content-Type is text/event-stream."
            )
        else:
            assembled = "".join(chunks)
            ok(f"Streamed {len(chunks)} chunks: {assembled.strip()[:80]!r}")
except requests.exceptions.Timeout:
    fail(f"Streaming timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 4: Error propagation — blocked model returns 4xx, not 200 ---

print()
print(f"4. Error propagation — request to blocked model returns 4xx (not silent failure)")
try:
    r = chat(NONEXISTENT_MODEL)
    if r.status_code == 200:
        body = r.json()
        actual = body.get("model", "unknown")
        fail(
            f"HTTP 200 — blocked model was silently accepted",
            f"Response model: {actual!r}. "
            f"LiteLLM may be falling back to a default. Check allowlist config.",
        )
    elif 400 <= r.status_code < 500:
        ok(f"HTTP {r.status_code} — blocked model correctly rejected")
    else:
        fail(f"HTTP {r.status_code} (expected 4xx)", r.text[:200])
except requests.exceptions.Timeout:
    fail(f"Request timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 5: /models returns only LiteLLM-configured model names ---

print()
print("5. /models — only LiteLLM-configured model names are returned (no raw Azure names)")
try:
    r = requests.get(
        f"{LITELLM_URL}/models",
        headers=AUTH,
        timeout=TIMEOUT,
    )
    if r.status_code == 200:
        model_ids = [m.get("id", "") for m in r.json().get("data", [])]
        raw_azure_names = [m for m in model_ids if m.startswith("azure/") or m.startswith("gpt-")]
        expected = [MODEL_STANDARD, MODEL_FAST]
        missing_expected = [m for m in expected if m not in model_ids]

        if raw_azure_names:
            fail(
                f"Raw Azure model names exposed in /models: {raw_azure_names}",
                "These should not be reachable directly. Check LiteLLM allowlist config.",
            )
        elif missing_expected:
            fail(
                f"Expected friendly models not found: {missing_expected}",
                f"Models returned: {model_ids}",
            )
        else:
            ok(f"Model list contains only friendly names: {model_ids}")
    else:
        fail(f"HTTP {r.status_code}", r.text[:200])
except requests.exceptions.Timeout:
    fail(f"Request timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 6: Direct Azure env vars are not set (cleanup check) ---

print()
print("6. Cleanup check — AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT not in environment")
azure_key_set = bool(os.environ.get("AZURE_OPENAI_API_KEY", ""))
azure_endpoint_set = bool(os.environ.get("AZURE_OPENAI_ENDPOINT", ""))

if azure_key_set or azure_endpoint_set:
    still_set = []
    if azure_key_set:
        still_set.append("AZURE_OPENAI_API_KEY")
    if azure_endpoint_set:
        still_set.append("AZURE_OPENAI_ENDPOINT")
    fail(
        f"These env vars are still set in the script environment: {still_set}",
        "Remove them from the Container App environment after the LiteLLM switch "
        "to ensure all traffic flows through LiteLLM. "
        "(This check is against the script's local .env — also verify in the ACA portal.)",
    )
else:
    ok("Neither AZURE_OPENAI_API_KEY nor AZURE_OPENAI_ENDPOINT is set in the local environment")

# --- Manual test reminders ---

print()
print("Manual validation still required (see PBI 9127 validation protocol):")
print("  Test A — Open browser, send a long prompt, inspect Network tab for text/event-stream")
print("  Test B — Set model to a non-existent name, confirm error message appears in UI")
print("  Test C — Open an old conversation, send a follow-up, inspect outgoing payload for history")

# --- Summary ---

print()
print("=" * 55)
total = passed + failed
print(f"Results: {passed}/{total} passed", "" if failed == 0 else f"— {failed} FAILED")
print()

if failed == 0:
    print("LiteLLM routing and streaming validated.")
    print("Next steps: PBI 9128 (persistence), PBI 9129 (Okta).")

sys.exit(0 if failed == 0 else 1)
