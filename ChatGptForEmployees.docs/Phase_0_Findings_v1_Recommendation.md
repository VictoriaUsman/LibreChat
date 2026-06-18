# Phase 0 Findings and v1 Recommendation
**PBI 9131 — Final Phase 0 Output**

**Validated by:** Technology Solutions
**Validation date:** 2026-05-21
**Status:** Complete

---

## 1. Architecture Topology

### Component Locations

| Component | Platform | Resource Name | Notes |
|---|---|---|---|
| LibreChat | Azure Container Apps | `librechat-nonprod` | Validated locally; ACA deployment pending |
| LiteLLM gateway | Azure Container Apps | `litellm-nonprod` | Validated locally via Docker |
| Conversation storage | MongoDB (local Docker / Cosmos DB in ACA) | `LibreChat` database | Validated locally; ACA uses Cosmos DB with MongoDB API |
| LiteLLM config | Volume-mounted YAML | `litellm_routing_config.yaml` | Validated locally; ACA uses Azure File Share mount |
| Model deployments | Azure OpenAI / AI Foundry | `aiswebsitechatbotdev` | Validated — endpoint confirmed live |
| Authentication | Okta (external) | `romtech.okta.com` | OIDC wiring validated locally; full flow requires ACA + HTTPS |

### Request Flow

```
Browser (Okta-authenticated user)
  |
  v HTTPS (ACA ingress, port 3080)
LibreChat — Azure Container App
  |  reads: /app/librechat.yaml            (config — feature governance, endpoint)
  |  writes: MongoDB (conversation history)
  |
  v HTTP/HTTPS (LITELLM_VIRTUAL_KEY, /v1/chat/completions)
LiteLLM Gateway — Azure Container App
  |  reads: litellm_routing_config.yaml   (model allowlist, routing targets)
  |  enforces: allowlist, rate limits, usage tracking
  |
  v HTTPS (Azure OpenAI API key)
Azure OpenAI / AI Foundry
  |-- Flagship deployment (ROMTech AI Standard --> website-chatbot-gpt-4o-mini)
  |-- Fast deployment    (ROMTech AI Fast     --> website-chatbot-gpt-4o-mini)
```

> Note: Both Phase 0 model slots point to the same deployment for POC purposes.
> v1 should provision two distinct deployments (GPT-4-class and GPT-4o-mini-class).

### Model Configuration Location

Model names, routing targets, and allowlist enforcement are defined in
`litellm_routing_config.yaml` mounted into the LiteLLM container.
Updating this file and restarting the LiteLLM container changes model availability
without a container image redeployment.

---

## 2. Configuration Reference

### LibreChat Container Environment Variables

| Variable | Purpose | Required |
|---|---|---|
| `HOST` | `0.0.0.0` — bind to all interfaces | Yes |
| `PORT` | `3080` — must match ACA targetPort | Yes |
| `MONGO_URI` | MongoDB / Cosmos DB connection string | Yes |
| `JWT_SECRET` | Session signing key (32-byte hex) | Yes |
| `JWT_REFRESH_SECRET` | Session refresh signing key (32-byte hex) | Yes |
| `CREDS_KEY` | Credential encryption key (64 hex chars) | Yes |
| `CREDS_IV` | Credential encryption IV (32 hex chars) | Yes |
| `LITELLM_VIRTUAL_KEY` | Scoped virtual key issued by Dev 1 | Yes (after PBI 9126) |
| `ALLOW_REGISTRATION` | `false` in production — disable open sign-up | Yes |
| `ALLOW_SOCIAL_LOGIN` | `true` — enables the Okta login button | Yes |
| `OPENID_CLIENT_ID` | Okta application client ID | Yes |
| `OPENID_CLIENT_SECRET` | Okta application client secret | Yes |
| `OPENID_ISSUER` | `https://romtech.okta.com/oauth2/default` | Yes |
| `OPENID_CALLBACK_URL` | `/oauth/openid/callback` | Yes |
| `OPENID_SESSION_SECRET` | Cookie signing secret | Yes |
| `OPENID_SCOPE` | `openid profile email` | Yes |
| `OPENID_BUTTON_TEXT` | `Login with ROMTech Okta` | Yes |

**Remove after LiteLLM wiring is confirmed (do not carry into v1):**
- `AZURE_OPENAI_API_KEY` — temporary direct connection used in PBI 9125 only
- `AZURE_OPENAI_ENDPOINT` — same

