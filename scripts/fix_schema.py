"""Check and add missing columns to bring the DB in sync with LiteLLM 1.86.2 schema.prisma."""
import psycopg2

DB_URL = "postgresql://litellm:litellm_phase0@localhost:5432/litellm"

NEEDED = [
    ("LiteLLM_VerificationToken", "budget_limits",            "JSONB"),
    ("LiteLLM_TeamTable",         "default_team_member_models","TEXT[] DEFAULT '{}'"),
    ("LiteLLM_TeamTable",         "budget_limits",             "JSONB"),
]

conn = psycopg2.connect(DB_URL)
conn.autocommit = True
cur = conn.cursor()

for table, column, col_type in NEEDED:
    cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
        (table, column),
    )
    exists = cur.fetchone()
    if exists:
        print(f"  OK      {table}.{column} already exists")
    else:
        cur.execute(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {col_type}')
        print(f"  ADDED   {table}.{column} ({col_type})")

conn.close()
print("\nDone.")
