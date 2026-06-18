#!/usr/bin/env python3
"""
Validates LibreChat feature governance flags and file upload behavior.
PBI 9563 — local dev instance (depends on PBI-01-FE / PBI 9561).

Automated tests:
  1.  Service health — /api/user responds
  2.  Config file — interface flags match the v1 governance spec
  3.  Config file — fileConfig is enabled (not globally disabled)
  4.  /api/endpoints — only the LiteLLM custom endpoint is registered
  5.  LiteLLM /models — only approved friendly model names returned
  6.  /api/plugins — plugins disabled or empty
  7.  File upload — valid file within limits is accepted
  8.  File upload — file exceeding size limit is rejected with 4xx
  9.  File upload — disallowed MIME type is rejected with 4xx
  10. LiteLLM routing regression — chat still works after feature config changes

Manual checks are printed at the end (browser inspection required).

Usage:
  pip install -r requirements.txt
  python scripts/validate_librechat_features.py

Required environment variables (scripts/.env):
  LIBRECHAT_URL           e.g. http://localhost:3080
  LITELLM_URL             e.g. http://localhost:4000
  LITELLM_VIRTUAL_KEY     scoped virtual key from Dev 1

Required for file upload tests (Tests 7-9):
  LIBRECHAT_TEST_USER_EMAIL
  LIBRECHAT_TEST_USER_PASSWORD
  (Create with: cd LibreChat && npm run create-user)
"""

import io
import os
import re
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────────────────────

LIBRECHAT_URL = os.environ.get("LIBRECHAT_URL", "").rstrip("/")
LITELLM_URL   = os.environ.get("LITELLM_URL",   "").rstrip("/")
VIRTUAL_KEY   = os.environ.get("LITELLM_VIRTUAL_KEY", "")
TEST_EMAIL    = os.environ.get("LIBRECHAT_TEST_USER_EMAIL", "")
TEST_PASSWORD = os.environ.get("LIBRECHAT_TEST_USER_PASSWORD", "")

CONFIG_FILE = Path(__file__).parent.parent / "config" / "librechat.yaml"

EXPECTED_MODELS  = ["ROMTech AI Standard", "ROMTech AI Fast"]
BLOCKED_PREFIXES = ["azure/", "openai/", "gpt-", "claude-", "anthropic/"]

TIMEOUT = 20
LITELLM_AUTH = {"Authorization": f"Bearer {VIRTUAL_KEY}", "Content-Type": "application/json"}

missing_core = [k for k, v in {
    "LIBRECHAT_URL": LIBRECHAT_URL,
    "LITELLM_URL":   LITELLM_URL,
    "LITELLM_VIRTUAL_KEY": VIRTUAL_KEY,
}.items() if not v]

if missing_core:
    print("ERROR: Missing required environment variables:")
    for k in missing_core:
        print(f"  {k}")
    print("\nFill in scripts/.env — see SETUP.md Step 4.")
    sys.exit(1)

passed = 0
failed = 0
findings: list[str] = []


def ok(label: str) -> None:
    global passed
    passed += 1
    print(f"  PASS  {label}")


def fail(label: str, detail: str = "") -> None:
    global failed
    failed += 1
    print(f"  FAIL  {label}")
    if detail:
        print(f"        {detail}")


def find(label: str) -> None:
    findings.append(label)
    print(f"  FIND  {label}")


def warn(label: str) -> None:
    print(f"  WARN  {label}")


# ── Header ────────────────────────────────────────────────────────────────────

print()
print("LibreChat Feature Governance + File Upload Validation — PBI 9563")
print(f"  LibreChat : {LIBRECHAT_URL}")
print(f"  LiteLLM   : {LITELLM_URL}")
print()

# ── Test 1: Service health ────────────────────────────────────────────────────

print("1. /api/user — LibreChat is alive")
try:
    r = requests.get(f"{LIBRECHAT_URL}/api/user", timeout=TIMEOUT)
    if r.status_code in (200, 401):
        ok(f"HTTP {r.status_code} — service is up")
    else:
        fail(f"HTTP {r.status_code}", r.text.strip()[:200])
        print("\nCannot continue — LibreChat is not reachable.")
        sys.exit(1)
