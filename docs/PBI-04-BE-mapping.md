# PBI-04-BE: dashboard mapping and acceptance evidence

Status: **not validated**. Prepared 2026-09-25. No dashboard configuration,
confirmed scope or paired dashboard/API measurements have been supplied.
This is an evidence template; no blank row is acceptance evidence.

Implementation instructions: [PBI-04-BE-implementation.md](PBI-04-BE-implementation.md).

**2026-09-25 code status:** the harness described in the implementation
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
| Dashboard/report/widgets/version | Pending | Pending | Pending |
| Included skill IDs and names | Pending | Pending | Ziven: pending |
| Excluded skill IDs and reasons | Pending | Pending | Ziven: pending |
| Team IDs and historical membership/filter rules | Pending | Pending | Ziven: pending |
| Business reporting timezone and day boundaries | Pending; do not default to UTC | Pending | Ziven: pending |
| SLA thresholds, targets, exclusions and effective dates | Pending | Pending | Ziven: pending |
| Baseline window, weighting, exclusions and missing-data rules | Pending | Pending | Ziven: pending |
| Comparison period and per-metric tolerance/rounding | Pending | Pending | Pending |

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

Record run ID, code revision/dirty state, dashboard/config versions, local and
UTC boundaries, timezone, scope, refresh/capture timestamps and sanitized
artifact locations/hashes before filling this table. Use the same period and
filters on both sides. Metric values below must come from actual observations.

| Metric | Dashboard value | API-derived value | Unit | Absolute / percentage delta | Agreed tolerance | Outcome / explanation / evidence |
|---|---|---|---|---|---|---|
| Not run | | | | | | Pending |

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
