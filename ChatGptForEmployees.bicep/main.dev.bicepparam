using 'main.bicep'

param environmentName = 'Dev'
param rgName = 'rg-dev-shared'
param location = 'eastus2'
param subId = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'

// Bumped from main-v1.57.4 to v1.99.0 to pick up fixes for CVE-2026-42208 (pre-auth SQL
// injection via a crafted Authorization header, CVSS 9.3) and CVE-2026-42271 (command
// injection/RCE chain via the MCP test endpoint, CVSS 8.7-10.0), both of which affect every
// version from 1.57.4 through 1.83.6. Patched upstream in v1.83.7-stable; v1.99.0 is the
// latest published release. Note the tag format itself changed (main-vX.Y.Z -> vX.Y.Z)
// somewhere after 1.57.4 — verified v1.99.0 exists in ghcr.io/berriai/litellm before pinning it.
//
// Pinned by IMMUTABLE DIGEST, not the `v1.99.0` tag — same rule as libreChatImage below.
// The entire review rests on one specific image: the 157-migration inventory, the
// 16-to-74-table baseline gap in 01-baseline-remediation.sql, and the prompt-storage
// OR-gate verification (store_prompts_in_spend_logs / STORE_PROMPTS_IN_SPEND_LOGS) were
// all validated against sha256:570a872d… and nothing else. A tag is a movable label, so
// deploying `:v1.99.0` would deploy whatever that label points at on the day, which is not
// necessarily the artifact any of that evidence describes. REVIEW-AND-CUTOVER.md already
// specifies the digest ("avoiding unpinned tags"); this is the file that has to agree with it.
param liteLlmImage = 'ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5'
// LibreChat runs OUR fork build (repo: ChatGptForEmployeesLibreChatFork), pulled from our
// ACR and pinned by IMMUTABLE DIGEST — never a mutable tag. To promote a new fork build:
// run the fork's build pipeline, copy the digest it prints, and paste it here.
//
// Take the digest from the pipeline's `Deploy by DIGEST` banner — NOT from the `az acr build`
// summary block, which also lists the node:20-alpine base-image digest under
// `runtime-dependency`. That one is provenance, not deployable.
//
// This digest = light-mode fix for the bot icon beside each response (fork `main` @ de8c5f078,
// PR 12024, ACR tag 29854, amd64, built 2026-08-12). The glyph was rendering in white on a
// white page: the endpoint entry that serves ROMChat sets no background, the shared wrapper
// hard-codes `text-white`, and the glyph is stroked with `currentColor`. Now themed via
// `text-text-primary`. WI 13121.
//
// Changing this line is now enough to deploy: the pipelines pass `bicepDetectFolder: ''`, so
// the incremental gate that used to skip BicepCreate no longer applies. If you ever see a
// green run that did NOT change the running image, check that first — history in
// main.bicep's header and LibreChat_Image_Deployments.md §5.
//
// Rollback: restore sha256:2473d02e… (fork `main` @ 73a0ce22e, tag 27154, 2026-08-07) and
// redeploy — still in the registry, as is sha256:7f4b246d… before it.
param libreChatImage = 'acrcgfedev.azurecr.io/librechat@sha256:1c67d91df0700b8639e8310eb6c7b1632c38beab1342025100677902437da6a1'
param ragApiImage = 'ghcr.io/danny-avila/librechat-rag-api-dev-lite:latest'

param oktaOrgUrl = 'https://romtech.okta.com'

// Maintenance-state enforcement for the LiteLLM v1.99.0 dev cutover (Follow-up 1
// P1; corrected to independently-meaningful states per the `89c57d0`
// working-changes follow-up, Finding 2; extended to a fourth state per the
// second working-changes follow-up, Finding 1). Left 'off' here for normal
// deploys. The cutover sequence in REVIEW-AND-CUTOVER.md, "Maintenance-mode
// enforcement", is:
//   1. Flip this to 'paused', commit together with the pinned liteLlmImage
//      digest (§3b/§2a Step 2b) -- push -- the resulting deploy uploads the
//      reviewed config and forces LiteLLM, LibreChat, and both scheduled jobs
//      all down/paused. Nothing serves traffic or runs a scheduled job yet;
//      verify via `az containerapp show` / `job show` before touching the
//      database.
//   2. Run the database remediation/migration sequence (§2a) against the
//      now-paused, already-correctly-configured environment.
//   3. Flip this to 'litellm-only' alone (image/config unchanged from step 1)
//      and commit/push again -- LiteLLM returns to normal scale for direct,
//      internal-only synthetic checks (§2a Step 8d, via the manually-
//      triggered job-cgfe-synth-check-dev job); LibreChat and both jobs stay
//      paused, so no ordinary employee traffic can reach LiteLLM yet.
//   4. Once those checks pass, flip this to 'validation' AND set
//      maintenanceTesterIpRanges (below) to the authorized tester's actual
//      public IP for this window, commit/push again -- LibreChat also comes
//      up, restricted to that IP only, for the full application smoke-test
//      pass (§2a Step 8e: Okta login, streaming, model picker, conversations,
//      upload). Both jobs remain paused.
//   5. Once those checks pass, flip this to 'off' and clear
//      maintenanceTesterIpRanges back to [], commit/push again -- this is the
//      release: LibreChat opens to everyone and both jobs' schedules resume,
//      with no stale-config race anywhere in this sequence, because the
//      image/config were already uploaded and validated in step 1.
// Do not leave this at anything other than 'off' after the maintenance window
// closes.
param maintenanceState = 'validation'
// See step 4 above -- populate with the authorized tester's/operator's actual
// public IP (as a /32 CIDR, e.g. '203.0.113.4/32') only for the 'validation'
// step of the maintenance window, then clear back to [] before releasing.
// Ignored in every state other than 'validation'; see libreChat.bicep's own
// param comment for what happens if 'validation' is set while this is empty
// (fails closed -- blocks everyone, including the tester).
param maintenanceTesterIpRanges = ['47.204.111.140/32']

// Pin the scheduled-jobs image to the exact build verified for this cutover
// (REVIEW-AND-CUTOVER.md Step 8d(i)). Recorded from the BuildJobsImage stage of the
// pipeline run for dev commit 8f5cf9b4ca4f444806891bab74957721194c4b9c.
// The synthetic check in Step 8d must run against a digest-pinned image, not the
// mutable :latest tag, which can move between a registry check and the image pull.
// RESET THIS TO '' IN A FOLLOW-UP COMMIT ONCE THE WINDOW CLOSES -- while it is set,
// job-cgfe-okta-sync-dev and job-cgfe-cleanup-dev share this pin and will silently
// ignore every later BuildJobsImage run. Deliberately NOT cleared in the same commit
// that ends the window: that deploy already resumes the cron schedules, and un-pinning
// simultaneously would send the first resumed run to whatever :latest points at.
param jobsImageDigest = 'sha256:ef836ac563af0aaa9a45f45575c26fd9bd707326234cbad4993cd7165b4abf0f'

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
