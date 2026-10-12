# PBI-08-BE: LibreChat integration — MCP server, agent and modelSpec

Prepared 2026-10-12 from the user's acceptance criteria. **Implementation guide,
not completion evidence.** No agent, database record, deployment or permission
grant is created by this document.

## Outcome and acceptance

An approved ROMChat user selects a dedicated CXOne entry and starts a conversation
with a server-created agent bound to the internal CXOne MCP server. The agent
builder remains disabled. The CXOne spec has its own 128000-token context cap;
ROMChat Standard and Fast retain 64000. File Search keeps working. An unreachable
or malformed MCP endpoint logs a sanitized error without preventing LibreChat
startup.

The 128000 context cap is separate from PBI-06's 3000-token tool-response budget.
Do not increase a global model limit or disable output guardrails to satisfy it.

## Dependencies and starting point

- Use the PBI-07-integrated MCP implementation and generated contract **1.1.0**,
  not the earlier PBI-06-only 1.0.0 contract. Inspect
  `docs/contracts/cxone-mcp-tools.contract.json`, its Markdown companion and
  changelog on that branch. Verify its snapshot tests at the chosen revision.
  The three tools are `compare_periods`, `drill_down` and `current_state`.
- Full PBI-04/05/06/07 closure is not a prerequisite for configuration work.
  PBI-06 identity/cache evidence and PBI-07 assistant-answer review depend on this
  integration. Keep unsupported live state, unverified completeness and business
  reconciliation limitations visible; do not flip confirmation flags to enable it.
- End-to-end acceptance requires a deployed internal MCP URL, network reachability,
  provisioned credentials, a real agent ID, an approved-user audience and the
  selected model/provider. Do not invent these values or put secrets in the repo.
- Select the approved underlying model through the existing provider route and
  verify that it supports the intended context budget. The agent owns its model
  configuration; the modelSpec selects the agent.

Create isolated feature branches in the repositories actually changed. Preserve
unrelated work. Confirm the deployed image revision before relying on fork-only
behaviour. The local fork inspected for this guide was `4e8997167`; its source is
an implementation lead, not proof that the deployed image contains those changes.

## Repositories and files

Paths below are relative to `C:/Data Engineering/LibreChat` unless stated otherwise.
Do not edit a duplicate config just because it has the same basename.

| Existing file or area | Required work |
|---|---|
| `ChatGptForEmployees/config/librechat.yaml` | Add the MCP registration and dedicated modelSpec; preserve existing caps, builder settings and capabilities. This is the path uploaded by the inspected dev/test/prod pipelines. |
| `ChatGptForEmployees.bicep/libreChat.bicep` | Supply the internal URL and secret references using existing environment-specific infrastructure conventions. Inspect caller modules/parameter files before changing its interface. |
| `ChatGptForEmployees.pipelines/{dev,test,prod}.yml` | Integrate config validation and any environment-specific agent-ID rendering without logging secrets or promoting an unresolved placeholder. Preserve the canonical upload path. |
| `Fork/ChatGptForEmployeesLibreChatFork/packages/api/src/` | Put new backend provisioning/validation logic in TypeScript here, following the fork's AGENTS.md/CLAUDE.md rules. Proposed addition: `agents/provision.ts`. |
| Fork `packages/data-schemas/src/methods/agent.ts` and associated permissions methods | Reuse existing agent persistence/versioning and ACL methods. Do not insert an incomplete MongoDB document directly. |
| Fork `api/server/controllers/agents/` and access-resource middleware | Trace MCP tool authorization and agent access checks; retain their restrictions for conversations and uploads. |
| Fork `packages/api/src/mcp/` and `api/server/services/initializeMCPs.js` | Verify per-server failure isolation, connection limits and identity propagation; fix only demonstrated gaps. |
| Fork `packages/data-provider/src/schemas.ts`, modelSpec handling and agents runtime | Trace `agent_id` selection and context-cap precedence from config through the actual agent run. |
| MCP `config/romchat-cxone-claim-instructions.md` on PBI-07 | Load the versioned reporting instructions into the dedicated agent. |
| Proposed `ROMTechMCP/docs/PBI-08-BE-evidence.md` | Record acceptance results, revisions, contract/config versions, sanitized artifacts and remaining limitations. |

For any CLI wrapper, follow existing fork command conventions. Keep legacy `/api`
JavaScript changes thin; place new backend logic in `packages/api` TypeScript.
Read additional directory instructions before editing those areas.

## 1. Register the MCP server

Add one stable server name, such as `romtech-cxone`, under `mcpServers`. Use explicit
`type: streamable-http` and the internal service URL including its MCP route.
Verify the scheme, DNS, ingress, TLS policy and reachability from the LibreChat
container, not merely from a workstation. If this fork requires an allowlist for
private services, allow only the intended service using its supported settings.

Illustrative shape, **not a deployment-ready configuration**:

```yaml
mcpServers:
  romtech-cxone:
    type: streamable-http
    url: "${CXONE_MCP_URL}"
    headers:
      X-ROMChat-Context-Secret: "${CXONE_MCP_CONTEXT_SECRET}"
```

