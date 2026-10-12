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

## Recommended decisions (analyst recommendation, **not an approval**)

Each item has a recommended answer and the reason. The boxes stay unticked: only the PBI owner can approve, and nothing
here is recorded as approved. Owner names, ticket numbers and dates are blank on purpose.

| # | Item | Recommendation | Reason |
|---|---|---|---|
| 1 | Reduced scope for closure | **Accept** October 1 contact-level reconciliation of the CS scope as the reconciled historical period | It is real, reproducible and complete for what it covers (2,021 of 2,021, production source, derived coverage). The original wording (every dashboard metric, SLA, baseline) cannot be met with the data that exists, so closing on the original wording is not possible; the choice is reduced scope with named follow-ups, or leave the PBI open indefinitely |
| 2 | Historical SLA | **Approve a documented deferral**, with a paired live observation as the follow-up | The reference does not exist: the dashboard has no October 1 SLA (subscription), and the API's SLA counts have unverified semantics (completion vs answer time, refusals, short abandons). The only way to verify the calculation is a paired same-moment capture of widget and API for the 29 CS skills, phone only, plus a short-abandon count. Passing the criterion on contact matches would be wrong, so it stays "not met", deferred |
| 3 | Baseline rules | **Move to a tracked follow-up** | One day cannot validate baseline; eight weeks was accepted on 2026-10-01 but weighting, holiday and missing-data rules were never given. Those belong with the baseline/compare work, not this PBI |
| 4 | ROMTech Service Level widget; team attribution | **Accept as documented limitations** | Asked for in the final message and not supplied. Out of the CS scope that was reconciled; neither blocks the contact comparison. Do not make non-CS or team-level claims in ROMChat until supplied |
| 5 | Reporting timezone | **Accept `America/New_York`** | Eastern is stated by Ziven; the exact October 1 match (2026-10-06 and 2026-10-12) supports it; only the IANA name was inferred |
| 6 | Name inferences | **Accept** the 4 word-order matches and "Biling General Spanish" = `Billing General Spanish` | Every name resolves to exactly one skill ID and no two names share an ID; the billing near-match differs by one letter and the other candidate (`Billing General VM`) is voicemail, which is excluded |

### What the follow-up item needs (fill in when created; not invented here)

- Title: SLA verification by paired observation (PBI-04 follow-up). Owner: ______  Ticket: ______  Target: ______
- Done when: dashboard widget and API summary captured at the same moment for the 29 CS skills (phone only, same window),
  the within/out-of-SLA counts compared, and short-abandon exclusion confirmed with a short-abandon count.

### Owner decisions (tick only when actually decided)

[ ] 1 accept  [ ] 2 approve deferral  [ ] 3 follow-up  [ ] 4 accept limitations  [ ] 5 accept zone  [ ] 6 accept names
Approved by: ______  Date: ______  Reference: ______

## Closure statement (use only once the above are decided)

> PBI-04 closed under the revised scope accepted by [owner / date / reference]. October 1 Contact History exports were
> reconciled against `GET /contacts` v27.0 for the Eastern day [2026-10-01T04:00Z, 2026-10-02T04:00Z) and the CS skill scope
> (run 9a2f97ddaacb). Historical SLA, remaining dashboard metrics and baseline behaviour remain unvalidated and are tracked
> in [follow-up references]. This closure does not certify SLA calculations, live state or baseline behaviour.
