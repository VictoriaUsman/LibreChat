// ─────────────────────────────────────────────────────────────────────────────────────
// There used to be a DEPLOY_TRIGGER counter here, bumped by hand so that a digest-only change
// would touch a `.bicep` file and force the deploy to run. **It was based on a wrong diagnosis
// and it did not work** — removed 2026-08-05 along with the real fix, in the pipelines.
//
// The gate is `DetectBicepChanges` (`ROMTech/PipelineTemplates`,
// `insert-stage-detect-folder-changes.yml`). It is folder-based, not file-type-based: it runs
// the deploy when any changed path falls under `ChatGptForEmployees.bicep/`, which includes the
// `.bicepparam` files. So a digest bump always qualified, and the counter was never the thing
// making deploys work.
//
// What actually skipped the deploy is the *baseline* it diffs against: the last successful run
// of the pipeline definition on ANY ref. A PR validation build — which builds the PR's merge
// commit, already containing the change — becomes that baseline, so the real merge to `dev`
// diffs against a commit that already had everything and sees nothing to do.
//
// Fixed by passing `bicepDetectFolder: ''` from `dev.yml` / `test.yml` / `prod.yml`, which takes
// the detect template's documented "no folder resolved → run the stage" path. See the note in
// `dev.yml` and `LibreChat_Image_Deployments.md` §5. Nothing to bump here any more.
// ─────────────────────────────────────────────────────────────────────────────────────
param appName string = 'ChatGptForEmployees'
param location string = 'eastus'
param subId string = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'

@allowed(['Dev', 'Test', 'Prod'])
param environmentName string = 'Dev'

@allowed(['rg-dev-shared', 'rg-test-shared', 'rg-prod-shared'])
param rgName string = 'rg-dev-shared'

param liteLlmImage string = 'ghcr.io/berriai/litellm:main-v1.57.4'
// v0.7.5 was a stale placeholder carried from the deployment template's
// example tag, not a deliberate choice -- it predates the v0.8.0 config
// schema, so Phase 0's summarization/customWelcome keys (config/librechat.yaml)
// were silently dropped on it. Bumped to the stable v0.8.6 release (shipped
// 2026-06-01, PBI: Pin LibreChat to Stable v0.8.6 Across All Environments)
// per the "pin to stable tag when v0.8.6 is released" plan in
// Phase_0_Findings_v1_Recommendation.md. Deploy to Dev/Test and smoke test
// (Okta login, send/stream chat, model picker, existing conversations, file
// upload) before promoting to Prod -- see Erik_recommendation.md Section 6.5.
// Rollback: revert this pin to v0.7.5 and redeploy; note this silently
// re-disables the v0.8.x-only config keys above, which is expected/known.
param libreChatImage string = 'ghcr.io/danny-avila/librechat:v0.8.6'
param ragApiImage string = 'ghcr.io/danny-avila/rag_api:main'

// The scheduled-jobs image lives in a per-env ACR (acr.bicep -> `acrcgfe<env>`);
// the deploy pipeline builds + pushes it, and jobs.bicep derives the mutable
// `:latest` tag ref from the registry and pulls it via the Job's admin
// credentials by default -- no jobsImage param is needed for normal deploys.
//
// jobsImageDigest (LiteLLM v1.99.0 review, third working-changes follow-up,
// Finding 2): optional pin to an exact `sha256:...` manifest digest, recorded
// by dev.yml's BuildJobsImage stage for the reviewed commit. Leave empty for
// ordinary deploys (jobs.bicep falls back to `:latest`). Set it in the env
// bicepparam ONLY when redeploying jobs.bicep to pin the scheduled-jobs image
// to a specific verified build before REVIEW-AND-CUTOVER.md Step 8d's
// synthetic check -- see that step for the required verification before use.
// Reset it to '' in a follow-up commit once the window closes: left set, the
// scheduled jobs stay frozen on that build and ignore every later image push
// (see jobs.bicep's param comment for why this is a separate commit).
param jobsImageDigest string = ''

param oktaOrgUrl string = 'https://romtech.okta.com'

