# Running the Stack Locally — Authoritative Guide

> **Status:** Reflects an end-to-end local bring-up actually performed on Windows 11 + PostgreSQL 18.
> Supersedes the partial, drifted instructions in `LOCAL_SETUP.md` and `SETUP.md` where they conflict.
>
> **Scope:** The full four-layer stack **plus RAG**:
> `LibreChat (UI) → LiteLLM (gateway, Postgres-backed) → Azure OpenAI`, with conversation
> state in MongoDB and RAG file-upload backed by **pgvector + a RAG API service**.

This guide is written to be **environment-agnostic** (your paths, Python install, and Azure
resource names will differ) and to call out, at every step, **how local differs from production
(Azure Container Apps)**. Look for the **🟦 PROD** notes.

---

## 0. Mental model: what runs where

| Layer | Local (this guide) | 🟦 Production (ACA) |
|---|---|---|
| Chat UI | LibreChat from a local clone, `npm run backend` on `:3080` | LibreChat container in Azure Container Apps |
| Gateway | LiteLLM via `start_litellm.py` on `:4000` | LiteLLM container in ACA |
| Models | Azure OpenAI (`gpt-5.4-mini`, `text-embedding-3-small`) | Same Azure OpenAI / AI Foundry, via private endpoints |
| Conversation DB | Local **MongoDB** service | **Cosmos DB** (Mongo API) |
| Gateway DB (usage/keys/limits) | Local **PostgreSQL** service | **Azure Database for PostgreSQL** (Flexible Server) |
| RAG vector store | Local **pgvector** (compiled from source) | **pgvector enabled as a managed extension** on Azure DB for PostgreSQL — *no compile* |
| RAG service | `rag_api` from a local clone, `python main.py` on `:8000` | `rag_api` container in ACA |
| Secrets | `.env` files on disk (gitignored) | **Azure Key Vault** + managed identity |
| Auth | Local email/password test user (Okta not wired) | **Okta OIDC** over HTTPS (requires ACA) |

**The single most important local-only wrinkle:** because local Postgres runs natively on
Windows, **pgvector must be compiled from source**. In prod it is just a config flag on the
managed database. Everything in §6 (pgvector) is therefore *throwaway* — it mirrors nothing
downstream.

---

## 1. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Git | any | |
| Node.js | 20 LTS recommended | newer (24) worked, but pin 20 for parity with prod image |
| **Python** | **3.12** | ⚠️ see the single-interpreter warning below |
| PostgreSQL | 16–18 | install as a service; note the **port** and **superuser password** |
| MongoDB Community | 7.x | install as a service |
| Azure CLI (`az`) | latest | optional but lets you pull Azure OpenAI keys without the portal |
| VS C++ Build Tools 2022 | — | **Windows only**, needed to compile pgvector (§6) |

> ### ⚠️ Use exactly ONE Python interpreter
> LiteLLM's database layer uses **Prisma**, whose client generator resolves the *bare* `python`
> on your `PATH`. If you have multiple Pythons installed (e.g. 3.12 **and** 3.14), `prisma generate`
> can emit the client into the *wrong* interpreter, and LiteLLM then fails with
> `Unable to find Prisma binaries`. **Fix:** either keep a single Python, or — better and
> environment-agnostic — **use a dedicated virtual environment** for LiteLLM and run everything
> through that venv's `python`. This guide assumes one Python 3.12; substitute `<venv>\Scripts\python`
> if you use a venv.

Verify:
```powershell
python --version          # 3.12.x  (and ONLY one version resolvable)
node --version
mongod --version
psql --version
```

🟦 **PROD:** none of this applies — containers pin their own runtimes; there is no "which Python"
problem because each image has exactly one.

---

## 2. One-time: clone the upstream apps

