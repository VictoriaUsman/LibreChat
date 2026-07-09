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
