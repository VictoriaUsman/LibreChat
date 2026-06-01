# Introduction

This repository contains the Phase 0 proof-of-concept work for the ROMTech Internal AI Chatbot — an internal, general-purpose AI assistant for ROMTech employees built on the following stack:

```
Okta (authentication)
  ↓
LibreChat (chat UI)
  ↓
LiteLLM (gateway — routing, model control, usage tracking, rate limiting)
  ↓
Azure AI Foundry / Azure OpenAI (model layer)
```

The goal of Phase 0 is to prove the core architecture before committing to a full v1 build. This repo holds the planning documents, deployment configuration templates, and validation scripts produced during that effort. It is not a production application — it is the foundation and evidence base for v1 planning.

For full context on scope, goals, and build order see `ROMTech_Internal_AI_Chatbot_Phase_0_POC_Plan.md` and `Erik_recommendation.md`.

# Getting Started

### 1. Installation process

Clone this repository and install the Python dependencies for the validation scripts:

```bash
pip install -r scripts/requirements.txt
```

### 2. Software dependencies

| Dependency | Purpose |
|---|---|
| Python 3.8+ | Required to run all validation scripts |
| `openai >= 1.0.0` | Azure OpenAI endpoint validation |
| `requests >= 2.31.0` | LiteLLM health and routing validation |
| `python-dotenv >= 1.0.0` | Loading `.env` files for local runs |
| Azure CLI (`az`) | Deploying and managing Azure Container Apps |

### 3. Configuration

Each script reads its configuration from a `.env` file in the `scripts/` directory. Templates for all required values are in `config/`:

| Template | Purpose |
|---|---|
| `config/azure_openai.env.template` | Azure OpenAI endpoint, API key, deployment names |
| `config/litellm.env.template` | LiteLLM container URL and master key |

Copy the relevant templates to `scripts/.env` and fill in the values before running any script. Do not commit a filled-in `.env` file — it is gitignored.

### 4. API references

- [Azure OpenAI REST API](https://learn.microsoft.com/en-us/azure/ai-services/openai/reference)
- [LiteLLM documentation](https://docs.litellm.ai)
- [LibreChat documentation](https://docs.librechat.ai)
- [Azure Container Apps documentation](https://learn.microsoft.com/en-us/azure/container-apps/)

# Build and Test

Run the validation scripts in order. Each script depends on the one before it.

**Step 1 — Validate Azure OpenAI endpoint (PBI-01-BE)**
```bash
cd scripts
python validate_azure_openai.py
```
Tests: direct chat completion, streaming, invalid-key 401 — for both model deployments.

**Step 2 — Validate LiteLLM container health (PBI-02-BE)**
```bash
python validate_litellm.py
```
Tests: liveliness, readiness, auth enforcement. Run after deploying `config/litellm_containerapp.yaml`.

**Step 3 — Validate LiteLLM routing and streaming (PBI-03-BE)**
```bash
python validate_litellm_routing.py
```
Tests: routing to both Azure OpenAI deployments, streaming through LiteLLM, invalid-key 401, unknown-model rejection.

**Step 4 — Validate model allowlist and friendly naming (PBI-04-BE)**
```bash
python validate_litellm_allowlist.py
```
Tests: `ROMTech AI Standard` and `ROMTech AI Fast` route correctly; raw deployment names and provider-prefixed names are blocked.

**Step 5 — Validate usage tracking (PBI-05-BE)**
```bash
python validate_litellm_usage.py
```
Checks token usage visibility, per-model and per-key attribution, and cost fields. Outputs findings for `config/usage_tracking_assessment.md.template`.

**Step 6 — Validate rate limiting (PBI-06-BE)**
```bash
python validate_litellm_rate_limits.py
```
Creates a temporary test key with `rpm_limit=1`, confirms a second back-to-back request returns HTTP 429, then deletes the test key.

**Step 7 — Generate department virtual keys (PBI-10-BE)**
```bash
python generate_department_keys.py
```
Reads all `DEPT_<NAME>_BUDGET` entries from `scripts/.env`, creates one scoped virtual key per department with `max_budget` and `budget_duration: monthly`, and writes the generated key values back to `scripts/.env`. Safe to re-run — departments that already have a key are skipped.

To add or remove a department, edit `scripts/.env`:
- Add: `DEPT_<NAME>_BUDGET=<monthly USD limit>` and `DEPT_<NAME>_KEY=`
- Remove: delete the `BUDGET` and `KEY` lines for that department

**Step 8 — Validate department budget enforcement (PBI-10-BE)**
```bash
python validate_department_keys.py
```
Tests that all department keys are accepted, that a key with an exhausted budget returns HTTP 429, and that per-key spend data is visible in `/spend/keys`. Run after `generate_department_keys.py`.

> **Windows setup note:** After any `pip install --upgrade litellm`, re-run the Prisma patch script:
> ```bash
> python scripts/patch_prisma_windows.py
> ```
> This restores a Windows-specific fix that prevents the LiteLLM process from crashing immediately on startup due to a signal propagation issue between Python and the Prisma query engine subprocess.

All scripts exit with code `0` on success and `1` on any failure.

# Contribute

This repository is internal to the ROMTech AI project team. To contribute:

1. Pick up a PBI from the active sprint backlog.
2. Create a feature branch named `pbi-<id>/<short-description>`.
3. Add or update the relevant script in `scripts/` and configuration template in `config/`.
4. Confirm all existing validation scripts still pass before opening a pull request.
5. Update this README if your change adds a new script or configuration step.

For questions about scope or architecture, refer to `ROMTech_Internal_AI_Chatbot_Phase_0_POC_Plan.md` or contact the gateway track lead.

If you want to learn more about creating good readme files then refer the following [guidelines](https://docs.microsoft.com/en-us/azure/devops/repos/git/create-a-readme?view=azure-devops). You can also seek inspiration from the below readme files:
- [ASP.NET Core](https://github.com/aspnet/Home)
- [Visual Studio Code](https://github.com/Microsoft/vscode)
- [Chakra Core](https://github.com/Microsoft/ChakraCore)
