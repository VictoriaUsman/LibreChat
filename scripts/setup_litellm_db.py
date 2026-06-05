#!/usr/bin/env python3
"""Creates the litellm PostgreSQL user and database (one-time setup)."""
import sys
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

PG_SETUP_URL = os.environ.get("PG_SETUP_URL", "postgresql://postgres:TheGhost1!@localhost:5433/postgres")

conn = psycopg2.connect(PG_SETUP_URL)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()

cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'litellm'")
if not cur.fetchone():
    cur.execute("CREATE USER litellm WITH PASSWORD 'litellm_phase0'")
    print("Created user: litellm")
else:
    print("User litellm already exists")

cur.execute("SELECT 1 FROM pg_database WHERE datname = 'litellm'")
if not cur.fetchone():
    cur.execute("CREATE DATABASE litellm OWNER litellm")
    print("Created database: litellm")
else:
    print("Database litellm already exists")

conn.close()
print("Done.")
