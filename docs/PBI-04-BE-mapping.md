# PBI-04-BE: dashboard mapping and acceptance evidence

Status: **partially confirmed; not fully validated**. Prepared 2026-09-25; updated
2026-10-01 with Ziven's reply and Skills.csv. Some business settings are now
confirmed; final scope and paired report/API measurements remain outstanding.
No blank row is acceptance evidence.

**2026-10-06 live comparison update:** real `/contacts` API retrieval now works
through the existing discovery setup. The Eastern full-day interpretation of
October 1 matches all 2,021 distinct exported contact IDs, all 29 per-skill
counts, skill names and displayed-second start times. Two team differences and
the marker/timezone/duplicate acceptance rules remain unresolved; other business
metrics are not validated. See [live comparison evidence](evidence/pbi-04/live-comparison-2026-10-06.md).
Earlier statements below that no API comparison was run describe the October 3
snapshot and are superseded by this evidence, not by a full PBI sign-off.

Implementation instructions: [PBI-04-BE-implementation.md](PBI-04-BE-implementation.md).

**2026-10-03 reference update:** the user supplied ContactHistory (20), (21)
and (22).csv and confirmed that together they are the full day's available
reporting. See the [reconciliation and closure guide](PBI-04-BE-closure-guide.md)
for code instructions, supported comparisons and the proposed reduced-scope
acceptance process. No API comparison or scope-change approval is recorded yet.

**2026-09-25 code status (historical snapshot):** the harness described in the implementation
guide now exists — `src/romtech_mcp/mapping/` (models, config loader,
`ReportingSource` adapter around PBI-02's `CXoneClient`, client-side
scope selection, timezone-aware windows, formula derivation and
comparison), `scripts/reconcile_dashboard.py`, and
`config/cxone-dashboard-mapping.example.json`. 175 tests pass
(`python -m pytest tests/mapping tests/cxone tests/infra -q`), all against
synthetic fixtures — no dashboard, credential, or live-tenant access was
used. This proves the harness computes what it claims to given fabricated
inputs; it proves nothing about this PBI's actual acceptance criteria,
every row of which is still genuinely pending real configuration and
observations below.

## Configuration decisions

| Decision | Confirmed value | Source / effective date | Confirmer / confirmation date |
|---|---|---|---|
| Dashboard/report/widgets/version | Dashboard is live-only; historical comparison requires a report. Exact widgets/report/version pending | Ziven reply, recorded 2026-10-01 | Ziven; email date not supplied |
| Included skill IDs and names | 16 ID/name pairs supplied; CS grouping and final inclusion pending | Skills.csv; see evidence below | Ziven; export/email dates not supplied |
| Excluded skill IDs and reasons | Pending | Pending | Ziven: pending |
| Team IDs and historical membership/filter rules | Pending | Pending | Ziven: pending |
| Business reporting timezone and day boundaries | Eastern; report output UTC. Exact IANA zone, DST and day boundaries pending | Ziven reply, recorded 2026-10-01 | Ziven; email date not supplied |
| SLA thresholds, targets, exclusions and effective dates | Per-skill raw settings supplied; units, API formula semantics and historical effective dates pending | Skills.csv; see evidence below | Ziven; export/email dates not supplied |
| Baseline window, weighting, exclusions and missing-data rules | Eight-week comparison accepted; December/holiday seasonality must be considered. Weighting, holiday policy and missing-data rules pending | Ziven reply, recorded 2026-10-01 | Ziven; email date not supplied |
| Comparison period and per-metric tolerance/rounding | Pending | Pending | Pending |

## Ziven evidence recorded 2026-10-01

Source: reply supplied by Behnam in this conversation, attributed to Ziven
Nickerson, and `C:\Data Engineering\LibreChat\Skills.csv`. The email date,
export date and configuration effective dates were not supplied; the recording
date is not a substitute for those dates.

