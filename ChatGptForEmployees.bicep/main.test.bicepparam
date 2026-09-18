using 'main.bicep'

// ============================================================================
// 🔴 THIS FILE IS ARMED FOR THE v1.99.0 CUTOVER -- MERGING IT TAKES TEST DOWN
// ============================================================================
// Prepared 2026-09-18, NOT yet merged. Two things below are staged together and
// are meant to land at the START of a maintenance window, with an operator present:
//
//   * liteLlmImage  -> pinned to the v1.99.0 digest (was the main-v1.57.4 tag)
//   * maintenanceState -> 'paused'  (was absent, defaulting to 'off')
//
// Merging to `test` therefore scales LiteLLM and LibreChat to zero and pauses both
// scheduled jobs. That is intended: it is §2a Step 2b. Do not merge to tidy up.
//
// Required on this branch first, or the window fails the way dev's did:
//   * ee3e767 -- LiteLLM sized 1.0 vCPU / 2Gi. v1.99.0 is OOM-killed at 0.5/1Gi and
//     writes ZERO logs while ACA keeps serving the old revision.
//   * cdeba17 -- pymongo bounded <4.18, or the scheduled jobs break on Cosmos.
//
// Full procedure: REVIEW-AND-CUTOVER.md §2a. Test-specific gaps and differences
// from dev: WORKING_NOTES.md §12.14 and §12.15.
// ============================================================================

param environmentName = 'Test'
param rgName = 'rg-test-shared'
param location = 'eastus2'
param subId = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'

// Bumped from main-v1.57.4 to v1.99.0 to pick up fixes for CVE-2026-42208 (pre-auth SQL
// injection via a crafted Authorization header, CVSS 9.3) and CVE-2026-42271 (command
// injection/RCE chain via the MCP test endpoint, CVSS 8.7-10.0), both of which affect every
// version from 1.57.4 through 1.83.6. Patched upstream in v1.83.7-stable; v1.99.0 is the
// latest published release.
//
// Pinned by IMMUTABLE DIGEST, not the `v1.99.0` tag. This is the bit-identical artifact that
// dev migrated onto and has been serving since 2026-09-18 -- the 157-migration inventory, the
// schema manifest and the prompt-storage OR-gate verification were all validated against
// sha256:570a872d... and nothing else. The tag was observed resolving to different content
// mid-review, so a tag here would deploy whatever that label points at on the day.
//
// Unlike libreChatImage below, this needs NO registry promotion: it is pulled straight from
// upstream ghcr.io in every environment, so the same digest is valid here as in dev.
//
// ⚠️ Deploying this REQUIRES ee3e767 (LiteLLM sized 1.0 vCPU / 2Gi) to be present on this
// branch. v1.99.0 does not fit in the 0.5/1Gi that non-prod containers used to get -- it is
// OOM-killed during startup and, because the kill is a SIGKILL, it writes ZERO log lines
// while ACA quietly keeps serving the old revision. That cost dev an entire window. Confirm
// `properties.template.containers[0].resources` reads 1.0/2Gi after the deploy.
param liteLlmImage = 'ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5'
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
param libreChatImage = 'acrcgfetest.azurecr.io/librechat@sha256:1c67d91df0700b8639e8310eb6c7b1632c38beab1342025100677902437da6a1'
param ragApiImage = 'ghcr.io/danny-avila/librechat-rag-api-dev-lite:latest'

