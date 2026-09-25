# PBI-03-BE — Container App implementation instructions

Status: ready for authoring and local validation; deployment acceptance depends
on WI 11711, confirmed environment details, and a runnable MCP server image.
This document is a specification, not a deployment record.

## Current repository and scope

- `ROMTechMCP.bicep/main.bicep` currently deploys only the Key Vault module.
- `keyvault.bicep` enables RBAC and supports a conditional Secrets User assignment.
- `src/romtech_mcp/cxone/` is an authentication/transport library. It is not yet
  a runnable HTTP MCP server or a production image.
- `discovery/Dockerfile` builds the measurement service, not the MCP server.
  Do not deploy that image as the production MCP implementation.
- The existing LibreChat, LiteLLM, RAG API resources and `deployJobs` gate are
  not defined in this repository. Identify their owning deployment before
  claiming integration or no-regression evidence.
- The pipeline imports shared templates from `ROMTech/PipelineTemplates`.
  Inspect those templates before changing parameter plumbing or deployment mode.
- **The work item that owns building a runnable MCP HTTP server/host is not
  identified anywhere in this repo.** PBI-02 built the auth/transport library;
  this PBI (PBI-03) builds the deployment infrastructure for one; neither has
  built the actual HTTP host process the container image would run. This is
  genuinely unresolved, not merely unbuilt: "do not add reporting tools or
  aggregation logic under this infrastructure PBI" excludes business/domain
  logic (report generation, aggregation) from PBI-03 — it does not itself say
  anything about a minimal HTTP host/transport shell, which is arguably
  infrastructure rather than reporting logic. Treat "PBI-03 doesn't build the
  host either" as unconfirmed, not as something that sentence already settles.
  Get explicit ownership assigned rather than inferring it either way.

Implement the new app, its identity, narrowly scoped vault access, and deployment
inputs. Do not recreate the existing environment, VNet, registry, or other apps.
Do not add reporting tools or aggregation logic under this infrastructure PBI.

## Inputs to obtain from Behnam / WI 11711

Two different kinds of input are conflated below in earlier drafts of this
table: some values already exist in this repo's checked-in `.bicepparam`
files (from earlier PBI work) and only need Behnam's *confirmation* they're
still correct for this new app; others are genuinely blank and need him to
*provide* them for the first time. Asking for the wrong kind wastes a round
trip.

| Input | Why it is needed | Status in this repo |
|---|---|---|
| Subscription, resource group, region, tenant | Deployment scope; region must match the existing environment | **Already configured** — `subId`, `rgName`, `location`, `tenantId` are set per-environment in `main.{dev,test,prod}.bicepparam`. Needs Behnam's *confirmation* these are still correct for the new app, not fresh discovery |
| Existing Container Apps Environment resource ID | Must match LibreChat, LiteLLM and RAG; confirm VNet integration and supported workload profile | **Blank** — `cxoneContainerAppsEnvironmentId` is `''` in every environment's `.bicepparam`; needs a real value |
| Environment Key Vault name, resource ID and URI | Confirm whether this is the vault already managed here; do not create a second vault by assumption | `keyvault.bicep` already deploys/references a vault per environment (`kv-romtech-<env>`) — needs Behnam's *confirmation* this is the one the new app should use, not a new lookup |
| ACR login server, resource ID, repository, pull authorization model | Build/push and private image pull depend on WI 11711 | **Blank** — `cxoneRegistryServer`/`cxoneImageRepository` are `''` |
| Released custom image digest | Deploy `registry/repository@sha256:<64 hex characters>` | **Blank** — `cxoneImageSha256` is `''`; also depends on the unidentified runnable-image work item above |
| Dedicated image-pull identity resource ID and authorization | Keep registry permissions separate from runtime secret access | **Blank** — `cxoneImagePullIdentityId` is `''` |
| MCP image's listening port, health paths and configuration contract | Ingress/probes must match the actual image | Partially set — `cxoneTargetPort` defaults to `8000`; `cxoneLivenessPath`/`cxoneReadinessPath` are `''`. Depends on the unidentified runnable-image work item |
| Existing app deployment location and current `deployJobs` behavior | Verify integration and avoid altering unrelated apps | **Blank** — not present in this repo; `deployJobs` itself isn't defined here |
| Deployment service connection's permitted role-assignment scope | Deployment principal must be able to create the vault-scoped assignment | **Already configured, permissions unverified** — `ROMTechMCPDevSC`/`ROMTechMCPTestSC`/`ROMTechMCPProdSC` are set per-environment in `ROMTechMCP.pipelines/templates/insert-variables-{dev,test,prod}.yml`. The connection identifiers are not the open item; whether that principal is actually permitted to create a Key Vault role assignment in the target scope is unconfirmed and needs checking (e.g. `az role assignment list` for its principal, with `--include-inherited`/`--include-groups` — a default-scope-only check would miss a role granted at the resource-group or subscription level), not obtaining from scratch |

