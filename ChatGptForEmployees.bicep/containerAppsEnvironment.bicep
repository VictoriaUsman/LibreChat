param envName string = 'Dev'
param location string = 'eastus'
param logAnalyticsWorkspaceName string
param logAnalyticsResourceGroup string
param storageAccountName string
@secure()
param storageAccountKey string
param liteLlmShareName string
param libreChatShareName string

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: logAnalyticsWorkspaceName
  scope: resourceGroup(logAnalyticsResourceGroup)
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-cgfe-${toLower(envName)}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

resource liteLlmStorageMount 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: environment
  name: 'litellm-config-store'
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAccountKey
      shareName: liteLlmShareName
      accessMode: 'ReadOnly'
    }
  }
}

resource libreChatStorageMount 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: environment
  name: 'librechat-data-store'
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAccountKey
      shareName: libreChatShareName
      accessMode: 'ReadWrite'
    }
  }
}

output environmentId string = environment.id
output defaultDomain string = environment.properties.defaultDomain
