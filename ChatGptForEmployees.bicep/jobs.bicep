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
// Optional pin to an exact manifest digest (LiteLLM v1.99.0 review, third
// working-changes follow-up, Finding 2). Empty (default) keeps the existing
// mutable `:latest` tag; set to a `sha256:...` digest recorded by dev.yml's
// BuildJobsImage stage to pin all three jobs below to that exact verified
// build -- see main.bicep's jobsImageDigest comment and
// REVIEW-AND-CUTOVER.md Step 8d for when/how this must be set.
param jobsImageDigest string = ''
param oktaOrgUrl string
// Maintenance-state enforcement (LiteLLM v1.99.0 review, Follow-up 1 P1;
// corrected per the `89c57d0` working-changes follow-up, Finding 2, and
// extended again per the second working-changes follow-up, Finding 1). Both
// jobs' cron expressions are forced to a never-fire sentinel in EVERY
// non-'off' state ('paused', 'litellm-only', or 'validation') -- jobs stay
// paused through the entire controlled-startup window, including while
// 'litellm-only' brings LiteLLM up and while 'validation' brings LibreChat up
// for authorized-tester application checks, and only resume in 'off', strictly
// after those checks pass (REVIEW-AND-CUTOVER.md §2a Steps 8d/8e, then §7's
// resume). This is deliberately independent of deployJobs: leaving
// deployJobs=true and using maintenanceState to neuter the trigger keeps the
// jobs' image/role-assignment/secret configuration current through the
// window, rather than removing the jobs outright (deployJobs=false alone does
// not stop an already-deployed job's existing schedule). Az CLI-level pause
// (`az containerapp job update --cron-expression`, §7) remains the immediate,
// out-of-band fallback when no Bicep deploy is in flight; this parameter is
// what keeps a concurrent or subsequent Bicep deploy from clobbering that
// pause. Shared with liteLlm.bicep and libreChat.bicep so all three modules
// read the same value from main.bicep.
@allowed(['off', 'paused', 'litellm-only', 'validation'])
param maintenanceState string = 'off'

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

// --- Synthetic LiteLLM check job inputs (05-synthetic-litellm-check.py) ---
// Manually-triggered (not scheduled) job that gives the runbook's Step 8d
// ("make the internal synthetic test executable", second working-changes
// follow-up, Finding 2) a concrete, prepared execution location that can
// resolve LiteLLM's internal FQDN -- this job runs inside the same Container
// Apps environment as ca-litellm-<env>, so `http://<liteLlmInternalUrl>` is
// reachable the same way any other app in this environment reaches it,
// without depending on exec-ing into a stopped/paused container.
param liteLlmInternalUrl string
@secure()
param liteLlmMasterKey string
// Must match a model_name actually declared in litellm_routing_config.yaml.
// "ROMTech AI Fast" is the lighter/cheaper of the two user-facing models.
param synthTestModelName string = 'ROMTech AI Fast'

var jobName = 'job-cgfe-okta-sync-${toLower(envName)}'
var cleanupJobName = 'job-cgfe-cleanup-${toLower(envName)}'
var synthCheckJobName = 'job-cgfe-synth-check-${toLower(envName)}'

// "00:00 on February 31st" -- no standard 5-field cron scheduler ever matches a
// day that doesn't exist, so this stops a job firing without deleting or
// disabling its trigger configuration outright. Same sentinel documented as the
// az-CLI-level pause command in REVIEW-AND-CUTOVER.md §7; declaring it here too
// means a non-'off' Bicep deploy can't reintroduce the real schedule mid-window
// even if it runs after (or instead of) that manual CLI pause.
var maintenanceNeverFireCron = '0 0 31 2 *'
var oktaSyncCron = maintenanceState == 'off' ? '0 5 * * 2,5' : maintenanceNeverFireCron
var cleanupCron = maintenanceState == 'off' ? '0 2 * * *' : maintenanceNeverFireCron

// Image is built + pushed to this env's ACR by the deploy pipeline (az acr build);
// we read the registry's admin credentials here (deploy-time) to pull it.
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}
// Digest-pinned ref (`@sha256:...`) when jobsImageDigest is set, else the
// mutable `:latest` tag -- see the jobsImageDigest param comment above.
var jobsImage = empty(jobsImageDigest)
  ? '${acr.properties.loginServer}/librechat-cleanup:latest'
  : '${acr.properties.loginServer}/librechat-cleanup@${jobsImageDigest}'

resource oktaSyncJob 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  properties: {
    environmentId: environmentId
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: {
        cronExpression: oktaSyncCron // 05:00 UTC Tue & Fri = midnight ET winter / 1am ET summer, unless maintenanceMode forces the never-fire sentinel
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
        cronExpression: cleanupCron // 02:00 UTC nightly (matches config/cleanup-job.yaml), unless maintenanceMode forces the never-fire sentinel
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

// Manually-triggered synthetic LiteLLM check (05-synthetic-litellm-check.py --
// second working-changes follow-up, Finding 2). `triggerType: 'Manual'`, not
// 'Schedule': this job never fires on its own; the operator starts it
// on-demand during Step 8d with `az containerapp job start -n
// job-cgfe-synth-check-<env> -g <resource-group>`. Same image + admin-creds
// ACR pull pattern as the two scheduled jobs above.
resource synthCheckJob 'Microsoft.App/jobs@2024-03-01' = {
  name: synthCheckJobName
  location: location
  properties: {
    environmentId: environmentId
    configuration: {
      triggerType: 'Manual'
      manualTriggerConfig: {
        replicaCompletionCount: 1
        parallelism: 1
      }
      // Bounded: health checks + one synthetic completion + a short poll for
      // the async spend-log writer (see the script's own SYNTH_CHECK_MAX_WAIT_
      // SECONDS, default 30s) -- 120s leaves generous headroom without letting
      // a hung request block the maintenance window indefinitely.
      replicaTimeout: 120
      // The script owns its own bounded waits/timeouts and always exits
      // explicitly; an ACA-level retry on a genuine failure (e.g. unexpectedly
      // populated content) would silently re-run a check whose result the
      // operator needs to see and act on, not retry away.
      replicaRetryLimit: 0
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'litellm-master-key', value: liteLlmMasterKey }
        // ACR admin password, read from the registry at deploy time (no Key Vault,
        // no Ops — the deploy SP is allowed to read a registry's own credentials).
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
          name: 'cgfe-synth-check'
          image: jobsImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          command: ['python']
          args: ['05-synthetic-litellm-check.py']
          env: [
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'LITELLM_MASTER_KEY', secretRef: 'litellm-master-key' }
            { name: 'LITELLM_INTERNAL_URL', value: 'http://${liteLlmInternalUrl}' }
            { name: 'SYNTHETIC_TEST_MODEL', value: synthTestModelName }
          ]
        }
      ]
    }
  }
}

output jobName string = oktaSyncJob.name
output cleanupJobName string = cleanupJob.name
output synthCheckJobName string = synthCheckJob.name
