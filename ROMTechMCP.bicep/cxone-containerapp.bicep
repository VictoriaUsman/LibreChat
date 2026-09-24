// The CX1 MCP server's Container App (PBI-03). Deliberately does NOT
// create the Container Apps Environment, the Key Vault, the ACR, or the
// image-pull identity — those are existing resources this app attaches
// to, confirmed via WI 11711 (see docs/PBI-03-BE-implementation.md and
// the "Inputs to obtain from Behnam / WI 11711" table there). This module
// creates exactly one thing: the Container App and its SYSTEM-assigned
// runtime identity. The Key Vault role assignment for that identity is a
// SEPARATE module (cxone-keyvault-access.bicep) — see that file's header
// for why the dependency graph is split this way.
//
// All of the WI-11711-dependent parameters below default to empty/unset
// so this file — and main.bicep's disabled path (deployCxoneMcp=false) —
// compiles today. None of them have a real value yet; do not fill in
// guessed values here. Deployment is gated at the call site in main.bicep,
// not by any validation inside this file (Bicep lacks a portable, non-
// experimental way to assert string shape at compile time) — see
// tests/infra/test_cxone_containerapp_bicep.py for the structural checks,
// and scripts/preflight_cxone_mcp.py for the input-shape checks intended
// to run against real parameter values once they exist.

param appName string = 'cx1-mcp'

@allowed([
  'Dev'
  'Test'
  'Uat'
  'Prod'
])
param environmentName string
param location string

@description('Resource ID of the EXISTING, shared Container Apps Environment — must be the SAME one LibreChat/LiteLLM/RAG API already run in. From WI 11711.')
param containerAppsEnvironmentId string = ''

@description('ACR login server, e.g. myregistry.azurecr.io. From WI 11711.')
param registryServer string = ''

@description('Image repository name WITHOUT a tag or digest, e.g. cx1-mcp. A tag/digest here is rejected by the preflight check (scripts/preflight_cxone_mcp.py), not by this template.')
param imageRepository string = ''

@description('Exactly 64 lowercase hex characters — the released image\'s sha256 digest. No "latest", no mutable release tag, no quickstart placeholder in production inputs.')
param imageSha256 string = ''

@description('Resource ID of the EXISTING, WI-11711-authorized user-assigned identity used ONLY to pull the image. Never used by application code inside the container — see identitySettings below.')
param imagePullIdentityId string = ''

@description('The port the MCP server actually listens on inside the container — must match the real image\'s bind address/port, not guessed.')
param targetPort int = 8000

@description('Path the platform polls to confirm the process is alive. Leave empty to omit the liveness probe until the real image\'s health contract is confirmed.')
param livenessPath string = ''

@description('Path the platform polls to confirm the app is ready to serve traffic. Leave empty to omit the readiness probe until the real image\'s health contract is confirmed.')
param readinessPath string = ''

@description('Non-secret: the confirmed environment vault\'s URI, e.g. https://kv-romtech-dev.vault.azure.net/. The app authenticates to it with its OWN system identity (romtech_mcp.cxone.credentials.AzureKeyVaultCredentialProvider) — never the image-pull identity.')
param vaultUri string = ''

@description('Key Vault secret NAMES (not values) for the four CXone credentials — matches romtech_mcp.cxone.config.SecretNames defaults. PBI-02 does not read arbitrary new env var names; these are passed through to whatever bootstrap code constructs CXoneConfig.')
param cxoneClientIdSecretName string = 'cxone-client-id'
param cxoneClientSecretSecretName string = 'cxone-client-secret'
param cxoneAccessKeyIdSecretName string = 'cxone-access-key-id'
param cxoneAccessKeySecretSecretName string = 'cxone-access-key-secret'

param cpu string = '0.5'
param memory string = '1Gi'

var livenessProbes = !empty(livenessPath)
  ? [
      {
        type: 'Liveness'
        httpGet: {
          path: livenessPath
          port: targetPort
        }
      }
    ]
  : []

var readinessProbes = !empty(readinessPath)
  ? [
      {
        type: 'Readiness'
        httpGet: {
          path: readinessPath
          port: targetPort
        }
      }
    ]
  : []

resource app 'Microsoft.App/containerApps@2025-01-01' = {
  name: '${appName}-${toLower(environmentName)}'
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
        // Internal only, on purpose — reached from LibreChat's agent
        // runtime inside the SAME Container Apps environment, never from
        // the public internet. Do not add a public route/proxy here.
        external: false
        targetPort: targetPort
        transport: 'http'
        // Required for the explicitly-internal-HTTP contract above: this
        // is not exposing plaintext traffic externally, since ingress is
        // already restricted to the environment's own network.
        allowInsecure: true
      }
      registries: [
        {
          server: registryServer
          identity: imagePullIdentityId
        }
      ]
      identitySettings: [
        // The pull identity exists ONLY for the image-pull lifecycle
        // stage — never available to application code inside the running
        // container. Application code uses the system identity
        // exclusively (romtech_mcp.cxone's ManagedIdentityCredential is
        // constructed with no client_id, which selects system-assigned).
        {
          identity: imagePullIdentityId
          lifecycle: 'None'
        }
        {
          identity: 'system'
          lifecycle: 'Main'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'cxone-mcp'
          image: '${registryServer}/${imageRepository}@sha256:${imageSha256}'
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            { name: 'CXONE_VAULT_URI', value: vaultUri }
            { name: 'CXONE_CLIENT_ID_SECRET_NAME', value: cxoneClientIdSecretName }
            { name: 'CXONE_CLIENT_SECRET_SECRET_NAME', value: cxoneClientSecretSecretName }
            { name: 'CXONE_ACCESS_KEY_ID_SECRET_NAME', value: cxoneAccessKeyIdSecretName }
            { name: 'CXONE_ACCESS_KEY_SECRET_SECRET_NAME', value: cxoneAccessKeySecretSecretName }
          ]
          probes: concat(livenessProbes, readinessProbes)
        }
      ]
      scale: {
        // Fixed at 1 deliberately — prevents idle scale-to-zero (the cold-
        // start problem CX1_Reporting_Build_Spec_v3.md §3.2 calls out), not
        // startup/crash/maintenance/node-replacement downtime. Increase
        // maxReplicas later with real capacity requirements; do not lower
        // minReplicas to save cost.
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output appResourceId string = app.id
output appFqdn string = app.properties.configuration.ingress.fqdn
output runtimePrincipalId string = app.identity.principalId
output internalBaseUrl string = 'http://${app.properties.configuration.ingress.fqdn}'
