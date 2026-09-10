# LiteLLM v1.99.0 dev migration review and cutover

## Status and scope

No remote DDL, migration resolution, migration deployment, Azure mutation,
application request, or external message has been performed as part of this
document or its preparation. All validation was run against ephemeral local
Docker containers. Files were created only under the tracked repository paths
listed in the implementation guide; no scratch or dump files were committed.

| Requested item | Status |
|---|---|
| 1. Verify exact prompt/response storage behavior | Complete for the pinned image's source; dev result pending owner-led migration |
| 2. Replace the database-name-only environment guard | Complete; SQL and local pass/fail evidence below |
| 3. Persist manual-migration mode in Bicep | Complete; `DISABLE_SCHEMA_UPDATE=true` added to `liteLlm.bicep` |
| 4. Rollback scope and timing | Documented below; full recovery rehearsal (sequences, owners, ACLs) still owner-led |
| 5. Recovery boundaries and partial failure | Documented below |
| 6. Artifacts in the repository | This file, the handoff, and the SQL are the tracked artifacts |
| 7. Scheduling correction and job pause procedure | Documented below |

## 1. Prompt/response storage: verified source behavior

Pinned image: `ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5`.
Traced directly in the image's installed source
(`/app/.venv/lib/python3.13/site-packages/litellm/proxy/spend_tracking/spend_tracking_utils.py`
and `/app/.venv/lib/python3.13/site-packages/litellm/proxy/proxy_server.py`).

**The controlling setting** is `general_settings.store_prompts_in_spend_logs`
(tracked YAML, or the DB-stored config table), gated through
`_should_store_prompts_and_responses_in_spend_logs()`. If that key is absent
or not a truthy value there, the function falls back to the environment
variable `STORE_PROMPTS_IN_SPEND_LOGS` (via `get_secret_bool`).

**Default when absent, null, or not explicitly true:** `False` — metadata-only.
Both `True` and the case-insensitive string `"true"` are accepted as on;
anything else (including `None`) is off.

**What is actually written when off** (`_get_response_for_spend_logs_payload`,
`_get_messages_for_spend_logs_payload`): the literal JSON string `"{}"` in
both the `response` and `messages` columns — not SQL `NULL`, not an omitted
field.

**Non-obvious finding:** even when storage IS enabled, `messages` is only ever
populated for `call_type == "_arealtime"`. Every other call type — including
ordinary streaming and non-streaming chat completions — writes `"{}"` to
`messages` regardless of the setting. `response`, by contrast, is populated
for any call type once storage is enabled.

**Reload/precedence, verified in `proxy_server.py`
(`_update_general_settings`):** if the tracked YAML explicitly sets
`store_prompts_in_spend_logs`, that YAML value **always wins** over a
DB-cached value on every periodic config reload — this is intentional
upstream behavior (the code comment states this exists so CI/CD-deployed
config changes take effect without a manual `/config/update` call). The
DB-stored value only takes effect when the YAML never sets the key at all.
**Conclusion: setting this key explicitly in `litellm_routing_config.yaml` is
reload-safe.**

**`turn_off_message_logging` is a separate, independent control**
(`litellm/litellm_core_utils/redact_messages.py`,
`should_redact_message_logging` / `perform_redaction`), with its own
precedence order: (1) a per-request dynamic parameter, (2) request headers
(`litellm-disable-message-redaction` / `litellm-enable-message-redaction`),
(3) the global `litellm.turn_off_message_logging` setting. It redacts
`response` and request-body content even when `store_prompts_in_spend_logs`
is on. **The two flags are not interchangeable** — do not treat one as proof
of the other's effect.

**Tracked configuration change:** none required. `store_prompts_in_spend_logs`
is not set in `litellm_routing_config.yaml`, and its documented default is
already the safe, metadata-only behavior. If this is ever set to `true` for a
specific need, it must be set explicitly in the tracked YAML (never left to
the DB-stored path) so the reload-safety guarantee above applies.

**Post-migration verification (owner-led, pending):** after the dev migration
and after sending synthetic, non-sensitive requests (never employee
conversations), run:

```sql
SELECT messages, response
FROM public."LiteLLM_SpendLogs"
ORDER BY "startTime" DESC
LIMIT 5;
```