// Gate for the Okta department-sync ACA Job. Kept FALSE until Ops has (a) built
// & pushed the jobs image to a registry and (b) created the
// ChatGptForEmployees<Env>-OktaApiToken Key Vault secret (see the Ops addendum,
// Ops_Requests_for_Launch.md). While false, the `jobs` module is not deployed,
// so the <registry> placeholder image and the (not-yet-created) Okta secret
// cannot fail the deployment. Flip to true in the env bicepparam once both are
// ready (see that file for the full enable steps).
param deployJobs bool = false

// Recipients for scheduled-job failure alerts (jobAlerts.bicep). Azure Monitor
// emails them natively — no app SMTP, no Ops. Leave [] to skip alert deployment;
// set it in the env bicepparam (inboxes/DLs we own) to turn alerting on.
param alertEmailAddresses array = []

param flagshipModelName string = 'gpt-5'
param flagshipModelVersion string = '2025-08-07'
param fastModelName string = 'gpt-5-mini'
param fastModelVersion string = '2025-08-07'
param embeddingsModelName string = 'text-embedding-3-small'
param embeddingsModelVersion string = '1'
// Read-aloud TTS. gpt-4o-mini-tts is the only TTS model available in our Azure OpenAI
// resource; see aiFoundry.bicep for why this version tracks the AI Foundry default.
param ttsModelName string = 'gpt-4o-mini-tts'
param ttsModelVersion string = '2025-12-15'

// capacity = TPM / 1000 (GlobalStandard). Quota in eastus2 is SHARED across all
// three envs: gpt-5 / gpt-5-mini / gpt-5.1 each have a 1M-TPM pool (fully consumed);
// gpt-5.4-mini and embeddings have 3M. Prod-heavy for launch — Prod takes ~all of
// each 1M pool (950K); dev + test sit at a 25K floor (950+25+25 = 1,000 = the quota).
// Prior WIP layout was test-heavy (Test=875, Prod=100), a load-testing artifact.
// ⚠️ DEPLOY ORDER: Test (875K -> 25K) MUST deploy BEFORE Prod (100K -> 950K), or the
// prod deploy transiently needs 950+875+25 = 1.85M and FAILS the 1M gpt-5 quota. The
// normal dev -> test -> prod promotion satisfies this; never deploy prod first.
var flagshipCapacity = environmentName == 'Prod' ? 950 : 25
var flagshipBackupCapacity = environmentName == 'Prod' ? 950 : 25
var fastCapacity = environmentName == 'Prod' ? 950 : 25
var fastBackupCapacity = environmentName == 'Prod' ? 950 : 25
// Embeddings (text-embedding-3-small) sit on a 3M quota (~1.6M free), so Prod can be
// raised independently — no deploy-order constraint, unlike the 1M-quota chat models.
// Prod=500K for launch-day file-upload / RAG-ingestion headroom; dev/test stay 120K.
var embeddingsCapacity = environmentName == 'Prod' ? 500 : 120
// gpt-4o-mini-tts sits on its own quota pool, independent of the chat and embeddings
// models, so there is no deploy-order constraint here either. Read-aloud is opt-in per
// message and the audio-token volume is tiny next to chat: a ~1-minute reply is ~1.5K
// audio tokens, so even a heavy 20K-read-alouds/month Prod month averages under 3K
// tokens/min across a working day. Prod=100K TPM leaves ~35x headroom for bursts;
// dev/test sit at 25K, matching the nonprod floor used above.
var ttsCapacity = environmentName == 'Prod' ? 100 : 25

// Backup models — LiteLLM falls back to these on 429 or transient error.
// Versions verified in AI Foundry model catalog.
param flagshipBackupModelName string = 'gpt-5.1'
param flagshipBackupModelVersion string = '2025-11-13'
param fastBackupModelName string = 'gpt-5.4-mini'
param fastBackupModelVersion string = '2026-03-17'

param postgresAdminUser string = 'cgfeadmin'
@secure()
param postgresAdminPassword string

@secure()
param liteLlmMasterKey string
@secure()
param jwtSecret string
@secure()
param jwtRefreshSecret string
@secure()
param credsKey string
@secure()
param credsIv string
@secure()
param liteLlmVirtualKey string
@secure()
param openIdClientId string
@secure()
param openIdClientSecret string
@secure()
param openIdSessionSecret string
@secure()
// Defaulted empty so the deployment doesn't require it when deployJobs=false
// (the env bicepparam supplies the real Key Vault value only when enabling the job).
param oktaApiToken string = ''

