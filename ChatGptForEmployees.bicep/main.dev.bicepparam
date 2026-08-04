using 'main.bicep'

param environmentName = 'Dev'
param rgName = 'rg-dev-shared'
param location = 'eastus2'
param subId = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'

param liteLlmImage = 'ghcr.io/berriai/litellm:main-v1.57.4'
// LibreChat runs OUR fork build (repo: ChatGptForEmployeesLibreChatFork), pulled from our
// ACR and pinned by IMMUTABLE DIGEST — never a mutable tag. To promote a new fork build:
// run the fork's build pipeline, copy the digest it prints, and paste it here.
//
// Take the digest from the pipeline's `Deploy by DIGEST` banner — NOT from the `az acr build`
// summary block, which also lists the node:20-alpine base-image digest under
// `runtime-dependency`. That one is provenance, not deployable.
//
// This digest = guided-tour copy + step-advance fixes (fork `main` @ 03925623b, PR 11524,
// ACR tag 25740, amd64, built 2026-08-04). Plain-language rewrite of all four tour steps,
// plus fixes for a step advance that could render the previous step, step 3's missing
// anchor on a collapsed sidebar, and two stacked backdrops.
// Rollback: restore sha256:5e198b62… (fork `main` @ 0b202deef, tag 25436, 2026-08-03) and
// redeploy — still in the registry, as is sha256:65932ee0… before it.
param libreChatImage = 'acrcgfedev.azurecr.io/librechat@sha256:12c7731e5ff2588b6cb30b13260aa27119b16c066195af431a78d2dc9d556942'
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
// param). The Okta token secret already exists in kv-romtech-dev, and the ACR +
// image (acrcgfedev / librechat-cleanup) are built and verified — so the Job is
// now ENABLED for Dev: on deploy it creates job-cgfe-okta-sync-dev with its
// AcrPull + Key Vault Secrets User role assignments and pulls the image. Trigger
// it via the portal ("Run now") to test, or wait for the Tue/Fri cron. Test/Prod
// are also enabled (in their own bicepparams) but only deploy when those pipelines
// run — so we validate in Dev first, then promote dev -> test -> prod when ready.
param deployJobs               = true
param oktaApiToken             = getSecret('e64069c2-4b14-4c32-a1f0-3493457f0eff', 'rg-dev-shared', 'kv-romtech-dev', 'ChatGptForEmployeesDev-OktaApiToken')
// Scheduled-job failure alert recipients. Azure Monitor emails these on a sync or
// cleanup job failure (jobAlerts.bicep). Empty [] = no alert deployed.
param alertEmailAddresses      = [
  'behnam.bozorgi@romtech.com'
  'andrea.tiamson@romtech.com'
  'ian.tristan@romtech.com'
]
