#!/usr/bin/env python3
"""
Sets up pgvector on the local PostgreSQL instance for the LibreChat RAG API (PBI-XX-BE).

What this script does:
  1. Verifies the PostgreSQL server is reachable via PG_SETUP_URL
  2. Creates the librechat_rag role if it does not exist
  3. Creates the librechat_rag database if it does not exist
  4. Enables the pgvector extension (CREATE EXTENSION IF NOT EXISTS vector)
  5. Grants the role full access to its database and public schema

Prerequisites — the pgvector extension must be installed on the PostgreSQL
server first (this script only runs CREATE EXTENSION; it cannot install the binary).

  NOTE: pgvector ships SOURCE ONLY. There is no official prebuilt
  "pgvector-pg<NN>-windows-x86_64.zip" on the releases page — those URLs 404.
  On Windows you must compile it. (In production this is a non-issue: Azure
  Database for PostgreSQL offers pgvector as a managed extension — just add
  'vector' to azure.extensions and run CREATE EXTENSION.)

  Windows build-from-source:
    1. Install "Build Tools for Visual Studio 2022" with the
       "Desktop development with C++" workload.
    2. Clone a pinned release (outside this repo — it's a throwaway build dir):
         git clone --depth 1 --branch v0.8.1 https://github.com/pgvector/pgvector.git
    3. In an "x64 Native Tools Command Prompt for VS 2022" (or after calling
       vcvars64.bat), compile against your PG headers:
         set "PGROOT=C:\\Program Files\\PostgreSQL\\<NN>"
         cd <clone>
         nmake /F Makefile.win
    4. Install (needs ADMIN — writes into Program Files) then restart the service:
         nmake /F Makefile.win install
         #   ... or copy manually:
         #   vector.dll     -> C:\\Program Files\\PostgreSQL\\<NN>\\lib\\
         #   vector.control -> C:\\Program Files\\PostgreSQL\\<NN>\\share\\extension\\
         #   sql\\vector--*.sql -> C:\\Program Files\\PostgreSQL\\<NN>\\share\\extension\\
         Restart-Service postgresql-x64-<NN>      # elevated

  See RUN_LOCAL.md §6 for the full walkthrough.

Usage:
  pip install -r requirements.txt
  python setup_pgvector.py

Required environment variables (scripts/.env):
  PG_SETUP_URL     Superuser connection string (used only by this setup script)
                   e.g. postgresql://postgres:yourpassword@localhost:5432/postgres
  RAG_DB_PASSWORD  Password for the librechat_rag role (created by this script)

Optional:
  RAG_DB_NAME      Database name (default: librechat_rag)
  RAG_DB_USER      Database role name (default: librechat_rag)
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
    import psycopg2
    from psycopg2 import sql as pgsql
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:
    print("ERROR: psycopg2-binary not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

# --- Configuration ---

PG_SETUP_URL = os.environ.get("PG_SETUP_URL", "").strip()
RAG_DB_PASSWORD = os.environ.get("RAG_DB_PASSWORD", "").strip()
RAG_DB_NAME = os.environ.get("RAG_DB_NAME", "librechat_rag")
RAG_DB_USER = os.environ.get("RAG_DB_USER", "librechat_rag")

missing = []
if not PG_SETUP_URL:
    missing.append("PG_SETUP_URL  (e.g. postgresql://postgres:yourpassword@localhost:5432/postgres)")
if not RAG_DB_PASSWORD:
    missing.append("RAG_DB_PASSWORD  (password for the new librechat_rag database role)")

if missing:
    print("ERROR: Missing required environment variables in scripts/.env:")
    for m in missing:
        print(f"  {m}")
    sys.exit(1)

passed = 0
failed = 0


def ok(label):
    global passed
    passed += 1
    print(f"  DONE  {label}")


def fail(label, detail=""):
    global failed
    failed += 1
    print(f"  FAIL  {label}")
    if detail:
        print(f"        {detail}")


def skip(label):
    print(f"  SKIP  {label}")


# --- Header ---

print()
print("pgvector Setup -- LibreChat RAG API (PBI-XX-BE)")
print(f"  Target database : {RAG_DB_NAME}")
print(f"  Target role     : {RAG_DB_USER}")
print()

# --- Step 1: Connect to PostgreSQL as superuser ---

print("1. Connect to PostgreSQL server")
conn = None
try:
    conn = psycopg2.connect(PG_SETUP_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT version()")
    version = cur.fetchone()[0]
    ok(f"Connected -- {version.split(',')[0]}")
except psycopg2.OperationalError as e:
    fail("Could not connect to PostgreSQL", str(e).strip())
    print()
    print("  Troubleshooting:")
    print("    - Is PostgreSQL running? Check Windows Services (services.msc)")
    print("    - Is PG_SETUP_URL correct? Format: postgresql://user:pass@host:port/postgres")
    print("    - Does the user have superuser privileges?")
    sys.exit(1)

# --- Step 2: Create librechat_rag role ---

print()
print(f"2. Create role '{RAG_DB_USER}'")
try:
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (RAG_DB_USER,))
    if cur.fetchone():
        skip(f"Role '{RAG_DB_USER}' already exists")
    else:
        cur.execute(
            pgsql.SQL("CREATE USER {} WITH PASSWORD %s").format(
                pgsql.Identifier(RAG_DB_USER)
            ),
            [RAG_DB_PASSWORD],
        )
        ok(f"Role '{RAG_DB_USER}' created")
except psycopg2.Error as e:
    fail(f"Could not create role '{RAG_DB_USER}'", str(e).strip())

# --- Step 3: Create librechat_rag database ---

print()
print(f"3. Create database '{RAG_DB_NAME}'")
try:
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (RAG_DB_NAME,))
    if cur.fetchone():
        skip(f"Database '{RAG_DB_NAME}' already exists")
    else:
        cur.execute(
            pgsql.SQL("CREATE DATABASE {} OWNER {}").format(
                pgsql.Identifier(RAG_DB_NAME),
                pgsql.Identifier(RAG_DB_USER),
            )
        )
        ok(f"Database '{RAG_DB_NAME}' created")
except psycopg2.Error as e:
    fail(f"Could not create database '{RAG_DB_NAME}'", str(e).strip())

conn.close()

# --- Steps 4-6: Connect to the new database ---

parsed = urllib.parse.urlparse(PG_SETUP_URL)
rag_setup_url = parsed._replace(path=f"/{RAG_DB_NAME}").geturl()

conn2 = None
try:
    conn2 = psycopg2.connect(rag_setup_url)
    conn2.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur2 = conn2.cursor()
except psycopg2.OperationalError as e:
    fail(f"Could not connect to '{RAG_DB_NAME}' database", str(e).strip())
    sys.exit(1)

# --- Step 4: Enable pgvector extension ---

print()
print("4. Enable pgvector extension")
try:
    cur2.execute("CREATE EXTENSION IF NOT EXISTS vector")
    ok("CREATE EXTENSION IF NOT EXISTS vector -- succeeded")
except psycopg2.Error as e:
    fail("CREATE EXTENSION vector failed", str(e).strip())
    print()
    print("  This usually means pgvector is not installed on the PostgreSQL server.")
    print("  Follow the Windows installation steps in the Prerequisites section above.")
    conn2.close()
    sys.exit(1)

# --- Step 5: Verify extension is active ---

print()
print("5. Verify extension is registered")
cur2.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'")
row = cur2.fetchone()
if row:
    ok(f"Extension 'vector' v{row[1]} confirmed in pg_extension")
else:
    fail("Extension 'vector' not found in pg_extension after CREATE EXTENSION")

# --- Step 6: Grant schema privileges ---

print()
print(f"6. Grant schema privileges to '{RAG_DB_USER}'")
try:
    cur2.execute(
        pgsql.SQL("GRANT ALL ON SCHEMA public TO {}").format(pgsql.Identifier(RAG_DB_USER))
    )
    cur2.execute(
        pgsql.SQL(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {}"
        ).format(pgsql.Identifier(RAG_DB_USER))
    )
    ok(f"Schema public: full access granted to '{RAG_DB_USER}'")
except psycopg2.Error as e:
    fail("Could not grant schema privileges", str(e).strip())

conn2.close()

# --- Summary ---

print()
print("=" * 50)
total = passed + failed
print(f"Results: {passed}/{total} steps completed", "" if failed == 0 else f"-- {failed} FAILED")
print()

if failed == 0:
    print("pgvector setup complete.")
    print(f"  Database: {RAG_DB_NAME}")
    print(f"  Role    : {RAG_DB_USER}")
    print()
    print("Next steps:")
    print("  1. Clone the LibreChat RAG API (see config/rag_api_dev2_handoff.md)")
    print("  2. Copy config/rag_api.env.template into the rag_api directory as .env")
    print("     and fill in the Azure OpenAI embedding credentials from PBI-18-BE")
    print("  3. Start the RAG API: uvicorn main:app --host 0.0.0.0 --port 8000 --reload")
    print("  4. Run: python scripts/validate_rag_api.py")
else:
    print("One or more steps failed. Resolve the errors above before proceeding.")

sys.exit(0 if failed == 0 else 1)
