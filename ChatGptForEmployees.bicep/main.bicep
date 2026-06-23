param appName string = 'ChatGptForEmployees'
param location string = 'eastus'
param subId string = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'

@allowed(['Dev', 'Test', 'Prod'])
param environmentName string = 'Dev'

@allowed(['rg-dev-shared', 'rg-test-shared', 'rg-prod-shared'])
param rgName string = 'rg-dev-shared'

param liteLlmImage string = 'ghcr.io/berriai/litellm:main-v1.57.4'
param libreChatImage string = 'ghcr.io/danny-avila/librechat:v0.7.5'
param ragApiImage string = 'ghcr.io/danny-avila/rag_api:main'

param flagshipModelName string = 'gpt-4o'
param fastModelName string = 'gpt-4o-mini'
param embeddingsModelName string = 'text-embedding-3-small'

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
param ragApiJwtSecret string
@secure()
param mongoConnectionString string

var workspaceName = 'cdb-workspace-${toLower(environmentName)}'
var minReplicas = environmentName == 'Prod' ? 1 : 0

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
    fastModelName: fastModelName
    embeddingsModelName: embeddingsModelName
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
    ragApiJwtSecret: ragApiJwtSecret
  }
}

module libreChat 'libreChat.bicep' = {
  name: 'libreChat'
  params: {
    envName: environmentName
    location: location
    environmentId: containerAppsEnvironment.outputs.environmentId
    libreChatImage: libreChatImage
    minReplicas: minReplicas
    appInsightsConnectionString: applicationInsights.outputs.appiConnString
    liteLlmInternalUrl: liteLlm.outputs.fqdn
    ragApiInternalUrl: ragApi.outputs.fqdn
    mongoConnectionString: mongoConnectionString
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