except requests.exceptions.ConnectionError:
    fail("Connection refused — is LibreChat running? (npm run backend in LibreChat/)")
    sys.exit(1)
except Exception as e:
    fail("Connection failed", str(e))
    sys.exit(1)

# ── Test 2: Interface flags in config/librechat.yaml ─────────────────────────

print()
print("2. config/librechat.yaml — interface governance flags")

if not CONFIG_FILE.exists():
    fail(f"config/librechat.yaml not found at {CONFIG_FILE}")
else:
    cfg = CONFIG_FILE.read_text(encoding="utf-8")

    EXPECTED_FALSE = [
        "endpointsMenu",
        "agents",
        "memories",
        "bookmarks",
        "prompts",
        "parameters",
        "multiConvo",
        "skills",
    ]
    for flag in EXPECTED_FALSE:
        pattern = rf"{re.escape(flag)}\s*:\s*false"
        check_ok = bool(re.search(pattern, cfg))
        ok(f"interface.{flag}: false") if check_ok else fail(
            f"interface.{flag}: false not found in librechat.yaml",
            "Add or correct the flag under the 'interface:' block.",
        )

# ── Test 3: fileConfig is enabled ─────────────────────────────────────────────

print()
print("3. config/librechat.yaml — fileConfig is enabled")

if CONFIG_FILE.exists():
    globally_disabled = bool(re.search(r"fileConfig\s*:\s*\n\s+disabled\s*:\s*true", cfg))
    fail(
        "fileConfig.disabled: true found — file upload is off globally",
        "Change to the per-endpoint structure with disabled: false under fileConfig.endpoints.custom",
    ) if globally_disabled else ok("fileConfig does not globally disable uploads")

    has_custom_block = bool(re.search(r"fileConfig", cfg) and re.search(r"custom\s*:", cfg))
    ok("fileConfig.endpoints.custom block present") if has_custom_block else fail(
        "fileConfig.endpoints.custom block not found",
        "Add a custom endpoint file config block — see SETUP.md.",
    )

    has_mime = bool(re.search(r"supportedMimeTypes", cfg))
    ok("supportedMimeTypes list present") if has_mime else fail(
        "supportedMimeTypes not configured",
        "Add supportedMimeTypes under fileConfig.endpoints.custom.",
    )

# ── Test 4: /api/endpoints — only LiteLLM ─────────────────────────────────────

print()
print("4. /api/endpoints — only LiteLLM custom endpoint registered")
try:
    r = requests.get(f"{LIBRECHAT_URL}/api/endpoints", timeout=TIMEOUT)
    if r.status_code == 200:
        endpoints = r.json()
        raw_vendors = [
            k for k in endpoints
            if k.lower() in ("openai", "anthropic", "google", "azureopenai", "bingai")
            and endpoints[k] not in (None, False, {})
        ]
        if raw_vendors:
            fail(f"Raw vendor endpoints enabled: {raw_vendors}",
                 "Remove vendor API keys from LibreChat/.env and restart.")
        else:
            ok(f"No raw vendor endpoints enabled  (keys: {list(endpoints.keys())})")
    elif r.status_code == 401:
        find("/api/endpoints returned 401 — auth enforcing (expected after Okta PBI)")
    else:
        find(f"/api/endpoints returned HTTP {r.status_code} — inspect manually")
except Exception as e:
    find(f"/api/endpoints check failed: {e}")

# ── Test 5: LiteLLM /models — only approved names ────────────────────────────

print()
print("5. LiteLLM /models — only approved friendly model names")
try:
    r = requests.get(f"{LITELLM_URL}/models", headers=LITELLM_AUTH, timeout=TIMEOUT)
    if r.status_code == 200:
        model_ids = [m.get("id", "") for m in r.json().get("data", [])]
        blocked = [m for m in model_ids if any(m.startswith(p) for p in BLOCKED_PREFIXES)]
        missing_expected = [m for m in EXPECTED_MODELS if m not in model_ids]
        if blocked:
            fail(f"Raw/vendor model names exposed: {blocked}",
                 "Check LiteLLM allowlist config.")
        elif missing_expected:
            fail(f"Expected models not found: {missing_expected}",
                 f"Returned: {model_ids}")
        else:
            ok(f"Model list: {model_ids}")
    else:
        fail(f"HTTP {r.status_code}", r.text[:200])
