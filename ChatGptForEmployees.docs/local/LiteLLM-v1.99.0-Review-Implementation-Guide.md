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
