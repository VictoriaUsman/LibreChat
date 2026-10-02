# PBI-04-BE: reconciliation and closure instructions

Prepared 2026-10-03. This guide defines the remaining work; it does not record
completed reconciliation or approval to reduce the original acceptance scope.

## Closure basis

Use the three Contact History exports supplied by the user as the available
historical reference. The user has confirmed that together they represent the
full day and are all the reporting available. Record that confirmation; do not
keep requesting another report as a prerequisite for starting this work.

Complete the comparisons these files support. Record unsupported comparisons
as **not validated by the available evidence**, then prepare a reduced-scope
acceptance decision for the PBI owner. Close the original PBI as fully validated
only if its original criteria are actually met. Otherwise closure requires an
explicit scope change with accepted limitations and tracked follow-up work.
The user's request for closure instructions is not that acceptance decision.

Related documents: [mapping/evidence register](PBI-04-BE-mapping.md),
[original implementation guide](PBI-04-BE-implementation.md).

## 1. Record and inspect the reference files

Inputs, outside the repository:

```text
C:\Data Engineering\LibreChat\ContactHistory (20).csv
C:\Data Engineering\LibreChat\ContactHistory (21).csv
C:\Data Engineering\LibreChat\ContactHistory (22).csv
C:\Data Engineering\LibreChat\Skills.csv
```

Earlier inspection found these reference facts; recompute them in the importer:

| Input | Rows | Distinct contact IDs within file |
|---|---:|---:|
| ContactHistory (20).csv | 1,000 | 996 |
| ContactHistory (21).csv | 1,000 | 999 |
| ContactHistory (22).csv | 30 | 30 |
| Combined | 2,030 | 2,021 |

Combined distinct master contact IDs: 1,661. Files 20 and 21 share four contact
IDs. These counts describe the export; none is automatically the dashboard's
"contacts offered" or "contacts handled" metric.

Displayed start dates are October 1, 2026, with observed times 01:35:48 through
23:46:14. Those are the earliest/latest records, not the report query boundaries.
The user confirmed full-day coverage; retain the full-day window even where
there are no rows near midnight. The 1,000/1,000/30 split alone does not prove
pagination completeness, but is consistent with the supplied multi-file export.

Columns include contact/master IDs, media type, skill name, agent, team,
telephone fields, start time, duration, logging/dispositions and an empty final
column. No skill IDs, UTC offsets or explicit queue/handle/SLA components exist.

Write a manifest with input basenames, SHA-256 hashes, row counts, duplicate
counts, recording date, source-confirmation note, code revision/dirty state,
configuration fingerprint and comparison status. Do not invent the report
generation time, filter settings or Ziven's email date.

The exports contain phone numbers and agent names. Read the originals in place;
do not copy them into Git, log raw rows or include telephone fields in evidence.
Committed evidence should contain aggregate counts and sanitized configuration.
Detailed mismatch artifacts, if needed locally, must be access-controlled and
excluded from Git. Do not treat ordinary unsalted hashes of phone numbers as
anonymization. The offline reconciliation CLI may write evidence; the PBI-06
runtime server's no-disk requirement remains separate and unchanged.

## 2. Establish one comparison window and scope

Ziven stated Eastern business time and UTC report output. Record that as the
provided evidence, but explicitly establish that these particular exports use
UTC before an acceptance-grade comparison. For exploratory analysis, label UTC
as an assumption rather than silently marking the timezone confirmed.

If the export is the UTC calendar day October 1, fetch exactly
`[2026-10-01T00:00:00Z, 2026-10-02T00:00:00Z)`. That is not the same window as
October 1 in Eastern business time. If selection used an Eastern calendar day
but display is UTC, derive the corresponding UTC boundaries from the agreed
IANA timezone. Do not shift timestamps merely to make totals match.

Record the report's media/direction/team/skill filters when available. All
observed rows are Phone, but this alone does not prove the report was filtered
to Phone. Do not infer inbound/outbound solely from skill names.

Fetch or load a dated authoritative skill inventory and join report skill names
to IDs. The supplied Skills.csv lacks many observed CS skill names. Resolve
these using verified inventory; never invent IDs or fuzzy-match them silently.
Keep raw names for provenance; any whitespace/case normalization must detect
collisions. Unmatched, renamed, deleted or duplicate-name skills are explicit
unresolved records. Historical ID/name changes require evidence.