// Maintenance-state enforcement (LiteLLM v1.99.0 review, Follow-up 1 P1: "preserve
// maintenance isolation throughout deployment"; corrected per the `89c57d0`
// working-changes follow-up, Finding 2, to independently-meaningful states
// instead of one true/false; extended again per the second working-changes
// follow-up, Finding 1: "validate LibreChat before releasing users and jobs").
// Threaded through to liteLlm.bicep, libreChat.bicep, and jobs.bicep,
// overriding whatever scale/cron/ingress values this file would otherwise
// compute/declare below:
//   'off'          -- normal operation (default).
//   'paused'       -- LiteLLM, LibreChat, and both jobs all forced down/paused.
//                     Used while the database migration itself runs.
//   'litellm-only' -- LiteLLM brought back to normal scale for controlled,
//                     internal-only synthetic checks (via the manually-
//                     triggered job-cgfe-synth-check-<env>); LibreChat and
//                     both jobs stay paused, so no ordinary employee traffic
//                     can reach LiteLLM yet (LibreChat is the only realistic
//                     path to it).
//   'validation'   -- LibreChat ALSO brought to normal scale, but restricted
//                     to `maintenanceTesterIpRanges` only via its ingress
//                     `ipSecurityRestrictions`; both jobs stay paused. Lets an
//                     authorized tester run the full application (Okta login,
//                     streaming, model picker, conversations, upload) before
//                     ordinary employees are let in.
// See REVIEW-AND-CUTOVER.md, "Maintenance-mode enforcement" (§8.1, as
// corrected), for the full enter/verify/release sequence: 'off' -> 'paused'
// (enter, together with the reviewed target image/config) -> run the
// migration -> 'litellm-only' (verify LiteLLM directly) -> 'validation'
// (authorized-tester application checks) -> 'off' (release LibreChat + jobs
// to everyone), each a separate commit.
@allowed(['off', 'paused', 'litellm-only', 'validation'])
param maintenanceState string = 'off'
// CIDR ranges allowed through LibreChat's ingress while maintenanceState ==
// 'validation' -- see libreChat.bicep's own param comment for the fail-closed
// behavior when this is left empty. Supplied by the env bicepparam only for
// the specific maintenance window, then removed.
param maintenanceTesterIpRanges array = []

var workspaceName = 'cdb-workspace-${toLower(environmentName)}'

// ─── Container App sizing ────────────────────────────────────────────────────────────
// Prod is sized for the company-wide rollout; dev and test stay at the smallest useful
// footprint. Before this, all three services ran 0.5 vCPU / 1 GiB, min 1 / max 2 in EVERY
// environment with no scale rule, so prod inherited a dev-sized app tier: 2 replicas
// totalling 1 vCPU per service, with no way to add capacity under load, while the Azure
// OpenAI deployments below are provisioned for ~950K TPM. Compute was the bottleneck, not
// tokens.
//
// Note what the old ceiling did NOT do: `concurrentRequests` is a scale-out TRIGGER, not
// admission control. The implicit default of 10 never rejected or queued an 11th request —
// it asked for another replica, which maxReplicas: 2 then refused. So the old tier accepted
// everything sent to it and let it contend for 1 vCPU. The symptom was latency collapse
// under load, not refused connections.
//
// ⚠️ cpu and memory MUST stay in ACA's 1:2 vCPU:GiB ratio (0.5/1Gi, 1/2Gi, 1.5/3Gi, 2/4Gi).
// The valid-combination list is closed, so a mismatched pair fails the deployment; they are
// kept in one object here rather than as two values that can drift apart. Our ceiling is
// 2 vCPU / 4 GiB, NOT the 4/8Gi you'll see quoted for the Consumption workload profile:
// containerAppsEnvironment.bicep declares no `workloadProfiles`, which makes this a
// Consumption-ONLY environment, and those cap at 2 cores / 4Gi per app.
var isProd = environmentName == 'Prod'
var containerSize = isProd ? { cpu: '1.0', memory: '2Gi' } : { cpu: '0.5', memory: '1Gi' }

