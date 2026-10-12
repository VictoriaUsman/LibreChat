# PBI-08-BE evidence (status 2026-10-12)

**PBI-08 is OPEN.** Implementation exists and a tool-backed conversation works locally with fixture data. No
deployed-environment acceptance has been run. Nothing is pushed or deployed; no agent, DB record or permission
grant exists outside the throwaway local stack.

## Revisions

| Repo | Branch | Commits (oldest first) |
|---|---|---|
| Fork `Fork/ChatGptForEmployeesLibreChatFork` (base `4e8997167`) | `pbi-08/cxone-agent-provision` | `c3566901d`, `5fec441c4`, `83f82321b`, `d92aa1297`, `68bde51dd`, `015d6241e` (head) |
| Config/infra (worktree `ChatGptForEmployees.worktrees/pbi-08`, base `dev` `b753ae4`) | `pbi-08/cxone-config` | `b71fae6`, `25cfc75`, `99d2136`, `54db73d`, `9c177ed` (head) |
| MCP contract | 1.1.0 from pbi-07, content hash `b641cd4adaee6c9bb98b4db229c2cc182ff143c184b6c9faa6170db3abdb48e8` | MCP server used locally: pbi-07 worktree, fixture backend (not pinned to a commit) |

The user's uncommitted PBI-07 prompt edits in the main `ChatGptForEmployees` checkout are not part of PBI-08.

## What was built

- **Provisioning** (fork `packages/api/src/agents/{provision,contract}.ts`, CLI `config/provision-cxone-agent.js`, `npm run
  provision-cxone-agent`, example manifest `config/cxone-agent.manifest.example.json`): dry-run/apply; contract hash is
  recomputed from the file (lexeme-preserving canonicalizer, verified against the real 1.1.0 hash) and each discovered
  tool's argument schema and description is compared with the contract; instruction-text hash; owner/audience must exist
  before any write; owner granted first; deterministic agent ID; refuses a same-name agent with another ID and ACL entries
  outside the manifest; drift on name, instructions, provider, model, `model_parameters.model`, stray model parameters,
  `maxContextTokens` and tools is corrected in place; read-back verification; on failure this run's grants are revoked
  (replaced roles restored) and a pre-existing agent's full prior fields restored. Compensating rollback, not a
  transaction (Cosmos DB multi-document transactions unverified): a crash between steps can leave partial grants; a rerun
  repairs it and the audience is never granted before the owner.
- **Startup isolation** (fork patch, `PATCHES.md`): a malformed or unset `${CXONE_MCP_URL}` made the schema's URL refinement
  throw and `loadCustomConfig` `process.exit(1)`. Each `mcpServers` entry is now validated alone; an invalid one is
  excluded and logged by name and category only. MCP init failure logs are URL-stripped and bounded. Unrelated invalid
  config still exits.
- **Ephemeral-agent restriction** (fork patch, `PATCHES.md`): servers with `chatMenu: false` are rejected from a request's
  `ephemeralAgent.mcp`; modelSpec-attached servers are unaffected.
