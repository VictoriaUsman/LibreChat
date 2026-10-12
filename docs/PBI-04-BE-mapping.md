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

**2026-10-12 update:** Ziven's final reply is recorded in
[ziven-response-2026-10-12.md](evidence/pbi-04/ziven-response-2026-10-12.md) (received 2026-10-12; no email date).
Confirmed: 29 skills currently selected, two billing skills intended but not selected, no team filters, phone only
with voicemail excluded, exports in her Eastern timezone, 30%/100% are colour thresholds, reported SLA 90 s / 90% with
short abandons of 15 s or less excluded, and no historical October 1 dashboard SLA. Ziven's 29 CS skill names (Customer Service Team SLA widget) are resolved to API IDs below as Set A; the two intended
billing additions and the all-department export population are kept separate. The SLA fields were found in the API but
their semantics (she says completion time, not answer time) are **not verified**. Historical SLA reconciliation is
not done and any deferral needs owner approval. PBI-04 remains open. The current acceptance table is in
[closure-2026-10-03.md](evidence/pbi-04/closure-2026-10-03.md).

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
| Included skill IDs and names | Customer Service Team SLA widget: Ziven's 29 names, all resolved to unique API IDs (Set A below; 4 name matches are word-order inferences). ROMTech Service Level widget: skill list not supplied. The export's 29 all-department skills are a separate population. 16 pairs were supplied earlier in Skills.csv | Ziven reply 2026-10-12; October 6 API capture; live `/skills` 2026-10-12 | Ziven; received 2026-10-12, no email date |
| Excluded skill IDs and reasons | Voicemail skills excluded (Ziven), including `Billing General VM`. Two billing skills intended but not selected | Ziven reply 2026-10-12 | Ziven; received 2026-10-12 |
| Team IDs and historical membership/filter rules | No team filters on either SLA widget | Ziven reply 2026-10-12 | Ziven; received 2026-10-12 |
| Business reporting timezone and day boundaries | Eastern; report output UTC. Exact IANA zone, DST and day boundaries pending | Ziven reply, recorded 2026-10-01 | Ziven; email date not supplied |
| SLA thresholds, targets, exclusions and effective dates | Reported: 90 s to completion, 90% goal, short abandons of 15 s or less excluded; the API's current per-skill settings equal it for all 29 CS skills (current values, not October 1). 30% and 100% widget thresholds are colour thresholds. Formula semantics and effective dates unverified | Ziven reply 2026-10-12; live `/skills` 2026-10-12; Skills.csv | Ziven; received 2026-10-12 |
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

**Set A: Ziven's 29 Customer Service Team SLA skills** (last column: API `contactsOffered` / Oct 1 export contacts):

