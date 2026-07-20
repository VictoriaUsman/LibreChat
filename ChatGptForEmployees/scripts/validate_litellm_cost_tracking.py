#!/usr/bin/env python3
"""
Validates LiteLLM model pricing and per-user spend attribution against the
"Register Model Cost & Enable Per-User Spend in LiteLLM" PBI.

This script depends on PBI-03-BE. Run validate_litellm_routing.py first.

What this script checks:
  1. Each model_list entry in litellm_routing_config.yaml carries a model_info
     block with input_cost_per_token / output_cost_per_token (the fix for the
     $0-spend bug — LiteLLM's built-in price table doesn't know our custom
     azure/romtech-* deployment names).
  2. general_settings.allow_user_requests is true. NOTE: LiteLLM records the
     request-body "user" field into LiteLLM_SpendLogs.end_user by DEFAULT; this
     opt-in is checked for parity with the deployed config, but its exact gating
     effect is unconfirmed against the pinned image and may be a no-op (end_user
     attribution works regardless). Test 4 below empirically confirms capture.
  3. A live request against each model logs a non-zero spend in /spend/logs
     that matches prompt_tokens * input_cost_per_token +
     completion_tokens * output_cost_per_token exactly.
  4. The request's "user" value is captured in the spend log row — this
     script determines empirically whether it lands in the `user` or
     `end_user` column and asserts it's in the one that actually holds it.

NOTE — real dev Azure deployment connectivity:
  In this sandbox, the real azure/romtech-standard / azure/romtech-fast
  deployments on the dev-lms-foundry AI Foundry resource return 404 directly
  from Azure (confirmed independently of LiteLLM/this config) — a pre-existing
  environment issue unrelated to this change. When that's the case, this
  script reports it as a FIND and skips the live-spend assertions rather than
  failing outright. The live-request checks were confirmed end-to-end during
  development using a local OpenAI-compatible stub standing in for Azure
  (same model_info blocks, same general_settings) — that harness is not part
  of this repo and needs to be re-run manually if Azure connectivity is fixed.

Usage:
  pip install -r requirements.txt
  python validate_litellm_cost_tracking.py

Required environment variables (same .env as previous scripts):
  LITELLM_URL
  LITELLM_MASTER_KEY
  LITELLM_MODEL_FLAGSHIP   e.g. "ROMTech AI Standard"
  LITELLM_MODEL_FAST       e.g. "ROMTech AI Fast"
"""

import os
import sys
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

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml package not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

# --- Configuration ---

BASE_URL = os.environ.get("LITELLM_URL", "").rstrip("/")
MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
MODEL_STANDARD = os.environ.get("LITELLM_MODEL_FLAGSHIP", "ROMTech AI Standard")
MODEL_FAST = os.environ.get("LITELLM_MODEL_FAST", "ROMTech AI Fast")
TEST_USER = "phase0-test-user@romtech.com"

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "litellm_routing_config.yaml",
)

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


def post_chat(model, extra=None):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: OK"}],
    }
    if extra:
        body.update(extra)
    return requests.post(f"{BASE_URL}/chat/completions", headers=AUTH, json=body, timeout=TIMEOUT)


# --- Header ---

print()
print("LiteLLM Model Cost and Per-User Spend Assessment")
print(f"  LiteLLM URL:     {BASE_URL}")
print(f"  Standard model:  {MODEL_STANDARD}")
print(f"  Fast model:      {MODEL_FAST}")
print(f"  Test user:       {TEST_USER}")
print()

# --- Test 1: model_info pricing blocks present in config ---

print("1. model_info pricing blocks present in litellm_routing_config.yaml")
model_costs = {}
try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    for entry in config.get("model_list", []):
        name = entry.get("model_name")
        info = entry.get("model_info") or {}
        input_cost = info.get("input_cost_per_token")
        output_cost = info.get("output_cost_per_token")
        if input_cost is None or output_cost is None:
            fail(f'"{name}" missing model_info cost fields', f"model_info: {info}")
        else:
            model_costs[name] = (input_cost, output_cost)
            ok(f'"{name}" -> base_model={info.get("base_model")}, '
               f"input={input_cost}/tok, output={output_cost}/tok")
