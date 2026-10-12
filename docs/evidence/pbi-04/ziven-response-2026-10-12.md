# Ziven's final reply, recorded 2026-10-12 (CS skill list, SLA semantics, scope)

**Date received: 2026-10-12**, supplied by Ian in the working conversation (the full message, opening "Good morning
Ian!"; an earlier relayed summary of it carried only the count of 29 skills). No email date exists; none is assumed.
The "API" checks were run by this branch on 2026-10-12 against the existing discovery setup (credentials not printed or
stored). Sanitised: skill names/IDs/settings and counts only. Supersedes the open questions in
[ziven-response-2026-10-08.md](ziven-response-2026-10-08.md), which stays as the 2026-10-08 snapshot.

## What Ziven stated (owner testimony; not API-verified)

| Topic | Statement |
|---|---|
| Customer Service Team SLA widget skills | The 29 skills listed in Set A below; no Team selections on the SLA widgets |
| Skills added but not selected on either SLA widget | Billing General and "Biling General Spanish" (billing not yet determined as Cardiac or Ortho; CS handles both); 31 skills in total with these |
| ROMTech Service Level widget skill list | **Not supplied** (this message lists the CS widget only) |
| 30% and 100% | Static targets for the colour chart: the colour shows whether the current percentage is above or below the threshold |
| What the SLA counter measures | How quickly a call is **completed**, not how quickly it is answered |
| SLA configuration | Each skill: threshold 90 seconds to completion, goal 90% of calls within the threshold |
| Refusal timeout | Per agent, currently 120 seconds on the Station ID (can be set per agent without Station IDs); Logistics and CS were recently switched to Station IDs |
| Short abandons | Callers who hang up right away: threshold 15 seconds or less; not counted against the SLA |
| Refused interactions | Refused then immediately re-routed and answered by another agent: counted as handled contacts; the refusal event is tracked separately in contact history and does not directly dilute the standard offered-vs-answered Service Level percentage, unless configured in custom reporting |
| Media | Phone calls only for now. Voicemail may be added later; weekend voicemails are handled Monday and would skew SLA aggregates |
| October 1 dashboard SLA results | Not available (not in the subscription) |
| Export timestamps | Adjusted to the time zone of the user exporting; for her, Eastern Time |
| Two-team repeated contact IDs | Only during the end-of-day transition as CS agents clock out and Outplex takes over for the late afternoon/evening; she suggests asking the Customer Service Supervisor (the question text for this item is not in this branch) |

Caveats on those statements: the export timezone is the **exporting user's** setting, so it is Eastern only for exports
made by her; it is not a business-wide setting (the October 6 exact match is what supports Eastern for these files).
The Eastern IANA name is still inferred as `America/New_York`.

## Set A: Ziven's 29 Customer Service Team SLA skills (resolved)

Each name was resolved against the live `/skills` inventory (active and inactive, 2026-10-12). All 29 resolve to exactly
one skill ID; no two names share an ID. Match rule per row: 20 exact; 3 differ only by case/underscore; 2 are the
inventory's 30-character name limit (inventory name is the first 30 characters of hers); 4 are **inferred**
because the words are the same but in a different order (`Order Status Cardiac` is the inventory's `Cardiac Order Status`,
and the same for Ortho and the Spanish variants). Those 4 are the only judgment calls. The last column is
API `contactsOffered` / October 1 export distinct contacts for the Eastern day.

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

Current API settings for all 29: media Phone Call, active, 90 s threshold, 90% goal, short-abandon on at 15 s (29 of 29).
These are **current** values, not October 1 configuration. Ziven's list contains no outbound skill (`CS - Outbound` and
`Outbound` are not in it) and no Logistics skill.

## Set B: intended additions, not selected (kept separate)

| Ziven's name | Match rule | Skill ID | Inventory name | Campaign | API settings |
|---|---|---|---|---|---|
| Billing General | exact | 36302045 | Billing General | Customer Service | 90 s / 90% / short-abandon on, 15 s |
| Biling General Spanish | UNRESOLVED by name | candidate 36302046 (`Billing General Spanish`, spelling corrected: inferred) | | | |

- "Biling General Spanish" has no inventory match under the exact, case/underscore, 30-character or word-order rules.
  `Billing General Spanish` is the near match by correcting one letter; treated as the same skill by inference.
- `Billing General VM` (36302047, Voice Mail) is **excluded**: voicemail is excluded. It is not an addition.
- Neither billing addition is in `Skills.csv` or the October 1 export (0 offered on 2026-10-01 Eastern).

## Full-export population (October 1 export, all departments): not the CS scope

Preserved for the contact reconciliation only. These are the 29 distinct skills in the October 1 export, captured via
the API on 2026-10-06. Each resolves to exactly one API skill ID and all are active in the live `/skills` inventory
(2026-10-12); the 8 also in `Skills.csv` carry the same IDs. Mixed departments (Customer Service, Logistics
Scheduling, Admin, Patient Collections, Patient Support, a test campaign).

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