Add trusted user, conversation and tenant context only after tracing the deployed
fork's actual placeholder/header support. Contract 1.1.0 names
`x-romchat-user-id`, `x-romchat-conversation-id`, `x-romchat-tenant-id` and
`x-romchat-context-secret`. User identity must come from the authenticated session;
conversation identity must change between conversations. A fixed conversation ID
or an unresolved literal placeholder is not acceptable. Do not invent a tenant
placeholder; derive tenant context from a trusted supported mechanism or document
and test the server's configured single-tenant policy.

The context secret establishes trust for cache identity; the MCP contract allows
uncached execution without trusted identity. It is **not** an authorization gate
for CXOne access. Enforce approved-user access in LibreChat's agent/tool ACLs and
the deployment's network/authentication boundary. Do not expose a public MCP
endpoint relying solely on that context header.

Use bounded connection/initialization/request timeouts compatible with the MCP
server's deadline. Choose startup versus on-demand initialization after testing
the local fork. `startup: false` alone does not prove malformed configuration is
safe or guarantee that a required startup error is logged.

## 2. Provision the agent server-side

Implement an operator-only, repeatable provisioning command. It must work while
`interface.agents: false` and `endpoints.agents.disableBuilder: true` remain set;
never temporarily enable the builder or grant ordinary users create/edit access.

Suggested command contract (new code to implement, not an existing CLI):

```text
provision-cxone-agent --manifest <non-secret manifest> --dry-run
provision-cxone-agent --manifest <non-secret manifest> --apply
```

The manifest should identify environment, stable provisioning key, existing
operator/owner identity, approved audience, provider/model, MCP server name,
expected contract version/hash, instruction version/hash and context limit.
Resolve deployment credentials through existing configuration; do not accept
database passwords or shared secrets in command-line arguments or commit them.

Implementation sequence:

1. Validate the manifest and resolve the owner/audience before making changes.
2. Discover the registered server's tools and compare them with the pinned
   contract. Resolve actual LibreChat tool identifiers/namespacing; do not assume
   that bare MCP names are the database tool IDs.
3. Reuse agent creation/update, version and ACL services. Bind only the intended
   server/tools and preserve supported File Search access. Follow MCP tool
   authorization checks; do not bypass them to seed the agent.
4. Create or update the agent identified by the stable provisioning key. Repeated
   runs must not create duplicate agents or widen permissions. Fail on ambiguous
   matches; do not pick the first agent with a matching display name.
5. Persist the dedicated instructions, approved provider/model and effective
   128000 context setting through the supported agent fields. Apply the required
   ACLs atomically where possible; otherwise keep partially provisioned agents
   unavailable until all steps succeed and make retries safe.
6. Read back and verify agent/tool/ACL configuration. Emit only the agent ID,
   version, non-secret fingerprints and changed/no-change result.

Prefer narrowly scoped approved groups/users. Verify both model-picker visibility
and backend authorization. A hidden picker entry alone is not access control:
an unapproved user must not invoke the persistent agent by submitting its ID or
select the same MCP tools through another route.

## 3. Add the modelSpec and verify context precedence

Append a dedicated entry without changing the default model selection or the two
existing presets. Render the actual environment's returned agent ID. Do not assume
environment substitution is supported for arbitrary `agent_id` fields; verify it
or use deterministic deployment rendering and validate the rendered file.

```yaml
# Fragment to append under modelSpecs.list after provisioning:
- name: "romtech-cxone"
  label: "ROMChat CXOne"
  preset:
    endpoint: "agents"
    agent_id: "<actual-provisioned-agent-id>"
    maxContextTokens: 128000
```

Keep `modelSpecs.enforce`/`prioritize` and existing UI settings unless a tested,
minimal change is required to show the spec. Do not enable a broad endpoint menu
or builder as a shortcut. The approved user must reach a persistent-agent
conversation, not a similarly labelled custom-model or ephemeral-agent fallback.

Inspect effective runtime precedence: persistent agent model parameters may
override preset options in some LibreChat versions. Assert 128000 at the actual
agent execution boundary, setting the matching agent parameter if required.
Keep the value on the spec as required by acceptance. Assert Standard and Fast
still resolve to 64000 at the same boundary. Do not count YAML text alone as proof.
Check summarization/truncation under each effective budget without raising shared
defaults or changing the existing summarization policy for other users.

## 4. Instructions, File Search and builder restrictions

Install PBI-07's claim instructions on the dedicated persistent agent and verify
they reach the model. Include timestamps, reporting timezone, missing-data and
unverified-completeness handling, no unsupported causal claims and no inferred
scheduled staffing. Candidate SLA values must not be described as validated.
Adapt any generic "cannot access internal systems" wording only within this
agent's instructions so it accurately describes the permitted read-only tools.

Do not blindly apply the earlier PBI-07 review patch to Standard/Fast prompts:
the user's PBI-08 design is a dedicated agent. Preserve unrelated prompts.

The inspected agents capabilities list contains `file_search` and `artifacts`.
Keep both. An explicit capabilities list replaces defaults; do not replace it
with only MCP-related capabilities. Retain the existing agents upload policy.
Verify agent-level File Search tools/resources as well as endpoint capabilities,
document ownership/ACL checks, upload, indexing and retrieval. Test existing
Standard/Fast document flows and the new agent separately.

