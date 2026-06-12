# Local Development Setup Guide — PBI 9565

> ⚠️ **Superseded by [RUN_LOCAL.md](RUN_LOCAL.md)** for an actually-verified, end-to-end bring-up
> (including RAG/pgvector, the Postgres/Prisma steps, and local-vs-prod notes). This document
> predates several fixes and assumes LibreChat is pre-cloned and that a prebuilt Windows pgvector
> exists (it doesn't). Use RUN_LOCAL.md; keep this only for the PBI-9565 acceptance-criteria history.

> **Goal:** Get the full local stack (LiteLLM → LibreChat → MongoDB) running on a fresh Windows machine from scratch.
>
> **All commands run from the repo root** (`ChatGptForEmployees\`) unless a step says otherwise.

---

## Prerequisites

Install all of the following before starting.

| Tool | Version | Install |
|------|---------|---------|
| Git | any | already have it |
| Node.js | 20 LTS | https://nodejs.org/en/download (choose "LTS") |
| Python | 3.8+ | https://www.python.org/downloads/windows/ — check **Add Python to PATH** |
| MongoDB Community Server | 7.x | https://www.mongodb.com/try/download/community — choose **Windows MSI**, install MongoD as a Service |
| Azure CLI | latest | https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows |

Verify each tool after install:

```powershell
node --version        # v20.x.x
python --version      # Python 3.x.x
mongod --version      # db version v7.x.x
az --version          # azure-cli x.x.x
```

---

## Step 1 — Get credentials from Dev 1 (PBI-01-BE handoff)

You need the following before you can fill in any config files:

| Value | Source |
|-------|--------|
| `LITELLM_VIRTUAL_KEY` | Scoped virtual key issued by Dev 1 (not the master key) |
| `LITELLM_URL` | Local LiteLLM base URL, e.g. `http://localhost:4000` |
| `AZURE_OPENAI_API_KEY` | See Step 2 below — find in Azure Portal |
| `AZURE_OPENAI_ENDPOINT` | See Step 2 below — find in Azure Portal |

### Step 2 — Find Azure OpenAI values in the Azure Portal

1. Open **portal.azure.com** and sign in with your ROMTech account.
2. Search for **Azure AI Foundry** (or navigate to **Cognitive Services**).
3. Open the resource named `aiswebsitechatbotdev` (or the resource Dev 1 points you to).
4. In the left sidebar click **Keys and Endpoint**.
5. Copy **KEY 1** → this is `AZURE_OPENAI_API_KEY`.
6. Copy **Endpoint** (format: `https://<name>.services.ai.azure.com`) → this is `AZURE_OPENAI_ENDPOINT`.

---

## Step 3 — Install LibreChat dependencies

```powershell
cd LibreChat
npm ci
cd ..
```

`npm ci` should complete without errors (may take a few minutes on first run).

---

## Step 4 — Start MongoDB

MongoDB should already be running as a Windows service after the MSI install. Verify:

```powershell
Get-Service MongoDB
```

Expected: `Running`. If not:

```powershell
Start-Service MongoDB
```

> **Azure note:** The local `MONGO_URI=mongodb://localhost:27017/LibreChat` is for local dev only.
> When deployed to Azure, this will be replaced with an Azure Cosmos DB for MongoDB connection string.

---

## Step 5 — Generate secrets

Run each command once and save the output — you will paste the values into `scripts\.env` in the next step.

```powershell
# JWT_SECRET (64 hex chars)
-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })

# JWT_REFRESH_SECRET (64 hex chars)
-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })

# CREDS_KEY (64 hex chars — must be exactly 32 bytes)
-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })

# CREDS_IV (32 hex chars — must be exactly 16 bytes)
-join ((1..16) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })

# LITELLM_MASTER_KEY — used to authenticate requests to the local LiteLLM proxy
-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })
```

Or with openssl (Git Bash / WSL):

```bash
openssl rand -hex 32   # JWT_SECRET, JWT_REFRESH_SECRET, CREDS_KEY, LITELLM_MASTER_KEY
openssl rand -hex 16   # CREDS_IV
```

---

## Step 6 — Create scripts/.env

Copy the template and fill it in:

```powershell
Copy-Item config\librechat_env.template scripts\.env
```

Open `scripts\.env` and set every value:

```dotenv
# Network binding (local dev)
HOST=localhost
PORT=3080

# Secrets — paste the values generated in Step 5
JWT_SECRET=<generated>
JWT_REFRESH_SECRET=<generated>
CREDS_KEY=<generated>
CREDS_IV=<generated>

# MongoDB (local)
MONGO_URI=mongodb://localhost:27017/LibreChat

# LiteLLM — from Dev 1 handoff (Step 1)
LITELLM_URL=http://localhost:4000
LITELLM_VIRTUAL_KEY=<virtual key from Dev 1>

# Azure OpenAI — from Azure Portal (Step 2)
# TEMPORARY: Phase 0 / local dev only. Remove after PBI 9126 LiteLLM switch.
AZURE_OPENAI_API_KEY=<key from Azure Portal>
AZURE_OPENAI_ENDPOINT=<endpoint from Azure Portal>

# Okta OIDC — leave blank until PBI 9129 (Okta access not yet provisioned)
# Full Okta login requires HTTPS and an ACA deployment — not testable locally.
# These variables must be present (even if empty) so the container starts without error.
OPENID_CLIENT_ID=
OPENID_CLIENT_SECRET=
OPENID_ISSUER=https://romtech.okta.com/oauth2/default
OPENID_CALLBACK_URL=https://<librechat-aca-url>/api/auth/openid/callback
OPENID_SESSION_SECRET=
OPENID_BUTTON_TEXT=Login with ROMTech Okta

# Auth
ALLOW_REGISTRATION=false
ALLOW_SOCIAL_LOGIN=true

# Show only the LiteLLM endpoint in the model picker
ENDPOINTS=custom

# Point LibreChat at the local config file (use your actual Windows path)
CONFIG_PATH=C:\Users\<you>\Documents\Romtech\ChatGptForEmployees\config\librechat.yaml

# Validation scripts
LIBRECHAT_URL=http://localhost:3080
LIBRECHAT_TEST_USER_EMAIL=
LIBRECHAT_TEST_USER_PASSWORD=
```

> **Okta note:** The full Okta SSO login flow (redirect → Okta → callback) requires
> the application to be registered in Okta and LibreChat to be reachable via HTTPS.
> Both conditions require an ACA deployment — this cannot be tested on localhost.
> Locally you can verify the OIDC redirect endpoint exists (`/api/auth/openid` returns a
> redirect, not 404), which is what `validate_librechat_okta.py` checks automatically.

> **.gitignore coverage:** `scripts\.env` is listed in `.gitignore` (pattern `*.env`) and will
> never appear in `git status`. Do not override `.gitignore` or rename the file to bypass this.
> Also covered: `LibreChat\.env` (inside the `LibreChat/` subtree, which is itself ignored).

---

## Step 7 — Create LiteLLM scripts/.env

Copy the LiteLLM template alongside the same file:

```powershell
Copy-Item config\litellm.env.template scripts\.env.litellm
```

Open `scripts\.env.litellm` and fill in:

```dotenv
LITELLM_MASTER_KEY=<generated in Step 5>
AZURE_OPENAI_API_KEY=<same key as above>
PORT=4000
LITELLM_ENV=local
```

---

## Step 8 — Update config/librechat.yaml for local dev

Open [config/librechat.yaml](config/librechat.yaml). The `baseURL` currently contains the ACA placeholder:

```yaml
baseURL: "http://localhost:4000/v1"
```

If it still says `<LITELLM_ACA_URL>`, replace it with the local LiteLLM URL:

```yaml
baseURL: "http://localhost:4000/v1"
```

> **Do not commit this change.** It is a local-only override of the ACA deployment config.
> Use `git restore config\librechat.yaml` to undo before pushing.

---

## Step 9 — Install Python dependencies

```powershell
pip install -r scripts\requirements.txt
```

---

## Step 10 — Start LiteLLM locally

Install LiteLLM (once):

```powershell
pip install litellm[proxy]
```

Start the proxy (Terminal 1 — keep running):

```powershell
$env:AZURE_OPENAI_API_KEY="<your key>"
$env:LITELLM_MASTER_KEY="<generated in Step 5>"
litellm --config config\litellm_routing_config.yaml --port 4000
```

Verify it is healthy:

```powershell
Invoke-RestMethod http://localhost:4000/health/liveliness
```

Expected: `{"status":"alive"}` or similar 200 response.

---

## Step 11 — Start LibreChat

Copy `scripts\.env` into LibreChat (LibreChat reads from its own `.env`):

```powershell
Copy-Item scripts\.env LibreChat\.env
```

**Terminal 2** — API server (keep running):

```powershell
cd LibreChat
npm run backend
```

**Terminal 3** — React dev server (keep running):

```powershell
cd LibreChat
npm run frontend
```

Open **http://localhost:3080** — you should see the LibreChat login page.

> Re-run `Copy-Item scripts\.env LibreChat\.env` any time you change `scripts\.env`.

---

## Step 12 — Create a test user

Registration is disabled (`ALLOW_REGISTRATION=false`), so create one account via the CLI:

```powershell
cd LibreChat
npm run create-user
cd ..
```

Follow the prompts, then add the credentials to `scripts\.env`:

```dotenv
LIBRECHAT_TEST_USER_EMAIL=yourtest@example.com
LIBRECHAT_TEST_USER_PASSWORD=yourpassword
```

Re-copy to LibreChat:

```powershell
Copy-Item scripts\.env LibreChat\.env
```

---

## Step 13 — Verify the system prompt (PBI 9575)

> **Sign-off gate:** The system prompt in `config\librechat.yaml` is marked DRAFT.
> It must not be deployed to any user-facing environment until Legal, HR, and Compliance
> have approved it and that approval is documented in the merge PR.

With LibreChat running (Step 11), open a new conversation at **http://localhost:3080** and verify:

1. The assistant identifies itself as **ROMTech AI** in its first response.
2. Ask "What are you?" — it should describe its scope (drafting, summarizing, analysis, research, translation).
3. Ask "I have a question about my benefits" — it should route to HR, not answer the question.
4. Ask "I think I clicked a phishing link" — it should direct to IT Security immediately.
5. Ask "Can you review this contract?" — it should decline legal advice and refer to the Legal team.
6. The system prompt text is **not visible** anywhere in the LibreChat UI (no system prompt field in the chat input area).

No regression checks:
- Send a normal chat message and confirm a streamed response arrives.
- Confirm the model picker still shows only **ROMTech AI Standard** and **ROMTech AI Fast**.

---

## Step 14 — Run the validation scripts

Run these in dependency order. Each script prints PASSED / FAILED per test.

| Order | Script | What it tests |
|-------|--------|---------------|
| 1 | `python scripts\validate_azure_openai.py` | Azure OpenAI endpoint is reachable and returns valid completions |
| 2 | `python scripts\validate_litellm.py` | LiteLLM proxy is alive and enforces authentication |
| 3 | `python scripts\validate_litellm_routing.py` | LiteLLM routes to correct Azure OpenAI models and streaming works |
| 4 | `python scripts\validate_litellm_allowlist.py` | Friendly model names work; raw Azure deployment names are blocked |
| 5 | `python scripts\validate_litellm_rate_limits.py` | RPM limits are enforced and return 429 (requires LiteLLM DB) |
| 6 | `python scripts\validate_litellm_usage.py` | Token usage appears in spend logs (requires LiteLLM DB) |
| 7 | `python scripts\validate_librechat.py` | LibreChat health endpoint returns 200 and UI is reachable |
| 8 | `python scripts\validate_librechat_litellm.py` | LibreChat routes chat through LiteLLM; streaming works end-to-end |
| 9 | `python scripts\validate_librechat_persistence.py --create` | Sends a test message and saves the conversation ID |
| — | *(restart LibreChat — Ctrl+C both terminals, re-run Step 11)* | |
| 10 | `python scripts\validate_librechat_persistence.py --verify` | Confirms the conversation survived the restart |
| 11 | `python scripts\validate_librechat_features.py` | Feature flags match governance spec; file upload accepts/rejects correctly |
| 12 | `python scripts\validate_librechat_okta.py` | OIDC redirect endpoint exists and points to Okta (partial — full flow needs ACA) |

Expected for all automated tests: **0 FAILED**.

> Scripts 5 and 6 require LiteLLM's PostgreSQL `DATABASE_URL` to be set. Without a local
> Postgres instance, spend-log assertions will fail — skip or set `DATABASE_URL` to a local
> Postgres connection string if you have one running.

---

## Acceptance criteria checklist

**Stack health**
- [ ] `npm ci` completes in `LibreChat\` without errors
- [ ] MongoDB service is running (`Get-Service MongoDB` → Running)
- [ ] `scripts\.env` has no empty or placeholder values for JWT_SECRET, JWT_REFRESH_SECRET, CREDS_KEY, CREDS_IV, LITELLM_MASTER_KEY, LITELLM_URL, LITELLM_VIRTUAL_KEY
- [ ] `ALLOW_REGISTRATION=false` and `ALLOW_SOCIAL_LOGIN=true` in `scripts\.env`
- [ ] `config\librechat.yaml` has no `<LITELLM_ACA_URL>` placeholder
- [ ] LiteLLM responds at `http://localhost:4000/health/liveliness`
- [ ] LibreChat loads at `http://localhost:3080` without console errors
- [ ] Model picker shows only **ROMTech AI Standard** and **ROMTech AI Fast**

**Validation scripts**
- [ ] `python scripts\validate_librechat.py` — 0 FAILED
- [ ] `python scripts\validate_librechat_litellm.py` — 0 FAILED
- [ ] `python scripts\validate_librechat_persistence.py` (create → restart → verify) — 0 FAILED
- [ ] `python scripts\validate_librechat_features.py` — 0 FAILED
- [ ] File attachment works; disallowed file type shows a visible error

**System prompt — PBI 9575**
- [ ] New conversation: assistant identifies itself as ROMTech AI
- [ ] HR routing: assistant refers HR questions to the HR portal, does not answer them
- [ ] Security routing: assistant directs security incident reports to IT Security
- [ ] Legal routing: assistant declines legal advice and refers to the Legal team
- [ ] System prompt text is not visible in the LibreChat UI
- [ ] Chat and streaming work normally after adding the system prompt
- [ ] **(ACA gate)** Legal, HR, and Compliance sign-off documented in the merge PR before deploying to any user-facing environment

**Security**
- [ ] `scripts\.env` does not appear in `git status`

---

## Troubleshooting

**Model picker shows OpenAI / Anthropic endpoints**
→ Set `ENDPOINTS=custom` in `scripts\.env` and re-copy to `LibreChat\.env`.

**LibreChat startup error: CONFIG_PATH not found**
→ `CONFIG_PATH` must be an absolute Windows path. Check for typos or forward slashes.

**Validation script: connection refused for LibreChat**
→ Both `npm run backend` and `npm run frontend` must be running inside `LibreChat\`.

**Validation script: LITELLM_URL missing**
→ Confirm `LITELLM_URL` (not `LITELLM_BASE_URL`) is set in `scripts\.env`.

**CREDS_KEY / CREDS_IV wrong length**
→ `CREDS_KEY` = 64 hex chars (32 bytes). `CREDS_IV` = 32 hex chars (16 bytes). Regenerate.

**LiteLLM model list check fails**
→ Model aliases in `config\litellm_routing_config.yaml` must exactly match
`"ROMTech AI Standard"` and `"ROMTech AI Fast"` — case-sensitive.

**System prompt not taking effect (assistant does not identify as ROMTech AI)**
→ `config\librechat.yaml` must be reloaded. Restart both LibreChat terminals (`Ctrl+C` in each, then re-run Steps 10 and 11). If `CONFIG_PATH` is set, confirm it points to the updated file.

**Model picker shows raw model names instead of ROMTech AI Standard / Fast**
→ Confirm `modelSpecs` is present in `config\librechat.yaml` and `CONFIG_PATH` in `scripts\.env` points to that file. Re-copy `scripts\.env` to `LibreChat\.env` and restart.

**scripts\.env appears in git status**
→ This should never happen — it is covered by the `*.env` pattern in `.gitignore`.
If it does, run `git rm --cached scripts\.env` immediately and do not commit.
