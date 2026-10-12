# PBI-09-BE: access control — agent and MCP server grants

Prepared 2026-10-12. Implementation and coding instructions, not completion evidence.

## Outcome

Only explicitly approved named users can use CXOne. Ziven must hold both VIEW on
the persistent CXOne agent and the equivalent viewer permission on the
`romtech-cxone` MCP server resource. Either grant alone is insufficient. Enforce
this at the API and tool execution boundaries, not merely in the picker.

Okta is the identity provider. Do not introduce Entra group synchronization or
grant access to a group, public/everyone principal, or an employee-wide role.
Use Ziven's existing authenticated LibreChat user record; do not guess his email,
user ID, or Okta subject, and do not create a duplicate user for provisioning.

## Starting point and dependencies

- Fork: `Fork/ChatGptForEmployeesLibreChatFork`, branch
  `pbi-08/cxone-agent-provision`, inspected head `015d6241e`.
- Config/infra: `ChatGptForEmployees.worktrees/pbi-08`, branch
  `pbi-08/cxone-config`, inspected head `9c177ed`.
- PBI-08 evidence: `docs/PBI-08-BE-evidence.md`. PBI-08 remains open; do not
  convert its local fixture results into deployed acceptance.
- Create isolated PBI-09 branches/worktrees from the applicable PBI-08 heads,
  after checking for newer fixes. Preserve unrelated work. Read each repository's
  `AGENTS.md` and `CLAUDE.md` before editing.
- New backend logic belongs in the fork's `packages/api` TypeScript workspace.
  Shared persistence changes belong in `packages/data-schemas`; keep legacy
  `api` JavaScript limited to route/service wiring and CLI adapters.

PBI-09 implementation and local authorization tests can proceed while PBI-08 is
open. Deployed acceptance needs the persistent agent, a resolvable MCP resource,
approved identities, the patched image, and a functioning provider route.
PBI-08's deployed LiteLLM tool-call compatibility and File Search checks remain
separate outstanding dependencies; report blocked checks explicitly.

Preserve PBI-08's `chatMenu: false`, agents `tools`, `file_search` and `artifacts`
capabilities, `disableBuilder: true`, and
`interface.agents: {use: true, create: false, share: false, public: false}`.
Role-level USE permits entering the feature; it is not either resource grant.
Keep Standard/Fast at 64000 and CXOne at 128000.

## Confirmed implementation gaps

These observations come from the inspected local fork, not upstream assumptions:

1. `packages/api/src/mcp/registry/MCPServersRegistry.ts:getServerConfig` resolves
   YAML/cache configuration before consulting the database repository and caches
   lookup results. A YAML registration is not proof of an ACL-protected database
   resource, and a successful config lookup is not authorization.
2. `packages/api/src/mcp/registry/db/ServerConfigsDB.ts:get` falls back to
   `hasAccessViaAgent` when direct MCP access is absent. This deliberately allows
   agent-only access with `consumeOnly: true`; it conflicts with PBI-09 for CXOne.
3. `api/server/middleware/accessResources/canAccessAgentFromBody.js` checks agent
   access, including an added conversation, but does not implement the required
   conjunction with a named-user MCP grant.
4. Generic resource middleware can bypass ACL checks for management capabilities.
   The CXOne consumption policy must not accidentally inherit that bypass.
5. PBI-08 provisioning accepts group/role audiences and grants only agent ACLs.
   Its local group/role examples are not PBI-09 named-user acceptance.
6. PBI-08's ephemeral-agent filter prevents client selection of a hidden server;
   it does not implement the two-resource permission policy.

Do not globally remove existing agent-inherited MCP access for unrelated servers.
Apply the stricter policy to an explicit, server-controlled CXOne binding.

## 1. Establish the protected resource binding

