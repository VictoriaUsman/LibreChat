# PBI-04-BE: metric mapping validation

Prepared 2026-09-25 from the acceptance criteria supplied by the user.
Repository baseline: `c7e330d`; discovery narrative inspected on `PBI-01`
at `e3d7580`, `discovery/findings.md`. This is an implementation guide,
not a completed mapping or evidence of dashboard reconciliation.

## Business input update (recorded 2026-10-01)

See [Ziven's evidence and remaining decisions](PBI-04-BE-mapping.md#ziven-evidence-recorded-2026-10-01).
Eight weeks is now accepted for comparison; detailed baseline and holiday rules
remain open. Business time is Eastern with UTC report output; exact IANA/DST
semantics remain to be confirmed. Per-skill SLA settings are supplied for 16
skills, but the separate main-CS scope is not identifiable in the supplied CSV.
Historical reconciliation must use a report export because the dashboard is
live-only under the current subscription. References below to historical
dashboard figures should therefore be read as historical report figures;
live-widget mapping remains a separate requirement.

## Outcome and scope

Produce a business-confirmed, versioned mapping between every metric on
Michelle's dashboard and reproducible API data, including explicit unsupported
metrics. Confirm scope before implementing production aggregation. Implement
only the extraction, validation and small reference calculations needed to
prove the mapping in this item; do not build the full reporting/aggregation
engine, MCP host or infrastructure here.

Use PBI-02's `CXoneClient.get(path, params=...)` and credential provider.
Endpoint access, passing tests and successful HTTP responses are not evidence
that a dashboard metric has the same meaning as an API field.

Keep implementation and acceptance separate: synthetic fixtures can validate
the harness now, but Ziven's configuration input and real paired observations
are required to complete the mapping. No credential or dashboard access is
assumed by these instructions.

## Inputs and decisions to capture with Ziven

Record each decision's value, source, effective date, confirmer and confirmation
date. Unanswered settings must remain explicitly unconfirmed, not defaults.

| Input | Required detail |
|---|---|
| Dashboard identity | Dashboard/report identifier, version, widgets and exact metric labels; configuration/export evidence and who owns its definition |
| Skill scope | IDs and names; included/excluded skills and reasons; inactive/deleted skills relevant to the historical comparison; channel/direction/queue filters |
| Team scope | Team IDs/names, membership rule, skill/team relationship, whether selection means intersection or union; membership effective during the historical period |
| Business timezone | Explicit IANA timezone confirmed against dashboard/business configuration, local day boundaries and daylight-saving behavior; UTC only if explicitly confirmed |
| SLA | Per-skill thresholds and units, target percentage separately, numerator/denominator, short-abandon rules, exclusions, channel differences and historical configuration changes |
| Baseline | Reference dates, weekday matching, lookback count, interval width, aggregation/weighting, holiday/outage exclusions, zero/missing-day handling and minimum valid samples |
| Comparison period | At least one closed historical period with retained data and dashboard figures; identical local boundaries and filters; refresh/export timestamp |
| Comparison rules | Metric-specific rounding and tolerances agreed before comparison; owner who accepts explanations or limitations |

Eight weeks is now accepted by Ziven; same-weekday selection and other
baseline rules remain unconfirmed. UTC is the report display timezone, not
the confirmed business day boundary. A live SLA setting or current
team membership is not automatically valid for a historical period.

### Discovery skill shortlist

The 2026-09-24 findings rank these names by 2026-09-23 UTC volume:

1. CS - Outbound
2. Logistics Scheduler
3. Default NO-Agent Inbound
4. Ortho Delivery Pickup
5. VM Remove From Queue
6. Ortho Tech Support
7. Cardiac Billing
8. Ortho General
9. Logistics Outbound
10. Ortho Billing

Use this list to start the discussion with Ziven, not as an allowlist. The
narrative does not supply trustworthy ID/name pairs or the ranking's numeric
evidence here. Recover the sanitized inventory/ranking artifact or recreate it
with a dated read-only fetch; retain the full inventory so lower-volume skills
can still be selected. Record the ranking metric and window when recovered.

The PBI says 83 available skills; discovery reports 85 returned skill rows.
Record inventory timestamp, unique IDs, duplicates and active/inactive filters,
then explain the discrepancy. Do not assume either count is invariant, fabricate
missing IDs, or reject a tenant solely because its inventory count changed.

## Mapping contract

Create one row per actual dashboard metric; an unknown metric inventory must
not be replaced with a guessed list. Each row must contain:

- Stable metric key, exact dashboard label, widget and definition evidence.
- Source endpoint path, API version, request parameters and response field paths;
  units, type, grain, interval meaning and field-semantics evidence.
- Availability: `historical`, `live_only`, `both`, or `unconfirmed`, justified
  for this field and endpoint. A date parameter alone does not prove historical
  semantics. For `both`, document and test the two contracts separately.
- Scope and join keys, cardinality, duplicate handling, team attribution and
  effective-date rules. Explain whether a skill summary can express the team
  filter; if not, identify a verified alternative source or mark unsupported.
- Exact formula, required components, denominator-zero behavior, null/missing
  behavior, weighting, exclusions and rounding stage. Use declared operations,
  not arbitrary executable formula strings.
- SLA and baseline configuration references where applicable; for a dashboard
  without a baseline, record confirmed `not_applicable`, not an invented rule.
- Mapping status: `unconfirmed`, `candidate`, `validated`, or `unsupported`;
  evidence references, confirmer and unresolved limitations.

Do not equate similarly named fields with dashboard definitions. In particular,
do not sum percentages, average averages without their weights, or equate a
threshold in seconds with an SLA target percentage. If the API provides only
rounded percentages or insufficient numerator/denominator data, explain whether
exact reproduction is possible. Do not substitute another metric silently.

## Client-side scoping and data validity

Discovery reports that `/skills/summary` ignores `skillId`, `skillIds` and
`skillNumber` query parameters. Fetch the requested time window, complete any
verified pagination, then apply confirmed ID-based scope locally. Do not send
those parameters as a filtering mechanism. Endpoint/version, date parameter
names and response paths must be verified against actual responses before the
adapter is considered validated; discovery is a lead, not a complete schema.

For that endpoint discovery observed one aggregated row per skill per requested
window, not per-interval buckets. Do not fabricate interval timestamps or
reconstruct team-level data from skill totals when the attribution is missing.
Do not assume other endpoints share its shape or silently ignored parameters.

Validate rows and required fields before calculation. Track requested, returned,
included, excluded and missing IDs. Preserve separate response validity,
coverage and value states: absent/null/unavailable is unknown, never zero.
Zero is valid only for an actually present, valid numeric field. Reject booleans,
nonfinite numbers and invalid count values; explicitly define numeric-string
support. Detect duplicate records and join expansion rather than double-count.
Unknown pagination or incomplete scope coverage makes the comparison unresolved.

Use timezone-aware local windows and convert each boundary to UTC. Internally
represent windows as `[start, end)`; verify the API's inclusivity/precision and
translate explicitly. Never add an assumed 24 UTC hours to represent every local
day. Historical calculations must reject dependencies classified as live-only
or still unconfirmed, including configuration needed to reproduce old figures.

## File-level code instructions (proposed additions)

| File | Responsibility |
|---|---|
| `src/romtech_mcp/mapping/models.py` | Typed scope, metric mapping, field availability, window, provenance and reconciliation results; explicit statuses and invariants |
| `src/romtech_mcp/mapping/config.py` | Load versioned non-secret JSON mapping/config; reject unconfirmed scope/timezone/SLA/baseline for dependent acceptance calculations; allow explicitly exploratory inventory mode |
| `src/romtech_mcp/mapping/source.py` | Small reporting adapter around injected `CXoneClient`; verified endpoint/shape/pagination; normalized observations and sanitized provenance |
| `src/romtech_mcp/mapping/scope.py` | Pure client-side skill/team selection with coverage diagnostics and verified historical attribution; no network or implicit scope expansion |
| `src/romtech_mcp/mapping/windows.py` | Confirmed timezone/date rules and explicit endpoint boundary conversion; baseline planning only from approved rules |
| `src/romtech_mcp/mapping/reconcile.py` | Explicit reference calculations for mapped metrics; compare matched dashboard/API observations; emit deltas, explanations and unresolved results |
| `scripts/reconcile_dashboard.py` | CLI for offline fixture comparison and explicit live extraction; write a run manifest and per-metric results; nonzero exit for unresolved required comparisons |
| `config/cxone-dashboard-mapping.example.json` | Schema/version and empty, explicitly unconfirmed business settings; no invented IDs, endpoint fields or production defaults |
| `docs/PBI-04-BE-mapping.md` | Human-reviewable mapping, confirmed configuration, inventory decisions, unsupported metrics and reconciliation evidence |
| `tests/mapping/` | Deterministic contract, scope, window and reconciliation tests using synthetic/sanitized fixtures |

Add package `__init__.py` files as needed. Keep business mapping out of
`cxone/config.py`, whose existing purpose is transport/authentication settings.
Use standard-library JSON and dataclasses unless an existing dependency is
needed. Add `tzdata` to runtime dependencies if required for IANA timezone
availability on Windows, and validate availability explicitly.

Suggested interfaces, to implement rather than assume already present:

```python
validate_mapping(mapping) -> list[ValidationIssue]
select_scope(observations, scope, period) -> ScopedObservations
build_windows(reference, confirmed_rules) -> list[ReportingWindow]
derive_metric(mapping, observations, period) -> MetricObservation
compare_metric(api_observation, dashboard_observation, tolerance) -> Comparison
```

The source adapter owns fetch/schema validation; pure functions own business
semantics. Keep errors typed and sanitized. Reuse the existing client's bounded
retry/deadline policy; record its policy and any known attempts/retries. Never
claim one network attempt per logical call when the transport retries. Do not
log raw responses, credentials, tokens, agent/contact records or SDK errors.

## Implementation sequence and reconciliation procedure

1. Inventory widgets and collect configuration evidence. Recover the ranked
   skill list and full ID inventory; narrow it with Ziven. Record exclusions,
   team selection, timezone, SLA and baseline decisions before coding formulas.
2. Implement schemas, loaders, scoping and window handling with synthetic tests.
   Create candidate mappings only from verified field semantics. Unknowns remain
   unknown; do not postpone them by guessing.
3. Capture dashboard figures for one agreed closed historical period, with
   metric labels, exact filters, timezone, boundaries and refresh time. If the
   dashboard has changed since that period, retain the applicable configuration.
4. Fetch API observations for those same boundaries and scope, apply local
   filters, and calculate only validated candidate formulas. Keep minimal
   aggregate evidence in an access-controlled location; avoid customer/agent
   details. Store hashes/references and sanitized diagnostics in the repository.
5. Compare every reproducible historical dashboard metric for that period.
   Live-only metrics must have availability evidence and an explicit historical
   non-applicability entry; assess their live mapping separately. Unsupported
   metrics require a specific reason and business acknowledgement, not a fake
   zero or a successful comparison status.
6. Report dashboard value, API value, unit, absolute delta, percentage delta
   where meaningful, rounding/tolerance, outcome and explanation. If dashboard
   value is zero, percentage delta is null; retain absolute difference. Any
   unexplained discrepancy blocks that metric's validation. An explained but
   out-of-tolerance result stays visible with an accepted limitation or follow-up;
   do not silently enlarge tolerance to make it pass.
7. Have Ziven confirm the final configuration and mapping/exclusions; record
   who reviewed reconciliation and any accepted discrepancies. Publish the
   mapping contract for the later aggregation work, including unsupported cases.

Each run manifest must identify run ID, UTC capture times, source commit and
dirty-tree state, dashboard/config versions, exact local and UTC boundaries,
scope IDs, source endpoint/version/parameters, artifact references and hashes,
validation outcomes and limitations. Preserve failed/partial runs. A dashboard
export and API capture must be independently traceable; an API-to-API fixture
comparison is not dashboard reconciliation.

## Required tests and completion

Test ignored server filtering (response contains excluded skills), missing IDs
and metrics, pagination completeness, duplicate/join inflation, and invalid
numeric values. Test skill/team intersection/union according to confirmed rules,
historical membership changes, live-field rejection, timezone/DST boundaries,
weighted ratios, zero denominators, rounding and baseline exclusions. Include
a mismatch test proving reconciliation reports failure instead of changing scope
or tolerance. Mock transport for ordinary tests; no automatic live tenant calls.

Run `python -m pytest tests/mapping tests/cxone -q`; run infrastructure tests only
if shared deployment files change. Test success qualifies implementation, not
business configuration or live acceptance. Completion requires all rows in the
companion mapping document to be supported by actual evidence, including the
historical comparison and explicit unsupported/live-only classifications.
