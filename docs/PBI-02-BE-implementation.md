# PBI-02-BE implementation instructions

Status: partially demonstrated by discovery; not implemented as a production client.
Assessment baseline: commit `187d89b`. This document specifies the remaining
work; it does not certify deployment or service-account ownership.

## Acceptance-criteria assessment

| Criterion | Current evidence | Remaining work |
|---|---|---|
| Four credentials from Key Vault through container managed identity | `discovery/cxone_client.py:load_config` reads environment variables; discovery Bicep accepts secret values as deployment parameters | Implement SDK-based secret retrieval, container identity, and vault authorization |
| Token exchange and Bearer requests | Demonstrated live by discovery | Extract into a reusable client and test independently of probe code |
| Transparent expiry recovery | `_ensure_auth` refreshes before locally calculated expiry | Handle API 401 once, serialize concurrent refresh, and replay the original read request |
| Dedicated service account | Required in documentation | Obtain operational evidence of the access key's owner; a successful login does not prove this |
| Distinct credential-class authentication errors | Raw HTTP exceptions currently propagate from authentication | Introduce safe typed errors and verified error-code mappings |
| Bounded backoff for 429/5xx | Discovery intentionally does not retry | Implement and test a production retry policy |
| No secrets, tokens, or raw response bodies in logs | Discovery avoids storing metric bodies, but this is not comprehensive production logging validation | Implement allowlisted logging and test failure paths for leakage |
| Discovered tenant host | Two-call flow demonstrated live | Preserve discovery and remove any need for a region-specific API-host setting |

## Scope and layout

Implement a transport/authentication library, not reporting aggregation, retention
measurement, lag estimation, MCP tools, or changes to business skill selection.
Keep discovery's no-retry measurement behavior intact. Use its tested protocol
behavior as a reference rather than importing its measurement/file-writing logic.

Proposed files, relative to the repository root:

```text
src/romtech_mcp/cxone/config.py
src/romtech_mcp/cxone/credentials.py
src/romtech_mcp/cxone/errors.py
src/romtech_mcp/cxone/client.py
tests/cxone/test_credentials.py
tests/cxone/test_authentication.py
tests/cxone/test_retry.py
tests/cxone/test_log_safety.py
```

Add production packaging and dependency configuration for `azure-identity`,
`azure-keyvault-secrets`, the selected HTTP client, and the test runner. Resolve
and lock compatible versions during implementation. An async client fits an
async MCP server: use Azure SDK async clients, an async HTTP transport, an async
lock, and nonblocking sleep. Do not call blocking `requests` from an async tool.
Expose lifecycle cleanup and reuse one client per process, not one per tool call.

## Credentials and infrastructure

1. Accept only non-secret configuration: vault URL, four secret names, API
   version, public token/discovery URLs, timeout/retry settings, and optionally
   the Azure client ID selecting a user-assigned managed identity. Distinguish
   that Azure identity selector from the CXOne application client ID.
2. Use `azure.identity.aio.ManagedIdentityCredential` and
   `azure.keyvault.secrets.aio.SecretClient` in the deployed container. Read all
   four values with `get_secret`. Do not fall back to environment-supplied CXOne
   credentials. Inject a fake credential provider for unit tests.
3. Suggested secret names: `cxone-client-id`, `cxone-client-secret`,
   `cxone-access-key-id`, `cxone-access-key-secret`. Names may be configured;
   values have no defaults. Reject missing, disabled, or empty secrets with a
   safe `CredentialLoadError` identifying the logical credential class and
   retrieval stage, without logging SDK exception text or values.
4. Keep values only in memory. Mark secret-bearing fields `repr=False`; avoid
   serializing credential/token objects. Read the latest secret versions on a
   new authentication cycle so rotation can take effect without rebuilding the
   image. Never log version URLs or fetched secret objects.
5. In `ROMTechMCP.bicep/keyvault.bicep`, explicitly enable RBAC authorization if
   using the existing Key Vault Secrets User role assignment. The current
   template has empty access policies and does not explicitly select RBAC.
   Verify existing vault consumers before changing the deployed access model.
6. Enable the production container's managed identity and pass its principal ID
   into the vault role assignment; `main.bicep` currently does not pass it.
   Scope Key Vault Secrets User to the intended vault, not the subscription.
   Confirm the container can reach the vault through the deployed network.
7. Provision secret values through the approved secret-management process.
   Do not put them in Bicep parameter files, pipeline YAML, Docker ARG/ENV,
   source, test fixtures, or build context. Add a production `.dockerignore`
   excluding `.env`, discovery results, and local credential files.

