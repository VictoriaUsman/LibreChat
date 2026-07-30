param appName string = 'ChatGptForEmployees'
param envName string = 'Dev'
param location string = 'eastus'

// Primary models — romtech-standard and romtech-fast are the deployment names
// LiteLLM references. Changing the model here swaps what those names point to.
param flagshipModelName string = 'gpt-5'
param flagshipModelVersion string = '2025-08-07'
param fastModelName string = 'gpt-5-mini'
param fastModelVersion string = '2025-08-07'

// Backup models — used by LiteLLM as fallback when primary hits 429 or error.
param flagshipBackupModelName string = 'gpt-5.1'
param flagshipBackupModelVersion string = '2025-11-13'
param fastBackupModelName string = 'gpt-5.4-mini'
param fastBackupModelVersion string = '2026-03-17'

param embeddingsModelName string = 'text-embedding-3-small'
param embeddingsModelVersion string = '1'

// Text-to-speech — backs LibreChat's read-aloud button. The `romtech-tts` deployment
// name below is what speech.tts.azureOpenAI in config/librechat.yaml resolves to (the
// app receives it as TTS_DEPLOYMENT_NAME; see libreChat.bicep).
// gpt-4o-mini-tts is the ONLY TTS model offered in this Azure OpenAI resource — the
// older character-billed tts / tts-hd models are not available to deploy, so this is
// settled rather than a preference.
// Version matches the manually validated deployment. Like the five deployments above,
// this one omits versionUpgradeOption and so inherits ARM's default of
// OnceNewDefaultVersionAvailable — pinning an older revision here would fight the
// auto-upgrade on every redeploy. Re-check this against the AI Foundry catalog when
// Azure promotes a new default.
// TTS does NOT route through LiteLLM (LibreChat calls Azure OpenAI directly), so this
// deployment's spend will not appear in per-department reporting — known and accepted.
param ttsModelName string = 'gpt-4o-mini-tts'
param ttsModelVersion string = '2025-12-15'

// Capacity values are driven by ternaries in main.bicep — defaults here are never used directly.
param flagshipCapacity int
param flagshipBackupCapacity int
param fastCapacity int
param fastBackupCapacity int
param embeddingsCapacity int
param ttsCapacity int

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

resource flagshipBackupDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundryAccount
  name: 'romtech-standard-backup'
  dependsOn: [flagshipDeployment]
  sku: {
    name: 'GlobalStandard'
    capacity: flagshipBackupCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: flagshipBackupModelName
      version: flagshipBackupModelVersion
    }
  }
}

resource fastDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundryAccount
  name: 'romtech-fast'
  dependsOn: [flagshipBackupDeployment]
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

resource fastBackupDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundryAccount
  name: 'romtech-fast-backup'
  dependsOn: [fastDeployment]
  sku: {
    name: 'GlobalStandard'
    capacity: fastBackupCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: fastBackupModelName
      version: fastBackupModelVersion
    }
  }
}

resource embeddingsDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundryAccount
  name: 'romtech-embeddings'
  dependsOn: [fastBackupDeployment]
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

resource ttsDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundryAccount
  name: 'romtech-tts'
  dependsOn: [embeddingsDeployment]
  sku: {
    name: 'GlobalStandard'
    capacity: ttsCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: ttsModelName
      version: ttsModelVersion
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
output ttsDeploymentName string = ttsDeployment.name
// Bare account name (no scheme, no suffix). LibreChat's genAzureEndpoint appends
// `.openai.azure.com` when the configured instanceName carries no domain, which is the
// host Microsoft documents for the deployment-scoped /audio/speech path. The account
// sets customSubDomainName, so that hostname resolves alongside the services.ai one.
output accountName string = aiFoundryAccount.name