// Maintenance-state machine for the v1.99.0 cutover window. Added for Test 2026-09-18;
// previously this file declared none of the three params below and fell back to main.bicep's
// defaults ('off' / [] / ''), which meant the staged window could not be driven here at all.
//
// The sequence, mirroring the dev run (REVIEW-AND-CUTOVER.md §2a), is:
//   1. Flip this to 'paused', committed together with the pinned liteLlmImage digest above --
//      the deploy uploads the reviewed config and forces LiteLLM, LibreChat and both
//      scheduled jobs down/paused. Verify via `az containerapp show` / `job show` BEFORE
//      touching the database.
//   2. Run the database remediation/migration sequence (§2a Steps 3.5-8a) against the
//      now-paused environment. Test has NO _prisma_migrations table, exactly like dev, so
//      the baseline remediation path is required, not optional.
//   3. Flip to 'litellm-only' -- LiteLLM returns to normal scale for internal-only synthetic
//      checks via job-cgfe-synth-check-test. LibreChat and both jobs stay paused.
//   4. Flip to 'validation' AND set maintenanceTesterIpRanges to the tester's real public IP
//      -- LibreChat comes up restricted to that IP for the smoke-test pass. Jobs stay paused.
//   5. Flip to 'off' and clear maintenanceTesterIpRanges -- release.
//
// ⚠️ Between steps 3 and 4, assert that the NEW revision is the one actually serving:
// `latestRevisionName` must equal `latestReadyRevisionName`. Under ACA's Single revision
// mode a revision that never becomes ready leaves the OLD image serving, and it answers
// every smoke test correctly. Dev's first window passed every functional gate this way while
// nothing had changed. A green test does not prove a deployment landed.
//
// Do not leave this at anything other than 'off' after the window closes.
//
// 🔴 SET TO 'paused' DELIBERATELY -- this is step 1 above, not an oversight.
// MERGING THIS FILE TO `test` OPENS THE MAINTENANCE WINDOW: LiteLLM and LibreChat go to
// zero replicas and both scheduled jobs are forced to the never-fire cron. Test is down
// from that moment until step 5 sets this back to 'off'. Merge only when an operator is
// ready to run the database sequence immediately afterwards.
//
// Why not leave it 'off' until the window: because the v1.99.0 digest above is in this same
// file. With 'off', merging would deploy v1.99.0 straight into service against a database
// that still has NO migration history -- and DISABLE_SCHEMA_UPDATE=true means it would boot
// cleanly and start serving anyway (§12.8 trap 1), writing against a 16-table schema the new
// version expects to have 75. Pairing the digest with 'paused' makes the worst case "test is
// down and nothing has changed" instead of "test is silently running on a mismatched schema."
param maintenanceState = 'validation'
// Populate with the authorized tester's actual public IP as a /32 CIDR (e.g.
// '203.0.113.4/32') ONLY for the 'validation' step, then clear back to [] before releasing.
// Ignored in every state other than 'validation'. Fails CLOSED when 'validation' is set while
// this is empty -- it blocks everyone, including the tester.
//
// Test is the right place to finally verify the DENY path, which dev could not: every egress
// route on the dev operator's machine shared the allow-listed address, so only the allow path
// was ever exercised. Have a second person confirm they are blocked.
param maintenanceTesterIpRanges = [
  '47.204.111.140/32'
]

// Pin the scheduled-jobs image for the duration of the window, so the synthetic check runs
// against a fixed artifact rather than the mutable :latest tag, which can move between a
// registry check and the image pull. Set it from the BuildJobsImage stage of this cutover's
// pipeline run, then CLEAR IT BACK TO '' afterwards -- while set, all three jobs are frozen
// on that build and silently ignore every later BuildJobsImage.
//
// 🔴 READ BEFORE SETTING THIS. On dev the pin was taken against a build created for the
// window, which was the first jobs build in a month. It re-resolved every unpinned dependency
// in requirements.txt and landed on pymongo 4.18.1, which refuses Cosmos DB's wire version 8
// -- BOTH scheduled jobs failed on their first post-window runs. The pin meant to stop the
// jobs changing is what changed them. Step 8d's synthetic check did not catch it because it
// never touches Mongo, while the jobs that do were cron-paused all window.
//
// So: PIN TO A BUILD THAT HAS ALREADY COMPLETED A SCHEDULED RUN CLEANLY. Test's jobs are
// currently healthy on the 2026-08-17 :latest build -- resolve and pin that digest rather
// than building fresh. If a fresh build is genuinely needed, treat the pin as an upgrade and
// diff resolved versions first: `podman run --rm <digest> pip freeze`, old against new.
// (cdeba17 has since bounded pymongo, but every other dependency there is still unpinned.)
param jobsImageDigest = ''

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
