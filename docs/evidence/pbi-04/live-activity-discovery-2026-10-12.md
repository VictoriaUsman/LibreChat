# Live `/skills/activity` discovery and paired-capture tool (2026-10-12)

Read-only. Credentials never printed or stored; only status codes, field NAMES, counts and timestamps were read. Nothing here
verifies a live source, an SLA calculation or a dashboard mapping: it identifies the candidate and builds the tool that
verification needs. PBI-04, PBI-06 and PBI-07 stay open.

## What was found

Candidate live endpoints probed with the existing discovery setup (`/incontactapi/services/v27.0`):

| Path | Result |
|---|---|
| `/skills/activity` | **200.** Top level: `lastPollTime`, `totalRecords`, `skillActivity[]` (159 rows, one per skill, no repeated skill ID; 130 Phone Call, 26 Voice Mail, 3 Digital). All 29 Customer Service skills present. Row fields include `inSLA`, `outSLA`, `serviceLevel`, `serviceLevelGoal`, `serviceLevelThreshold`, `queueCount`, `skillQueueCount`, `personalQueueCount`, `parkedCount`, `contactsActive`, `earliestQueueTime`, `agentsLoggedIn`, `agentsAvailable`, `agentsIdle`, `agentsWorking`, `agentsACW`, `agentsUnavailable`, `mediaTypeName`, `campaignName`, `isActive`, `isOutbound`, `serverTime` |
| `/agents/states` | 200. Per-agent rows (86) with names, state, team, station and contact fields: **personal data**; not used or stored here. It is the likely source for an agent-state widget but was not examined beyond field names |
| `/skills/summary` | 400 without a date window (it is the historical, window-aggregated endpoint) |
| `/agents/summary`, `/skills/queue-activity`, `/skills/agents`, `/skills/data-queue` | 404/400: not valid on this tenant/version |

Observations (taken at about 02:50 Eastern, so every count was **zero**; the values could not be characterized):

- `lastPollTime` is a top-level source timestamp and advanced between two calls about 90 s apart (06:50:25.973Z then
  06:52:03.313Z), which makes it the only candidate observation time. The cadence is not established.
- The per-row `serverTime` held stale-looking values (dates from March to September) for idle skills, so it is **not**
  used as an observation time.
- `inSLA`/`outSLA` match the widgets' "in SLA / out of SLA" labels by name only. Whether they are a since-midnight or a
  rolling count, whether they exclude short abandons and whether they use completion time are **unverified**.

## What was built

- `src/romtech_mcp/mapping/live_activity.py`: validated read of `/skills/activity` (typed counts, repeated or missing
  skills and count mismatches recorded as issues, never a quiet pass) and per-skill-list sums that name any skill missing
  from the response. Keeps no agent, customer or per-row `serverTime` data. Does not set or imply `live.verified`.
- `scripts/capture_live_activity.py`: repeats the read `--samples` times `--interval-seconds` apart for a skill list and
  writes counts plus the source `lastPollTime` and this machine's receive time. A one-sample live smoke run succeeded
  (29 of 29 skills present, complete).
- `tests/mapping/test_live_activity.py`: 17 tests on synthetic transport. `tests/mapping` total: 219 passing.

## Running the paired observation (needs a person at the dashboard, during business hours)

1. Open the ROMTech Teams dashboard so both SLA widgets and the agent-state widget are visible.
2. Run:

```
python scripts/capture_live_activity.py --skills-json docs/evidence/pbi-04/cs-skill-scope-2026-10-12.json ^
  --credentials-env-file <discovery .env> --samples 5 --interval-seconds 30 --label "CS Team SLA widget, 29 skills" ^
  --output <path>.json
```

3. While it runs, write down, with the local time to the second, each widget value: Customer Service Team SLA in / out /
   percent, and the agent-state counts. Note the widget's "last updated" time.
4. Compare each widget reading with the nearest sample by `lastPollTime`. Questions it answers: do `inSLA`/`outSLA` summed over
   the 29 CS skills equal the widget's in/out; is the percentage `in / (in + out)`; does the count reset at midnight or roll;
   how do `agentsLoggedIn`/`agentsAvailable`/`agentsWorking`/`agentsUnavailable` relate to the widget's states.
5. Record the readings next to the capture file in this folder. Only then can the live source be considered for
   `live.verified`, and only for the fields that agree.

Short-abandon exclusion cannot be settled from these counts alone: it needs a short-abandon count for the same window (from
`/contacts` durations or another verified field) to show the in/out totals leave them out.
