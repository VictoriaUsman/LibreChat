// Twice-weekly ACA Job running sync_okta_attribution.py (WI 11553's script,
// scheduled per "Schedule the Department-Sync Script as a Twice-Weekly ACA
// Job"). Modeled on liteLlm.bicep's identity/secrets/env conventions.
//
// IMAGE PULL — admin credentials, NOT a managed-identity AcrPull role.
// The deploy pipeline (`az acr build`) builds + pushes the image to this env's
// ACR (acr.bicep). The Job authenticates to the registry with the ACR's ADMIN
// credentials, read from the registry at deploy time and injected as a Job secret.
// Why not identity + AcrPull: the deploy service principal can create/manage the
// registry but is NOT permitted to write role assignments on it
// (Microsoft.Authorization/roleAssignments/write), so an identity pull can't be
// provisioned without an Ops grant. TO HARDEN LATER: have Ops grant the deploy SP
// "User Access Administrator" on the ACR, then switch `registries` back to
// identity: 'system' + an AcrPull role assignment.
//
// SECRETS — no Key Vault role needed. DB / Mongo / Okta-token values are resolved
// from Key Vault at DEPLOY time (getSecret in the bicepparam) and passed by value,
// so the Job never reads Key Vault at runtime.
//
// Remaining external dependency:
//   - Wire an Azure Monitor alert on Job execution failure (needs the alert
//     destination from Ops).

param envName string = 'Dev'
param location string = 'eastus'
param environmentId string
param acrName string
param oktaOrgUrl string

@secure()
param oktaApiToken string
@secure()
param databaseUrl string
@secure()
param mongoUri string

var jobName = 'job-cgfe-okta-sync-${toLower(envName)}'

// Image is built + pushed to this env's ACR by the deploy pipeline (az acr build);
// we read the registry's admin credentials here (deploy-time) to pull it.
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}
var jobsImage = '${acr.properties.loginServer}/librechat-cleanup:latest'

resource oktaSyncJob 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  properties: {
    environmentId: environmentId
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: {
        cronExpression: '0 5 * * 2,5' // 05:00 UTC Tue & Fri = midnight ET winter / 1am ET summer
        parallelism: 1
        replicaCompletionCount: 1
      }
      // 50 min: the two sources (Okta, Mongo) are fetched SEQUENTIALLY, each with
      // its own ~21 min worst-case retry backoff, so a both-sources-down run needs
      // ~42 min of sleeps plus fetch/sync/audit. Must exceed that so the replica
      // isn't killed BEFORE it writes the status='failed' sync_run_log audit row.
      replicaTimeout: 3000
      // 0: the script owns retries and exits non-zero only AFTER writing a
      // status='failed' row; ACA retrying on any non-zero exit would re-run the
      // whole ~42 min backoff for no benefit. The twice-weekly schedule is the
      // retry cadence.
      replicaRetryLimit: 0
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'mongo-uri', value: mongoUri }
        { name: 'okta-api-token', value: oktaApiToken }
        // ACR admin password, read from the registry at deploy time (no Key Vault,
        // no Ops — the deploy SP is allowed to read a registry's own credentials).
        { name: 'acr-password', value: acr.listCredentials().passwords[0].value }
      ]
      // Pull from the ACR using its admin credentials (see module header).
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
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

output jobName string = oktaSyncJob.name
