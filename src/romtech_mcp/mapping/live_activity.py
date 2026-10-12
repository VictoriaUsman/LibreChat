"""
Read-only capture of the live `GET /skills/activity` endpoint for PAIRED dashboard/API observations (PBI-04 SLA
verification, PBI-06 live-source verification).

Observed 2026-10-12 (docs/evidence/pbi-04/live-activity-discovery-2026-10-12.md): the endpoint returns one row per skill
(159 rows, all 29 Customer Service skills present) with `inSLA`, `outSLA`, queue counts and agent counts, plus a top-level
`lastPollTime`. It is NOT verified here that these fields mean what the dashboard widgets show, that `inSLA`/`outSLA` are a
since-midnight or rolling count, or which queue/agent field maps to which widget figure: that is exactly what a paired
capture is for. Nothing in this module sets or implies `live.verified`.

The per-row `serverTime` field held stale-looking values (months old) for idle skills, so it is recorded as-is but never used
as the observation time; `lastPollTime` is the only candidate observation timestamp.

Counts and timestamps only: no agent, customer or credential data is read or kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from romtech_mcp.cxone.errors import CXoneError

PATH_TEMPLATE = "/incontactapi/services/{version}/skills/activity"
API_VERSION = "v27.0"
COUNT_FIELDS = (
    "inSLA", "outSLA", "queueCount", "skillQueueCount", "personalQueueCount", "parkedCount", "contactsActive",
    "agentsLoggedIn", "agentsAvailable", "agentsIdle", "agentsWorking", "agentsACW", "agentsUnavailable",
)


@dataclass(frozen=True)
class ActivityRow:
    skill_id: str
    media_type: str
    counts: tuple  # ((field, int), ...) for COUNT_FIELDS
    service_level: int | None


@dataclass(frozen=True)
class ActivityCapture:
    captured_at_utc: str  # when THIS machine received the response
    request_started_utc: str
    last_poll_time: str | None  # the source's own poll timestamp (top level), verbatim
    total_records: int | None
    rows: tuple[ActivityRow, ...]
    issues: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.issues and self.total_records == len(self.rows)


def _nonneg_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def fetch_activity(client, *, now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> ActivityCapture:
    """One read of `/skills/activity`, validated. Any problem is recorded in `issues` (never a silent partial)."""
    started = now_utc()
    issues: list[str] = []
    try:
        response = await client.get(PATH_TEMPLATE.format(version=API_VERSION))
    except CXoneError as exc:
        return ActivityCapture(_iso(now_utc()), _iso(started), None, None, (), (f"fetch_failed: {exc!r}",))
    received = now_utc()
    if response.status_code != 200:
        return ActivityCapture(_iso(received), _iso(started), None, None, (), (f"http_status_{response.status_code}",))
    try:
        body = response.json()
    except ValueError:
        return ActivityCapture(_iso(received), _iso(started), None, None, (), ("not_json",))
    rows_raw = body.get("skillActivity") if isinstance(body, dict) else None
    if not isinstance(rows_raw, list):
        return ActivityCapture(_iso(received), _iso(started), None, None, (), ("missing_skillActivity_array",))
    total = body.get("totalRecords")
    if not _nonneg_int(total):
        issues.append("missing_or_invalid_totalRecords")
        total = None
    poll = body.get("lastPollTime")
    if not isinstance(poll, str) or not poll:
        issues.append("missing_lastPollTime")
        poll = None
    rows: list[ActivityRow] = []
    seen: set[str] = set()
    for raw in rows_raw:
        sid = None if not isinstance(raw, dict) or isinstance(raw.get("skillId"), bool) else raw.get("skillId")
        if not isinstance(sid, int):
            issues.append("row_without_integer_skillId")
            continue
        key = str(sid)
        if key in seen:
            issues.append("repeated_skillId")
            continue
        seen.add(key)
        counts = []
        for f in COUNT_FIELDS:
            v = raw.get(f)
            if not _nonneg_int(v):
                issues.append(f"skill_row_invalid_{f}")
                v = 0
            counts.append((f, v))
        sl = raw.get("serviceLevel")
        rows.append(ActivityRow(key, str(raw.get("mediaTypeName")), tuple(counts), sl if _nonneg_int(sl) else None))
    if total is not None and total != len(rows):
        issues.append(f"row_count_{len(rows)}_differs_from_totalRecords_{total}")
    return ActivityCapture(_iso(received), _iso(started), poll, total, tuple(rows), tuple(sorted(set(issues))))


def summarize(capture: ActivityCapture, skill_ids: tuple[str, ...]) -> dict:
    """Sums of each count over the requested skills, with the skills that were not in the response named, so a missing
    skill is visible rather than counted as zero."""
    wanted = set(skill_ids)
    present = {r.skill_id: r for r in capture.rows if r.skill_id in wanted}
    totals = {f: sum(dict(r.counts)[f] for r in present.values()) for f in COUNT_FIELDS}
    return {
        "skills_requested": len(wanted), "skills_present": len(present),
        "skills_missing": sorted(wanted - set(present)), "totals": totals,
        "in_plus_out_sla": totals["inSLA"] + totals["outSLA"],
        "sla_percent_from_counts": (None if totals["inSLA"] + totals["outSLA"] == 0
                                    else round(100 * totals["inSLA"] / (totals["inSLA"] + totals["outSLA"]), 2)),
    }
