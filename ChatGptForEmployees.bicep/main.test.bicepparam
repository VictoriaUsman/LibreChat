using 'main.bicep'

param environmentName = 'Test'
param rgName = 'rg-test-shared'
param location = 'eastus2'
param subId = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'

param liteLlmImage = 'ghcr.io/berriai/litellm:main-v1.57.4'
// Test migrates off upstream's mutable ghcr tag onto OUR fork build, pinned by digest —
// the same digest validated in dev (fork `main` @ a4e71a966, ACR tag 26023, amd64).
//
// The registry host MUST be acrcgfetest, not acrcgfedev: libreChat.bicep resolves
// `acrcgfe<env>` and takes the pull credentials from that registry alone (see its
// `registries` block). A dev host here fails to pull for lack of credentials.
//
// The copy into acrcgfetest is automatic: test.yml's ImportLibreChatImage stage reads this
// value and imports the digest from acrcgfedev. Just set the digest here — promotion is a
// registry copy, never a rebuild, so test runs the bit-identical image that dev validated.
// The stage runs before BicepCreate, so the image is present when the app is repointed; see
// LibreChat_Image_Deployments.md §3.
param libreChatImage = 'acrcgfetest.azurecr.io/librechat@sha256:7f4b246df2d70f6c8ee93026e4f27e5cee310b8305b847fbef4e2cbd422e612c'
param ragApiImage = 'ghcr.io/danny-avila/librechat-rag-api-dev-lite:latest'

param flagshipModelName = 'gpt-5'
param fastModelName = 'gpt-5-mini'
param embeddingsModelName = 'text-embedding-3-small'

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

// Okta department-sync ACA Job — enabled for Test. Deploys only when the Test
// pipeline runs (i.e. when we promote dev -> test). See main.dev.bicepparam for notes.
param deployJobs               = true
param oktaApiToken             = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-test-shared', 'kv-romtech-test', 'ChatGptForEmployeesTest-OktaApiToken')
// Scheduled-job failure alert recipients (sync + cleanup jobs). See jobAlerts.bicep.
param alertEmailAddresses      = [
  'behnam.bozorgi@romtech.com'
  'andrea.tiamson@romtech.com'
  'ian.tristan@romtech.com'
]
