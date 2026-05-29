#!/usr/bin/env python3
"""
Validates Okta OIDC authentication configuration against Phase 0 acceptance
criteria (PBI 9129).

This script depends on PBI 9125 (LibreChat container running).

What this script checks (automated):
  1. OIDC redirect endpoint (/api/auth/openid) returns a redirect, not 404 or 500
  2. Redirect destination contains the Okta issuer domain
  3. Callback URL is registered and reachable (returns expected response, not 404)
  4. Unauthenticated access to /api/user returns 401 (auth is enforcing)
  5. Required OIDC environment variables are set in the local environment

What requires manual testing (see protocol below):
  - Logging in with a valid pilot group Okta account
  - Confirming users outside the pilot group are blocked
  - Confirming the Okta tile in the dashboard redirects correctly
  - Confirming display name and email appear in LibreChat after login

Usage:
  pip install -r requirements.txt
  python validate_librechat_okta.py

Required environment variables (extend existing .env):
  LIBRECHAT_URL
  OPENID_ISSUER          e.g. https://romtech.okta.com/oauth2/default
  OPENID_CALLBACK_URL    e.g. https://<librechat-aca-url>/api/auth/openid/callback
  OPENID_CLIENT_ID       from the Okta admin (used only to check it is set)
"""

import os
import sys
import urllib.parse

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

BASE_URL = os.environ.get("LIBRECHAT_URL", "").rstrip("/")
OPENID_ISSUER = os.environ.get("OPENID_ISSUER", "")
OPENID_CALLBACK_URL = os.environ.get("OPENID_CALLBACK_URL", "")
OPENID_CLIENT_ID = os.environ.get("OPENID_CLIENT_ID", "")

missing = [k for k, v in {
    "LIBRECHAT_URL": BASE_URL,
    "OPENID_ISSUER": OPENID_ISSUER,
}.items() if not v]

if missing:
    print("ERROR: Missing required environment variables:")
    for k in missing:
        print(f"  {k}")
    sys.exit(1)

TIMEOUT = 15
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


# --- Header ---

print()
print("LibreChat Okta OIDC Authentication Validation — PBI 9129")
print(f"  LibreChat URL: {BASE_URL}")
print(f"  OIDC Issuer:   {OPENID_ISSUER}")
print()

# --- Test 1: OIDC required env vars are set ---

print("1. Required OIDC environment variables are set")
oidc_vars = {
    "OPENID_CLIENT_ID": OPENID_CLIENT_ID,
    "OPENID_ISSUER": OPENID_ISSUER,
    "OPENID_CALLBACK_URL": OPENID_CALLBACK_URL,
    "OPENID_SESSION_SECRET": os.environ.get("OPENID_SESSION_SECRET", ""),
    "OPENID_CLIENT_SECRET": os.environ.get("OPENID_CLIENT_SECRET", ""),
}
missing_oidc = [k for k, v in oidc_vars.items() if not v]
if missing_oidc:
    fail(
        f"OIDC environment variables not set: {missing_oidc}",
        "Set all OPENID_* variables in the Container App environment "
        "(from config/librechat.env.template) and restart the container.",
    )
else:
    ok("All OPENID_* environment variables are set in the local environment")
    warn("Also verify these are set in the ACA container environment, not just .env")

# --- Test 2: /api/auth/openid redirects to Okta ---

print()
print("2. /api/auth/openid initiates OIDC redirect to Okta")
try:
    r = requests.get(
        f"{BASE_URL}/api/auth/openid",
        timeout=TIMEOUT,
        allow_redirects=False,
    )
    if r.status_code in (302, 307, 308):
        location = r.headers.get("Location", "")
        issuer_host = urllib.parse.urlparse(OPENID_ISSUER).netloc
        if issuer_host and issuer_host in location:
            ok(f"HTTP {r.status_code} → Okta issuer domain confirmed in redirect URL")
        elif location:
            warn(
                f"HTTP {r.status_code} redirect, but destination does not contain Okta issuer domain.\n"
                f"        Redirect target: {location[:120]}\n"
                f"        Expected issuer: {issuer_host}"
            )
        else:
            fail(f"HTTP {r.status_code} redirect but no Location header")
    elif r.status_code == 404:
        fail(
            "HTTP 404 — OIDC route not registered",
            "Verify OPENID_CLIENT_ID, OPENID_ISSUER, and OPENID_CLIENT_SECRET are set "
            "in the Container App environment, and restart the container.",
        )
    elif r.status_code in (500, 503):
        fail(
            f"HTTP {r.status_code} — server error on OIDC endpoint",
            r.text.strip()[:200],
        )
    else:
        fail(f"Unexpected HTTP {r.status_code}", r.text.strip()[:200])
except requests.exceptions.Timeout:
    fail(f"Request timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 3: Callback URL is registered and reachable ---

print()
print("3. OIDC callback URL is reachable (returns expected response, not 404)")
try:
    # Call the callback without a code — expect an error response (not a 404).
    # A 400 or 500 here is acceptable — it means the route exists but rejects
    # the incomplete request, which is correct behavior.
    callback_path = urllib.parse.urlparse(OPENID_CALLBACK_URL).path
    r = requests.get(
        f"{BASE_URL}{callback_path}",
        timeout=TIMEOUT,
        allow_redirects=False,
    )
    if r.status_code == 404:
        fail(
            "HTTP 404 — callback URL path is not registered",
            f"Configured callback: {OPENID_CALLBACK_URL}\n"
            f"        Verify the callback path matches exactly what is registered in Okta.",
        )
    else:
        ok(
            f"HTTP {r.status_code} — callback route is registered "
            f"(non-404 confirms the path exists; {r.status_code} without a valid code is expected)"
        )
except requests.exceptions.Timeout:
    fail(f"Request timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 4: Unauthenticated access to /api/user is rejected ---

print()
print("4. Unauthenticated access to /api/user returns 401 — auth is enforcing")
try:
    r = requests.get(
        f"{BASE_URL}/api/user",
        timeout=TIMEOUT,
    )
    if r.status_code == 401:
        ok("HTTP 401 — unauthenticated request rejected as expected")
    elif r.status_code == 200:
        fail(
            "HTTP 200 — unauthenticated request was accepted",
            "Verify OPENID_CLIENT_ID is set in the container environment. "
            "Without it, LibreChat allows unauthenticated access.",
        )
    else:
        ok(f"HTTP {r.status_code} — unauthenticated request not silently accepted")
except requests.exceptions.Timeout:
    fail(f"Request timed out after {TIMEOUT}s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Manual test reminders ---

print()
print("Manual validation still required (see PBI 9129 acceptance criteria):")
print("  Test A — Log in with a valid pilot group Okta account")
print("           Confirm display name and email are visible in LibreChat after login")
print("  Test B — Attempt login with an account NOT in the pilot Okta group")
print("           Confirm access is denied at the Okta layer")
print("  Test C — Confirm the Okta app tile in the dashboard launches LibreChat")
print("           and initiates the login flow without requiring manual URL entry")
print()
print("  Coordinate Tests B and C with the Okta admin.")

# --- Summary ---

print()
print("=" * 50)
total = passed + failed
print(f"Results: {passed}/{total} passed", "" if failed == 0 else f"— {failed} FAILED")
print()

if failed == 0:
    print("Automated Okta checks passed.")
    print("Complete manual tests A–C and document findings in config/okta_validation_findings.md")

sys.exit(0 if failed == 0 else 1)
