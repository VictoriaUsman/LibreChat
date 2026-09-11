# LiteLLM v1.99.0 — review implementation guide

## Implementation review addendum — 2026-09-11

Reviewed implementation through commit `cff94a7` against Behnam's notes and this guide. This is the historical review; the follow-up below records the latest status through `93557da` and takes precedence over its open-status statements. The original brief remains the acceptance checklist.

### Follow-up review through `93557da` — 2026-09-11

**Not ready for dev execution.** The four findings below remain open. This update records required work only; it does not implement or authorize the cutover.

Progress observed: prompt storage is explicitly disabled in both tracked YAML and Bicep; rollback Path B is marked unavailable pending implementation; job configuration/execution commands and the final migration name have been corrected. These documentation/configuration changes are not evidence of deployment. Azure job pause/resume verification and Bicep compilation remain pending. Synthetic proxy results were not rerun in this follow-up review.

#### Follow-up 1 — P1: complete the deployment sequence before restarting writers

**Location:** [REVIEW-AND-CUTOVER.md](REVIEW-AND-CUTOVER.md), Step 1 image check (reviewed lines 535–544) and Step 8 restart instructions (778–783).

The preflight requires the target v1.99.0 image to be deployed before migration, but the procedure does not include an explicit deployment of the pinned image and updated configuration after migration. Restart instructions also allow reactivating the previous revision, which could run the previous image/settings against the upgraded database.

**Correction:** record the current image/revision and settings for recovery; verify the intended pinned artifact separately. Keep writers stopped through remediation, migration, and database validation. Include an explicit deployment of the reviewed target image with the updated Bicep and routing configuration, verify the effective image/settings, then perform controlled application checks before restoring traffic and jobs. Do not reactivate an old revision against the upgraded schema as a normal restart step.

- [ ] Preflight distinguishes the currently deployed revision from the intended upgrade artifact.
- [ ] The sequence includes exact deployment commands, prerequisites, exit handling, and effective-state checks.
- [ ] The new revision has `DISABLE_SCHEMA_UPDATE=true` and both prompt-storage controls set to false before it starts against the upgraded database.
- [ ] Only the verified target revision receives traffic after database and application checks pass; job schedules remain paused until their release gate.

#### Follow-up 2 — P1: repair PowerShell quoting in SQL commands

**Location:** [REVIEW-AND-CUTOVER.md](REVIEW-AND-CUTOVER.md), Step 3.5 row-count capture and Step 5 baseline verification (reviewed lines 607 and 642).

Backslash-double-quote sequences inside PowerShell double-quoted strings do not escape the quotes. An argument-capture check reproduced split SQL arguments without executing SQL. These commands cannot reliably collect the required baseline evidence.

**Correction:** prefer reviewable SQL files invoked with `psql -f`, or use quoting verified for the documented PowerShell version and native argument handling. Review every executable SQL example for the same issue. Preserve quoted PostgreSQL identifiers exactly and stop if evidence collection fails.

- [ ] A local argument-capture check confirms each SQL command reaches psql intact, or commands use verified SQL files.
- [ ] Corrected queries execute successfully against an isolated fixture in the documented shell.
- [ ] Evidence collection checks the native exit code and does not treat a created output file as proof of success.

#### Follow-up 3 — P2: restore complete schema and historical-data verification

**Location:** [REVIEW-AND-CUTOVER.md](REVIEW-AND-CUTOVER.md), Steps 3.5, 5, and 8 (reviewed lines 750–777 for final checks).

Four table counts and a few schema-object checks do not establish full baseline equivalence or preservation of the original 19 tables. Matching counts cannot detect changed values. A sample of migration checksums also does not establish that all 157 match the pinned source.

**Correction:** capture and compare deterministic fingerprints for the existing columns of all 19 original tables while writers are stopped, with counts as supporting evidence. Restore complete baseline comparison before resolving it, including types, nullability, defaults, indexes, and constraints. Compare the final schema against the pinned target, verify all migration names/checksums and successful state, and verify all 10 previously validated views. Exclude intentionally added columns from historical-row fingerprints so comparisons measure preservation of original data.

- [ ] Pre/post evidence covers all 19 original tables and detects value changes as well as row loss.
- [ ] Full baseline equivalence is a required gate before `migrate resolve --applied`.
- [ ] All 157 expected migration names and checksums are compared, with successful completion and no unresolved failures; sampling is insufficient.
- [ ] Final target-schema comparison, index validity, and all 10 view checks pass before writers resume.
- [ ] Mismatches stop the procedure; execution evidence remains pending until actually collected.

#### Follow-up 4 — P2: handle an uncertain commit outcome explicitly

**Location:** [REVIEW-AND-CUTOVER.md](REVIEW-AND-CUTOVER.md), Step 4 stop/recovery condition (reviewed lines 634–636).

A nonzero client exit does not prove the server rolled back. A connection can fail after the server committed but before the client received confirmation. The statement that any nonzero exit leaves the schema unchanged can therefore authorize an unsafe rerun.

**Correction:** distinguish a confirmed transaction rollback from an unknown outcome. On connection loss or missing commit confirmation, keep writers stopped, capture the error, reconnect read-only, and inspect the actual catalog and migration-history state. Use the documented recovery boundaries to decide the next action; do not infer rollback from the process exit code alone.

- [ ] The failure table covers confirmed rollback, confirmed commit, and unknown commit outcome separately.
- [ ] An unknown outcome requires owner review of catalog/history evidence before any retry or recovery action.
- [ ] No recovery instruction permits blind remediation reruns or bypassing migration-history guards.

**Review scope:** repository inspection and a local PowerShell argument-capture check. No database commands, deployments, or implementation changes were performed during the review. This follow-up is a documentation update only.

### Earlier findings at `cff94a7` (historical)

### Finding 1 — P1: prompt-storage controls do not guarantee metadata-only behavior

