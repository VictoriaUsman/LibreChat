# Local Setup Guide — PBI 9561
## Install and Run LibreChat Locally, Wired to LiteLLM

> **All commands in this guide are run from the `frontend/` directory**  
> unless stated otherwise.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Node.js | 18 or 20 LTS | https://nodejs.org |
| Git | any | already have it |
| Python | 3.10+ | for validation scripts |
| MongoDB Community Server | 7.x | see step 3 |
| openssl or PowerShell | — | for secret generation |

---

## Step 1 — Get the LiteLLM handoff from Dev 1 (PBI-01-BE)

Before doing anything else, obtain:

- **LITELLM_BASE_URL** — the local LiteLLM URL (e.g. `http://localhost:4000`)
- **LITELLM_VIRTUAL_KEY** — the scoped virtual key for this environment

You cannot complete the setup without these two values.

---

## Step 2 — Clone LibreChat

From inside the `frontend/` directory:

```powershell
git clone https://github.com/danny-avila/LibreChat.git LibreChat
cd LibreChat
npm ci
```

`npm ci` should complete without errors.

---

## Step 3 — Install and start MongoDB Community Server

1. Download MongoDB Community Server 7.x from  
   https://www.mongodb.com/try/download/community  
   Install using the MSI wizard — choose "Install MongoD as a Service".

2. Verify the service is running:

```powershell
Get-Service MongoDB
# Status should be: Running
```

If it is not running:

```powershell
Start-Service MongoDB
```

---

## Step 4 — Create your scripts/.env file

From the `frontend/` directory, copy the template and fill it in:

```powershell
Copy-Item frontend\config\librechat_env.template frontend\scripts\.env
```

Open `scripts/.env` in an editor and replace every `<…>` placeholder:

### Generate secrets (PowerShell — run once each)

```powershell
# JWT_SECRET, JWT_REFRESH_SECRET, CREDS_KEY  (64-char hex)
-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })

# CREDS_IV  (32-char hex)
-join ((1..16) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })
```

Or with openssl (Git Bash / WSL):

```bash
openssl rand -hex 32   # for JWT_SECRET, JWT_REFRESH_SECRET, CREDS_KEY
openssl rand -hex 16   # for CREDS_IV
```

### CONFIG_PATH — absolute path to config/librechat.yaml

Set `CONFIG_PATH` to the full absolute path of `frontend\config\librechat.yaml`.
Example (adjust to your actual path):

```
CONFIG_PATH=C:\Users\you\Documents\Romtech\ChatGptForEmployees\frontend\config\librechat.yaml
```

---

## Step 5 — Copy the .env into the LibreChat repo

LibreChat reads its `.env` from its own root directory.  
Copy `scripts/.env` there (run from `frontend/`):

```powershell
Copy-Item frontend\scripts\.env LibreChat\.env
```

> After any change to `scripts/.env`, repeat this copy.

---

## Step 6 — Start LibreChat

From the `frontend/` directory (terminal 1):

```powershell
cd LibreChat
npm run backend     # starts the API server on :3080
```

In a second terminal (also from `frontend/`):

```powershell
cd LibreChat
npm run frontend    # starts the React dev server (proxies to :3080)
```

Open **http://localhost:3080** — you should see the LibreChat login page.

---

## Step 7 — Create a test user (required for validation scripts)

Since `ALLOW_REGISTRATION=false`, use the LibreChat CLI to create one account:

```powershell
cd LibreChat
npm run create-user
```

Follow the prompts.  Then add those credentials to `scripts/.env`:

```
LIBRECHAT_TEST_USER_EMAIL=yourtest@example.com
LIBRECHAT_TEST_USER_PASSWORD=yourpassword
```

And re-copy to the LibreChat repo:

```powershell
Copy-Item Frontend\scripts\.env LibreChat\.env
```

---

## Step 8 — Run the validation scripts

Run all three from the `frontend/` directory.

### 8a. Structural + health check

```powershell
python scripts\validate_librechat.py
```

Expected: `RESULT: All checks passed  (0 failures)`

### 8b. LiteLLM routing check

```powershell
python scripts\validate_librechat_litellm.py
```

Expected: `RESULT: All checks passed  (0 failures)`

### 8c. Persistence check — full restart test

```powershell
# Phase 1: send a message and save the conversation ID
python scripts\validate_librechat_persistence.py --create

# Stop LibreChat (Ctrl+C in both terminal windows), then restart:
#   cd LibreChat
#   npm run backend
#   npm run frontend   (second terminal)

# Phase 2: verify the conversation survived
python scripts\validate_librechat_persistence.py --verify
```

Or skip the restart (tests storage only):

```powershell
python scripts\validate_librechat_persistence.py --auto
```

---

## What the configuration files do

| File | Purpose |
|------|---------|
| `config/librechat.yaml` | Defines the custom LiteLLM endpoint and file upload rules. Env vars like `${LITELLM_VIRTUAL_KEY}` are substituted at runtime. |
| `config/librechat_env.template` | Template for all required env vars. Copy to `scripts/.env` and fill in. |
| `scripts/.env` | Your filled-in secrets and config. **Gitignored — never commit.** |
| `scripts/validate_librechat.py` | Checks config, secrets, and service health. |
| `scripts/validate_librechat_litellm.py` | Sends a live message through LibreChat → LiteLLM and checks the response. |
| `scripts/validate_librechat_persistence.py` | Creates a conversation, optionally restarts LibreChat, and verifies the conversation survives. |

---

## Acceptance criteria checklist

- [ ] `npm ci` completes in the LibreChat repo without errors
- [ ] MongoDB service is running (`Get-Service MongoDB` shows Running)
- [ ] `scripts/.env` has no `<…>` placeholders — all secrets generated and filled in
- [ ] `ALLOW_REGISTRATION=false` in `scripts/.env`
- [ ] `ALLOW_SOCIAL_LOGIN=true` in `scripts/.env`
- [ ] `config/librechat.yaml` has no `<…>` placeholders
- [ ] LibreChat loads at http://localhost:3080 without console errors
- [ ] `python scripts\validate_librechat.py` → 0 failures
- [ ] `python scripts\validate_librechat_litellm.py` → 0 failures
- [ ] `python scripts\validate_librechat_persistence.py --create` then restart then `--verify` → 0 failures
- [ ] Model picker shows only **ROMTech AI Standard** and **ROMTech AI Fast**
- [ ] A file can be attached to a message and its content is accessible to the model
- [ ] Uploading a disallowed file type shows a visible error
- [ ] `scripts/.env` is listed in `.gitignore` and does not appear in `git status`

---

## Troubleshooting

**LibreChat shows all OpenAI/Anthropic endpoints in the UI**  
→ Make sure `ENDPOINTS=custom` is set in `.env` and you copied the updated file to `LibreChat\.env`.

**`CONFIG_PATH` not found error on LibreChat startup**  
→ `CONFIG_PATH` must be an absolute Windows path pointing to `frontend\config\librechat.yaml`.  Check for typos.

**Validation script says "connection refused" for LibreChat**  
→ Both `npm run backend` and `npm run frontend` must be running.  The API server is what the scripts hit.

**`CREDS_KEY` / `CREDS_IV` wrong length error**  
→ `CREDS_KEY` must be exactly 64 hex chars (32 bytes).  `CREDS_IV` must be exactly 32 hex chars (16 bytes).  Regenerate using the commands in Step 4.

**LiteLLM model list check fails**  
→ Confirm the model aliases in the LiteLLM config (from PBI-01-BE handoff) exactly match `"ROMTech AI Standard"` and `"ROMTech AI Fast"` — these strings are case-sensitive.