Do not request secret values in chat or commit them. PBI-02's four secret values
must already be provisioned through the approved Key Vault process.

## Files to implement

1. Add `ROMTechMCP.bicep/cxone-containerapp.bicep` for the app.
2. Add `ROMTechMCP.bicep/cxone-keyvault-access.bicep` for the vault-scoped role
   assignment, or place that assignment in the app module with an existing vault
   reference. Use a scoped module if the vault is in a different resource group.
3. Wire modules into `main.bicep`. Add vault name/URI outputs to `keyvault.bicep`
   if that module owns the confirmed target vault.
4. Update environment parameter inputs and pipeline wiring only after inspecting
   the shared templates. Add preflight validation for the enabled app inputs.
5. Add focused infrastructure checks and a deployment evidence document.

While dependencies are unavailable, a dedicated `deployCxoneMcp` flag may default
to false so existing deployments still work. This is independent of `deployJobs`.
Turning it off is not PBI completion. Once an environment deploys this app, keep
its deployment configuration enabled rather than silently disabling updates.

## Container App contract

Use the following shape as guidance, filling in typed parameters and validating
the chosen API version against the actual environment. This is an excerpt, not
a complete deployable module:

```bicep
resource app 'Microsoft.App/containerApps@2025-01-01' = {
  name: 'cx1-mcp-${toLower(environmentName)}'
  location: location
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${imagePullIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: targetPort
        transport: 'http'
        allowInsecure: true
      }
      registries: [
        { server: registryServer, identity: imagePullIdentityId }
      ]
      identitySettings: [
        { identity: imagePullIdentityId, lifecycle: 'None' }
        { identity: 'system', lifecycle: 'Main' }
      ]
    }
    template: {
      containers: [
        {
          name: 'cxone-mcp'
          image: '${registryServer}/${imageRepository}@sha256:${imageSha256}'
          // Add confirmed non-secret config, resources, and probes here.
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}
```

- `external: false` restricts app ingress to the Container Apps environment.
  Internal ingress is narrower than arbitrary VNet-wide access; test the positive
  path from LibreChat in that same environment. `allowInsecure: true` permits the
  explicitly required internal HTTP without a redirect to HTTPS. Do not add a
  public proxy or environment HTTP route that exposes this app.
- Keep `minReplicas: 1` fixed. `maxReplicas: 1` is a conservative initial value;
  increase later with capacity requirements. This prevents idle scale-to-zero,
  not startup during deployment, crashes, maintenance, or node replacement.
- Validate image inputs before deployment: nonempty registry/repository,
  repository without tag/digest, and exactly 64 hexadecimal digest characters.
  Check that the manifest exists in the supplied registry. No `latest`, mutable
  release tag, guessed digest, or quickstart placeholder in production inputs.
- Match the image's actual listening port and bind address (`0.0.0.0`). Define
  explicit CPU/memory compatible with the environment. Use health endpoints that
  exist; TCP readiness alone proves only that a socket accepts connections.
- Output app resource ID, FQDN, runtime principal ID, and internal HTTP base URL.
  Do not guess the eventual MCP endpoint path; use the server's transport contract.

