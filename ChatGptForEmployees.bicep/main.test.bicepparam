using 'main.bicep'

// Redeploy trigger (2026-07-14). The pipeline's "Detect Folder Changes" gate only
// runs the Bicep stage when a file under ChatGptForEmployees.bicep/ changed since
// the LAST SUCCESSFUL build. A prior Test build advanced that baseline without
// deploying (Bicep stage skipped, build still marked successful), leaving Test
// stuck on librechat v0.7.5 while the params below already pin v0.8.6. This no-op
// edit is a changed file under the watched folder, so it forces the Bicep stage to
// run and roll the v0.8.6 revision. Follow-up: make the gate diff against the last
// successfully-DEPLOYED SHA (or add a forceDeploy param) so this can't silently
// skip a deploy again — Prod will hit the same trap on its v0.8.6 cutover.
param environmentName = 'Test'
param rgName = 'rg-test-shared'
param location = 'eastus2'
param subId = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'

param liteLlmImage = 'ghcr.io/berriai/litellm:main-v1.57.4'
param libreChatImage = 'ghcr.io/danny-avila/librechat:v0.8.6'
param ragApiImage = 'ghcr.io/danny-avila/librechat-rag-api-dev-lite:latest'

param flagshipModelName = 'gpt-4.1'
param fastModelName = 'gpt-4.1-mini'
param embeddingsModelName = 'text-embedding-3-small'

// Raised to ~1,000,000 TPM each for flagship (gpt-4.1) + fast (gpt-4.1-mini) ahead of the
// QA/IT audience moving onto Test (GlobalStandard ~1,000 TPM/unit, so 1000 = ~1M TPM; was
// 100 / 40). AGGREGATE QUOTA: GlobalStandard quota is shared per subscription/region, so
// Dev (~1M) + Test (~1M) [+ Prod] must ALL fit within the eastus2 gpt-4.1 / gpt-4.1-mini
// quota — verify in Azure AI Foundry > Quotas BEFORE deploying, or the deploy fails with a
// quota error. embeddingsCapacity unchanged.
param flagshipCapacity = 1000
param fastCapacity = 1000
param embeddingsCapacity = 20

param postgresAdminUser = 'cgfeadmin'

// Secrets from Key Vault
param postgresAdminPassword    = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-test-shared', 'kv-romtech-test', 'ChatGptForEmployeesTest-PostgresAdminPassword')
param liteLlmMasterKey         = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-test-shared', 'kv-romtech-test', 'ChatGptForEmployeesTest-LiteLlmMasterKey')
param jwtSecret                = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-test-shared', 'kv-romtech-test', 'ChatGptForEmployeesTest-JwtSecret')
param jwtRefreshSecret         = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-test-shared', 'kv-romtech-test', 'ChatGptForEmployeesTest-JwtRefreshSecret')
param credsKey                 = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-test-shared', 'kv-romtech-test', 'ChatGptForEmployeesTest-CredsKey')
param credsIv                  = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-test-shared', 'kv-romtech-test', 'ChatGptForEmployeesTest-CredsIv')
param liteLlmVirtualKey        = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-test-shared', 'kv-romtech-test', 'ChatGptForEmployeesTest-LiteLlmVirtualKey')
param openIdClientId           = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-test-shared', 'kv-romtech-test', 'ChatGptForEmployeesTest-OpenIdClientId')
param openIdClientSecret       = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-test-shared', 'kv-romtech-test', 'ChatGptForEmployeesTest-OpenIdClientSecret')
param openIdSessionSecret      = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-test-shared', 'kv-romtech-test', 'ChatGptForEmployeesTest-OpenIdSessionSecret')