Create one authoritative mapping between the persistent agent's public ID, its
MongoDB `_id`, the server name `romtech-cxone`, and the MCP resource's MongoDB
`_id`. Use database resource IDs for ACL operations, not display names or tool IDs.
Scope resolution to the application's existing tenant/environment conventions.
Fail closed on missing, duplicate, conflicting, or mismatched bindings.

First inspect `packages/data-schemas/src/methods/mcpServer.ts`, the MCP schema,
registry initialization, and YAML reconciliation to determine whether this YAML
server already has a persistent resource. Resolve it through supported methods.
If it does not, implement an idempotent resource-registration/reconciliation
operation through the shared model layer. Record this design decision in evidence.

Requirements for the chosen design:

- There is a real, stable MCP resource to which a viewer ACL is attached.
- The binding survives restart, config reload, and server reinitialization.
- No duplicate database server shadows the YAML server or changes transport
  precedence. Do not rely on the existing database-only fallback for YAML access.
- Keep URLs/headers/credentials under existing configuration management. Do not
  copy resolved secrets into a new ACL manifest, logs, or unnecessary DB fields.
- Missing or unavailable MCP configuration does not fall back to an unprotected
  server with the same name. Standard/File Search remain usable.

## 2. Implement the two-grant policy in TypeScript

Suggested module: `packages/api/src/agents/access.ts`, with focused tests.
Adapt the name to existing modules if needed; avoid a second competing ACL system.
Reuse resource types, permission bits, role IDs, database methods and error types.

For protected CXOne consumption, the decision is:

```text
authenticated user from the session
AND direct named-user VIEW on the bound agent resource
AND direct named-user VIEW on the bound MCP resource
```

Use `PrincipalType.USER`, `ResourceType.AGENT`, `ResourceType.MCPSERVER`,
`PermissionBits.VIEW`, `AccessRoleIds.AGENT_VIEWER`, and
`AccessRoleIds.MCPSERVER_VIEWER` from the existing libraries. Confirm role-to-bit
mapping in `packages/data-schemas/src/methods/accessRole.ts`.

Existing generic permission helpers expand role/group/public principals. Either
add a supported direct-user query or invoke the underlying permission method
with only the authenticated user's principal. An agent-derived MCP permission,
role-level USE, ownership of a conversation, cached server config, or membership
in a broad role must not substitute for either explicit resource grant.

Keep administrative management authority separate from consumption. An operator
may manage grants through existing administrative authorization, but must have
explicit resource permissions to consume CXOne. Existing named owner ACLs can
satisfy VIEW through their permission bits; Ziven receives viewer roles, not
owner/editor permissions. Never make him an administrator to pass the test.

Derive identity from `req.user`/the authenticated server context, never request
headers, tool arguments, a submitted user ID, or the agent author's identity.
Resolve the effective agent after modelSpec processing and conversation loading;
do not trust only the raw body `agent_id`.

## 3. Wire all consumption paths

Trace these existing locations before making narrowly scoped changes:

| Area | Required work |
|---|---|
| `api/server/routes/agents/chat.js`, `middleware/accessResources/canAccessAgentFromBody.js` | Require both grants for the effective protected agent before streaming/model execution. Preserve existing authentication and agent checks. |
| `packages/api/src/agents/load.ts`, `added.ts`, `initialize.ts` | Cover resolved modelSpecs, resumed conversations, added agents and reachable handoff paths; do not authorize from client-supplied selection alone. |
| `api/server/routes/agents/openai.js`, `responses.js`, `tools.js` | Trace alternate chat/response/direct-tool APIs and apply the same protected-resource policy wherever CXOne can be invoked. |
| `packages/api/src/mcp/MCPManager.ts:callTool` and the tool adapter that invokes it | Recheck both grants immediately before dispatch using the caller and trusted binding, including reused connections and cached tool definitions. |
| `mcp/registry/MCPServersRegistry.ts`, `registry/db/ServerConfigsDB.ts` | Ensure YAML precedence, cached config and agent-inherited access cannot bypass the CXOne guard. Keep unrelated server semantics intact. |
| `api/server/services/PermissionService.js`, `packages/data-schemas/src/methods/aclEntry.ts` | Reuse grant/revoke operations and implement any narrowly scoped persistence query in the shared layer. |

