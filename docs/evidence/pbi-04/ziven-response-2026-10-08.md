# Ziven's reply on the `*` marker, repeated IDs and the two SLA counters (2026-10-08)

Source: Ziven's written reply to Ian's four questions, plus three dashboard screenshots (the widget list and the two
widget settings panels). The screenshots show agent names and are **not** copied into this repository; only widget
settings and totals are transcribed below. Contact IDs and agent names Ziven cited are deliberately left out (same
sanitisation rule as the rest of this folder).

Status of everything below: **Ziven's statements are owner testimony; the "checked against the export" figures are
read-only counts from the three October 1 CSVs (`ContactHistory (20|21|22).csv`) made on 2026-10-08.** Nothing here is
API-verified, nothing changes a confirmation flag, and PBI-04 stays open.

## 1. The trailing `*` marker

Ziven: when a call results in another leg being created within the call (her example: a conference call that was
transferred, spawning another leg), the new leg is a Child Contact ID shown with a trailing `*`. The child has its own
number, distinct from the parent's.

| Check against the export | Result |
|---|---|
| Rows with a trailing `*` | 374 rows (371 distinct IDs) |
| Marked rows whose `Master Contact ID` differs from their own ID | 374 of 374 |
| Marked rows whose master is another contact present in the export | 374 of 374 (269 distinct masters) |
| Unmarked rows whose `Master Contact ID` equals their own ID | 1,656 of 1,656; no unmarked row has a different master |
| Her cited child row: master equals her cited parent, not itself | yes |
| Marked IDs that also appear unmarked in the export | 0 (no collision between `X` and `X*` here) |

Consequences:

- In this export, `*` is exactly "child leg": `Master Contact ID` is the parent and the marker never appears on a
  parent. That supports a rule of the form *trailing `*` is a display flag on a child leg; the unmarked number is the
  contact's own ID; the parent is the `Master Contact ID` column*. It agrees with the October 6 live result (stripping
  the marker gave an exact ID match with the API).
- Her statement does **not** say a child shares the parent's ID, so stripping `*` must never be treated as
  "collapse to the parent". The earlier live note that marked contacts carried several transfer labels, including
  `None`, is not contradicted, but the API's transfer field was not compared with the master column.
- Not yet verified: that the API exposes a parent/master field matching the export's, and that the rule holds on
  other days.
- Code (2026-10-12): `--id-marker-rule` now accepts only the named rule `child-leg-master-contact`. The rule is
  accepted only if the export itself satisfies it (every `*` row has a Master Contact ID that is a different contact,
  no unmarked row has one, no ID appears both ways); otherwise the comparison is UNRESOLVED. Records keep both the
  contact's own ID and the Master Contact ID; a child is never collapsed into its parent. On the October 1 files the
  three checks report 0 violations.

## 2. Two rows with the same Contact ID, different teams

Ziven: when an agent refuses a routed call, two identical contact IDs are created, one for each team (her examples: a
refusal followed by routing to another team, and a refusal followed by voicemail).

| Repeated-ID class in the export (9 IDs) | Count | Covered by her explanation? |
|---|---:|---|
| Identical in every column | 6 (2 inside file 20, 4 across files 20 and 21, 3 of them marked IDs) | No. A refusal gives different teams or agents; these look like export overlap |
| Differ in Agent and Team | 2 | **Yes**, this is the mechanism she describes |
| Differ in Agent only (same Team) | 1 | Not stated by her. Plausibly a refusal inside one team; needs confirmation |

Both IDs she cited are repeated IDs in the export. The importer used to ignore the Agent column, which is why the
earlier closure notes counted "seven exact repeats and two Team-only differences": the seven included the Agent-only
repeat, and the "Team-only" pair actually differs in Agent as well. The importer now reads the Agent cell only as an
opaque per-run token (no name is kept or written anywhere), so a repeat is "exact" only if every kept field including
the agent matches. Re-run on the same three files (2026-10-12): 6 exact repeats (2 within a file, 4 across files),
1 repeat that differs only in agent, 3 conflicting repeated IDs (all three differ only in team and/or agent). The
October 3 notes keep their original wording as a historical snapshot.