// LiteLLM is sized separately from the other two apps, and always at 1.0/2Gi.
//
// LiteLLM v1.99.0 does not fit in 1Gi. Measured against the pinned digest: it idles at
// ~782Mi with no database configured at all, and ~960Mi once DATABASE_URL is set and the
// Prisma query engine is resident. At a 1Gi limit it is OOM-killed (exit 137) during
// startup, before it ever binds :4000.
//
// That failure is near-invisible, so it is worth knowing the shape of it: the kill is a
// SIGKILL, which never flushes Python's block-buffered stdout, so the container produces
// ZERO log lines — and because the app runs in ACA's Single revision mode, traffic stays
// on the last revision that became ready. The previous version keeps serving and every
// functional test passes against it while the new revision quietly crash-loops. This is
// exactly what happened on dev during the v1.99.0 cutover on 2026-09-17.
//
// LibreChat (~348Mi) and RAG API (~251Mi) measured in dev have ample room at 0.5/1Gi and
// deliberately keep using containerSize above; there is no reason to pay for headroom they
// do not use. ACA's vCPU:GiB ratio is a closed list, so 2Gi cannot be taken without also
// taking 1.0 vCPU — the pair is kept in one object here for the same reason as above.
// In Prod this is identical to containerSize; it differs only for Dev and Test.
var liteLlmSize = { cpu: '1.0', memory: '2Gi' }

// min is the always-on floor and is billed continuously; max is a ceiling that only costs
// while it is actually in use. LibreChat and LiteLLM floor at 2 in prod so a rolling revision
// swap never leaves one replica serving alone. RAG API is deliberately left at 1: it is not on
// every turn (only File Search upload and retrieval), and losing it briefly degrades one
// feature rather than stopping chat. Raise it to 2 if File Search becomes load-bearing.
//
// `concurrency` is the per-replica in-flight request count that triggers a scale-out, measured
// over a 15-second window. It is tuned per service:
//   LibreChat — Node relays streams on an event loop, but the same container also serves the
//     SPA and handles uploads, and 2 GiB is near Node's default old-space ceiling. 15 is a
//     trusted number at 1 vCPU; 20+ was optimistic.
//   LiteLLM  — must be AT OR BELOW LibreChat's, never above: every chat turn becomes a LiteLLM
//     request, so a higher threshold here means the downstream service scales out later than
//     the one feeding it. It also runs a SINGLE uvicorn worker (no --num_workers in its args),
//     so all of it is one GIL-bound process that parses SSE, counts tokens, prices each chunk
//     from model_info, and writes a spend row per request. It queues on CPU well before a high
//     threshold would trip. Raise this only together with --num_workers.
//   RAG API  — most conservative, and the heavy part is document parsing/chunking on upload,
//     where 2 GiB is the binding constraint. Embedding calls themselves are remote (Azure
//     OpenAI), so they are I/O waits rather than local compute.
var libreChatScale = { min: isProd ? 2 : 1, max: isProd ? 10 : 2, concurrency: 15 }
var liteLlmScale   = { min: isProd ? 2 : 1, max: isProd ? 10 : 2, concurrency: 12 }
var ragApiScale    = { min: 1,              max: isProd ? 5 : 2,  concurrency: 10 }
// ─────────────────────────────────────────────────────────────────────────────────────

module applicationInsights 'applicationInsights.bicep' = {
  name: 'applicationInsights'
  params: {
    appName: appName
    envName: environmentName
    location: location
    rgName: rgName
    subId: subId
    workspaceName: workspaceName
  }
}

module storage 'storage.bicep' = {
  name: 'storage'
  params: {
    envName: environmentName
    location: location
  }
}

module containerAppsEnvironment 'containerAppsEnvironment.bicep' = {
  name: 'containerAppsEnvironment'
  params: {
    envName: environmentName
    location: location
    logAnalyticsWorkspaceName: workspaceName
    logAnalyticsResourceGroup: rgName
    storageAccountName: storage.outputs.storageAccountName
    storageAccountKey: storage.outputs.storageAccountKey
    liteLlmShareName: storage.outputs.liteLlmShareName
    libreChatShareName: storage.outputs.libreChatShareName
  }
}

