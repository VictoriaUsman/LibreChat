// Azure Container Registry for the scheduled-jobs image (WI 11711).
// One registry per environment (`acrcgfe<env>`), mirroring the per-env naming
// of storage (`stcgfe<env>`). ACR names are alphanumeric-only (5-50 chars) —
// no hyphens — hence acrcgfe<env> rather than acr-cgfe-<env>.
//
// The deploy pipeline runs `az acr build` against this registry to build
// scripts/Dockerfile.cleanup and push `librechat-cleanup:latest`; the ACA Job
// (jobs.bicep) pulls it using this registry's ADMIN credentials (the deploy
// service principal isn't permitted to assign an AcrPull role — see jobs.bicep).
// Basic SKU is plenty for these small internal images.

param envName string = 'Dev'
param location string = 'eastus'

var acrName = 'acrcgfe${toLower(envName)}'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    // Admin user ON: the deploy service principal can create/manage this registry
    // but can't write role assignments on it, so the ACA Job pulls with admin
    // credentials rather than a managed-identity AcrPull role (see jobs.bicep).
    // Harden to identity pull later if Ops grants the SP User Access Administrator.
    adminUserEnabled: true
  }
}

// NOTE: ChatGptForEmployeesDevSC (14143789-…) has "Container Registry Data Importer and
// Data Reader" (577a9874-…) on acrcgfetest and acrcgfeprod — pre-provisioned manually via
// az rest because the Test/Prod service connections only have Contributor (no roleAssignments/write).
// If those SCs are ever granted User Access Administrator, restore this as a Bicep resource.

output name string = acr.name
output loginServer string = acr.properties.loginServer
output id string = acr.id
