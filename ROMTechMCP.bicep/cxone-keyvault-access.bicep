// Grants exactly Key Vault Secrets User, scoped to one existing vault, to
// one existing principal. Deliberately its own module (PBI-03): the vault
// is referenced with `existing`, never created here, so this assignment
// can never make vault CREATION depend on the Container App's principal
// existing first — and the app module never depends on this one either.
// The dependency graph stays acyclic:
//
//   existing environment + pull identity + immutable image -> Container App -> runtime principal
//   vault (created/referenced elsewhere) + runtime principal -> THIS module
//
// Never grants Contributor, Owner, Secrets Officer, or any registry role —
// only Key Vault Secrets User, and only to the runtime (system-assigned)
// identity, never the image-pull identity.

@description('Name of the EXISTING Key Vault to grant access to — the confirmed environment vault, not a new one.')
param vaultName string

@description('Principal (object) ID being granted access — the Container App\'s SYSTEM-assigned runtime identity. Never the image-pull identity.')
param principalId string

@description('Set explicitly so this can never accidentally target a User or Group principal by mistake.')
param principalType string = 'ServicePrincipal'

var keyVaultSecretsUserRoleDefinitionId = '4633458b-17de-408a-b874-0445c86b69e6'

// Assumes the vault is in the SAME resource group this file is deployed
// into — true today (keyvault.bicep's vault lives alongside everything
// else in this repo). If WI 11711 confirms the real environment vault is
// in a different resource group, the CALLER handles that by invoking this
// file as a module with an explicit `scope: resourceGroup('<other-rg>')`
// (Bicep requires the cross-resource-group scope at the module-invocation
// level, not declarable inline inside a single resource here).
resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: vaultName
}

@description('Built-in Key Vault Secrets User role — the only role this module ever assigns.')
resource keyVaultSecretsUserRoleDefinition 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  scope: subscription()
  name: keyVaultSecretsUserRoleDefinitionId
}

// Deterministic name from (vault, principal, role) — re-running this
// deployment is a no-op, and it can never collide with a different
// principal's assignment on the same vault (e.g. LibreChat's own identity).
resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, principalId, keyVaultSecretsUserRoleDefinition.id)
  scope: vault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinition.id
    principalId: principalId
    principalType: principalType
  }
}

output roleAssignmentId string = roleAssignment.id
output roleDefinitionId string = keyVaultSecretsUserRoleDefinition.id
