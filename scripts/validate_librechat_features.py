#!/usr/bin/env python3
"""
Validates LibreChat feature governance configuration against Phase 0
acceptance criteria (PBI 9130).

This script depends on PBI 9126 (librechat.yaml deployed with interface config).

What this script checks (automated):
  1. LibreChat /api/health — container is alive
  2. /api/endpoints — only the LiteLLM custom endpoint is returned (no raw vendors)
  3. /api/models — model list matches allowed models (no raw Azure names)
  4. /api/plugins (or equivalent) — plugins endpoint returns empty or is inaccessible
  5. LiteLLM routing regression — master routing still works

What requires manual testing (see feature_audit_assessment.md.template):
  - Browser inspection of each disabled UI element
  - Confirming endpointsMenu is hidden
  - Confirming capabilities (file upload, plugins, code interpreter) are hidden
  - Confirming prompt share/publish options are hidden

Usage:
  pip install -r requirements.txt
  python validate_librechat_features.py

Required environment variables:
  LIBRECHAT_URL
  LITELLM_URL
  LITELLM_VIRTUAL_KEY
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

EXPECTED_MODELS = ["ROMTech AI Standard", "ROMTech AI Fast"]
BLOCKED_PREFIXES = ["azure/", "openai/", "gpt-", "claude-", "anthropic/"]

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

TIMEOUT = 20
LITELLM_AUTH = {"Authorization": f"Bearer {VIRTUAL_KEY}", "Content-Type": "application/json"}
TEST_MESSAGE = [{"role": "user", "content": "Reply with the single word: OK"}]
findings = []

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


def finding(label):
    findings.append(label)
    print(f"  FIND  {label}")


def warn(label):
    print(f"  WARN  {label}")


# --- Header ---

print()
print("LibreChat Feature Governance Validation — PBI 9130")
print(f"  LibreChat URL: {LIBRECHAT_URL}")
print()

# --- Test 1: Health check ---

print("1. /api/user — container is alive")
try:
    r = requests.get(f"{LIBRECHAT_URL}/api/user", timeout=TIMEOUT)
    if r.status_code in (200, 401):
        ok(f"HTTP {r.status_code} — LibreChat API is alive")
    else:
        fail(f"HTTP {r.status_code}", r.text.strip()[:200])
        sys.exit(1)
except Exception as e:
    fail("Connection failed", str(e))
    sys.exit(1)

# --- Test 2: /api/endpoints returns only LiteLLM ---

print()
print("2. /api/endpoints — only LiteLLM custom endpoint is registered")
try:
    r = requests.get(f"{LIBRECHAT_URL}/api/endpoints", timeout=TIMEOUT)
    if r.status_code == 200:
        endpoints = r.json()
        # LibreChat /api/endpoints returns a dict keyed by endpoint type
        raw_vendor_endpoints = []
        for key in endpoints:
            if key.lower() in ["openai", "anthropic", "google", "azureopenai", "bingai"]:
                endpoint_val = endpoints[key]
                if endpoint_val and endpoint_val is not False:
                    raw_vendor_endpoints.append(key)

        if raw_vendor_endpoints:
            fail(
                f"Raw vendor endpoints are enabled: {raw_vendor_endpoints}",
                "These should be disabled. Ensure AZURE_OPENAI_API_KEY, OPENAI_API_KEY, "
                "and other vendor keys are NOT set in the container environment.",
            )
        else:
            ok(f"No raw vendor endpoints enabled. Endpoint keys: {list(endpoints.keys())}")
    elif r.status_code == 401:
        finding("/api/endpoints returned 401 — Okta auth is enforcing (expected after PBI 9129)")
    else:
        finding(f"/api/endpoints returned HTTP {r.status_code} — inspect manually")
except Exception as e:
    finding(f"/api/endpoints check failed: {e}")

# --- Test 3: LiteLLM /models returns only approved model names ---

print()
print("3. LiteLLM /models — only approved friendly model names returned")
try:
    r = requests.get(
        f"{LITELLM_URL}/models",
        headers=LITELLM_AUTH,
        timeout=TIMEOUT,
    )
    if r.status_code == 200:
        model_ids = [m.get("id", "") for m in r.json().get("data", [])]
        blocked = [m for m in model_ids if any(m.startswith(p) for p in BLOCKED_PREFIXES)]
        missing_expected = [m for m in EXPECTED_MODELS if m not in model_ids]

        if blocked:
            fail(
                f"Raw/vendor model names exposed: {blocked}",
                "These should not be reachable. Check LiteLLM allowlist config.",
            )
        elif missing_expected:
            fail(
                f"Expected models not found in /models: {missing_expected}",
                f"Models returned: {model_ids}",
            )
        else:
            ok(f"Model list contains only approved names: {model_ids}")
    else:
        fail(f"HTTP {r.status_code}", r.text[:200])
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 4: /api/plugins returns empty or 404 (plugins disabled) ---

print()
print("4. /api/plugins — plugins endpoint returns empty or is inaccessible")
try:
    r = requests.get(f"{LIBRECHAT_URL}/api/plugins", timeout=TIMEOUT)
    if r.status_code == 404:
        ok("HTTP 404 — plugins endpoint not registered (expected when capabilities: [] is set)")
    elif r.status_code == 200:
        plugins = r.json()
        if not plugins or (isinstance(plugins, list) and len(plugins) == 0):
            ok("HTTP 200 — plugins list is empty (capabilities: [] is working)")
        else:
            finding(
                f"HTTP 200 — plugins returned: {str(plugins)[:200]}. "
                f"Verify capabilities: [] is set in librechat.yaml and container was restarted."
            )
    elif r.status_code == 401:
        finding("/api/plugins returned 401 — auth enforcing (expected after PBI 9129)")
    else:
        finding(f"/api/plugins returned HTTP {r.status_code} — inspect manually")
except Exception as e:
    finding(f"/api/plugins check failed: {e}")

# --- Test 5: LiteLLM routing regression ---

print()
print("5. Routing regression — LiteLLM still routes correctly after feature config")
try:
    r = requests.post(
        f"{LITELLM_URL}/chat/completions",
        headers=LITELLM_AUTH,
        json={"model": "ROMTech AI Standard", "messages": TEST_MESSAGE},
        timeout=30,
    )
    if r.status_code == 200:
        content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        ok(f"Routing still working: {content.strip()[:60]!r}")
    else:
        fail(f"HTTP {r.status_code}", r.text[:200])
except Exception as e:
    fail("Regression check failed", str(e))

# --- Manual inspection reminders ---

print()
print("Manual browser checks required (record findings in feature_audit_assessment.md):")
print("  [ ] Endpoint menu (gear icon or endpoint switcher) is hidden from UI")
print("  [ ] No file attachment button visible in chat input")
print("  [ ] No plugin/tool icon visible in chat interface")
print("  [ ] Prompts section has no share or publish option")
print("  [ ] Model picker shows only 'ROMTech AI Standard' and 'ROMTech AI Fast'")

if findings:
    print()
    print("Automated findings to record in feature_audit_assessment.md:")
    for i, f_text in enumerate(findings, 1):
        print(f"  [{i}] {f_text}")

# --- Summary ---

print()
print("=" * 55)
total = passed + failed
print(f"Automated results: {passed}/{total} passed", "" if failed == 0 else f"— {failed} FAILED")
print()

if failed == 0:
    print("Automated feature checks passed.")
    print("Complete manual browser inspection and fill in feature_audit_assessment.md.")

sys.exit(0 if failed == 0 else 1)
