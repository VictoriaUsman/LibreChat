# PBI-03-BE — deployment evidence

Status: **no real deployment has occurred.** Everything below is pending.
This document exists so evidence has a fixed place to land once WI 11711's
inputs are confirmed and a real image is built — not to imply any of it
has happened yet. Do not check any row off without an actual command
output backing it, and never paste a secret value, a raw CXOne response
body, or a credential into this file.

Compile-time evidence that already exists (structural, not deployment) is
in `tests/infra/` — 42 tests passing as of this writing (52 more in
`tests/cxone/` cover PBI-02's auth/transport library; 94 total), covering
internal ingress, fixed `minReplicas`, digest-based image references,
pull-identity isolation, the single intended role assignment, that the
disabled (`deployCxoneMcp=false`) path compiles for every environment, and
that `scripts/preflight_from_bicepparam.py` is actually wired into all
three pipeline YAML files (as a `CxoneMcpPreflight` stage running before
what-if/create, against each environment's real resolved parameters — not
just callable standalone and never invoked, which is what a review caught
in the first version of this PBI). That is not a substitute for anything
in the table below.

## Acceptance evidence

| Acceptance | Required evidence | Status |
|---|---|---|
| Same environment | Compare `managedEnvironmentId` for all four apps (LibreChat, LiteLLM, RAG API, cx1-mcp); verify VNet configuration | **Pending** — no `containerAppsEnvironmentId` confirmed yet (WI 11711) |
| Internal-only ingress | Deployed `external: false`; no public routing/proxy exposure | **Pending** — not deployed |
| Dedicated identity | Compare system principal IDs with LibreChat/LiteLLM; confirm they differ | **Pending** — not deployed |
| Vault access only | Vault-scoped Secrets User assignment; review direct/inherited/group-derived effective permissions; retrieve all four secrets inside the container without printing values | **Pending** — not deployed |
| Warm idle service | Deployed `minReplicas: 1`, ready revision, replica still running after an idle period. `minReplicas: 1` only prevents idle scale-to-zero — it does not guarantee no startup delay during deployment, a crash, or platform maintenance; do not word this row's result as a broader cold-start guarantee than that | **Pending** — not deployed |
| Immutable image | Deployed image contains expected digest and matches the pushed manifest | **Pending** — no image built/pushed yet |
| LibreChat connectivity | Successful HTTP request from LibreChat to the actual MCP endpoint, including the protocol handshake if required | **Pending** — no MCP server image exists yet (`src/romtech_mcp/cxone` is auth/transport only, not a runnable HTTP server) |
| Outside access rejected | Same endpoint fails from outside the VNet without VPN/proxy, using a healthy internal positive control | **Pending** — not deployed |
| Jobs independent | Deploy with the shared deployment's existing `deployJobs` value unchanged; validate both values with this app enabled where available | **Pending** — not deployed |
| No regression | `what-if` shows no unintended existing-app changes; existing LibreChat/LiteLLM/RAG health checks pass after deployment | **Pending** — not deployed |
| Missing-role identity produces a distinct credential error | An isolated identity, confirmed via `az role assignment list --include-inherited --include-groups` to hold no role (direct, inherited, or group-derived), and actually selected by the code under test (system-assigned identity on a scratch container by default, or `azure_managed_identity_client_id` explicitly overridden for a user-assigned one — merely attaching an identity does not select it), tested from inside a real running container against a known-good vault/secret, raises `CredentialLoadError` (`stage=secret_retrieval`, `reason_code="retrieval_failed"`), paired with a successful positive-control retrieval by the authorized identity — never by removing the working app's own access, and `reason_code="retrieval_failed"` alone (also covers missing secrets/network failures) is not sufficient proof by itself. See procedure in `docs/PBI-03-BE-implementation.md` | **Pending** — not deployed; procedure documented, not yet exercised |
| Dedicated CXone service account | Account identifier, purpose/owner, key-generation provenance, appropriate API permissions, rotation responsibility | **Pending** — needs CXOne administrator confirmation, separate from this PBI's infra work (carried over from PBI-02) |

## Template for filling in a row once evidence exists

```
### <Acceptance row name>
- Environment: <Dev/Test/Uat/Prod>
- Date/time (UTC): <...>
- Command(s) run: <...>
- Sanitized output: <...>  (never a secret value or raw CXOne body)
- Result: PASS / FAIL — <one line>
```

## What is still blocking every row above

From `docs/PBI-03-BE-implementation.md`'s "Inputs to obtain from Behnam /
WI 11711" table: subscription, resource group, region, tenant, and the
per-environment deployment service connection identifiers (`ROMTechMCPDevSC`
/ `ROMTechMCPTestSC` / `ROMTechMCPProdSC`, in
`ROMTechMCP.pipelines/templates/insert-variables-{dev,test,prod}.yml`) are
already configured in this repo and only need Behnam's *confirmation* —
for the service connections, specifically whether that principal is
actually permitted to create a Key Vault role assignment in the target
scope, not whether the connection exists. Genuinely blank and needing him
to *provide* for the first time: the existing Container Apps Environment
resource ID, ACR details and pull-authorization model, a released image
digest, a dedicated image-pull identity, and the MCP image's actual
listening port/health paths. None of these can be discovered or guessed
from this repository or from code review — see the message already
drafted for Behnam in this project's history.

Separately, and not resolved by WI 11711 alone: no work item in this repo
identifies who builds the runnable MCP HTTP server/host itself. PBI-02
built the auth/transport library it would use; PBI-03 builds the
deployment infrastructure for it; whether authoring a minimal HTTP host
shell itself belongs to either PBI is genuinely unresolved, not settled by
either PBI's existing scope text. Until that ownership is assigned, there
is no image to build a real digest from regardless of what WI 11711
supplies.
