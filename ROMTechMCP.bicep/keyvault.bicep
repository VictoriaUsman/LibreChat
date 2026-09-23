param appName string = ''
param environmentName string = ''
param tenantId string = ''

// Pass this from your compute resource's managed identity output once it exists.
// Leave empty to skip the role assignment (useful before the app is deployed).
param appSystemManagedIdentityObjectId string = ''

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
    name: 'kv-romtech-${toLower(environmentName)}'
    location: 'eastus'
    properties: {
        accessPolicies: []
        sku: {
            family: 'A'
            name: 'standard'
        }
        tenantId: tenantId
    }
}

@description('This is the built-in Key Vault Secrets User role.')
resource keyVaultSecretsUserRoleDefinition 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = if (!empty(appSystemManagedIdentityObjectId)) {
    scope: subscription()
    name: '4633458b-17de-408a-b874-0445c86b69e6'
}

resource roleAssignmentKeyVault 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(appSystemManagedIdentityObjectId)) {
    scope: keyVault
    name: guid(keyVault.id, appSystemManagedIdentityObjectId, keyVaultSecretsUserRoleDefinition.id)
    properties: {
        roleDefinitionId: keyVaultSecretsUserRoleDefinition.id
        principalId: appSystemManagedIdentityObjectId
        principalType: 'ServicePrincipal'
    }
}

// Add secrets here as needed, e.g.:
// resource mySecret 'Microsoft.KeyVault/vaults/secrets@2024-12-01-preview' = {
//     name: '${appName}${environmentName}-MySecret'
//     parent: keyVault
//     properties: { value: mySecretValue }
// }
