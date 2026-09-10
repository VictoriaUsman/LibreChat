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
     end_user       |     model     |  call_type  | messages | response
--------------------+---------------+-------------+----------+----------
 shipped-test-user  | gpt-3.5-turbo | acompletion | {}       | {}
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

```powershell
# Confirm the deployed LiteLLM image digest matches the pinned, reviewed digest.
az containerapp show -n ca-litellm-dev -g rg-dev-shared --query "properties.template.containers[0].image" -o tsv
```

Compare the output against
`ghcr.io/berriai/litellm@sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5`
— the exact digest every finding in this document was verified against (see
§3b's tag-vs-digest risk). **Stop if it does not match**: re-resolve and diff
per §3b before continuing.

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

**Step 3 — Stop writers.**

```powershell
# Record the current scale settings BEFORE changing anything, so Step 8's
# restart has real values to restore instead of an unfilled placeholder.
az containerapp show -n ca-litellm-dev -g rg-dev-shared --query "properties.template.scale" -o json | Tee-Object -Variable originalScale
$originalScale | Out-File -FilePath ".\ca-litellm-dev-original-scale.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw "Failed to capture original scale settings; stop before scaling down." }
```

**Note (unverified):** `--min-replicas 0 --max-replicas 0` below has not been
verified against the real Azure CLI/API in this preparation environment (no
`az` CLI access — see §3a(a)). It is the intuitive way to stop a container app
from accepting connections, but it has not been confirmed that Container Apps
accepts `--max-replicas 0` for this app's scale configuration. If it is
rejected or behaves unexpectedly, a more conservative, separately-verifiable
alternative is `--min-replicas 0 --max-replicas 1` combined with deliberately
deactivating the current revision (`az containerapp revision deactivate`),
which stops routed traffic without depending on a zero-max-replica scale
setting.

```powershell
# Scale the LiteLLM container app to zero so it cannot open new connections
# or run its own startup path against the database during remediation.
az containerapp update -n ca-litellm-dev -g rg-dev-shared --min-replicas 0 --max-replicas 0
if ($LASTEXITCODE -ne 0) { throw "Failed to scale down ca-litellm-dev; stop." }
```

Confirm zero running revisions/replicas via `az containerapp replica list`
before continuing. Both scheduled jobs are already paused from Step 2.

**Step 3a — Capture pre-remediation baseline.**

Row counts and view resolution recorded here are what Step 8's "before vs.
after" verification compares against — without this step, that later check
has nothing to compare to.

```powershell
psql -X -v ON_ERROR_STOP=1 -c "SELECT 'LiteLLM_SpendLogs' AS table_name, count(*) FROM public.\"LiteLLM_SpendLogs\" UNION ALL SELECT 'LiteLLM_UserTable', count(*) FROM public.\"LiteLLM_UserTable\" UNION ALL SELECT 'LiteLLM_VerificationToken', count(*) FROM public.\"LiteLLM_VerificationToken\" UNION ALL SELECT 'LiteLLM_OrganizationTable', count(*) FROM public.\"LiteLLM_OrganizationTable\";" | Tee-Object -FilePath ".\pre-remediation-row-counts.txt"
if ($LASTEXITCODE -ne 0) { throw "Failed to capture pre-remediation row counts; stop." }

# Confirm the attribution rollup views resolve before remediation touches anything.
psql -X -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM attribution.v_spend_by_dept_week; SELECT count(*) FROM attribution.v_spend_by_dept_month;"
if ($LASTEXITCODE -ne 0) { throw "attribution rollup views did not resolve pre-remediation; stop and investigate before proceeding." }
```

Save both outputs (`pre-remediation-row-counts.txt` and the view-count
results) somewhere the operator can compare against Step 8's post-migration
counts — they are the actual baseline that step's "before vs. after"
comparison requires.

**Step 4 — Run `01-baseline-remediation.sql`.**

Exact invocation from §2, run from the repo root:

```powershell
psql -X -v ON_ERROR_STOP=1 -v target_env=dev -f ChatGptForEmployees/scripts/01-baseline-remediation.sql
if ($LASTEXITCODE -ne 0) { throw "Remediation script failed or aborted (see §5 boundary 1) — do not proceed to Step 5." }
```

**Expected result:** the script's own `BEGIN`/`COMMIT`-wrapped output (see §2's
"Case: dev (passing)" transcript) ending in `COMMIT` and exit code `0`.
**Stop/recovery condition:** any nonzero exit means the transaction rolled
back (§5, boundary 1) — the live schema is unchanged, so it is safe to
diagnose and rerun once the cause is understood. Do **not** proceed to Step 5
on a nonzero exit.

