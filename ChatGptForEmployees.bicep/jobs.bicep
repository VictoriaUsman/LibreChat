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