- **Config** (`librechat.yaml`): `mcpServers.romtech-cxone` (streamable-http, `chatMenu: false`, session user + conversation
  headers, context secret from env, timeout 30 s > the server's 20 s deadline, `initTimeout` 15 s); agents capabilities
  `file_search`, `artifacts`, **`tools`** (required, see findings); `interface.agents: {use: true, create: false,
  share: false, public: false}` (**changed from `false`**, see findings); `disableBuilder` stays true. The `romtech-cxone`
  modelSpec is NOT committed: `scripts/render_librechat_config.py` renders it with the real agent ID, rejects placeholder
  IDs and validates invariants (64000 caps, builder disabled, capabilities, `interface.agents` shape, server settings).
- **Bicep/pipelines**: optional `cxoneMcpUrl` / secret `cxoneMcpContextSecret` (default empty; `az bicep build` of
  `main.bicep` succeeds; committed `main.json`/`libreChat.json` were already out of sync and not regenerated). dev/test/prod
  pipelines validate and fail fast before upload (also re-validate the processed file) and render the spec when
  `cxoneAgentId` is set. Simulated locally; not run in Azure DevOps.

## Findings that change deployment

1. **Image before config.** On the stock image a bad/unset `CXONE_MCP_URL` exits the app. The isolation patch must be in the
   deployed image before this `librechat.yaml` reaches any environment. The same goes for the ephemeral restriction
   (without it, `chatMenu: false` is only cosmetic and the Standard-chat bypass below is open).
2. **`interface.agents: false` makes the persistent agent unreachable.** It removes the role-level agents USE permission;
   `GET /api/agents/:id` returns 403 for everyone before ACLs are consulted. Config now grants `use` only. This departs
   from the guide's "keep `interface.agents: false`"; the owner should be told. Who can open the agent is still decided by
   its ACLs.
3. **The `tools` capability is required and opens a bypass that the patch closes.** Without `tools` the agent run silently
   drops every MCP tool. With it, a plain Standard chat with a hand-built `ephemeralAgent:{mcp:["romtech-cxone"]}` called
   the CXOne tool for any signed-in user (measured). After the fork patch the same request makes no tool call.
4. **LiteLLM 1.99.0 + tools + `api_version: "2024-10-21"` = 404 locally.** Chat requests that include `tools` for these
   gpt-5.x models are routed to the Azure Responses API (`/openai/responses?api-version=...`), which returned 404 with
   the pinned version; plain chat worked. A local copy with `2025-04-01-preview` fixed it (not committed). The committed
   `litellm_routing_config.yaml` pins `2024-10-21` on all four model entries, so deployed tool calls may fail the same way.
   **Unverified for dev/test/prod; must be checked before CXOne is relied on there.**
5. **Cap precedence (code reading, `initialize.ts` ~466-473):** for the initial agent the spec preset's `maxContextTokens`
   overrides `agent.model_parameters`. Both are 128000, so they agree. Tests prove 128000 survives `initializeAgent`; the
   override itself is untested (the test double replaces parameter extraction).
6. No tenant placeholder exists in LibreChat; no tenant header is sent (the MCP server's single-tenant policy applies).
   `{{LIBRECHAT_BODY_CONVERSATIONID}}` is probably empty on a new conversation's first message (unverified); the server
   then runs the tool uncached, which is safe.
7. A server excluded at config load leaves the agent without its tools and the model is not told. Instructions do not yet
   cover that case.
8. **Fixture data is not labelled strongly enough in answers.** In a local UI conversation the agent said "Yes, I have call
   data for Dec 25, 2025" and reported the same 1,284 figure for every date, noticing the fixture only when asked to compare
   2024 vs 2025. Tool results carry `data_source: "fixture"`; the claim instructions do not require the assistant to say so.
   Irrelevant against the real backend, but fixture mode should be used only for plumbing checks.

## Test results (local)

| Check | Result |
|---|---|
| Fork `provision.spec.ts` | 23 passed |
| Fork `isolate.spec.ts` + `ephemeral.spec.ts` | 7 + 4 passed |
| Fork `api` `loadCustomConfig.spec.js` (includes 3 isolation cases) | 23 passed |
| Fork `initialize.test.ts` + `MCPServersInitializer.test.ts` | 60 passed combined (includes 2 new 128000 cases) |
| Config `test_render_librechat_config.py` | 10 passed |
| eslint / tsc on new and edited fork TypeScript | clean at `015d6241e` |

Not re-run: the rest of the fork suite. Existing specs that need `mongodb-memory-server` (e.g. `load.spec.ts`) could not run on
this machine (binary MD5 check failed; not bypassed).

## Local integration runs (dev machine; NOT deployed-environment results)

Stack: Docker MongoDB 7, LiteLLM 1.99.0 (local config copy with `2025-04-01-preview`) to Azure OpenAI gpt-5.4-mini, the real
pbi-07 MCP server with the **fixture** backend, LibreChat from the fork build. The local contract is the real 1.1.0 with the
fixture server's descriptions (the fixture server appends ` FIXTURE DATA in this scaffold.`; against the real contract the
description check correctly refuses it, and with the suffix stripped verification returns no problems).

| Check | Result |
|---|---|
| Dry run discovers 3 tools through LibreChat's MCP init, plans create, writes nothing | pass |
| Apply: 1 agent; tools `<tool>_mcp_romtech-cxone` x3 + `file_search`; `mcpServerNames [romtech-cxone]`; 128000 | pass |
| ACL: operator owner, group/role viewer; member VIEW true/EDIT false, outsider none (real `checkPermission`) | pass |
| Rerun = `no-change` (1 agent); cap change -> `update` and back | pass |
| Unknown principal refused, nothing written; out-of-band extra grant -> `ACL drift` refused | pass |
| Malformed/empty URL: process starts, server excluded, `invalid_url` logged without the value | pass |
| Unreachable port, garbage response, hanging server: init finishes in 15-25 s with 0 tools, sanitized log, provisioning refuses | pass |
| Context secret absent from all captured logs | pass |
| USER-role account: GET agent 200; create agent 403; edit CXOne agent 403 (browser User-Agent; bare curl is rejected by the app's UA filter) | pass |
| Persistent agent conversation (API and UI): model calls `compare_periods`, answer states interval, timezone, baseline coverage and "business reconciliation pending", no causal claim | pass (fixture data) |
| Standard chat + `ephemeralAgent.mcp:["romtech-cxone"]` | blocked: 0 CallToolRequests after the fork patch |
| Unrelated invalid config key | still exits (observed once, by accident) |

Not covered locally: File Search (RAG API not running), summarization/truncation at 64000 vs 128000 in a long conversation,
resumed conversations, ordinary-user UI behaviour of the builder, readiness endpoint, header values received by the server
from a live conversation, the real (non-fixture) backend, the deployed gateway. The model-drift fix (`015d6241e`) is covered
by unit tests only, not re-run against the local database.

## Open - not performed, not passed

Deployed internal MCP URL and reachability from the LibreChat container; real provisioning and idempotent rerun in an
environment; approved model and group choice; ACL denial for an unapproved user in the deployed environment; picker selects
the persistent agent; runtime 128000 vs Standard/Fast 64000 (new and resumed conversations); File Search on both routes and
cross-user denial; failure injection against a deployed instance; **deployed LiteLLM tool-call behaviour (finding 4)**;
PBI-06 real-header cache evidence; PBI-07 assistant-answer reviews; owner decision on the `interface.agents` change.
Reviewer: none recorded.
