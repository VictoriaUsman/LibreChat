using 'main.bicep'

param environmentName = 'Dev'
param rgName = 'rg-dev-shared'
param location = 'eastus2'
param subId = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'

param liteLlmImage = 'ghcr.io/berriai/litellm:main-v1.57.4'
param libreChatImage = 'ghcr.io/danny-avila/librechat:v0.8.6'
param ragApiImage = 'ghcr.io/danny-avila/librechat-rag-api-dev-lite:latest'

param oktaOrgUrl = 'https://romtech.okta.com'

param flagshipModelName = 'gpt-5'
param fastModelName = 'gpt-5-mini'
param embeddingsModelName = 'text-embedding-3-small'

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
// --- Okta department-sync ACA Job ---
// The ACR + image build/push + AcrPull/KV-role assignments are now all in-repo
// (WI 11711); the image ref is derived from the ACR automatically (no jobsImage
// param). The Okta token secret already exists in kv-romtech-dev. The Job is kept
// OFF pending a deploy that confirms the image builds and the Job can pull it —
// then ENABLE by:
//   1. set `deployJobs = true`
//   2. restore the getSecret line for oktaApiToken (uncomment below, delete the '' line)
// While deployJobs=false, the Job (and its getSecret dependency) don't deploy, so
// the pipeline stays green even before the first image build.
param deployJobs               = false
param oktaApiToken             = ''
// param oktaApiToken          = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-dev-shared', 'kv-romtech-dev', 'ChatGptForEmployeesDev-OktaApiToken')
