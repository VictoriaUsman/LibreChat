# LiteLLM v1.99.0 dev migration review and cutover

## Status and scope

No remote DDL, migration resolution, migration deployment, Azure mutation,
application request, or external message has been performed against dev,
Azure, or any other real environment, as part of this document or its
preparation. All validation — including the synthetic application requests
in §1a, the OR-gate corroboration in §1b, the shipped-configuration
corroboration in §1c, and a container-run `prisma migrate deploy`/`migrate
resolve` against a local ephemeral database (§1a and §2a) — was run against
ephemeral local Docker containers only; none of it touched dev, test, prod, or
any Azure resource. Files were created only under the tracked repository
paths listed in the implementation guide; no scratch or dump files were
committed.

| Requested item | Status |
|---|---|
| 1. Verify exact prompt/response storage behavior | Complete for the pinned image's source, corroborated by executed local synthetic runtime tests against the pinned image (§1a default-off behavior; §1b the OR-gate risk; §1c the actual shipped `false`/`false` configuration). `store_prompts_in_spend_logs: false` and `STORE_PROMPTS_IN_SPEND_LOGS=false` are both now explicitly pinned (config files and `liteLlm.bicep`) because the general setting alone cannot block the env var; dev result against real traffic still pending owner-led migration |
| 2. Replace the database-name-only environment guard | Complete; SQL and local pass/fail evidence below |
| 3. Persist manual-migration mode in Bicep | Complete; `DISABLE_SCHEMA_UPDATE=true` added to `liteLlm.bicep`; the executable cutover sequence using it is §2a |
| 4. Rollback scope and timing | Documented below; Path A (recover onto the original server) is the only currently implementable path — Path B requires IaC work not yet done; full recovery rehearsal (sequences, owners, ACLs) still owner-led |
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