LibreChat and the RAG API are **not** part of this repo (they're gitignored). Clone them into the
`ChatGptForEmployees/` umbrella directory (alongside `scripts/` and `config/`):

```powershell
# from <REPO_ROOT>\ChatGptForEmployees
git clone --depth 1 --branch v0.8.6-rc1 https://github.com/danny-avila/LibreChat.git LibreChat
git clone --depth 1                      https://github.com/danny-avila/rag_api.git    rag_api
```

> `ChatGptForEmployees/LibreChat/` and `ChatGptForEmployees/rag_api/` are in `.gitignore` — they are
> local checkouts and must never be committed. (Older layouts kept these at the repo root / under a
> `frontend/` prefix; the current layout is under the `ChatGptForEmployees/` umbrella.)

🟦 **PROD:** these are built as container images in CI from pinned tags, not cloned onto a dev box.

---

## 3. One-time: secrets & `.env` files

All secrets live in gitignored `.env` files (`*.env` is ignored). **Never commit them.**

### 3a. `scripts/.env` (LibreChat + LiteLLM + validation scripts)
Copy `config/librechat_env.template` → `scripts/.env` and fill in. Generate fresh secrets:
```powershell
# JWT_SECRET / JWT_REFRESH_SECRET / CREDS_KEY  → 64 hex chars
-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })
# CREDS_IV → 32 hex chars
-join ((1..16) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })
```
Key values to set:
- `MONGO_URI=mongodb://localhost:27017/LibreChat`
- `LITELLM_MASTER_KEY=sk-<random>` — LiteLLM admin key
- `LITELLM_VIRTUAL_KEY=` — **start with the master key**; replace with a scoped key after the DB is up (§5c)
- `LITELLM_URL=http://localhost:4000` — **no `/v1`** (the backend validation/health scripts append paths themselves; LibreChat's gateway URL is set separately in `librechat.yaml`)
- `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` — see §3c
- `CONFIG_PATH=<REPO_ROOT>\ChatGptForEmployees\config\librechat.yaml` (absolute)
- `DATABASE_URL=postgresql://litellm:litellm_phase0@localhost:<PGPORT>/litellm` (after §5)
- `RAG_API_URL=http://localhost:8000`

### 3b. `rag_api/.env` (RAG service)
Copy `config/rag_api.env.template` → `rag_api/.env`. **Heads-up:** the RAG API code reads the DB
connection from **`POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`** (plus `DB_HOST` / `DB_PORT`),
*not* `DB_USER` / `DB_PASS` / `DB_NAME`. Set the `POSTGRES_*` names. Also set the Azure embedding
creds (`RAG_AZURE_OPENAI_*`, deployment `text-embedding-3-small`).

### 3c. Azure OpenAI credentials
If you have `az` access to the resource:
```powershell
az cognitiveservices account keys list -n <FOUNDRY_RESOURCE> -g <RG> --query key1 -o tsv
az cognitiveservices account show     -n <FOUNDRY_RESOURCE> -g <RG> --query properties.endpoint -o tsv
```
Otherwise: Azure Portal → the AI Foundry / OpenAI resource → **Keys and Endpoint**.

🟦 **PROD:** there are **no `.env` files and no plaintext keys**. LibreChat/LiteLLM/rag_api read
secrets from **Azure Key Vault** via managed identity; Mongo→Cosmos and Postgres connection strings
are Key Vault references. The `AZURE_OPENAI_API_KEY` in particular is local-only.

---

## 4. One-time: Python deps & LibreChat build

```powershell
# LiteLLM + validation deps (into your single Python / venv)
python -m pip install "litellm[proxy]" prisma psycopg2-binary -r scripts/requirements.txt

# RAG API deps — ALWAYS in its own venv (its langchain tree must not collide with LiteLLM's deps)
python -m venv rag_api/.venv
rag_api/.venv/Scripts/python -m pip install -r rag_api/requirements.lite.txt

# LibreChat
cd LibreChat
npm ci
npm run frontend     # one-time client build (NOT a dev server); rerun only after UI/version changes
cd ..
```

> **Windows + LiteLLM Prisma:** after installing/upgrading `litellm`, run the bundled patch once —
> `python scripts/patch_prisma_windows.py` — and generate the client:
> `python -m prisma generate --schema <site-packages>/litellm/proxy/schema.prisma`.
> Without these, LiteLLM crashes on startup (a `CTRL_C_EVENT` propagation bug, and/or
> "Unable to find Prisma binaries").

🟦 **PROD:** `npm ci` / `prisma generate` happen at image-build time; the Windows Prisma patch is
irrelevant on Linux containers.

---

## 5. One-time: LiteLLM's Postgres database

Usage tracking, rate limits, and **scoped virtual keys** require Postgres. (Without it LiteLLM
still runs, but only the master key works and there's no usage/limit data.)

### 5a. Create the role + database
```powershell
# override the script's default port/superuser to match your install
$env:PG_SETUP_URL = "postgresql://postgres:<SUPERUSER_PW>@localhost:<PGPORT>/postgres"
python scripts/setup_litellm_db.py
```

### 5b. Grant schema ownership (PostgreSQL 15+)
On PG15+, non-owners can't create objects in `public`, so LiteLLM can't create its views/migrations.
Grant it (one-time, as superuser):
```sql
-- psql -d litellm
GRANT ALL ON SCHEMA public TO litellm;
ALTER SCHEMA public OWNER TO litellm;
GRANT ALL ON ALL TABLES    IN SCHEMA public TO litellm;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO litellm;
```
> If the `litellm` DB pre-existed (tables owned by `postgres`), the grants above are what make
> `/spend/logs` work and stop the `permission denied for schema public` traceback at startup.
> Benign `prisma migrate deploy` "nothing to apply" log lines are expected and harmless.

### 5c. Mint a scoped virtual key (after LiteLLM is running, §7)
Don't ship the master key to LibreChat. With LiteLLM up:
```bash
curl -s http://localhost:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"models":["ROMTech AI Standard","ROMTech AI Fast"],"key_alias":"librechat-local"}'
```
Put the returned `key` in `scripts/.env` as `LITELLM_VIRTUAL_KEY`, copy to `LibreChat/.env`, restart LibreChat.

🟦 **PROD:** managed **Azure Database for PostgreSQL**; `DATABASE_URL` is a Key Vault reference;
least-privilege roles are provisioned by IaC, not ad-hoc grants. Virtual keys are issued **per
department/team** with budgets (see the v1 PBI backlog).

---

## 6. One-time: pgvector (RAG vector store) — **local Windows build**

> 🟦 **PROD does NOT do any of this.** On Azure Database for PostgreSQL you enable pgvector by
> adding `vector` to the `azure.extensions` server parameter and running `CREATE EXTENSION vector`.
> No compiler, no DLLs, nothing committed. The steps below exist **only** because local Postgres
> runs natively on Windows.

The official pgvector project ships **source only** — there is **no** prebuilt
`pgvector-pgNN-windows-x86_64.zip` (any such download 404s). Build it:

```powershell
# 1. clone a pinned release OUTSIDE this repo (it's a throwaway build dir)
git clone --depth 1 --branch v0.8.1 https://github.com/pgvector/pgvector.git <SOMEWHERE>\pgvector

# 2. compile against your PG headers (needs VS C++ Build Tools)
#    run inside an "x64 Native Tools Command Prompt for VS 2022", OR call vcvars64.bat first:
set "PGROOT=C:\Program Files\PostgreSQL\<NN>"
cd /d <SOMEWHERE>\pgvector
nmake /F Makefile.win

# 3. install — needs ADMIN (writes into Program Files) + a service restart:
nmake /F Makefile.win install         # OR copy vector.dll→lib\, vector.control + sql\vector--*.sql→share\extension\
#    then, elevated:  Restart-Service postgresql-x64-<NN>
```

Then create the RAG database and enable the extension:
```powershell
$env:PG_SETUP_URL   = "postgresql://postgres:<SUPERUSER_PW>@localhost:<PGPORT>/postgres"
$env:RAG_DB_PASSWORD = "<pick-a-password>"   # also goes in rag_api/.env as POSTGRES_PASSWORD/DB_PASS
python scripts/setup_pgvector.py             # creates librechat_rag DB/role + CREATE EXTENSION vector
```

---

## 7. Running it (three terminals)

Start order matters: **LiteLLM → RAG API → LibreChat**.

**Terminal 1 — LiteLLM (`:4000`)** — from `<REPO_ROOT>\ChatGptForEmployees`:
```powershell
$env:PYTHONUTF8 = "1"        # REQUIRED on Windows: LiteLLM's startup banner crashes the cp1252 console otherwise
$env:PYTHONPATH = "config"   # REQUIRED: lets LiteLLM import the telemetry callback (config/callbacks/…)
python scripts/start_litellm.py
```

**Terminal 2 — RAG API (`:8000`)**:
```powershell
cd <REPO_ROOT>\ChatGptForEmployees\rag_api
.\.venv\Scripts\python.exe main.py
```

**Terminal 3 — LibreChat (`:3080`)**:
```powershell
cd <REPO_ROOT>\ChatGptForEmployees\LibreChat
npm run backend
```

> If you change `scripts\.env`, re-sync it: `Copy-Item scripts\.env LibreChat\.env`, then restart LibreChat.
> If you start LibreChat **before** the RAG API, it logs "RAG API not reachable" — restart it once RAG is up.

Open **http://localhost:3080**, create a user once (registration is disabled):
```powershell
cd LibreChat; npm run create-user -- <email> "<name>" <username> "<password>" --email-verified=true
```
(The `--` is required, or npm swallows the args.)

🟦 **PROD:** all three are ACA containers started by the platform; no terminals, no manual user
creation (users come from Okta), `NODE_ENV=production`, HTTPS ingress.

---

## 8. Validation

Run with `PYTHONUTF8=1` (scripts print Unicode that the Windows console otherwise can't encode):
```powershell
$env:PYTHONUTF8="1"
python scripts/validate_librechat.py             # health
python scripts/validate_librechat_litellm.py     # chat + streaming through the gateway
python scripts/validate_litellm.py               # gateway health/auth   (needs LITELLM_URL WITHOUT /v1)
python scripts/validate_litellm_routing.py       # routing/allowlist
python scripts/validate_litellm_rate_limits.py   # 429 enforcement      (needs Postgres)
python scripts/validate_litellm_usage.py         # spend logs           (needs Postgres)
python scripts/validate_rag_api.py               # RAG: upload→embed→pgvector
python scripts/validate_e2e_rag.py               # RAG end-to-end (upload, retrieve, isolation, reject)
```

---

## 9. Gotchas we actually hit (and the fixes baked into the configs)

| Symptom | Cause | Fix |
|---|---|---|
| LiteLLM exits on the ASCII banner | Windows cp1252 console can't encode the banner | run with `PYTHONUTF8=1` |
| `Unable to find Prisma binaries` / immediate exit | Prisma client not generated, or generated into the wrong Python | single interpreter (or venv); `prisma generate`; `patch_prisma_windows.py` |
| `permission denied for schema public` at LiteLLM startup | PG15+ + pre-existing `litellm` tables owned by `postgres` | grants in §5b |
| Model picker presets / system prompt ignored ("Skipping model spec") | `modelSpecs` used `endpoint: "custom"` | use the custom endpoint **name** — fixed in `config/librechat.yaml` → `endpoint: "LiteLLM Gateway"` |
| Chat works but **auto-titles fail**, or any `max_tokens` request → HTTP 400 | `gpt-5.4-mini` requires `max_completion_tokens`; `drop_params` doesn't catch it because `base_model` (gpt-4o-mini) reports `max_tokens` as supported | `additional_drop_params: ["max_tokens"]` per model — fixed in `config/litellm_routing_config.yaml` |
| pgvector "download the zip" step 404s | official pgvector has no Windows binaries | build from source (§6) |
| `validate_litellm.py` health → 404 | `LITELLM_URL` included `/v1`; health is not under `/v1` | set `LITELLM_URL=http://localhost:4000` (no `/v1`) |

---

## 10. Local vs Prod — quick reference

- **No `.env`/plaintext keys in prod** → Key Vault + managed identity.
- **No pgvector compile in prod** → managed extension flag on Azure DB for PostgreSQL.
- **No Windows Prisma patch / `PYTHONUTF8` in prod** → Linux containers.
- **Mongo → Cosmos DB; local PG → Azure DB for PostgreSQL.**
- **Master key locally is convenient; prod uses per-team scoped virtual keys with budgets.**
- **Okta is not testable locally** (needs HTTPS + ACA) — local uses an email/password test user.
- **Two model slots point at one Azure deployment in Phase 0** — prod provisions two distinct deployments.
- **`config/librechat.yaml baseURL` and the two config fixes** (modelSpecs endpoint, `max_tokens`) apply to prod too and should be carried into the deployed config.

---

## 11. Known doc/config gaps found during this bring-up

These were corrected or are flagged for the team:
- `config/rag_api.env.template` used `DB_USER/DB_PASS/DB_NAME`; the code reads `POSTGRES_USER/PASSWORD/DB` — **template corrected**.
- `scripts/setup_pgvector.py` prerequisites told you to download a prebuilt Windows zip that doesn't exist — **docstring corrected** to build-from-source.
- `config/dev2_handoff.md` has a scoped LiteLLM **virtual key** committed in plaintext. Calibrated
  view: it's a gateway-issued, allowlist-scoped token (not an Azure or master key) that is only
  valid against the specific LiteLLM Postgres DB that minted it — so it's effectively dead anywhere
  else (verified 401 against a fresh DB). **Hygiene, not incident:** going forward keep real keys out
  of committed handoffs — fill `config/dev2_handoff.md.template` with a placeholder and pass the
  actual key to the recipient out-of-band. Scrubbing this value from history is optional tidiness,
  not urgent remediation.
- Several env-var name conventions differ between the RAG app (`POSTGRES_*`/`DB_*`), the validation
  scripts (`RAG_DB_*`, `RAG_AZURE_OPENAI_*`), and the gateway scripts — set all the names the
  consuming script expects (this guide lists them per file).
