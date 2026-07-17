// Twice-weekly ACA Job running sync_okta_attribution.py (WI 11553's script,
// scheduled per "Schedule the Department-Sync Script as a Twice-Weekly ACA
// Job"). First Microsoft.App/jobs resource in this repo -- modeled on the
// shape of config/cleanup-job.yaml (that job has no bicep of its own yet)
// and on liteLlm.bicep's identity/secrets/env conventions.
//
// Ops dependencies (NOT done by this module -- explicitly out of scope per
// the PBI):
//   - Grant this Job's principalId (see `principalId` output) "Key Vault
//     Secrets User" on kv-romtech-<env>, the same way keyvault.bicep does
//     for liteLlm/libreChat/ragApi.
//   - Confirm this Job's outbound network path reaches the Cosmos Mongo and
//     Postgres endpoints (VNet/firewall config), same as the other apps in
//     this Container Apps environment.
//   - Create the `ChatGptForEmployees<Env>-OktaApiToken` secret in each
//     kv-romtech-<env> Key Vault (see sync_okta_attribution.py's docstring).
//   - Build and push a real image to replace the `jobsImage` placeholder
//     value used in main.<env>.bicepparam.
//   - Wire an Azure Monitor alert on Job execution failure.

param envName string = 'Dev'
param location string = 'eastus'
param environmentId string
param jobsImage string
param oktaOrgUrl string

@secure()
param oktaApiToken string
@secure()
param databaseUrl string
@secure()
param mongoUri string

var jobName = 'job-okta-sync-${toLower(envName)}'

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
      // 30 min: covers the in-script retry path's ~21 min worst-case sleep
      // (3 retries at ~1/4/16 min) plus fetch/sync time. Deliberately larger
      // than the cleanup job's 300s, which has no retry sleep to accommodate.
      replicaTimeout: 1800
      // Infra-level backstop on top of (not instead of) the in-script
      // backoff -- only engages for failures the script itself can't catch
      // (unhandled crash, OOM), matching the cleanup job's replicaRetryLimit.
      replicaRetryLimit: 1
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'mongo-uri', value: mongoUri }
        { name: 'okta-api-token', value: oktaApiToken }
      ]
    }
    template: {
      containers: [
        {
          name: 'okta-sync'
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

output principalId string = oktaSyncJob.identity.principalId
output jobName string = oktaSyncJob.name