The [selected CSV columns](evidence/pbi-04/ziven-skills-2026-10-01.csv) preserve
all 16 supplied skill rows and their raw scope/SLA settings. The
[metadata](evidence/pbi-04/ziven-skills-2026-10-01.metadata.json) records the
original file hash and retained columns. Assigned-user and contact details
are not copied into this evidence extract.

- The file contains 16 unique IDs, all Active, across Admin, Logistics
  Scheduling, Patient Collections, Patient Support and Post Delivery campaigns.
  It has no CS grouping or second page. Ziven describes separate CS and other
  department pages, so the main-CS export or an explicit ID list is still
  needed. Do not assume these 16 are the final allowlist or the full inventory;
  they do not resolve the historical 83/85 inventory discrepancy.
- SLA goals are 90% for 14 skills and 100% for two (18499110 and 18499108).
  Raw thresholds include 60, 90, 120, 185000 and 190800. Preserve them exactly;
  threshold units and applicability, especially voicemail thresholds, still
  need verification. Short-abandon enable flags, thresholds and `Short Abandons`
  flags differ by skill. Do not collapse them into global settings or infer
  the API numerator/denominator from these column names.
- Eastern business time and UTC report display are distinct. `America/New_York`
  is a candidate interpretation, not an explicitly confirmed IANA identifier.
  Confirm DST and local day boundaries; translate the same local period to UTC
  for report/API reconciliation rather than treating UTC midnight as the
  business day boundary.
- Eight weeks is business-confirmed for comparison. Weekday matching,
  weighting, minimum valid samples and zero/missing-data handling remain open.
  December/holiday seasonality is an explicit requirement, but Ziven did not
  specify dates or whether to exclude, annotate or compare seasonal periods.
  Do not automatically discard December or equate statistical outlier removal
  with an agreed holiday policy.
- The current dashboard only exposes live data; historical dashboard viewing
  requires an additional paid feature. Use a historical report export for a
  closed, retained period as the reconciliation reference. Capture report name,
  exact labels, filters, timestamps, units and agreed tolerances. Live widgets
  still require separate mapping; this does not establish that all dashboard
  metrics exist in historical reports.

The existing example config remains a template. Its global SLA target and
short-abandon fields cannot represent the supplied per-skill differences;
production configuration needs that representation resolved before confirmation.
PBI-04 remains open for the missing CS scope, metric/report definitions,
historical SLA semantics and paired report/API evidence.

## Skill inventory and narrowing

Start with the volume-ranked names in the implementation guide, recover their
verified IDs, then record Ziven's actual choices. Do not adopt the ranked list
unchanged by default. Reconcile the PBI's 83 skills with discovery's 85 returned
rows using dated inventory and unique-ID counts.

| Skill ID | Name | Team relationship and effective period | Discovery rank/source | Include/exclude and reason | Confirmed by/date |
|---|---|---|---|---|---|
| Pending inventory | | | | | |

## Metric mapping

Add one row per actual dashboard metric. Attach a per-metric detail record for
formula components, joins, exclusions, missing/zero behavior, precision, SLA and
baseline dependencies, source schema evidence and configuration versions.

| Metric key / dashboard label | Endpoint/version + response fields | Units/grain/formula reference | Historical/live availability | Scope/config reference | Status / evidence |
|---|---|---|---|---|---|
| Pending dashboard inventory | Unconfirmed | Unconfirmed | Unconfirmed | Pending | Not validated |

## Unsupported and live-only metrics

| Dashboard metric | Unavailable field/dimension/semantics | Reason and evidence | Historical restriction | Business acknowledgement / follow-up |
|---|---|---|---|---|
| Pending assessment; do not interpret as none | | | | |

## Historical reconciliation

Following Ziven's reply, use a historical report export as the reference;
a past-day dashboard capture is unavailable with the current subscription.

Record run ID, code revision/dirty state, dashboard/config versions, local and
UTC boundaries, timezone, scope, refresh/capture timestamps and sanitized
artifact locations/hashes before filling this table. Use the same period and
filters on both sides. Metric values below must come from actual observations.

