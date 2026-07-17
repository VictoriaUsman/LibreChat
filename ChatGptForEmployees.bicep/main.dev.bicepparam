using 'main.bicep'

param environmentName = 'Dev'
param rgName = 'rg-dev-shared'
param location = 'eastus2'
param subId = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'

param liteLlmImage = 'ghcr.io/berriai/litellm:main-v1.57.4'
param libreChatImage = 'ghcr.io/danny-avila/librechat:v0.8.6'
param ragApiImage = 'ghcr.io/danny-avila/librechat-rag-api-dev-lite:latest'

// Placeholder until Ops builds/pushes a real image (see jobs.bicep's Ops
// dependencies comment).
param jobsImage = '<registry>/librechat-cleanup:latest'
param oktaOrgUrl = 'https://romtech.okta.com'

param flagshipModelName = 'gpt-4.1'
param fastModelName = 'gpt-4.1-mini'
param embeddingsModelName = 'text-embedding-3-small'

// URGENT (2026-07-14): raise flagship (gpt-4.1) AND fast (gpt-4.1-mini) throughput to
// ~1,000,000 TPM each for Dev. GlobalStandard capacity unit ~= 1,000 TPM (see main.bicep),
// so 1000 = ~1M TPM. Overrides the main.bicep defaults (flagship 100 / fast 20), Dev only
// (test/prod unchanged). PREREQUISITE: the subscription needs >=1M TPM of quota for EACH
// model (gpt-4.1 and gpt-4.1-mini, GlobalStandard, eastus2), or the deploy FAILS with a
// quota error — verify in Azure AI Foundry > Quotas before merging. embeddingsCapacity is
// unchanged (~20K TPM via the main.bicep default).
param flagshipCapacity = 1000
param fastCapacity = 1000

param postgresAdminUser = 'cgfeadmin'

// Secrets from Key Vault
param postgresAdminPassword    = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-dev-shared', 'kv-romtech-dev', 'ChatGptForEmployeesDev-PostgresAdminPassword')
param liteLlmMasterKey         = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-dev-shared', 'kv-romtech-dev', 'ChatGptForEmployeesDev-LiteLlmMasterKey')
param jwtSecret                = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-dev-shared', 'kv-romtech-dev', 'ChatGptForEmployeesDev-JwtSecret')
param jwtRefreshSecret         = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-dev-shared', 'kv-romtech-dev', 'ChatGptForEmployeesDev-JwtRefreshSecret')
param credsKey                 = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-dev-shared', 'kv-romtech-dev', 'ChatGptForEmployeesDev-CredsKey')
param credsIv                  = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-dev-shared', 'kv-romtech-dev', 'ChatGptForEmployeesDev-CredsIv')
param liteLlmVirtualKey        = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-dev-shared', 'kv-romtech-dev', 'ChatGptForEmployeesDev-LiteLlmVirtualKey')
param openIdClientId           = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-dev-shared', 'kv-romtech-dev', 'ChatGptForEmployeesDev-OpenIdClientId')
param openIdClientSecret       = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-dev-shared', 'kv-romtech-dev', 'ChatGptForEmployeesDev-OpenIdClientSecret')
param openIdSessionSecret      = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-dev-shared', 'kv-romtech-dev', 'ChatGptForEmployeesDev-OpenIdSessionSecret')
param oktaApiToken             = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-dev-shared', 'kv-romtech-dev', 'ChatGptForEmployeesDev-OktaApiToken')