**This is an OR-gate, not an override.** `_should_store_prompts_and_responses_in_spend_logs()`
returns `True` immediately if `general_settings.store_prompts_in_spend_logs`
is true. **Otherwise — including when that setting is explicitly `False` — it
falls through and returns whatever `STORE_PROMPTS_IN_SPEND_LOGS` evaluates to.**
An earlier version of this document stated that an explicit YAML `false`
blocks a `true` environment variable ("anything else, including `None`, is
off"). **That was incorrect and has been corrected here.** A `false` general
setting does not short-circuit the function to `False`; it only skips the
first `True` branch and lets the environment variable decide the outcome
unconditionally.

**Decision table** (source-level, `general_settings.store_prompts_in_spend_logs`
× `STORE_PROMPTS_IN_SPEND_LOGS`), matching the addendum's verified table and
re-confirmed against actual runtime behavior in §1b below:

| General setting | Environment boolean | Storage enabled |
|---|---|---|
| Absent | Absent | No |
| False | Absent | No |
| False | True | **Yes** |
| Absent | True | **Yes** |
| True | False | **Yes** |
| False | False | No |

Both `True` and the case-insensitive string `"true"` are accepted as on for
either control.

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

**Tracked configuration change made (this correction):** because the general
setting cannot block a `true` environment variable, leaving
`store_prompts_in_spend_logs` unset in the tracked YAML (the prior "no change
required" position) left storage exposed to any `STORE_PROMPTS_IN_SPEND_LOGS=true`
introduced by a shared environment default, a manual container-app env
override, or human error — with no YAML-level defense against it. Both
controls are now pinned explicitly:

- `general_settings.store_prompts_in_spend_logs: false` added to
  `ChatGptForEmployees/config/litellm_routing_config.yaml` (the single config
  file deployed to every environment) and, separately, to
  `ChatGptForEmployees/config/litellm_routing_config.local.yaml` — this second
  file is **untracked** (its own header reads "DO NOT COMMIT, DO NOT DEPLOY")
  and exists only on this developer's machine for local rehearsal; it is not
  a deployed control and is not equivalent to the committed
  `litellm_routing_config.yaml` change.
- `{ name: 'STORE_PROMPTS_IN_SPEND_LOGS', value: 'false' }` added to the
  LiteLLM container's `env` array in `ChatGptForEmployees.bicep/liteLlm.bicep`
  (alongside `DISABLE_SCHEMA_UPDATE`), so no conflicting env-var override —
  present or future, shared-module or manual — can re-enable storage.

**Shared-environment impact (mirroring §3's note for `DISABLE_SCHEMA_UPDATE`):**
both of these tracked changes land in Test and Prod on their next respective
deploy too, not only dev — `litellm_routing_config.yaml` is the single file
deployed to every environment, and `liteLlm.bicep`'s `env` array (where
`STORE_PROMPTS_IN_SPEND_LOGS` was added) is identical across Dev, Test, and
Prod instantiations of the module.

With both pinned `false`, the decision table above only ever lands on the
"No" rows for this deployment. Per the reload-precedence finding already
verified below, the tracked YAML value wins over any DB-cached value on
reload, so this pin is reload-safe. **This closes the OR-gate risk for the
values we control; it does not change upstream's function itself.**

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
empty fresh database (all migrations applied cleanly, ending at the pinned
image's actual final migration, `20260819000000_shadow_eval_max_budget` —
corrected here from an earlier transcription that misnamed this as
`20260819000000_add_spend_log_timestamps`, conflating it with the adjacent,
differently-dated `20260818000000_add_spend_log_timestamps`; verified by
listing `/app/litellm-proxy-extras/litellm_proxy_extras/migrations/` in the
pinned image directly — see the reproduction command in the addendum) and
reported `/health/liveliness` = `200` after about 30 seconds. Seeing the auto-migration
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

### 1b. OR-gate test against the pinned image (executed, this session)

The review addendum's decision table (§1) was independently re-verified by
actually running the pinned image with the one combination that matters
most: an explicit tracked-YAML `false` **and** a `true` environment variable,
reusing the §1a harness pattern.

**Setup:** a dedicated Docker bridge network (`orgate-test-net`) with a fresh
`postgres:16-alpine` (`orgate-test-pg`, empty `orgate_test` database, no
`DISABLE_SCHEMA_UPDATE` — same auto-migration rationale as §1a) and the pinned
image `ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5`
(`orgate-test-litellm`), started with:

```yaml
model_list:
  - model_name: "orgate-test-model"
    litellm_params:
      model: gpt-3.5-turbo
      mock_response: "MOCK-RESPONSE-ORGATE-TEST-2026"

general_settings:
  master_key: sk-orgate-test-key
  database_url: os.environ/DATABASE_URL
  store_prompts_in_spend_logs: false
```

...and the container's environment set to `STORE_PROMPTS_IN_SPEND_LOGS=true`.
Again, `mock_response` means no real provider credentials and no real prompt
content ever left the container. The proxy came up healthy after the same
auto-migration path as §1a (ending at `20260819000000_shadow_eval_max_budget`).

**One request sent** (non-streaming chat completion, `end_user=orgate-test-user`,
message containing the fixed marker `ORGATE-TEST-MARKER`), then the resulting
row was polled from `LiteLLM_SpendLogs`.

**Database inspection — actual output, verbatim:**

```
     end_user     |     model     |  call_type  | messages |                                                                                                                                                                                                                                              response
------------------+---------------+-------------+----------+----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 orgate-test-user | gpt-3.5-turbo | acompletion | {}       | {"id": "chatcmpl-620f1aa1-c288-430e-af4f-754deb4c7c5b", "model": "orgate-test-model", "usage": {"total_tokens": 30, "prompt_tokens": 10, "completion_tokens": 20, "prompt_tokens_details": null, "completion_tokens_details": null}, "object": "chat.completion", "choices": [{"index": 0, "message": {"role": "assistant", "content": "MOCK-RESPONSE-ORGATE-TEST-2026", "tool_calls": null, "function_call": null}, "finish_reason": "stop"}], "created": 1789058623, "system_fingerprint": null}
(1 row)
```

**Result: confirmed.** With `general_settings.store_prompts_in_spend_logs: false`
explicitly set in the tracked YAML and `STORE_PROMPTS_IN_SPEND_LOGS=true` in
the environment, the `response` column was populated with the full response
payload — not `{}` — proving the explicit YAML `false` did **not** block the
`true` environment variable. `messages` remained `{}`, consistent with the
independently-documented, unrelated `_arealtime`-only behavior for that
column. This directly corroborates the addendum's decision table and the
"False / True → Yes" row above against actual runtime behavior, not just
source tracing.

Environment torn down immediately after (`docker rm -f
orgate-test-litellm orgate-test-pg`; `docker network rm orgate-test-net`); no
state persisted from this test.

**This is why both controls are now pinned `false` together** (see the
"Tracked configuration change made" note above) — pinning only the YAML side,
as the pre-correction version of this document effectively did by leaving the
key unset, would not have been sufficient even if the key had been set to
`false`, because this test shows that alone does not block the env var.

### 1c. Synthetic runtime test of the actual shipped configuration (executed, this session)

§1a tested the default-absent case, and §1b tested `store_prompts_in_spend_logs: false`
paired with `STORE_PROMPTS_IN_SPEND_LOGS=true` specifically to prove the
OR-gate bug. Neither one tests the configuration this branch actually ships:
`store_prompts_in_spend_logs: false` in the tracked YAML **and**
`STORE_PROMPTS_IN_SPEND_LOGS=false` in the environment, together. This section
closes that gap with real evidence rather than a source-level inference from
the two prior tests.

**Setup:** a dedicated Docker bridge network (`shipped-test-net`) with a fresh
`postgres:16-alpine` (`shipped-test-pg`, empty `shipped_test` database) and
the pinned image
`ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5`
(`shipped-test-litellm`), started with the container's environment set to
`STORE_PROMPTS_IN_SPEND_LOGS=false` and this config (mounted read-only,
`mock_response` again meaning no real provider credentials and no real prompt
content ever left the container):

```yaml
model_list:
  - model_name: "shipped-test-model"
    litellm_params:
      model: gpt-3.5-turbo
      mock_response: "MOCK-RESPONSE-SHIPPED-TEST-2026"

general_settings:
  master_key: sk-shipped-test-key
  database_url: os.environ/DATABASE_URL
  store_prompts_in_spend_logs: false
```

The container came up healthy (`/health/liveliness` → 200) after its own
startup migration against the fresh database (same auto-migration path as
§1a/§1b; this harness again omitted `DISABLE_SCHEMA_UPDATE` deliberately, for
the same reason given in §1a).

**One request sent** (non-streaming chat completion, `end_user=shipped-test-user`,
message containing the fixed marker `SHIPPED-CONFIG-TEST-MARKER`), returning
HTTP 200 with `content: "MOCK-RESPONSE-SHIPPED-TEST-2026"`.

**Database inspection — actual output, verbatim:**

```
     end_user      |     model     |  call_type  | messages | response
-------------------+---------------+-------------+----------+----------
 shipped-test-user | gpt-3.5-turbo | acompletion | {}       | {}
(1 row)
```

**Result: confirmed.** With the exact configuration this branch ships —
`store_prompts_in_spend_logs: false` in the tracked YAML **and**
`STORE_PROMPTS_IN_SPEND_LOGS=false` in the environment — both `messages` and
`response` read the empty JSON object `{}`, matching the "False / False → No"
row of the decision table in §1 against actual runtime behavior, not just
source tracing or inference from §1a/§1b individually.

Environment torn down immediately after (`docker rm -f shipped-test-litellm
shipped-test-pg`; `docker network rm shipped-test-net`); no state persisted
from this test.

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

## 2a. Full cutover sequence

This is the single ordered, executable operator procedure for the dev
migration. It exists because §2 (environment guard) and §4 (rollback scope)
are necessary background but, individually, neither is a step-by-step
sequence — this section is what an operator actually runs, in order, without
reconstructing commands from scratch files or conversation history.

**Every command below assumes a PowerShell session, working directory at the
repo root** (the same directory this file's other invocations assume), with
`PGHOST`, `PGPORT`, `PGDATABASE=litellm`, `PGUSER`, `PGPASSWORD`, and
`PGSSLMODE=require` already exported securely in the operator's environment
(never inline on any command line, never committed). All exit-code checks
below use PowerShell's `$LASTEXITCODE` after each native command.

**⚠️ Do not wrap steps 4 onward in one single transaction / one script run.**
`20260415120000_health_check_latest_per_model_index` uses `CREATE INDEX
CONCURRENTLY`, which PostgreSQL refuses to run inside a transaction block.
`prisma migrate deploy` (step 7) already applies each migration in its own
transaction — the danger this warning guards against is an operator wrapping
the whole sequence (remediation + resolve + deploy) in a manual `BEGIN`/`COMMIT`
of their own to make it feel "atomic." Don't. Each step below is already
scoped to its own transaction where one is needed (the remediation script
has its own internal `BEGIN`/`COMMIT`; migration resolution and `migrate
deploy` are separate, independently-committing operations).

**Step 1 — Environment and image verification.**

```powershell
# Confirm the psql connection target is the real dev host, not a rehearsal fixture.
psql -X -v ON_ERROR_STOP=1 -Atc "SELECT current_database(), inet_server_addr(), current_user;"
if ($LASTEXITCODE -ne 0) { throw "psql connectivity check failed; stop." }
```

Manually compare the printed host/IP against
`psql-db-cgfe-dev.postgres.database.azure.com`'s resolved address. This is a
human verification step — the script cannot prove server identity by itself
(§2's stated limitation).

**Distinguish two things explicitly, and record both — this is what Follow-up
1 requires before proceeding:**

1. **The currently deployed revision** — what `ca-litellm-dev` is actually
   running right now, pre-upgrade. Capture it in full, not just the image:

   ```powershell
   New-Item -ItemType Directory -Force -Path "$env:TEMP\romchat-cutover" | Out-Null
   az containerapp show -n ca-litellm-dev -g rg-dev-shared --query "{image:properties.template.containers[0].image, env:properties.template.containers[0].env, revision:properties.latestRevisionName, scale:properties.template.scale}" -o json | Tee-Object -Variable currentRevisionState
   if ($LASTEXITCODE -ne 0) { throw "Failed to capture the currently deployed revision; stop." }
   $currentRevisionState | Out-File -FilePath "$env:TEMP\romchat-cutover\ca-litellm-dev-pre-cutover-revision.json" -Encoding utf8
   ```

   This file is the recovery reference (what to compare against if something
   goes wrong) and is also what Step 8's restart guidance means by "the
   previous revision" that must **not** be reactivated once the database is
   migrated.

2. **The intended target artifact** — the pinned digest
   `ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5`,
   with the Bicep changes already made in this repo
   (`DISABLE_SCHEMA_UPDATE=true` and `STORE_PROMPTS_IN_SPEND_LOGS=false` in
   `liteLlm.bicep`) — this is **not yet deployed** as of this step. Confirm
   `ChatGptForEmployees.bicep/main.dev.bicepparam`'s `liteLlmImage` currently
   points at the mutable `v1.99.0` tag, not this digest — that is the true
   state as of this step, and nothing before Step 2b changes it. **Step 2b,
   below, is where this runbook switches that value to the digest, sets
   `maintenanceState = 'paused'`, and commits both together** (§3b, §8.1) —
   deploying the target artifact at zero replicas *before* the database
   migration runs, not after. Do not treat that switch as optional or already
   done, and do not assume the tag still resolves to the exact image
   validated by this document in the meantime.

Compare `currentRevisionState.image` above against the target digest. If they
already match, this environment has already been upgraded — stop and
reconcile before proceeding; this runbook assumes a pre-upgrade starting
state.

**Step 2 — Confirm complete recovery prerequisites are met.**

Verify, and record confirmation of each, before proceeding:

- A verified, restorable pre-change backup of the `litellm` database exists
  (Azure PITR is continuously available per §4's recovery paths, but confirm
  the specific point-in-time is recent and restorable — do not assume).
- The owner (Behnam) has approved the maintenance window and is reachable for
  the duration.
- §7's job-pause procedure has been applied for both `job-cgfe-okta-sync-dev`
  and `job-cgfe-cleanup-dev` (confirmed via `az containerapp job show`, not
  merely applied and assumed).
- No other writer (application traffic, ad-hoc scripts) can reach the `litellm`
  database during the window.

**Stop condition:** if any of the above is not true, do not proceed past this
step.

**Step 2b — Enter maintenance state `'paused'` (Bicep-enforced primary
mechanism, Follow-up 1 & its working-changes correction, §8.1).** Before the
manual scale-down in Step 3 below, commit and push
`ChatGptForEmployees.bicep/main.dev.bicepparam` with **both** `liteLlmImage`
switched to the pinned digest (§3b — do this now, not at the old,
no-longer-current 8b(i)) **and** `maintenanceState = 'paused'`, in the same
commit. This is the primary mechanism, not Step 3's manual `az` command:
because it is declared in Bicep, no subsequent redeploy during the window
can silently undo it the way it could undo a manual
`--min-replicas`/`--cron-expression` change (§8.1). Watch the pipeline
through `BicepCreate`/`UploadConfigs`/`DeployLiteLLM`, then verify effective
state before continuing:

```powershell
az containerapp show -n ca-litellm-dev -g rg-dev-shared --query "{image:properties.template.containers[0].image, scale:properties.template.scale}" -o json
az containerapp show -n ca-librechat-dev -g rg-dev-shared --query "properties.template.scale" -o json
az containerapp job show -n job-cgfe-okta-sync-dev -g rg-dev-shared --query "properties.configuration.scheduleTriggerConfig.cronExpression" -o tsv
az containerapp job show -n job-cgfe-cleanup-dev -g rg-dev-shared --query "properties.configuration.scheduleTriggerConfig.cronExpression" -o tsv
```

**Stop condition:** proceed only once LiteLLM's `image` is the pinned
digest, LiteLLM's and LibreChat's `scale` are both `{min:0,max:0}`, and both
job cron expressions read `0 0 31 2 *`. This is Azure-CLI-dependent and
owner-led, like every other `az` step in this document — not executed in
this preparation environment.

**Step 3 — Stop writers.**

```powershell
# Scratch files this runbook writes during the real cutover go outside the
# repo working tree, never at the repo root — this directory is not tracked
# and is not part of the commit.
New-Item -ItemType Directory -Force -Path "$env:TEMP\romchat-cutover" | Out-Null

# Record the current scale settings BEFORE changing anything, so Step 8's
# restart has real values to restore instead of an unfilled placeholder.
az containerapp show -n ca-litellm-dev -g rg-dev-shared --query "properties.template.scale" -o json | Tee-Object -Variable originalScale
if ($LASTEXITCODE -ne 0) { throw "Failed to capture original scale settings; stop before scaling down." }
$originalScale | Out-File -FilePath "$env:TEMP\romchat-cutover\ca-litellm-dev-original-scale.json" -Encoding utf8
```

**This is now defense-in-depth, not the primary mechanism (Follow-up 1,
§8.1).** Step 2b's Bicep-declared `maintenanceState = 'paused'` deploy
already forces `ca-litellm-dev` (and `ca-librechat-dev`) to 0/0 scale in a
way a later redeploy cannot silently undo; this manual command covers the
gap before that deploy completes, or if an operator needs to react
immediately without waiting for a pipeline run. **Note (unverified):**
`--min-replicas 0 --max-replicas 0`
below has not been verified against the real Azure CLI/API in this
preparation environment (no `az` CLI access — see §3a(a)). It is the
intuitive way to stop a container app from accepting connections, but it has
not been confirmed that Container Apps accepts `--max-replicas 0` for this
app's scale configuration. If it is rejected or behaves unexpectedly, a more
conservative, separately-verifiable alternative is `--min-replicas 0
--max-replicas 1` combined with deliberately deactivating the current
revision (`az containerapp revision deactivate`), which stops routed traffic
without depending on a zero-max-replica scale
setting.

```powershell
# Scale the LiteLLM container app to zero so it cannot open new connections
# or run its own startup path against the database during remediation.
az containerapp update -n ca-litellm-dev -g rg-dev-shared --min-replicas 0 --max-replicas 0
if ($LASTEXITCODE -ne 0) { throw "Failed to scale down ca-litellm-dev; stop." }
```

Confirm zero running revisions/replicas via `az containerapp replica list`
before continuing. Both scheduled jobs are already paused from Step 2.

**Step 3.5 — Capture pre-remediation baseline.**

Everything captured here, while writers are stopped, is what Step 8a's
required gate compares against — a mismatch there stops the procedure
outright (§5, and Follow-up 3). Row counts alone (the previous version of
this step) cannot detect a changed value in an existing row, only a changed
row *count* — the fingerprint further below is what actually closes that
gap.

**PowerShell quoting note, applies to every SQL command in this section and
the rest of this document:** backslash is not PowerShell's escape character
inside a double-quoted string. `psql -c "SELECT ... public.\"Table\" ..."`
looks like it embeds a double-quoted Postgres identifier, but PowerShell
treats the unescaped `"` as the end of the string — the argument silently
splits into two garbled pieces instead of one SQL string, and psql never
sees valid SQL. Confirmed with a local argument-capture test (a stub `psql`
function that echoes `$args`): the old form for this exact query produced two
broken arguments, not one. Every command below that needs a double-quoted
identifier is written into a `.sql` file in this session's scratch directory
and run with `-f`, which sidesteps the whole class of bug rather than hand-
tuning PowerShell escaping. A command using only single-quoted SQL string
literals (no double-quoted identifiers) has no such bug and is left as `-c`.

```powershell
# Row counts -- supporting evidence only now; the fingerprint below is the
# actual required gate.
@'
SELECT 'LiteLLM_SpendLogs' AS table_name, count(*) FROM public."LiteLLM_SpendLogs"
UNION ALL SELECT 'LiteLLM_UserTable', count(*) FROM public."LiteLLM_UserTable"
UNION ALL SELECT 'LiteLLM_VerificationToken', count(*) FROM public."LiteLLM_VerificationToken"
UNION ALL SELECT 'LiteLLM_OrganizationTable', count(*) FROM public."LiteLLM_OrganizationTable";
'@ | Set-Content -Path "$env:TEMP\romchat-cutover\01-pre-row-counts.sql" -Encoding utf8
psql -X -v ON_ERROR_STOP=1 -f "$env:TEMP\romchat-cutover\01-pre-row-counts.sql" | Tee-Object -FilePath "$env:TEMP\romchat-cutover\pre-remediation-row-counts.txt"
if ($LASTEXITCODE -ne 0) { throw "Failed to capture pre-remediation row counts; stop." }

# Attribution rollup views -- unquoted lowercase identifiers only, no double-quoted
# identifier, so this one was never affected by the quoting bug; left as -c.
psql -X -v ON_ERROR_STOP=1 -c "SELECT 'attribution.v_spend_by_dept_week' AS view_name, count(*) FROM attribution.v_spend_by_dept_week UNION ALL SELECT 'attribution.v_spend_by_dept_month', count(*) FROM attribution.v_spend_by_dept_month;" | Tee-Object -FilePath "$env:TEMP\romchat-cutover\pre-remediation-row-counts.txt" -Append
if ($LASTEXITCODE -ne 0) { throw "attribution rollup views did not resolve pre-remediation; stop and investigate before proceeding." }
```

**All previously-documented views must resolve, not just the two attribution
rollups above (Follow-up 3).** 10 views were previously documented as
existing (8 in `public`, 2 in `attribution` — the two just counted). Record
the actual current list and count rather than assuming the prior number still
holds:

```powershell
psql -X -v ON_ERROR_STOP=1 -Atc "SELECT table_schema, table_name FROM information_schema.views WHERE table_schema IN ('public','attribution') ORDER BY 1,2;" | Tee-Object -FilePath "$env:TEMP\romchat-cutover\pre-remediation-views.txt"
if ($LASTEXITCODE -ne 0) { throw "Failed to enumerate views pre-remediation; stop." }
```

**Stop condition:** if this doesn't come back as 10 rows (8 `public` + 2
`attribution`), stop and reconcile before proceeding — either the previously-
documented count is stale or something on this host already differs from
what was reviewed, and either way Step 8a's later view check cannot be
trusted against an unreconciled baseline.

**View definitions and execution — required gate, not name-list-only
(Follow-up 3, §8.3).** A same-named view can silently change its query; the
10-row list above only catches a missing or added view. Capture full
definitions now, and confirm every view still actually executes before
remediation runs:

```powershell
psql -X -v ON_ERROR_STOP=1 -v target_schemas=public,attribution -Atf ChatGptForEmployees/scripts/03-view-inventory.sql | Set-Content -Path "$env:TEMP\romchat-cutover\pre-remediation-view-definitions.txt" -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw "Failed to capture pre-remediation view definitions; stop." }
psql -X -v ON_ERROR_STOP=1 -v target_schemas=public,attribution -f ChatGptForEmployees/scripts/04-view-execution-check.sql
if ($LASTEXITCODE -ne 0) { throw "A view failed to execute before remediation even began; stop and investigate -- do not proceed on a baseline that is already broken." }
```

**⚠️ `pre-remediation-view-definitions.txt` must survive unmodified to Step
8a**, exactly like `03-fingerprint-frozen.sql`'s output above — it is the
frozen pre-migration reference the post-migration capture is diffed against.

**Full historical-data fingerprint (Follow-up 3).** This is what actually
detects a changed value in an existing row, not just a changed row count.
Rather than hand-listing the ~19 original table names (error-prone, and this
runbook has already been caught transcribing a migration name wrong once —
see Finding 5), generate one deterministic fingerprint query per table
currently in `public`/`attribution` directly from the live catalog:

```powershell
@'
SELECT format(
  'SELECT %L::text AS table_name, md5(coalesce(string_agg(md5(t.*::text), '''' ORDER BY %s), ''__EMPTY__'')) AS fingerprint FROM (SELECT %s FROM %I.%I) t;',
  n.nspname || '.' || c.relname,
  coalesce(pk.pk_cols, all_cols.col_list),
  all_cols.col_list,
  n.nspname, c.relname
) AS fingerprint_sql
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN LATERAL (
  SELECT string_agg(quote_ident(a.attname), ', ' ORDER BY a.attnum) AS col_list
  FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
) all_cols ON true
LEFT JOIN LATERAL (
  SELECT string_agg(quote_ident(a.attname), ', ' ORDER BY a.attname) AS pk_cols
  FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
  WHERE i.indrelid = c.oid AND i.indisprimary
) pk ON true
WHERE n.nspname IN ('public','attribution') AND c.relkind = 'r'
ORDER BY 1;
'@ | Set-Content -Path "$env:TEMP\romchat-cutover\02-generate-fingerprint-sql.sql" -Encoding utf8
psql -X -v ON_ERROR_STOP=1 -Atc (Get-Content "$env:TEMP\romchat-cutover\02-generate-fingerprint-sql.sql" -Raw) | Set-Content -Path "$env:TEMP\romchat-cutover\03-fingerprint-frozen.sql" -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw "Failed to generate the frozen fingerprint SQL; stop." }
```

Because this generator runs **before** `01-baseline-remediation.sql`, the
per-table queries it writes into `03-fingerprint-frozen.sql` can only
reference columns that exist right now — they cannot possibly select
`messages`, `response`, `sso_user_id`, `organization_id`, `created_by`, or
`updated_by` (the columns remediation is about to add), so Follow-up 3's
required exclusion of remediation-added columns happens automatically, with
no hand-maintained exclusion list to keep in sync. This pattern (generate the
per-table fingerprint SQL once from the live catalog, freeze it to a file,
reuse the exact same file for the post-migration comparison) was verified
against a local ephemeral Postgres fixture built from
`01-baseline-remediation.sql`'s actual tables/columns: the frozen file,
generated once before any schema change, produced byte-identical fingerprint
output both immediately after generation and after simulating remediation
plus several *unrelated* later migrations (new columns added to an original
table, plus an entirely new table) — confirming the frozen queries genuinely
ignore anything added after they were captured. The same fixture confirmed
the fingerprint changes when an existing row's value is edited and when a row
is deleted, so it does detect both failure modes Follow-up 3 named, not just
row loss.

**⚠️ `03-fingerprint-frozen.sql` must survive unmodified from this step to
Step 8a.** Regenerating it post-migration instead of reusing this exact file
would defeat the purpose — a freshly-generated version would include every
column the 157 migrations added, hiding a real change to original data
underneath them. It already lives outside the repo working tree
(`$env:TEMP\romchat-cutover\`, per this document's no-scratch-files-in-the-
commit policy), same as every other file this step writes.

```powershell
psql -X -v ON_ERROR_STOP=1 -f "$env:TEMP\romchat-cutover\03-fingerprint-frozen.sql" | Tee-Object -FilePath "$env:TEMP\romchat-cutover\pre-remediation-fingerprints.txt"
if ($LASTEXITCODE -ne 0) { throw "Failed to capture pre-remediation fingerprints; stop." }
```

All of the above (row counts, view list, and fingerprints) land in
`$env:TEMP\romchat-cutover\` — that directory is the actual baseline Step
8a's required gate compares against.

**Step 4 — Run `01-baseline-remediation.sql`.**

Exact invocation from §2, run from the repo root:

```powershell
psql -X -v ON_ERROR_STOP=1 -v target_env=dev -f ChatGptForEmployees/scripts/01-baseline-remediation.sql
if ($LASTEXITCODE -ne 0) { throw "Remediation script failed or aborted (see §5 boundary 1) — do not proceed to Step 5." }
```

**Expected result:** the script's own `BEGIN`/`COMMIT`-wrapped output (see §2's
"Case: dev (passing)" transcript) ending in `COMMIT` and exit code `0`.

**Stop/recovery condition — three distinct cases (Follow-up 4).** A nonzero
client exit does **not** by itself prove the server rolled back: a network or
connection failure can happen *after* the server committed but *before* the
client received confirmation, leaving a genuinely unknown outcome, not a
confirmed rollback. Treat "any nonzero exit = safe to rerun" as false —
determine which of these three cases actually occurred before doing anything
else:

| Case | How to recognize it | Action |
|---|---|---|
| **1. Confirmed rollback** | psql reported the error directly (a `RAISE EXCEPTION` message from the script's own guards, a syntax error, a constraint violation) and the connection is still usable to verify state immediately after. | Safe to diagnose and rerun once the cause is understood — this is what §5 boundary 1 describes. Do **not** proceed to Step 5. |
| **2. Confirmed commit** | The script's output actually printed `COMMIT` and `$LASTEXITCODE` is `0`. | This is the success path (named here for contrast, not a failure case) — proceed to Step 5. |
| **3. Unknown outcome** | The connection dropped, timed out, or psql exited nonzero with a network/connection error rather than a clear SQL error and confirmable-still-connected state (e.g. no `COMMIT` printed, no explicit `RAISE EXCEPTION`, and/or the connection itself is now unusable). | **Do not assume rollback and do not rerun.** Keep writers stopped, capture whatever error output exists, reconnect read-only, and inspect the actual catalog state directly — e.g. `SELECT to_regclass('public."LiteLLM_CredentialsTable"');` (via the same `-f` file pattern as Step 3.5/8a, not `-c`, since it needs a double-quoted identifier) and `SELECT to_regclass('public._prisma_migrations');` — before deciding whether it's actually case 1 or 2 in disguise, whether to rerun, or whether to escalate to §4's recovery path (Path A). Cross-reference §5's boundary table: if the catalog shows the new table/columns already present, treat this as boundary 1 already crossed (post-commit), not as a safe-to-rerun pre-commit failure, even though the client never confirmed it. |

Do **not** proceed to Step 5 on anything other than a confirmed case 2.

**Step 5 — Compare the resulting schema against the expected baseline.**

```powershell
# The first query needs a double-quoted identifier, so it goes into a .sql file
# and runs with -f (see Step 3.5's quoting note) instead of -c. The other two
# use only single-quoted string literals against information_schema, so they
# have no quoting bug and are left as -c.
@'
SELECT to_regclass('public."LiteLLM_CredentialsTable"');
'@ | Set-Content -Path "$env:TEMP\romchat-cutover\04-step5-credentials-table-check.sql" -Encoding utf8
psql -X -v ON_ERROR_STOP=1 -f "$env:TEMP\romchat-cutover\04-step5-credentials-table-check.sql"
psql -X -v ON_ERROR_STOP=1 -Atc "SELECT count(*) FROM information_schema.columns WHERE table_name='LiteLLM_SpendLogs' AND column_name IN ('messages','response');"
psql -X -v ON_ERROR_STOP=1 -Atc "SELECT column_name FROM information_schema.columns WHERE table_name='LiteLLM_UserTable' AND column_name='sso_user_id';"
```

**Expected result:** the first query returns the table's regclass (not
`NULL`/empty), the second returns `2`, the third returns `sso_user_id`. This
mirrors the local pass-case verification already run in §2. **Stop condition:**
any mismatch means the remediation did not apply as expected — stop and
follow §5's incident route (capture state, do not rerun, do not delete
history) rather than proceeding to Step 6.

**Required gate, not supporting evidence (Follow-up 2, §8.2): full baseline
schema comparison.** The three spot checks above are a fast first look only;
row/column presence cannot detect a wrong type, a wrong default, a missing
index, or a missing/altered foreign key anywhere else in the schema. Compare
the complete catalog manifest instead, before proceeding to Step 6:

```powershell
# Capture the ACTUAL side: the real dev database, immediately after Step 4's
# remediation commit.
psql -X -v ON_ERROR_STOP=1 -v target_schemas=public -Atf ChatGptForEmployees/scripts/02-schema-manifest.sql | Set-Content -Path "$env:TEMP\romchat-cutover\actual-baseline-manifest.txt" -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw "Failed to capture the actual post-remediation schema manifest; stop." }
```

The EXPECTED side is generated once from the pinned image's own
`20250326162113_baseline/migration.sql` applied to a fresh, empty database —
**not** by also running `01-baseline-remediation.sql` on top of it (that
script's own history guard rejects a database that already has this state;
see §8.2 for why these are two separate, converging paths, not one composed
one). This was executed and its output recorded in §8.2 (270 manifest lines,
17 tables) as of this document's current pinned digest; regenerate it if the
digest ever changes:

```powershell
docker network create romchat-schema-ref-net 2>$null
docker run --rm -d --name romchat-schema-ref-pg --network romchat-schema-ref-net -e POSTGRES_DB=dev_rehearsal -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:16-alpine
Start-Sleep -Seconds 5
docker create --name romchat-schema-extract-tmp ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5 | Out-Null
docker cp romchat-schema-extract-tmp:/app/litellm-proxy-extras/litellm_proxy_extras/migrations/20250326162113_baseline/migration.sql "$env:TEMP\romchat-cutover\baseline-migration.sql"
docker rm romchat-schema-extract-tmp | Out-Null
docker cp "$env:TEMP\romchat-cutover\baseline-migration.sql" romchat-schema-ref-pg:/tmp/baseline-migration.sql
docker cp ChatGptForEmployees/scripts/02-schema-manifest.sql romchat-schema-ref-pg:/tmp/02-schema-manifest.sql
docker exec -u postgres romchat-schema-ref-pg psql -X -v ON_ERROR_STOP=1 -d dev_rehearsal -f /tmp/baseline-migration.sql
if ($LASTEXITCODE -ne 0) { docker rm -f romchat-schema-ref-pg; docker network rm romchat-schema-ref-net; throw "Failed to apply the pinned image's baseline migration to the reference database; stop." }
docker exec -u postgres romchat-schema-ref-pg psql -X -v ON_ERROR_STOP=1 -v target_schemas=public -d dev_rehearsal -Atf /tmp/02-schema-manifest.sql | Set-Content -Path "$env:TEMP\romchat-cutover\expected-baseline-manifest.txt" -Encoding utf8
docker rm -f romchat-schema-ref-pg
docker network rm romchat-schema-ref-net
```

```powershell
$baselineSchemaDiff = Compare-Object (Get-Content "$env:TEMP\romchat-cutover\expected-baseline-manifest.txt") (Get-Content "$env:TEMP\romchat-cutover\actual-baseline-manifest.txt")
if ($baselineSchemaDiff) {
  $baselineSchemaDiff | Out-File -FilePath "$env:TEMP\romchat-cutover\baseline-schema-mismatch.txt" -Encoding utf8
  throw "Baseline schema does not match the pinned image's expected schema; stop -- do not proceed to Step 6."
}
```

**Required: `$baselineSchemaDiff` must be empty.** Any difference here is a
harder stop than the three spot checks above — it means the real database's
post-remediation schema does not actually match what `20250326162113_baseline`
expects, and marking that migration "applied" in Step 6 would be false.

**Neither `prisma` nor the LiteLLM schema/migrations exist anywhere in this
repository.** They exist only inside the pinned image itself, at
`/app/litellm-proxy-extras/litellm_proxy_extras/schema.prisma` (with its
adjacent `migrations/` directory) and `/app/.venv/bin/prisma`. Steps 6 and 7
therefore run `prisma` **inside a throwaway container of the pinned image**,
with its entrypoint overridden to the `prisma` binary and `DATABASE_URL`
pointed at the real dev host — not on the operator's own machine, and not
against any schema file checked into this repo.

**This exact invocation shape was tested** against a local ephemeral
`postgres:16-alpine` container loaded with a fixture built from the pinned
image's own `20250326162113_baseline/migration.sql` (the canonical, complete
definition of the baseline-resolved state — simpler and more faithful than
hand-reconstructing it, since that migration file already contains every
table/column the remediation script adds, e.g. `LiteLLM_CredentialsTable` and
`LiteLLM_UserTable.sso_user_id`). Full transcript in
`.superpowers/sdd/addendum-fix-round2-report.md`. Summary: `prisma migrate
resolve` exited 0 with `Migration 20250326162113_baseline marked as applied.`;
`prisma migrate deploy` exited 0, applied all 156 remaining migrations in
order ending at `20260819000000_shadow_eval_max_budget`, and a follow-up
`prisma migrate status` reported `Database schema is up to date!` with 157/157
ledger rows `finished_at IS NOT NULL`. No `PRISMA_QUERY_ENGINE_BINARY` or
other extra env var was needed for this pinned v1.99.0 image; the recurring
`prisma:warn ... Falling back to Prisma engines built "debian"` line is
benign (image reports as the `wolfi` distro, prisma still resolves working
engines) and appeared on every invocation without affecting the exit code.

**One part of this invocation was not exercised by that local test:**
`sslmode=require` and reachability of the real external Azure FQDN
(`psql-db-cgfe-dev.postgres.database.azure.com`) — the local test's
`DATABASE_URL` pointed at a non-TLS Postgres container reachable by
docker-network container name, not a TLS-terminated external host. Everything
else about the command (the `prisma` binary, schema path, `resolve`/`deploy`
behavior, migration count and order, and exit-code handling) was tested and
confirmed working as described above.

**Step 6 — Resolve `20250326162113_baseline`, and only that migration, as applied.**

```powershell
# Build DATABASE_URL from the operator's already-exported PG* variables
# (never hard-code credentials on the command line). This points at the real
# Azure dev host with sslmode=require -- unlike the local test above, which
# pointed at a docker-network Postgres container by container name, this
# reaches psql-db-cgfe-dev.postgres.database.azure.com directly; ordinary
# Docker networking on the operator's machine can reach that external FQDN
# with no special --network setup.
$dbUrl = "postgresql://$([uri]::EscapeDataString($env:PGUSER)):$([uri]::EscapeDataString($env:PGPASSWORD))@$($env:PGHOST):$($env:PGPORT)/$($env:PGDATABASE)?sslmode=require"

docker run --rm `
  -e DATABASE_URL=$dbUrl `
  --entrypoint /app/.venv/bin/prisma `
  ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5 `
  migrate resolve --applied 20250326162113_baseline --schema /app/litellm-proxy-extras/litellm_proxy_extras/schema.prisma
if ($LASTEXITCODE -ne 0) { throw "Baseline resolution failed; stop and capture state per §5 boundary 2 — do not resolve any other migration to work around this." }
```

**Do not** resolve any migration other than `20250326162113_baseline` at this
step. **Expected result:** (matching the tested run above) `Migration
20250326162113_baseline marked as applied.`, and `_prisma_migrations` now
contains exactly one row, for `20250326162113_baseline`, marked applied.
**Stop condition:** per §5, boundary 2 — once this succeeds, the remediation
script's own history guard permanently refuses to rerun it; any failure here
before that guard trips should be treated as pre-commit-equivalent (capture
state, do not force).

**Step 7 — Run `prisma migrate deploy` for the remaining migrations.**

```powershell
docker run --rm `
  -e DATABASE_URL=$dbUrl `
  --entrypoint /app/.venv/bin/prisma `
  ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5 `
  migrate deploy --schema /app/litellm-proxy-extras/litellm_proxy_extras/schema.prisma
if ($LASTEXITCODE -ne 0) { throw "migrate deploy failed partway; STOP — follow §5's incident route (capture _prisma_migrations, the Postgres error, and catalog state; do not rerun, do not delete history, do not auto-resolve; follow the recovery path in §4 (Path A; not yet rehearsed against a real Azure PITR restore))." }

# Confirm, as tested: 157/157 rows applied.
docker run --rm `
  -e DATABASE_URL=$dbUrl `
  --entrypoint /app/.venv/bin/prisma `
  ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5 `
  migrate status --schema /app/litellm-proxy-extras/litellm_proxy_extras/schema.prisma
if ($LASTEXITCODE -ne 0) { throw "migrate status reported a non-zero exit after migrate deploy; stop and investigate per §5 before assuming the schema is fully up to date." }
```

**Expected result:** all 156 remaining migrations (157 total including the
resolved baseline) apply in order, ending at the pinned image's actual final
migration, `20260819000000_shadow_eval_max_budget` (§1a/§5 corrected naming —
see Finding 5), and `migrate status` reports `Database schema is up to date!`
— exactly what the tested local run above produced. **Stop condition:** any
partial failure is boundary-2 territory (§5) — stop immediately, capture the
ledger and error, and do not attempt a forward fix without a separate,
specifically-reviewed procedure.

**Step 8 — Post-migration verification, staged application release, and
resume.** (The target image was already deployed, at zero replicas, back in
Step 2b — this step verifies the database, then brings the application up
in stages, not all at once.)

This step has six required gates, run **in order**: **8a** database/schema
verification; **8b** bringing LiteLLM up (`maintenanceState = 'litellm-only'`)
for direct, internal-only testing; **8c** verifying that state's effective
configuration; **8d** controlled synthetic checks against LiteLLM directly
(§8.5); **8e** bringing LibreChat up for an authorized tester only
(`maintenanceState = 'validation'`) and running the LibreChat-dependent
application smoke tests (§8.1, §8.5 — added correcting Finding 1 of the
second working-changes follow-up review: an earlier version of this
sequence went straight from 8b/8c/8d to a full release, which started
ordinary traffic and both job schedules before any LibreChat-dependent check
had run at all); and **8f** the full release (`maintenanceState = 'off'`).
Only after all six pass does §7's job-resume procedure run at the end. A
mismatch anywhere in 8a stops the procedure outright (§5, Follow-up 3) — do
not proceed to 8b on an unreconciled mismatch, and do not treat any of 8a's
checks as optional supporting evidence; row counts remain a useful quick
look, but the fingerprint, full migration ledger, and full view list are the
actual gate.

### 8a. Database/schema verification (required gate)

```powershell
# All 157 ledger entries present and applied cleanly. No double-quoted
# identifier here -- _prisma_migrations is lowercase and unquoted -- so this
# command was never affected by the PowerShell quoting bug described in
# Step 3.5.
psql -X -v ON_ERROR_STOP=1 -c "SELECT count(*) AS total, count(*) FILTER (WHERE finished_at IS NOT NULL AND rolled_back_at IS NULL) AS applied_clean FROM public._prisma_migrations;" | Tee-Object -FilePath "$env:TEMP\romchat-cutover\post-migration-migration-count.txt"
if ($LASTEXITCODE -ne 0) { throw "Failed to verify the migration ledger; stop." }
```

**Required: both `total` and `applied_clean` must read `157`.** Anything else
means an unresolved, still-running, or rolled-back migration exists — stop
per §5's boundary-2 row; do not proceed. Sampling checksums, as an earlier
version of this step did, is no longer sufficient — full-ledger verification
of all 157 names/checksums is the gate (Follow-up 3):

```powershell
psql -X -v ON_ERROR_STOP=1 -c "SELECT migration_name, checksum, finished_at IS NOT NULL AS applied FROM public._prisma_migrations ORDER BY started_at;" | Set-Content -Path "$env:TEMP\romchat-cutover\post-migration-migration-ledger.txt"
if ($LASTEXITCODE -ne 0) { throw "Failed to capture the full migration ledger; stop." }
```

**Diff all 157 checksums against the pinned image's own migration files —
an actual runnable procedure, not the unactionable prose an earlier version
of this step left here (Follow-up 3).** This was verified end-to-end in this
session, in PowerShell, against a local ephemeral database migrated with the
pinned digest: the resulting 157 `_prisma_migrations.checksum` values were
captured and diffed against independently-computed `sha256sum`s of the pinned
image's own `migration.sql` files, and **all 157 rows matched byte-for-byte**
— confirming Prisma's checksum here is exactly SHA-256 of the raw
`migration.sql` file content (64 lowercase hex characters, matching the
`checksum` column's actual observed format). One migration directory's name
contains literal spaces (`20251122125322_Add organization_id to spend
logs`), and the script below was hardened against that (an earlier draft of
this same script silently dropped/garbled that row when its path variables
weren't quoted). The naive approach of passing this script to `docker run
... -c "..."` directly from PowerShell was tried first and rejected: nested
double-quotes inside a native command's argument get mangled by PowerShell's
own re-quoting for external processes (confirmed — it silently truncated
`echo "hello world"` to `hello`), a different manifestation of the same class
of bug Step 3.5 already documents for `psql -c`. The mount-and-run form below
sidesteps it entirely, the same way Step 3.5's `-f` files sidestep the `psql
-c` version.

1. Capture the applied ledger in a diff-friendly, unaligned format
   (`-Atc`, not the human-readable `-c` table above):

   ```powershell
   psql -X -v ON_ERROR_STOP=1 -Atc "SELECT migration_name || '|' || checksum FROM public._prisma_migrations ORDER BY migration_name;" | Set-Content -Path "$env:TEMP\romchat-cutover\applied-checksums.txt" -Encoding ascii
   if ($LASTEXITCODE -ne 0) { throw "Failed to capture applied checksums; stop." }
   ```

2. Compute the expected checksums directly from the pinned image's own
   migration files (no `prisma`/schema checkout exists anywhere in this repo
   — see the note above Step 6). Write the extraction script to a local file
   with forced LF line endings (Windows line endings break the script inside
   the Linux container — confirmed: CRLF here produced `sort: not found`),
   then mount that file into a throwaway container and run it directly,
   rather than passing it as a `-c` argument:

```powershell
$expectedChecksumsScript = @'
find /app/litellm-proxy-extras/litellm_proxy_extras/migrations -mindepth 1 -maxdepth 1 -type d | while IFS= read -r d; do
  n=$(basename "$d")
  if [ -f "$d/migration.sql" ]; then
    echo "$n|$(sha256sum "$d/migration.sql" | cut -d" " -f1)"
  fi
done | sort
'@ -replace "`r`n", "`n"
[System.IO.File]::WriteAllText("$env:TEMP\romchat-cutover\07-compute-expected-checksums.sh", $expectedChecksumsScript, [System.Text.Encoding]::ASCII)

docker run --rm -v "${env:TEMP}\romchat-cutover:/scripts" --entrypoint sh ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5 /scripts/07-compute-expected-checksums.sh | Set-Content -Path "$env:TEMP\romchat-cutover\expected-checksums.txt" -Encoding ascii
if ($LASTEXITCODE -ne 0) { throw "Failed to compute expected checksums from the pinned image; stop." }
```

> **Note:** the closing `'@` of a PowerShell here-string must start at column 0 with
> no leading whitespace — this code block is intentionally left-aligned (not
> indented to match this numbered list item) so it can be copied and run exactly
> as shown, rather than reproducing the `WhitespaceBeforeHereStringFooter` parse
> error that indenting it would cause.

3. Compare, and stop on any difference — the same required-throw pattern as
   the fingerprint and view-list gates immediately below:

   ```powershell
   $checksumDiff = Compare-Object (Get-Content "$env:TEMP\romchat-cutover\applied-checksums.txt") (Get-Content "$env:TEMP\romchat-cutover\expected-checksums.txt")
   if ($checksumDiff) {
     $checksumDiff | Out-File -FilePath "$env:TEMP\romchat-cutover\checksum-mismatch.txt" -Encoding utf8
     throw "Migration checksum mismatch between the applied ledger and the pinned image's own migration files; stop and follow §5's incident route."
   }
   ```

**Expected result:** `$checksumDiff` is empty and nothing is thrown — both
files hold the same 157 `name|checksum` lines. This diff, not the earlier
prose, is the actual "all 157 rows, not a sample" gate.

- **Schema/index validity** — re-run Step 5's checks plus the health-check
  index's validity, in one file (double-quoted identifiers, so `-f` not
  `-c`, per Step 3.5's quoting note):

  (here-string left unindented — see the column-0 note after the checksum
  script above)

```powershell
@'
SELECT to_regclass('public."LiteLLM_CredentialsTable"');
SELECT count(*) FROM information_schema.columns WHERE table_name='LiteLLM_SpendLogs' AND column_name IN ('messages','response');
SELECT column_name FROM information_schema.columns WHERE table_name='LiteLLM_UserTable' AND column_name='sso_user_id';
SELECT indexrelid::regclass, indisvalid FROM pg_index WHERE indexrelid = 'public."LiteLLM_HealthCheckTable_model_id_model_name_checked_at_idx"'::regclass;
'@ | Set-Content -Path "$env:TEMP\romchat-cutover\05-post-migration-schema-checks.sql" -Encoding utf8
psql -X -v ON_ERROR_STOP=1 -f "$env:TEMP\romchat-cutover\05-post-migration-schema-checks.sql" | Tee-Object -FilePath "$env:TEMP\romchat-cutover\post-migration-schema-checks.txt"
if ($LASTEXITCODE -ne 0) { throw "Post-migration schema check failed to run; stop." }
```

  Expected: the table's regclass (not `NULL`), `2`, `sso_user_id`, and
  `indisvalid = t` (not `f`, which would mean the `CREATE INDEX CONCURRENTLY`
  from `20260415120000_health_check_latest_per_model_index` failed partway).

- **Required gate, not supporting evidence (Follow-up 2, §8.2): full
  target-schema comparison.** The spot check above cannot detect a wrong
  type, wrong default, missing index, or missing/altered foreign key
  anywhere else in the schema. Compare the complete post-migration catalog
  manifest against the pinned image's own fully-migrated reference:

  ```powershell
  psql -X -v ON_ERROR_STOP=1 -v target_schemas=public -Atf ChatGptForEmployees/scripts/02-schema-manifest.sql | Set-Content -Path "$env:TEMP\romchat-cutover\actual-final-manifest.txt" -Encoding utf8
  if ($LASTEXITCODE -ne 0) { throw "Failed to capture the actual post-migration schema manifest; stop." }
  ```

  The expected reference is generated by applying the pinned image's complete
  migration history to a fresh, empty database — exactly Steps 6–7 above,
  reused for this purpose, run against a disposable local reference database
  rather than the real dev host. **`prisma migrate resolve --applied` only
  records a ledger row — it executes no SQL** (corrected per the `89c57d0`
  working-changes follow-up, Finding 1: an earlier version of this block
  jumped straight to `migrate resolve` + `migrate deploy` against a
  completely empty database, which would mark the baseline "applied" without
  ever creating its tables, then attempt to run the 156 later migrations —
  most of them `ALTER TABLE` against tables that were never created — against
  that empty schema. The baseline SQL itself must be executed first, exactly
  as Step 6 already does for the real dev host and as the working reference
  file this document uses for §8.2's baseline reference already does):

  ```powershell
  docker network create romchat-schema-final-net 2>$null
  docker run --rm -d --name romchat-schema-final-pg --network romchat-schema-final-net -e POSTGRES_DB=dev_rehearsal -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:16-alpine
  Start-Sleep -Seconds 5
  # Extract and apply the baseline migration's own SQL FIRST -- this is the step
  # the earlier version of this block was missing. Without it, the two prisma
  # commands below mark the baseline "applied" without ever creating its tables.
  docker create --name romchat-schema-final-extract-tmp ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5 | Out-Null
  docker cp romchat-schema-final-extract-tmp:/app/litellm-proxy-extras/litellm_proxy_extras/migrations/20250326162113_baseline/migration.sql "$env:TEMP\romchat-cutover\baseline-migration.sql"
  docker rm romchat-schema-final-extract-tmp | Out-Null
  docker cp "$env:TEMP\romchat-cutover\baseline-migration.sql" romchat-schema-final-pg:/tmp/baseline-migration.sql
  docker exec -u postgres romchat-schema-final-pg psql -X -v ON_ERROR_STOP=1 -d dev_rehearsal -f /tmp/baseline-migration.sql
  if ($LASTEXITCODE -ne 0) { docker rm -f romchat-schema-final-pg; docker network rm romchat-schema-final-net; throw "Failed to apply the pinned image's baseline migration to the final-reference database; stop." }
  $refDbUrl = "postgresql://postgres:postgres@romchat-schema-final-pg:5432/dev_rehearsal?sslmode=disable"
  docker run --rm --network romchat-schema-final-net -e DATABASE_URL=$refDbUrl --entrypoint /app/.venv/bin/prisma ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5 migrate resolve --applied 20250326162113_baseline --schema /app/litellm-proxy-extras/litellm_proxy_extras/schema.prisma
  if ($LASTEXITCODE -ne 0) { docker rm -f romchat-schema-final-pg; docker network rm romchat-schema-final-net; throw "Failed to mark the baseline migration resolved on the final-reference database; stop." }
  docker run --rm --network romchat-schema-final-net -e DATABASE_URL=$refDbUrl --entrypoint /app/.venv/bin/prisma ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5 migrate deploy --schema /app/litellm-proxy-extras/litellm_proxy_extras/schema.prisma
  if ($LASTEXITCODE -ne 0) { docker rm -f romchat-schema-final-pg; docker network rm romchat-schema-final-net; throw "Failed to build the fully-migrated reference database; stop." }
  docker cp ChatGptForEmployees/scripts/02-schema-manifest.sql romchat-schema-final-pg:/tmp/02-schema-manifest.sql
  docker exec -u postgres romchat-schema-final-pg psql -X -v ON_ERROR_STOP=1 -v target_schemas=public -d dev_rehearsal -Atf /tmp/02-schema-manifest.sql | Set-Content -Path "$env:TEMP\romchat-cutover\expected-final-manifest.txt" -Encoding utf8
  docker rm -f romchat-schema-final-pg
  docker network rm romchat-schema-final-net
  ```

  This corrected sequence (baseline SQL applied, then resolved, then
  deployed — not resolved-then-deployed alone) was executed in full in this
  session, re-run specifically to verify this fix: 157/157 migrations
  applied, `Database schema is up to date!`, 75 tables, 1384 manifest lines
  (COLUMN records in the corrected format — see Finding 3 below). Reuse that
  recorded output only as a sanity check on the shape of the result, not as a
  substitute for rerunning it here — the reference must come from whatever
  digest is actually pinned in `main.dev.bicepparam` at the time of the real
  cutover.

  ```powershell
  $finalSchemaDiff = Compare-Object (Get-Content "$env:TEMP\romchat-cutover\expected-final-manifest.txt") (Get-Content "$env:TEMP\romchat-cutover\actual-final-manifest.txt")
  if ($finalSchemaDiff) {
    $finalSchemaDiff | Out-File -FilePath "$env:TEMP\romchat-cutover\final-schema-mismatch.txt" -Encoding utf8
    throw "Post-migration schema does not match the pinned image's fully-migrated expected schema; stop -- do not proceed to 8b."
  }
  ```

  **Required: `$finalSchemaDiff` must be empty** before proceeding to 8b —
  same enforced-throw pattern as the fingerprint and view-list gates
  elsewhere in this step, not left as printed output for the operator to
  notice.

- **Preserved historical data — required gate, not supporting evidence
  (Follow-up 3).** Re-run the *exact* frozen fingerprint file generated in
  Step 3.5 (do not regenerate it — see that step's warning) and diff:

  ```powershell
  psql -X -v ON_ERROR_STOP=1 -f "$env:TEMP\romchat-cutover\03-fingerprint-frozen.sql" | Tee-Object -FilePath "$env:TEMP\romchat-cutover\post-migration-fingerprints.txt"
  if ($LASTEXITCODE -ne 0) { throw "Failed to capture post-migration fingerprints; stop." }
  $fingerprintDiff = Compare-Object (Get-Content "$env:TEMP\romchat-cutover\pre-remediation-fingerprints.txt") (Get-Content "$env:TEMP\romchat-cutover\post-migration-fingerprints.txt")
  if ($fingerprintDiff) {
    $fingerprintDiff | Out-File -FilePath "$env:TEMP\romchat-cutover\fingerprint-mismatch.txt" -Encoding utf8
    throw "Historical-data fingerprint mismatch between the Step 3.5 baseline and the post-migration state; stop and follow §5's incident route."
  }
  ```

  **Required: `Compare-Object` must return nothing — the `throw` above
  enforces this rather than leaving it to the operator to notice printed
  output.** Any difference means at least one original table's data changed
  or was lost somewhere between the Step 3.5 baseline and now — do not
  proceed to 8b.

  Row counts remain useful as a quick first look but are not the gate:

  (here-string left unindented, same reason as above)

```powershell
@'
SELECT 'LiteLLM_SpendLogs' AS table_name, count(*) FROM public."LiteLLM_SpendLogs"
UNION ALL SELECT 'LiteLLM_UserTable', count(*) FROM public."LiteLLM_UserTable"
UNION ALL SELECT 'LiteLLM_VerificationToken', count(*) FROM public."LiteLLM_VerificationToken"
UNION ALL SELECT 'LiteLLM_OrganizationTable', count(*) FROM public."LiteLLM_OrganizationTable";
'@ | Set-Content -Path "$env:TEMP\romchat-cutover\06-post-row-counts.sql" -Encoding utf8
psql -X -v ON_ERROR_STOP=1 -f "$env:TEMP\romchat-cutover\06-post-row-counts.sql" | Tee-Object -FilePath "$env:TEMP\romchat-cutover\post-migration-row-counts.txt"
psql -X -v ON_ERROR_STOP=1 -c "SELECT 'attribution.v_spend_by_dept_week' AS view_name, count(*) FROM attribution.v_spend_by_dept_week UNION ALL SELECT 'attribution.v_spend_by_dept_month', count(*) FROM attribution.v_spend_by_dept_month;" | Tee-Object -FilePath "$env:TEMP\romchat-cutover\post-migration-row-counts.txt" -Append
```

  Compare both against Step 3.5's `pre-remediation-row-counts.txt`.

- **All previously-documented views resolve, not just the two attribution
  rollups (Follow-up 3):**

  ```powershell
  psql -X -v ON_ERROR_STOP=1 -Atc "SELECT table_schema, table_name FROM information_schema.views WHERE table_schema IN ('public','attribution') ORDER BY 1,2;" | Tee-Object -FilePath "$env:TEMP\romchat-cutover\post-migration-views.txt"
  if ($LASTEXITCODE -ne 0) { throw "Failed to enumerate post-migration views; stop." }
  $viewDiff = Compare-Object (Get-Content "$env:TEMP\romchat-cutover\pre-remediation-views.txt") (Get-Content "$env:TEMP\romchat-cutover\post-migration-views.txt")
  if ($viewDiff) {
    $viewDiff | Out-File -FilePath "$env:TEMP\romchat-cutover\view-list-mismatch.txt" -Encoding utf8
    throw "View list changed between the Step 3.5 baseline and the post-migration state; stop and follow §5's incident route."
  }
  ```

  **Required: identical view list (10, per Step 3.5's reconciled baseline)
  before and after — enforced by the `throw` above, not left as printed
  output for the operator to catch.** A missing or changed view is a stop
  condition, same as a fingerprint mismatch.

- **View definitions and execution — required gate (Follow-up 3, §8.3).**
  The name-list check above cannot detect a same-named view whose query
  changed. Diff full definitions against Step 3.5's frozen capture, then
  confirm every view still actually executes:

  ```powershell
  psql -X -v ON_ERROR_STOP=1 -v target_schemas=public,attribution -Atf ChatGptForEmployees/scripts/03-view-inventory.sql | Set-Content -Path "$env:TEMP\romchat-cutover\post-migration-view-definitions.txt" -Encoding utf8
  if ($LASTEXITCODE -ne 0) { throw "Failed to capture post-migration view definitions; stop." }
  $viewDefDiff = Compare-Object (Get-Content "$env:TEMP\romchat-cutover\pre-remediation-view-definitions.txt") (Get-Content "$env:TEMP\romchat-cutover\post-migration-view-definitions.txt")
  if ($viewDefDiff) {
    $viewDefDiff | Out-File -FilePath "$env:TEMP\romchat-cutover\view-definition-mismatch.txt" -Encoding utf8
    throw "A view's definition changed between the Step 3.5 baseline and the post-migration state; stop and follow §5's incident route."
  }
  psql -X -v ON_ERROR_STOP=1 -v target_schemas=public,attribution -f ChatGptForEmployees/scripts/04-view-execution-check.sql
  if ($LASTEXITCODE -ne 0) { throw "A view failed to execute (or timed out) after migration; stop -- do not proceed to 8b. Do not substitute a bare count(*) or catalog check here -- see §8.3 for why that silently passes a broken view." }
  ```

  **Required: `$viewDefDiff` empty, and the execution check exits 0** — both
  enforced by their own `throw`, not left as printed output. Every view's
  definition must be unchanged from Step 3.5's baseline, and every view must
  actually execute (not merely appear in the catalog), before proceeding to
  8b.

**Only once every check above passes** does this procedure move to 8b. This
is the full baseline-equivalence gate Follow-up 3 requires; it is not
satisfied by any subset of it, and it is required before `migrate resolve
--applied` would ever run again on a future attempt, not just a nice-to-have
report.

### 8b. Bring LiteLLM up for testing: `maintenanceState = 'litellm-only'` (Follow-up 1 & its working-changes correction, §8.1)

Everything through 8a validated the *database*. The target image and
reviewed config are **already deployed** as of Step 2b, above —
`ca-litellm-dev` has been running the pinned digest, with
`DISABLE_SCHEMA_UPDATE=true` and both prompt-storage controls `false`,
scaled to `{min:0,max:0}`, since before remediation even started; LibreChat
and both jobs have likewise been held down/paused since Step 2b. This step
does not deploy anything new; it brings **LiteLLM only** up to normal scale
so Step 8d can run controlled synthetic checks directly against it — it
deliberately does **not** release LibreChat or resume either job yet (that
is 8e, strictly after 8d passes).

**Step 8b(i) — Flip `maintenanceState` to `'litellm-only'` and commit.** Edit
`ChatGptForEmployees.bicep/main.dev.bicepparam` so the line reads:

```
param maintenanceState = 'litellm-only'
```

The `liteLlmImage` line should already read the pinned digest from Step
2b — do not change it here; this commit changes `maintenanceState` only, so
the image/config LiteLLM comes up with is byte-identical to what was
verified in Step 2b and re-verified all through 8a, with nothing new to
review at this transition. Then commit it (from the repo root):

```powershell
git add ChatGptForEmployees.bicep/main.dev.bicepparam
git commit -m "Bring LiteLLM up for controlled testing (LibreChat/jobs remain paused)"
if ($LASTEXITCODE -ne 0) { throw "Failed to commit the maintenanceState transition; stop — do not trigger the pipeline against an uncommitted change." }
```

**Stop condition:** do not proceed to trigger the pipeline (below) until this
commit exists on the ref that will actually be deployed, and until it changes
`maintenanceState` only — if `liteLlmImage` or any env var also differs from
what Step 2b/8a validated, treat this as a new, unreviewed change and restart
validation from 8a rather than proceeding.

**This project's only deploy path is its CI/CD pipeline**
(`ChatGptForEmployees.pipelines/dev.yml`, triggered on push to `dev`); there
is no separate ad-hoc `az containerapp update --image` mechanism used
anywhere else in this project, and improvising one here would deploy through
a path nothing else in this project goes through and this review never
validated. The same pipeline run also redeploys RAG API — LibreChat's own
deploy stage restarts it too, but it stays at 0/0 scale per `libreChat.bicep`
in this state, so it does not yet serve anything.

**Owner-led, Azure CLI/ADO-dependent — unverified in this preparation
environment, like every other Azure step in this document:**

1. Re-confirm the commit above is actually present on the ref about to be
   triggered, immediately before triggering anything.
2. Trigger the pipeline against the reviewed commits on
   `fix/litellm-cve-upgrade-v1.99.0-dev` — via this branch's normal
   promotion to `dev` per the project's existing branch policy, or a manual
   run of the `dev.yml` pipeline definition against this ref if the ADO
   project supports that without merging first (confirm which applies before
   the maintenance window; this preparation environment has no ADO access to
   check).
3. Watch the pipeline through `BicepCreate`, `UploadConfigs`, and
   `DeployLiteLLM`. **Stop condition:** any of those three stages failing
   means this transition is not confirmed — do not proceed to 8c, and do not
   assume a partially-completed run left the app in a known state (capture
   the pipeline logs and re-run 8c's effective-state check before deciding
   anything). Treat this as an incident requiring investigation before any
   further action.
4. `ca-litellm-dev`'s scale is expected to return to its normal declared
   values as a direct effect of this deploy (§8.1's table). `ca-librechat-<env>`
   and both jobs are expected to remain at 0/0 / the never-fire sentinel.
   **Confirm all of this in 8c below rather than assuming it.**
5. **If Step 3 used the revision-deactivation alternative instead of
   `--max-replicas 0`:** an earlier version of this step said to "reactivate
   that revision" here — do **not** do that; the revision Step 3 deactivated
   is the pre-upgrade one Step 1 recorded, and reactivating it is exactly the
   action Follow-up 1 forbids (see the restart-guidance note at the end of
   8e). Leave it deactivated. The revision Step 2b's maintenance-entry deploy
   created (running the pinned digest) is what should end up active; confirm
   that in 8c.

### 8c. Verify effective running state (Follow-up 1)

```powershell
az containerapp show -n ca-litellm-dev -g rg-dev-shared --query "{image:properties.template.containers[0].image, env:properties.template.containers[0].env, revision:properties.latestRevisionName, scale:properties.template.scale}" -o json | Tee-Object -Variable liteLlmEffectiveState
if ($LASTEXITCODE -ne 0) { throw "Failed to read LiteLLM's post-deploy effective state; stop." }
$liteLlmEffectiveState | Out-File -FilePath "$env:TEMP\romchat-cutover\ca-litellm-dev-litellm-only-state.json" -Encoding utf8
az containerapp show -n ca-librechat-dev -g rg-dev-shared --query "properties.template.scale" -o json | Tee-Object -Variable libreChatScaleState
if ($LASTEXITCODE -ne 0) { throw "Failed to read LibreChat's post-deploy scale; stop." }
az containerapp job show -n job-cgfe-okta-sync-dev -g rg-dev-shared --query "properties.configuration.scheduleTriggerConfig.cronExpression" -o tsv
az containerapp job show -n job-cgfe-cleanup-dev -g rg-dev-shared --query "properties.configuration.scheduleTriggerConfig.cronExpression" -o tsv
```

**Required, before 8d:**

- LiteLLM `image` is the exact pinned digest from §3b/Step 1's
  target-artifact record — not the tag, and not the "currently deployed
  revision" Step 1 recorded pre-cutover.
- LiteLLM `env` contains `DISABLE_SCHEMA_UPDATE=true` and
  `STORE_PROMPTS_IN_SPEND_LOGS=false`.
- LiteLLM `scale` is back to its normal declared values (not `{min:0,max:0}`)
  — matching `ca-litellm-dev-original-scale.json` from Step 3, per §8.1.
- **LibreChat's `scale` is still `{min:0,max:0}`** — this is the entire point
  of the `'litellm-only'` state; if LibreChat is already at normal scale
  here, ordinary employee traffic can already reach LiteLLM and this gate
  has already failed silently. Stop and diagnose rather than proceeding to
  8d.
- Both jobs' cron expressions are still the `0 0 31 2 *` sentinel — not yet
  `0 5 * * 2,5` / `0 2 * * *`.
- LiteLLM `revision` differs from the revision name Step 1 recorded in
  `ca-litellm-dev-pre-cutover-revision.json` — confirming this is the
  revision Step 2b created, not the pre-cutover one somehow still live.

**Stop condition:** any mismatch means direct testing must not proceed. Do
not run 8d's checks against an unverified state — go back to 8b and diagnose
before continuing.

### 8d. Controlled synthetic checks against LiteLLM directly (not through LibreChat)

LibreChat is still at 0/0 (8c). This step now has a concrete, prepared
execution location — `job-cgfe-synth-check-<env>` (`jobs.bicep`), a
manually-triggered ACA Job running
`ChatGptForEmployees/scripts/05-synthetic-litellm-check.py` — instead of the
unresolved candidates an earlier version of this step listed (second
working-changes follow-up, Finding 2: "make the internal synthetic test
executable"). This job runs inside the same Container Apps environment as
`ca-litellm-dev`, so it resolves LiteLLM's internal FQDN the same way any
other app in the environment does, without exec-ing into any container.

#### 8d(i) — Verify the jobs image before starting anything (third working-changes follow-up, Finding 2)

The job pulls a shared image (`jobs.bicep`'s `jobsImage`) built by the
`BuildJobsImage` pipeline stage (`dev.yml`). Completion of `BicepCreate`,
`UploadConfigs`, or `DeployLiteLLM` does **not** establish that this image is
ready or current — `BuildJobsImage` only depends on `BicepCreate` and can
fail, be skipped, or simply not have run yet for this commit even while
those other stages succeed. Do not start the job until this is confirmed:

1. In the pipeline run for this cutover's reviewed commit, confirm the
   `BuildJobsImage` stage actually **Succeeded** for that exact commit —
   check the stage result and the commit SHA in its own logs, not merely
   that the overall pipeline is green.
2. From that stage's logs, record the pushed digest it printed
   (`librechat-cleanup:<commit-sha>` and its `sha256:...` digest) alongside
   the commit SHA:
   ```powershell
   New-Item -ItemType Directory -Force -Path "$env:TEMP\romchat-cutover" | Out-Null
   @{
     commit = '<commit SHA from the BuildJobsImage stage log>'
     digest = '<sha256:... digest from the BuildJobsImage stage log>'
   } | ConvertTo-Json | Set-Content -Path "$env:TEMP\romchat-cutover\jobs-image-build-record.json" -Encoding utf8
   ```
3. Pin the scheduled-jobs image to that exact digest rather than trusting the
   mutable `:latest` tag: set `jobsImageDigest` to the recorded digest in
   `main.dev.bicepparam`, commit, and redeploy (`BicepCreate`) so
   `job-cgfe-synth-check-dev` (and the two scheduled jobs, which share the
   same image) resolve to `librechat-cleanup@sha256:...` instead of
   `:latest`. **The digest pin is mandatory for cutover.** A mutable tag can
   move between a registry check and the execution's image pull, so a tag
   lookup is not an acceptable substitute. Keep this pin unchanged through
   synthetic testing, application validation, and release.
4. Confirm the deployed job actually reflects that image before starting it:
   ```powershell
   $jobsBuildRecord = Get-Content -Encoding utf8 "$env:TEMP\romchat-cutover\jobs-image-build-record.json" -Raw | ConvertFrom-Json -ErrorAction Stop
   if ($jobsBuildRecord.digest -cnotmatch '^sha256:[0-9a-f]{64}$') {
       throw "Build evidence has no valid SHA-256 image digest; stop."
   }
   $expectedSynthImage = "acrcgfedev.azurecr.io/librechat-cleanup@$($jobsBuildRecord.digest)"
   $deployedSynthImage = az containerapp job show -n job-cgfe-synth-check-dev -g rg-dev-shared --query "properties.template.containers[0].image" -o tsv
   if ($LASTEXITCODE -ne 0) { throw "Failed to read the synthetic job image; stop." }
   if ($deployedSynthImage -cne $expectedSynthImage) {
       throw "Synthetic job must use the exact recorded digest reference; tags and mismatched images are rejected. Stop before job start."
   }
   ```
   **Required:** the deployed reference equals the recorded immutable image
   reference. After starting the job in 8d(ii), also verify the captured
   execution template uses this same reference; a concurrent job update
   between the preflight and start must not produce acceptable evidence.

**Stop condition:** a failed/skipped `BuildJobsImage` for this commit, a
missing or mismatched digest, or a job image that doesn't match must block
`job start` below. Fix the image/deploy first and re-verify rather than
running the synthetic check against an unverified image.

#### 8d(ii) — Start the job and verify the execution it actually started (third working-changes follow-up, Finding 1)

An earlier version of this step started the job and then read `[0]` from
execution history and `properties.template.containers[0].exitCode` to
decide pass/fail. Neither is reliable: execution history `[0]` is not
guaranteed to be the execution just started, and `exitCode` is not a
documented field of the [Azure jobs execution
schema](https://learn.microsoft.com/en-us/rest/api/resource-manager/containerapps/jobs-executions/list?view=rest-resource-manager-containerapps-2025-07-01)
— a null there must never be read as success. The commands below instead
capture the started execution's own identity and poll only that execution.

**Verify the exact command/response shape in an Azure rehearsal before the
maintenance window** — the shape below follows the documented list schema
(`name`, `properties.status`), but has not been independently exercised
against a live job execution in this review; treat any deviation there
(field names, `--execution` support on `job logs show`, etc.) as blocking
until resolved, not as something to work around silently.

```powershell
New-Item -ItemType Directory -Force -Path "$env:TEMP\romchat-cutover" | Out-Null

# 1. Start the job and capture the execution it actually created — never
#    assume it will be history's first entry afterward.
$jobStartResult = az containerapp job start -n job-cgfe-synth-check-dev -g rg-dev-shared -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $jobStartResult) { throw "job start did not return a usable execution identity; stop." }
$synthExecName = $jobStartResult.name
if ([string]::IsNullOrWhiteSpace($synthExecName)) { throw "job start response had no execution name; stop." }
$jobStartResult | ConvertTo-Json -Depth 10 | Out-File -FilePath "$env:TEMP\romchat-cutover\synth-check-execution-start.json" -Encoding utf8
if ($jobStartResult.properties.template.containers[0].image -cne $expectedSynthImage) {
    throw "Started execution does not report the required digest-pinned image; do not accept this run or proceed to 8e. Keep maintenance in effect and investigate."
}
Write-Host "Started execution: $synthExecName"

# 2. Poll ONLY that execution, bounded by a deadline, for an explicit
#    terminal status. Filter by exact name and require exactly one match —
#    never fall back to [0] if the filter is empty or ambiguous.
$deadline = (Get-Date).AddMinutes(5)
$synthExecStatus = $null
do {
    Start-Sleep -Seconds 10
    $matches = az containerapp job execution list -n job-cgfe-synth-check-dev -g rg-dev-shared --query "[?name=='$synthExecName']" -o json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Failed to poll execution '$synthExecName'; stop." }
    if ($matches.Count -ne 1) { throw "Expected exactly one execution named '$synthExecName', found $($matches.Count); stop and investigate rather than guessing which one." }
    $synthExecStatus = $matches[0].properties.status
    Write-Host "Execution $synthExecName status: $synthExecStatus"
} while ($synthExecStatus -notin @('Succeeded', 'Failed', 'Stopped') -and (Get-Date) -lt $deadline)

if ($synthExecStatus -ne 'Succeeded') {
    throw "Execution $synthExecName ended as '$synthExecStatus' (or is still nonterminal at the deadline) -- treat Failed, Stopped, timeout, and any unrecognized status as a stop condition. Do not proceed to 8e."
}

# 3. Only now retrieve logs, scoped to this same execution, and require the
#    script's own PASS line for THIS run -- not an older run's output, not an
#    unscoped tail, and not a still-running execution's partial output.
$synthExecLogs = az containerapp job logs show -n job-cgfe-synth-check-dev -g rg-dev-shared --execution "$synthExecName" 2>&1
$synthExecLogs | Out-File -FilePath "$env:TEMP\romchat-cutover\synth-check-execution-logs.txt" -Encoding utf8
if (-not ($synthExecLogs -match 'PASS: all synthetic LiteLLM checks succeeded')) {
    throw "Execution $synthExecName reported job-level status 'Succeeded' but its own PASS marker was not found in the retrieved logs -- job status alone is not sufficient. Stop and investigate before proceeding to 8e."
}
Write-Host "Confirmed script-level PASS for execution $synthExecName."
```

If `--execution` is not accepted by the installed CLI version, resolve the
actually-supported way to scope `az containerapp job logs show` to one
execution (or an equivalent Log Analytics query keyed to this execution's
name/time-window) before the maintenance window — logs must be scoped to
this specific execution, never the job's general/latest log stream.

**What the script checks, in order (all bounded, see the script's own
docstring for exact env vars/timeouts):** `/health/liveliness` and
`/health/readiness` against LiteLLM's internal FQDN; one synthetic,
non-sensitive chat completion (a fixed marker string, never employee
content — the same pattern as §1a/§1b/§1c's local Docker harnesses, but
against the real dev database this time) with a freshly-generated unique
`end_user` marker; a bounded poll of `LiteLLM_SpendLogs` for that specific
row (per §1's "identify the synthetic requests' own rows" requirement — not
the latest-N-rows query alone); and a check that `messages`/`response` on
that row match the documented empty representation. The script never prints
row content, only match/mismatch status.

**Validated locally**, against an isolated Docker LiteLLM (mock response,
`store_prompts_in_spend_logs: false` + `STORE_PROMPTS_IN_SPEND_LOGS=false`,
matching the actual shipped configuration) and Postgres, running the actual
script file unmodified in each case:

| Case | Expected exit | Observed |
|---|---|---|
| Healthy, storage off, matching row found | `0` (pass) | ✅ |
| Wrong `LITELLM_MASTER_KEY` | `2` (completion request failed) | ✅ (HTTP 401) |
| Nonexistent model name | `2` (completion request failed) | ✅ (HTTP 400) |
| Completion succeeds but the polled database has no matching row within the bound | `3` (unresolved — not evidence storage is off) | ✅ |
| Database unreachable | `5` (distinguished from case above — query never ran, not "ran and found nothing") | ✅ |
| Storage actually enabled (content populated) | `4` (stop and escalate; no content printed) | ✅ — **and this positive case caught a real bug during validation**: the first draft compared the jsonb `messages`/`response` values against the Python string `"{}"`, but `psycopg2` auto-adapts a `jsonb` column to a native Python object (an empty `dict`, confirmed via `pg_typeof`), so that comparison was **always** `False` regardless of actual content — every run would have raised a false "content is populated" alarm. Fixed to compare against the Python `{}` value (with the string form kept as a defensive fallback); re-validated against both the true-empty and populated cases above after the fix. |

**Stop condition:** anything other than the specific execution started in
8d(ii) reaching `Succeeded` with its own scoped logs containing the PASS
line means do not proceed to 8e — that includes a non-`Succeeded` terminal
status, a timeout, and a `Succeeded` status whose logs don't show the PASS
marker (8d(ii)'s script already `throw`s on each of these). Capture the
job's logged output (never raw row content — the script itself never prints
it) and follow the incident route (§5) rather than proceeding to a
validation phase against a LiteLLM instance that hasn't actually passed this
check.

**Cleanup:** none required beyond the job's own normal completion —
`job-cgfe-synth-check-<env>` is a standing, reusable Bicep-declared resource
(not a throwaway container an operator creates and must remember to remove),
so there is nothing to clean up per invocation.

**Application smoke tests that need LibreChat (Okta login, send/stream a
chat via the UI, model picker, existing conversations load, file upload)
still cannot run in this state** — LibreChat remains at 0/0. That is 8e,
next — not a bare release to `'off'` (see that step's own history: an
earlier version of this runbook released full traffic and both job
schedules together, before any LibreChat-dependent check had run at all;
8e exists specifically to close that gap, per the second working-changes
follow-up, Finding 1).

### 8e. Bring LibreChat up for authorized-tester validation: `maintenanceState = 'validation'` (second working-changes follow-up, Finding 1)

**Only after 8a–8d have all passed.** Direct LiteLLM success (8d) does not
establish that the complete application works — Okta login, the LibreChat
UI, streaming, model selection, conversation loading, and file upload all
depend on LibreChat itself, which has been at 0/0 since Step 2b. This step
brings LibreChat up **for an authorized tester only**, before any ordinary
employee is let in.

**Step 8e(i) — Set the tester allow-list and flip to `'validation'`.** Edit
`ChatGptForEmployees.bicep/main.dev.bicepparam`:

```
param maintenanceTesterIpRanges = ['<tester's actual public IP>/32']
param maintenanceState = 'validation'
```

Both values change together, in one commit — a `'validation'` state with no
tester IP configured fails closed (blocks everyone, including the tester;
see `libreChat.bicep`'s own param comment), so there is no meaningful
partial state between these two lines. Commit and push:

```powershell
git add ChatGptForEmployees.bicep/main.dev.bicepparam
git commit -m "Bring LibreChat up for authorized-tester validation (tester IP allow-listed)"
if ($LASTEXITCODE -ne 0) { throw "Failed to commit the validation-phase transition; stop." }
```

Watch the same three pipeline stages, then verify effective state:

```powershell
az containerapp show -n ca-librechat-dev -g rg-dev-shared --query "{scale:properties.template.scale,ipRestrictions:properties.configuration.ingress.ipSecurityRestrictions}" -o json | Tee-Object -Variable libreChatValidationState
if ($LASTEXITCODE -ne 0) { throw "Failed to read LibreChat's post-deploy effective state; stop." }
$libreChatValidationState | Out-File -FilePath "$env:TEMP\romchat-cutover\ca-librechat-dev-validation-state.json" -Encoding utf8
az containerapp job show -n job-cgfe-okta-sync-dev -g rg-dev-shared --query "properties.configuration.scheduleTriggerConfig.cronExpression" -o tsv
az containerapp job show -n job-cgfe-cleanup-dev -g rg-dev-shared --query "properties.configuration.scheduleTriggerConfig.cronExpression" -o tsv
```

**Required, before running any application check:**

- LibreChat `scale` is back to its normal declared values (not `{min:0,max:0}`).
- LibreChat's `ipSecurityRestrictions` contains exactly one `Allow` entry, for
  the tester's actual configured IP — **not** the `0.0.0.0/32` fail-closed
  sentinel (which means `maintenanceTesterIpRanges` was left empty and this
  deploy is blocking the tester too, not just ordinary employees).
- Both jobs' cron expressions are still the `0 0 31 2 *` sentinel — not yet
  restored.

**Stop condition:** any mismatch means do not run application checks yet —
in particular, if `ipSecurityRestrictions` is empty (no restriction at all)
rather than the expected single-entry allow-list, ordinary employee traffic
can already reach LibreChat and this gate has already failed silently; stop
and diagnose rather than proceeding.

**Step 8e(ii) — Application smoke tests, from the allow-listed tester IP
only, using an authorized synthetic test account and non-sensitive test
data:** Okta login, model selection (both `ROMTech AI Standard` and
`ROMTech AI Fast`), send/stream a chat, existing-conversation loading, and
file upload. Record pass/fail evidence only — never copy employee
conversation content into tickets, logs, or chat, consistent with every
other content-handling rule in this document.

**Stop condition:** any failed check means do not proceed to 8f. Keep
`maintenanceState = 'validation'` (LibreChat restricted, both jobs paused)
in effect, capture diagnostics, and follow the incident route (§5) — do not
switch to `'off'` merely to diagnose a failure, and do not reactivate the
previous image against the upgraded database (see 8f's own note on this).

### 8f. Release: `maintenanceState = 'off'` (Follow-up 1 & both working-changes corrections, §8.1)

**Only after 8a, 8b, 8c, 8d, and 8e have all passed.** Edit
`ChatGptForEmployees.bicep/main.dev.bicepparam` so the lines read:

```
param maintenanceTesterIpRanges = []
param maintenanceState = 'off'
```

Same discipline as 8b(i)/8e(i): clear the tester allow-list back to empty in
the same commit that flips to `'off'` — leaving a stale IP-restriction entry
around after the window closes would be a leftover, unreviewed access rule
on a production-facing app. Commit and push, then watch the same three
pipeline stages. LibreChat's `ipSecurityRestrictions` clears (Azure's
"no restriction" value, this app's normal unrestricted state) and both jobs
resume their normal schedules (`0 5 * * 2,5` / `0 2 * * *`) as a direct
effect of this deploy — confirm with `az containerapp show`/`job show`,
expecting LibreChat's scale to match its own original values, its
`ipSecurityRestrictions` to be empty again, and both job cron expressions to
be back to normal. Then resume the paused jobs' operational side per §7
(confirm no unwanted execution occurred during the window, and run a
controlled catch-up if a scheduled run was missed).

**Reactivating a previous (pre-upgrade) revision against the now-migrated
database is not a normal restart action and must not be done as a routine
step (Follow-up 1).** The pre-upgrade image has no `DISABLE_SCHEMA_UPDATE`
guard and was never validated against a schema built by 157 migrations it
doesn't know about — reactivating it here could attempt its own schema
mutation against the upgraded database, or otherwise behave incorrectly
against a schema state it was never designed for. Only the revision verified
in 8c receives traffic. If that revision is ever unhealthy after this point,
the correct response is the recovery path in §4 (Path A) or a forward-fix
redeploy of a corrected target image through 8b again — never a manual
reactivation of the revision Step 1 recorded as "currently deployed"
pre-cutover.

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
config currently contains `master_key`, `database_url`, `allow_user_requests`,
and (as of Finding 1's correction, §1) `store_prompts_in_spend_logs: false`;
no `disable_prisma_schema_update` key is present.

**Standing requirement:** startup will no longer repair an outdated schema
automatically. **Every future LiteLLM image upgrade, in every environment,
requires an explicit reviewed migration step (§2a, "Full cutover sequence")
executed before the new image is allowed to start against the
database.** Sections 2 and 4 alone are necessary background (the environment
guard and the rollback/recovery boundaries, respectively) but neither one is,
by itself, the ordered operator procedure — §2a is. If an operator skips this
and the new image starts anyway, check
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
docker run --rm --network disable-schema-test-net -e PGPASSWORD=postgres postgres:16-alpine psql -h disable-schema-test-pg -U postgres -d disable_schema_test -Atc "SELECT to_regclass('public.LiteLLM_UserTable');"
```

**Quoting note added in the Follow-up 2 correction round (not present when
this test was originally run):** the `to_regclass` command above previously
read `SELECT to_regclass('public.\"LiteLLM_UserTable\"');` — a
backslash-escaped double quote inside a PowerShell double-quoted string,
which does not work in PowerShell (see Step 3.5's quoting note) and would
have split into two garbled arguments rather than reaching psql as one SQL
string. `LiteLLM_UserTable` is mixed-case, so the technically-correct fixed
form needs the identifier double-quoted to avoid Postgres folding it to
lowercase; written safely that means a `.sql` file run with `-f` (as
elsewhere in this document) rather than `-c`. The simpler literal shown above
sidesteps the issue for this specific historical record by dropping the
quoting entirely — `to_regclass` on the unquoted, lowercase-folded
`public.litellm_usertable` also correctly returns nothing on a database with
no such table (case-folded or not, the table doesn't exist either way), so it
does not misrepresent what was actually being tested. **This specific
sub-check's original literal command text had this quoting defect (now
corrected here); the test was not rerun, but its overall conclusion is not
invalidated** — the same test session independently corroborated "the
database was left completely untouched" via two other checks that do not
have this bug: a `pg_tables` row count for schema `public` (zero) and a check
for the absence of `_prisma_migrations` (also absent), both described just
below.

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

**Required action (not optional, not either/or):** this runbook switches
`main.dev.bicepparam` to reference the digest directly and commits that
change — **Step 2b in §2a is where that actually happens now** (moved there,
together with `maintenanceState = 'paused'`, as part of Follow-up 1's
maintenance-state enforcement, §8.1 — it used to be Step 8b(i), deploying the
target image for the first time only after migration; now the target image
deploys before migration, at zero replicas, and Step 8b is a
`maintenanceState` flip only, not a fresh digest switch), immediately before
the pipeline is
triggered. An earlier version of this section framed this as a choice
between switching to the digest *or* re-resolving and diffing the tag
against the digest as an alternative; that framing is gone now that the
digest switch itself is a required step this runbook takes — once the
bicepparam pins the digest directly, there is no longer a tag to re-resolve
against, so diffing it is neither necessary nor meaningful as an alternative
path. Do not skip Step 2b and do not assume the tag still resolves to the
exact image validated by this document in its place.

## 4. Rollback scope and timing

**Path A is currently the only implementable recovery path.** A second path
("Path B", redirecting workloads to a PITR-restored server) was previously
described as a ready procedure. It is not: see "Path B is not currently
implementable" below for what would need to be built first.

| Path | Scope and consequences |
|---|---|
| **A — Recover `litellm` onto the original server (implementable today)** | Restore the verified pre-change backup into a **new, empty** recovery database on the same server. Validate it there, then perform an owner-led connection/name transition. `librechat_rag` on that same server is untouched throughout. Owners, ACLs, sequence values, and views on the restored copy still need explicit verification before cutover. |
| **B — Redirect workloads to a PITR-restored server (not currently implementable — see below)** | The restored server has a new FQDN and its own copies of every database on that server, including a **historical** copy of `librechat_rag`. This is not a revision re-pin. Repointing RAG workloads to that restored copy would move them to historical embeddings — do not do this as part of a `litellm`-only recovery. |

**Connection-string/IaC consumers of `postgresql.bicep`'s outputs** (traced
directly in `main.bicep` and verified against `jobs.bicep` itself — an
earlier version of this table incorrectly stated that the cleanup job
consumes `liteLlmConnectionString`; it does not):

| Output | Consumers |
|---|---|
| `liteLlmConnectionString` | `liteLlm.bicep` (`databaseUrl` param); `jobs.bicep`'s **Okta sync job only** (`databaseUrl` param → `DATABASE_URL` env). The cleanup job in the same file declares no `database-url` secret and no `DATABASE_URL` env var at all. |
| `hostname`, `adminUser`, `adminPassword` | `jobs.bicep`'s **cleanup job** (separate `librechat_rag` connection: `postgresHost`/`postgresUser`/`postgresPassword` params → `RAG_DB_HOST`/`RAG_DB_USER`/`RAG_DB_PASSWORD` env, with `RAG_DB_NAME` hardcoded to `librechat_rag`); `ragApi.bicep` (same three params, plus `ragApiConnectionString`) |
| `ragApiConnectionString` | `ragApi.bicep` only |

No LibreChat container-app Bicep file consumes `postgresql.bicep` outputs
directly (LibreChat itself talks to LiteLLM's HTTP endpoint and to Mongo, not
to this Postgres server).

**Path B is not currently implementable.** `postgresql.bicep` takes only
`envName`, `location`, `adminUser`, and `adminPassword` as parameters; it has
**no parameter for a restored server's hostname**. Its server name is a
computed variable, `var serverName = 'psql-db-cgfe-${toLower(envName)}'` —
derived from `envName`, not settable from outside the module. Updating
`postgresAdminPassword` (or any Key Vault reference feeding it) changes only
the *password* `main.bicep` passes to `postgresql.bicep`; it has no effect on
which server that password is checked against, because the module always
computes and deploys against `psql-db-cgfe-<env>`. There is currently no Bicep
parameter or mechanism anywhere in this module chain (`postgresql.bicep`,
`liteLlm.bicep`, `jobs.bicep`, `ragApi.bicep`) to redirect any consumer to a
different server's FQDN. Describing "update the password reference" as a way
to redirect to a restored server was therefore incorrect — there is no host
to redirect to without additional IaC work.

**What would need to be added before Path B could be used:** a host-override
parameter (e.g. `postgresHostOverride string = ''`) threaded through
`postgresql.bicep` so its outputs (`hostname`, and the connection strings
built from it) can point at an operator-supplied FQDN instead of the
always-computed `psql-db-cgfe-<env>` name, plus a decision on how to keep
`librechat_rag` pinned to the *live* server while `litellm` alone moves to the
restored one (since today a single module instance serves both databases from
one server/one set of outputs). That work has not been done and has not been
rehearsed. **Until it exists, Path B is unavailable — not a slower fallback,
not a documented-but-untested option. Path A (recover onto the original
server) is the only implementable recovery path for a `litellm`-only
incident.**

Writers (LiteLLM, both jobs) must stay stopped for the duration of Path A.
Preserve failure-state evidence (logs, catalog state) before starting
recovery. `attribution`'s tables and both rollup views must be restored and
verified alongside the `public` schema — they live in the same database, so a
`litellm`-database-level restore includes them, but they need their own
row-count/view-resolution check afterward (do not assume `pg_restore --clean
--if-exists` alone proves new objects absent from the old archive were
removed — it does not).

**Estimated recovery timeline (Path A only) — planning estimates only, not
measured, not an agreed SLA:**

| Phase | Estimate |
|---|---|
| Fault assessment, stop/drain writers | 10–15 min |
| Azure PITR restore completion into the same server | 15–30 min (Azure-side, largely unmeasured) |
| Database extraction/restore + validation | 15–30 min |
| Data/application/reporting/job checks before resuming traffic | 15–20 min |

These numbers are unvalidated planning placeholders pending an actual owner-run
rehearsal against a real Azure PITR restore; replace them with measured
timings once that rehearsal happens. **Full backup/restore validation
(sequence values, ownership, permissions, database-level settings) has not yet
happened against a complete dump — the local Docker-only rehearsal covers
schema and row-data mechanics, not Azure recovery or sequence/ACL recovery.**
The Path-B-only "IaC/secret changes + redeploy" line from an earlier version
of this table has been removed along with Path B itself, above — it estimated
work for a mechanism that does not exist.

## 5. Recovery boundaries and partial failure

Two distinct boundaries, each with a different recovery consequence:

**Boundary 1 — Remediation commit.** Before `01-baseline-remediation.sql`'s
`COMMIT`, any statement failure rolls back everything in that transaction —
the live schema is unchanged. **After** it commits, the live schema has
changed (the new table and columns exist) even though migration history is
still absent. At that point, an image-only re-pin does **not** reverse
anything — the only way back is the recovery path in section 4 (Path A; not
yet rehearsed against a real Azure PITR restore).

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
| Migration partially applied (deploy failed partway) | **Stop.** Capture the ledger (`_prisma_migrations`), the Postgres error, and the current catalog state. Do not rerun, do not delete history, do not auto-resolve. Follow the recovery path in section 4 (Path A; not yet rehearsed against a real Azure PITR restore) |

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
- `ChatGptForEmployees.docs/local/LiteLLM-v1.99.0-Review-Implementation-Guide.md`
  — the review guide itself, now tracked (it was never committed despite being
  listed in its own artifact table).

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
not have a documented "pause" API call. **The apparent supported approach
(unverified — Azure CLI is not available in this preparation environment)**
is to update the job's `scheduleTriggerConfig` via `az containerapp job
update` to a cron expression that will not fire during the window, and
confirm the effective state afterward. A concrete candidate command, named
here specifically rather than left abstract, is:

```
az containerapp job update -n <job-name> -g <resource-group> --cron-expression "0 0 31 2 *"
```

`0 0 31 2 *` ("00:00 on February 31st") is a commonly-used never-fire
sentinel — February never has a 31st day, so a standard 5-field cron
scheduler never matches it, which stops the job firing without deleting or
disabling its trigger configuration outright. **This exact command has not
been run against a real job in this preparation environment and is therefore
unverified** — before the actual maintenance window, an operator with Azure
CLI access must confirm `az containerapp job update` accepts
`--cron-expression` on an existing scheduled-trigger job (check the current
[Azure Container Apps job command
reference](https://learn.microsoft.com/en-us/cli/azure/containerapp/job?view=azure-cli-latest)
for the deployed CLI version, since parameter support can change between
versions) and that the resulting `job show` output reflects the new,
non-firing expression before relying on it. This step is **owner-led**. "Apply
the candidate pause mechanism" below is labeled unverified for that same
reason — this document does not claim the command above has been tested
against a live job, only that it is a concrete, specifically-named candidate
rather than an abstract description.

**`job show` vs. `job execution list` — these check different things and
must not be conflated:** `az containerapp job execution list` reports
execution *history/state* (past and currently-running executions) — it does
not report the job's *configured* trigger type or cron schedule. Confirming
what will fire in the future — the actual pause target — requires `az
containerapp job show` (see the [job command
reference](https://learn.microsoft.com/en-us/cli/azure/containerapp/job?view=azure-cli-latest#az-containerapp-job-show)
and the separate [execution command
reference](https://learn.microsoft.com/en-us/cli/azure/containerapp/job/execution?view=azure-cli-latest)).
An earlier version of this procedure used `execution list` alone for both
purposes; that was incorrect and is corrected below.

**Procedure (owner-executed):**

1. For both jobs, run **two separate checks, not one:**
   - `az containerapp job show -n <job-name> -g <resource-group>` — capture
     the configured `triggerType` and `scheduleTriggerConfig.cronExpression`
     (the values this document expects: `0 5 * * 2,5` for
     `job-cgfe-okta-sync-<env>`, `0 2 * * *` for `job-cgfe-cleanup-<env>`)
     *before* changing anything. This is the record of what is configured to
     fire, not what has fired.
   - `az containerapp job execution list -n <job-name> -g <resource-group>` —
     capture any currently-running or recently-completed executions
     separately. This is state/history, not configuration.
2. Apply the candidate pause mechanism above (**owner-led, unverified** — see
   above; if the `--cron-expression "0 0 31 2 *"` candidate is rejected or
   behaves unexpectedly, do not substitute an untested command silently —
   stop and re-verify against the current CLI reference first). Re-run
   **both** `job show` (to confirm the effective trigger configuration no
   longer permits a run during the window) and `job execution list` (to
   confirm no new scheduled execution has started) to verify the pause took
   effect.
3. If an execution is already running when the window starts, wait for it to
   finish or stop it deliberately per Behnam's window plan (checked via `job
   execution list`) — stopping one execution does not, by itself, pause its
   schedule (that is a `job show`-level configuration change, not an
   execution-level one).
4. Confirm the deployment pipeline cannot silently redeploy and restore the
   original schedule mid-window (check whether a maintenance parameter is
   needed, or whether a post-deploy pause/check step suffices, given the
   pipeline's `bicepDetectFolder: ''` setting means every push re-runs
   `BicepCreate` regardless of what changed — Bicep reapplying the
   originally-declared cron expressions on redeploy is the specific failure
   mode this step guards against).
5. After database verification, restore the exact original schedule
   configuration, confirm it via `job show` (configuration) and `job
   execution list` (that no unwanted run occurred in the interim), and run
   or schedule one controlled catch-up sync if the Tuesday/Friday window was
   missed.
6. Record the result, including whether any run alerted or retried
   unexpectedly, and which of the two commands (`show` vs. `execution list`)
   supported each claim in the record.

If Behnam explicitly decides to accept a missed/failed sync run instead of
pausing, record that decision explicitly here, along with its alert/retry
consequence and the catch-up plan — an expected failure is not the same thing
as a pause and must not be described as one.

## 8. Follow-up review implementation (through `89c57d0`)

**Naming note:** this is top-level section "8", not to be confused with §2a's
"Step 8" and its "8a"–"8f" sub-steps, which are a different, pre-existing
numbering scheme nested inside section 2a (now 8a/8b/8c/8d/8e/8f — two extra
sub-steps were added across two rounds of corrections; see §8.1). Cross-
references below spell out "§2a Step 8b" etc. in full for exactly this
reason.

This section implements the three findings from the implementation guide's
`89c57d0` follow-up review (Findings 1–3), **and has itself since been
corrected twice**, in response to two further follow-up reviews of these
working changes:

- The first (referred to throughout as the "`89c57d0` working-changes
  follow-up") found three defects: the maintenance mechanism in §8.1
  released traffic and job schedules together, before any application check
  ran; the Step 8a final-reference generation procedure in §8.2 skipped
  executing the baseline SQL; and the schema manifest in §8.2 compared
  physical column position, rejecting a valid remediation pattern.
- The second (referred to throughout as the "second working-changes
  follow-up") found two more: even after the first correction, switching
  straight from `'litellm-only'` to `'off'` still started LibreChat and
  resumed both job schedules *before* any LibreChat-dependent check (login,
  streaming, conversations, upload) had run at all — direct LiteLLM success
  doesn't prove the complete application works; and Step 8d's synthetic
  check had no concrete, runnable execution mechanism — just a list of
  unresolved candidates.

All five are fixed and re-validated below, in place, rather than in a
separate section — see §8.1's, §8.2's, and §8.5's own "corrected"/
"follow-up" callouts for exactly what changed and how each fix was
re-verified. §8.6's summary table names which round fixed which defect.

Neither this section nor its corrections authorize database changes or
deployment — the same status as the rest of this document: **no remote DDL,
migration resolution, migration deployment, Azure mutation, or application
request has been performed against dev, Azure, or any other real environment
as part of this section, including its corrections.** All validation below
ran against ephemeral local Docker containers only, using the same pinned
digest
(`ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5`,
already present in the local Docker image cache from earlier sessions'
work) already validated elsewhere in this document.

### 8.1. Maintenance-state enforcement (Bicep) — Finding 1, corrected

**Problem restated:** `UploadConfigs` depends on `BicepCreate`, so infrastructure
deployment can start the target revision before the reviewed
`litellm_routing_config.yaml` is actually uploaded; `deployJobs=true` means a
redeploy reapplies `jobs.bicep`'s declared cron schedules from scratch,
silently undoing a manual `az containerapp job update --cron-expression`
pause. Neither gap is closed by anything in the runbook's Step 8 sequence as
previously written — that sequence only checks state *after* deployment, it
does not prevent either race from happening *during* deployment.

**This subsection was itself corrected once already**, in response to the
`89c57d0` *working-changes* follow-up review, Finding 2: "separate controlled
startup from traffic and job release." The first implementation used a
single `maintenanceMode bool` gating LiteLLM's scale and both jobs' cron
together — release was one flip that brought LiteLLM to normal scale
**and** resumed both job schedules **at the same time**, before Step 8d's
controlled synthetic checks had run at all. That is exactly backwards: it
released real traffic and resumed jobs *before* the checks meant to
authorize that release. The design below replaces that boolean with a
three-value `maintenanceState`, described in full further down.

**Implementation — a Bicep-level `maintenanceState` parameter, not a
pipeline-ordering fix.** This repository's deploy pipeline
(`ChatGptForEmployees.pipelines/dev.yml`) is templated from an external repo
(`ROMTech/PipelineTemplates`) not present in this working tree — its actual
stage/condition internals could not be inspected as part of this
implementation, so reordering *its* stages is recorded here as an outstanding
gate (see "What is still not verified" below), not something this change
claims to have done. Instead, the fix is made structurally, in the Bicep
modules this repository does own, so that no ordering of the pipeline's own
stages — inspected or not — can matter.

**Why one boolean was not enough:** LiteLLM's own ingress is already
`external: false` (internal-only) — the only realistic path an ordinary
employee has to it is through LibreChat. Step 8d's controlled synthetic
checks need LiteLLM itself running (a stopped container can't serve even a
synthetic request), but must NOT expose it to ordinary employee traffic
before those checks pass, and must NOT resume either job's schedule before
they pass either. A single true/false can express "everything stopped" or
"everything normal," but not "LiteLLM up for direct testing, LibreChat and
both jobs still held back."

**`@allowed(['off', 'paused', 'litellm-only', 'validation']) param
maintenanceState string = 'off'`**, added to `liteLlm.bicep`, `jobs.bicep`,
`libreChat.bicep`, and threaded through `main.bicep` so all three modules
read the same value. **The fourth state, `'validation'`, was added in a
second correction round**, described after the table and the three-state
sequence below, in response to the *second* working-changes follow-up,
Finding 1: "validate LibreChat before releasing users and jobs" — direct
LiteLLM success (`'litellm-only'`) doesn't prove the complete application
works, and the original design still switched straight to `'off'` (full
release) as the only way to bring LibreChat up at all, which resumed both
job schedules and opened ordinary access at the same moment as the very
first LibreChat-dependent check.

| State | `liteLlm.bicep` scale | `libreChat.bicep` scale | `libreChat.bicep` ingress | `jobs.bicep` cron |
|---|---|---|---|---|
| `off` (default) | normal | normal | unrestricted | normal (`0 5 * * 2,5` / `0 2 * * *`) |
| `paused` | 0/0 | 0/0 | n/a (0 replicas) | never-fire sentinel (`0 0 31 2 *`) |
| `litellm-only` | normal | **0/0** | n/a (0 replicas) | never-fire sentinel |
| `validation` | normal | **normal** | **tester IP allow-list only** | never-fire sentinel |

The key asymmetries: in `litellm-only`, LiteLLM is up but LibreChat — the
only thing an ordinary employee actually calls — is still at 0/0. In
`validation`, LibreChat is ALSO up (so an authorized tester can exercise the
real UI), but its ingress is restricted to `maintenanceTesterIpRanges` only,
via Azure Container Apps' `ipSecurityRestrictions` — a real ingress-level
access control, not a replica-count proxy for one. Both jobs stay paused in
every state except `off`.

**The four-deploy sequence (was three, was two):**

1. **Enter maintenance = `'paused'` (§2a Step 2b).** Commit
   `main.dev.bicepparam` with `liteLlmImage` switched to the pinned digest
   (§3b) **and** `maintenanceState = 'paused'` in the same commit, then push.
   Whatever order `BicepCreate` / `UploadConfigs` / `DeployLiteLLM` actually
   run in, LiteLLM and LibreChat are both forced to 0 replicas by the Bicep
   template itself, and both job schedules are forced to the never-fire
   sentinel — it is structurally impossible for any target image to serve a
   single request, or for either job to fire, during this deploy, whether or
   not the reviewed config has already landed on the Azure File Share by the
   time the revision is created. Once this deploy completes,
   `litellm_routing_config.yaml` **is** correctly on the File Share (uploaded
   during this same run), and the target image/env are the reviewed ones —
   but nothing is serving yet. Verify via `az containerapp show`/`job show`
   (both apps at 0/0, both jobs at the sentinel) before proceeding to the
   database migration steps.
2. Run the migration sequence (§2a Steps 3–7) against the now-paused,
   already-correctly-configured environment.
3. **Bring LiteLLM up for direct testing = `'litellm-only'` (§2a Step 8b).**
   Once Step 8a's schema/view verification gate passes (§8.2/§8.3, plus the
   existing fingerprint/ledger/checksum checks), commit `main.dev.bicepparam`
   with `maintenanceState = 'litellm-only'` **alone** — image/config
   unchanged since step 1 — and push. LiteLLM returns to normal scale;
   LibreChat and both jobs remain paused. Verify effective state (8c), then
   run Step 8d's controlled synthetic checks — including §1's pending
   prompt-storage query — directly against LiteLLM's internal endpoint via
   `job-cgfe-synth-check-<env>` (§8.5; never through LibreChat, which is
   still down).
4. **Bring LibreChat up for authorized-tester validation = `'validation'`
   (§2a Step 8e, new in the second correction).** Once 8d's checks pass,
   commit `main.dev.bicepparam` with `maintenanceTesterIpRanges` set to the
   tester's actual public IP **and** `maintenanceState = 'validation'`
   together, and push. LibreChat comes up, restricted to that IP; both jobs
   remain paused. Run the LibreChat-dependent application smoke tests (Okta
   login, streaming, model picker, conversations, upload) from that IP only.
5. **Release = `'off'` (§2a Step 8f).** Only once 8e's checks pass, commit
   `main.dev.bicepparam` with `maintenanceTesterIpRanges = []` **and**
   `maintenanceState = 'off'` together, and push. LibreChat opens to
   everyone and both jobs resume their normal schedules, with a controlled
   catch-up per §7 if a scheduled run was missed. Nothing about the
   image/config changes in this step either.

This replaces Step 3's manual `az containerapp update --min-replicas 0
--max-replicas 0` as the *primary* mechanism for keeping both apps at zero
replicas through the window (that manual command, and its
revision-deactivation alternative, remain a valid immediate, out-of-band
fallback — e.g. if an operator needs to react before any Bicep deploy can run
— but a subsequent Bicep deploy with `maintenanceState` left at its default
`'off'` would silently undo either one; only committing a non-`'off'` value
survives a redeploy). The same reasoning applies to §7's `--cron-expression`
candidate pause command for the two scheduled jobs.

**`maintenanceTesterIpRanges` fails closed, not open.** If `maintenanceState
= 'validation'` is deployed with this array left empty, `libreChat.bicep`
substitutes the reserved, unroutable `0.0.0.0/32` rather than applying no
restriction at all (an empty `ipSecurityRestrictions` array is Azure's
"no restriction" value, which would silently readmit ordinary traffic
instead of blocking it). A misconfigured `'validation'` deploy therefore
blocks the tester too, rather than accidentally exposing the app —
noticeable and fixable, rather than silently unsafe.

**Validated:** `bicep build`/`bicep what-if` could not be run in this
preparation environment (neither `bicep` nor `az` is installed — same
limitation already recorded in §3a(a) for the original `DISABLE_SCHEMA_UPDATE`
change; this document treats the pipeline's own
`insert-stage-bicep-whatif.yml@templates` stage as the actual syntax gate, not
this preparation environment). The conditional logic itself was manually
traced against all three modules' full resource blocks line-by-line to
confirm `maintenanceState` (and `maintenanceTesterIpRanges`) is read in
exactly the places intended (`liteLlm.bicep`'s and `libreChat.bicep`'s
`scale` blocks; `libreChat.bicep`'s `ipSecurityRestrictions`; `jobs.bicep`'s
two `cronExpression` values) and nowhere else silently short-circuits it —
in particular, that `liteLlm.bicep` compares only against `'paused'` while
`libreChat.bicep`'s scale compares against `('off' or 'validation')` and its
`ipSecurityRestrictions` compares only against `'validation'` — three
different comparisons, deliberately, which is what actually produces the
asymmetric `litellm-only`/`validation` rows in the table above.

**What is still not verified (owner-led / outside this repo):**

- The external `ROMTech/PipelineTemplates` stage definitions themselves were
  not inspected — this implementation deliberately does not depend on their
  internals (see above), but an operator should still confirm no stage in
  that template repo does something this Bicep-level mechanism can't
  override (e.g. a stage that calls `az containerapp update --min-replicas`
  directly, bypassing the Bicep-declared scale, would not be caught by
  `maintenanceState` and needs separate reconciliation if it exists).
- The actual `az containerapp show`/`job show` effective-state checks after a
  real non-`'off'` deploy — this is Azure-CLI-dependent and requires the
  owner-led pipeline run; not performed here.
- Whether Azure Container Apps accepts a `scale` update from `{min:2,max:2}`
  (or whatever the environment's normal values are) down to `{min:0,max:0}`
  and back via a Bicep-driven revision update, as opposed to the
  `az containerapp update` CLI form already noted as unverified in Step 3 —
  same underlying Container Apps API, but not independently confirmed here.
- Whether Azure Container Apps' `ipSecurityRestrictions` actually behaves as
  documented against a real deployed app (allow-listed IP admitted, all
  others rejected) — this is a real, current Azure Container Apps ingress
  feature, but was not exercised against a live Container App in this
  preparation environment (no `az`/Azure access); confirm with a real request
  from both an allow-listed and a non-allow-listed source before relying on
  it for the actual maintenance window.
- Whether `az containerapp job start` and `az containerapp job execution
  list`/`job logs show` behave exactly as §2a Step 8d now documents against a
  real Manual-trigger job — the job's own script logic was validated locally
  (§8.5), but the ACA job-invocation mechanism itself was not (no `az`
  access).

### 8.2. Complete baseline and target-schema comparison — Finding 2

**New artifact:** `ChatGptForEmployees/scripts/02-schema-manifest.sql` — a
read-only, parameterized (`-v target_schemas=<comma-separated schema list>`)
catalog query producing one deterministic manifest line per table, column
(with canonical type+modifiers, nullability, and default expression),
constraint (`pg_get_constraintdef` — includes foreign-key `ON DELETE`/`ON
UPDATE` actions verbatim), and index (`pg_get_indexdef` plus `indisvalid`).
Deliberately scoped to ordinary tables (`relkind='r'`) only — views are
handled separately (§8.3) — and to whichever schema(s) are passed in, so it
never conflates LiteLLM's vendor-managed `public` tables with the custom
`attribution` schema unless both are explicitly requested together.

**Replaces** the old Step 5 / Step 8a spot checks (four table/column
presence queries plus one index-validity check) as the actual required gate;
those spot checks remain in place afterward as a fast first look, not the
gate itself (same pattern this document already uses for row counts vs. the
historical-data fingerprint).

**How the two comparisons work:**

- **Baseline gate (before `migrate resolve --applied`, Step 5):** the
  *expected* reference is generated once from the pinned image's own
  `20250326162113_baseline/migration.sql` (the same file Step 6 already
  treats as "the canonical, complete definition of the baseline-resolved
  state") applied to a fresh, empty database — **not** by also running
  `01-baseline-remediation.sql` on top of it (that script's own history guard
  correctly rejects being applied twice to a database that already has this
  state; the two paths — an old hand-maintained schema plus remediation, vs.
  a fresh database plus the vendor's own baseline migration — are meant to
  converge on the identical target schema, not be composed). The *actual*
  side is the real dev database immediately after Step 4's remediation
  script commits. Diff the two manifests; any difference blocks Step 6.
- **Final gate (before releasing traffic, Step 8a):** the *expected*
  reference is generated by applying the pinned image's complete migration
  history (`prisma migrate resolve --applied 20250326162113_baseline` +
  `prisma migrate deploy`, i.e. exactly Steps 6–7 already documented and
  tested) to a fresh, empty database. The *actual* side is the real dev
  database after Step 7 completes. Diff the two manifests; any difference
  blocks 8b/release.

**Executed this session, against the actual pinned digest** (not a
synthetic stand-in — the real reference this gate needs):

1. Extracted `20250326162113_baseline/migration.sql` from the pinned image
   and applied it alone to a fresh `postgres:16-alpine` container
   (`dev_rehearsal` database) — 17 tables created, matching the 17-table
   `LiteLLM_*` baseline. Ran `02-schema-manifest.sql -v target_schemas=public`
   against it: **270 manifest lines**, captured as the baseline reference.
2. From that same database, ran `prisma migrate resolve --applied
   20250326162113_baseline` (exit 0, `Migration 20250326162113_baseline
   marked as applied.`) then `prisma migrate deploy` (exit 0, ending
   `All migrations have been successfully applied.`) then `prisma migrate
   status` (`157 migrations found`, `Database schema is up to date!`) — the
   same sequence and same result already recorded in Step 6/7's own
   validation, reproduced again here as the source for the *final* manifest.
   Ran `02-schema-manifest.sql` again: **75 tables, 1384 manifest lines**,
   captured as the final reference. `diff` against the baseline reference
   showed 1,198 added/changed lines (new tables/columns/constraints/indexes
   from the 156 migrations) and zero unexpected removals or alterations of
   anything present at baseline — consistent with additive-only migrations.
3. Confirmed the pinned image's own vendor schema declares **zero views**
   (`03-view-inventory.sql -v target_schemas=public` against the fully-
   migrated reference returned no rows) — direct confirmation that the 8
   `public` + 2 `attribution` views this project already tracks are entirely
   custom additions, never something to diff against this pinned-image
   reference (see §8.3).
4. **Detection validated against isolated fixtures**, independent of the
   real-image run above: a small synthetic two-table schema (`Org`/`User`,
   with a default, a unique index, and a foreign key with `ON DELETE
   SET NULL ON UPDATE CASCADE`) produced a clean, empty diff against itself,
   then each of the following deliberately-introduced defects was
   independently confirmed to produce a non-empty, correctly-localized diff:
   a dropped column (with its default), a changed default value, a dropped
   unique index, and a dropped foreign-key constraint. No false negatives
   and no false positives were observed across the four cases.

**Two corrections made after a follow-up review of these working changes
(`89c57d0` working-changes follow-up):**

- **Finding 1 — the Step 8a *final*-reference generation block skipped
  executing the baseline SQL.** The standalone PowerShell block originally
  written into §2a Step 8a (as opposed to the interactive sequence actually
  run for item 2 above, which reused the same database item 1 had already
  applied `baseline-migration.sql` to) went straight to `prisma migrate
  resolve --applied` + `prisma migrate deploy` against a **freshly created,
  still-empty** container. `migrate resolve --applied` only records a ledger
  row — it executes no SQL — so that block would have marked the baseline
  "applied" without ever creating its tables, then handed `migrate deploy`
  156 later migrations (mostly `ALTER TABLE` against tables that were never
  created) to run against an empty schema. Fixed by adding the same
  extract-and-apply-`baseline-migration.sql` step used everywhere else in
  this document (Step 5, and item 1 above) before the resolve/deploy calls.
  **Re-executed in full after the fix**, specifically to verify it: baseline
  SQL applied (exit 0), `migrate resolve --applied` (exit 0, `Migration
  20250326162113_baseline marked as applied.`), `migrate deploy` (exit 0,
  `All migrations have been successfully applied.`), and
  `02-schema-manifest.sql` against the result: **75 tables, 1384 manifest
  lines** — matching item 2's figures, confirming the corrected standalone
  block now produces the same result the interactive session already had.
- **Finding 3 — the manifest's COLUMN record included physical ordinal
  position (`pg_attribute.attnum`), rejecting a valid remediation pattern.**
  The vendor baseline declares a column like `sso_user_id` inline in its
  `CREATE TABLE`, at whatever position `schema.prisma` puts it; the real
  remediation script (`01-baseline-remediation.sql`) instead catches an old,
  pre-Prisma database up to that same schema using `ALTER TABLE ... ADD
  COLUMN`, which always appends the column physically last. Both produce a
  logically identical column (same name, type, nullability, default, and
  every constraint/index referencing it) at a different physical position —
  comparing `attnum` as part of equivalence rejected that valid, intentional
  pattern. Fixed by dropping `attnum` from the COLUMN record entirely
  (columns are still identified and ordered by name, keeping output
  deterministic); composite index/constraint column order is unaffected,
  since `pg_get_indexdef`/`pg_get_constraintdef` already encode that order by
  column name, not raw `attnum`. **Validated with a new positive fixture**
  built specifically for this: the same logical table (`user_id` PK, `email`,
  `sso_user_id` with a unique index) constructed two ways — inline in one
  `CREATE TABLE` (`sso_user_id` declared second), and as a base table without
  it followed by `ALTER TABLE ... ADD COLUMN "sso_user_id"` (appended last)
  — produced **byte-identical manifests, confirmed via `diff` returning
  nothing**, after the fix; both manifests were captured and are recorded as
  identical. **Regression-checked**: all four of item 4's original negative
  fixtures (missing column, wrong default, missing unique index, missing
  foreign key) were re-run against the fixed script and still produce the
  same correctly-localized diffs as before — the fix did not weaken
  detection of any of them.

Both reference manifests (the 270-line baseline and 1384-line final) are
reproducible from the exact commands above and are **not** committed to this
repository as static files — like the fingerprint/checksum working files
elsewhere in this document, they are regenerable derived artifacts, not
source, and a committed copy would only risk silently going stale against a
future re-pin of the digest.

**Wired in:** §2a's Step 5 and Step 8a now each include this exact gate as
literal commands, in addition to (not replacing) the original four-query/
one-index spot checks, which remain as a fast first look.

### 8.3. View definition and execution verification — Finding 3

**New artifacts:**

- `ChatGptForEmployees/scripts/03-view-inventory.sql` — read-only, captures
  `pg_get_viewdef(oid, true)` for every view in the requested schema(s), with
  embedded newlines translated to the literal two-character sequence `\n` so
  each view's full multi-line definition stays exactly one manifest line
  (unambiguous for line-based diffing — the old check only compared
  schema/name pairs, so a same-named view with a changed query was invisible
  to it).
- `ChatGptForEmployees/scripts/04-view-execution-check.sql` — read-only,
  inside an explicit `READ ONLY` transaction with a 10s statement timeout,
  actually executes every view via safely-quoted dynamic SQL (`format('%I.%I',
  ...)` + `\gexec`) and aggregates a row-count plus an md5 hash of every row's
  full content (`string_agg(v::text, '')`) — never the row content itself.

**A real defect was found and fixed while validating this, not merely
assumed safe:** the first draft used a bare `SELECT count(*) FROM <view>`.
Tested against a fixture view whose `SELECT` list contained
`CAST(email AS integer)` (guaranteed to fail against real email strings),
`count(*)` returned a row count successfully with **no error** — `EXPLAIN
VERBOSE` confirmed why: because `count(*)` never references any of the
view's projected columns, Postgres's planner proves the cast is unused and
prunes it from the plan entirely, so a genuinely broken view passes a
count(*)-only check. This is the same class of mistake Follow-up 3 already
named for catalog enumeration/`LIMIT 0` substituting for execution — it just
takes a sharper form here, since `count(*) FROM view` looks like it "runs the
view" but structurally cannot force evaluation of anything the view
projects. The fix (hashing every row's full text via `string_agg`) was
re-tested against the same broken-cast fixture and correctly failed with a
nonzero exit and no rows ever printed; a control run against an unmodified
view (both zero rows and with an inserted row) correctly succeeded with a
stable hash.

**Validated fixture matrix, this session, against isolated Docker Postgres:**

| Case | Expected | Observed |
|---|---|---|
| Unmodified view, 0 rows | Inventory diff empty; execution succeeds | ✅ both |
| Unmodified view, 1 row | Execution succeeds, stable hash | ✅ |
| Same name, changed join (`JOIN` → `LEFT JOIN`) | Inventory diff non-empty | ✅ (single differing line, correctly localized) |
| Same name, query fails at runtime (bad numeric cast on free-text data) | Execution check fails, nonzero exit, no row content printed | ✅ (after the count(*)→string_agg fix above; confirmed failing on the original count(*) draft first, then confirmed fixed) |
| Pinned image's own final schema | Zero views (vendor schema declares none) | ✅ — confirms the 8 public + 2 attribution views are entirely custom, per §8.2 |

**Replaces** the schema/name-only view list in Step 3.5 (pre-remediation
capture) and Step 8a (post-migration comparison) as the required gate for
view *definitions*, and adds an execution check that did not exist at all
before this change. The existing row-count checks for the two attribution
rollup views, and the view-name-list `Compare-Object` check, remain in place
as supporting evidence.

**Wired in:** §2a's Step 3.5 now captures definitions via
`03-view-inventory.sql` alongside the existing name-list capture, frozen the
same way as `03-fingerprint-frozen.sql`; Step 8a now diffs that frozen
capture against a post-migration re-capture and runs
`04-view-execution-check.sql`, both as required, enforced-`throw` gates.

### 8.5. Application-release validation phase and executable synthetic check — second working-changes follow-up

**Finding 1 — "validate LibreChat before releasing users and jobs"** is
implemented as the fourth `maintenanceState` value, `'validation'`, and its
own runbook step (§2a Step 8e), described in full in §8.1 (see that
subsection's "second correction round" table and four-deploy sequence) —
not repeated here. In short: LibreChat now comes up, restricted to an
authorized tester's IP via `ipSecurityRestrictions`, in a distinct state
between "LiteLLM verified directly" (`'litellm-only'`) and "everyone let in"
(`'off'`), so the LibreChat-dependent smoke tests (Okta login, streaming,
model picker, conversations, upload) run and pass *before* ordinary
employees or either scheduled job are released — closing the exact ordering
defect the review found.

**Finding 2 — "make the internal synthetic test executable"** is implemented
as:

- `ChatGptForEmployees/scripts/05-synthetic-litellm-check.py` — a new,
  fully-specified script (see its own docstring for the complete exit-code
  table, environment variables, and content-handling rules) that checks
  LiteLLM's health endpoints, sends one synthetic chat completion with a
  unique, identifiable marker, polls `LiteLLM_SpendLogs` for that specific
  row within a bounded wait, and verifies `messages`/`response` match the
  documented empty representation — printing only match/mismatch status,
  never row content.
- A new manually-triggered (`triggerType: 'Manual'`) ACA Job,
  `job-cgfe-synth-check-<env>`, added to `jobs.bicep`, reusing the existing
  `librechat-cleanup` image (this script is now also `COPY`'d into
  `Dockerfile.cleanup`) and admin-credential ACR-pull pattern already
  established for the two scheduled jobs — this is the "one prepared
  execution location" the review required: it runs inside the same
  Container Apps environment as `ca-litellm-<env>`, so it resolves
  LiteLLM's internal FQDN without exec-ing into any container, and the
  operator starts it with a single documented command
  (`az containerapp job start -n job-cgfe-synth-check-<env> -g
  <resource-group>`, §2a Step 8d).

**Validated against an isolated Docker LiteLLM (mock response, matching the
actual shipped `store_prompts_in_spend_logs: false` /
`STORE_PROMPTS_IN_SPEND_LOGS=false` configuration) and Postgres, running the
real script file unmodified in every case** (full table also in §2a Step 8d):
healthy/matching-row/pass (exit `0`); wrong master key (exit `2`, HTTP 401);
nonexistent model name (exit `2`, HTTP 400); completion succeeds but the
polled database has no matching row within the bound (exit `3`, distinct
from "couldn't check"); database unreachable (exit `5`, distinct from "ran
and found nothing"); and content actually populated (exit `4`, no content
printed).

**A real defect was found and fixed during this validation, not merely
assumed correct:** the first draft compared the `messages`/`response`
values read back from Postgres against the Python string `"{}"`. Running it
against a live row (`pg_typeof` confirmed the column is `jsonb`) showed
`psycopg2` auto-adapts a `jsonb` column to a native Python object — an empty
`dict`, not the string `"{}"` — so that comparison was **always** `False`
regardless of the row's actual content. Every run of the original draft
would have raised a false "content is populated" alarm on a database where
storage was genuinely off, exactly the kind of false-positive-into-a-real-
incident-escalation this script exists to prevent. Fixed to compare against
the Python `{}` value directly (keeping the string form as a defensive
fallback), then re-validated against both the true-empty and the
deliberately-populated cases above to confirm the fix behaves correctly in
both directions, not just the direction that was broken.

**Cleanup:** none required per invocation — `job-cgfe-synth-check-<env>` is
a standing Bicep-declared resource the operator starts on demand, not a
throwaway container created and torn down each time.

**What is still not verified (owner-led / outside this repo):** the ACA
job-invocation mechanism itself (`az containerapp job start` /
`job execution list` / `job logs show`) against a real deployed job, and
`ipSecurityRestrictions`' actual enforcement against a real deployed app —
both listed in §8.1's own "what is still not verified," not repeated twice.

### 8.6. Summary and outstanding gates

| Round | Finding | Status |
|---|---|---|
| `89c57d0` follow-up | 1 — maintenance isolation | Bicep mechanism implemented (`liteLlm.bicep`, `jobs.bicep`, `libreChat.bicep`, `main.bicep`, `main.dev.bicepparam`) and wired into §2a as Steps 2b/8b–8f. **Corrected twice** (see the next two rows) |
| `89c57d0` follow-up | 2 — baseline/target schema comparison | `02-schema-manifest.sql` implemented, validated against the real pinned image (full 17→75 table run, re-verified after the working-changes corrections) and against synthetic fixtures (4/4 defect classes detected, regression-checked after the Finding-3 fix below), wired into §2a Step 5 and Step 8a as required, enforced-`throw` gates |
| `89c57d0` follow-up | 3 — view definition/execution verification | `03-view-inventory.sql`/`04-view-execution-check.sql` implemented; a real detection gap (`count(*)` pruning) was found and fixed during the original validation pass; 5/5 fixture cases behave as expected; wired into §2a Step 3.5 and Step 8a as required, enforced-`throw` gates; no defects raised against this finding by either later follow-up |
| working-changes follow-up | 1 (Finding 2 above, defect) — Step 8a final-reference generation skipped baseline SQL | Fixed: the standalone block now applies `baseline-migration.sql` before `migrate resolve`/`migrate deploy`, matching the pattern already used elsewhere; re-executed in full after the fix (75 tables, 1384 lines, matching) (§8.2) |
| working-changes follow-up | 2 (Finding 1 above, defect) — `maintenanceMode bool` released traffic + jobs together | Fixed: redesigned to a three-value `maintenanceState` (`'off'`/`'paused'`/`'litellm-only'`) (§8.1) — **itself found insufficient by the second working-changes follow-up; see below** |
| working-changes follow-up | 3 (Finding 2 above, defect) — manifest compared physical column position | Fixed: `attnum` dropped from the COLUMN record; validated with a new inline-vs-appended-column fixture (byte-identical manifests) and a full regression check of the original 4 negative fixtures (§8.2) |
| second working-changes follow-up | 1 — validate LibreChat before releasing users and jobs | Fixed: `maintenanceState` extended to a fourth value, `'validation'` (LibreChat up, restricted to an authorized tester's IP via `ipSecurityRestrictions`; both jobs still paused), with a new §2a Step 8e between the old `'litellm-only'` and release steps (§8.1, §8.5) |
| second working-changes follow-up | 2 — make the internal synthetic test executable | Fixed: `05-synthetic-litellm-check.py` (new script, fully bounded/exit-coded) plus a new manually-triggered `job-cgfe-synth-check-<env>` ACA Job as its prepared execution location; validated end-to-end against a local Docker LiteLLM+Postgres harness across 6 cases (pass, bad auth, bad model, no-row-found, db-unreachable, content-populated); **a real bug (psycopg2 jsonb-vs-string comparison, always false) was found and fixed during that validation** (§8.5) |

**Three full follow-up review passes have now found real, confirmed defects
in this section's own implementation** across two rounds of "working
changes" corrections: a bool that couldn't express the required states (then
found still insufficient once extended, requiring a second extension to four
states); a reference-generation procedure that skipped a required step; a
comparison field that produced false positives; a release sequence that
skipped application validation entirely; and an unspecified test-execution
mechanism. Each was fixed and re-validated against the same isolated
fixtures/real-image runs used originally (with new fixtures added where the
original ones didn't cover the defect), not merely asserted fixed. This
history is recorded plainly — including the fact that the Finding-1 fix
itself needed a second, later correction — because it is directly relevant
to how much confidence to place in this section without a further
independent review pass, not to minimize it. Given that pattern, an
additional independent review of this section specifically (not just of the
original three findings) would be reasonable before relying on it for a real
maintenance window.

**What would still make each finding fully closed, beyond this pass:** an
actual owner-led dev run exercising Step 2b through 8f against the real
Azure environment and the real dev database — the same "execution remains
owner-led / pending" boundary that applies to every other change in this
document (§1's dev query, §2a generally, §3a(a)'s Bicep build), plus the
specific unverified items each subsection lists (external pipeline-template
internals, `ipSecurityRestrictions` enforcement, `az containerapp job start`
behavior). This section implements and locally validates all findings raised
against it so far; it does not, and cannot from this preparation
environment, supply real-environment execution evidence, and it cannot rule
out a further, not-yet-found defect the way real execution eventually would.