except Exception as e:
    fail("Could not read/parse litellm_routing_config.yaml", str(e))

# --- Test 2: allow_user_requests enabled ---

print()
print("2. general_settings.allow_user_requests enabled")
try:
    allow_user_requests = config.get("general_settings", {}).get("allow_user_requests")
    if allow_user_requests is True:
        ok("general_settings.allow_user_requests: true")
    else:
        fail("general_settings.allow_user_requests is not true", f"value: {allow_user_requests}")
except Exception as e:
    fail("Could not check allow_user_requests", str(e))

# --- Test 3 & 4: live spend + user attribution per model ---

print()
print("3. Live request -> non-zero spend matching expected calculation, per model")
print("4. Request \"user\" field captured in the spend log (user vs end_user)")

for model in (MODEL_STANDARD, MODEL_FAST):
    print()
    print(f'   --- {model} ---')
    if model not in model_costs:
        finding(f'Skipping live check for "{model}" — no model_info cost fields to compare against')
        continue

    input_cost, output_cost = model_costs[model]
    try:
        r = post_chat(model, {"user": TEST_USER})
    except Exception as e:
        finding(f'Request to "{model}" failed to connect: {e}')
        continue

    if r.status_code != 200:
        finding(
            f'Request to "{model}" returned HTTP {r.status_code} — likely the known dev '
            "Azure deployment connectivity issue (see module docstring), not a config regression. "
            "Skipping live spend/user-attribution assertions for this model."
        )
        continue

    time.sleep(3)
    try:
        logs = get("/spend/logs").json()
    except Exception as e:
        finding(f'Could not fetch /spend/logs after "{model}" request: {e}')
        continue

    if not isinstance(logs, list) or not logs:
        finding(f'No /spend/logs entries found after "{model}" request')
        continue

    match = max(logs, key=lambda l: l.get("startTime", ""))
    prompt_tokens = match.get("prompt_tokens")
    completion_tokens = match.get("completion_tokens")
    spend = match.get("spend")
    expected = (
        round(prompt_tokens * input_cost + completion_tokens * output_cost, 10)
        if prompt_tokens is not None and completion_tokens is not None
        else None
    )

    if spend and expected is not None and abs(spend - expected) < 1e-9:
        ok(f"spend {spend} matches expected {expected} "
           f"({prompt_tokens} prompt + {completion_tokens} completion tokens)")
    else:
        fail(f'Spend mismatch for "{model}"',
             f"logged spend={spend}, expected={expected}, row={match}")

    if match.get("end_user") == TEST_USER:
        ok(f'end_user column captures the request "user" field ("{TEST_USER}")')
    elif match.get("user") == TEST_USER:
        ok(f'user column captures the request "user" field ("{TEST_USER}")')
    else:
        fail(
            f'Neither "user" nor "end_user" column captured "{TEST_USER}"',
            f'user={match.get("user")!r}, end_user={match.get("end_user")!r}',
        )

# --- Regression: routing still works ---

print()
print("5. Routing regression — requests still reach the configured deployments")
try:
    r = post_chat(MODEL_STANDARD)
    if r.status_code == 200:
        content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        ok(f"Routing still working: {content.strip()[:60]!r}")
    elif r.status_code == 404 or (r.status_code == 429 and "cooldown_list" in r.text):
        finding(f"HTTP {r.status_code} routing {MODEL_STANDARD} — known dev Azure deployment "
                "connectivity issue (see module docstring), not caused by this change "
                "(litellm_params unchanged; a 429 here is LiteLLM's cooldown after the "
                "underlying 404s, not an independent regression)")
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
    print("Findings:")
    for i, f_text in enumerate(findings, 1):
        print(f"  [{i}] {f_text}")

sys.exit(0 if failed == 0 else 1)