The observed full-day skill set is suitable for reconciling that report, but
does not automatically define the production CS allowlist. Keep these scopes
separate. Report team names do not prove historical membership rules; confirm
those rules or defer team-filter validation explicitly.

## 3. Implement a Contact History reconciliation path

Extend the mapping package rather than the MCP runtime. Suggested files:

| File | Responsibility |
|---|---|
| `mapping/contact_history.py` | CSV parsing, normalized records, duplicate classification and report counts |
| `mapping/contact_history_source.py` | Verified contact-detail API adapter, only if a suitable endpoint is available |
| `mapping/contact_history_reconcile.py` | Align scope/window, compare identities/fields/counts, produce typed outcomes |
| `scripts/reconcile_contact_history.py` | Offline/API modes, explicit assumptions, sanitized evidence output and exit codes |
| `tests/mapping/test_contact_history*.py` | Synthetic unit and integration fixtures for this contract |

These are proposed modules, not existing commands. Reuse PBI-02's CXone client,
credential provider, deadlines and retries. Reuse existing mapping outcome and
coverage types. Keep `scripts/reconcile_dashboard.py` working for its existing
metric-summary use case; do not force contact-detail rows into its skill-summary
schema or relabel contact-row counts as dashboard totals.

### Importer

Use `csv.DictReader` with `utf-8-sig` and `newline=''`. Support quoted commas,
BOM, empty optional cells and the known empty trailing column. Reject missing
required headers, malformed nonempty fields and unexpected row shapes with
sanitized file/line diagnostics. Keep contact/master IDs as strings.

Parse the displayed US date format explicitly; do not use locale-dependent
day/month guessing. Apply the declared source timezone; reject or flag ambiguous
local timestamps instead of inventing a DST fold. Retain provenance as source
file plus row number. Retain duration text until its units/format and meaning
are established. Never interpret it as handle time by default.

Classify repeated IDs separately from exact duplicate records. Report:

- Raw rows and exact repeated rows, within and across files.
- Unique contact IDs and unique master IDs.
- Repeated contact IDs with differing skills, timestamps or other relevant fields.
- Per-skill contact membership and master/contact relationships.

Do not blindly `drop_duplicates(Contact ID)` or count master IDs as calls.
Establish the report/API grain first: contact, routed leg, transfer or master
interaction. Exact duplicate removal is permitted only under a documented
export-overlap rule, retaining its audit count. Conflicting repeated IDs remain
unresolved until explained. Per-skill distinct counts may not sum to a global
distinct count when the same contact appears under several skills.

### API comparison

Verify the actual contact-detail endpoint/version, date-filter semantics,
pagination, fields and retained history using available discovery evidence and
authoritative documentation during implementation. Do not guess a URL. Fetch
all pages and validate coverage before comparison; enforce client-side scope
where server filters are not verified. Fail explicitly on partial fetch/outage.

If a suitable detail endpoint is available, compare the report and API using
the verified identity/grain. Show matched records, export-only/API-only records,
field mismatches, and per-skill counts. Compare timestamps and duration only
when their semantics and precision are aligned. Exact counts use zero tolerance;
any timestamp/duration tolerance must be justified before looking at mismatches.

If only a skill-summary endpoint is available, compare counts only after
establishing an equivalent definition and filters. Do not compare 2,021 unique
contact IDs to `contactsOffered` merely because both sound like volume. If no
equivalent measure is established, output `UNRESOLVED`; importer output and a
successful API request are not reconciliation evidence.

Separate synthetic API fixtures from real captured responses in manifests.
Mocks validate the code, not the actual day. If the API no longer retains that
day, record unavailable evidence; do not interpret an empty/all-zero response
as a successful comparison or change the date on the reference export.

### CLI contract

Accept repeated `--report` paths, a source timezone and exact window,
skill-mapping/config path, either `--live` or a captured `--api-fixture`, an
`--output-dir`, and an explicit exploratory mode. Write a run manifest and
comparison summary. Return nonzero for failed fetches, mismatches and required
unresolved comparisons; a waived/deferred comparison remains visible and is
never transformed into `MATCH` by a flag.

