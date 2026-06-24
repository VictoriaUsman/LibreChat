using 'main.bicep'

param environmentName = 'Prod'
param rgName = 'rg-prod-shared'
param location = 'eastus2'
param subId = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'

param liteLlmImage = 'ghcr.io/berriai/litellm:main-v1.57.4'
param libreChatImage = 'ghcr.io/danny-avila/librechat:v0.7.5'
param ragApiImage = 'ghcr.io/danny-avila/librechat-rag-api-dev-lite:latest'

param flagshipModelName = 'gpt-4o'
param fastModelName = 'gpt-4o-mini'
param embeddingsModelName = 'text-embedding-3-small'

param postgresAdminUser = 'cgfeadmin'

// Secrets from Key Vault
param postgresAdminPassword    = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-prod-shared', 'kv-romtech-prod', 'ChatGptForEmployeesProd-PostgresAdminPassword')
param liteLlmMasterKey         = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-prod-shared', 'kv-romtech-prod', 'ChatGptForEmployeesProd-LiteLlmMasterKey')
param jwtSecret                = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-prod-shared', 'kv-romtech-prod', 'ChatGptForEmployeesProd-JwtSecret')
param jwtRefreshSecret         = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-prod-shared', 'kv-romtech-prod', 'ChatGptForEmployeesProd-JwtRefreshSecret')
param credsKey                 = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-prod-shared', 'kv-romtech-prod', 'ChatGptForEmployeesProd-CredsKey')
param credsIv                  = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-prod-shared', 'kv-romtech-prod', 'ChatGptForEmployeesProd-CredsIv')
param liteLlmVirtualKey        = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-prod-shared', 'kv-romtech-prod', 'ChatGptForEmployeesProd-LiteLlmVirtualKey')
param openIdClientId           = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-prod-shared', 'kv-romtech-prod', 'ChatGptForEmployeesProd-OpenIdClientId')
param openIdClientSecret       = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-prod-shared', 'kv-romtech-prod', 'ChatGptForEmployeesProd-OpenIdClientSecret')
param openIdSessionSecret      = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-prod-shared', 'kv-romtech-prod', 'ChatGptForEmployeesProd-OpenIdSessionSecret')
param ragApiJwtSecret          = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-prod-shared', 'kv-romtech-prod', 'ChatGptForEmployeesProd-RagApiJwtSecret')