except Exception as e:
    fail("Unexpected error", str(e))

# ── Test 6: /api/plugins — disabled or empty ──────────────────────────────────

print()
print("6. /api/plugins — plugins disabled or empty")
try:
    r = requests.get(f"{LIBRECHAT_URL}/api/plugins", timeout=TIMEOUT)
    if r.status_code == 404:
        ok("HTTP 404 — plugins endpoint not registered")
    elif r.status_code == 401:
        find("/api/plugins returned 401 — auth enforcing")
    elif r.status_code == 200:
        plugins = r.json()
        if not plugins or (isinstance(plugins, list) and len(plugins) == 0):
            ok("HTTP 200 — plugins list is empty")
        else:
            find(f"HTTP 200 — plugins returned content: {str(plugins)[:200]}")
    else:
        find(f"/api/plugins returned HTTP {r.status_code}")
except Exception as e:
    find(f"/api/plugins check failed: {e}")

# ── File upload tests (Tests 7-9) — require auth ─────────────────────────────

print()
print("─" * 55)
print("File upload tests (7-9) — require LIBRECHAT_TEST_USER_EMAIL/PASSWORD")

upload_token: str | None = None

if not TEST_EMAIL or not TEST_PASSWORD:
    warn("LIBRECHAT_TEST_USER_EMAIL / LIBRECHAT_TEST_USER_PASSWORD not set.")
    warn("Create a test user:  cd LibreChat && npm run create-user")
    warn("Then add credentials to scripts/.env.")
    for n, label in [
        (7, "valid file upload accepted"),
        (8, "oversized file rejected with 4xx"),
        (9, "disallowed MIME type rejected with 4xx"),
    ]:
        fail(f"Test {n} skipped — test user credentials missing", "Set in scripts/.env")
