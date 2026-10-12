# PBI-04: remaining live retrieval and comparison work

Prepared 2026-10-06 against commit `7e841d0`. Continue the existing implementation;
do not rebuild the CSV importer. This supplements the
[closure guide](PBI-04-BE-closure-guide.md).

## Current state and execution prerequisite

The three full-day October 1 exports have been imported and characterized.
`scripts/reconcile_contact_history.py` accepts only `--import-only` or
`--api-fixture`; it has no live fetch mode. No contact-detail endpoint is
verified in the current branch. `CXONE_VAULT_URI` is absent in the current shell.
No live request or report/API reconciliation was performed while writing this
guide. Only the example mapping configuration is present.

Use the existing deployed environment with its managed identity and Key Vault
access, or an explicitly configured development credential provider. Setting a
vault URI alone does not grant access: the existing production provider uses
managed identity. Do not expect a workstation Azure login automatically to
satisfy that provider, hard-code secrets, or ask for secrets in chat. Preserve
the deployed authentication path and verify dependencies in the selected Python
environment. The task needs read-only CXOne reporting access, not write access.

## 1. Establish the actual endpoint contract

Inspect tenant discovery evidence and official CXOne documentation for a
historical contact-detail API and a skill inventory API. Verify access using
the existing `CXoneClient`; do not guess endpoint paths from report titles.
Record endpoint path, API version, permissions, request parameters, response
array and field paths, pagination protocol and retention behavior.

In particular establish whether date filtering selects contacts by start time,
completion time or another lifecycle event. If the API filters by completion
but the report selects by start, fetching the same nominal dates is not a
complete comparable population. Use a documented retrieval strategy or return
`UNRESOLVED` rather than claim complete coverage.

Fetch the authoritative skill inventory and map all 29 report skill names to
IDs, including the 21 missing from Skills.csv. Retain inventory capture time and
config/version evidence. Handle inactive/renamed skills explicitly; a current
inventory is not automatically evidence of October 1 names. Keep report scope
separate from the final production CS allowlist.

Use Ziven's UTC-report statement as evidence to investigate these exports;
confirm whether their selected full day is a UTC or Eastern calendar day.
For a confirmed UTC calendar day the window is
`[2026-10-01T00:00:00Z, 2026-10-02T00:00:00Z)`. Otherwise convert the confirmed
local-day boundaries. Until established, permit only labelled exploratory runs.

## 2. Add the real source without changing the importer

Add `src/romtech_mcp/mapping/contact_history_source.py`. Reuse
`cxone.bootstrap.build_cxone_config`, `build_credential_provider` and
`CXoneClient`; use their existing retry/authentication/deadline policies and
close async resources on all exits. Do not add a second retry loop.

Suggested interface (design sketch, not an already available API):

```python
class ContactHistorySource:
    async def fetch_contacts(self, window, scope) -> ApiContactFetch: ...
    async def fetch_skill_inventory(self): ...
```

Load verified endpoint/field contracts from configuration. Validate configuration
types and required fields before fetching. Consume every page; detect repeated
continuation tokens and enforce a bounded page/request limit. On an outage,
deadline, malformed page or incomplete pagination, produce an explicit failure
or incomplete result; never present the accumulated subset as complete.

Never follow an arbitrary continuation URL with credentials. Validate its host
and path against the verified API contract and use the existing client's safe
request mechanism. Do not log tokens, headers, raw responses or customer data.

Normalize only fields needed for comparison: contact ID, skill ID and UTC start
time, plus additional identity/grain fields only where verified. Keep identifiers
as strings; reject null identifiers, invalid timestamps and conflicting repeated
API records. Read sensitive response fields only as necessary and do not persist
raw bodies by default.

Extend `ApiContactFetch` with explicit provenance: requested UTC bounds, filter
scope, verified grain, capture time, completeness/page evidence, source contract
version and validation issues. Derive complete coverage from the fetch execution,
not a caller-supplied `coverage='complete'` label alone. If history is expired or
the endpoint is unavailable, report that without interpreting zero rows as proof
of zero contacts.

## 3. Tighten comparison preconditions before relying on MATCH

The current code is useful scaffolding, but the following checks must be added
before it becomes acceptance evidence:

- `compare_contacts` only checks that `grain` is non-null. Restrict it to
  implemented, verified grains. The current dictionary key is contact ID; it
  cannot truthfully compare master interactions or routed-leg identities simply
  because a caller supplies those words.
- Both sides use `setdefault(contact_id, record)`. Detect conflicts instead of
  silently choosing the first record. An explanation string is not a merge
  policy. Implement a narrow documented rule where justified, such as ignoring
  Team-only differences for a comparison explicitly excluding team attribution;
  differing skill/start values must remain unresolved unless separately resolved.
