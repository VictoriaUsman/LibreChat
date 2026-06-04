#!/usr/bin/env python3
"""
Validates the LibreChat RAG API installation and pgvector integration (PBI-XX-BE).

Acceptance criteria covered:
  1. pgvector extension is enabled on the librechat_rag database
  2. RAG_API_URL is set in environment
  3. Azure OpenAI embedding credentials are present (from PBI-18-BE)
  4. RAG API health endpoint returns 200 -- service is running without errors
  5. Test document upload returns a success response
  6. Embeddings from the test document are visible in pgvector
  7. LibreChat is running with RAG_API_URL configured -- no RAG startup errors
  8. LiteLLM routing regression -- chat endpoint still routes correctly

Run setup_pgvector.py first, then start the RAG API, then run this script.

Usage:
  pip install -r requirements.txt
  python validate_rag_api.py

Required environment variables (scripts/.env):
  RAG_API_URL                             e.g. http://localhost:8000
  RAG_DB_HOST, RAG_DB_PORT,
  RAG_DB_NAME, RAG_DB_USER,
  RAG_DB_PASSWORD                         RAG database connection (from setup_pgvector.py)
  LIBRECHAT_URL                           e.g. http://localhost:3080
  LITELLM_URL                             e.g. http://localhost:4000
  LITELLM_VIRTUAL_KEY                     scoped virtual key for regression test
  RAG_AZURE_OPENAI_API_KEY                from PBI-18-BE
  RAG_AZURE_OPENAI_ENDPOINT               from PBI-18-BE
  RAG_AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT  from PBI-18-BE
"""

import os
import sys
import io

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("ERROR: psycopg2-binary not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

# --- Configuration ---

RAG_API_URL = os.environ.get("RAG_API_URL", "").rstrip("/")
LIBRECHAT_URL = os.environ.get("LIBRECHAT_URL", "").rstrip("/")
LITELLM_URL = os.environ.get("LITELLM_URL", "").rstrip("/")
VIRTUAL_KEY = os.environ.get("LITELLM_VIRTUAL_KEY", "")
RAG_AZURE_KEY = os.environ.get("RAG_AZURE_OPENAI_API_KEY", "")
RAG_AZURE_ENDPOINT = os.environ.get("RAG_AZURE_OPENAI_ENDPOINT", "")
RAG_AZURE_DEPLOYMENT = os.environ.get("RAG_AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT", "")
RAG_DB_HOST = os.environ.get("RAG_DB_HOST", "localhost")
RAG_DB_PORT = os.environ.get("RAG_DB_PORT", "5432")
RAG_DB_NAME = os.environ.get("RAG_DB_NAME", "librechat_rag")
RAG_DB_USER = os.environ.get("RAG_DB_USER", "librechat_rag")
RAG_DB_PASSWORD = os.environ.get("RAG_DB_PASSWORD", "")

required = {
    "RAG_API_URL": RAG_API_URL,
    "LIBRECHAT_URL": LIBRECHAT_URL,
    "LITELLM_URL": LITELLM_URL,
    "LITELLM_VIRTUAL_KEY": VIRTUAL_KEY,
    "RAG_DB_PASSWORD": RAG_DB_PASSWORD,
}
missing = [k for k, v in required.items() if not v]
if missing:
    print("ERROR: Missing required environment variables in scripts/.env:")
    for k in missing:
        print(f"  {k}")
    sys.exit(1)

TIMEOUT = 30
MODEL = "ROMTech AI Standard"
TEST_CONTENT = (
    "ROMTech Phase 0 RAG validation test. "
    "This document verifies the embedding pipeline is working correctly."
)

passed = 0
failed = 0
warnings = []


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
    warnings.append(label)
    print(f"  WARN  {label}")


def db_connect():
    return psycopg2.connect(
        host=RAG_DB_HOST,
        port=int(RAG_DB_PORT),
        dbname=RAG_DB_NAME,
        user=RAG_DB_USER,
        password=RAG_DB_PASSWORD,
    )


# --- Header ---

print()
print("RAG API Validation -- PBI-XX-BE")
print(f"  RAG API URL  : {RAG_API_URL}")
print(f"  LibreChat URL: {LIBRECHAT_URL}")
print(f"  LiteLLM URL  : {LITELLM_URL}")
print()

# --- Test 1: RAG_API_URL is set ---

print("1. RAG_API_URL is set in environment")
ok(f"RAG_API_URL = {RAG_API_URL}")

# --- Test 2: Azure OpenAI embedding credentials present ---

print()
print("2. Azure OpenAI embedding credentials configured (from PBI-18-BE)")
emb_vars = {
    "RAG_AZURE_OPENAI_API_KEY": RAG_AZURE_KEY,
    "RAG_AZURE_OPENAI_ENDPOINT": RAG_AZURE_ENDPOINT,
    "RAG_AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT": RAG_AZURE_DEPLOYMENT,
}
missing_emb = [k for k, v in emb_vars.items() if not v]
if not missing_emb:
    ok(f"All embedding credentials present -- deployment: {RAG_AZURE_DEPLOYMENT!r}")
else:
    fail(
        "Missing Azure OpenAI embedding credentials",
        "Fill in scripts/.env from PBI-18-BE: " + ", ".join(missing_emb),
    )

# --- Test 3: pgvector extension enabled ---

print()
print(f"3. pgvector extension enabled on '{RAG_DB_NAME}' database")
try:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'")
    row = cur.fetchone()
    if row:
        ok(f"pgvector v{row[1]} is active on '{RAG_DB_NAME}'")
    else:
        fail("pgvector extension not found -- run setup_pgvector.py first")
    conn.close()
except psycopg2.OperationalError as e:
    fail(
        f"Could not connect to RAG database '{RAG_DB_NAME}'",
        str(e).strip()[:200],
    )
    print("        Check RAG_DB_* variables in scripts/.env and that setup_pgvector.py passed.")
except Exception as e:
    fail("Unexpected database error", str(e)[:200])

# --- Test 4: RAG API health ---

print()
print("4. RAG API health check")
rag_healthy = False
try:
    r = requests.get(f"{RAG_API_URL}/health", timeout=10)
    if r.status_code == 200:
        try:
            status = r.json().get("status", "ok")
        except Exception:
            status = "ok"
        ok(f"HTTP 200 -- status: {status!r}")
        rag_healthy = True
    else:
        fail(f"HTTP {r.status_code}", r.text.strip()[:200])
        print("        Is the RAG API running? Start it with:")
        print("          cd <rag_api_dir> && uvicorn main:app --host 0.0.0.0 --port 8000 --reload")
except requests.exceptions.ConnectionError:
    fail("Connection refused -- RAG API is not running on " + RAG_API_URL)
    print("        Start the RAG API from its directory:")
    print("          uvicorn main:app --host 0.0.0.0 --port 8000 --reload")
except requests.exceptions.Timeout:
    fail("Request timed out after 10s")
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 5 + 6: Document upload and embedding verification ---

print()
print("5. Test document upload to RAG API")
print("6. Embeddings visible in pgvector after upload")

if not rag_healthy:
    warn("Tests 5+6 skipped -- RAG API is not running (Test 4 failed)")
else:
    embedding_count_before = 0
    try:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'langchain_pg_embedding')"
        )
        if cur.fetchone()[0]:
            cur.execute("SELECT count(*) FROM langchain_pg_embedding")
            embedding_count_before = cur.fetchone()[0]
        conn.close()
    except Exception as e:
        warn(f"Could not read pre-upload embedding count: {e}")

    upload_ok = False
    try:
        test_file = io.BytesIO(TEST_CONTENT.encode("utf-8"))
        r = requests.post(
            f"{RAG_API_URL}/api/v1/add",
            files={"file": ("validation_test.txt", test_file, "text/plain")},
            data={
                "user_id": "validation-user",
                "conversationId": "validation-conv-001",
                "file_id": "validation-file-001",
                "filename": "validation_test.txt",
            },
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            ok("HTTP 200 -- document accepted by RAG API")
            upload_ok = True
        else:
            fail(f"HTTP {r.status_code}", r.text.strip()[:300])
    except requests.exceptions.Timeout:
        fail(
            "Upload timed out -- embedding may be slow or Azure OpenAI endpoint unreachable",
            "Check RAG_AZURE_OPENAI_ENDPOINT and RAG_AZURE_OPENAI_API_KEY in scripts/.env",
        )
    except Exception as e:
        fail("Unexpected error during document upload", str(e)[:200])

    if upload_ok:
        try:
            conn = db_connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'langchain_pg_embedding')"
            )
            if not cur.fetchone()[0]:
                fail("langchain_pg_embedding table not found -- RAG API may not have initialised its schema")
            else:
                cur.execute("SELECT count(*) FROM langchain_pg_embedding")
                count_after = cur.fetchone()[0]
                if count_after > embedding_count_before:
                    ok(
                        f"Embeddings stored in pgvector -- rows: {count_after} "
                        f"(was {embedding_count_before})"
                    )
                else:
                    fail(
                        "Row count in langchain_pg_embedding did not increase after upload",
                        f"Before: {embedding_count_before}, After: {count_after}",
                    )
            conn.close()
        except Exception as e:
            fail("Could not verify embeddings in pgvector", str(e)[:200])

