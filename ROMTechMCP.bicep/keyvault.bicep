param appName string = ''
param environmentName string = ''
param tenantId string = ''

// Pass this from your compute resource's managed identity output once it exists.
// Leave empty to skip the role assignment (useful before the app is deployed).
param appSystemManagedIdentityObjectId string = ''

// The role assignment below (Key Vault Secrets User) only has any effect
// when the vault is in RBAC mode — with `accessPolicies: []` and RBAC NOT
// explicitly enabled, a vault defaults to legacy access-policy mode, where
// that role assignment would silently do nothing. Default true since this
// is a new vault with no other consumers yet. If this template has
// ALREADY been deployed with access-policy-mode consumers relying on it,
// confirm that before flipping this — switching an existing vault's
// authorization model can break those consumers (PBI-02 implementation
// notes, docs/PBI-02-BE-implementation.md).
param enableRbacAuthorization bool = true

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
    name: 'kv-romtech-${toLower(environmentName)}'
    location: 'eastus'
    properties: {
        accessPolicies: []
        enableRbacAuthorization: enableRbacAuthorization
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

// Non-secret — safe to output. Consumed by cxone-containerapp.bicep (via
// main.bicep) so the app gets a vault URI without main.bicep needing to
// re-derive the vault's naming convention itself, and by
// cxone-keyvault-access.bicep, which only needs the vault's NAME (not this
// output, since it references the vault directly by the same convention —
// kept here too in case that convention ever needs to change in one place).
output vaultName string = keyVault.name
output vaultUri string = keyVault.properties.vaultUri