**Step 5 — Compare the resulting schema against the expected baseline.**

```powershell
psql -X -v ON_ERROR_STOP=1 -Atc "SELECT to_regclass('public.\"LiteLLM_CredentialsTable\"');"
psql -X -v ON_ERROR_STOP=1 -Atc "SELECT count(*) FROM information_schema.columns WHERE table_name='LiteLLM_SpendLogs' AND column_name IN ('messages','response');"
psql -X -v ON_ERROR_STOP=1 -Atc "SELECT column_name FROM information_schema.columns WHERE table_name='LiteLLM_UserTable' AND column_name='sso_user_id';"
```

**Expected result:** the first query returns the table's regclass (not
`NULL`/empty), the second returns `2`, the third returns `sso_user_id`. This
mirrors the local pass-case verification already run in §2. **Stop condition:**
any mismatch means the remediation did not apply as expected — stop and
follow §5's incident route (capture state, do not rerun, do not delete
history) rather than proceeding to Step 6.

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
```

**Expected result:** all 156 remaining migrations (157 total including the
resolved baseline) apply in order, ending at the pinned image's actual final
migration, `20260819000000_shadow_eval_max_budget` (§1a/§5 corrected naming —
see Finding 5), and `migrate status` reports `Database schema is up to date!`
— exactly what the tested local run above produced. **Stop condition:** any
partial failure is boundary-2 territory (§5) — stop immediately, capture the
ledger and error, and do not attempt a forward fix without a separate,
specifically-reviewed procedure.

**Step 8 — Post-migration and application checks.**

```powershell
# All 157 ledger entries present, and their checksums match the source migration files
# shipped in the pinned image (not recomputed from a different image/tag).
psql -X -v ON_ERROR_STOP=1 -c "SELECT migration_name, checksum, finished_at IS NOT NULL AS applied FROM public._prisma_migrations ORDER BY started_at;"
```

Verify: 157 rows, all `applied = true`, and each `checksum` matches the
corresponding `migration.sql` under
`/app/litellm-proxy-extras/litellm_proxy_extras/migrations/<name>/` in the
pinned digest (spot-check a sample, or diff programmatically if the operator
has extracted the migration folder from the image).

Then:

- **Schema/index validity:** re-run the Step 5 queries plus a check that
  `20260415120000_health_check_latest_per_model_index`'s index exists and is
  valid (`SELECT indexrelid::regclass, indisvalid FROM pg_index WHERE
  indexrelid = 'public."LiteLLM_HealthCheckTable_model_id_model_name_checked_at_idx"'::regclass;`
  — not `INVALID`, which would indicate a concurrently-built index that failed
  partway).
- **Preserved historical data and views:** row counts on `LiteLLM_SpendLogs`,
  `LiteLLM_UserTable`, `LiteLLM_VerificationToken`, and `LiteLLM_OrganizationTable`
  must match the pre-remediation baseline captured in Step 3a
  (`pre-remediation-row-counts.txt`) — remediation and migration only add
  columns/tables, they must not have changed row counts; the `attribution`
  schema's two rollup views must still resolve (`SELECT count(*) FROM
  attribution.v_spend_by_dept_week;` and `SELECT count(*) FROM
  attribution.v_spend_by_dept_month;`), and their counts should match Step
  3a's baseline too.
- **Prompt-storage check:** restart `ca-litellm-dev` using the scale settings
  captured in Step 3 (`.\ca-litellm-dev-original-scale.json`) rather than an
  assumed value — e.g. `az containerapp update -n ca-litellm-dev -g
  rg-dev-shared --min-replicas <value from originalScale.minReplicas>
  --max-replicas <value from originalScale.maxReplicas>` (or, if Step 3 used
  the revision-deactivation alternative, reactivate that revision instead).
  Confirm it starts healthy (`/health/liveliness`,
  `/health/readiness`, and actual `to_regclass` table checks per §3a's
  caveat, not health-probe status alone), then run §1's pending dev query
  (`SELECT messages, response FROM public."LiteLLM_SpendLogs" ORDER BY
  "startTime" DESC LIMIT 5;`) against synthetic, non-sensitive traffic only,
  per §1's identification and no-paste-content rules.
- **Application smoke tests:** Okta login, send/stream a chat, model picker,
  existing conversations load, file upload — the same smoke-test list
  referenced elsewhere in this program's Bicep review notes.

**Only after all of the above pass**, resume the paused jobs per §7's resume
procedure (restoring `0 5 * * 2,5` and `0 2 * * *`, with a controlled
catch-up if a scheduled run was missed during the window).

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