- Investigate the trailing `*` marker. Preserve raw and canonical identities;
  implement only the verified transformation. `--id-marker-rule` currently turns
  arbitrary nonempty text into a boolean permission to continue: replace this
  with a supported rule identifier plus evidence, including collision checks.
  **Done 2026-10-12** (`child-leg-master-contact`, `repeat-differs-in-team-or-agent-only`; see
  `evidence/pbi-04/ziven-response-2026-10-08.md`). The `--id-marker-rule`/`--repeat-rule` flags are choices, not text.
- Validate source window/filter/grain provenance on both sides. Out-of-window
  export rows or an unexplained population mismatch must not quietly disappear
  through filtering and yield a full-day `MATCH`. Intentional subset comparisons
  must be explicitly labelled and cannot count as full-day validation.
- Validate timezone-aware bounds, finite nonnegative timestamp tolerance, strict
  booleans and typed IDs. `_load_api_fixture` currently uses `bool(raw['captured'])`,
  which treats the string `"false"` as true; require an actual JSON boolean.
- Distinguish data agreement from acceptance. Synthetic fixtures may produce a
  test match but never real-day evidence. Neither `captured: true` nor arbitrary
  evidence text proves provenance. Require an actual capture manifest and source
  verification for acceptance-grade output.
- Keep duration/SLA/abandonment/ASA/AHT outside this contact comparison until
  their required field semantics and reference evidence exist. A contact match
  must not promote unrelated metrics to `VALIDATED`.

Do not resolve conflicts by taking whichever row matches the API. Establish
the rule independently and record residual differences.

## 4. Extend the CLI

Add mutually exclusive `--live`, `--api-fixture` and `--import-only` modes to
`scripts/reconcile_contact_history.py`. Reject invalid combinations. Add a
verified source configuration argument and inventory-fetch option; preserve
offline operation for tests and genuinely captured responses.

Keep three statuses separate in the output:

1. Execution status: import/fetch completed or failed.
2. Comparison status: MATCH, MISMATCH or UNRESOLVED, with reasons/counts.
3. Acceptance status: actual-day evidence and PBI-owner decision, never implied
   solely by a successful command or comparison match.

Write sanitized manifests and summaries: input hashes, revision/dirty state,
source endpoint/version, selected window, inventory/config fingerprints,
capture timestamps, page/row counts, scope, rules and comparison totals. Avoid
per-contact IDs, telephone numbers, agent names and raw records in committed
artifacts. PBI-04's offline CLI may write evidence; do not add disk writes to
the PBI-06 MCP server.

Exit nonzero for failed execution, required unresolved comparisons and mismatches.
Import-only success must continue to say that no API comparison was performed.
Do not add a flag that forces a MATCH or changes production confirmation flags.

## 5. Required tests and actual run

Add synthetic source/CLI tests for full pagination, repeated cursor, later-page
failure, schema errors, missing/null IDs, conflicting API duplicates, date-filter
semantics and secret-safe diagnostics. Add comparison regression tests for
unsupported grain, Team-only versus substantive conflicts, marker collisions,
out-of-window records, mismatched capture scope/window, false-string booleans,
naive timestamps and nonfinite tolerances. Confirm synthetic matches cannot be
reported as actual-day validation.

Run existing mapping and relevant CXone tests with project dependencies present:

```powershell
$env:PYTHONPATH = 'src'
python -m pytest tests/mapping tests/cxone -q
```

Then run the completed live CLI in the authorized execution environment against
the October 1 files. Use the full-day confirmation already supplied; do not ask
for another report merely because the files contain duplicates. Use established
scope/timezone/rules and retain evidence of actual retrieval. Inspect every
export-only/API-only record class, skill mismatch and timestamp mismatch; either
resolve it or leave it explicitly outstanding. Do not mark this step done based
on synthetic tests.

## 6. Final deliverable and closure decision

Update `docs/PBI-04-BE-mapping.md` and
`docs/evidence/pbi-04/closure-2026-10-03.md` with the real run, validated measures,
remaining differences and supporting sanitized artifacts. Preserve the previous
import-only history rather than rewriting it as a completed comparison.

Prepare the PBI owner's concrete reduced-scope acceptance decision only after
the supported comparison work is complete. Assign real follow-up references and
owners for unverified metrics and original criteria. Record approval only when
it is actually given. If endpoint access, retained data or equivalent semantics
cannot be established, state the blocker and keep reconciliation unresolved;
the original acceptance criteria have not passed.
