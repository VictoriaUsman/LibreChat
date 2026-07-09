using 'main.bicep'

param environmentName = 'Test'
param rgName = 'rg-test-shared'
param location = 'eastus2'
param subId = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'

param liteLlmImage = 'ghcr.io/berriai/litellm:main-v1.57.4'
param libreChatImage = 'ghcr.io/danny-avila/librechat:v0.7.5'
param ragApiImage = 'ghcr.io/danny-avila/librechat-rag-api-dev-lite:latest'

param flagshipModelName = 'gpt-4.1'
param fastModelName = 'gpt-4.1-mini'
param embeddingsModelName = 'text-embedding-3-small'

// Raised to >=100K TPM for realistic load testing (was 20 = ~20K TPM, which
// produced artificial 429s under concurrent test load). Confirm quota is
// available in this region BEFORE deploying — see PBI: Increase Azure OpenAI
// TPM Capacity for Realistic Testing.
param flagshipCapacity = 100
param fastCapacity = 40
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
