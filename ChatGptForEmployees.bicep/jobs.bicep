// Scheduled ACA Jobs for this app:
//   - oktaSyncJob  (job-cgfe-okta-sync-<env>) — twice-weekly Okta→Postgres sync
//                  (sync_okta_attribution.py, WI 11553).
//   - cleanupJob   (job-cgfe-cleanup-<env>)   — nightly orphaned-file cleanup
//                  (cleanup_orphaned_files.py, WI 11364/12340). Report-only by
//                  default; see its resource header.
// Both share the same image (ACR) and the admin-creds pull below.
// Failure alerting for these jobs lives in jobAlerts.bicep (WI 12341).
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
// SECRETS — no Key Vault role needed. DB / Mongo / Okta-token / storage values are
// resolved from Key Vault or other module outputs at DEPLOY time and passed by
// value, so the Jobs never read Key Vault at runtime.

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

// --- Nightly cleanup job inputs (cleanup_orphaned_files.py) ---
@secure()
param storageConnectionString string
param blobContainerName string
param postgresHost string
param postgresUser string
@secure()
param postgresPassword string

var jobName = 'job-cgfe-okta-sync-${toLower(envName)}'
var cleanupJobName = 'job-cgfe-cleanup-${toLower(envName)}'

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

// Nightly orphaned-file cleanup (cleanup_orphaned_files.py — the WI 11364
// fail-closed script). Same image + admin-creds ACR pull as the sync job above.
// SAFE BY DEFAULT: CLEANUP_ENFORCE is left unset, so the job runs REPORT-ONLY
// (logs what it would delete, deletes nothing). Going live is a deliberate,
// documented step: seed the canary conversation (seed_canary_conversation.py),
// then set CLEANUP_ENFORCE=true. NOTE: until the canary exists the script
// fail-closes (exit 1) BY DESIGN — seed it before the first scheduled run so the
// nightly cron (and its failure alert) don't fire every night on a missing canary.
resource cleanupJob 'Microsoft.App/jobs@2024-03-01' = {
  name: cleanupJobName
  location: location
  properties: {
    environmentId: environmentId
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: {
        cronExpression: '0 2 * * *' // 02:00 UTC nightly (matches config/cleanup-job.yaml)
        parallelism: 1
        replicaCompletionCount: 1
      }
      // Per config/cleanup-job.yaml. The script is idempotent/re-runnable, so a
      // single retry on a transient failure is safe (unlike the sync job, which
      // owns its own retries). Raise replicaTimeout if prod file volume needs it.
      replicaTimeout: 300
      replicaRetryLimit: 1
      secrets: [
        { name: 'mongo-uri', value: mongoUri }
        { name: 'storage-conn-str', value: storageConnectionString }
        { name: 'rag-db-password', value: postgresPassword }
        // ACR admin password (deploy-time), same as the sync job — see module header.
        { name: 'acr-password', value: acr.listCredentials().passwords[0].value }
      ]
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
          name: 'cgfe-cleanup'
          image: jobsImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          command: ['python']
          args: ['cleanup_orphaned_files.py']
          env: [
            { name: 'MONGO_URI', secretRef: 'mongo-uri' }
            { name: 'AZURE_STORAGE_CONNECTION_STRING', secretRef: 'storage-conn-str' }
            { name: 'AZURE_CONTAINER_NAME', value: blobContainerName }
            { name: 'RAG_DB_HOST', value: postgresHost }
            { name: 'RAG_DB_PORT', value: '5432' }
            { name: 'RAG_DB_NAME', value: 'librechat_rag' }
            { name: 'RAG_DB_USER', value: postgresUser }
            { name: 'RAG_DB_PASSWORD', secretRef: 'rag-db-password' }
            // CLEANUP_ENFORCE intentionally omitted → report-only. See header.
          ]
        }
      ]
    }
  }
}

output jobName string = oktaSyncJob.name
output cleanupJobName string = cleanupJob.name
