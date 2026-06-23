param appName string = 'ChatGptForEmployees'
param envName string = 'Dev'
param location string = 'eastus'
param flagshipModelName string = 'gpt-4o'
param fastModelName string = 'gpt-4o-mini'
param embeddingsModelName string = 'text-embedding-3-small'
param flagshipCapacity int = 30
param fastCapacity int = 100
param embeddingsCapacity int = 120

var accountName = 'ais${toLower(appName)}${toLower(envName)}'

resource aiFoundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    publicNetworkAccess: 'Enabled'
    customSubDomainName: accountName
    allowProjectManagement: true
    networkAcls: {
      defaultAction: 'Allow'
      ipRules: []
      virtualNetworkRules: []
    }
  }
}

resource flagshipDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundryAccount
  name: 'romtech-standard'
  sku: {
    name: 'GlobalStandard'
    capacity: flagshipCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: flagshipModelName
    }
  }
}

resource fastDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundryAccount
  name: 'romtech-fast'
  dependsOn: [flagshipDeployment]
  sku: {
    name: 'GlobalStandard'
    capacity: fastCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: fastModelName
    }
  }
}

resource embeddingsDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundryAccount
  name: 'romtech-embeddings'
  dependsOn: [fastDeployment]
  sku: {
    name: 'GlobalStandard'
    capacity: embeddingsCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingsModelName
    }
  }
}

resource aiFoundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: aiFoundryAccount
  name: 'proj-default'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    description: 'Default project'
    displayName: 'proj-default'
  }
}

output endpoint string = 'https://${aiFoundryAccount.name}.services.ai.azure.com'
@secure()
output apiKey string = aiFoundryAccount.listKeys().key1
output flagshipDeploymentName string = flagshipDeployment.name
output fastDeploymentName string = fastDeployment.name
output embeddingsDeploymentName string = embeddingsDeployment.name
