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
   with real content, confirming the OR-gate; §1c newly confirms the same
   `{}` result under the exact configuration actually being shipped — both
   controls `false` together, not just the default-absent case). **Tracked
   config change made:** both `store_prompts_in_spend_logs: false` (in
   `litellm_routing_config.yaml`, plus the local-only override file — see the
   note below) and `STORE_PROMPTS_IN_SPEND_LOGS=false` (in `liteLlm.bicep`'s
   env array) are now pinned explicitly, since either one alone is
   insufficient. The YAML value still wins over a DB-cached value on reload,
   so this pin is reload-safe. `turn_off_message_logging` is confirmed
   separate. The dev verification query is still pending your migration and
   real traffic. Because `litellm_routing_config.yaml` deploys to every
   environment from one file, and `liteLlm.bicep`'s env array is identical
   across environments, both pins land in Test and Prod on their next
   respective deploy too — not only dev (same shared-module point as item 3
   below). **Note on the local override:** the edit to
   `litellm_routing_config.local.yaml` is untracked (its own header says "DO
   NOT COMMIT, DO NOT DEPLOY") — it exists only on this developer's machine
   and is not a deployed control, unlike the committed
   `litellm_routing_config.yaml` and `liteLlm.bicep` changes.
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
   `scripts/01-baseline-remediation.sql`, `liteLlm.bicep` (the
   `DISABLE_SCHEMA_UPDATE` change), and the review guide itself
   (`LiteLLM-v1.99.0-Review-Implementation-Guide.md`) are committed at the
   tracked paths the guide specifies, on branch
   `fix/litellm-cve-upgrade-v1.99.0-dev`. A hardcoded commit count/list here
   has gone stale in each of the last two rounds of fixes as new commits
   landed, so rather than repeat that mistake: **run `git log --oneline
   origin/main..HEAD` yourself to see the current, authoritative list** (local
   `main` is a long-stale ref — hundreds of commits behind and from an earlier
   repo layout — so it is not a useful comparison point here; `origin/main` is
   the current, meaningful one).

   As of this fix, that list is (newest first):
   - `9e87a96` — litellm v1.99.0 review: fix round-2 critical/important findings
   - `247ae17` — litellm v1.99.0 review: track the review guide itself (was never committed)
   - `e75b04d` — docs: fix five findings from 2026-09-11 review addendum
   - `cff94a7` — litellm v1.99.0 review: address final review findings across runbook/handoff/bicep
   - `7e8f4af` — litellm v1.99.0 review: short handoff response
   - `88cabc9` — litellm v1.99.0 review: add executed synthetic test evidence for spend-log storage
   - `20dc3fb` — litellm v1.99.0 review: finalized cutover and rollback runbook
   - `b824cee` — litellm v1.99.0 review: disable automatic schema mutation on startup
   - `b7995cd` — litellm v1.99.0 review: corrected remediation SQL with target_env guard
   - `525f8cd` — Bump dev litellm image to v1.99.0 to patch critical/high CVEs
   - `cac938e` — Merged PR 12621: ADO 11662 — document the Azure Monitor OTP verification requirement for jobAlerts
   - `b991743` — ADO 11662 — document the Azure Monitor OTP verification requirement for jobAlerts

   The last two entries (`cac938e`, `b991743`) predate this LiteLLM v1.99.0
   work — they're pre-existing commits this branch inherited from `dev` that
   haven't been promoted to `main` yet, unrelated to this review. The review
   and remediation work itself is the nine commits from `b7995cd` through
   `9e87a96`.

   Note: `ChatGptForEmployees/config/litellm_routing_config.local.yaml` is
   edited on this developer's machine as part of this work but is
   **untracked** (its own file header says "DO NOT COMMIT, DO NOT DEPLOY") —
   it is not one of the committed artifacts above and is not a deployed
   control; the edit exists only on this checkout.

   Of the commits listed above, the nine review-work commits (`b7995cd`
   through `9e87a96`) are **local to this checkout only** — `origin/fix/litellm-cve-upgrade-v1.99.0-dev`
   is still at `525f8cd`, so none of this review's work has been pushed.
   Pushing the branch or opening a PR is a separate, not-yet-authorized next
   step.
7. **Scheduling** — confirmed Tue/Fri 05:00 UTC for Okta sync (the nightly
   change never merged) and nightly 02:00 UTC for cleanup. Corrected: the
   procedure previously used `az containerapp job execution list` alone to
   both capture the configured schedule and confirm a pause — that command
   only reports execution history/state, not the job's configured trigger.
   Capturing/confirming the actual schedule now uses `az containerapp job
   show` (separately from `execution list`, which still checks
   currently-running executions). Pause/resume itself is still written up as
   owner-executed and **unverified** — Azure CLI access isn't available in
   this preparation environment — but is no longer left as an abstract
   description: `REVIEW-AND-CUTOVER.md` §7 now names a concrete candidate
   (`az containerapp job update --cron-expression "0 0 31 2 *"`, a
   never-fire February 31st sentinel), explicitly flagged as untested against
   a real job and requiring confirmation before the maintenance window.

**What's still outstanding and owner-led, not done here:**

- Running any of this against the actual dev database.
- The full backup/PITR recovery rehearsal (sequences, owners, ACLs) — the
  local rehearsal covered schema/data mechanics only.
- Azure-side job pause/resume execution.
- The post-migration prompt/response verification query against real dev
  data.

No dev migration has been executed as part of preparing any of this.
