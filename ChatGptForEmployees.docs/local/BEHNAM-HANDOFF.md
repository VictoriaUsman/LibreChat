# LiteLLM v1.99.0 review — response

Indexed to your seven notes. Full detail in `REVIEW-AND-CUTOVER.md` in this
same folder. Nothing in this response required touching dev, deploying, or
messaging anyone else — it's being sent to you directly, now, as the
authorized handoff.

1. **Prompt/response storage** — traced to source in the pinned image
   (digest `sha256:570a872d...`). Controlling setting:
   `general_settings.store_prompts_in_spend_logs`, default off (writes an
   empty JSON object `{}`, not NULL). Verified in source that an explicit YAML
   value always wins over a DB-cached value on reload, so no tracked config
   change is needed — the safe default already holds and is reload-safe if we
   ever do set it. `turn_off_message_logging` is confirmed separate. Beyond
   source tracing, an actual synthetic runtime test was executed against the
   pinned image (`REVIEW-AND-CUTOVER.md` §1a) — non-streaming, streaming, and
   failed-model request paths all showed the empty `{}` in both `messages` and
   `response`. That's distinct from your dev verification query, which is
   still pending your migration and real traffic.
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
   config, so nothing overrides it.
4. **Rollback scope/timing** — two named paths (recover onto the original
   server vs. redirect to a PITR-restored server), with `postgresql.bicep`'s
   actual consumers mapped (`liteLlm`, both jobs, `ragApi`). Timeline numbers
   are explicitly labeled planning estimates, not measured.
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
   change never merged) and nightly 02:00 UTC for cleanup. Pause/resume
   procedure is written up as owner-executed since Azure CLI access isn't
   available in this preparation environment.

**What's still outstanding and owner-led, not done here:**

- Running any of this against the actual dev database.
- The full backup/PITR recovery rehearsal (sequences, owners, ACLs) — the
  local rehearsal covered schema/data mechanics only.
- Azure-side job pause/resume execution.
- The post-migration prompt/response verification query against real dev
  data.

No dev migration has been executed as part of preparing any of this.
