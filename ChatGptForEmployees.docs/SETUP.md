# Local Setup Guide — PBI 9561
## Install and Run LibreChat Locally, Wired to LiteLLM

> **All commands run from the repo root** (`ChatGptForEmployees\`)

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Node.js | 18 or 20 LTS | https://nodejs.org |
| Git | any | already have it |
| Python | 3.10+ | for validation scripts |
| MongoDB Community Server | 7.x | see Step 3 |
| openssl or PowerShell | — | for secret generation |

---

## Step 1 — Get the LiteLLM handoff from Dev 1 (PBI-01-BE)

You need two values before doing anything else:

- **LITELLM_URL** — local LiteLLM base URL (e.g. `http://localhost:4000`)
- **LITELLM_VIRTUAL_KEY** — scoped virtual key for this environment

---

## Step 2 — Install LibreChat dependencies

LibreChat is already cloned at `LibreChat\`. Install its Node dependencies:

```powershell
cd LibreChat
npm ci
cd ..
```

`npm ci` should complete without errors.

---

## Step 3 — Install and start MongoDB Community Server

1. Download MongoDB Community Server 7.x from  
   https://www.mongodb.com/try/download/community  
   Install using the MSI wizard — choose **Install MongoD as a Service**.

2. Verify it is running:

```powershell
Get-Service MongoDB
# Expected: Running
```

If not running:

```powershell
Start-Service MongoDB
```

---

## Step 4 — Fill in scripts/.env

Open `scripts\.env` in your editor. It was created from `config\librechat_env.template`.  
Add or fill in the following values for local development:

### 4a — Generate secrets (run each command once, paste the output)

```powershell
# JWT_SECRET, JWT_REFRESH_SECRET, CREDS_KEY  →  64 hex chars each
-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })

# CREDS_IV  →  32 hex chars
-join ((1..16) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })
```

Or with openssl (Git Bash / WSL):

```bash
openssl rand -hex 32   # JWT_SECRET, JWT_REFRESH_SECRET, CREDS_KEY
openssl rand -hex 16   # CREDS_IV
```

### 4b — Values to set in scripts/.env

```dotenv
# Secrets — generate with the commands above
JWT_SECRET=<generated>
JWT_REFRESH_SECRET=<generated>
CREDS_KEY=<generated>
CREDS_IV=<generated>

# MongoDB
MONGO_URI=mongodb://localhost:27017/LibreChat

# LiteLLM — from Dev 1 handoff
LITELLM_URL=<local LiteLLM URL, e.g. http://localhost:4000>
LITELLM_VIRTUAL_KEY=<virtual key from Dev 1>

# LibreChat local URL — used by validation scripts
LIBRECHAT_URL=http://localhost:3080

# Auth
ALLOW_REGISTRATION=false
ALLOW_SOCIAL_LOGIN=true

# Show only the LiteLLM endpoint in the model picker
ENDPOINTS=custom

# Point LibreChat at the local config file
# Use the absolute path on your machine:
CONFIG_PATH=C:\Users\you\Documents\Romtech\ChatGptForEmployees\config\librechat.yaml

# Node
HOST=localhost
PORT=3080
```

---

## Step 5 — Replace the placeholder in config/librechat.yaml

Open `config\librechat.yaml`. Find this line:

```yaml
baseURL: "https://<LITELLM_ACA_URL>/v1"
```

Replace `<LITELLM_ACA_URL>` with your local LiteLLM URL, for example:

```yaml
baseURL: "http://localhost:4000/v1"
```

> **Do not commit this change.** It is a local-only override of the ACA deployment config.

---

## Step 6 — Copy scripts/.env into LibreChat

LibreChat reads its environment from its own `.env` file:

```powershell
Copy-Item scripts\.env LibreChat\.env
```

> Repeat this any time you change `scripts\.env`.

---

## Step 7 — Start LibreChat

**Terminal 1** (API server, stays running):

```powershell
cd LibreChat
npm run backend
```

**Terminal 2** (React dev server, stays running):

```powershell
cd LibreChat
npm run frontend
```

Open **http://localhost:3080** — you should see the LibreChat login page.

---

## Step 8 — Create a test user

Registration is disabled, so create one account via the CLI:

```powershell
cd LibreChat
npm run create-user
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

## Step 9 — Run the validation scripts

Install Python dependencies first (once):

```powershell
pip install -r scripts\requirements.txt
```

### 9a — Health check

```powershell
python scripts\validate_librechat.py
```

Expected: all tests pass, 0 FAILED.

### 9b — LiteLLM routing and streaming

```powershell
python scripts\validate_librechat_litellm.py
```

Expected: all tests pass, 0 FAILED.

### 9c — Persistence (full restart test)

```powershell
# Phase 1 — send a message
python scripts\validate_librechat_persistence.py --create

# Restart LibreChat: Ctrl+C both terminals, then re-run Steps 7 backend + frontend

# Phase 2 — verify the conversation survived
python scripts\validate_librechat_persistence.py --verify
```

---

## Acceptance criteria checklist

- [ ] `npm ci` completes in `LibreChat\` without errors
- [ ] MongoDB service is running
- [ ] `scripts\.env` has no empty or placeholder values for JWT_SECRET, JWT_REFRESH_SECRET, CREDS_KEY, CREDS_IV, LITELLM_URL, LITELLM_VIRTUAL_KEY
- [ ] `ALLOW_REGISTRATION=false` in `scripts\.env`
- [ ] `ALLOW_SOCIAL_LOGIN=true` in `scripts\.env`
- [ ] `config\librechat.yaml` has no `<LITELLM_ACA_URL>` placeholder
- [ ] LibreChat loads at http://localhost:3080 without console errors
- [ ] `python scripts\validate_librechat.py` — 0 FAILED
- [ ] `python scripts\validate_librechat_litellm.py` — 0 FAILED
- [ ] `python scripts\validate_librechat_persistence.py` (create → restart → verify) — 0 FAILED
- [ ] Model picker shows only **ROMTech AI Standard** and **ROMTech AI Fast**
- [ ] File can be attached to a message and content is accessible to the model
- [ ] Uploading a disallowed file type shows a visible error
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
→ Model aliases in LiteLLM config must exactly match `"ROMTech AI Standard"` and `"ROMTech AI Fast"` — case-sensitive.