The ingress and identity settings follow Microsoft's
[ingress configuration](https://learn.microsoft.com/en-us/azure/container-apps/ingress-how-to)
and [managed identity availability controls](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity).

## Runtime identity, image pull, and Key Vault

The system-assigned identity belongs only to this app. Grant it exactly the
Key Vault Secrets User role (`4633458b-17de-408a-b874-0445c86b69e6`) on the
confirmed environment vault. Set `principalType: 'ServicePrincipal'` and use a
deterministic role-assignment name derived from vault ID, principal ID, and role
definition ID. Do not assign Contributor, Owner, Secrets Officer, or registry
roles to this runtime identity.

A private image still needs pull authorization. The recommended design uses a
separate existing user-assigned pull identity supplied/authorized by WI 11711.
The `lifecycle: 'None'` setting keeps that identity unavailable to container code.
The PBI's single-role constraint applies to the runtime identity; document this
separation with the platform owner. Do not silently grant AcrPull to the runtime
identity to work around it. Confirm the registry's RBAC/ABAC mode and appropriate
pull permission with WI 11711 rather than assuming one role fits all registries.
See Microsoft's [managed-identity image-pull guidance](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull).

Keep the dependency graph acyclic:

```text
existing environment + existing authorized pull identity + immutable image
                                      -> Container App -> runtime principal
vault creation/reference + runtime principal -> vault role assignment
```

If the app needs the vault URI, expose it from the vault module. Do not then make
that same vault module depend on the app's principal ID: split the assignment
out so vault creation does not wait for the app that depends on the vault.
Avoid defining the same assignment in both old and new modules.

Handle first deployment explicitly: a system principal exists only after the
app is created, and vault authorization can propagate later. The server must
not permanently crash during startup because the role assignment is pending.
Prefer lazy secret loading with safe unavailable responses until access works,
or an explicit two-stage bootstrap supported by the deployment. Do not make
resource creation depend on successful vault access when the role assignment
depends on that resource being created.

Pass only vault URL, secret names, and ordinary server settings as environment
variables. Add application bootstrap code that constructs `CXoneConfig` and
`AzureKeyVaultCredentialProvider` from those names: PBI-02 does not automatically
read arbitrary new environment-variable names. Use the system identity for vault
access; do not set its selector to the image-pull identity. No CXOne secret values
in Bicep, image layers, deployment outputs, or logs.

## Deployment integration

- Authoring, Bicep compilation, template assertions and preflight checks can be
  completed now. Image build/push and Azure deployment wait for real inputs.
- Keep the module outside all `deployJobs` conditionals. Do not add or flip that
  gate merely to deploy a web service.
- Preserve existing resource names, identities, images, scale settings, networking
  and pipeline defaults. Reference the shared environment by ID rather than
  redeclaring or taking ownership of it.
- Use the existing approved deployment mode. Do not introduce complete-mode
  resource-group deployment against the shared group: this repo does not declare
  the other apps. Inspect shared pipeline templates and the Azure what-if result.
- The deployment principal's build/push and role-assignment permissions are
  separate from the app's runtime permissions. Do not solve pipeline access by
  granting extra roles to the runtime identity.

## Validation and acceptance evidence

Run local Bicep compilation and parameter compilation for each changed environment.
Add checks against the compiled template/preflight for internal ingress, fixed
minimum replica count, digest-based image reference, private pull identity
isolation, and only the intended runtime role assignment. Reject missing inputs
when deployment is enabled. Verify the disabled/default path still compiles.
These checks do not prove Azure reachability or permissions.

Once WI 11711 and the image are ready, capture the following non-secret evidence:

| Acceptance | Required evidence |
|---|---|
| Same environment | Compare `managedEnvironmentId` for all four apps; verify environment VNet configuration |
| Internal-only ingress | Deployed `external: false`; no public routing/proxy exposure |
| Dedicated identity | Compare system principal IDs with LibreChat/LiteLLM; confirm they differ |
| Vault access only | Vault-scoped Secrets User assignment; review direct, inherited, and group-derived effective permissions; retrieve all four secrets inside the container without printing values |
| Warm idle service | Deployed `minReplicas: 1`, ready revision, and a replica still running after an idle period |
| Immutable image | Deployed image contains expected digest and matches the pushed manifest |
| LibreChat connectivity | Successful HTTP request from LibreChat to the actual MCP endpoint, including the protocol handshake if required |
| Outside access rejected | Same endpoint fails from a machine outside the VNet without VPN/proxy; use a healthy internal positive control so a broken app cannot count as isolation |
| Jobs independent | Deploy with the shared deployment's existing `deployJobs` value unchanged; where available validate both values with this app enabled |
| No regression | What-if shows no unintended existing-app changes; existing LibreChat, LiteLLM and RAG health/smoke checks pass after deployment |
| Missing-role identity produces a distinct credential error | An isolated identity confirmed to hold no role on a known-good vault/secret raises PBI-02's `CredentialLoadError` (`stage=secret_retrieval`, `reason_code="retrieval_failed"`) retrieving that same secret, paired with a successful control retrieval by the actually-authorized identity — never by removing the working app's own access. See procedure below |

### Missing-role identity deny-path procedure

`reason_code="retrieval_failed"` is deliberately broad — `AzureKeyVaultCredentialProvider.get_secret`
collapses a missing secret, a disabled secret, a network failure, and an
access-denied rejection into the same code (see its comment in
`src/romtech_mcp/cxone/credentials.py`), because which Azure SDK exception
maps to which of those hasn't been empirically confirmed. Observing that
error alone does NOT prove the role assignment was the cause. Isolate the
variable instead of just removing the working app's access:

1. Use a **separate, dedicated test identity** — never the deployed app's
   own runtime identity or role assignment (removing the working app's
   access risks leaving it broken and conflates "we tested the deny path"
   with "we took the real app down"). `build_credential_provider()` (see
   `src/romtech_mcp/cxone/bootstrap.py`) always targets the SYSTEM-assigned
   identity by default — `ManagedIdentityCredential`'s `client_id` is `None`
   unless explicitly overridden — so which option below you use determines
   how the test must construct the provider, and getting this wrong means
   the test authenticates as the wrong identity entirely, not the intended
   unauthorized one:
   - **Preferred:** a scratch Container App (or other scratch compute)
     whose own SYSTEM-assigned identity is the test identity. No code
     change needed — the default (no `azure_managed_identity_client_id`)
     already targets it.
   - **Alternative:** a user-assigned test identity attached to some
     container. Merely attaching it does NOT select it — you must
     construct `AzureKeyVaultCredentialProvider` with
     `azure_managed_identity_client_id=<test identity's client ID>`
     explicitly (a one-off override for this test, not a bootstrap.py
     change) or `ManagedIdentityCredential` will default to that
     container's system identity instead. Getting this wrong means an
     observed `retrieval_failed` could reflect the wrong identity being
     selected, not the intended identity being denied.
2. Confirm this test identity's effective permissions on the target vault
   BEFORE the test — with BOTH `--include-inherited` and `--include-groups`:
   `az role assignment list --assignee <principal-id> --scope
   <vault-resource-id> --include-inherited --include-groups`. Without
   `--include-inherited`, the command only returns assignments made
   directly at that exact scope — a role granted at the resource-group or
   subscription level would not show up, and its absence there would not
   actually prove the identity lacks effective access. `--include-groups`
   is required to also rule out access granted via an AAD group the
   identity's principal is a member of. Confirm no `Key Vault Secrets User`
   (or equivalent) entry appears through either path; don't assume absence,
   verify it with both flags.
3. Pick a **known-good** vault and secret name — one a properly-authorized
   identity can successfully retrieve right now. Run the authorized
   retrieval as a positive control (Step 5) close in time to the negative
   test, so a difference is attributable to the missing role, not to the
   secret being missing/disabled or a transient network failure.
4. From inside the actual running container set up per step 1 (not from a
   local machine or a generic client-secret flow), trigger
   `AzureKeyVaultCredentialProvider.get_secret` (via `SecretNames` in
   `src/romtech_mcp/cxone/config.py`), constructed exactly as step 1
   specifies for whichever option was used. `ManagedIdentityCredential`
   authenticates through the Azure Instance Metadata Service, which only
   exists on real Azure compute with a managed identity attached; running
   this anywhere else does not exercise the same code path the deployed
   app actually uses, and would not satisfy this acceptance row. Confirm
   it raises `CredentialLoadError`
   with `stage=secret_retrieval` and `reason_code="retrieval_failed"`, and
   that the sanitized error carries the (non-secret) secret name, not a
   bare Azure SDK exception, a hang, a generic timeout, or a
   silently-missing credential. Capture the sanitized error's
   `repr()`/log line as evidence — never the raw Azure SDK exception text
   or any secret value.
5. Immediately confirm the SAME secret is still successfully retrievable
   through the actually-authorized (real app) identity, as the positive
   control referenced in step 3.
6. Tear down the test identity/its (lack of) role assignment and the
   scratch container, if one was created; do not leave test-only
   principals or compute provisioned against the vault afterward.

Store evidence in `docs/PBI-03-BE-evidence.md` when it actually exists. Record
environment, image digest, time, result, and sanitized outputs; mark unperformed
checks pending. Do not log credentials or raw CXOne bodies during verification.

PBI-03 remains incomplete until the real custom app is deployed and the network,
identity, jobs-independence and no-regression checks pass. Its vault-access check
can also supply PBI-02's managed-identity evidence; dedicated CXOne service-account
ownership still needs separate administrator confirmation.
