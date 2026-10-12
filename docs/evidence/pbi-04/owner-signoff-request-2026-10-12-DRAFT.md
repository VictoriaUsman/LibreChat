# PBI-04: owner sign-off request (DRAFT, nothing approved)

Prepared 2026-10-12 for the PBI owner. **No approval, owner name, ticket number or date below has been given or filled
in.** PBI-04 is open. Evidence index: [closure-2026-10-03.md](closure-2026-10-03.md) (current acceptance table at the top),
[live-reconciliation-2026-10-12.md](live-reconciliation-2026-10-12.md), [ziven-response-2026-10-12.md](ziven-response-2026-10-12.md).
Ziven's final reply has been received; no further input is being requested from her.

## What was reconciled

October 1, 2026, Eastern day, contact scope only: 2,021 of 2,021 distinct contacts, skills and start times agree between
the three Contact History exports and the live `/contacts` API (production source, derived complete coverage, run
`9a2f97ddaacb`, revision `fba46b7`). The per-skill `contactsOffered` from `/skills/summary` equals the export for all 29
skills. Ziven's 29 CS Team SLA skills are resolved to API IDs and their current per-skill SLA settings equal her stated
configuration (90 s, 90%, short abandons of 15 s or less excluded) for all 29.

## What was not reconciled

| Original criterion | State | Why |
|---|---|---|
| Historical SLA reconciled against the dashboard | **Not done** | No October 1 dashboard SLA exists (not in the subscription). API SLA counts exist (`contactsWithinSLA`, `contactsOutOfSLA`); their semantics are unverified (Ziven: completion time, not answer time) and 7 of 780 offered CS contacts are in neither count |
| Remaining dashboard metrics | Not done | Agent state counts and agent status are live-only; mapping is candidate-only |
| ROMTech Service Level widget scope | Not supplied | Skill list asked for, not provided |
| Team attribution rule | Not given | Referred to the Customer Service Supervisor |
| Baseline weighting, holiday, missing-data rules | Open | Eight weeks accepted only |
| Date-filter semantics of `/contacts` (start vs completion) | Unverified | Exact match supports start time for this day only |
| Inventory count discrepancy (83/85 vs live 80 active) | Not explained | |

## Decisions requested from the PBI owner (tick only when actually decided)

1. **Reduced scope for closure:** accept October 1 contact-level reconciliation of the CS scope as the reconciled
   historical period, with SLA, remaining metrics and baseline deferred. Decision: [ ] accept  [ ] reject  [ ] other: ______
2. **Historical SLA deferral.** Required if SLA cannot be reconciled. Proposed route: a paired live observation (dashboard
   widget and API summary captured at the same moment for the 29 CS skills, phone only, same window), plus a short-abandon
   count, to verify the SLA calculation going forward. Owner: ______  Follow-up ticket: ______  Target date: ______
   Decision: [ ] approve deferral  [ ] do not defer
3. **Baseline rules:** [ ] in scope for PBI-04 (state the rules)  [ ] moved to follow-up (owner/ticket: ______)
4. **ROMTech Service Level widget and team attribution:** accept as documented limitations [ ] / other: ______
5. **Timezone:** accept `America/New_York` as the production reporting zone [ ]
6. **Name inferences to accept:** 4 skill names matched by word order, and "Biling General Spanish" matched by correcting one
   letter (both listed in the evidence).

## Closure statement (use only once the above are decided)

> PBI-04 closed under the revised scope accepted by [owner / date / reference]. October 1 Contact History exports were
> reconciled against `GET /contacts` v27.0 for the Eastern day [2026-10-01T04:00Z, 2026-10-02T04:00Z) and the CS skill scope
> (run 9a2f97ddaacb). Historical SLA, remaining dashboard metrics and baseline behaviour remain unvalidated and are tracked
> in [follow-up references]. This closure does not certify SLA calculations, live state or baseline behaviour.