## API access and fields (read-only, 2026-10-12)

Access was **not blocked**: the existing discovery setup authenticated (credentials not printed or stored) and
returned both endpoints. Sanitised output: [skill-inventory-and-sla-fields-2026-10-12.json](skill-inventory-and-sla-fields-2026-10-12.json).

- `/skills` (isActive=true) returns 80 skills with `skillId`, `skillName`, `campaignName`, `mediaTypeName`, `isActive`,
  `serviceLevelThreshold`, `serviceLevelGoal`, `enableShortAbandon`, `shortAbandonThreshold`, `countShortAbandons`.
  This is a current inventory, not evidence of October 1 configuration.
- `/skills/summary` returns, per skill and requested window, `contactsOffered`, `contactsHandled`, `contactsWithinSLA`,
  `contactsOutOfSLA`, `serviceLevel`, `serviceLevelGoal`, `serviceLevelThreshold`, `abandonCount`, `abandonRate` and others.
  It returns a row for every skill on any date, so presence or zeros prove nothing about retention.

Exploratory numbers for the 29 export-population skills (all departments, not the CS scope), Eastern day 2026-10-01 (`[2026-10-01T04:00Z, 2026-10-02T04:00Z)`), **not a
validation**:

| Check | Result |
|---|---|
| `contactsOffered` equals the export's distinct contacts, per skill | 29 of 29 skills; totals 2,021 and 2,021 |
| `contactsWithinSLA` / `contactsOutOfSLA` summed | 482 / 747 (1,229 together, fewer than the 2,021 offered) |
| `contactsHandled` / `abandonCount` summed | 1,356 / 405 |
| Export-population skills with API settings 90 s, 90%, short-abandon on at 15 s | 20 of 29 |
| Other settings in the export population | 2 skill(s) 60 s/100%/off 15 s, 2 skill(s) 30 s/90%/off 15 s, 2 skill(s) 90 s/90%/off 15 s, 1 skill(s) 90 s/90%/on 90 s, 1 skill(s) 120 s/90%/off 15 s, 1 skill(s) 120 s/90%/on 15 s |

This is a statement about the mixed-department export population only. It is **not** a comparison with the CS
configuration Ziven described, because her CS list is not yet entered; do not read it as a discrepancy. Whether
the dashboard widgets use the per-skill API settings or one widget-level configuration is also not established.

## Checks for Set A on the Eastern day 2026-10-01 (exploratory, not a validation)

| Check | Result |
|---|---|
| API `contactsOffered` equals the export's distinct contacts, per skill | 29 of 29; totals 780 and 780 |
| `contactsHandled` + `abandonCount` | 619 + 161 = 780 (equals offered) |
| `contactsWithinSLA` + `contactsOutOfSLA` | 301 + 472 = 773; 7 offered contacts in neither count |
| API per-skill settings vs Ziven's stated configuration | 29 of 29 equal (90 s, 90%, short-abandon at 15 s) |

The 7-contact gap is **consistent with** her
statement that short abandons are excluded from SLA, but that is a hypothesis: no short-abandon count was retrieved, so
it is not verified. (The wider all-department population has a much larger gap, 792; it is not the CS scope.)

## SLA semantics: still unverified

- Ziven says the counter measures time to **completion**, not time to answer. Whether the API's `contactsWithinSLA` /
  `contactsOutOfSLA` use the same definition (completion vs answer, handling of refusals, short abandons, transfers and
  conferences) has not been checked against API fields. No semantics are assumed from the field names.
- No October 1 dashboard value exists, so nothing can be compared with the API figures. The screenshot values (232/132 and
  153/117) are a live 30-minute view at an unknown time.
- Checking needs a paired live capture (widget and API summary at the same instant, same skills and phone-only scope) or a
  retained historical SLA reference, plus a short-abandon count for the same window.

## Repeated two-team contact IDs and the end-of-day remark

In the October 1 export (times as displayed, Eastern) the three repeated IDs that differ in team and/or agent are: one at
16:40 between `CS - Tier 2 Spanish` and `Outplex CS` (consistent with her transition statement), one at 16:08 with a blank
team on one row, and one at 09:01 within a single team (agent-only). The 09:01 case is a morning repeat with no Outplex
team, so her end-of-day explanation does not cover it as relayed. This is a question for the Customer Service Supervisor,
as she suggests; it does not block the contact comparison, which excludes team and agent from its key.

## Effect on the acceptance table

The current table is in [closure-2026-10-03.md](closure-2026-10-03.md) (section "Current acceptance table, 2026-10-12");
the October 3 table is kept below it as a historical snapshot. **PBI-04 remains open.**
