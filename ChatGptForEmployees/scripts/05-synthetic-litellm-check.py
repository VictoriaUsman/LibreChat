#!/usr/bin/env python3
"""
Synthetic, internal-only LiteLLM check for the LiteLLM v1.99.0 dev cutover
(REVIEW-AND-CUTOVER.md §2a Step 8d; second working-changes follow-up review,
Finding 2: "make the internal synthetic test executable"). Runs as the
manually-triggered ACA Job job-cgfe-synth-check-<env> (jobs.bicep), which
gives this script a prepared, always-available execution location that can
resolve LiteLLM's internal FQDN (ca-litellm-<env>, ingress external: false) --
the same way any other app inside this Container Apps environment reaches it.

WHAT THIS DOES, in order, each step bounded and each failure explicit:
  1. GET  {LITELLM_INTERNAL_URL}/health/liveliness   -- must be 200.
  2. GET  {LITELLM_INTERNAL_URL}/health/readiness    -- must be 200.
  3. POST {LITELLM_INTERNAL_URL}/v1/chat/completions -- one non-streaming
     request, model=SYNTHETIC_TEST_MODEL, a fixed non-sensitive marker string
     as content, `user` set to a freshly-generated unique marker so the
     resulting LiteLLM_SpendLogs row can be identified unambiguously (per §1's
     "identify the synthetic requests' own rows" requirement -- the latest-N-
     rows query alone is not sufficient).
  4. Poll public."LiteLLM_SpendLogs" for a row matching that unique `end_user`
     value, bounded by SYNTH_CHECK_MAX_WAIT_SECONDS (the async spend-log
     writer is not synchronous with the HTTP response -- §1a/§1b/§1c's local
     harnesses observed it land within the first ~5s poll interval; this
     script polls longer to be safe against real dev-host latency).
  5. Verify `messages` and `response` on that row match the documented
     empty-storage representation, exactly `{}` (§1) -- NOT that they are
     merely non-null, and NOT SQL NULL, an omitted field, or the two-
     character string "{}" misread as populated content.

WHAT THIS PRINTS: row counts, boolean match/mismatch status, and the
generated marker itself (which is not employee content) -- NEVER the actual
`messages`/`response` column values. If content is ever found populated, this
script prints ONLY that fact (never the content) and exits non-zero; per §1,
that requires stopping promotion and escalating to Behnam, not further ad hoc
inspection of the row by this script or its operator.

EXIT CODES (every one of these is a stop condition per §2a Step 8d -- a
nonzero exit here means do not proceed to 8e):
  0  all checks passed: healthy, completion succeeded, spend-log row found
     within the bound, both fields read exactly "{}".
  1  a health check failed or did not return 200.
  2  the synthetic completion request failed, timed out, or returned a
     non-2xx status.
  3  no matching LiteLLM_SpendLogs row appeared within
     SYNTH_CHECK_MAX_WAIT_SECONDS (an unresolved test result, per Finding 2 --
     NOT evidence that storage is disabled).
  4  a matching row was found but `messages` and/or `response` were NOT the
     expected empty representation -- i.e. content was unexpectedly stored.
     STOP PROMOTION IMMEDIATELY and escalate to Behnam per §1; do not treat
     this as a script bug to retry past.
  5  a required environment variable is missing, or the database query itself
     failed (connectivity/auth) -- distinguished from case 3 (query succeeded,
     zero matching rows) so an operator doesn't confuse "couldn't check" with
     "checked and it's empty".

Required environment variables (set as ACA Job secrets/env in jobs.bicep):
  LITELLM_INTERNAL_URL   e.g. http://ca-litellm-dev.<region>.azurecontainerapps.io
                          (liteLlm.bicep's own `fqdn` output, passed through
                          jobs.bicep -- internal-only; this job runs inside the
                          same Container Apps environment).
  LITELLM_MASTER_KEY     the same secret liteLlm.bicep itself uses.
  DATABASE_URL           litellm Postgres connection string (already set).

Optional:
  SYNTHETIC_TEST_MODEL       model_name from litellm_routing_config.yaml to
                              call. Default "ROMTech AI Fast" (the lighter of
                              the two user-facing models).
  SYNTH_CHECK_CONNECT_TIMEOUT_SECONDS   default 10.
  SYNTH_CHECK_READ_TIMEOUT_SECONDS      default 30 (chat completions can be
                                         slower than a health check).
  SYNTH_CHECK_MAX_WAIT_SECONDS          default 30 -- total bound for polling
                                         the spend-log row.
  SYNTH_CHECK_POLL_INTERVAL_SECONDS     default 2.

Usage (local rehearsal, e.g. against the §1a/§1b/§1c-style Docker harness):
  pip install -r requirements.txt
  LITELLM_INTERNAL_URL=http://localhost:4000 \\
  LITELLM_MASTER_KEY=sk-... \\
  DATABASE_URL=postgresql://postgres:postgres@localhost:5432/synth_test \\
  python 05-synthetic-litellm-check.py

Owner-run invocation against the real dev environment (Step 8d; corrected
per the LiteLLM v1.99.0 review, third working-changes follow-up, Finding 1 --
`az containerapp job execution list ... | [0]` does NOT reliably identify
the execution just started, and `properties.template.containers[0].exitCode`
is not a documented field of the jobs-executions API):
  az containerapp job start -n job-cgfe-synth-check-dev -g rg-dev-shared \
    --output json
  # Capture the execution name/id from THAT response. Poll only that exact
  # execution (by name, requiring exactly one match) until its
  # `properties.status` reaches a terminal state (Succeeded/Failed), bounded
  # by a deadline -- never assume history[0] is the run just started. Then
  # pull logs scoped to that same execution and require this script's own
  # "PASS:" line for the matching run; do not accept an older execution's
  # logs, an unscoped tail, or a still-running execution as evidence. See
  # REVIEW-AND-CUTOVER.md Step 8d for the exact, current commands -- this
  # script's own nonzero exit remains the stop signal either way.

This script never sends, logs, or prints employee conversation content. Its
own synthetic request content is a single fixed, clearly-marked, non-
sensitive string -- never real conversation data.
"""

