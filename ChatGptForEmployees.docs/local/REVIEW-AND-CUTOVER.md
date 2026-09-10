# LiteLLM v1.99.0 dev migration review and cutover

## Status and scope

No remote DDL, migration resolution, migration deployment, Azure mutation,
application request, or external message has been performed against dev,
Azure, or any other real environment, as part of this document or its
preparation. All validation — including the synthetic application requests
in §1a and a container-run `prisma migrate deploy` against a local ephemeral
database (also §1a) — was run against ephemeral local Docker containers only;
none of it touched dev, test, prod, or any Azure resource. Files were created
only under the tracked repository paths listed in the implementation guide;
no scratch or dump files were committed.

| Requested item | Status |
|---|---|
| 1. Verify exact prompt/response storage behavior | Complete for the pinned image's source, corroborated by an executed local synthetic runtime test against the pinned image (§1a); dev result against real traffic still pending owner-led migration |
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
`_get_messages_for_spend_logs_payload`): an empty JSON object `{}` in
both the `response` and `messages` columns — not SQL `NULL`, not an omitted
field, and not the two-character string `"{}"`.

**Non-obvious finding:** even when storage IS enabled, `messages` is only ever
populated for `call_type == "_arealtime"`. Every other call type — including
ordinary streaming and non-streaming chat completions — writes an empty JSON
object `{}` to `messages` regardless of the setting. `response`, by contrast, is populated
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

### 1a. Synthetic runtime test against the pinned image (executed, this session)

The static source tracing above was corroborated by actually running the
pinned image and inspecting real database rows, in an isolated local Docker
environment — not the dev database.

**Setup:** a dedicated Docker bridge network (`litellm-synth-test-net`; not
`--network host`, which is unreliable on Docker Desktop for Windows) with two
throwaway containers: a fresh `postgres:16-alpine` (`synth-test-pg`, empty
`synth_test` database) and the pinned image
`ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5`
(`synth-test-litellm`), started with this minimal config (no
`store_prompts_in_spend_logs` key set, i.e. relying on the documented
default):

```yaml
model_list:
  - model_name: "synthetic-test-model"
    litellm_params:
      model: gpt-3.5-turbo
      mock_response: "MOCK-RESPONSE-ROMCHAT-SYNTHETIC-TEST-2026"

general_settings:
  master_key: sk-synthetic-test-key
  database_url: os.environ/DATABASE_URL
```

The `mock_response` field is LiteLLM's own documented test feature: the proxy
returns the canned string directly, without calling any real provider, so no
Azure OpenAI credentials were needed and no real prompt content ever left the
container. **This harness deliberately omitted `DISABLE_SCHEMA_UPDATE`** so
the container would build its own schema from scratch against the fresh
empty database — the opposite configuration from §3/§3a below, where that
same env var is set specifically to prevent this automatic migration. The
container ran its own startup Prisma migration against the
empty fresh database (all migrations up through
`20260819000000_add_spend_log_timestamps` applied cleanly) and reported
`/health/liveliness` = `200` after about 30 seconds. Seeing the auto-migration
actually run here — and confirming in §3a that it does **not** run when
`DISABLE_SCHEMA_UPDATE=true` — is direct evidence that the startup
auto-migration path §3 closes is real, not theoretical.