module aiFoundry 'aiFoundry.bicep' = {
  name: 'aiFoundry'
  params: {
    appName: appName
    envName: environmentName
    location: location
    flagshipModelName: flagshipModelName
    flagshipModelVersion: flagshipModelVersion
    fastModelName: fastModelName
    fastModelVersion: fastModelVersion
    embeddingsModelName: embeddingsModelName
    embeddingsModelVersion: embeddingsModelVersion
    flagshipCapacity: flagshipCapacity
    flagshipBackupModelName: flagshipBackupModelName
    flagshipBackupModelVersion: flagshipBackupModelVersion
    flagshipBackupCapacity: flagshipBackupCapacity
    fastCapacity: fastCapacity
    fastBackupModelName: fastBackupModelName
    fastBackupModelVersion: fastBackupModelVersion
    fastBackupCapacity: fastBackupCapacity
    embeddingsCapacity: embeddingsCapacity
    ttsModelName: ttsModelName
    ttsModelVersion: ttsModelVersion
    ttsCapacity: ttsCapacity
  }
}

module cosmosDb 'cosmosDb.bicep' = {
  name: 'cosmosDb'
  params: {
    envName: environmentName
    location: location
  }
}

module postgresql 'postgresql.bicep' = {
  name: 'postgresql'
  params: {
    envName: environmentName
    location: location
    adminUser: postgresAdminUser
    adminPassword: postgresAdminPassword
  }
}

module liteLlm 'liteLlm.bicep' = {
  name: 'liteLlm'
  params: {
    envName: environmentName
    location: location
    environmentId: containerAppsEnvironment.outputs.environmentId
    liteLlmImage: liteLlmImage
    minReplicas: liteLlmScale.min
    maxReplicas: liteLlmScale.max
    concurrentRequests: liteLlmScale.concurrency
    containerCpu: liteLlmSize.cpu
    containerMemory: liteLlmSize.memory
    appInsightsConnectionString: applicationInsights.outputs.appiConnString
    azureOpenAiEndpoint: aiFoundry.outputs.endpoint
    azureOpenAiApiKey: aiFoundry.outputs.apiKey
    liteLlmMasterKey: liteLlmMasterKey
    databaseUrl: postgresql.outputs.liteLlmConnectionString
    maintenanceState: maintenanceState
  }
}

// ACR for the scheduled-jobs image — deployed always (the pipeline pushes to it
// even while the Job itself stays gated off via deployJobs).
module acr 'acr.bicep' = {
  name: 'acr'
  params: {
    envName: environmentName
    location: location
  }
}

module jobs 'jobs.bicep' = if (deployJobs) {
  name: 'jobs'
  params: {
    envName: environmentName
    location: location
    environmentId: containerAppsEnvironment.outputs.environmentId
    acrName: acr.outputs.name
    jobsImageDigest: jobsImageDigest
    oktaOrgUrl: oktaOrgUrl
    oktaApiToken: oktaApiToken
    databaseUrl: postgresql.outputs.liteLlmConnectionString
    mongoUri: cosmosDb.outputs.connectionString
    // Nightly cleanup job inputs
    storageConnectionString: storage.outputs.blobConnectionString
    blobContainerName: storage.outputs.blobContainerName
    postgresHost: postgresql.outputs.hostname
    postgresUser: postgresql.outputs.adminUser
    postgresPassword: postgresql.outputs.adminPassword
    maintenanceState: maintenanceState
    // Synthetic LiteLLM check job inputs (second working-changes follow-up,
    // Finding 2) -- liteLlm.outputs.fqdn is this environment's internal FQDN
    // for ca-litellm-<env> (ingress external: false), reachable from any app
    // (including this job) inside the same Container Apps environment.
    liteLlmInternalUrl: liteLlm.outputs.fqdn
    liteLlmMasterKey: liteLlmMasterKey
  }
}

// Failure alerting for the scheduled jobs (WI 12341). Deploys only when the jobs
// are on AND an alert recipient is set (Azure Monitor emails it natively — no app
// SMTP, no Ops). Set alertEmailAddress in the env bicepparam to enable.
module jobAlerts 'jobAlerts.bicep' = if (deployJobs && !empty(alertEmailAddresses)) {
  name: 'jobAlerts'
  params: {
    envName: environmentName
    location: location
    workspaceName: workspaceName
    alertEmailAddresses: alertEmailAddresses
  }
}

