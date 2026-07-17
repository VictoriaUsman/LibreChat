param appName string = 'ChatGptForEmployees'
param envName string = 'Dev'
param location string = 'eastus'
param flagshipModelName string = 'gpt-4.1'
param flagshipModelVersion string = '2025-04-14'
param fastModelName string = 'gpt-4.1-mini'
param fastModelVersion string = '2025-04-14'
param embeddingsModelName string = 'text-embedding-3-small'
param embeddingsModelVersion string = '1'
// Defaults here are only used if a caller omits the param — main.bicep is the
// effective entry point and always passes its own value explicitly. Kept in
// sync with main.bicep's default to avoid two different-looking defaults.
param flagshipCapacity int = 100
param fastCapacity int = 100
param embeddingsCapacity int = 120

// GPT-5 family — added alongside gpt-4.1/gpt-4.1-mini (keep both until devs
// have wired LiteLLM to the new deployments and tested, then remove old ones).
// Verify model names and versions in the AI Foundry model catalog before deploy.
param gpt5FlagshipModelName string = 'gpt-5'
param gpt5FlagshipModelVersion string = '2025-08-07'
param gpt5FastModelName string = 'gpt-5-mini'
param gpt5FastModelVersion string = '2025-08-07'
param gpt5FlagshipBackupModelName string = 'gpt-5.1'
param gpt5FlagshipBackupModelVersion string = '2025-11-13'
param gpt5FastBackupModelName string = 'gpt-5.4-mini'
param gpt5FastBackupModelVersion string = '2026-03-17'
param gpt5FlagshipCapacity int = 25
param gpt5FastCapacity int = 25
param gpt5FlagshipBackupCapacity int = 25
param gpt5FastBackupCapacity int = 25

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
      version: flagshipModelVersion
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
      version: fastModelVersion
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
      version: embeddingsModelVersion
    }
  }
}

// GPT-5 deployments — chained sequentially after existing ones to avoid
// hitting the concurrent-deployment limit on the AI Foundry account.
resource gpt5FlagshipDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundryAccount
  name: 'gpt-5'
  dependsOn: [embeddingsDeployment]
  sku: {
    name: 'GlobalStandard'
    capacity: gpt5FlagshipCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: gpt5FlagshipModelName
      version: gpt5FlagshipModelVersion
    }
  }
}

resource gpt5FastDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundryAccount
  name: 'gpt-5-mini'
  dependsOn: [gpt5FlagshipDeployment]
  sku: {
    name: 'GlobalStandard'
    capacity: gpt5FastCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: gpt5FastModelName
      version: gpt5FastModelVersion
    }
  }
}

resource gpt5FlagshipBackupDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundryAccount
  name: 'gpt-5-1'
  dependsOn: [gpt5FastDeployment]
  sku: {
    name: 'GlobalStandard'
    capacity: gpt5FlagshipBackupCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: gpt5FlagshipBackupModelName
      version: gpt5FlagshipBackupModelVersion
    }
  }
}

resource gpt5FastBackupDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundryAccount
  name: 'gpt-5-4-mini'
  dependsOn: [gpt5FlagshipBackupDeployment]
  sku: {
    name: 'GlobalStandard'
    capacity: gpt5FastBackupCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: gpt5FastBackupModelName
      version: gpt5FastBackupModelVersion
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
output gpt5FlagshipDeploymentName string = gpt5FlagshipDeployment.name
output gpt5FastDeploymentName string = gpt5FastDeployment.name
output gpt5FlagshipBackupDeploymentName string = gpt5FlagshipBackupDeployment.name
output gpt5FastBackupDeploymentName string = gpt5FastBackupDeployment.name