### librechat.yaml (mounted into container at /app/librechat.yaml)

See `config/librechat.yaml` for the validated local configuration. Key settings:
- LiteLLM gateway endpoint and virtual key reference
- Approved model list (`ROMTech AI Standard`, `ROMTech AI Fast`)
- Feature governance flags (see Section 3)

### LiteLLM Container Environment Variables

| Variable | Purpose |
|---|---|
| `LITELLM_MASTER_KEY` | Master API key — never share with end users |
| `PORT` | `4000` |
| `LITELLM_ENV` | `nonprod` |
| `DATABASE_URL` | PostgreSQL connection string (required for usage tracking and rate limiting) |

Full routing config: see `config/litellm_routing_config.yaml`.

---

## 3. Feature Governance Ledger

Validated during PBI 9130 against LibreChat v0.8.6-rc1.

| Feature | v1 Decision | Config Mechanism | Phase 0 Result |
|---|---|---|---|
| Basic chat | Enable | Default | Validated |
| Streaming responses | Enable | Default | Validated |
| Conversation history | Enable | Default | Validated |
| Model picker | Enable (approved models only) | `modelSelect: true` + LiteLLM allowlist | Validated |
| Endpoint switcher | Disable | `endpointsMenu: false` | Validated |
| Agent Builder | Disable | `agents: false` | Validated — removed from UI |
| Skills | Disable | `skills: false` | Validated — removed from UI |
| Memories | Disable | `memories: false` | Validated — removed from UI |
| Bookmarks | Disable | `bookmarks: false` | Validated — removed from UI |
| Prompts | Disable | `prompts: false` | Validated — removed from UI |
| Parameters panel | Disable | `parameters: false` | Validated — removed from UI |
| Attach Files sidebar button | Disable for v1 | `fileConfig: disabled: true` disables uploads server-side but does NOT remove the sidebar button in v0.8.6-rc1 | Partial — server-side blocked, button still visible. Fix before v1 or accept as cosmetic gap. |
| MCP Settings | Disable for v1 | No interface config key in v0.8.6-rc1 | Not removable via config in this version. Fix before v1 or accept as cosmetic gap. |
| Web search | Disable | Not enabled — no config needed | Validated |
| Image generation | Disable | Not enabled — no config needed | Validated |
| Code interpreter | Disable | Not enabled — no config needed | Validated |
| RAG / document search | Defer to later phase | Not built | Not built — deferred |

---

## 4. Gaps and Risks

| Identified Gap or Risk | Classification | Recommended Action |
|---|---|---|
| LiteLLM usage tracking (token counts, spend by model/user/key) requires PostgreSQL — unavailable without it | Fix before v1 | Provision Azure Database for PostgreSQL (Flexible Server, BAA-eligible region) before v1 launch |
| LiteLLM rate limiting via virtual keys requires PostgreSQL — virtual key creation returns 500 without it | Fix before v1 | Same as above — single PostgreSQL instance covers both usage tracking and rate limiting |
| `azure/<deployment-name>` model names bypass the LiteLLM allowlist when called with the master key | Acceptable for v1 | Mitigated in production: end users hold scoped virtual keys (not the master key), which cannot bypass the allowlist. Master key is admin-only. |
| Invalid LiteLLM API keys return HTTP 400 instead of 401 when no database is configured | Acceptable for v1 | Resolved by provisioning PostgreSQL. Requests are rejected either way — the status code difference is cosmetic. |
| LibreChat "Attach Files" sidebar button remains visible even when file uploads are disabled server-side | Fix before v1 | Investigate whether a newer LibreChat release (v0.8.6 stable or later) adds an interface config key for this button, or accept as a cosmetic gap pending a future config update. |
| LibreChat "MCP Settings" sidebar button has no interface config key in v0.8.6-rc1 | Fix before v1 | Same approach as Attach Files button above. |
| LibreChat v0.8.6-rc1 is a release candidate, not a stable release | Needs stakeholder decision | Pin to the stable release tag when v0.8.6 is released before v1 ACA deployment. Monitor LibreChat changelog. |
| Both Phase 0 model slots point to the same Azure OpenAI deployment | Fix before v1 | Provision a second deployment (GPT-4o-mini-class) and update `litellm_routing_config.yaml` with distinct deployment names for Standard and Fast. |
| Okta OIDC end-to-end flow not validated locally (LibreChat enforces HTTPS for OIDC issuers) | Acceptable for v1 | Expected behavior — HTTPS is automatic in ACA. OIDC env vars, button appearance, and strategy registration were all confirmed working. Full flow validation is part of ACA deployment. |
| ALLOW_REGISTRATION must be set to false before production rollout | Fix before v1 | Add `ALLOW_REGISTRATION=false` to the ACA container environment. If not set, any user with network access can create an account. |
| LiteLLM pricing data is bundled with the package version and may lag Azure agreement pricing | Needs stakeholder decision | Override token prices in `litellm_routing_config.yaml` using `input_cost_per_token` and `output_cost_per_token` per model entry once Azure agreement pricing is confirmed. |
| Conversation data retention policy not yet defined | Needs stakeholder decision | Legal and Compliance review required before v1 launch. Erik's recommendation: 90-day default with user-deletable conversations. |

