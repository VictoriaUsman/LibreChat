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

param flagshipModelName string = 'gpt-4.1'
param flagshipModelVersion string = '2025-04-14'
param fastModelName string = 'gpt-4.1-mini'
param fastModelVersion string = '2025-04-14'
param embeddingsModelName string = 'text-embedding-3-small'
param embeddingsModelVersion string = '1'

// capacity = throughput (tokens-per-minute rate limit), NOT context window or
// output length — that's maxContextTokens in config/librechat.yaml (PBI-01-FE).
// GlobalStandard capacity units are ~1,000 TPM each for gpt-4.1 in eastus2 at
// time of writing; confirm the exact unit in the target region before relying
// on this for capacity planning, as Azure's per-unit TPM can vary by model/region.
// flagshipCapacity=100 (~100K TPM) supports realistic concurrent load testing
// without hitting artificial 429s (see PBI: Increase Azure OpenAI TPM Capacity
// for Realistic Testing). Raising capacity has a direct cost impact — see PR.
param flagshipCapacity int = 100
param fastCapacity int = 20
param embeddingsCapacity int = 20

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
    fastCapacity: fastCapacity
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

module libreChat 'libreChat.bicep' = {
  name: 'libreChat'
  params: {
    envName: environmentName
    location: location
    environmentId: containerAppsEnvironment.outputs.environmentId
    defaultDomain: containerAppsEnvironment.outputs.defaultDomain
    libreChatImage: libreChatImage
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