Code (2026-10-12): the named rule `repeat-differs-in-team-or-agent-only` explains repeats that differ in team and/or
agent and nothing else. It never covers skill, start time or any other compared field, and every variant of a repeated
ID is compared with the API record, so a documented rule can no longer produce a MATCH over a conflicting skill. Her
statement explains why two rows exist; it does not say which row is the contact's team of record, so team is not
compared at all.

## 3. Eastern-day match

Ziven's reply to the exact Eastern-day match is "excellent for a perfect match". She did not state the export's
configured timezone, so the export timezone is still established by the data (October 6 live comparison), not by an
owner confirmation. If that confirmation is wanted, ask for the report's timezone setting.

## 4. The two SLA counters

Ziven: the "ROMTech Teams Dashboard" has two SLA counters: ROMTech as a whole (everyone in CXone outside the CS
department) and Customer Service Team SLA (the CS teams only). Both check against the skills in the CSV she supplied,
and each can have its own filters.

Transcribed from the screenshots (dashboard "last updated 12:03 PM"; the date and timezone of the capture are not
shown):

| Setting | ROMTech Service Level | Customer Service Team SLA |
|---|---|---|
| Campaigns | 2 selected | 1 selected |
| ACD skills | 29 selected | 29 selected |
| Media types | Phone Call | 9 of 9 selected |
| Trending intervals / duration | 24 intervals / 30 minutes | 24 intervals / 30 minutes |
| Threshold | 30% | 100% |
| Displayed in SLA / out of SLA / percent | 232 / 132 / 64% | 153 / 117 / 57% |

What does not line up, so these counters are **not** reconciled:

1. **Skill counts.** Both widgets select 29 skills. The supplied `Skills.csv` has 16 rows across 5 campaigns (only 8 of
   its skills resolve against the export's skills). The export has 29 distinct skills, which matches the widgets'
   count but not the CSV's. "Skills in the CSV" and "29 selected" cannot both describe the same list. The two widgets
   also select the same number of skills although one is meant to exclude CS; whether they select the same 29 or
   differ only by campaign is not visible.
2. **Media types.** The export is phone only (2,030 of 2,030 rows). The ROMTech widget is phone-only; the CS widget
   includes all nine media types, so its population is wider than any phone-contact list.
3. **Population.** The export spans CS teams and non-CS teams (including a department scheduling team and 657 rows
   with a blank team), so on its own it is neither widget's population.
4. **Window.** A 30-minute trending duration with 24 intervals, captured at an unknown date and time, is not the
   October 1 full day. A live snapshot cannot be compared with a historical export.
5. **Semantics.** The panels show "Threshold 30%" and "100%". The per-skill service-level time threshold and goal
   percentage are in `Skills.csv` (Service Level Threshold / Goal). What the panel's percentage controls, and exactly
   what counts as "in SLA" (answered within N seconds, abandons, short abandons), is not stated.
6. Contact-level agreement does not validate SLA: the export has no queue, answer or abandon components.

Questions for Ziven before any SLA validation:

- Which skill list is each widget filtered to: the 29, or the 16 in the CSV?
- Which campaigns are selected in each widget?
- What does "in SLA" count, and what do the 30% and 100% thresholds mean?
- Can a historical (October 1) view of either counter be produced, and over which window and timezone?

## Effect on the PBI-04 acceptance table

| Criterion | Change |
|---|---|
| Grain, `*` marker meaning | Marker meaning now supported by owner statement and 374/374 export rows; the rule still has to be encoded and API-verified |
| Two conflicting repeats | Mechanism explained for 2 of the 3 non-exact repeats; Agent-only repeat unconfirmed; merge rule still to be written |
| SLA thresholds and semantics | Still `proposed deferral`: two counters identified, definitions not established, populations do not line up |
| Reviewed with Ziven | Partly done (this reply); not a sign-off |