import os
import sys
import time
import uuid

import psycopg2
import requests

SYNTHETIC_MARKER_TEXT = "ROMCHAT-SYNTHETIC-CUTOVER-CHECK-2026"


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"FAIL: required environment variable {name} is not set", file=sys.stderr)
        sys.exit(5)
    return value


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"FAIL: {name}={raw!r} is not a valid integer", file=sys.stderr)
        sys.exit(5)


def check_health(base_url: str, path: str, connect_timeout: int, read_timeout: int) -> None:
    url = f"{base_url}{path}"
    try:
        resp = requests.get(url, timeout=(connect_timeout, read_timeout))
    except requests.RequestException as exc:
        print(f"FAIL: {path} request error: {exc}", file=sys.stderr)
        sys.exit(1)
    if resp.status_code != 200:
        print(f"FAIL: {path} returned HTTP {resp.status_code}, expected 200", file=sys.stderr)
        sys.exit(1)
    print(f"OK: {path} -> 200")


def send_synthetic_completion(
    base_url: str,
    master_key: str,
    model: str,
    marker: str,
    connect_timeout: int,
    read_timeout: int,
) -> None:
    url = f"{base_url}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": f"{SYNTHETIC_MARKER_TEXT}-{marker}"}
        ],
        "user": marker,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {master_key}"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=(connect_timeout, read_timeout))
    except requests.RequestException as exc:
        print(f"FAIL: synthetic completion request error: {exc}", file=sys.stderr)
        sys.exit(2)
    if resp.status_code // 100 != 2:
        hint = (
            "confirm LITELLM_MASTER_KEY is correct"
            if resp.status_code in (401, 403)
            else f"confirm model_name={model!r} exists in litellm_routing_config.yaml"
        )
        print(
            f"FAIL: synthetic completion returned HTTP {resp.status_code} ({hint})",
            file=sys.stderr,
        )
        sys.exit(2)
    print(f"OK: synthetic completion -> HTTP {resp.status_code}")


