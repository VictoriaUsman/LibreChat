#!/usr/bin/env python3
"""
Generates one scoped LiteLLM virtual key per department defined in scripts/.env.

Reads all DEPT_<NAME>_BUDGET entries, creates a key for each, and writes the
key value back into the matching DEPT_<NAME>_KEY line in .env.

Safe to re-run — departments that already have a key are skipped.

Usage:
    python scripts/generate_department_keys.py

Requirements:
    LiteLLM must be running on LITELLM_URL with LITELLM_MASTER_KEY set.
"""

import os
import re
import sys

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

BASE_URL = os.environ.get("LITELLM_URL", "").rstrip("/")
MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
ENV_PATH = os.path.join(os.path.dirname(__file__), '.env')

if not BASE_URL or not MASTER_KEY:
    print("ERROR: LITELLM_URL and LITELLM_MASTER_KEY must be set in scripts/.env")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {MASTER_KEY}",
    "Content-Type": "application/json",
}

# --- Read .env and discover departments ---

with open(ENV_PATH, encoding='utf-8') as f:
    env_content = f.read()

budget_pattern = re.compile(r'^DEPT_([A-Z0-9]+)_BUDGET=(.+)$', re.MULTILINE)
key_pattern    = re.compile(r'^(DEPT_([A-Z0-9]+)_KEY)=(.*)$', re.MULTILINE)

departments = {m.group(1): float(m.group(2)) for m in budget_pattern.finditer(env_content)}
existing_keys = {m.group(2): m.group(3).strip() for m in key_pattern.finditer(env_content)}

if not departments:
    print("No DEPT_*_BUDGET entries found in scripts/.env — nothing to do.")
    sys.exit(0)

print(f"\nFound {len(departments)} department(s): {', '.join(departments)}\n")

created = 0
skipped = 0

for dept, budget in departments.items():
    existing = existing_keys.get(dept, "")
    if existing:
        print(f"  SKIP  {dept} — key already exists ({existing[:12]}...)")
        skipped += 1
        continue

    alias = f"dept-{dept.lower()}-phase0"
    payload = {
        "key_alias": alias,
        "key_name": f"Department: {dept.title()}",
        "models": ["ROMTech AI Standard", "ROMTech AI Fast"],
        "max_budget": budget,
        "budget_duration": "monthly",
        "metadata": {
            "department": dept.lower(),
            "team_id": f"dept-{dept.lower()}",
            "purpose": "phase0-budget-validation",
        },
        "tags": [f"dept:{dept.lower()}"],
    }

    try:
        r = requests.post(f"{BASE_URL}/key/generate", headers=HEADERS, json=payload, timeout=30)
        r.raise_for_status()
        key_value = r.json().get("key", "")
        if not key_value:
            print(f"  FAIL  {dept} — response missing key field: {r.text[:200]}")
            continue

        # Write key value back into .env
        env_content = re.sub(
            rf'^(DEPT_{dept}_KEY)=.*$',
            f'\\1={key_value}',
            env_content,
            flags=re.MULTILINE,
        )
        print(f"  OK    {dept} — budget ${budget:.3f}/month | alias: {alias} | key: {key_value[:12]}...")
        created += 1

    except requests.exceptions.ConnectionError:
        print(f"  FAIL  {dept} — cannot connect to {BASE_URL}. Is LiteLLM running?")
    except Exception as e:
        print(f"  FAIL  {dept} — {e}")

# Write updated .env back to disk
with open(ENV_PATH, 'w', encoding='utf-8') as f:
    f.write(env_content)

print(f"\nDone — {created} created, {skipped} skipped.")
if created:
    print("Key values written to scripts/.env")
