# LiteLLM v1.99.0 review — response

Indexed to your seven notes. Full detail in `REVIEW-AND-CUTOVER.md` in this
same folder. Nothing in this response required touching dev, deploying, or
messaging anyone else — it's being sent to you directly, now, as the
authorized handoff.

1. **Prompt/response storage** — traced to source in the pinned image
   (digest `sha256:570a872d...`). Controlling function
   `_should_store_prompts_and_responses_in_spend_logs()` is an **OR-gate, not
   an override**: it returns true if `general_settings.store_prompts_in_spend_logs`
   is true; otherwise it falls through to `STORE_PROMPTS_IN_SPEND_LOGS`
   regardless of what the general setting was — including an explicit
   `false`. An earlier version of this handoff said an explicit YAML value
   "always wins" and that no tracked config change was needed; that was
   wrong for the false/true case and has been corrected. This was verified
   two ways: source tracing, and an actual synthetic runtime test
   (`REVIEW-AND-CUTOVER.md` §1a — non-streaming, streaming, and failed-model
   paths all showed empty `{}` under the default-off case; §1b — with
   `general_settings.store_prompts_in_spend_logs: false` explicit AND
   `STORE_PROMPTS_IN_SPEND_LOGS=true`, the `response` column was populated
   with real content, confirming the OR-gate). **Tracked config change made:**
   both `store_prompts_in_spend_logs: false` (in `litellm_routing_config.yaml`
   and the local override) and `STORE_PROMPTS_IN_SPEND_LOGS=false` (in
   `liteLlm.bicep`'s env array) are now pinned explicitly, since either one
   alone is insufficient. The YAML value still wins over a DB-cached value on
   reload, so this pin is reload-safe. `turn_off_message_logging` is confirmed
   separate. The dev verification query is still pending your migration and
   real traffic.
2. **Environment guard** — rewritten to require an explicit
   `-v target_env=dev`, checked via `set_config`/`current_setting` (psql
   doesn't interpolate inside `DO $$ $$`). Verified locally in an isolated
   Docker Postgres container: missing/blank/`test`/`prod` all abort before any
   DDL with a nonzero exit and zero schema change; `dev` succeeds and produces
   exactly the expected schema.
3. **Bicep manual-migration mode** — `DISABLE_SCHEMA_UPDATE=true` added to
   `liteLlm.bicep`. Heads up: this module is shared, so it lands in Test and
   Prod on their next deploy too, not just dev. No conflicting
   `general_settings.disable_prisma_schema_update` exists in the tracked
   config, so nothing overrides it. The actual ordered, executable operator
   sequence for using this (environment/image checks through post-migration
   application checks) is now written up as `REVIEW-AND-CUTOVER.md` §2a — it
   did not exist as a single procedure before this correction; §3 previously
   pointed to "section 2/4," which only covers background, not the sequence
   itself.
4. **Rollback scope/timing** — corrected. Only Path A (recover `litellm` onto
   the original server) is currently implementable: `postgresql.bicep` has no
   parameter for a restored server's hostname (its server name is a computed
   variable derived from `envName`), so there is no mechanism today to
   redirect `liteLlm`/`jobs`/`ragApi` to a different server's FQDN. Path B is
   now marked not currently implementable, with what IaC work it would need
   named explicitly. The connection-consumer table is also corrected: the
   cleanup job does **not** consume `liteLlmConnectionString` (it has no
   `DATABASE_URL`/`database-url` secret at all) — only the Okta sync job does;
   the cleanup job uses the separate `hostname`/`adminUser`/`adminPassword`
   outputs to reach `librechat_rag`, same as `ragApi.bicep`. Timeline numbers
   are explicitly labeled planning estimates, not measured, and now cover
   Path A only.
5. **Recovery boundaries** — the pre-commit vs. post-commit vs.
   history-resolved boundaries are laid out with a phase/state table. No blind
   reruns, no history deletion, no auto-resolve after failure.
6. **Artifacts in repo** — this file, `REVIEW-AND-CUTOVER.md`,
   `scripts/01-baseline-remediation.sql`, and `liteLlm.bicep` (the
   `DISABLE_SCHEMA_UPDATE` change) are committed at the tracked paths the
   guide specifies, on branch `fix/litellm-cve-upgrade-v1.99.0-dev`, as five
   local commits:
   - `b7995cd` — corrected remediation SQL with target_env guard
   - `b824cee` — disable automatic schema mutation on startup
   - `20dc3fb` — finalized cutover and rollback runbook
   - `88cabc9` — add executed synthetic test evidence for spend-log storage
   - `7e8f4af` — short handoff response (this file)

   These commits are **local to this checkout only** — nothing has been
   pushed. Pushing the branch or opening a PR is a separate, not-yet-authorized
   next step.
7. **Scheduling** — confirmed Tue/Fri 05:00 UTC for Okta sync (the nightly
   change never merged) and nightly 02:00 UTC for cleanup. Corrected: the
   procedure previously used `az containerapp job execution list` alone to
   both capture the configured schedule and confirm a pause — that command
   only reports execution history/state, not the job's configured trigger.
   Capturing/confirming the actual schedule now uses `az containerapp job
   show` (separately from `execution list`, which still checks
   currently-running executions). Pause/resume itself is still written up as
   owner-executed/pending verification since Azure CLI access isn't available
   in this preparation environment — this document does not invent an
   untested specific pause command.

**What's still outstanding and owner-led, not done here:**

- Running any of this against the actual dev database.
- The full backup/PITR recovery rehearsal (sequences, owners, ACLs) — the
  local rehearsal covered schema/data mechanics only.
- Azure-side job pause/resume execution.
- The post-migration prompt/response verification query against real dev
  data.

No dev migration has been executed as part of preparing any of this.