def poll_spend_log_row(
    database_url: str,
    marker: str,
    max_wait_seconds: int,
    poll_interval_seconds: int,
):
    """Returns (messages_text, response_text) for the matching row, or None if
    no row appeared within max_wait_seconds. Raises SystemExit(5) on a
    connection/query failure, distinct from "queried fine, found nothing"."""
    deadline = time.monotonic() + max_wait_seconds
    attempt = 0
    while True:
        attempt += 1
        try:
            conn = psycopg2.connect(database_url, connect_timeout=10)
        except psycopg2.Error as exc:
            print(f"FAIL: could not connect to the database: {exc}", file=sys.stderr)
            sys.exit(5)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT messages, response FROM public."LiteLLM_SpendLogs" '
                    'WHERE end_user = %s ORDER BY "startTime" DESC LIMIT 1;',
                    (marker,),
                )
                row = cur.fetchone()
        except psycopg2.Error as exc:
            print(f"FAIL: query against LiteLLM_SpendLogs failed: {exc}", file=sys.stderr)
            sys.exit(5)
        finally:
            conn.close()

        if row is not None:
            print(f"OK: matching LiteLLM_SpendLogs row found after {attempt} poll(s)")
            return row

        if time.monotonic() >= deadline:
            return None
        time.sleep(poll_interval_seconds)


def main() -> None:
    base_url = _required_env("LITELLM_INTERNAL_URL").rstrip("/")
    master_key = _required_env("LITELLM_MASTER_KEY")
    database_url = _required_env("DATABASE_URL")
    model = os.environ.get("SYNTHETIC_TEST_MODEL", "ROMTech AI Fast").strip()

    connect_timeout = _int_env("SYNTH_CHECK_CONNECT_TIMEOUT_SECONDS", 10)
    read_timeout = _int_env("SYNTH_CHECK_READ_TIMEOUT_SECONDS", 30)
    max_wait_seconds = _int_env("SYNTH_CHECK_MAX_WAIT_SECONDS", 30)
    poll_interval_seconds = _int_env("SYNTH_CHECK_POLL_INTERVAL_SECONDS", 2)

    marker = f"synth-check-{uuid.uuid4().hex[:16]}"
    print(f"Starting synthetic LiteLLM check against {base_url} (marker={marker}, model={model!r})")

    check_health(base_url, "/health/liveliness", connect_timeout, read_timeout)
    check_health(base_url, "/health/readiness", connect_timeout, read_timeout)
    send_synthetic_completion(base_url, master_key, model, marker, connect_timeout, read_timeout)

    row = poll_spend_log_row(database_url, marker, max_wait_seconds, poll_interval_seconds)
    if row is None:
        print(
            f"FAIL: no LiteLLM_SpendLogs row matched end_user={marker!r} within "
            f"{max_wait_seconds}s -- unresolved test result, not evidence that "
            "storage is disabled. Do not proceed to release.",
            file=sys.stderr,
        )
        sys.exit(3)

    messages_value, response_value = row
    # psycopg2 auto-adapts a jsonb column to a native Python object (dict/list/
    # etc.), NOT the raw "{}" text -- confirmed by actually running this
    # script against a live Postgres row during validation, which caught this
    # exact mistake: comparing against the string "{}" is always False for a
    # jsonb column, regardless of its actual content, and would have raised a
    # false "content is populated" alarm on every run. The correct comparison
    # is against the empty dict {} (or, defensively, the literal two-character
    # string, in case some future driver/column-type combination ever returns
    # raw text instead).
    messages_ok = messages_value == {} or messages_value == "{}"
    response_ok = response_value == {} or response_value == "{}"
    print(f"messages field matches expected empty representation: {messages_ok}")
    print(f"response field matches expected empty representation: {response_ok}")

    if not (messages_ok and response_ok):
        print(
            "FAIL: prompt/response content is NOT empty for this synthetic row. "
            "Per REVIEW-AND-CUTOVER.md §1: stop promotion immediately, confirm "
            "store_prompts_in_spend_logs is explicitly false in the deployed "
            "config, and escalate to Behnam before any further action. This "
            "script deliberately does not print the actual field contents.",
            file=sys.stderr,
        )
        sys.exit(4)

    print("PASS: all synthetic LiteLLM checks succeeded; both fields read '{}' as expected.")
    sys.exit(0)


if __name__ == "__main__":
    main()