For direct CXOne tool calls without a selected agent, resolve the configured
protected agent from the trusted binding and require both grants, or reject the
unsupported route clearly. Do not permit an MCP-only user through this route.
Preserve the PBI-08 rejection of request-supplied CXOne ephemeral tools even for
users who otherwise have grants, unless a separately agreed design changes it.

Authorize before returning cached CXOne results too. A conversation cache or an
existing connection is never a durable access token. Background app-level tool
discovery may continue without impersonating a human; distinguish discovery
from user-initiated tool execution explicitly.

## 4. Return clear denials

Before streaming starts, return HTTP 403 with a stable code such as
`CXONE_ACCESS_DENIED` and a message such as:

> You do not have access to CXOne reporting. Ask an administrator to grant access
> to both the CXOne agent and its MCP server.

Use the application's error envelope and localization conventions. A missing
grant must not become a generic 500, an empty tool list followed by an invented
answer, or a successful response containing an invisible error. If revocation
is detected after SSE headers are sent, use the established stream error event,
stop the protected operation, and show the same understandable denial in the UI.

Preserve normal 401 behavior for unauthenticated requests. A database/config
failure must fail closed with a sanitized operational error; do not claim that a
permission lookup succeeded. Logs may carry a bounded reason code and existing
correlation ID, but no secrets, tool bodies, or unnecessary identity details.

## 5. Provision and revoke named-user grants

Extend the PBI-08 TypeScript provisioning workflow or add a focused companion
module/CLI using existing command conventions. Document the actual command after
implementation; the following is a proposed interface, not an existing command:

```text
cxone-access --manifest <non-secret-file> --dry-run
cxone-access --manifest <non-secret-file> --apply
cxone-access --manifest <non-secret-file> --revoke --dry-run
cxone-access --manifest <non-secret-file> --revoke --apply
```

The manifest identifies the environment, exact resource binding, operator and
approved existing user IDs. Keep real identity manifests outside source control;
commit a placeholder example only. Resolve Ziven's verified local account and
show an unambiguous reviewable target before writes. Reject absent/ambiguous
users and all non-user audience principals before any mutation.

For each approved user, grant exactly agent viewer and MCP viewer. Read back
both grants and verify their effective direct-user VIEW permissions. An
idempotent rerun creates no duplicate resources/ACLs and does not widen access.
Emit a sanitized changed/no-change result covering both resources.

Update the CXOne PBI-08 provisioner and examples so later reruns cannot restore
group/role audiences or disagree with the new access manifest. Inventory existing
ACLs on both resources. Unexpected public/group/role/other-user grants must be
reported as drift; removal needs an explicit, reviewable reconciliation plan.
Do not revoke unrelated resource permissions or silently expand the approved list.

Use transactions only where verified supported. Otherwise retain prior ACL
snapshots and compensate on failure: restore replaced roles, revoke only grants
introduced by this run, and report rollback failures. A partial grant is unusable
because runtime requires both. Test failures between writes and retries.

Support revoking either resource grant independently for acceptance testing and
revoking both as the normal offboarding operation. Revocation must take effect
without deployment, restart, logout or a new conversation.

## 6. Revocation semantics

After a revoke is acknowledged, the next protected request and every subsequent
tool dispatch must evaluate current permissions and be denied if either grant
is absent. Prefer fresh direct-user ACL checks for this small audience rather
than caching positive authorization decisions. If existing authorization caches
remain, implement and test invalidation across every replica; local-only cache
eviction or a long TTL is insufficient.

Test the same session and conversation with warmed config/tool/connection caches.
Recheck before serving a cached tool response. For a tool already dispatched
before revocation, document the race boundary: the remote request cannot be
unsent. Revalidate before releasing its result and prevent subsequent calls;
cancel an in-flight operation where the existing runtime supports cancellation.
Do not promise removal of previously delivered chat history as part of revocation.

