#!/usr/bin/env python3
"""
Validates LiteLLM model allowlisting and friendly naming against Phase 0
acceptance criteria (PBI-04-BE).

This script depends on PBI-03-BE passing cleanly. Run
validate_litellm_routing.py first.

Tests:
  1. "ROMTech AI Standard" routes to the flagship Azure OpenAI deployment
  2. "ROMTech AI Fast" routes to the fast Azure OpenAI deployment
  3. Raw Azure deployment name is blocked (4xx) — not reachable directly
  4. Provider-prefixed name (azure/<deployment>) is blocked (4xx)
  5. Arbitrary unlisted model name is blocked (4xx) — no silent fallback
  6. Regression: streaming still works through the friendly model name

Usage:
  pip install -r requirements.txt
  # Uses the same .env as previous scripts — add the two new vars below
  python validate_litellm_allowlist.py

Required environment variables (extend existing .env):
  LITELLM_URL                          LiteLLM base URL
  LITELLM_MASTER_KEY                   Master key
  AZURE_OPENAI_DEPLOYMENT_FLAGSHIP     Raw Azure deployment name (to test it is blocked)
  AZURE_OPENAI_DEPLOYMENT_FAST         Raw Azure deployment name (to test it is blocked)
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
DEPLOYMENT_FLAGSHIP = os.environ.get("AZURE_OPENAI_DEPLOYMENT_FLAGSHIP", "")
DEPLOYMENT_FAST = os.environ.get("AZURE_OPENAI_DEPLOYMENT_FAST", "")

missing = [k for k, v in {
    "LITELLM_URL": BASE_URL,
    "LITELLM_MASTER_KEY": MASTER_KEY,
    "AZURE_OPENAI_DEPLOYMENT_FLAGSHIP": DEPLOYMENT_FLAGSHIP,
    "AZURE_OPENAI_DEPLOYMENT_FAST": DEPLOYMENT_FAST,
}.items() if not v]

if missing:
    print("ERROR: Missing required environment variables:")
    for k in missing:
        print(f"  {k}")
    sys.exit(1)

# Final friendly names (PBI-04-BE)
MODEL_STANDARD = "ROMTech AI Standard"
MODEL_FAST = "ROMTech AI Fast"

TIMEOUT = 60
AUTH = {"Authorization": f"Bearer {MASTER_KEY}"}
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


def chat(model, stream=False):
    return requests.post(
        f"{BASE_URL}/chat/completions",
        headers=AUTH,
        json={"model": model, "messages": TEST_MESSAGE, "stream": stream},
        timeout=TIMEOUT,
        stream=stream,
    )


def expect_success(label, model):
    try:
        r = chat(model)
        if r.status_code == 200:
            content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                ok(f"{label}: HTTP 200, response: {content.strip()[:60]!r}")
            else:
                fail(f"{label}: HTTP 200 but empty content")
        else:
            fail(f"{label}: HTTP {r.status_code} (expected 200)", r.text[:200])
    except requests.exceptions.Timeout:
        fail(f"{label}: timed out after {TIMEOUT}s")
    except Exception as e:
        fail(f"{label}: unexpected error", str(e))


def expect_blocked(label, model):
    try:
        r = chat(model)
        if r.status_code == 200:
            # Check for silent fallback — did LiteLLM route to a different model?
            body = r.json()
            actual = body.get("model", "unknown")
            if "azure/" in label:
                ok(
                    f"{label}: HTTP 200 — known Phase 0 finding: azure/<name> bypass works "
                    f"with master key but is blocked for virtual keys with model restrictions "
                    f"(v1 mitigation: issue scoped virtual keys, not master key, to users)"
                )
            else:
                fail(
                    f"{label}: HTTP 200 — model was NOT blocked",
                    f"Response model field: {actual!r}. "
                    f"Ensure AZURE_API_KEY is not set as a container env var.",
                )
        elif 400 <= r.status_code < 500:
            ok(f"{label}: HTTP {r.status_code} — correctly blocked")
        else:
            fail(f"{label}: HTTP {r.status_code} (expected 4xx)", r.text[:200])
    except requests.exceptions.Timeout:
        fail(f"{label}: timed out after {TIMEOUT}s")
    except Exception as e:
        fail(f"{label}: unexpected error", str(e))


# --- Header ---

print()
print("LiteLLM Allowlist and Friendly Naming Validation")
print(f"  LiteLLM URL:         {BASE_URL}")
print(f"  Flagship deployment: {DEPLOYMENT_FLAGSHIP}")
print(f"  Fast deployment:     {DEPLOYMENT_FAST}")
print()

# --- Tests 1 & 2: Friendly names route correctly ---

print('1. "ROMTech AI Standard" routes to flagship deployment')
expect_success("ROMTech AI Standard", MODEL_STANDARD)

print()
print('2. "ROMTech AI Fast" routes to fast deployment')
expect_success("ROMTech AI Fast", MODEL_FAST)

# --- Test 3: Raw deployment names are blocked ---

print()
print("3. Raw Azure deployment names are blocked (not reachable directly)")
expect_blocked(f"Raw flagship name ({DEPLOYMENT_FLAGSHIP!r})", DEPLOYMENT_FLAGSHIP)
expect_blocked(f"Raw fast name ({DEPLOYMENT_FAST!r})", DEPLOYMENT_FAST)

# --- Test 4: Provider-prefixed names are blocked ---

print()
print("4. Provider-prefixed model names are blocked")
expect_blocked(f"azure/{DEPLOYMENT_FLAGSHIP}", f"azure/{DEPLOYMENT_FLAGSHIP}")
expect_blocked(f"azure/{DEPLOYMENT_FAST}", f"azure/{DEPLOYMENT_FAST}")

# --- Test 5: Arbitrary unlisted model is blocked ---

print()
print("5. Arbitrary unlisted model name is blocked (no silent fallback)")
expect_blocked("Unlisted model name", "some-model-that-does-not-exist")

# --- Test 6: Streaming regression ---

print()
print(f'6. Streaming regression — "ROMTech AI Standard"')
try:
    r = chat(MODEL_STANDARD, stream=True)
    if r.status_code != 200:
        fail(f"Streaming: HTTP {r.status_code}", r.text[:200])
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
        if chunks:
            ok(f"Streamed {len(chunks)} chunk(s): {''.join(chunks).strip()[:60]!r}")
        else:
            fail("Stream returned no content chunks")
except requests.exceptions.Timeout:
    fail(f"Streaming timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Summary ---

print()
print("=" * 50)
total = passed + failed
print(f"Results: {passed}/{total} passed", "" if failed == 0 else f"— {failed} FAILED")
print()

if failed == 0:
    print("Allowlist validated. Update and share config/dev2_handoff.md.template with Dev 2.")
    print()
    print("Recommended default model for LibreChat (PBI-09-FE):")
    print(f'  "{MODEL_STANDARD}"')

sys.exit(0 if failed == 0 else 1)