Identify the synthetic test rows specifically (by `end_user`/`model` — the
latest five rows alone may include unrelated traffic). Record a content-free
summary such as "N rows inspected, both fields read `{}`" — never paste
returned content into tickets, logs, or chat. If either field is populated,
stop promotion immediately, confirm `store_prompts_in_spend_logs` is
explicitly `false` in the deployed config, and give Behnam the finding before
any further action — turning storage off does not delete already-stored
content, and any cleanup requires his decision. **This status is: pending dev
execution.**

## 2. Environment guard

The old guard checked only `current_database() IN ('litellm', 'dev_rehearsal')`.
Every environment's database is named `litellm`, so that check alone cannot
distinguish dev from test or prod — it is retained only as a secondary,
non-authoritative check.

The corrected script (`ChatGptForEmployees/scripts/01-baseline-remediation.sql`)
requires an explicit `-v target_env=dev` argument, verified through a
transaction-local `romchat.target_env` setting (`set_config`/`current_setting`)
rather than interpolating `:'target_env'` directly inside a `DO $$ ... $$`
body, which psql does not support.

**Supported invocation (dev):**

```powershell
# PGHOST, PGPORT, PGDATABASE=litellm, PGUSER, PGPASSWORD, PGSSLMODE=require
# supplied securely in the operator's environment beforehand.
psql -X -v ON_ERROR_STOP=1 -v target_env=dev -f ChatGptForEmployees/scripts/01-baseline-remediation.sql
```

**Local rehearsal invocation** uses the same script against an isolated
`postgres:16-alpine` container (database name `dev_rehearsal`), never the real
dev host.

**Verified locally** (see Task 1 of the implementation plan for exact
commands): missing, blank, `test`, and `prod` values for `target_env` all
abort with a nonzero `psql` exit code before any DDL runs, leaving the fixture
schema completely unchanged (`LiteLLM_CredentialsTable` absent,
`messages`/`response` columns absent). `target_env=dev` against the fixture
succeeds and produces exactly the expected schema.

**Limitation, stated explicitly:** passing `target_env=dev` expresses operator
intent only. It does not, by itself, prove the psql connection is actually to
the dev server — an operator must separately verify `PGHOST`, the connected
database, and the connected role against `psql-db-cgfe-dev.postgres.database.azure.com`
before running this script. No cloud IP is hard-coded as identity anywhere in
the script.

## 3. Manual-migration mode (Bicep)

`{ name: 'DISABLE_SCHEMA_UPDATE', value: 'true' }` has been added to the
LiteLLM container's `env` array in `ChatGptForEmployees.bicep/liteLlm.bicep`.

**Shared-module impact:** `liteLlm.bicep` is instantiated once per environment
by `main.bicep`, but the module body (including this `env` array) is
identical across Dev, Test, and Prod. This change therefore takes effect in
**all three environments** on their next respective deploy, not only dev.

**Precedence:** a `general_settings.disable_prisma_schema_update` value in
`litellm_routing_config.yaml` (the single config file deployed to every
environment) would take precedence over this environment variable. Confirmed
absent as of this change — `general_settings` in both the committed and local
config currently contains only `master_key`, `database_url`, and
`allow_user_requests`.

**Standing requirement:** startup will no longer repair an outdated schema
automatically. **Every future LiteLLM image upgrade, in every environment,
requires an explicit reviewed migration step (this document's section 2/4
procedure) executed before the new image is allowed to start against the
database.** If an operator skips this and the new image starts anyway, check
for: the container crash-looping (a P3005-style error in `az containerapp
logs show`), or — if the wrapper's own auto-recovery ran anyway — an
unexpectedly-populated `_prisma_migrations` table that nobody reviewed. Either
signal means stop and audit before continuing.

Disabling startup schema mutation removes that mutation path as one
additional defense alongside the `attribution` schema living outside
Prisma's management. It does not, by itself, guarantee that no future
migration or manual change can ever affect `attribution` — that guarantee
still depends on `attribution` never being declared in LiteLLM's own
`schema.prisma`.

## 4. Rollback scope and timing

Two distinct recovery paths, not one:

| Path | Scope and consequences |
|---|---|
| **A — Recover `litellm` onto the original server** | Restore the verified pre-change backup into a **new, empty** recovery database on the same server. Validate it there, then perform an owner-led connection/name transition. `librechat_rag` on that same server is untouched throughout. Owners, ACLs, sequence values, and views on the restored copy still need explicit verification before cutover. |
| **B — Redirect workloads to a PITR-restored server** | The restored server has a new FQDN and its own copies of every database on that server, including a **historical** copy of `librechat_rag`. This is not a revision re-pin. Repointing RAG workloads to that restored copy would move them to historical embeddings — do not do this as part of a `litellm`-only recovery. |

**Connection-string/IaC consumers of `postgresql.bicep`'s outputs** (traced
directly in `main.bicep`):

| Output | Consumers |
|---|---|
| `liteLlmConnectionString` | `liteLlm.bicep` (`databaseUrl` param); `jobs.bicep` (both the Okta sync and cleanup jobs, `databaseUrl` param) |
| `hostname`, `adminUser`, `adminPassword` | `jobs.bicep` (cleanup job's separate `librechat_rag` connection: `postgresHost`/`postgresUser`/`postgresPassword` params); `ragApi.bicep` (same three, plus `ragApiConnectionString`) |
| `ragApiConnectionString` | `ragApi.bicep` only |

No LibreChat container-app Bicep file consumes `postgresql.bicep` outputs
directly (LibreChat itself talks to LiteLLM's HTTP endpoint and to Mongo, not
to this Postgres server).

Recovering via **Path A** requires no IaC changes (same server, same
connection name after the owner-led transition). Recovering via **Path B**
requires updating the `postgresAdminPassword`/host references that flow into
`liteLlm.bicep`, `jobs.bicep`, and `ragApi.bicep` — concretely, whatever
parameter file or Key Vault reference `main.bicep`'s `postgresql` module
consumes for `adminPassword`/host would need to point at the new server's
FQDN, followed by a redeploy of `liteLlm`, both jobs, and `ragApi`.

Writers (LiteLLM, both jobs) must stay stopped for the duration of either
path. Preserve failure-state evidence (logs, catalog state) before starting
recovery. `attribution`'s tables and both rollup views must be restored and
verified alongside the `public` schema — they live in the same database, so a
`litellm`-database-level restore includes them, but they need their own
row-count/view-resolution check afterward (do not assume `pg_restore --clean
--if-exists` alone proves new objects absent from the old archive were
removed — it does not).

**Estimated recovery timeline — planning estimates only, not measured, not an
agreed SLA:**

| Phase | Estimate |
|---|---|
| Fault assessment, stop/drain writers | 10–15 min |
| Azure PITR restore completion + restored-server network config | 15–30 min (Azure-side, largely unmeasured) |
| Database extraction/restore + validation (Path A) | 15–30 min |
| IaC/secret changes + redeploy (Path B only) | 15–30 min additional |
| Data/application/reporting/job checks before resuming traffic | 15–20 min |

These numbers are unvalidated planning placeholders pending an actual owner-run
rehearsal against a real Azure PITR restore; replace them with measured
timings once that rehearsal happens. **Full backup/restore validation
(sequence values, ownership, permissions, database-level settings) has not yet
happened against a complete dump — the local Docker-only rehearsal covers
schema and row-data mechanics, not Azure recovery or sequence/ACL recovery.**

## 5. Recovery boundaries and partial failure

Two distinct boundaries, each with a different recovery consequence:

**Boundary 1 — Remediation commit.** Before `01-baseline-remediation.sql`'s
`COMMIT`, any statement failure rolls back everything in that transaction —
the live schema is unchanged. **After** it commits, the live schema has
changed (the new table and columns exist) even though migration history is
still absent. At that point, an image-only re-pin does **not** reverse
anything — the only way back is the tested restore path in section 4.

**Boundary 2 — Baseline resolution / migration-history creation.** Once
`prisma migrate resolve --applied 20250326162113_baseline` has run, the
script's own history guard (`to_regclass('public._prisma_migrations') IS NOT
NULL`) blocks any rerun of the remediation script. If `prisma migrate deploy`
then partially succeeds before failing on some later migration, **do not**:
delete rows from `_prisma_migrations` to "restart", remove the history guard,
or resolve a failed migration as applied to make the error go away. Any of
those actions can leave the schema and the ledger permanently inconsistent
with each other.

| State | Correct response |
|---|---|
| Pre-commit failure (remediation transaction) | Transaction auto-rolled-back; safe to fix and rerun once the underlying issue is understood |
| Remediation committed | Live schema changed; treat as boundary 1. Any further failure is now a rollback-path decision, not a "just rerun it" decision |
| Baseline resolved | History now exists; the remediation script permanently refuses to rerun (by design) |
| Migration partially applied (deploy failed partway) | **Stop.** Capture the ledger (`_prisma_migrations`), the Postgres error, and the current catalog state. Do not rerun, do not delete history, do not auto-resolve. Follow the tested restore path in section 4 |

An owner-reviewed **forward repair** (fixing the one failed migration in
place and re-attempting only it) may be possible in some cases, but it is a
separate, specifically-reviewed procedure each time it's needed — never the
default response, and never permission to bypass the history guard on a
future run. The standard incident route is: stop, capture state, restore.

## 6. Artifacts in the repository

- `ChatGptForEmployees/scripts/01-baseline-remediation.sql` — canonical,
  reviewed, locally-validated execution artifact. All invocations in this
  document reference this exact file.
- `ChatGptForEmployees.docs/local/REVIEW-AND-CUTOVER.md` — this document.
- `ChatGptForEmployees.docs/local/BEHNAM-HANDOFF.md` — short review response.
- `ChatGptForEmployees.bicep/liteLlm.bicep` — the `DISABLE_SCHEMA_UPDATE`
  change.

No dumps, no `migration-review/` scratch content, and no credentials are
included in this commit. A local commit is not, by itself, evidence that a
remote reviewer can access it — the commit/branch reference and any
separately-authorized sharing step are recorded in the handoff document.

## 7. Scheduling and job pause procedure

**Confirmed schedules** (`ChatGptForEmployees.bicep/jobs.bicep`):

| Job | Cron | Meaning |
|---|---|---|
| Okta attribution sync (`job-cgfe-okta-sync-<env>`) | `0 5 * * 2,5` | Tuesday and Friday, 05:00 UTC |
| Orphaned-file cleanup (`job-cgfe-cleanup-<env>`) | `0 2 * * *` | Nightly, 02:00 UTC |

The maintenance window for the dev migration must avoid both. A previously
discussed nightly-cadence change to the Okta sync job **did not merge** — the
schedule above (twice-weekly, not nightly) is what's actually deployed.

**Pause/resume mechanism:** Azure Container Apps Jobs scheduled triggers do
not have a documented "pause" API call. The verified, supported approach is
to update the job's `scheduleTriggerConfig` via `az containerapp job update`
to a state that will not fire during the window, and confirm the effective
state afterward — this must be checked against the currently deployed CLI/API
version before the actual maintenance window (see the [Azure Container Apps
job command reference](https://learn.microsoft.com/en-us/cli/azure/containerapp/job?view=azure-cli-latest)),
not assumed from this document. This step is **owner-led** (Azure CLI access
is not available in this preparation environment).

**Procedure (owner-executed):**

1. `az containerapp job execution list` for both jobs — capture trigger type,
   schedule, and any currently-running executions before changing anything.
2. Apply the verified pause mechanism; re-run the same list command to
   confirm no new scheduled execution can start.
3. If an execution is already running when the window starts, wait for it to
   finish or stop it deliberately per Behnam's window plan — stopping one
   execution does not, by itself, pause its schedule.
4. Confirm the deployment pipeline cannot silently redeploy and restore the
   original schedule mid-window (check whether a maintenance parameter is
   needed, or whether a post-deploy pause/check step suffices, given the
   pipeline's `bicepDetectFolder: ''` setting means every push re-runs
   `BicepCreate` regardless of what changed).
5. After database verification, restore the exact original schedule
   configuration, confirm it via the same list command, and run or schedule
   one controlled catch-up sync if the Tuesday/Friday window was missed.
6. Record the result, including whether any run alerted or retried
   unexpectedly.

If Behnam explicitly decides to accept a missed/failed sync run instead of
pausing, record that decision explicitly here, along with its alert/retry
consequence and the catch-up plan — an expected failure is not the same thing
as a pause and must not be described as one.