| Ziven's name | Match rule | Skill ID | Inventory name | Campaign | Oct 1 offered / export |
|---|---|---|---|---|---:|
| Remote Onboarding | exact | 36302025 | Remote Onboarding | Customer Service | 8 / 8 |
| Cardiac Appointments | exact | 35588248 | Cardiac Appointments | Customer Service | 25 / 25 |
| Cardiac Appointments Spanish | exact | 35588249 | Cardiac Appointments Spanish | Customer Service | 0 / 0 |
| Cardiac Billing | exact | 20954831 | Cardiac Billing | Customer Service | 126 / 126 |
| Cardiac Billing Spanish | exact | 20954832 | Cardiac Billing Spanish | Customer Service | 0 / 0 |
| Cardiac Delivery Pickup | exact | 20954834 | Cardiac Delivery Pickup | Customer Service | 17 / 17 |
| Cardiac Delivery Pickup Spanish | inventory 30-char name limit | 20954835 | Cardiac Delivery Pickup Spanis | Customer Service | 0 / 0 |
| Cardiac General | exact | 20954836 | Cardiac General | Customer Service | 26 / 26 |
| Cardiac General Spanish | exact | 20954837 | Cardiac General Spanish | Customer Service | 2 / 2 |
| Cardiac Sales | exact | 20954625 | Cardiac Sales | Customer Service | 0 / 0 |
| Cardiac Sales Spanish | exact | 20954628 | Cardiac Sales Spanish | Customer Service | 0 / 0 |
| Cardiac Tech Support | exact | 20954838 | Cardiac Tech Support | Customer Service | 12 / 12 |
| Cardiac Tech Support Spanish | exact | 20954840 | Cardiac Tech Support Spanish | Customer Service | 0 / 0 |
| Customer Service General | exact | 35588202 | Customer Service General | Customer Service | 50 / 50 |
| Customer Service General Spanish | inventory 30-char name limit | 35588203 | Customer Service General Spani | Customer Service | 0 / 0 |
| Order Status Cardiac | same words, order differs (inferred) | 35588243 | Cardiac Order Status | Customer Service | 7 / 7 |
| Order Status Cardiac Spanish | same words, order differs (inferred) | 35588244 | Cardiac Order Status Spanish | Customer Service | 0 / 0 |
| Order Status Ortho | same words, order differs (inferred) | 35588246 | Ortho Order Status | Customer Service | 57 / 57 |
| Order Status Ortho Spanish | same words, order differs (inferred) | 35588247 | Ortho Order Status Spanish | Customer Service | 0 / 0 |
| Ortho Billing | exact | 18499102 | Ortho Billing | Customer Service | 63 / 63 |
| Ortho Billing Spanish | exact | 18499103 | Ortho Billing Spanish | Customer Service | 1 / 1 |
| Ortho Delivery_Pickup | case/underscore only | 18499100 | Ortho Delivery Pickup | Customer Service | 146 / 146 |
| Ortho Delivery_Pickup Spanish | case/underscore only | 18499101 | Ortho Delivery Pickup Spanish | Customer Service | 3 / 3 |
| Ortho General | exact | 18499104 | Ortho General | Customer Service | 104 / 104 |
| Ortho General Spanish | exact | 18499105 | Ortho General Spanish | Customer Service | 1 / 1 |
| Ortho Sales | exact | 20954624 | Ortho Sales | Ortho Sales | 0 / 0 |
| Ortho Sales Spanish | exact | 20954629 | Ortho Sales Spanish | Ortho Sales | 0 / 0 |
| Ortho Tech Support | exact | 18499098 | Ortho Tech Support | Customer Service | 131 / 131 |
| Ortho Tech Support Spanish | case/underscore only | 18499099 | Ortho Tech Support spanish | Customer Service | 1 / 1 |

**Set B (intended additions, not selected):** `Billing General` 36302045; "Biling General Spanish" unresolved by name, candidate `Billing General Spanish` 36302046 (inferred); `Billing General VM` excluded (voicemail).

October 1 export population, **all departments, not the CS scope** (kept for the contact reconciliation):

| Skill ID | Name | Campaign | Resolved by | API SLA settings | Oct 1 export contacts |
|---|---|---|---|---|---:|
| 35588248 | Cardiac Appointments | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 25 |
| 20954831 | Cardiac Billing | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 126 |
| 20954834 | Cardiac Delivery Pickup | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 17 |
| 20954836 | Cardiac General | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 26 |
| 20954837 | Cardiac General Spanish | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 2 |
| 35588243 | Cardiac Order Status | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 7 |
| 20954838 | Cardiac Tech Support | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 12 |
| 35588833 | CS - Outbound | Customer Service | capture + /skills | 30 s / 90% / short-abandon off | 458 |
| 35588202 | Customer Service General | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 50 |
| 18492667 | Default NO-Agent Inbound | Admin | Skills.csv + capture + /skills | 90 s / 90% / short-abandon on, 90 s | 250 |
| 18499108 | Logistics Outbound | Logistics Scheduling | Skills.csv + capture + /skills | 60 s / 100% / short-abandon off | 52 |
| 29277623 | Logistics Scheduler | Logistics Scheduling | Skills.csv + capture + /skills | 120 s / 90% / short-abandon off | 219 |
| 35588224 | Logistics Scheduler Spanish | Logistics Scheduling | Skills.csv + capture + /skills | 120 s / 90% / short-abandon on, 15 s | 6 |
| 18499102 | Ortho Billing | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 63 |
| 18499103 | Ortho Billing Spanish | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 1 |
| 18499100 | Ortho Delivery Pickup | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 146 |
| 18499101 | Ortho Delivery Pickup Spanish | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 3 |
| 18499104 | Ortho General | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 104 |
| 18499105 | Ortho General Spanish | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 1 |
| 35588246 | Ortho Order Status | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 57 |
| 18499098 | Ortho Tech Support | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 131 |
| 18499099 | Ortho Tech Support spanish | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 1 |
| 18499109 | Outbound | Customer Service | capture + /skills | 60 s / 100% / short-abandon off | 13 |
| 36302048 | Patient Collections Bill Spani | Patient Collections | Skills.csv + capture + /skills | 90 s / 90% / short-abandon on, 15 s | 1 |
| 36302043 | Patient Collections Billing | Patient Collections | Skills.csv + capture + /skills | 90 s / 90% / short-abandon on, 15 s | 1 |
| 36301865 | Patient Support | Patient Support | Skills.csv + capture + /skills | 90 s / 90% / short-abandon off | 15 |
| 36302025 | Remote Onboarding | Customer Service | capture + /skills | 90 s / 90% / short-abandon on, 15 s | 8 |
| 20954688 | Test IB | Test1 | capture + /skills | 30 s / 90% / short-abandon off | 2 |
| 21036611 | VM Remove From Queue | Admin | Skills.csv + capture + /skills | 90 s / 90% / short-abandon off | 224 |

