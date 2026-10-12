# Ziven's final reply, recorded 2026-10-12 (SLA settings, scope, skill sets)

**Date received: 2026-10-12**, relayed by Ian in the working conversation. No email date exists; none is assumed.
The verbatim message is not stored in this repository: the points below are Ian's relayed summary of it, and the
checks marked "API" were run by this branch on 2026-10-12. Sanitised: skill names/IDs/settings and counts only.
This supersedes the open questions at the end of [ziven-response-2026-10-08.md](ziven-response-2026-10-08.md), which
stays as the 2026-10-08 snapshot.

## What Ziven confirmed (owner statements)

| Point | Statement |
|---|---|
| Skills currently selected on the dashboard SLA widgets | 29 |
| Intended additions, not yet selected | Billing General and "Biling General Spanish" (two skills) |
| Team filters | None |
| Media | Phone calls only; voicemail excluded |
| Export time | Her Eastern timezone |
| 30% and 100% widget thresholds | Colour thresholds (not SLA targets) |
| Reported SLA configuration | 90 seconds to completion, 90% goal, short abandons of 15 seconds or less excluded |
| Historical October 1 dashboard SLA results | Unavailable |

Not stated: an IANA zone name (Eastern is read as `America/New_York`, consistent with the October 6 exact match, but
not named by her); the list of the 29 selected skills; which campaigns the two widgets select.

## Two separate skill sets

**Set A: the 29 currently selected.** Ziven gave a count, not names. The only 29-skill list this branch holds is the
29 distinct skills in the October 1 export (captured via the API on 2026-10-06), so it is **the candidate list, not a
confirmed copy of the widget selection**. Each of the 29 resolves to exactly one API skill ID; all 29 are present and
active in the live `/skills` inventory (2026-10-12); the 8 that also appear in Ziven's 16-row `Skills.csv` carry the
same IDs. No name is unresolved. The other 21 are resolved by the October 6 capture and the live inventory only, not by
the supplied CSV. Per-skill settings are the API's `serviceLevelThreshold`, `serviceLevelGoal`, `enableShortAbandon`
and `shortAbandonThreshold`.

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

**Set B: intended additions, not selected.**

| Skill ID | Name | Campaign | Media | API SLA settings | Oct 1 offered (API summary) |
|---|---|---|---|---|---:|
| 36302045 | Billing General | Customer Service | Phone Call | 90 s / 90% / short-abandon on, 15 s | 0 |
| 36302046 | Billing General Spanish | Customer Service | Phone Call | 90 s / 90% / short-abandon on, 15 s | 0 |
| 36302047 | Billing General VM | Customer Service | Voice Mail | 185000 s / 90% / short-abandon off | 0 |

- "Biling General Spanish" is not an inventory name; the only near match is `Billing General Spanish`
  (36302046). Treated as the same skill by correcting the spelling: **an inference, to be confirmed**.
- The inventory also has `Billing General VM` (36302047, media Voice Mail). Ziven did not mention it and voicemail
  is excluded from the widgets; confirm it is not an intended addition.
- Neither billing skill is in `Skills.csv` or the October 1 export (0 offered on 2026-10-01 Eastern), so they add no
  October 1 check.

## API access and fields (read-only, 2026-10-12)

Access was **not blocked**: the existing discovery setup authenticated (credentials not printed or stored) and
returned both endpoints. Sanitised output: [skill-inventory-and-sla-fields-2026-10-12.json](skill-inventory-and-sla-fields-2026-10-12.json).

- `/skills` (isActive=true) returns 80 skills with `skillId`, `skillName`, `campaignName`, `mediaTypeName`, `isActive`,
  `serviceLevelThreshold`, `serviceLevelGoal`, `enableShortAbandon`, `shortAbandonThreshold`, `countShortAbandons`.
  This is a current inventory, not evidence of October 1 configuration.
- `/skills/summary` returns, per skill and requested window, `contactsOffered`, `contactsHandled`, `contactsWithinSLA`,
  `contactsOutOfSLA`, `serviceLevel`, `serviceLevelGoal`, `serviceLevelThreshold`, `abandonCount`, `abandonRate` and others.
  It returns a row for every skill on any date, so presence or zeros prove nothing about retention.

Exploratory numbers for the 29 skills, Eastern day 2026-10-01 (`[2026-10-01T04:00Z, 2026-10-02T04:00Z)`), **not a
validation**:

| Check | Result |
|---|---|
| `contactsOffered` equals the export's distinct contacts, per skill | 29 of 29 skills; totals 2,021 and 2,021 |
| `contactsWithinSLA` / `contactsOutOfSLA` summed | 482 / 747 (1,229 together, fewer than the 2,021 offered) |
| `contactsHandled` / `abandonCount` summed | 1,356 / 405 |
| Skills whose API settings are 90 s, 90%, short-abandon on at 15 s | 20 of 29 |
| Other settings among the 29 | 2 skill(s) 60 s/100%/off 15 s, 2 skill(s) 30 s/90%/off 15 s, 2 skill(s) 90 s/90%/off 15 s, 1 skill(s) 90 s/90%/on 90 s, 1 skill(s) 120 s/90%/off 15 s, 1 skill(s) 120 s/90%/on 15 s |

So Ziven's reported configuration holds for 20 of the 29 skills in the API's per-skill settings, not all of them.
Whether the dashboard widgets use the per-skill API settings or one widget-level configuration is not established.

## SLA semantics: still unverified

- Within + out of SLA is 1,229 of 2,021 offered. What accounts for the remaining 792 (short abandons of 15 s or less,
  other abandons, contacts never answered, outbound or special skills) has **not** been checked; no explanation is
  asserted here.
- No dashboard value for October 1 exists (Ziven: unavailable), so there is nothing to compare the API figures with.
  The dashboard values in the screenshots (232 in / 132 out, 153 in / 117 out) are a live 30-minute view at an unknown
  time and cannot be used.
- Reconciling SLA needs a retained historical reference that carries answer/abandon components, or a live
  paired capture (dashboard widget and API summary taken at the same instant with the same skills, media and window).

## Effect on the acceptance table

The current table is in [closure-2026-10-03.md](closure-2026-10-03.md) (section "Current acceptance table, 2026-10-12");
the October 3 table is kept below it as a historical snapshot. **PBI-04 remains open.**