## 7. Verification matrix

Use ordinary USER-role accounts for the four grant states, not administrator
accounts that might bypass generic middleware. Test the API directly and assert
the number of actual MCP tool calls, not only picker visibility.

| Agent direct VIEW | MCP direct VIEW | Expected CXOne use |
|---|---|---|
| No | No | Clear 403; no provider/tool execution for the denied request |
| Yes | No | Clear 403; no CXOne call, including agent-inherited server fallback |
| No | Yes | Clear 403; direct MCP/tool routes cannot bypass the agent requirement |
| Yes | Yes | Tool-backed conversation succeeds; neither grant confers create/edit/share |

Required additional checks:

- Ziven's verified account has both viewer grants on the exact bound resources.
- Group/public/employee-role-only ACLs do not satisfy protected consumption;
  the provisioning command refuses to create such audience grants.
- Direct agent ID, modelSpec selection, resumed conversation, added-agent and
  reachable alternate API routes enforce the same rule. A crafted ephemeral
  request cannot access CXOne through Standard/Fast.
- Revoke agent VIEW after a successful call: same session/conversation is denied.
  Restore it, then revoke MCP VIEW and repeat. Restore both and confirm recovery
  without restart. Repeat across replicas with warm caches when deployed.
- Simulated ACL-store failure, unresolved resource and mismatched binding fail
  closed; ordinary permission denials remain understandable, not generic 500s.
- Provision dry run writes nothing; apply/rerun/read-back succeeds; grant failure
  and rollback preserve pre-existing permissions and leave no usable partial access.
- For users without CXOne grants, Standard/Fast chat and File Search
  upload/index/retrieve still work. Cross-user file access remains denied.
- Keep existing agent/MCP sharing behavior for unrelated resources, builder
  restrictions, model/context settings and PBI-08 startup isolation unchanged.

Add policy unit tests and real persistence tests using a supported MongoDB test
instance. Add route/stream integration tests that execute real middleware and
permission queries. Use a controlled MCP server/provider stub to count dispatches;
ordinary tests must not call the live CXone tenant. Do not mock the authorization
decision itself and call the result an integration test.

Reuse tests around `canAccessAgentFromBody`, `canAccessMCPServerResource`,
`ServerConfigsDB`, agent loading, MCP dispatch and ACL methods. Run tests from
the proper workspaces, then lint/typecheck changed TypeScript. If a MongoDB test
binary cannot be validated, use a supported local test database or report the
blocked test; do not disable integrity checks or record it as passed.

## 8. Evidence, rollout and completion

Create `docs/PBI-09-BE-evidence.md` separately when implementation/testing begins.
Record exact application/config/MCP revisions, environment and UTC run time,
resource-binding fingerprints, sanitized grant outcomes, all four matrix results,
revocation latency/race boundary, tests run, Standard/File Search regressions,
reviewer and remaining blockers. Keep identifying details in an access-controlled
operator record; public evidence need not contain Ziven's user ID or email.

Rollout order: implement and test the guard -> review the resolved resource and
named-user grant plan -> deploy the patched image through the normal process ->
apply/read back both grants -> execute deployed acceptance -> record the result.
Do not enable CXOne on an image that lacks the two-grant enforcement. Existing
authorization and environment controls govern deployment and real grants; this
guide does not create either.

Rollback should disable the CXOne entry and revoke its consumption grants while
preserving Standard/File Search and existing data. Do not roll back the security
guard to an agent-only image while leaving CXOne enabled.

PBI-09 closes only when every acceptance item has evidence, including Ziven's
two grants, each single-grant denial, clear API errors, live revocation and the
Standard/File Search regression checks. Local fixture tests prove authorization
plumbing only. Keep unfinished PBI-08, PBI-06 and PBI-07 acceptance visible under
their own items.