**Location:** [REVIEW-AND-CUTOVER.md, prompt-storage guidance](REVIEW-AND-CUTOVER.md#1-promptresponse-storage-verified-source-behavior), particularly the conclusion that no tracked configuration change is required; update the corresponding statement in [BEHNAM-HANDOFF.md](BEHNAM-HANDOFF.md) too.

The pinned image's `_should_store_prompts_and_responses_in_spend_logs()` returns true if the general setting is true; otherwise it checks `STORE_PROMPTS_IN_SPEND_LOGS`. An explicit YAML false does **not** override an environment true. If YAML omits the setting, database-stored configuration may enable it on reload.

The review executed the actual source function with controlled general-setting and environment-boolean inputs. These are source-level decision tests, not a new end-to-end proxy test:

| General setting | Environment boolean | Storage enabled |
|---|---|---|
| Absent | Absent | No |
| False | Absent | No |
| False | True | **Yes** |
| Absent | True | **Yes** |
| True | False | **Yes** |
| False | False | No |

**Correction:** explicitly control both the tracked general setting and the environment fallback for metadata-only operation, verify database-reload precedence, and correct the runbook's default/override explanation. The intended configuration is `general_settings.store_prompts_in_spend_logs: false` plus `STORE_PROMPTS_IN_SPEND_LOGS=false`, with no conflicting effective override. Do not infer safety solely from a minimal-config default test. Keep the actual dev query pending until owner-led execution.

- [ ] Both controls are explicitly configured in the appropriate tracked files, with shared-environment impact documented.
- [ ] The runbook and handoff accurately distinguish the default from effective YAML, database and environment settings.
- [ ] Tests cover the true/false combinations above and the database-reload case.
- [ ] A synthetic proxy test confirms the deployed configuration keeps both fields empty; real dev verification remains clearly pending until performed.

### Finding 2 — P1: the canonical runbook lacks the executable cutover sequence

**Location:** [REVIEW-AND-CUTOVER.md, manual-migration requirement](REVIEW-AND-CUTOVER.md#3-manual-migration-mode-bicep).

The document requires an explicit migration step and refers to sections 2/4, but those sections contain the environment guard and rollback discussion. They do not provide the complete baseline-resolution/deployment sequence. This omission is material now that Bicep disables automatic schema updates.

**Correction:** restore a single ordered operator procedure, using the committed SQL as the canonical artifact. Include environment/image verification, complete recovery prerequisites, stopped writers, remediation, baseline comparison, resolution of only `20250326162113_baseline`, execution of the remaining 156 migrations, and post-migration/application checks. Provide actual commands with explicit exit handling and correct working-directory assumptions. Do not wrap the complete migration history in one transaction because it contains `CREATE INDEX CONCURRENTLY`.

- [ ] The owner can follow the runbook without reconstructing commands from scratch documents or conversation history.
- [ ] Every mutation has prerequisites, an expected result, and a stop/recovery condition.
- [ ] Verification includes 157 successful ledger entries and their source checksums, final schema/index validity, preserved historical data and views, prompt-storage checks, and application smoke tests.
- [ ] The manual-migration requirement links to the actual procedure, and execution-stage results remain unchecked until performed.

### Finding 3 — P1: rollback Path B cannot be implemented using the described parameters

**Location:** [REVIEW-AND-CUTOVER.md, rollback mapping](REVIEW-AND-CUTOVER.md#4-rollback-scope-and-timing), checked against [postgresql.bicep](../../ChatGptForEmployees.bicep/postgresql.bicep), [main.bicep](../../ChatGptForEmployees.bicep/main.bicep), and [jobs.bicep](../../ChatGptForEmployees.bicep/jobs.bicep).

`postgresql.bicep` derives the server name from `envName`; it has no restored-server host parameter. Changing the admin-password reference does not redirect its FQDN. Path B also proposes updating/redeploying RAG against changed outputs while instructing operators not to use the historical RAG database. The connection-consumer table incorrectly says cleanup consumes `liteLlmConnectionString`: that connection goes to LiteLLM and Okta sync; cleanup uses separate RAG host/credential inputs.

**Correction:** name an implementable primary recovery path and its exact database/connection transition. If Path B remains supported, specify the required IaC mechanism for targeting the restored server and preserving the live RAG target separately. Otherwise mark Path B unavailable pending that implementation and rehearsal. Do not describe an unspecified host/password edit as a ready recovery procedure.

- [ ] The connection map distinguishes LiteLLM/Okta sync from cleanup/RAG consumers correctly.
- [ ] Each recovery step names actual parameters, outputs, secret references, or owner-led database operations that exist or are explicitly prepared for the procedure.
- [ ] The selected recovery path keeps live `librechat_rag` and its post-recovery-point embeddings intact, or identifies a separately approved reconciliation requirement.
- [ ] Timing estimates reflect the selected implementation and identify unmeasured steps.
- [ ] Unsupported alternatives are labeled pending, not presented as executable fallbacks.

### Finding 4 — P2: job pausing is still unspecified and its verification command is incorrect

**Location:** [REVIEW-AND-CUTOVER.md, scheduling and pause procedure](REVIEW-AND-CUTOVER.md#7-scheduling-and-job-pause-procedure).

“Apply the verified pause mechanism” does not supply a concrete configuration or command. `az containerapp job execution list` lists executions; it does not establish the configured trigger or prove future scheduled executions are disabled. Job configuration must be inspected with `az containerapp job show`, separately from execution-state checks. See the [job command reference](https://learn.microsoft.com/en-us/cli/azure/containerapp/job?view=azure-cli-latest#az-containerapp-job-show) and [execution command reference](https://learn.microsoft.com/en-us/cli/azure/containerapp/job/execution?view=azure-cli-latest).

**Correction:** choose a supported pause/resume operation and document the exact commands or API payload, resource group/job names, state checks, handling of in-flight executions, and schedule restoration. Account for Bicep reapplying the original schedule during deployment. If Azure validation requires Behnam's access, label that verification pending rather than calling the mechanism verified.

- [ ] Configuration is captured and verified with `job show`; running executions are checked separately with `job execution list`.
- [ ] A concrete supported operation prevents new scheduled runs for the full maintenance window.
- [ ] The procedure handles in-flight runs, retries and deployment-time schedule restoration.
- [ ] Resume restores Okta sync to `0 5 * * 2,5` and cleanup to `0 2 * * *`, with a controlled catch-up and effective-state checks.

### Finding 5 — P2: synthetic-test evidence references a migration absent from the pinned image

**Location:** [REVIEW-AND-CUTOVER.md, synthetic runtime evidence](REVIEW-AND-CUTOVER.md#1a-synthetic-runtime-test-against-the-pinned-image-executed-this-session).

The document reports that migrations through `20260819000000_add_spend_log_timestamps` applied. The inspected pinned image instead contains `20260818000000_add_spend_log_timestamps`, with final migration `20260819000000_shadow_eval_max_budget`. The reported name is absent from that image. This discrepancy needs reconciliation; it does not by itself establish whether the runtime test failed or used a different image.

**Correction:** compare the statement with the original logs, image identity and migration ledger. Correct a transcription error if the evidence supports that explanation. If the evidence is unavailable or identifies another image, rerun the synthetic test against the pinned digest and record reproducible evidence. Do not merely change the reported migration name to make the document appear consistent.

- [ ] The reported migration names and completed ledger match the actual tested image.
- [ ] Test evidence identifies the immutable image digest, configuration, requests, observed results and limitations.
- [ ] Reproducible test instructions or a focused harness are included without credentials or employee content.
- [ ] Any result not supported by retained or reproduced evidence is marked unverified.

### Checks that passed during this review

- The committed remediation script rejected missing, blank, `test`, and `prod` inputs with nonzero exit codes and unchanged schema in an isolated PostgreSQL fixture.
- It rejected an incorrect database and rejected a rerun after migration history existed; the history-rejection case left the schema unchanged.
- The valid local `target_env=dev` case succeeded. This proves the acknowledgement guard, not server identity; separate connection verification is still required.
- `DISABLE_SCHEMA_UPDATE=true` is present in the LiteLLM Bicep environment array.
- `git diff --check` passed for the implementation commits.

**Validation still outstanding:** Bicep compilation was not performed because neither the Bicep nor Azure CLI was available in the review environment. Obtain a real build/validation result before relying on the rendered configuration. Do not assume pushing the feature branch automatically validates it: the checked-in dev pipeline triggers on `dev`, and any additional branch-validation policy must be verified separately.

No repository implementation files or remote data were changed by the review. Its temporary guard-test container was removed. Adding this addendum is a documentation-only change; all five findings remain open until their corrections are implemented and validated.

## Purpose and current scope

Address Behnam's seven review notes before the ROMChat LiteLLM dev upgrade. This document is an implementation brief and acceptance checklist. Creating it does not apply the proposed code, SQL, configuration, or database changes.

The two execution blockers are:

1. Establishing and enforcing metadata-only spend logging.
2. Correcting the remediation script's environment guard.

Behnam said the remaining changes can land alongside the dev run. Prepare them together where practical, and make any unfinished item explicit before scheduling execution.

**Original planning state:** when this brief was first written, the prompt-storage investigation, revised guard, and Bicep changes were not complete. Implementation has since progressed through `cff94a7`; use the dated addendum above for the reviewed status and remaining findings. Do not treat local test results as verification of effective behavior on dev.

## Responsibilities

| Owner | Responsibility |
|---|---|
| Ian | Investigate the pinned image; implement and locally validate the reviewed changes; prepare a focused commit and review response |
| Behnam | Run remediation and migrations as `cgfeadmin`; decide reporting grants; apply the narrow sequence-read grant; choose and coordinate the maintenance window |
| Ian and Behnam | Complete recovery validation, review final artifacts, and record post-migration results |

Do not send messages, deploy, change grants, or run remote DDL as part of preparing this guide. Subsequent implementation should remain separate from the owner-led dev execution.

## Repository locations and implementation boundaries

Paths below are relative to the `ChatGptForEmployees` repository root:

| Artifact | Intended location |
|---|---|
| Remediation SQL | `ChatGptForEmployees/scripts/01-baseline-remediation.sql` |
| Cutover and rollback runbook | `ChatGptForEmployees.docs/local/REVIEW-AND-CUTOVER.md` |
| Short review response | `ChatGptForEmployees.docs/local/BEHNAM-HANDOFF.md` |
| This guide | `ChatGptForEmployees.docs/local/LiteLLM-v1.99.0-Review-Implementation-Guide.md` |
| LiteLLM infrastructure | `ChatGptForEmployees.bicep/liteLlm.bicep` |
| Shared routing configuration | `ChatGptForEmployees/config/litellm_routing_config.yaml` |
| Job schedules | `ChatGptForEmployees.bicep/jobs.bicep` |

`ChatGptForEmployees.docs/local/` is the repository's intended documentation location here; `.docs/local/` in the review is shorthand, not a request to create a second documentation tree.

The previous working artifacts are under the enclosing workspace's `migration-review/` directory, outside this repository. Transfer the reviewed SQL and Markdown into the tracked locations above. Do not assume a reviewer can access those local scratch files.

Preserve unrelated changes, including `litellm_routing_config.local.yaml`. Do not commit credentials, connection strings containing passwords, database dumps, employee content, or the entire scratch directory. Do not modify vendor migration files or mark additional migrations applied to make a test pass.

## 1. Verify and control prompt/response storage

### Implementation instructions

Inspect the exact image used in the rehearsal:

```text
ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5
```

The initial source search found `store_prompts_in_spend_logs` and `turn_off_message_logging`. Treat these as investigation leads, not interchangeable controls or an already verified solution.

Trace the complete path from configuration to the SpendLogs database write:

1. Identify the precise setting and configuration section controlling `messages` and `response` storage.
2. Establish behavior when the setting is absent, explicitly false, explicitly true, or null. Record the declared default and effective fallback behavior separately if they differ.
3. Check configuration precedence: YAML, environment, stored database configuration, and any applicable request-level controls. Determine whether a later reload can override the intended setting.
4. Check successful, streaming, and failed request paths where applicable. Confirm what representation is actually written when storage is off: omitted fields, SQL NULL, `{}`, or another value.
5. Distinguish spend-table storage from callback logging, exception logging, and general message redaction. Do not claim one flag proves all telemetry is content-free.
6. If a configuration change is needed, set the verified control explicitly in the appropriate tracked configuration. Document any shared-environment impact before deployment.

Record the image digest, source paths/functions, relevant line references, and the conclusion in the cutover runbook. Validate with synthetic, non-sensitive prompt/response markers in an isolated environment. Do not use employee conversations as test fixtures.

After the owner-led dev migration and synthetic application requests, Behnam requested:

```sql
SELECT messages, response
FROM public."LiteLLM_SpendLogs"
ORDER BY "startTime" DESC
LIMIT 5;
```

Run this only after the columns exist. The authorized operator should inspect the result in the controlled database session. Record a content-free summary, such as “five rows inspected; both fields empty,” rather than copying any unexpected conversation text into tickets, logs, or chat. Also identify the synthetic requests' own rows; the latest five rows alone may contain unrelated traffic or only older default values.

If content is populated, stop promotion, enforce the verified storage-off setting, and give Behnam the finding for his grant decision. Turning off future storage does not remove already stored content; any cleanup or grant change needs his direction. Empty values in these two fields do not, by themselves, certify every telemetry field or sink as metadata-only.

### Acceptance criteria

- [ ] The exact storage setting, section, default, effective behavior, and precedence are documented from the pinned image.
- [ ] The metadata-only setting is explicit in tracked configuration if required.
- [ ] Synthetic tests demonstrate no prompt/response content in the two SpendLogs fields when storage is disabled; relevant request paths are covered.
- [ ] The runbook includes Behnam's query, synthetic-request identification, and content-free evidence handling.
- [ ] The actual dev result is recorded after migration, or clearly marked **pending dev execution** before that point.
- [ ] Any populated content is escalated to Behnam; no grant changes or historical-content deletion are performed implicitly.

## 2. Replace the database-name-only environment guard

### Implementation instructions

All environments use a database named `litellm`. Retain the database-name check as a secondary check, but remove any claim that it independently protects production.

Require explicit `psql -v target_env=dev` input and reject missing, blank, test, or prod values before remediation DDL. Combine that acknowledgement with verified connection targeting: the dev server is `psql-db-cgfe-dev.postgres.database.azure.com`. An explicit `dev` argument expresses operator intent; it is not proof that the connection is actually to dev. Prefer a constrained client invocation or wrapper that validates the host/database and prevents connection-string overrides from silently selecting another environment.

Do not paste `:'target_env'` directly inside a dollar-quoted `DO $$ ... $$` body. psql does not interpolate variables inside quoted SQL text. One valid pattern is to pass the safely quoted variable to a transaction-local setting outside the block, then read it inside:

```sql
-- Example of variable handling only; retain the other guards and reviewed DDL.
\set ON_ERROR_STOP on
BEGIN;

SELECT set_config('romchat.target_env', :'target_env', true);

DO $$
BEGIN
    IF current_setting('romchat.target_env', true) IS DISTINCT FROM 'dev' THEN
        RAISE EXCEPTION 'Wrong target environment; remediation aborted';
    END IF;
END $$;

-- Additional verified connection/database/history/owner checks precede DDL.
-- Reviewed remediation goes here.
COMMIT;
```

With no `target_env` supplied, the unresolved substitution must fail before DDL under `ON_ERROR_STOP`. Test that behavior in the actual PostgreSQL 16 client rather than assuming it. Use `:'variable'` quoting for values; do not construct SQL by concatenating arbitrary shell input. See the [psql interpolation documentation](https://www.postgresql.org/docs/current/app-psql.html).

Do not hard-code a cloud server IP as permanent identity. If host validation is used, document the checked connection property and its limitations. Local rehearsal must have a clearly separate, constrained test connection; do not weaken the production-facing script with an unrestricted bypass.

Preserve the transaction, timeouts, owner check, migration-history guard, and existing lock ordering unless a specific test demonstrates a necessary change.

### Acceptance criteria

- [ ] Missing, blank, `test`, and `prod` environment inputs abort before DDL with a nonzero client exit.
- [ ] An incorrect database or connection target is rejected by the supported execution path.
- [ ] The supported dev invocation and a controlled local rehearsal invocation are documented.
- [ ] Passing cases execute correctly against an isolated fixture; failing cases leave schema, data, and migration history unchanged.
- [ ] psql variable handling is tested, including the missing-variable case.
- [ ] Documentation distinguishes an explicit acknowledgement from verified server identity.

## 3. Persist manual-migration mode in Bicep

### Implementation instructions

Add the setting to the LiteLLM container's `env` array in `ChatGptForEmployees.bicep/liteLlm.bicep`:

```bicep
{ name: 'DISABLE_SCHEMA_UPDATE', value: 'true' }
```

Check the effective configuration for a conflicting `general_settings.disable_prisma_schema_update` value, because the image's configuration value can take precedence over the environment fallback. Document the effective setting, not only the presence of an environment variable.

This module is shared. Review which environments consume it and state the deployment impact. Do not silently deploy test/prod while preparing the dev change. Follow the repository's established Bicep validation/build workflow; update generated JSON only if the repository expects generated templates to be maintained.

Add a standing runbook requirement: **every future LiteLLM upgrade must have explicit migration review and execution before the new application starts against the database.** Startup will no longer repair an outdated schema automatically. Define what operators check if migrations were skipped.

Record that disabling startup schema mutation removes that mutation path as an additional defense alongside attribution's separate schema. Do not promise that every possible future migration or database change is incapable of affecting attribution. If describing the old image's rollback behavior, verify that image's handling separately.

### Acceptance criteria

- [ ] `DISABLE_SCHEMA_UPDATE=true` is declared in Bicep and appears in the rendered LiteLLM container configuration.
- [ ] No effective configuration override re-enables automatic updates.
- [ ] Bicep validation succeeds, and any required generated artifacts are consistent.
- [ ] Shared-environment impact and the manual-migration requirement are documented.
- [ ] Startup behavior is validated on the appropriate local test environment, or its remaining application validation is explicitly recorded.

## 4. Make rollback scope and timing explicit

### Implementation instructions

Document two distinct recovery paths rather than treating them as the same operation:

| Path | Scope and operational consequences |
|---|---|
| Recover `litellm` back onto the original server | Restore the verified pre-change database into an empty recovery database, validate it, then perform an owner-led connection/name transition. The live `librechat_rag` database stays in place. Sequence state, owners, grants, views, and attribution data still require verification. |
| Redirect workloads to a PITR-restored server | The restored server has a new FQDN and restored copies of the server's databases. Trace and change the appropriate IaC connection outputs/parameters, reconcile secrets and redeploy affected workloads. This is not a revision re-pin. |

A server-level restore creates a separate historical copy; it does not itself overwrite the original live RAG database. Repointing RAG workloads to that restored copy would move them to historical embeddings. State exactly which database each workload will use and how post-recovery-point RAG writes are preserved or reconciled.

Trace actual consumers of `postgresql.bicep` outputs in the repository, including LiteLLM, the RAG API, both jobs, and any LibreChat dependencies. Distinguish direct connection-string consumers from indirect application dependencies. Record affected outputs, secret references, Bicep parameters, apps/jobs, and verification steps. Do not assume an existing parameter can redirect an entire restore path without inspecting the templates.

Keep writers stopped during the database transition. Preserve failed-state evidence where feasible. Include attribution's rollback and sync recovery, not only public tables. Do not use `pg_restore --clean --if-exists` over the upgraded database as proof that new objects absent from the old archive will be removed.

Provide an estimated recovery timeline with separate allowances for:

- Fault assessment and stopping/draining writers.
- Azure restore completion and restored-server access/network configuration.
- Database extraction/restore and validation, if using the original-server path.
- IaC/secret changes and workload redeployments, if changing connection targets.
- Data, application, reporting, and job checks before service restoration.

Label initial numbers **planning estimates**, not measured recovery times. Behnam's 90-minute example is not an agreed SLA or a measured result. Replace estimates with observed rehearsal timing where available; explicitly state uncertainty and the maintenance window allowance.

### Acceptance criteria

- [ ] The selected primary recovery path and fallback path are named and described separately.
- [ ] Connection-string/secret/IaC consumers and redeploy scope are mapped to real repository references.
- [ ] Live `librechat_rag` preservation and any reconciliation requirement are explicit.
- [ ] Estimated outage/recovery duration has a breakdown, assumptions, and measured-versus-unmeasured labels.
- [ ] Complete backup/restore validation includes sequence values, ownership, permissions, and database settings; the earlier limited local copy is not described as full recovery evidence.

## 5. Document recovery boundaries and partial failure

### Implementation instructions

Describe two boundaries explicitly:

1. **Remediation commit:** the live schema has changed, even if migration history is still absent. Before commit, a failed transaction can roll back its uncommitted changes. After commit, an image-only re-pin is not a complete reversal.
2. **Baseline resolution / migration-history creation:** the remediation script's history guard blocks a rerun. Subsequent migrations may partially succeed before a failure. Do not delete history or remove guards to restart the procedure.

Explain the operational consequence in the rollback protocol: stop, capture the ledger/catalog/error state, and follow the tested restore path to return to the pre-upgrade state. Do not automatically rerun remediation or resolve a failed migration as applied.

Avoid stating that a guard makes all other recovery technically impossible. An owner-reviewed forward repair may be possible, but it is a separate reviewed procedure, not the default rollback and not permission to bypass the guard. The standard incident route must remain clear under pressure.

### Acceptance criteria

- [ ] Both boundaries are called out at the corresponding execution steps and in rollback instructions.
- [ ] A phase/state decision table covers pre-commit failure, committed remediation, baseline resolution, and partially applied migrations.
- [ ] The protocol prohibits blind reruns, history deletion, and automatic `resolve --applied` after failure.
- [ ] Any forward-repair alternative requires a separately reviewed plan and owner execution.

## 6. Put executable and reviewable text artifacts in the repository

### Implementation instructions

Place the revised SQL and Markdown at the repository paths listed above. Make the repository SQL the canonical execution artifact; ensure the runbook links to that exact file and invocation. Include the revised review response and relevant local test evidence without sensitive data.

Review the focused diff, validate the artifacts, and prepare a commit when implementation is authorized. Do not commit unrelated files or push/deploy as a side effect of creating documentation. A local commit is not evidence that remote reviewers can access it; record the branch/commit and any separately authorized sharing step.

### Acceptance criteria

- [ ] The actual `.sql` is tracked alongside the scripts.
- [ ] `REVIEW-AND-CUTOVER.md` and the handoff exist under `ChatGptForEmployees.docs/local/`.
- [ ] Links and relative paths resolve without access to the original scratch directory.
- [ ] Documentation matches the exact revised SQL, settings, and commands.
- [ ] The focused implementation commit contains no credentials, copied employee content, dumps, or unrelated changes.
- [ ] Behnam is given the reviewable commit/artifact locations through the authorized review process.

## 7. Correct scheduling and define how jobs are paused

### Implementation instructions

Use the confirmed Okta sync schedule: **`0 5 * * 2,5` — Tuesday and Friday at 05:00 UTC.** Avoid a maintenance window spanning those times. The nightly cadence change did not merge; do not describe it as active. The repository also declares cleanup at `0 2 * * *`; account for that schedule if the window could overlap it.

Choose a real, supported pause/resume mechanism and document exact commands or portal steps after checking the deployed job configuration and supported API. For example, changing a scheduled job to manual triggering is a candidate only after confirming support and the required payload for the deployed API/CLI. Do not invent a generic “disable job” command. See the [Azure Container Apps job command reference](https://learn.microsoft.com/en-us/cli/azure/containerapp/job?view=azure-cli-latest).

The procedure must:

1. Capture each relevant job's trigger type, schedule and currently running executions.
2. Prevent new scheduled executions and verify the effective state.
3. Wait for or deliberately stop active executions according to Behnam's window plan. Stopping one execution alone does not pause its schedule.
4. Prevent the deployment pipeline/IaC from restoring a schedule during maintenance. Decide whether a maintenance parameter or a controlled post-deploy pause/check is needed.
5. Restore the exact original configuration, confirm schedules, and run or schedule one controlled catch-up after database verification.
6. Record the result and confirm retry/alert behavior.

Do not treat an expected failed sync as a pause. If Behnam explicitly chooses to accept a missed/failed run, document that decision, its alert/retry consequences, and the catch-up plan.

### Acceptance criteria

- [ ] The runbook states the Tue/Fri cron correctly and identifies applicable cleanup scheduling.
- [ ] The pause/resume method uses verified supported operations and includes effective-state checks.
- [ ] Running executions and automatic retries are accounted for.
- [ ] Deployment cannot silently resume the job during the migration window.
- [ ] Original schedules and a controlled catch-up/verification step are restored after success or recovery.

## Validation and review package

Use focused local tests for the new guard and configuration behavior. Reuse the earlier migration evidence where the underlying DDL is unchanged, but run the revised executable script against an isolated fixture to validate its new psql contract. Do not spend time re-proving points Behnam has already accepted unless a change affects them.

| Validation | Required evidence |
|---|---|
| Prompt storage | Pinned source/default/precedence findings; synthetic results; later dev result marked pending until run |
| Environment guard | Passing local case and rejected missing/wrong environment/target cases; no DDL on rejection |
| Bicep/configuration | Successful validation/rendering; persisted setting; precedence and shared-environment impact |
| Recovery | Concrete scope/connection mapping, timing estimate and complete-recovery evidence or explicit outstanding gate |
| Artifacts | Focused diff, valid links, exact executable SQL, commit location once implemented |
| Scheduling | Correct cron, verified pause/resume procedure, protection against deploy-time re-enablement |

Do not re-check the already accepted nullable unique-index semantics, constant-default table-rewrite behavior, 157 = baseline + 156 arithmetic, or scope of the narrow sequence grant solely to repeat evidence. Confirm the grant's actual application only when needed for the complete dump.

## Completion and handoff

The preparation task is ready for Behnam's review when the implementation-stage criteria above pass and every execution-stage result is explicitly marked pending rather than checked prematurely.

Provide a short response indexed to review notes 1–7, with:

- What changed or was verified.
- File and commit references.
- Local validation results and limitations.
- The remaining owner decisions or maintenance actions.
- A clear statement that no dev migration has been executed as part of preparation.

Dev execution remains owner-led. Its completion requires the full recovery prerequisites, approved maintenance coordination, actual prompt/response field verification, and the runbook's application/data checks. Behnam decides any reporting-grant changes before promotion to test or production.

## Follow-up review through `89c57d0` — 2026-09-11

**Status: not ready for dev execution.** This appended review takes precedence over earlier open-status summaries where the findings overlap. It records implementation instructions only; it does not authorize database changes or deployment.

Progress verified in this review: the uncertain-commit instructions are corrected; frozen historical-data fingerprints and complete migration checksum comparisons are included. All 30 PowerShell blocks parse when read as UTF-8, and `git diff --check` passes. Parsing does not prove that commands execute correctly. No runtime database or Azure checks were performed in this review.

### Finding 1 — P1: preserve maintenance isolation throughout deployment

**Locations:** [dev.yml](../../ChatGptForEmployees.pipelines/dev.yml), [liteLlm.bicep](../../ChatGptForEmployees.bicep/liteLlm.bicep), [jobs.bicep](../../ChatGptForEmployees.bicep/jobs.bicep), [main.dev.bicepparam](../../ChatGptForEmployees.bicep/main.dev.bicepparam), and [REVIEW-AND-CUTOVER.md](REVIEW-AND-CUTOVER.md), Steps 8b–8d and section 7.

`UploadConfigs` depends on `BicepCreate`. Consequently, infrastructure deployment can start the target revision before the new YAML is uploaded. The dev parameters also set `deployJobs=true`, so deployment reapplies normal schedules from `jobs.bicep`, undoing a manual schedule pause. The runbook's later release checks do not themselves prevent either event.

#### Code instructions and implementation guidelines

1. Trace the complete deployment order, including the shared pipeline templates, app revision activation, configuration upload, ingress, and both scheduled jobs. Record any shared template that cannot yet be inspected as an outstanding gate.
2. Implement a reviewed maintenance control that persists across the infrastructure deployment. It must keep ordinary application writers and scheduled executions stopped while allowing explicitly controlled synthetic checks. Do not rely on a manual pause that Bicep immediately overwrites.
3. Ensure the reviewed routing configuration is available before the target revision starts against the migrated database. Use a verified staged deployment or configuration prerequisite; merely restarting after uploading YAML does not eliminate the earlier startup interval.
4. If adding a Bicep maintenance parameter, wire it through the actual entry point, modules, and pipeline invocation. Verify the rendered resources enforce maintenance for existing jobs and apps. Setting `deployJobs=false` alone is not proof that existing deployed jobs stop.
5. Keep `DISABLE_SCHEMA_UPDATE=true` and both prompt-storage controls false during startup. Verify the active revision and effective configuration before releasing normal traffic. Release jobs only after database and application checks pass.
6. Document exact enter/verify/release commands, failure handling, and restoration of captured settings. Keep the target image/configuration commit reviewable before the maintenance window. Behnam retains ownership of remote execution and the window.

#### Acceptance criteria

- [ ] Pipeline ordering guarantees the reviewed YAML exists before target startup.
- [ ] A deployment during maintenance cannot restore normal traffic or either job schedule prematurely.
- [ ] Effective app/job state is checked after infrastructure deployment and before synthetic checks.
- [ ] A deployment/configuration failure leaves maintenance in effect and follows the incident procedure.
- [ ] Bicep validation/rendering and pipeline review pass; the maintenance enter/deploy/release sequence is rehearsed in an appropriate isolated environment.
- [ ] Any Azure-dependent verification remains explicitly pending until performed; prose assertions do not count as evidence.

### Finding 2 — P1: implement complete baseline and target-schema comparison

**Location:** [REVIEW-AND-CUTOVER.md](REVIEW-AND-CUTOVER.md), Step 5 before baseline resolution and Step 8a after migration.

Step 5 still checks only selected table/column presence. Step 8a repeats those checks plus one index. These checks cannot establish that the baseline is accurate or that the final database matches the pinned target. Migration ledger checksums establish source history, not actual catalog equivalence.

#### Code instructions and implementation guidelines

1. Add reviewable comparison scripts under `ChatGptForEmployees/scripts/`, with SQL executed through `psql -f` and explicit native exit-code handling. Use read-only catalog queries against the database being checked.
2. Derive the expected baseline from the exact baseline SQL in the pinned image, using an isolated reference database or a reviewed catalog manifest generated from it. Derive the final reference from the same pinned image's complete migration history and target schema. Record the digest and generation procedure.
3. Compare all expected tables and columns, including PostgreSQL types/type modifiers, nullability, defaults, primary keys, unique constraints/indexes, foreign keys and their actions, and relevant index definitions and validity. Normalize equivalent catalog representations explicitly rather than ignoring differences broadly.
4. Scope LiteLLM equivalence to vendor-managed objects. Inventory and verify intentional custom objects, including attribution tables and reporting views, separately so they are preserved rather than automatically treated as unwanted objects. Stop on unexplained differences.
5. Run the full baseline comparison after remediation and **before** resolving `20250326162113_baseline`. A nonempty unexplained diff or failed query blocks resolution. Do not move this gate after migration.
6. Run the full final comparison after deployment of all migrations but before app startup/release, alongside the existing fingerprint, ledger, checksum, and index-validity checks. Save sanitized difference reports without employee row content or credentials.
7. Validate the comparison on isolated fixtures: an equivalent schema must pass; a missing column, wrong default/type, missing unique index, and missing or altered foreign key must each fail. Do not repair differences automatically as part of verification.

#### Acceptance criteria

- [ ] A complete, reproducible baseline comparison blocks `migrate resolve --applied` on any unexplained mismatch.
- [ ] A complete pinned-target comparison blocks application release on any unexplained mismatch.
- [ ] Reference artifacts are tied to the reviewed image digest and can be reproduced without scratch-directory dependencies.
- [ ] Intended custom objects remain preserved and separately accounted for.
- [ ] Positive and deliberately mismatched fixture results demonstrate that the comparison detects meaningful schema drift.
- [ ] Runbook commands capture evidence, check failures, and mark actual dev results pending until owner execution.

### Finding 3 — P2: verify view definitions and query execution

**Location:** [REVIEW-AND-CUTOVER.md](REVIEW-AND-CUTOVER.md), Step 3.5 view capture and Step 8a view verification.

The current comparison checks only schema/name pairs. A view can retain its name while its definition changes or its query fails. Listing 10 views is not evidence that all 10 still resolve correctly.

#### Code instructions and implementation guidelines

1. Capture the complete pre-change view inventory and deterministic definitions from the catalog, for example using `pg_get_viewdef` with a consistent session/search path. Save schema, name, and definition in a format that preserves multiline text unambiguously.
2. Compare the same inventory and definitions after migration. Stop on a missing view or an unexplained definition change. Record any expected normalization explicitly.
3. Generate one read-only execution check per view using PostgreSQL identifier quoting (`format('%I.%I', schema_name, view_name)`). A pattern such as `SELECT count(*) FROM <quoted_view>` executes the query while returning no employee content. Do not substitute catalog enumeration or `LIMIT 0` for execution validation.
4. Run checks with `ON_ERROR_STOP=1`, a read-only transaction/session, and an appropriate statement timeout. Treat a timeout or query failure as an unresolved gate. Save view names, counts/status, and sanitized errors; do not export view rows.
5. Compare result counts while ordinary writers remain stopped, where unchanged counts are expected. Counts supplement definition and execution checks; they do not replace the existing historical-data fingerprints.
6. Validate locally that a same-name definition change is detected and that a view query failure stops the check. Update the runbook to invoke these scripts at the actual pre/post gates.

#### Acceptance criteria

- [ ] All 10 expected views are reconciled before execution, with their definitions captured.
- [ ] Post-migration definitions match the captured baseline or have an explicitly reviewed explanation.
- [ ] Every view query executes successfully; failures/timeouts prevent release.
- [ ] Evidence contains no employee conversation content or credentials.
- [ ] An isolated definition-change test and query-failure test demonstrate the checks work.

### Completion rule for this follow-up

Close these findings only with implementation and supporting validation evidence. Keep remote checks and owner decisions visibly pending. Updating this guide or adding commands to the runbook alone does not establish cutover readiness.

## Follow-up review of working changes after `89c57d0` — 2026-09-11

**Status: three blockers remain; not ready for dev execution.** This review covers the uncommitted implementation changes inspected after `89c57d0`, not a new implementation commit. Its findings supersede overlapping earlier status statements. The instructions below authorize no remote execution and do not themselves implement the corrections.

Validation observed: view definition/execution scripts are now implemented; all 39 PowerShell code blocks parse when read as UTF-8; `git diff --check` passes. SQL runtime tests, Bicep compilation, and Azure maintenance verification were not performed in this review. Previously reported fixture results were not independently rerun.

### Finding 1 — P1: create the baseline in the final reference database

**Location:** [REVIEW-AND-CUTOVER.md](REVIEW-AND-CUTOVER.md), Step 8a final-reference setup (reviewed lines 1143–1148).

The procedure creates an empty reference database, marks `20250326162113_baseline` applied, and then deploys later migrations. Resolving a migration does not execute its SQL. This skips creation of the baseline tables and prevents the remaining migrations from building the intended reference.

#### Code instructions and guidelines

1. For a verified empty, disposable reference database, run the pinned image's `prisma migrate deploy` directly. Let it execute all 157 migrations, including the baseline. Do not copy the existing-dev baseline-resolution procedure into the empty-reference workflow.
2. If retaining a two-step reference setup, execute the pinned baseline SQL successfully first, verify its catalog, and only then resolve that baseline and deploy the remaining migrations. Prefer the direct full-history approach for the empty reference.
3. Keep the dev and reference connection variables clearly separate. Verify the local container/database identity before any reference mutation; never reuse the dev connection URL in reference-generation commands.
4. Check each native command's exit code immediately, including container creation, readiness, migration execution, SQL-script copying, and manifest extraction. Replace the fixed startup sleep with a bounded readiness check. Preserve the failing exit status before cleanup commands can overwrite it.
5. Require successful reference generation and a nonempty, validated manifest before comparing it with dev. Capture the image digest and successful migration ledger alongside the reference. Clean up only the specifically created disposable resources.
6. Correct the statement that the currently documented sequence was executed successfully. Attach results for the corrected sequence or mark its runtime validation pending; do not carry forward unsupported evidence claims.

#### Acceptance criteria

- [ ] A fresh isolated reference builds successfully using all 157 migrations, with the baseline actually executed.
- [ ] Baseline tables exist and the final ledger has the expected successful migration names/checksums with no unresolved failures.
- [ ] Manifest extraction succeeds and produces the expected catalog coverage before any comparison is accepted.
- [ ] A failed startup, migration, copy, or extraction stops the procedure and cannot be masked by cleanup.
- [ ] The runbook separates empty-reference creation from existing-dev baseline resolution and records validation for the corrected commands.

### Finding 2 — P1: separate controlled startup from traffic and job release

**Locations:** [REVIEW-AND-CUTOVER.md](REVIEW-AND-CUTOVER.md), Steps 8b–8d (reviewed lines 1325–1337); [main.bicep](../../ChatGptForEmployees.bicep/main.bicep), [liteLlm.bicep](../../ChatGptForEmployees.bicep/liteLlm.bicep), and [jobs.bicep](../../ChatGptForEmployees.bicep/jobs.bicep).

The single `maintenanceMode=false` transition restores app scale and both normal job schedules before effective-state and application checks. The mechanism preserves the pause during migration but still releases workloads before the checks intended to authorize that release.

#### Code instructions and guidelines

1. Implement independently controlled states for app startup, ordinary user access, and scheduled jobs. Separate parameters are one option; choose names and defaults consistent with this repository and wire them through the actual pipeline and module entry points.
2. Preserve this order: database validation; target startup with normal traffic blocked and jobs paused; effective image/configuration verification; controlled synthetic application and prompt-storage checks; explicit normal-traffic release; job release and catch-up verification.
3. Define a supported, verified access restriction that allows authorized synthetic checks while blocking ordinary writers. Replica count alone cannot distinguish synthetic requests from employee traffic once the app starts. Account for LibreChat and other callers, not only direct external access to LiteLLM.
4. Keep both job schedules paused through the controlled-startup deployment. A deployment to start the app must not implicitly restore either job schedule. Verify the effective trigger state after each deployment and drain or stop existing executions separately.
5. Keep the pinned image, schema-update flag, and both prompt-storage controls unchanged between startup and release. Identify exact pipeline invocations and parameter changes for each transition; do not rely on a post-deployment manual re-pause to close an earlier release interval.
6. On failed health, effective-state, or synthetic checks, maintain access restrictions and paused jobs. Capture evidence and follow the incident route; do not reactivate the old revision against the migrated schema.
7. Update module comments, dev parameters, runbook steps, and handoff together so none still instruct operators to release jobs before checks. Keep unsupported scale/cron behavior explicitly unverified until tested.

#### Acceptance criteria

- [ ] The target can start and receive controlled synthetic requests while normal users and both scheduled jobs remain blocked.
- [ ] A startup deployment does not restore job schedules or ordinary access.
- [ ] Effective configuration and application checks pass before normal traffic is released.
- [ ] Job release occurs only after application checks pass, with captured schedules restored and catch-up handled.
- [ ] Failure-path validation demonstrates that a failed check leaves restrictions in place.
- [ ] Bicep validation/rendering and an appropriate maintenance rehearsal support the documented transitions; Azure-dependent results remain pending until performed.

### Finding 3 — P1: exclude physical column positions from schema equivalence

**Location:** [02-schema-manifest.sql](../../ChatGptForEmployees/scripts/02-schema-manifest.sql), COLUMN record generation (reviewed lines 69–70).

The manifest includes `pg_attribute.attnum` in each column record. The vendor baseline declares `sso_user_id` as the fourth column of `LiteLLM_UserTable`; remediation adds it to an existing table using `ADD COLUMN`, which appends it. The intended remediation therefore produces a different physical column order even when all required named columns and their properties match. The current comparison rejects that valid result.

#### Code instructions and guidelines

1. Remove physical ordinal position from the column equivalence record. Identify columns by schema, table, and column name, and order manifest output deterministically using those names.
2. Retain `attnum` internally where it is required for catalog joins, dropped-column filtering, or reading index/constraint definitions. Only remove it as a standalone equivalence requirement; do not remove valid catalog join keys.
3. Continue comparing types and modifiers, nullability, defaults, and all existing constraint/index checks. Preserve meaningful column order inside composite indexes and keys; that order is part of their definition and must not be normalized away.
4. Do not rebuild or reorder live tables to satisfy the manifest. Document physical table-column order as an intentional normalization, without using it to excuse other differences.
5. Add an isolated regression fixture with two paths: a fresh baseline containing `sso_user_id` in its declared position, and a pre-baseline table remediated by appending the column. Their normalized manifests must match when their logical definitions match.
6. Retain negative fixtures proving that wrong types/defaults/nullability and missing or changed indexes/foreign keys still fail. Include a composite-index column-order change to ensure meaningful ordering remains checked.
7. Regenerate the expected manifests using the revised script, update any recorded line counts or examples affected by the format, and rerun both baseline and final comparison workflows. Keep the script version tied to the captured evidence.

#### Acceptance criteria

- [ ] A logically equivalent table with different physical column positions passes comparison.
- [ ] The actual append-column remediation pattern is represented in an isolated positive fixture.
- [ ] Wrong types, defaults, nullability, constraints, and indexes still fail comparison.
- [ ] Changed composite-key/index ordering remains detectable.
- [ ] No live table rewrite or broad difference suppression is introduced to make the comparison pass.
- [ ] Runbook references and validation evidence use the corrected manifest format consistently.

### Completion and scope

Close these blockers only after the corrected implementation and relevant isolated checks pass. Keep owner-led dev execution, Azure verification, and maintenance decisions explicitly pending. This appended section is a documentation update only.

## Latest follow-up: application release and synthetic checks — 2026-09-11

**Status: two execution gaps remain; not ready for dev execution.** Reviewed the latest working changes after `89c57d0`. This section supersedes overlapping earlier status statements without changing the original acceptance requirements.

Two earlier blockers are corrected in the inspected code/instructions: final-reference setup now executes baseline SQL before resolving it, and the schema manifest excludes physical column position while retaining its catalog join keys. All 39 PowerShell blocks parse when read as UTF-8, and diff checks pass. Bicep compilation, Azure maintenance behavior, and SQL runtime results were not independently verified in this review. No files or databases were changed during the review; this subsequent update adds documentation only.

### Finding 1 — P1: validate LibreChat before releasing users and jobs

**Location:** [REVIEW-AND-CUTOVER.md](REVIEW-AND-CUTOVER.md), Step 8e release instructions (reviewed lines 1453–1464); maintenance state handling in [main.bicep](../../ChatGptForEmployees.bicep/main.bicep), [libreChat.bicep](../../ChatGptForEmployees.bicep/libreChat.bicep), and [jobs.bicep](../../ChatGptForEmployees.bicep/jobs.bicep).

The `litellm-only` state now allows direct LiteLLM checks while LibreChat and jobs remain paused. However, switching to `off` starts LibreChat and restores both job schedules before login, streaming, existing conversations, model selection, and upload checks. Direct LiteLLM success does not establish that the complete application works.

#### Code instructions and guidelines

1. Add a restricted application-validation phase between `litellm-only` and normal release. It must run LibreChat and LiteLLM for authorized testers while ordinary user access stays blocked and both scheduled jobs remain paused.
2. Select and implement a supported access restriction appropriate to the deployed architecture. Verify its effect on browser requests, authentication callbacks, streaming, and alternate access paths. Do not treat an internal LiteLLM endpoint or a running replica count as a LibreChat access restriction.
3. Extend the maintenance state or use independent controls for application startup, ordinary access, and jobs. Wire the chosen controls through the dev parameters, entry-point Bicep, modules, and actual pipeline invocation. Document a state table showing app availability, permitted callers, and job schedules at every stage.
4. Keep the reviewed image, YAML, and schema-update/prompt-storage settings unchanged during these transitions. Validate the effective restriction and job state after deployment before testers begin.
5. Run Okta login, model selection, send/stream chat, existing-conversation loading, and file-upload checks using an authorized synthetic test account and non-sensitive test data. Record pass/fail evidence without copying employee conversation content.
6. Release normal access only after the application checks pass. Restore job schedules afterward, verify no unexpected execution occurred during maintenance, and handle any required catch-up. Update Step 8e so it no longer schedules application validation after full release.
7. On failed checks, retain restricted access and paused jobs. Capture diagnostics and follow the documented incident procedure. Do not switch to `off` merely to diagnose a failure or reactivate the previous image against the upgraded database.
8. Update module comments, runbook transitions, and handoff together. Keep the exact restriction mechanism and any Azure verification explicitly pending until implemented and tested; naming another maintenance state alone is insufficient.

#### Acceptance criteria

- [ ] LibreChat and LiteLLM can run for authorized validation without admitting ordinary users or resuming jobs.
- [ ] The pipeline preserves the restriction and both paused schedules throughout the validation deployment.
- [ ] Login, model selection, streaming, conversation loading, and upload checks pass before normal release.
- [ ] Failed checks leave restricted access and paused schedules in effect.
- [ ] Normal access and job release are explicit, ordered actions with effective-state verification.
- [ ] Bicep validation/rendering and a suitable rehearsal support the chosen mechanism; pending Azure evidence is clearly identified.

### Finding 2 — P2: make the internal synthetic test executable

**Location:** [REVIEW-AND-CUTOVER.md](REVIEW-AND-CUTOVER.md), Step 8d controlled checks (reviewed lines 1409–1430).

The runbook explicitly leaves the mechanism for reaching LiteLLM's internal endpoint unspecified. A list of candidate execution locations cannot be followed as an operator procedure. The location, authentication, exact request, and evidence checks must be resolved before the maintenance window.

#### Code instructions and guidelines

1. Choose a verified execution location inside the network that can resolve and reach LiteLLM's internal FQDN, such as an approved running container or a prepared temporary validation workload. Confirm its existence, tools, network access, and required operator permissions in advance. Do not depend on executing into a stopped container.
2. Add a reviewable validation script under `ChatGptForEmployees/scripts/` and document the exact owner-run invocation, working directory, prerequisites, and arguments. Use parameterized target values and verify the dev target explicitly. Avoid commands that require operators to reconstruct missing details during the outage.
3. Obtain the required LiteLLM credential through the approved secret mechanism. Do not embed keys in the script, commit them, print them, or include them in captured diagnostics. Specify the minimum permissions needed for the synthetic request and any read-only database verification.
4. Implement bounded health checks and a synthetic chat request against the internal endpoint using an available configured model. Define request/connect timeouts and explicit failure handling. Make the request identifiable with a unique non-sensitive marker or supported request identifier, and record the identifier without dumping response content.
5. Verify that the test produced the expected request and a corresponding spend-log record. Allow bounded time for asynchronous logging. A missing row is an unresolved test result, not evidence that prompt storage is disabled.
6. Query the matching synthetic record specifically and verify `messages` and `response` against the documented empty representations. Return only a content-free result such as matched-row count and empty/nonempty status. The latest-five-rows query alone is insufficient to identify this test.
7. Stop on an unreachable endpoint, authentication failure, failed completion, absent/ambiguous log record, timeout, or unexpectedly populated content fields. Keep maintenance restrictions in effect and follow the incident route; do not release workloads after an inconclusive result.
8. Document cleanup for any temporary validation workload and synthetic artifacts, including who performs it and when. Keep cleanup scoped to resources created for this test and preserve the required audit evidence.
9. Validate the script in an isolated environment for success, unreachable endpoint, rejected authentication, missing log row, and unexpected content-storage results. Mark the actual dev test pending until owner execution; local success is not proof of Azure reachability.

#### Acceptance criteria

- [ ] The runbook names one prepared execution location and exact runnable commands, with required permissions and secret handling.
- [ ] Internal DNS/connectivity and necessary tools are verified before the maintenance window.
- [ ] Health and synthetic completion checks have bounded waits and explicit failure exits.
- [ ] The synthetic spend-log row is identified unambiguously and its content fields are verified without exporting their contents.
- [ ] Missing evidence or any failed check blocks release and leaves maintenance controls in effect.
- [ ] Success and relevant failure cases are validated locally; actual dev results remain pending until performed.
- [ ] Temporary resource cleanup and sanitized evidence locations are documented.

### Handoff and completion

Provide the revised code and runbook together, with validation results and remaining owner prerequisites. Close these findings only after their implementation and relevant checks pass. Behnam retains ownership of remote execution and the maintenance window; this documentation update does not execute or approve a cutover.

## Latest follow-up: synthetic execution identity and image readiness — 2026-09-11

**Status: two execution-instruction gaps remain.** The restricted `validation` state and synthetic-check job are implemented in the inspected working changes after `89c57d0`. This section supersedes overlapping earlier status statements; it does not establish readiness for remote execution.

Review validation: all 43 PowerShell blocks parse, the new Python script passes syntax parsing, and diff checks pass. Runtime tests and Azure restrictions were not independently verified in this review. No files or databases were changed during that review; this subsequent update is documentation only.

### Finding 1 — P1: follow the exact synthetic job execution to verified success

**Location:** [REVIEW-AND-CUTOVER.md](REVIEW-AND-CUTOVER.md), Step 8d job start/result commands (reviewed lines 1425–1433).

The procedure starts a job and then selects `[0]` from execution history. That does not establish that the inspected execution is the one just started. It also reads `properties.template.containers[0].exitCode`, which is not a documented execution-result field in the [Azure jobs execution schema](https://learn.microsoft.com/en-us/rest/api/resource-manager/containerapps/jobs-executions/list?view=rest-resource-manager-containerapps-2025-07-01). A null result must not be interpreted as success.

#### Code instructions and implementation guidelines

1. Capture structured output from `az containerapp job start` and check its native exit code immediately. Extract and validate the returned execution name or resource ID using the installed CLI's verified response shape. Stop if the identity is missing or ambiguous; do not fall back to the first history entry.
2. Store that execution identity in the sanitized evidence for this test. Poll only that execution using a supported exact-execution lookup, or filter history by its exact identity and require exactly one match. Verify the relevant CLI/API contract before documenting the final command.
3. Implement a bounded polling loop with a deadline and interval. Require an explicit terminal success status. Treat failed, stopped, unknown, missing, ambiguous, and timed-out results as blocking outcomes; a successful CLI lookup is not a successful job execution.
4. Retrieve logs for that same execution and its intended container/replica. Require the script's final PASS result and synthetic marker from that execution. Do not accept a PASS line from an earlier run, unscoped logs, or a still-running execution.
5. If numeric process exit evidence is needed, obtain it through a verified replica/runtime diagnostic interface rather than the container template. Never coerce a missing exit-code property to zero. Terminal job success and the matching script result remain required gates.
6. Keep automatic retries disabled as currently configured. A manual rerun must receive a new execution identity and its own evidence; it must not overwrite or conceal a failed result requiring investigation.
7. Update the runbook and the Python script's invocation/docstring together so neither still recommends `[0]` or the unsupported template exit-code query. Keep maintenance restrictions and paused jobs in effect on every inconclusive or failed result.
8. Validate the polling logic with representative mocked responses: successful current execution, failed current execution with an older successful run present, missing identity, nonterminal timeout, CLI failure, and absent/mismatched PASS logs. Confirm the actual response/log retrieval shape in an appropriate Azure rehearsal before the window.

#### Acceptance criteria

- [ ] The execution returned by `job start` is captured and used for all subsequent status/log checks.
- [ ] An older successful execution cannot satisfy the current run's gate.
- [ ] Polling has a deadline and requires explicit terminal success plus the matching script PASS evidence.
- [ ] Null/missing fields, failed commands, ambiguity, timeout, or missing logs block progression to application validation.
- [ ] Runbook and script instructions use supported execution/result fields consistently.
- [ ] Local failure-case checks pass; actual Azure command/response verification remains pending until performed.

### Finding 2 — P2: verify the updated jobs image before starting the synthetic check

**Locations:** [dev.yml](../../ChatGptForEmployees.pipelines/dev.yml), `BuildJobsImage`; [Dockerfile.cleanup](../../ChatGptForEmployees/scripts/Dockerfile.cleanup); [jobs.bicep](../../ChatGptForEmployees.bicep/jobs.bicep); and [REVIEW-AND-CUTOVER.md](REVIEW-AND-CUTOVER.md), Step 8d prerequisites.

The new validation script is copied into the jobs image by `Dockerfile.cleanup`. The cutover instructions do not require `BuildJobsImage` to complete successfully before starting the job. An older image can therefore be used even if the app/configuration deployment stages have completed, leaving the synthetic job without the reviewed script.

#### Code instructions and implementation guidelines

1. Add successful completion of `BuildJobsImage` for the exact reviewed source commit to the synthetic-test prerequisites. Check the actual stage result and artifact identity; completion of `BicepCreate`, `UploadConfigs`, or `DeployLiteLLM` does not establish jobs-image readiness.
2. Record the produced registry image digest and source commit. Prefer deploying the synthetic job with that immutable image digest. If the shared mutable tag is retained, define and verify how the execution's actual image digest is matched to the reviewed build; tag equality alone is insufficient evidence.
3. Account for pipeline ordering: the job resource may be deployed before its image is built. Ensure the job's effective image reference is updated or verified after the build and before manual execution. Keep both scheduled jobs paused during this work.
4. Verify the built image contains `05-synthetic-litellm-check.py` and its required dependencies at the configured working path. Compare a script hash or equivalent build provenance with the reviewed source. Do not use a live synthetic request merely to discover whether the image contains the file.
5. If adding pipeline validation or digest outputs, use the existing build/deployment conventions and pass artifact identity explicitly. Do not introduce an unrelated deployment route or release scheduled jobs as a side effect of preparing the validation image.
6. Document exact readiness checks and evidence locations in Step 8d. A failed/skipped build, unavailable image, mismatched digest/source, or missing script must stop the procedure before `job start`.
7. Validate a positive built-image case and a negative stale/missing-script image case. Keep registry/deployed-execution verification explicitly pending until performed with the appropriate access.

#### Acceptance criteria

- [ ] `BuildJobsImage` succeeds for the reviewed commit before the synthetic job starts.
- [ ] The image used by the synthetic execution is tied to that build by digest or equivalent verified provenance.
- [ ] The image contains the reviewed script and required dependencies at the configured path.
- [ ] Failed/skipped builds, stale images, or missing scripts block job execution.
- [ ] Image preparation and verification preserve maintenance restrictions and paused schedules.
- [ ] The runbook records the build/run identity, image digest, and readiness evidence alongside the exact synthetic execution identity.

### Completion and handoff

Close these findings with the corrected implementation/instructions and supporting checks, not documentation assertions alone. Keep Azure rehearsal, effective access restrictions, and owner-led dev results visibly pending until verified. Behnam retains ownership of remote execution and the maintenance window.

## Final image-verification correction — 2026-09-11

The remaining mutable-tag fallback is removed from `REVIEW-AND-CUTOVER.md` Step 8d and the pipeline's related guidance. Cutover now requires `jobsImageDigest` to match the recorded build digest; checking what `:latest` resolves to before execution is no longer accepted.

The executable preflight validates the recorded SHA-256 digest and requires the deployed synthetic job's full image reference to match it exactly. The captured job-start execution template must also report that reference before its result can be accepted. This catches a different job image introduced between preflight and start. Keep the pin unchanged through validation and release. Missing or mismatched execution-image evidence blocks progression and requires investigation with maintenance still in effect.

Validation performed: all 44 PowerShell blocks parse; local comparison checks accept the exact digest and reject a mutable tag, wrong digest, and missing image; diff checks pass. These are local syntax/comparison checks, not Azure integration tests. The actual job-start response shape, Bicep compilation, execution/log retrieval, and maintenance behavior remain pending Azure verification before cutover.

- [x] Remove the mutable-tag exception from cutover instructions and pipeline guidance.
- [x] Require the recorded digest on the deployed job and captured execution template.
- [x] Check matching, wrong, mutable, and missing image-reference cases locally.
- [ ] Verify the job-start response includes the expected execution image and confirm the complete procedure in Azure before the maintenance window.

No image digest was invented or deployed, and no database changes were made. Ordinary deployment defaults remain unchanged; this correction makes the existing digest-pin option mandatory for the cutover procedure.