Intended additions (Ziven 2026-10-12), not selected, kept separate:

| Skill ID | Name | Campaign | Media | API SLA settings | Oct 1 offered (API summary) |
|---|---|---|---|---|---:|
| 36302045 | Billing General | Customer Service | Phone Call | 90 s / 90% / short-abandon on, 15 s | 0 |
| 36302046 | Billing General Spanish | Customer Service | Phone Call | 90 s / 90% / short-abandon on, 15 s | 0 |
| 36302047 | Billing General VM | Customer Service | Voice Mail | 185000 s / 90% / short-abandon off | 0 |

## Metric mapping

Add one row per actual dashboard metric. Attach a per-metric detail record for
formula components, joins, exclusions, missing/zero behavior, precision, SLA and
baseline dependencies, source schema evidence and configuration versions.

| Metric key / dashboard label | Endpoint/version + response fields | Units/grain/formula reference | Historical/live availability | Scope/config reference | Status / evidence |
|---|---|---|---|---|---|
| ROMTech Service Level: contacts in SLA / out of SLA / percent | candidate: `/skills/summary` `contactsWithinSLA`, `contactsOutOfSLA`, `serviceLevel` (field names only) | Counts per skill per requested window; formula and short-abandon handling unverified | Dashboard live-only (30-minute trending); API window-aggregated; no October 1 dashboard value | Widget: 2 campaigns, 29 skills, Phone Call, no team filter, 24 intervals / 30 min; 30% is a colour target (above/below it changes the colour) | Not validated: the widget's skill list was not supplied; for the CS skills 7 of 780 offered on Oct 1 fall in neither count |
| Customer Service Team SLA: in / out / percent | same candidate fields | same | same | Widget: 1 campaign, 29 skills, all 9 media types, no team filter; 100% is a colour target | Not validated; media types differ from the phone-only widget |
| Customer Service Agent State Count: Available, Unavailable, Inbound, Outbound, Preview, Waiting | candidate: `/skills/summary` `agentsAvailable`, `agentsUnavailable`, `agentsWorking`, `agentsLoggedIn` (names only; per-state mapping unknown) | Live snapshot of agents | Live-only | Widget settings not supplied | Not validated |
| Customer Service Team Agent Status: per-agent state, time, team, session time | Not identified. `/skills/summary` is per skill, not per agent | Live per-agent view | Live-only | Widget settings not supplied | Unsupported until an agent-level source is verified |

## Unsupported and live-only metrics

| Dashboard metric | Unavailable field/dimension/semantics | Reason and evidence | Historical restriction | Business acknowledgement / follow-up |
|---|---|---|---|---|
| Any October 1 dashboard value (all four widgets) | Dashboard exposes live data only | Ziven: historical dashboard results unavailable | Use a retained report/API reference | Pending owner approval for any SLA deferral |
| Customer Service Team Agent Status | No verified per-agent API source; names are personal data and are not stored | Not assessed against an agent endpoint | Live-only | Pending |
| Short-abandon and 30 s/100% colour behaviour | Colour thresholds are display settings, not metrics | Ziven 2026-10-12 | Not applicable | None |
| Other dashboard metrics beyond the four widgets seen | Not inventoried | Only four widgets supplied | Unknown | Ziven to supply any others; "none" is not assumed |

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
