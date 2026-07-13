param envName string = 'Dev'
param location string = 'eastus'

var storageAccountName = 'stcgfe${toLower(envName)}'
var liteLlmShareName = 'litellm-config'
var libreChatShareName = 'librechat-data'

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    publicNetworkAccess: 'Enabled'
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

// Recoverability backstop for the nightly orphaned-file cleanup job (PBI:
// Harden Nightly Orphaned-File Cleanup to Fail-Closed, safety layer #7). If
// the cleanup job's other safeguards (canary check, circuit breaker,
// mark-and-sweep grace window) all fail and it deletes a blob it shouldn't
// have, soft-delete + versioning give a >=7 day recovery window before the
// data is unrecoverable.
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 7
    }
    isVersioningEnabled: true
  }
}

// Container for user-uploaded files (source: 'azure_blob' in the LibreChat
// File schema). Must match AZURE_CONTAINER_NAME used by
// scripts/cleanup_orphaned_files.py.
resource filesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'files'
  properties: {
    publicAccess: 'None'
  }
}

resource liteLlmShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: liteLlmShareName
  properties: {
    shareQuota: 1
    enabledProtocols: 'SMB'
  }
}

resource libreChatShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: libreChatShareName
  properties: {
    shareQuota: 5
    enabledProtocols: 'SMB'
  }
}

output storageAccountName string = storageAccount.name
#disable-next-line outputs-should-not-contain-secrets
@secure()
output storageAccountKey string = storageAccount.listKeys().keys[0].value
output liteLlmShareName string = liteLlmShareName
output libreChatShareName string = libreChatShareName
output blobContainerName string = filesContainer.name
// Consumed by libreChat.bicep (fileStrategy: azure_blob) and, separately, by
// the cleanup job. Managed identity would be preferable to a key-bearing
// connection string — tracked as a security follow-up in the working notes.
#disable-next-line outputs-should-not-contain-secrets
@secure()
output blobConnectionString string = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