**Three synthetic requests were sent** (all content is one of the fixed
markers given in this task's instructions, never real conversation content),
using distinct `end_user` values so the resulting rows could be identified
unambiguously:

| Request | `end_user` | Result |
|---|---|---|
| Non-streaming chat completion | `synthetic-test-user-nonstream` | HTTP 200, `content: "MOCK-RESPONSE-ROMCHAT-SYNTHETIC-TEST-2026"` |
| Streaming chat completion (`stream: true`) | `synthetic-test-user-stream` | HTTP 200, SSE chunks reassembling to the same mock string, terminated by `data: [DONE]` |
| Undefined model (`does-not-exist-model`) | `synthetic-test-user-fail` | HTTP 400, `"Invalid model name passed in model=does-not-exist-model. Call /v1/models to view available models for your key."` |

**Database inspection**, after polling until the async spend-log writer had
flushed (all three rows appeared within the first 5-second poll interval):

```
           end_user            |        model         | messages | response |  call_type
-------------------------------+----------------------+----------+----------+-------------
 synthetic-test-user-fail      | does-not-exist-model | {}       | {}       |
 synthetic-test-user-stream    | gpt-3.5-turbo        | {}       | {}       | acompletion
 synthetic-test-user-nonstream | gpt-3.5-turbo        | {}       | {}       | acompletion
(3 rows)
```

**Observations:**

- Both the non-streaming and streaming successful requests wrote the literal
  `{}` to `messages` and `response`, exactly matching the source-traced
  default-off behavior above (call type is not `_arealtime`, so `messages`
  is `{}` unconditionally, and storage is off by default so `response` is
  also `{}`).
- The undefined-model request **did produce a `LiteLLM_SpendLogs` row**
  (contrary to an assumption that a routing failure produces no row at all).
  Its `messages` and `response` fields are likewise `{}`, and its `call_type`
  is empty rather than `acompletion` — consistent with the same
  metadata-only, default-off behavior; the failed-routing path did not leak
  the synthetic marker text (`"SYNTHETIC-MARKER-FAIL-ROMCHAT"`) into either
  column.
- No other inspected column exposed request or response content for any of
  the three rows.

**What this does and does not prove:** this validates the default-off
prompt/response storage path against the pinned image's *actual runtime
behavior* — not just its source code — for three concrete request shapes
(successful non-streaming, successful streaming, and a failed/undefined-model
path), in an isolated, disposable local environment built specifically for
this test. It does **not** replace the still-pending real dev-database
verification with real application traffic against the actual deployed
config and database — that check remains **pending owner-led execution**, as
stated above, because only that check confirms behavior against the real
deployed `litellm_routing_config.yaml`, the real `STORE_PROMPTS_IN_SPEND_LOGS`
environment configuration (if any), and real request volume/shapes from
LibreChat itself, none of which this synthetic harness reproduces.

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

Note: the script's own header comment (inside
`ChatGptForEmployees/scripts/01-baseline-remediation.sql` itself) shows the
bare-filename form `-f 01-baseline-remediation.sql`, written for an operator
whose shell is already inside `ChatGptForEmployees/scripts/`. Every invocation
in this document uses the repo-root-relative form
(`-f ChatGptForEmployees/scripts/01-baseline-remediation.sql`) instead, since
that's the form that actually resolves when running from the repo root, which
is how every command in this runbook is written to be run.

**Verified locally**, using an isolated `postgres:16-alpine` container
(`litellm-guard-test`, database `dev_rehearsal`) on a dedicated Docker bridge
network (`litellm-guard-test-net`), loaded with a pre-remediation fixture (four
bare tables — `LiteLLM_OrganizationTable`, `LiteLLM_UserTable`,
`LiteLLM_VerificationToken`, `LiteLLM_SpendLogs` — with no other columns).
Each case below ran the corrected script from the repo root against that
fixture:

```powershell
$psqlBase = @('-h','litellm-guard-test','-U','postgres','-d','dev_rehearsal')

# Case: missing target_env entirely
psql @psqlBase -X -v ON_ERROR_STOP=1 -f /repo/ChatGptForEmployees/scripts/01-baseline-remediation.sql
```
**Result:** `ERROR:  syntax error at or near ":"` (the unsubstituted
`:'target_env'` literal is invalid inside `set_config()`'s argument list),
exit code 3.

```powershell
# Case: blank
psql @psqlBase -X -v ON_ERROR_STOP=1 -v target_env= -f /repo/ChatGptForEmployees/scripts/01-baseline-remediation.sql
```
**Result:** `ERROR:  Wrong target environment; remediation aborted` (raised
inside the `DO $$` block), exit code 3.

```powershell
# Case: test
psql @psqlBase -X -v ON_ERROR_STOP=1 -v target_env=test -f /repo/ChatGptForEmployees/scripts/01-baseline-remediation.sql
```
**Result:** `ERROR:  Wrong target environment; remediation aborted`, exit
code 3.

```powershell
# Case: prod
psql @psqlBase -X -v ON_ERROR_STOP=1 -v target_env=prod -f /repo/ChatGptForEmployees/scripts/01-baseline-remediation.sql
```
**Result:** `ERROR:  Wrong target environment; remediation aborted`, exit
code 3.

After all four rejection cases, the fixture schema was confirmed unchanged:
`SELECT to_regclass('public."LiteLLM_CredentialsTable"');` returned NULL, and
`SELECT count(*) FROM information_schema.columns WHERE table_name='LiteLLM_SpendLogs' AND column_name IN ('messages','response');`
returned `0`.

```powershell
# Case: dev (passing)
psql @psqlBase -X -v ON_ERROR_STOP=1 -v target_env=dev -f /repo/ChatGptForEmployees/scripts/01-baseline-remediation.sql
```
**Result:**
```
BEGIN
SET
SET
SET
 set_config
-----------
 dev
(1 row)

 DO
 LOCK TABLE
 CREATE TABLE
 ALTER TABLE
 ALTER TABLE
 ALTER TABLE
 CREATE INDEX
 CREATE INDEX
 ALTER TABLE
 COMMIT
Exit code: 0
```

Post-check confirmed the expected schema: `LiteLLM_CredentialsTable` now
appears in `pg_tables` alongside the four fixture tables, and
`information_schema.columns` returns both `messages` and `response` for
`LiteLLM_SpendLogs`.

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

**`liteLlm.json` is already stale, independent of this change.** The
checked-in generated ARM template `ChatGptForEmployees.bicep/liteLlm.json` was
not regenerated alongside this `liteLlm.bicep` edit — it was already out of
sync with `liteLlm.bicep` before this change (confirmed against a prior,
unrelated `liteLlm.bicep` edit that also isn't reflected in the JSON). This is
not a blocking gap: the deploy pipeline consumes `bicepParamFile` →
`main.bicep` directly at deploy time, never this checked-in JSON file. Noted
here for completeness only.

### 3a. Validation limitations and the executed `DISABLE_SCHEMA_UPDATE` test

**(a) `bicep build` was not run locally, and cannot be in this environment.**
Neither the `bicep` CLI nor the `az` CLI is available in this preparation
environment (confirmed absent when this change was made — `Get-Command bicep`
and `Get-Command az` both returned nothing). Syntax validation of
`liteLlm.bicep` has therefore not happened locally and will not happen here;
it will run in the deploy pipeline's existing `insert-stage-bicep-whatif.yml@templates`
stage on the next push of this branch. Treat that pipeline stage — not this
document — as the actual syntax gate for this file.

**(b) The `DISABLE_SCHEMA_UPDATE=true` claim above was directly tested**, not
just asserted from documentation. The pinned image was run with that env var
set against a completely fresh, empty database, in an isolated Docker
environment (not dev):

```powershell
docker network create disable-schema-test-net
docker run --rm -d --name disable-schema-test-pg --network disable-schema-test-net -e POSTGRES_DB=disable_schema_test -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:16-alpine
docker run --rm -d --name disable-schema-test-litellm --network disable-schema-test-net -e DATABASE_URL="postgresql://postgres:postgres@disable-schema-test-pg:5432/disable_schema_test" -e DISABLE_SCHEMA_UPDATE=true -e LITELLM_MASTER_KEY=sk-disable-schema-test ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5
docker logs disable-schema-test-litellm --tail 100
docker run --rm --network disable-schema-test-net -e PGPASSWORD=postgres postgres:16-alpine psql -h disable-schema-test-pg -U postgres -d disable_schema_test -Atc "SELECT to_regclass('public.\"LiteLLM_UserTable\"');"
```

**Observed:** the container started and stayed running — it did not
crash-loop. On startup it detected the schema difference and *printed* the
full list of DDL it would need to run, but never executed any of it:

```
Changes to DB Schema detected
Required SQL commands:
CREATE TYPE "JobStatus" AS ENUM ('ACTIVE', 'INACTIVE');
CREATE TABLE "LiteLLM_BudgetTable" ( ... );
CREATE TABLE "LiteLLM_CredentialsTable" ( ... );
... [~150 CREATE TYPE / CREATE TABLE / CREATE INDEX statements — the entire
     LiteLLM schema — printed as text, never executed] ...
```

Direct query against the live database confirmed this: `SELECT
to_regclass('public."LiteLLM_UserTable"')` returned an empty result (table
absent), and follow-up checks confirmed zero rows in `pg_tables` for schema
`public` and no `_prisma_migrations` table either — the database was left
completely untouched.

Because the tables genuinely do not exist, the rest of startup logged a
series of background errors — each one a real, expected consequence of
skipping schema creation on a truly empty database, not a defect in the env
var itself:

```
16:08:14 - LiteLLM Proxy:WARNING: proxy_server.py:8617 - Could not read coordination_redis from the database: The table `public.LiteLLM_Config` does not exist in the current database.
16:08:15 - LiteLLM Proxy:WARNING: proxy_server.py:1090 - Password migration skipped: The table `public.LiteLLM_UserTable` does not exist in the current database.
16:08:16 - LiteLLM Proxy:ERROR: proxy_server.py:7366 - ...ProxyConfig:_init_mcp_servers_in_db - The table `public.LiteLLM_MCPServerTable` does not exist in the current database.
16:08:16 - LiteLLM Proxy:ERROR: cloudzero_endpoints.py:279 - Error checking CloudZero status: The table `public.LiteLLM_Config` does not exist in the current database.
16:08:16 - LiteLLM Proxy:ERROR: vantage_endpoints.py:261 - Error checking Vantage status: The table `public.LiteLLM_Config` does not exist in the current database.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:4000 (Press CTRL+C to quit)
16:08:17 - LiteLLM Proxy:ERROR: utils.py:5658 - Error getting LiteLLM_SpendLogs row count: relation "LiteLLM_SpendLogs" does not exist
```

The process completed startup rather than crash-looping, and both
`/health/liveliness` and `/health/readiness` returned HTTP 200 (readiness
body: `{"status":"healthy","db":"connected"}`) despite zero application
tables existing in the database.

**Conclusion: `DISABLE_SCHEMA_UPDATE=true` works as claimed** — it suppresses
schema mutation entirely rather than merely warning while still applying it.
This directly confirms the "Standing requirement" claim above against actual
runtime behavior, not just documentation.

**Additional operational caveat found by this test, beyond the original
claim:** on a genuinely unmigrated database, a container running with
`DISABLE_SCHEMA_UPDATE=true` reports itself healthy (`/health/readiness` →
200, `"db":"connected"`) while functionally broken for any database-backed
request. Health-probe status alone is not sufficient evidence that a cutover
succeeded — after any real cutover, verify actual table presence (e.g. the
`to_regclass` query used above, or row counts on key tables) in addition to
probe status, not instead of it.

Environment torn down immediately after
(`docker stop`/`docker network rm`); no state persisted from this test.

### 3b. Tag-vs-digest cutover risk

`ChatGptForEmployees.bicep/main.dev.bicepparam` currently pins `liteLlmImage`
to the mutable tag `ghcr.io/berriai/litellm:v1.99.0`, **not** the exact digest
(`sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5`)
that every finding in this runbook — including the `DISABLE_SCHEMA_UPDATE`
test in §3a and the synthetic storage test in §1a — was verified against. The
implementation plan's own Global Constraints note that during this review the
`v1.99.0` tag was observed to resolve to different content than this pinned
digest.

**Recommendation:** before the maintenance window, either switch
`main.dev.bicepparam` to reference the digest directly, or re-resolve the
`v1.99.0` tag and diff its digest against
`sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5`
immediately before cutover. Do not assume the tag still resolves to the exact
image validated by this document.

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