| Metric | Historical report value | API-derived value | Unit | Absolute / percentage delta | Agreed tolerance | Outcome / explanation / evidence |
|---|---|---|---|---|---|---|
| Not run | | | | | | Pending: no API-side comparison has been run (see below) |

### Contact History exports: import completed, API comparison NOT run (2026-10-03)

Reference: three Contact History exports (`ContactHistory (20|21|22).csv`) plus
`Skills.csv`, read in place. The user confirmed in conversation (no email date
recorded) that the three exports together are the full day and all the reporting
available. Importer/reconciliation code: `mapping/contact_history.py`,
`mapping/contact_history_reconcile.py`, `scripts/reconcile_contact_history.py`;
sanitized evidence: `docs/evidence/pbi-04/contact-history-import/` (counts,
hashes and skill names only; no phone numbers, agent names or per-contact IDs).

What the import established (the importer recomputed every figure in the closure guide):

| Fact | Value |
|---|---|
| Rows (20 / 21 / 22 / combined) | 1,000 / 1,000 / 30 / 2,030 |
| Distinct exported contact IDs (per file / combined) | 996 / 999 / 30 / 2,021 |
| Distinct master contact IDs | 1,661 (259 masters have more than one contact) |
| Exact repeated rows | 7 (3 within a file, 4 across files 20 and 21) |
| Repeated IDs with differing fields | 2, both differing only in `Team` (unexplained) |
| Contacts appearing under more than one skill | 0 |
| IDs printed with a trailing `*` | 374 rows; meaning **not established**, never stripped silently |
| Media type | Phone, all rows (does not prove the report was filtered to Phone) |
| Earliest / latest start (as displayed) | 01:35:48 / 23:46:14 on 10/1/2026 |
| Report skills / resolved to an ID by the supplied `Skills.csv` | 29 / 8 |

Skill mapping: 21 of 29 report skill names (including all `Cardiac *`, `Ortho *`,
`Customer Service General`, `CS - Outbound`, `Outbound`, `Test IB`,
`Remote Onboarding`) have no entry in the supplied 16-row `Skills.csv`. They are
recorded as **unresolved**; no ID was invented or fuzzy-matched. A dated
authoritative inventory is needed.

What is NOT established, so the comparison status is **UNRESOLVED** (not MATCH):

- No verified contact-detail API endpoint, so no API-side records were fetched or
  compared; nothing here is a reconciliation of the report against the API.
- The export's grain (contact / routed leg / transfer / master interaction), the
  meaning of the `*` marker and the explanation of the two conflicting repeats.
- That the displayed times are UTC (labelled an ASSUMPTION in the run manifest;
  Ziven's statement is Eastern business time with UTC report output).
- Duration units and lifecycle meaning (`Duration` is kept as text, not compared).
- Report filters, generation time and source email date (not supplied; not invented).

The 2,021 distinct IDs and 1,661 masters are properties of the export; they are
not "contacts offered" or "contacts handled", and no dashboard metric is
validated by this import. Service level, abandonment, ASA, AHT, live state and
the eight-week baseline cannot be validated from these columns at all.

## Acceptance checklist

- [ ] Every dashboard metric has an endpoint/field mapping or explicit unsupported status.
- [ ] Skill and team IDs recorded; discovery ranking narrowed with Ziven.
- [ ] Inventory-count discrepancy explained; no hard-coded 83/85 assumption.
- [ ] Timezone confirmed against the business/dashboard configuration.
- [ ] SLA thresholds and semantics verified against the API fields used.
- [ ] Baseline rules confirmed, or explicitly not applicable where appropriate.
- [ ] At least one historical period reconciled; every discrepancy explained.
- [ ] Unsupported metrics listed without approximation or zero substitution.
- [ ] Live-only and historical fields distinguished; no live field used historically.
- [ ] Client-side scoping verified after a complete fetch; ignored server filters unused.
- [ ] Evidence traceable; configuration and accepted limitations reviewed with Ziven.

Do not close this PBI on endpoint access, template completion or passing mocks.
