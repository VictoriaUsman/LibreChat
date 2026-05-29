#!/usr/bin/env python3
"""
validate_librechat.py  –  PBI 9561 acceptance check (structural + service health)

Checks:
  1. scripts/.env exists and all required vars are set with non-placeholder values
  2. ALLOW_REGISTRATION=false
  3. ALLOW_SOCIAL_LOGIN=true
  4. config/librechat.yaml has no <placeholder> values
  5. LibreChat responds at http://localhost:3080 (or LIBRECHAT_URL)
  6. MongoDB is reachable at MONGO_URI

Run from the project root:
  python scripts/validate_librechat.py

Requirements:
  pip install requests pymongo
  (pymongo check is skipped if not installed)
"""

import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed.  Run: pip install requests")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
ENV_FILE = SCRIPT_DIR / ".env"
CONFIG_FILE = PROJECT_ROOT / "config" / "librechat.yaml"

PLACEHOLDER = re.compile(r"<[^>]+>")

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    line = f"  {tag}  {label}"
    if not ok and detail:
        line += f"  ({detail})"
    print(line)
    if not ok:
        failures.append(label)


# ── Load scripts/.env ─────────────────────────────────────────────────────────
if not ENV_FILE.exists():
    print(f"FATAL: scripts/.env not found at {ENV_FILE}")
    print("       Copy config/librechat_env.template to scripts/.env and fill it in.")
    sys.exit(1)

env: dict[str, str] = {}
with open(ENV_FILE) as fh:
    for raw in fh:
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()

# ── 1. Required vars present and not placeholders ────────────────────────────
print("\n[1] Checking scripts/.env — required values")

REQUIRED = [
    "JWT_SECRET",
    "JWT_REFRESH_SECRET",
    "CREDS_KEY",
    "CREDS_IV",
    "LITELLM_BASE_URL",
    "LITELLM_VIRTUAL_KEY",
    "MONGO_URI",
]

for var in REQUIRED:
    val = env.get(var, "")
    bad = not val or bool(PLACEHOLDER.search(val))
    check(f"{var} is set and not a placeholder", not bad,
          "empty or still contains <…>" if bad else "")

# ── 2. Auth flags ─────────────────────────────────────────────────────────────
print("\n[2] Checking auth settings")
check("ALLOW_REGISTRATION=false",
      env.get("ALLOW_REGISTRATION", "").lower() == "false")
check("ALLOW_SOCIAL_LOGIN=true",
      env.get("ALLOW_SOCIAL_LOGIN", "").lower() == "true")

# ── 3. librechat.yaml — no placeholders ───────────────────────────────────────
print("\n[3] Checking config/librechat.yaml")
if CONFIG_FILE.exists():
    yaml_text = CONFIG_FILE.read_text(encoding="utf-8")
    check("librechat.yaml has no <placeholder> values",
          not PLACEHOLDER.search(yaml_text),
          "found <…> — fill in all placeholder tokens")
else:
    check("config/librechat.yaml exists", False, f"not found at {CONFIG_FILE}")

# ── 4. LibreChat service health ───────────────────────────────────────────────
print("\n[4] Checking LibreChat service")
lc_url = env.get("LIBRECHAT_URL", "http://localhost:3080")
try:
    r = requests.get(lc_url, timeout=5)
    check(f"LibreChat responds at {lc_url}", r.status_code == 200,
          f"HTTP {r.status_code}")
except requests.exceptions.ConnectionError:
    check(f"LibreChat responds at {lc_url}", False, "connection refused — is LibreChat running?")
except Exception as exc:
    check(f"LibreChat responds at {lc_url}", False, str(exc))

# ── 5. MongoDB reachability ───────────────────────────────────────────────────
print("\n[5] Checking MongoDB")
try:
    import pymongo  # type: ignore

    mongo_uri = env.get("MONGO_URI", "mongodb://localhost:27017/LibreChat")
    client = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
    client.server_info()
    check("MongoDB is reachable", True)
    client.close()
except ImportError:
    print("  SKIP  MongoDB check — pymongo not installed (pip install pymongo)")
except Exception as exc:
    check("MongoDB is reachable", False, str(exc))

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
