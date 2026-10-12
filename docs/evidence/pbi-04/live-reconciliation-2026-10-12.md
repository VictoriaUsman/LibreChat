# October 1 Contact History: reconciliation through the production live source (2026-10-12)

Run `9a2f97ddaacb` of `scripts/reconcile_contact_history.py --live`, code revision `fba46b7`
(`contact_history_source.py`, which reuses the existing `CXoneClient`; see the commit message for the design). The
October 6 result came from a throwaway probe script; this one comes from the tested production path and records its own
provenance. Artifacts: [manifest and summary](contact-history-live-2026-10-12/) (counts, hashes, skill names only: no
contact IDs, agent names, phone numbers or credentials). Skill inventory used:
[skill-inventory-export-population-2026-10-12.csv](skill-inventory-export-population-2026-10-12.csv) (the 29 export skills,
names and IDs from the October 6 capture, all present in the live `/skills` inventory on 2026-10-12).

## Inputs and declared rules (all stated before the run)

| Item | Value |
|---|---|
| Reports | `ContactHistory (20|21|22).csv`, read in place (hashes in the manifest); Ian's 2026-10-03 confirmation that together they are the full day |
| Source timezone | `America/New_York` (Ziven 2026-10-12: exports use the exporting user's timezone, Eastern for her; October 6 exact match) |
| Window | `[2026-10-01T04:00:00Z, 2026-10-02T04:00:00Z)`, the Eastern calendar day |
| Grain | `contact` (the only supported grain) |
| Timestamp tolerance | 1 second, declared up front: the export shows whole seconds, the API has sub-second values |
| ID marker rule | `child-leg-master-contact` (accepted only because the export satisfies it: 374/374 `*` rows have a different master, no unmarked row does, no ID appears both ways) |
| Repeat rule | `repeat-differs-in-team-or-agent-only` (explains 3 repeated IDs; covers nothing else) |
| Credentials | Existing discovery credentials read in memory from the gitignored env file via the development-only provider; nothing printed or stored |

## Fetch (derived, not asserted)

`GET /incontactapi/services/v27.0/contacts`, 3 pages (1,000 + 1,000 + 21), reported total 2,021 on every page, 2,021 rows
fetched, no repeated contact ID, no validation issue. Coverage COMPLETE was derived from those checks. Captured
2026-10-12T04:54Z. Filter scope: none (all contacts in the window; skill scope would be client-side).

## Result: MATCH (contact scope only)

| Measure | Value |
|---|---:|
| Export rows / in window / outside window | 2,030 / 2,030 / 0 |
| Exact export repeats removed | 6 |
| Distinct export contacts / API contacts | 2,021 / 2,021 |
| Matched / export-only / API-only | 2,021 / 0 / 0 |
| Skill mismatches / start-time mismatches (1 s tolerance) | 0 / 0 |
| Child-leg rows (kept under their own IDs) | 374 |
| Repeated IDs explained by the team/agent rule | 3 |
| API repeats / API records outside window | 0 / 0 |

## What this does not establish

- **Date-filter semantics:** whether `startDate`/`endDate` select by start time or by completion time is still not
  established (recorded as `unverified` in the manifest). The exact match supports start-time selection for this day but
  does not prove it for other days or for contacts that span the window edge.
- **Not an acceptance-grade result:** `acceptance_grade` is false by design. Owner acceptance, the metric/SLA work and
  the other criteria are separate.
- **Repeatability:** a second run today produces a new capture; the committed manifest/summary are this capture's record.
  The code revision recorded is `fba46b7`; `code_dirty` is true only because unrelated untracked documentation files
  were present (no tracked code file differed).
- **SLA, abandonment, ASA, AHT, duration and every dashboard metric:** not reconciled. A contact match does not validate
  SLA correctness.
- **Tolerance:** 1 second is a precision allowance for whole-second export display, not an agreed business tolerance.
