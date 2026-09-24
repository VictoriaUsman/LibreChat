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

// -----------------------------------------------------------------------
// PBI-03: CX1 MCP server Container App
// -----------------------------------------------------------------------
// Defaults to false so every existing deployment is entirely unaffected —
// independent of `deployJobs` (that gate belongs to a different app
// entirely and is not defined in this repository). Flipping this to true
// before WI 11711's inputs exist will fail deployment (empty required
// values), which is deliberate: the disabled path is the only one that
// should ever succeed until those inputs are real. See
// docs/PBI-03-BE-implementation.md for what's still needed from Behnam.
param deployCxoneMcp bool = false

@description('Resource ID of the EXISTING, shared Container Apps Environment. From WI 11711 — no default.')
param cxoneContainerAppsEnvironmentId string = ''
@description('ACR login server. From WI 11711.')
param cxoneRegistryServer string = ''
@description('Image repository name WITHOUT a tag or digest.')
param cxoneImageRepository string = ''
@description('Exactly 64 lowercase hex characters — the released image\'s sha256 digest.')
param cxoneImageSha256 string = ''
@description('Resource ID of the EXISTING, WI-11711-authorized image-pull identity.')
param cxoneImagePullIdentityId string = ''
param cxoneTargetPort int = 8000
param cxoneLivenessPath string = ''
param cxoneReadinessPath string = ''

module keyvault 'keyvault.bicep' = {
    name: 'keyvault'
    params: {
        appName: appName
        environmentName: environmentName
        tenantId: tenantId
    }
}

// Deliberately NOT passed appSystemManagedIdentityObjectId here — that
// conditional role assignment inside keyvault.bicep is legacy plumbing
// from before the app existed. The CX1 MCP app's OWN vault access is
// granted by cxoneKeyvaultAccess below instead, kept as a separate module
// so vault creation never depends on the app's principal existing first.
module cxoneApp 'cxone-containerapp.bicep' = if (deployCxoneMcp) {
    name: 'cxoneApp'
    params: {
        environmentName: environmentName
        location: location
        containerAppsEnvironmentId: cxoneContainerAppsEnvironmentId
        registryServer: cxoneRegistryServer
        imageRepository: cxoneImageRepository
        imageSha256: cxoneImageSha256
        imagePullIdentityId: cxoneImagePullIdentityId
        targetPort: cxoneTargetPort
        livenessPath: cxoneLivenessPath
        readinessPath: cxoneReadinessPath
        vaultUri: keyvault.outputs.vaultUri
    }
}

module cxoneKeyvaultAccess 'cxone-keyvault-access.bicep' = if (deployCxoneMcp) {
    name: 'cxoneKeyvaultAccess'
    params: {
        vaultName: keyvault.outputs.vaultName
        // Non-null assertion: cxoneKeyvaultAccess shares cxoneApp's exact
        // condition (deployCxoneMcp), so cxoneApp is never null whenever
        // this module itself is actually evaluated for deployment.
        principalId: cxoneApp!.outputs.runtimePrincipalId
    }
}