## 5. Failure isolation and logging

Trace YAML/schema validation, URL parsing, server registry inspection and network
connection separately. A malformed URL can fail before any socket attempt. Catch
CXOne server-specific failures at the narrowest boundary that permits the rest
of LibreChat to load. Keep unrelated configuration errors visible rather than
catching and ignoring all startup exceptions.

For an unreachable or malformed MCP endpoint:

- LibreChat starts and its readiness check succeeds; Standard/Fast and File Search
  remain usable.
- Log a bounded, sanitized error with server name and failure category. Never
  log secrets, resolved identity headers, credential-bearing URLs or tool bodies.
- CXOne invocation returns a clear unavailable/error result, with no fabricated
  data or silent substitution of a fixture backend.
- Connections/retries are bounded. Recovery after correction/restart is tested.

Test at least unreachable host/port, invalid URL, malformed MCP response and
initialization timeout. Separately test an unset/unresolved endpoint variable.
Distinguish a malformed endpoint in otherwise valid YAML (in scope) from a
syntactically invalid whole YAML document; do not silently reinterpret the latter
as a valid deployment.

## 6. Verification and acceptance evidence

Run focused unit/integration tests with installed project dependencies. Reuse
existing fork tests around `initializeMCPs`, MCP registry/connections, agent ACLs,
modelSpec selection and agents file uploads; add regression cases for this path.
Use fake MCP/provider/database boundaries for ordinary tests, then perform the
authorized deployed integration checks. No automatic tenant calls in unit tests.

| Acceptance criterion | Required proof |
|---|---|
| Internal MCP registration | Rendered config and internal discovery of the three contract-matching tools from the LibreChat runtime. |
| Backend-created, bound agent; builder disabled | Provision/read-back result, idempotent rerun, correct tool binding, UI builder hidden and ordinary-user create/edit denied. |
| Agents modelSpec with real ID | Config validation and picker selection produce a conversation whose actual endpoint/agent ID match the provisioned agent. |
| Dedicated 128000 cap | Both spec value and effective persistent-agent runtime limit. |
| Standard/Fast unchanged at 64000 | Before/after config assertions and runtime limit checks, including new and resumed conversations. |
| Approved-user entry works | Approved account sees/selects it and completes a tool-backed conversation; unapproved account cannot see or directly invoke it. |
| File Search unaffected | Existing capabilities retained; upload/index/retrieve a known test document with an answer supported by its content, on existing routes and CXOne. Cross-user document access remains denied. |
| Bad endpoint does not block startup | Failure-injection tests for URL parsing and connectivity; readiness plus ordinary conversation/File Search succeed; sanitized error logged. |

Also gather PBI-06 real-header identity/cache evidence: same-conversation
compare-to-drill reuse, separate user/conversation isolation, and safe cache
bypass when trusted context is missing. Gather PBI-07 actual assistant-answer
reviews for normal, anomalous, missing-data and "right now" prompts. Record these
under their own PBIs; an integration pass does not certify business metrics.

Record application/MCP/image revisions, contract version/hash, rendered config
fingerprint, agent/instruction versions, environment, UTC run time, test counts,
sanitized expected/actual observations and reviewer. Record deployment checks not
performed as open, not passed. Do not put user documents, credentials or raw CXone
records in evidence.

## 7. Delivery, rollout and rollback

Order: pin contract and target image -> prepare/validate config and provisioning
code -> provision internal endpoint/secrets -> create the restricted agent ->
render its actual ID into config -> deploy to the validation environment -> run
the acceptance matrix -> record owner decision and deploy through the normal
release process. Do not publish a placeholder ID as a working picker option.

Before changing external configuration, produce a concrete diff and dry-run
provisioning plan. Existing user authorization and normal environment access
controls govern execution; this guide does not itself grant deployment access.

Rollback removes/disables the CXOne spec and revokes its agent access while
preserving Standard/Fast, document capabilities and existing conversations/data.
Restore the prior agent version/config if an update failed. Do not delete all
agents, shared MCP configuration or user files as a rollback shortcut.

PBI-08 closes only after its acceptance matrix has actual evidence. Any unavailable
capability or changed criterion needs an explicit owner decision and tracked
follow-up. No approval is implied by this guide.

## Reference notes

Local fork code and the deployed revision take precedence over assumptions based
on current upstream documentation. In particular, confirm identity placeholders,
private-address policy, persistent-agent cap precedence and startup isolation.

- [LibreChat modelSpecs reference](https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/model_specs): agent-based specs and per-preset context settings; the deployed fork's effective behaviour still requires testing.
- [LibreChat MCP server reference](https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/mcp_servers): transport, environment-backed headers and startup options; these options alone do not establish the required failure isolation.
- PBI-07 branch: `docs/contracts/cxone-mcp-tools.md`, `config/romchat-cxone-claim-instructions.md`, `docs/PBI-06-BE-evidence.md`, `docs/PBI-07-BE-evidence.md`.
