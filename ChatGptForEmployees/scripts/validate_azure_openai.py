#!/usr/bin/env python3
"""
Validates Azure AI Foundry / Azure OpenAI test endpoints against Phase 0
acceptance criteria.

Tests run against each configured deployment:
  1. Direct chat completion returns a valid response
  2. Streaming works end-to-end
  3. An invalid API key returns a 401 error (not a silent failure)

Two deployments are expected per Erik's architecture recommendation:
  - Flagship  (GPT-4-class)       — AZURE_OPENAI_DEPLOYMENT_FLAGSHIP
  - Fast      (GPT-4o-mini-class) — AZURE_OPENAI_DEPLOYMENT_FAST

Usage:
  pip install -r requirements.txt
  cp ../config/azure_openai.env.template .env   # fill in all values
  python validate_azure_openai.py

Required environment variables (or .env file in this directory):
  AZURE_OPENAI_ENDPOINT
  AZURE_OPENAI_API_KEY
  AZURE_OPENAI_API_VERSION
  AZURE_OPENAI_DEPLOYMENT_FLAGSHIP
  AZURE_OPENAI_DEPLOYMENT_FAST
"""

import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # .env loading is optional; env vars may already be set

try:
    from openai import AzureOpenAI, AuthenticationError
except ImportError:
    print("ERROR: openai package not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

# --- Configuration ---

ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01")
DEPLOYMENT_FLAGSHIP = os.environ.get("AZURE_OPENAI_DEPLOYMENT_FLAGSHIP", "")
DEPLOYMENT_FAST = os.environ.get("AZURE_OPENAI_DEPLOYMENT_FAST", "")

missing = [k for k, v in {
    "AZURE_OPENAI_ENDPOINT": ENDPOINT,
    "AZURE_OPENAI_API_KEY": API_KEY,
    "AZURE_OPENAI_DEPLOYMENT_FLAGSHIP": DEPLOYMENT_FLAGSHIP,
    "AZURE_OPENAI_DEPLOYMENT_FAST": DEPLOYMENT_FAST,
}.items() if not v]

if missing:
    print("ERROR: Missing required environment variables:")
    for k in missing:
        print(f"  {k}")
    print("\nCopy config/azure_openai.env.template to scripts/.env and fill in the values.")
    sys.exit(1)

BAA_FLAGSHIP = os.environ.get("AZURE_OPENAI_DEPLOYMENT_FLAGSHIP_BAA_VERIFIED", "no").strip().lower()
BAA_FAST = os.environ.get("AZURE_OPENAI_DEPLOYMENT_FAST_BAA_VERIFIED", "no").strip().lower()

TEST_MESSAGE = [{"role": "user", "content": "Reply with the single word: OK"}]
INVALID_KEY = "invalid-key-00000000000000000000000000000000000"

DEPLOYMENTS = [
    ("Flagship", DEPLOYMENT_FLAGSHIP, BAA_FLAGSHIP),
    ("Fast",     DEPLOYMENT_FAST,     BAA_FAST),
]

total_passed = 0
total_failed = 0


def ok(label):
    global total_passed
    total_passed += 1
    print(f"    PASS  {label}")


def fail(label, detail=""):
    global total_failed
    total_failed += 1
    print(f"    FAIL  {label}")
    if detail:
        print(f"          {detail}")


def warn(label):
    print(f"    WARN  {label}")


# --- Header ---

print()
print("Azure AI Foundry / Azure OpenAI — Phase 0 Endpoint Validation")
print(f"  Endpoint:    {ENDPOINT}")
print(f"  API Version: {API_VERSION}")
print()

client = AzureOpenAI(
    azure_endpoint=ENDPOINT,
    api_key=API_KEY,
    api_version=API_VERSION,
)

# --- Run tests for each deployment ---

for label, deployment, baa_verified in DEPLOYMENTS:

    print(f"{'=' * 50}")
    print(f"Deployment: {label} ({deployment})")
    print(f"{'=' * 50}")

    if baa_verified != "yes":
        warn("BAA_VERIFIED is not set to 'yes' — confirm this deployment is BAA-eligible before use in production")

    # Test 1: Direct chat completion
    print()
    print("  1. Direct chat completion")
    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=TEST_MESSAGE,
        )
        content = response.choices[0].message.content if response.choices else ""
        if content:
            ok(f"Response received: {content.strip()[:80]!r}")
        else:
            fail("Response body was empty")
    except Exception as e:
        fail("Request failed", str(e))

    # Test 2: Streaming
    print()
    print("  2. Streaming response")
    try:
        stream = client.chat.completions.create(
            model=deployment,
            messages=TEST_MESSAGE,
            stream=True,
        )
        chunks = []
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    chunks.append(delta)
        if chunks:
            ok(f"Streamed {len(chunks)} chunk(s): {''.join(chunks).strip()[:80]!r}")
        else:
            fail("Stream completed but returned no content chunks")
    except Exception as e:
        fail("Streaming request failed", str(e))

    # Test 3: Invalid key returns 401
    print()
    print("  3. Invalid API key returns 401 (not silent failure)")
    try:
        bad_client = AzureOpenAI(
            azure_endpoint=ENDPOINT,
            api_key=INVALID_KEY,
            api_version=API_VERSION,
        )
        bad_client.chat.completions.create(
            model=deployment,
            messages=TEST_MESSAGE,
        )
        fail(
            "Expected a 401 AuthenticationError but the request succeeded",
            "The endpoint is not validating keys — do not proceed until this is resolved",
        )
    except AuthenticationError:
        ok("Returned 401 AuthenticationError as expected")
    except Exception as e:
        fail("Unexpected error type (expected 401 AuthenticationError)", str(e))

    print()

# --- Summary ---

print("=" * 50)
total = total_passed + total_failed
print(f"Results: {total_passed}/{total} passed", "" if total_failed == 0 else f"— {total_failed} FAILED")
print()

sys.exit(0 if total_failed == 0 else 1)