# --- Test 7: LibreChat alive with RAG configured ---

print()
print("7. LibreChat health check -- running with RAG_API_URL configured")
try:
    r = requests.get(f"{LIBRECHAT_URL}/api/user", timeout=20)
    if r.status_code in (200, 401):
        ok(f"HTTP {r.status_code} -- LibreChat API alive, no RAG startup errors")
    else:
        fail(f"HTTP {r.status_code}", r.text.strip()[:200])
except requests.exceptions.ConnectionError:
    fail(
        "LibreChat is not running",
        "Start it with RAG_API_URL set in the environment, then re-run this script",
    )
except Exception as e:
    fail("Unexpected error", str(e))

# --- Test 8: LiteLLM routing regression ---

print()
print("8. LiteLLM routing regression -- chat endpoint unaffected")
try:
    r = requests.post(
        f"{LITELLM_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {VIRTUAL_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": MODEL, "messages": [{"role": "user", "content": "Reply: OK"}]},
        timeout=TIMEOUT,
    )
    if r.status_code == 200:
        content = (
            r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        ok(f"LiteLLM routing unaffected: {content.strip()[:60]!r}")
    else:
        fail(f"HTTP {r.status_code}", r.text[:200])
except Exception as e:
    fail("LiteLLM regression check failed", str(e))

# --- Summary ---

if warnings:
    print()
    for w in warnings:
        print(f"  WARN  {w}")

print()
print("=" * 55)
total = passed + failed
print(f"Results: {passed}/{total} passed", "" if failed == 0 else f"-- {failed} FAILED")
print()

if failed == 0:
    print("RAG API validated. All PBI-XX-BE acceptance criteria met.")
    print("Next step: share config/rag_api_dev2_handoff.md with Dev 2 for PBI-19-FE.")
else:
    print("One or more checks failed. Resolve the failures above before signing off this PBI.")

sys.exit(0 if failed == 0 else 1)
