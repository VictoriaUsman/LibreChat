// redeploy trigger (2026-07-21): no-op change to force a fresh pipeline run so the
// Bicep create stage re-applies after the approval gate and actually creates the
// now-enabled job-cgfe-okta-sync-<env>. Safe to remove once the deploy has run.
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
// the deploy pipeline builds + pushes it, and jobs.bicep derives the image ref
// from the registry and pulls it via the Job's managed identity. No jobsImage
// param is needed.
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
var workspaceName = 'cdb-workspace-${toLower(environmentName)}'
var minReplicas = 1

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
    minReplicas: minReplicas
    appInsightsConnectionString: applicationInsights.outputs.appiConnString
    azureOpenAiEndpoint: aiFoundry.outputs.endpoint
    azureOpenAiApiKey: aiFoundry.outputs.apiKey
    liteLlmMasterKey: liteLlmMasterKey
    databaseUrl: postgresql.outputs.liteLlmConnectionString
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
    minReplicas: minReplicas
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
    minReplicas: minReplicas
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
