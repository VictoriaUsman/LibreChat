// Twice-weekly ACA Job running sync_okta_attribution.py (WI 11553's script,
// scheduled per "Schedule the Department-Sync Script as a Twice-Weekly ACA
// Job"). First Microsoft.App/jobs resource in this repo -- modeled on the
// shape of config/cleanup-job.yaml (that job has no bicep of its own yet)
// and on liteLlm.bicep's identity/secrets/env conventions.
//
// Now wired in-repo (WI 11711): the ACR (acr.bicep) + the image build/push
// (deploy pipeline `az acr build`) + this Job's AcrPull and "Key Vault Secrets
// User" role assignments (below). The Okta token secret already exists in every
// kv-romtech-<env>.
// Remaining external dependencies:
//   - Confirm this Job's outbound path reaches Cosmos Mongo + Postgres (it shares
//     the app's Container Apps environment, so should inherit it).
//   - Wire an Azure Monitor alert on Job execution failure (needs the alert
//     destination from Ops).

param envName string = 'Dev'
param location string = 'eastus'
param environmentId string
param acrName string
param keyVaultName string
param oktaOrgUrl string

@secure()
param oktaApiToken string
@secure()
param databaseUrl string
@secure()
param mongoUri string

var jobName = 'job-cgfe-okta-sync-${toLower(envName)}'

// The image is built + pushed to this env's ACR by the deploy pipeline
// (az acr build). The Job pulls it via its own managed identity (AcrPull, below).
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}
resource acrPullRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  scope: subscription()
  name: '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
}
resource kvSecretsUserRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  scope: subscription()
  name: '4633458b-17de-408a-b874-0445c86b69e6' // Key Vault Secrets User
}
var jobsImage = '${acr.properties.loginServer}/librechat-cleanup:latest'

resource oktaSyncJob 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    environmentId: environmentId
    configuration: {
      triggerType: 'Schedule'
      // 05:00 UTC Tue & Fri = midnight ET winter / 1am ET summer.
      scheduleTriggerConfig: {
        cronExpression: '0 5 * * 2,5'
        parallelism: 1
        replicaCompletionCount: 1
      }
      // 50 min: the two sources (Okta, Mongo) are fetched SEQUENTIALLY, each
      // with its own ~21 min worst-case retry backoff (~1/4/16 min), so a
      // both-sources-down run needs ~42 min of sleeps plus fetch/sync/audit
      // time. 1800s (30 min) would kill the replica mid-run -- BEFORE it writes
      // the status='failed' sync_run_log audit row -- exactly when recording the
      // failure matters most. Sized above the summed two-source worst case.
      replicaTimeout: 3000
      // 0: the script owns retries (run_with_retries + exponential backoff) and
      // exits non-zero only AFTER exhausting them, having already written a
      // status='failed' sync_run_log row. ACA retries a replica on ANY non-zero
      // exit, so any value >0 re-runs the whole ~42 min backoff for no benefit
      // and writes a second audit row (skewing run counts). The twice-weekly
      // schedule is the retry cadence.
      replicaRetryLimit: 0
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'mongo-uri', value: mongoUri }
        { name: 'okta-api-token', value: oktaApiToken }
      ]
      // Pull the image from this env's ACR using the Job's own managed identity
      // (granted AcrPull below) — no admin creds on the registry.
      registries: [
        {
          server: acr.properties.loginServer
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'cgfe-okta-sync'
          image: jobsImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          command: ['python']
          args: ['sync_okta_attribution.py']
          env: [
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'MONGO_URI', secretRef: 'mongo-uri' }
            { name: 'OKTA_ORG_URL', value: oktaOrgUrl }
            { name: 'OKTA_API_TOKEN', secretRef: 'okta-api-token' }
          ]
        }
      ]
    }
  }
}

// The Job's identity pulls its image from ACR and reads its secrets from Key
// Vault — both granted here. This module only deploys when deployJobs=true, so
// these assignments are inherently conditional on the Job existing.
resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, oktaSyncJob.id, acrPullRole.id)
  properties: {
    roleDefinitionId: acrPullRole.id
    principalId: oktaSyncJob.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
resource kvSecretsAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, oktaSyncJob.id, kvSecretsUserRole.id)
  properties: {
    roleDefinitionId: kvSecretsUserRole.id
    principalId: oktaSyncJob.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output principalId string = oktaSyncJob.identity.principalId
output jobName string = oktaSyncJob.name