Acceptance status must be derived from evidence separately from CLI success.
Never flip production scope/timezone/metric confirmation flags based merely on
an exploratory run. Do not bypass `assert_ready_for_acceptance` on the existing
dashboard path to accommodate this new, narrower report comparison.

## 4. State what the reports cannot validate

| Area | What this evidence can establish |
|---|---|
| Contact records and skill attribution | Comparable if API identity, time window and skill mapping are verified |
| Contact volume | Comparable only for an explicitly equivalent counting definition |
| Duration | Comparable only if report/API units and lifecycle definitions are verified |
| Service level, abandonment rate, ASA, AHT | Not validated by these columns alone; queue/answer/abandon/handle components are missing |
| Live queue depth and staffing | Not validated by historical Contact History exports |
| Eight-week baseline and holiday behavior | Eight-week preference is recorded; one day cannot validate historical baseline samples or holiday policy |

Missing reference evidence is not proof that the API capability is unsupported.
Preserve candidate/unconfirmed metric status as appropriate and record the
separate reconciliation limitation. Do not set `MappingStatus.UNSUPPORTED`
solely because a CSV omits a field, and do not set `VALIDATED` without evidence.

Retain per-skill SLA thresholds/goals and short-abandon settings from Skills.csv.
Their presence does not validate API SLA formulas or their historical effective
dates. Also retain unresolved production CS scope, team semantics, inventory
83/85 discrepancy and dashboard metric inventory in the decision register; do
not let a contact-count match implicitly close those original criteria.

## 5. Tests and evidence

Use synthetic fixtures rather than customer phone/agent data in committed tests.
Cover multiple files; exact duplicates and conflicting repeated IDs; master
contacts spanning skills; duplicate/unmatched skill names; missing headers;
malformed rows; empty results; boundary timestamps; UTC versus Eastern day
selection; unknown duration semantics; pagination completeness; outage handling;
and mismatched/unknown metric definitions. Verify no raw personal fields appear
in logs or committed evidence. Test that unresolved evidence cannot produce a
successful acceptance outcome.

Run the mapping tests plus relevant CXone client tests after implementation.
Then execute the actual report/API reconciliation and record its command,
environment, input hashes, outcomes and unresolved differences. A documentation
change or passing synthetic suite does not replace this real comparison.

Update `docs/PBI-04-BE-mapping.md` with the input confirmation, actual mappings,
comparison results and limitations. Add a dated closure-evidence artifact under
`docs/evidence/pbi-04/` containing only sanitized evidence. Do not overwrite the
original acceptance checklist with a narrower one without preserving the scope
change and its approval.

## 6. Closure decision to prepare for the PBI owner

Prepare a concrete acceptance table for every original PBI-04 criterion:
`met`, `not met`, or `proposed deferral`, with evidence or follow-up reference.
Include all outstanding scope, timezone, SLA, baseline, metric-inventory and
reconciliation items; the missing report fields are not the only possible gap.

Closure under reduced scope requires all of the following:

1. The supported report/API comparisons have actually run; their definitions,
   scope and time window are established, and differences are resolved or
   explicitly accepted with an explanation.
2. Every unvalidated requirement has a named follow-up owner, acceptance criteria
   and a tracked item/reference. Do not fabricate ticket IDs or approval dates.
3. The PBI owner explicitly accepts the revised scope and residual limitations;
   record who accepted it, when, and the decision reference. Until then retain
   "ready for reduced-scope review", not "closed" or "fully validated".
4. Production configuration flags and documentation accurately reflect what was
   proven. A management waiver does not turn a metric into a technically
   validated mapping or authorize bypassing runtime configuration checks.

Suggested closure statement, to fill only after execution and approval:

> PBI-04 closed under the revised scope accepted by [owner/date/reference].
> October 1 Contact History exports were reconciled against [endpoint/version]
> for [exact window and scope]. [List the measures validated and evidence link.]
> [List unresolved original criteria] remain unvalidated and are tracked in
> [follow-up references]. This closure does not certify all dashboard metrics,
> SLA calculations, live state or historical baseline behavior.

If no comparable API measure can be established, report that honestly and
prepare a different explicit scope decision; do not call the files reconciled.
