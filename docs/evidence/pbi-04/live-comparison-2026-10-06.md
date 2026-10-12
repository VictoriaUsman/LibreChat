# October 1 Contact History: live API comparison

Run on 2026-10-06 from PBI-04 baseline commit `7e841d0` with the new
`scripts/probe_contact_history_live.py` discovery helper. Existing discovery
credentials were read in memory from the gitignored local environment file;
production authentication was not changed. Discovery auth code came from the
existing `pbi/cxone-fetch-timing` worktree (`c2a7fec`). No raw API contact records,
credentials, phone numbers or agent names were saved by this run.

## Verified execution

Authentication succeeded. The official NICE [Reporting API reference](https://developer.niceincontact.com/api/reportingapi)
documents GET `/contacts`, with startDate/endDate, top/skip and selectable fields.
The tenant accepted the v27.0 request. Data was fetched sequentially with
`top=1000`, checking a stable `totalRecords` across pages and unique API contact
IDs. This is real tenant evidence, not a synthetic fixture.

| Check | UTC-calendar-day hypothesis | Eastern-calendar-day hypothesis |
|---|---:|---:|
| UTC window | Oct 1 00:00–Oct 2 00:00 | Oct 1 04:00–Oct 2 04:00 |
| API rows | 2,025 | 2,021 |
| Export distinct IDs after diagnostic marker removal | 2,021 | 2,021 |
| Matched IDs | 1,988 | 2,021 |
| Export-only IDs | 33 | 0 |
| API-only IDs | 37 | 0 |
| Matched skill-name differences | 0 | 0 |
| Matched start differences of at least one second | 1,988 | 0 |
| Matched contacts with a team-name difference in any export row | 2 | 2 |

The UTC interpretation produced a consistent four-hour timestamp difference
plus subsecond precision. Interpreting the displayed export times as
`America/New_York` and fetching the corresponding Eastern full day produced an
exact contact-population and skill match. All 29 per-skill distinct contact
counts agree. Each observed skill name maps to exactly one ID in this capture,
including the 21 names absent from Skills.csv. This proves observed mapping
agreement for these contacts, not final production CS scope or a complete skill
inventory.

Eastern-window pages: 1,000 + 1,000 + 21 rows, reported total 2,021 on every
page, no repeated API IDs. Start timestamps differ only below one second;
the export displays whole seconds. This is evidence supporting an Eastern
display interpretation, not an independent confirmation of the export settings
or an agreed timestamp tolerance.

## Diagnostic rules and remaining limits

- The export contains 2,030 rows. Rows were grouped by contact ID after removing
  trailing `*` for this diagnostic comparison. All export skill/time variants
  were checked against the API record; raw rows were not silently rewritten.
- Prior import found seven exact repeats and two IDs differing only in Team.
  This live run likewise found two contacts with team differences. No team
  attribution policy or explanation is accepted yet.
- The `*` marker's meaning remains unverified. Observed marked contacts have
  multiple API transfer labels, including `None`; do not claim this run proves
  that the marker means transfer. Confirm its display semantics before adopting
  normalization as an acceptance rule.
- No SLA, abandonment, ASA, AHT, live queue/staffing or baseline behavior was
  reconciled. Contact-level agreement does not validate those calculations.
- No PBI-owner reduced-scope approval was requested or recorded by this run.

## Artifacts and reproduction

Sanitized capture summaries include input hashes, page counts, skill-ID pairs,
timestamp-difference histograms and explicit assumptions:

- [UTC-window evidence](contact-history-api-probe-2026-10-06.json)
- [Eastern-window evidence](contact-history-api-probe-eastern-2026-10-06.json)

The helper requires the existing discovery module path and local credential
file, supplied explicitly; it is an exploratory tool, not the production live
adapter proposed in the implementation guide. It stops on errors and does not
follow redirects or save raw response bodies. Reproduction requires authorized
network access and the existing discovery dependencies.

```powershell
python scripts/probe_contact_history_live.py `
  --discovery-dir 'C:\Data Engineering\LibreChat\ROMTechMCP.worktrees\pbi-01-corrections\discovery' `
  --env-file discovery/.env `
  --report 'C:\Data Engineering\LibreChat\ContactHistory (20).csv' `
  --report 'C:\Data Engineering\LibreChat\ContactHistory (21).csv' `
  --report 'C:\Data Engineering\LibreChat\ContactHistory (22).csv' `
  --source-timezone America/New_York `
  --window-start 2026-10-01T04:00:00Z `
  --window-end 2026-10-02T04:00:00Z `
  --output docs/evidence/pbi-04/contact-history-api-probe-eastern-2026-10-06.json
```

Do not label the full PBI closed. The next decision is to confirm the export
timezone/selection settings, marker and duplicate rules, explain the team
differences, and have the PBI owner review the demonstrated contact-level
comparison plus explicit deferrals for the remaining original criteria.