else:
    print()
    print("  Authenticating with LibreChat...")
    try:
        r = requests.post(
            f"{LIBRECHAT_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            upload_token = r.json().get("token")
            if upload_token:
                print("  Auth OK — proceeding with file upload tests")
            else:
                fail("Auth token missing from login response")
        else:
            fail(f"Login failed — HTTP {r.status_code}", r.text.strip()[:200])
    except Exception as e:
        fail("Login request failed", str(e))

UPLOAD_URL = f"{LIBRECHAT_URL}/api/files"
UPLOAD_PARAMS = {"endpoint": "custom", "model": "ROMTech AI Standard"}

# ── Test 7: Valid file within limits is accepted ──────────────────────────────

print()
print("7. File upload — valid file within limits is accepted")
if upload_token:
    auth_headers = {"Authorization": f"Bearer {upload_token}"}
    small_file = io.BytesIO(b"This is a test file for PBI 9563 validation.\n")
    try:
        r = requests.post(
            UPLOAD_URL,
            headers=auth_headers,
            params=UPLOAD_PARAMS,
            files={"file": ("test.txt", small_file, "text/plain")},
            timeout=30,
        )
        if r.status_code in (200, 201):
            ok(f"HTTP {r.status_code} — valid file accepted by upload endpoint")
        elif r.status_code == 404:
            fail("HTTP 404 — /api/files endpoint not found",
                 "Check LibreChat version — file upload may use a different endpoint.")
        elif r.status_code == 401:
            fail("HTTP 401 — auth token rejected by upload endpoint")
        else:
            fail(f"HTTP {r.status_code} — unexpected response",
                 r.text.strip()[:300])
    except Exception as e:
        fail("Upload request failed", str(e))

# ── Test 8: Oversized file is rejected ───────────────────────────────────────

print()
print("8. File upload — file exceeding 10 MB size limit is rejected with 4xx")
if upload_token:
    auth_headers = {"Authorization": f"Bearer {upload_token}"}
    # 11 MB — exceeds fileSizeLimit: 10
    big_file = io.BytesIO(b"0" * (11 * 1024 * 1024))
    try:
        r = requests.post(
            UPLOAD_URL,
            headers=auth_headers,
            params=UPLOAD_PARAMS,
            files={"file": ("big.txt", big_file, "text/plain")},
            timeout=60,
        )
        if 400 <= r.status_code < 500:
            ok(f"HTTP {r.status_code} — oversized file correctly rejected")
        elif r.status_code in (200, 201):
            fail("HTTP 200 — oversized file was accepted (size limit not enforced)",
                 f"fileSizeLimit is 10 MB — an 11 MB file should be rejected. "
                 f"Confirm fileSizeLimit is set under fileConfig.endpoints.custom.")
        else:
            find(f"HTTP {r.status_code} for oversized file — inspect manually")
    except Exception as e:
        fail("Oversized file upload request failed", str(e))

# ── Test 9: Disallowed MIME type is rejected ──────────────────────────────────

print()
print("9. File upload — disallowed MIME type (application/x-msdownload) rejected with 4xx")
if upload_token:
    auth_headers = {"Authorization": f"Bearer {upload_token}"}
    fake_exe = io.BytesIO(b"MZ\x90\x00" + b"\x00" * 100)
    try:
        r = requests.post(
            UPLOAD_URL,
            headers=auth_headers,
            params=UPLOAD_PARAMS,
            files={"file": ("malware.exe", fake_exe, "application/x-msdownload")},
            timeout=30,
        )
        if 400 <= r.status_code < 500:
            ok(f"HTTP {r.status_code} — disallowed MIME type correctly rejected")
        elif r.status_code in (200, 201):
            fail("HTTP 200 — disallowed MIME type was accepted",
                 "application/x-msdownload (.exe) should be rejected. "
                 "Verify supportedMimeTypes is set in fileConfig.endpoints.custom.")
        else:
            find(f"HTTP {r.status_code} for disallowed MIME — inspect manually")
    except Exception as e:
        fail("Disallowed MIME upload request failed", str(e))

# ── Test 10: LiteLLM routing regression ───────────────────────────────────────

print()
print("10. LiteLLM routing regression — chat still working after feature config changes")
try:
    r = requests.post(
        f"{LITELLM_URL}/chat/completions",
        headers=LITELLM_AUTH,
        json={
            "model": "ROMTech AI Standard",
            "messages": [{"role": "user", "content": "Reply with the single word: OK"}],
        },
        timeout=30,
    )
    if r.status_code == 200:
        content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        ok(f"Routing working: {content.strip()[:60]!r}")
    else:
        fail(f"HTTP {r.status_code}", r.text[:200])
except Exception as e:
    fail("Regression check failed", str(e))

# ── Manual browser checks ─────────────────────────────────────────────────────

print()
print("─" * 55)
print("Manual browser checks required — record in feature_audit_assessment.md")
print()
print("  Disabled elements (should NOT be visible):")
print("  [ ] Endpoints menu / endpoint switcher")
print("  [ ] Agents")
print("  [ ] Memories")
print("  [ ] Bookmarks")
print("  [ ] Prompts")
print("  [ ] Parameters panel")
print("  [ ] Skills")
print()
print("  Enabled elements (SHOULD be accessible):")
print("  [ ] File attachment (paperclip) button is visible in the chat input")
print("  [ ] A file within limits can be attached and its content is accessible to the model")
print("  [ ] Model picker shows only 'ROMTech AI Standard' and 'ROMTech AI Fast'")
print()
print("  MCP Settings sidebar button (known gap from Phase 0):")
print("  [ ] Open the sidebar — is the MCP Settings button present?")
print("      If YES: check config/librechat.yaml for an 'mcp' key under 'interface:'")
print("              If no config key exists in this release → record as accepted cosmetic gap")
print("      If NO:  record as resolved")

# ── Findings ─────────────────────────────────────────────────────────────────

if findings:
    print()
    print("Automated findings to record in feature_audit_assessment.md:")
    for i, f_text in enumerate(findings, 1):
        print(f"  [{i}] {f_text}")

# ── Summary ───────────────────────────────────────────────────────────────────

print()
print("=" * 55)
total = passed + failed
print(f"Automated results: {passed}/{total} passed", "" if failed == 0 else f"  —  {failed} FAILED")
print()

if failed == 0:
    print("Automated checks passed.")
    print("Complete the manual browser checklist above and fill in feature_audit_assessment.md.")

sys.exit(0 if failed == 0 else 1)
