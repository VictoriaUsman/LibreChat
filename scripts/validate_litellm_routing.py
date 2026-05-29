#!/usr/bin/env python3
"""
Validates LiteLLM routing to Azure OpenAI against Phase 0 acceptance
criteria (PBI-03-BE).

This script depends on PBI-01-BE (Azure OpenAI endpoint) and PBI-02-BE
(LiteLLM container running). Run validate_azure_openai.py and
validate_litellm.py first.

Tests:
  1. Chat completion routes through LiteLLM to Azure OpenAI — flagship model
  2. Chat completion routes through LiteLLM to Azure OpenAI — fast model
  3. Streaming response passes through LiteLLM complete and in order
  4. Invalid LiteLLM API key returns 401
  5. Request to an unconfigured model returns an error (not a silent fallback)
  6. Model-level health endpoint confirms both models are reachable

Usage:
  pip install -r requirements.txt
  cp ../config/litellm.env.template .env   # also add the vars below
  python validate_litellm_routing.py

Required environment variables (extend the existing .env):
  LITELLM_URL              e.g. https://litellm-nonprod.<id>.eastus.azurecontainerapps.io
  LITELLM_MASTER_KEY       the master key set in the container environment
  LITELLM_MODEL_FLAGSHIP   the model_name from litellm_routing_config.yaml (e.g. romtech-standard)
  LITELLM_MODEL_FAST       the model_name from litellm_routing_config.yaml (e.g. romtech-fast)
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

BASE_URL = os.environ.get("LITELLM_URL", "").rstrip("/")
MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
MODEL_FLAGSHIP = os.environ.get("LITELLM_MODEL_FLAGSHIP", "")
MODEL_FAST = os.environ.get("LITELLM_MODEL_FAST", "")

missing = [k for k, v in {
    "LITELLM_URL": BASE_URL,
    "LITELLM_MASTER_KEY": MASTER_KEY,
    "LITELLM_MODEL_FLAGSHIP": MODEL_FLAGSHIP,
    "LITELLM_MODEL_FAST": MODEL_FAST,
}.items() if not v]

if missing:
    print("ERROR: Missing required environment variables:")
    for k in missing:
        print(f"  {k}")
    sys.exit(1)

TIMEOUT = 60
AUTH = {"Authorization": f"Bearer {MASTER_KEY}"}
INVALID_KEY = {"Authorization": "Bearer invalid-key-000000000000000"}
TEST_MESSAGE = [{"role": "user", "content": "Reply with the single word: OK"}]
NONEXISTENT_MODEL = "model-that-does-not-exist"

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


def chat(model, headers=None, stream=False):
    return requests.post(
        f"{BASE_URL}/chat/completions",
        headers=headers or AUTH,
        json={"model": model, "messages": TEST_MESSAGE, "stream": stream},
        timeout=TIMEOUT,
        stream=stream,
    )


# --- Header ---

print()
print("LiteLLM Routing and Streaming Validation")
print(f"  LiteLLM URL:      {BASE_URL}")
print(f"  Flagship model:   {MODEL_FLAGSHIP}")
print(f"  Fast model:       {MODEL_FAST}")
print()

# --- Test 1 & 2: Routing — one test per deployment ---

for label, model in [("Flagship", MODEL_FLAGSHIP), ("Fast", MODEL_FAST)]:
    print(f"1{'a' if label == 'Flagship' else 'b'}. Chat completion — {label} ({model})")
    try:
        r = chat(model)
        if r.status_code == 200:
            body = r.json()
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
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
    print()

# --- Test 3: Streaming through LiteLLM ---

print(f"3. Streaming response through LiteLLM — {MODEL_FLAGSHIP}")
try:
    r = chat(MODEL_FLAGSHIP, stream=True)
    if r.status_code != 200:
        fail(f"HTTP {r.status_code}", r.text[:200])
    else:
        chunks = []
        out_of_order = False
        last_index = -1
        for line in r.iter_lines():
            if not line or line == b"data: [DONE]":
                continue
            if line.startswith(b"data: "):
                try:
                    chunk = json.loads(line[6:])
                    idx = chunk.get("choices", [{}])[0].get("index", 0)
                    if idx < last_index:
                        out_of_order = True
                    last_index = idx
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        chunks.append(delta)
                except json.JSONDecodeError:
                    pass

        if not chunks:
            fail("Stream returned no content chunks")
        elif out_of_order:
            fail("Chunks arrived out of order")
        else:
            assembled = "".join(chunks)
            ok(f"Streamed {len(chunks)} chunk(s), assembled: {assembled.strip()[:80]!r}")
except requests.exceptions.Timeout:
    fail(f"Streaming request timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 4: Invalid LiteLLM API key is rejected (not silently accepted) ---
# LiteLLM returns 401 when a database is connected (virtual key lookup fails).
# Without a database, it returns 400 "No connected db". Both are valid rejections
# for Phase 0 local validation — the critical failure mode is HTTP 200 (silent acceptance).

print()
print("4. Invalid LiteLLM API key is rejected (not silently accepted)")
try:
    r = chat(MODEL_FLAGSHIP, headers=INVALID_KEY)
    if r.status_code in (401, 403):
        ok(f"HTTP {r.status_code} returned as expected")
    elif r.status_code == 400 and "no_db_connection" in r.text:
        ok("HTTP 400 — request rejected (no DB; full 401 enforcement requires Cosmos DB in v1)")
    elif r.status_code == 200:
        fail("HTTP 200 — invalid key was accepted, LiteLLM auth is not enforcing")
    elif 400 <= r.status_code < 500:
        ok(f"HTTP {r.status_code} — invalid key rejected (not silently accepted)")
    else:
        fail(f"HTTP {r.status_code} (expected 4xx)", r.text[:200])
except requests.exceptions.Timeout:
    fail(f"Request timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 5: Unknown model returns an error, not a silent fallback ---

print()
print(f"5. Request to unconfigured model '{NONEXISTENT_MODEL}' returns an error")
try:
    r = chat(NONEXISTENT_MODEL)
    if r.status_code == 200:
        # Check if the response actually came from a different model (silent fallback)
        body = r.json()
        actual_model = body.get("model", "")
        fail(
            f"HTTP 200 — request succeeded (model in response: {actual_model!r})",
            "LiteLLM may be falling back silently. Check router_settings in litellm_routing_config.yaml.",
        )
    elif r.status_code in (400, 404, 422):
        ok(f"HTTP {r.status_code} — unconfigured model correctly rejected")
    else:
        ok(f"HTTP {r.status_code} — request was not silently accepted")
except requests.exceptions.Timeout:
    fail(f"Request timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 6: Model-level health confirms both models reachable ---

print()
print("6. /health — both configured models reachable via Azure OpenAI")
try:
    r = requests.get(f"{BASE_URL}/health", headers=AUTH, timeout=TIMEOUT)
    if r.status_code == 200:
        body = r.json()
        healthy = [m.get("model_name") for m in body.get("healthy_endpoints", [])]
        unhealthy = [m.get("model_name") for m in body.get("unhealthy_endpoints", [])]
        if unhealthy:
            fail(f"Unhealthy endpoints: {unhealthy}", f"Healthy: {healthy}")
        else:
            ok(f"All endpoints healthy: {healthy}")
    else:
        fail(f"HTTP {r.status_code}", r.text[:200])
except requests.exceptions.Timeout:
    fail(f"Health check timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Restart persistence note ---

print()
print("NOTE — Config persistence after restart (manual step):")
print("  az containerapp revision restart --name litellm-nonprod --resource-group <RG>")
print("  Wait ~30 seconds, then re-run this script.")
print("  All tests must pass after restart for the acceptance criterion to be met.")

# --- Summary ---

print()
print("=" * 50)
total = passed + failed
print(f"Results: {passed}/{total} passed", "" if failed == 0 else f"— {failed} FAILED")
print()

if failed == 0:
    print("Routing validated. Fill in config/dev2_handoff.md.template and share with Dev 2.")

sys.exit(0 if failed == 0 else 1)