---

## 5. Stack Verdict

- [x] **Proceed to v1 build after listed fixes.**
  Core functionality validated. The following items from Section 4 must be resolved
  before the v1 deployment date:
  - Provision PostgreSQL for LiteLLM usage tracking and rate limiting
  - Provision two distinct Azure OpenAI deployments (Standard and Fast)
  - Set `ALLOW_REGISTRATION=false` in the ACA container environment
  - Confirm Attach Files and MCP Settings sidebar buttons can be hidden in the stable LibreChat release; if not, accept as cosmetic gaps with a clear timeline for resolution

**Rationale:**
The LiteLLM + LibreChat + Azure OpenAI stack is validated for all core Phase 0 acceptance criteria: streaming chat works end-to-end, the model allowlist is enforced, conversation history persists across restarts, and the OIDC wiring is correct. The two infrastructure gaps (PostgreSQL, second model deployment) are straightforward provisioning tasks, not architectural risks. There are no blockers or unresolved questions about the stack's fit for ROMTech's requirements.

---

## 6. Backlog Handoff Parameters (v1 PBIs)

The following v1 PBIs are derived directly from Phase 0 findings and are ready to
be pulled into Sprint 1 upon leadership sign-off.

| PBI Title | Derived From | Priority | Notes |
|---|---|---|---|
| Provision PostgreSQL for LiteLLM (usage tracking + rate limiting) | PBI-05-BE, PBI-06-BE | High | Single instance covers both. Required before any spend reporting or per-user limits work. |
| Configure per-department LiteLLM virtual keys with budget caps | PBI-06-BE | High | One key per team/department with `max_budget` and `budget_duration`. Requires PostgreSQL. |
| Provision second Azure OpenAI deployment (GPT-4o-mini-class for Fast model) | Phase 0 model config | High | Phase 0 used one deployment for both slots. v1 needs two distinct deployments. |
| Set ALLOW_REGISTRATION=false and validate unauthenticated access is blocked | PBI 9129 | High | Must be done before any user rollout. |
| Complete Okta pilot group rollout and validate full OIDC flow in ACA | PBI 9129 | High | Coordinate with Okta admin. Validate end-to-end with HTTPS in ACA environment. |
| Investigate Attach Files and MCP Settings button removal in stable LibreChat release | PBI 9130 | Medium | Check v0.8.6 stable release notes; if still not configurable, accept or patch. |
| Override Azure OpenAI token prices in litellm_routing_config.yaml | PBI-05-BE | Medium | Match LiteLLM cost estimates to actual ROMTech Azure agreement pricing. |
| Azure Monitor integration for LiteLLM spend log forwarding | PBI-05-BE | Medium | Forward audit logs to Log Analytics for operational dashboard. |
| Legal and Compliance review — conversation retention policy | Erik recommendation | High | Required before v1 launch. Starting point: 90-day default, user-deletable. |
| Production container hardening — pin image versions, review ACA security posture | Deployment | High | Do not run RC or latest tags in production. Pin to stable release tags. |
| SCIM provisioning from Okta to LibreChat | Erik recommendation | Medium | Auto-deprovisioning when employees leave. Not required for pilot launch. |

---

## Approvals

| Role | Name | Sign-off Date |
|---|---|---|
| Dev 1 (Backend) | | |
| Dev 2 (Frontend) | | |
| Project Lead | | |
| Architecture Review | Erik | |
