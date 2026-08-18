using 'main.bicep'

param environmentName = 'Prod'
param rgName = 'rg-prod-shared'
param location = 'eastus2'
param subId = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'

param liteLlmImage = 'ghcr.io/berriai/litellm:main-v1.57.4'
// Prod migrates off upstream's mutable ghcr tag onto OUR fork build, pinned by digest —
// the same digest validated in dev and test (fork `main` @ a4e71a966, ACR tag 26023, amd64).
// This closes the last mutable-tag exposure: a re-pushed upstream `:v0.8.6` could otherwise
// reach production on any replica pull.
//
// The registry host MUST be acrcgfeprod, not acrcgfedev/acrcgfetest: libreChat.bicep resolves
// `acrcgfe<env>` and takes pull credentials from that registry alone. A wrong host here points
// production at a lower environment's registry.
//
// The copy into acrcgfeprod is automatic: prod.yml's ImportLibreChatImage stage reads this
// value and imports the digest from acrcgfedev. It runs before BicepCreate, so the image is
// present when the app is repointed; see LibreChat_Image_Deployments.md §3.
// This value is inert until the test -> main promotion; it deploys when that PR completes.
param libreChatImage = 'acrcgfeprod.azurecr.io/librechat@sha256:1c67d91df0700b8639e8310eb6c7b1632c38beab1342025100677902437da6a1'
param ragApiImage = 'ghcr.io/danny-avila/librechat-rag-api-dev-lite:latest'

param flagshipModelName = 'gpt-5'
param fastModelName = 'gpt-5-mini'
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
// ⚠️ Read-aloud TTS needs no key here — it reuses the shared Foundry account key via
// aiFoundry.outputs.apiKey (see main.bicep). The cost gate still applies: do NOT run the
// Prod pipeline with speech.tts enabled until a week of real dev audio-output spend has
// been checked in Azure Cost Management against the ~$0.015-per-response estimate
// recorded in config/librechat.yaml's speech block.

// Okta department-sync ACA Job — enabled for Prod. Deploys only when the Prod
// pipeline runs (i.e. when we promote test -> prod). See main.dev.bicepparam for notes.
param deployJobs               = true
param oktaApiToken             = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-prod-shared', 'kv-romtech-prod', 'ChatGptForEmployeesProd-OktaApiToken')
// Scheduled-job failure alert recipients (sync + cleanup jobs). See jobAlerts.bicep.

// ADO 11662 — a NEW address here requires one-time passcode verification.
// APPEND to the end of this list; do not insert (receivers are named
// positionally in jobAlerts.bicep, so inserting rewrites the others).
// The new recipient must complete the passcode within 30 minutes of the
// deploy or they will silently receive nothing, with no deployment error.
// After deploying, run 04-verify-receivers.sh and confirm exit 0.
param alertEmailAddresses      = [
  'behnam.bozorgi@romtech.com'
  'andrea.tiamson@romtech.com'
  'ian.tristan@romtech.com'
]