module ragApi 'ragApi.bicep' = {
  name: 'ragApi'
  params: {
    envName: environmentName
    location: location
    environmentId: containerAppsEnvironment.outputs.environmentId
    ragApiImage: ragApiImage
    minReplicas: ragApiScale.min
    maxReplicas: ragApiScale.max
    concurrentRequests: ragApiScale.concurrency
    containerCpu: containerSize.cpu
    containerMemory: containerSize.memory
    azureOpenAiEndpoint: aiFoundry.outputs.endpoint
    azureOpenAiApiKey: aiFoundry.outputs.apiKey
    embeddingsDeploymentName: aiFoundry.outputs.embeddingsDeploymentName
    databaseUrl: postgresql.outputs.ragApiConnectionString
    postgresHost: postgresql.outputs.hostname
    postgresUser: postgresql.outputs.adminUser
    postgresPassword: postgresql.outputs.adminPassword
    jwtSecret: jwtSecret
  }
}

// Azure Static Web App (Free) hosting the user Help/FAQ page. bicep creates the empty
// site; the pipeline's DeployHelpPage stage pushes the HTML (SWA deploy token + CLI).
// Its URL is wired into LibreChat below (helpUrl). See staticSite.bicep.
module staticSite 'staticSite.bicep' = {
  name: 'staticSite'
  params: {
    envName: environmentName
    location: 'eastus2' // SWA control-plane region (independent of the general location)
  }
}

module libreChat 'libreChat.bicep' = {
  name: 'libreChat'
  params: {
    envName: environmentName
    location: location
    environmentId: containerAppsEnvironment.outputs.environmentId
    defaultDomain: containerAppsEnvironment.outputs.defaultDomain
    libreChatImage: libreChatImage
    acrName: acr.outputs.name
    minReplicas: libreChatScale.min
    maxReplicas: libreChatScale.max
    concurrentRequests: libreChatScale.concurrency
    containerCpu: containerSize.cpu
    containerMemory: containerSize.memory
    maintenanceState: maintenanceState
    maintenanceTesterIpRanges: maintenanceTesterIpRanges
    appInsightsConnectionString: applicationInsights.outputs.appiConnString
    liteLlmInternalUrl: liteLlm.outputs.fqdn
    ragApiInternalUrl: ragApi.outputs.fqdn
    mongoConnectionString: cosmosDb.outputs.connectionString
    jwtSecret: jwtSecret
    jwtRefreshSecret: jwtRefreshSecret
    credsKey: credsKey
    credsIv: credsIv
    liteLlmVirtualKey: liteLlmVirtualKey
    openIdClientId: openIdClientId
    openIdClientSecret: openIdClientSecret
    openIdSessionSecret: openIdSessionSecret
    storageConnectionString: storage.outputs.blobConnectionString
    blobContainerName: storage.outputs.blobContainerName
    helpUrl: staticSite.outputs.defaultHostname
    // romtech-tts is a deployment on the same Foundry account as the chat and
    // embeddings deployments, and Azure OpenAI keys are account-scoped rather than
    // deployment-scoped. A separate Key Vault secret would hold a byte-identical copy
    // of this key, so it buys no isolation and would break read-aloud silently on
    // rotation. Same source liteLlm and ragApi use.
    ttsApiKey: aiFoundry.outputs.apiKey
    ttsInstanceName: aiFoundry.outputs.accountName
    ttsDeploymentName: aiFoundry.outputs.ttsDeploymentName
  }
}

module keyvault 'keyvault.bicep' = {
  name: 'keyvault'
  params: {
    environmentName: environmentName
    liteLlmPrincipalId: liteLlm.outputs.principalId
    libreChatPrincipalId: libreChat.outputs.principalId
    ragApiPrincipalId: ragApi.outputs.principalId
  }
}

output libreChatUrl string = 'https://${libreChat.outputs.fqdn}'
output liteLlmInternalUrl string = liteLlm.outputs.fqdn
output ragApiInternalUrl string = ragApi.outputs.fqdn
output helpPageUrl string = 'https://${staticSite.outputs.defaultHostname}'
output staticSiteName string = staticSite.outputs.name
