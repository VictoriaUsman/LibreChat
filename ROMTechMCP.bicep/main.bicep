param appName string = 'ROMTechMCP'
param location string = 'eastus'

@allowed([
    'Dev'
    'Test'
    'Uat'
    'Prod'
])
param environmentName string = 'Prod'

@allowed([
    'rg-dev-shared'
    'rg-test-shared'
    'rg-uat-shared'
    'rg-prod-shared'
])
param rgName string = 'rg-prod-shared'

@allowed([
    'e64069c2-4b14-4c32-a1f0-3493457f0eff'
])
param subId string = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'

@allowed([
    '04e23ac0-68f3-4873-b961-01af4fe0bd04'
])
param tenantId string = '04e23ac0-68f3-4873-b961-01af4fe0bd04'

// Add your resource modules here. Pass appSystemManagedIdentityObjectId to keyvault
// once your compute resource (App Service, Function App, Container App, etc.) is defined.

module keyvault 'keyvault.bicep' = {
    name: 'keyvault'
    params: {
        appName: appName
        environmentName: environmentName
        tenantId: tenantId
    }
}
