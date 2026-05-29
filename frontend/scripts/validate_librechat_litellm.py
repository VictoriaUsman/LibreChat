#!/usr/bin/env python3
"""
validate_librechat_litellm.py  –  PBI 9561 acceptance check (LiteLLM routing)

Checks:
  1. LiteLLM /health endpoint responds
  2. LiteLLM exposes ROMTech AI Standard and ROMTech AI Fast in its model list
  3. LibreChat accepts a chat message and returns a streaming SSE response
  4. The response contains real text tokens (confirms the Azure OpenAI round-trip)

Prerequisites:
  - LibreChat running at LIBRECHAT_URL (default http://localhost:3080)
  - LiteLLM running at LITELLM_BASE_URL
  - LIBRECHAT_TEST_USER_EMAIL / LIBRECHAT_TEST_USER_PASSWORD in scripts/.env
    (create once: cd <LibreChat-repo> && npm run create-user)

Run from the project root:
  python scripts/validate_librechat_litellm.py

Requirements:
  pip install requests
"""

import sys
import json
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed.  Run: pip install requests")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
ENV_FILE = SCRIPT_DIR / ".env"

# ── Load scripts/.env ─────────────────────────────────────────────────────────
if not ENV_FILE.exists():
    print(f"FATAL: scripts/.env not found at {ENV_FILE}")
    sys.exit(1)

env: dict[str, str] = {}
with open(ENV_FILE) as fh:
    for raw in fh:
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()

LIBRECHAT_URL = env.get("LIBRECHAT_URL", "http://localhost:3080")
LITELLM_BASE_URL = env.get("LITELLM_BASE_URL", "")
TEST_EMAIL = env.get("LIBRECHAT_TEST_USER_EMAIL", "")
TEST_PASSWORD = env.get("LIBRECHAT_TEST_USER_PASSWORD", "")
EXPECTED_MODELS = {"ROMTech AI Standard", "ROMTech AI Fast"}

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    line = f"  {tag}  {label}"
    if not ok and detail:
        line += f"  ({detail})"
    print(line)
    if not ok:
        failures.append(label)


# ── Preflight ─────────────────────────────────────────────────────────────────
if not LITELLM_BASE_URL:
    print("FATAL: LITELLM_BASE_URL not set in scripts/.env")
    sys.exit(1)
if not TEST_EMAIL or not TEST_PASSWORD:
    print("FATAL: LIBRECHAT_TEST_USER_EMAIL / LIBRECHAT_TEST_USER_PASSWORD not set.")
    print("       Create a test user:  cd <LibreChat-repo> && npm run create-user")
    sys.exit(1)

# ── 1. LiteLLM health ─────────────────────────────────────────────────────────
print("\n[1] Checking LiteLLM health")
try:
    r = requests.get(f"{LITELLM_BASE_URL}/health", timeout=5)
    check("LiteLLM /health responds with 200", r.status_code == 200,
          f"HTTP {r.status_code}")
except requests.exceptions.ConnectionError:
    check("LiteLLM /health responds with 200", False,
          "connection refused — is LiteLLM running?")
    print("\nCannot continue: LiteLLM is unreachable.")
    sys.exit(1)
except Exception as exc:
    check("LiteLLM /health responds with 200", False, str(exc))
    sys.exit(1)

# ── 2. LiteLLM model list ─────────────────────────────────────────────────────
print("\n[2] Checking LiteLLM model list")
try:
    r = requests.get(f"{LITELLM_BASE_URL}/v1/models", timeout=5)
    check("LiteLLM /v1/models responds", r.status_code == 200,
          f"HTTP {r.status_code}")
    if r.status_code == 200:
        available = {m["id"] for m in r.json().get("data", [])}
        for model in sorted(EXPECTED_MODELS):
            check(f"'{model}' in LiteLLM model list",
                  model in available,
                  f"not found — available: {sorted(available)[:6]}")
except Exception as exc:
    check("LiteLLM /v1/models responds", False, str(exc))

# ── 3. Authenticate with LibreChat ────────────────────────────────────────────
print("\n[3] Authenticating with LibreChat")
token: str | None = None
try:
    r = requests.post(
        f"{LIBRECHAT_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=10,
    )
    check("Login succeeds (HTTP 200)", r.status_code == 200, f"HTTP {r.status_code}")
    if r.status_code == 200:
        token = r.json().get("token")
        check("Auth token returned", bool(token), "token missing from response")
except Exception as exc:
    check("Login succeeds (HTTP 200)", False, str(exc))

if not token:
    print("\nCannot continue: LibreChat authentication failed.")
    sys.exit(1)

# ── 4. Send a message — expect streaming SSE back ─────────────────────────────
print("\n[4] Sending test message through LibreChat → LiteLLM")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
payload = {
    "text": "Respond with exactly three words: streaming test ok",
    "endpoint": "custom",
    "model": "ROMTech AI Standard",
    "conversationId": "new",
    "parentMessageId": "00000000-0000-0000-0000-000000000000",
}
try:
    r = requests.post(
        f"{LIBRECHAT_URL}/api/ask/custom",
        headers=headers,
        json=payload,
        stream=True,
        timeout=30,
    )
    check("Message request accepted (HTTP 200)", r.status_code == 200,
          f"HTTP {r.status_code}")

    if r.status_code == 200:
        got_text = False
        for raw_chunk in r.iter_lines(chunk_size=4096):
            if not raw_chunk:
                continue
            chunk = raw_chunk.decode("utf-8", errors="replace")
            if chunk.startswith("data: "):
                chunk = chunk[6:]
            try:
                data = json.loads(chunk)
                if data.get("text") or data.get("delta"):
                    got_text = True
                    break
            except json.JSONDecodeError:
                pass
        check("Streaming response contains text tokens", got_text,
              "no text/delta tokens received — check LiteLLM routing and Azure OpenAI")
except Exception as exc:
    check("Message request accepted (HTTP 200)", False, str(exc))

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'=' * 52}")
if failures:
    print(f"RESULT: {len(failures)} failure(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("RESULT: All checks passed  (0 failures)")
    sys.exit(0)
