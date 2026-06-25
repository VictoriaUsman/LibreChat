param environmentName string = 'Dev'
param liteLlmPrincipalId string = ''
param libreChatPrincipalId string = ''
param ragApiPrincipalId string = ''

resource keyVaultSecretsUserRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  scope: subscription()
  name: '4633458b-17de-408a-b874-0445c86b69e6'
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: 'kv-romtech-${toLower(environmentName)}'
}

resource liteLlmRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, liteLlmPrincipalId, keyVaultSecretsUserRole.id)
  properties: {
    roleDefinitionId: keyVaultSecretsUserRole.id
    principalId: liteLlmPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource libreChatRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, libreChatPrincipalId, keyVaultSecretsUserRole.id)
  properties: {
    roleDefinitionId: keyVaultSecretsUserRole.id
    principalId: libreChatPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource ragApiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, ragApiPrincipalId, keyVaultSecretsUserRole.id)
  properties: {
    roleDefinitionId: keyVaultSecretsUserRole.id
    principalId: ragApiPrincipalId
    principalType: 'ServicePrincipal'
  }
}