Azure reference: [Key Vault secrets and Python SDK setup](https://learn.microsoft.com/en-us/azure/key-vault/general/apps-api-keys-secrets),
[managed identity developer guidance](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview-for-developers).

## Authentication and token lifecycle

Preserve the flow empirically confirmed for this application registration:

1. Read the four credentials from the provider.
2. POST the password-grant form to the configured public token endpoint, using
   Basic authentication for application client ID/secret and access key
   ID/secret as username/password. Do not change the registered authentication
   method merely because another example uses a different one.
3. Require a nonempty access token, ID token, and valid positive token lifetime.
4. Decode the ID token payload to obtain `tenantId` for routing. Decoding alone
   is not identity verification: use this only for the token just received
   directly from the trusted token endpoint, never caller-provided JWTs or an
   authorization decision. Do not include the JWT in parse errors.
5. GET the configured discovery endpoint with `tenantId`; require its
   `api_endpoint`. Validate an HTTPS URL without user info, query, or fragment.
   Publish the token and discovered endpoint atomically only after both succeed.
6. Send API requests to this discovered host with `Authorization: Bearer ...`.
   Accept relative API paths only; do not attach credentials to arbitrary
   caller-supplied absolute URLs or follow redirects to other hosts.

Use a monotonic expiry deadline and a safety margin capped for short token
lifetimes. Before each request, refresh if absent or near expiry. Protect this
with a lock and recheck after acquiring it so simultaneous requests share a
single authentication cycle.

On an API 401, invalidate only the token generation used by that request.
Reuse a newer token if another caller already refreshed; otherwise authenticate
once and replay the original GET with identical query parameters. A second 401
is terminal. Do not retry 403 as token expiry. Initially expose read operations;
do not automatically replay non-idempotent writes without an explicit policy.

NICE reference: [Getting Started](https://developer.niceincontact.com/Documentation/GettingStarted),
[Your First App](https://developer.niceincontact.com/Documentation/YourFirstApp).

## Authentication errors and safe logging

Define typed errors with safe fields such as `stage`, `credential_class`,
`reason_code`, `status_code`, and `attempt_count`. Distinguish:

- Key Vault/managed-identity access or secret retrieval failure.
- Application credential rejection: client ID/client secret.
- API-user credential rejection: access key ID/access key secret.
- Ambiguous authentication rejection: class unknown.
- Tenant discovery failure, authorization failure, throttling exhaustion,
  transient server failure exhaustion, and malformed protocol response.

Do not infer the rejected class from HTTP 400/401 alone. Parse an allowlisted
OAuth error code in memory and map it only where its meaning is verified for
this flow. For example, test `invalid_client` as the application class and
`invalid_grant` as the API-user/grant class only when supported by NICE's
documented or observed response. Never print `error_description` or the body.
Record sanitized evidence of the mappings in tests/docs. If CXOne returns an
ambiguous error, report `unknown` honestly; the class-identification acceptance
criterion needs clarification for that case rather than a guessed diagnosis.

Use fixed log messages and an allowlist of scalar metadata. No credentials,
Authorization headers, token payloads, request bodies, raw response bodies,
arbitrary response headers, raw exceptions, or HTTP debug dumps. Avoid exception
chaining that could expose an underlying request/response at the MCP boundary.
Apply this to success, retries, terminal errors, validation, and startup paths.

## Bounded retries

Implement one explicit retry owner per transport. Do not stack hidden HTTP
adapter retries under application retries. Configure Azure SDK retry limits
separately and include their time in the overall deadline.

Suggested initial policy (implementation defaults, not discovered CXOne limits):

- Three transient attempts per HTTP operation, including the initial attempt.
- Retry 429 and 5xx; do not retry permanent 4xx credential rejection.
- Exponential backoff with jitter, base 1 second, cap 30 seconds, plus explicit
  connect/read timeouts and a configurable end-to-end deadline.
- Honor valid `Retry-After` seconds or HTTP-date values. If the requested wait
  exceeds the remaining deadline, fail safely rather than retrying early.
- Allow at most one API-401 authentication recovery per logical caller request.
  The recovery replay may have its own three-attempt transient budget; this
  gives at most six API sends, not an unbounded recursive retry loop.
- Bound token and discovery HTTP operations too. Retry their transient 429/5xx
  failures, not their permanent authentication rejections. Document the total
  deadline across vault access, authentication, discovery, sleeps, and replay.

Inject clock, sleeper, random jitter, HTTP transport, and credential provider so
tests are deterministic and do not sleep or contact live services.

## Required verification

Use synthetic sentinel secrets/tokens and mocked responses. Verify:

1. All four secrets are requested; production construction uses managed identity;
   missing/empty values fail safely with no environment fallback.
2. Token request uses both credential pairs, discovery uses the tenant claim,
   and API calls use the discovered host and correct Bearer token.
3. A locally expired token is renewed; a premature API 401 renews once and
   replays successfully; a second 401 terminates. Concurrent expiry causes one
   refresh, and a late 401 cannot discard a newer token.
4. Known application/user rejection cases yield distinct safe errors; ambiguous
   failures remain unknown. Permanent rejection causes no retry loop.
5. 429 and 5xx retry with bounded attempts; Retry-After and deadlines are obeyed;
   exhausted retries, malformed JSON, timeouts, and 403 terminate predictably.
6. Logs and outward exception text contain none of the synthetic secrets, tokens,
   raw response payloads, or upstream descriptions, including nested failures.
7. Closing the client closes its HTTP and Azure SDK resources.

For deployment acceptance, retain non-secret evidence that the real container
identity retrieves all four secrets and successfully calls the discovered host.
Confirm dedicated service-account ownership with the CXOne administrator:
account identifier, purpose/owner, key-generation provenance, appropriate API
permissions, and rotation responsibility. Do not retrieve or disclose keys for
this evidence. Dedicated-account ownership cannot be inferred from a JWT alone.

Do not rotate or invalidate production credentials just to test negative paths;
use mocks or approved nonproduction fixtures. Build the production image and
check its context/layers for accidental inclusion of secret files without
printing any values. Run Bicep validation and the focused test suite.

PBI-02 is complete only when code/tests and deployment/service-account evidence
cover all acceptance criteria. Missing infrastructure or account confirmation
must remain explicitly outstanding, not be marked complete by unit tests.
