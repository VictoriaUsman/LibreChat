using 'main.bicep'

param appName = 'ROMTechMCP'
param location = 'eastus'
param environmentName = 'Dev'
param rgName = 'rg-dev-shared'
param subId = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'
param tenantId = '04e23ac0-68f3-4873-b961-01af4fe0bd04'

// PBI-03: CX1 MCP server — disabled until WI 11711's inputs are confirmed.
// See docs/PBI-03-BE-implementation.md. Flip deployCxoneMcp only once the
// params below are filled in with real, WI-11711-confirmed values.
param deployCxoneMcp = false
param cxoneContainerAppsEnvironmentId = ''
param cxoneRegistryServer = ''
param cxoneImageRepository = ''
param cxoneImageSha256 = ''
param cxoneImagePullIdentityId = ''
param cxoneTargetPort = 8000
param cxoneLivenessPath = ''
param cxoneReadinessPath = ''
