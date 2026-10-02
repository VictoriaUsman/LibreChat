"""
Compare a Contact History export with API contact records (PBI-04 closure).

The comparison is only as good as its preconditions, so every one is explicit
and a missing one yields UNRESOLVED, never a quiet MATCH:

  - the grain being compared is stated (`grain`), and both sides use it;
  - every export skill name resolved to a skill ID (no unmatched/ambiguous);
  - the export has no unexplained conflicting repeated IDs;
  - the API fetch is COMPLETE (pagination verified) and covers the window;
  - the timestamp tolerance, if any, is supplied by the caller up front.

Counts use zero tolerance. Duration is not compared: its units and lifecycle
meaning are not established, so it is reported as not compared rather than
guessed. Nothing here proves a dashboard metric; it can only show that two
sources agree about which contacts exist, for which skill, and when.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .contact_history import ContactRecord, SkillResolution, dedupe_exact, summarize
from .models import ComparisonOutcome, CoverageState


@dataclass(frozen=True)
class ApiContact:
    contact_id: str
    skill_id: str
    start_utc: datetime


@dataclass(frozen=True)
class ApiContactFetch:
    records: tuple[ApiContact, ...]
    coverage: CoverageState
    endpoint_path: str
    api_version: str
    captured: bool  # True = a real captured response; False = synthetic fixture (validates code, not the day)


@dataclass(frozen=True)
class ContactComparison:
    outcome: ComparisonOutcome
    unresolved_reasons: tuple[str, ...]
    grain: str | None
    window_start_utc: str
    window_end_utc: str
    export_rows: int
    export_rows_in_window: int
    export_rows_outside_window: int
    export_exact_repeats_removed: int
    export_unique_contacts: int
    api_unique_contacts: int
    matched: int
    export_only: int
    api_only: int
    skill_mismatches: int
    start_time_mismatches: int
    timestamp_tolerance_seconds: float
    per_skill: dict[str, dict[str, int]] = field(default_factory=dict)  # skill id -> {export, api}
    duration: str = "not compared: units and lifecycle meaning are not established"
    api_fetch_is_real_capture: bool | None = None
    # Identity lists for LOCAL, access-controlled artifacts only; never written into committed evidence.
    export_only_ids: tuple[str, ...] = ()
    api_only_ids: tuple[str, ...] = ()


def compare_contacts(
    export_records: tuple[ContactRecord, ...] | list[ContactRecord],
    resolution: SkillResolution,
    api: ApiContactFetch | None,
    *,
    window_start_utc: datetime,
    window_end_utc: datetime,
    grain: str | None,
    timestamp_tolerance_seconds: float | None,
    overlap_rule_documented: bool = False,
    id_marker_explained: bool = False,
) -> ContactComparison:
    reasons: list[str] = []
    if window_end_utc <= window_start_utc:
        raise ValueError("window end must be after window start")
    if grain is None:
        reasons.append("the report/API grain (contact, routed leg, transfer or master interaction) is not established")
    if timestamp_tolerance_seconds is None:
        reasons.append("no timestamp tolerance was declared up front (use 0 for exact)")
    if timestamp_tolerance_seconds is not None and timestamp_tolerance_seconds < 0:
        raise ValueError("timestamp tolerance must be >= 0")
    tolerance = timedelta(seconds=timestamp_tolerance_seconds or 0)
    if not resolution.complete:
        reasons.append(
            f"{len(resolution.unmatched)} skill name(s) unmatched and {len(resolution.ambiguous)} ambiguous "
            "against the skill inventory")
    summary = summarize(list(export_records))
    if summary.conflicting_repeated_ids and not overlap_rule_documented:
        reasons.append(f"{summary.conflicting_repeated_ids} repeated contact ID(s) have differing fields and are unexplained")
    marked = sum(1 for r in export_records if r.id_marker)
    if marked and not id_marker_explained:
        reasons.append(
            f"{marked} export row(s) have a trailing '*' on the contact ID whose meaning is not established; "
            "it is not assumed to be ignorable")
    if api is None:
        reasons.append("no API records supplied")
    elif api.coverage is not CoverageState.COMPLETE:
        reasons.append("API fetch coverage is not verified complete (pagination/partial fetch)")

    in_window = [r for r in export_records if window_start_utc <= r.start_utc < window_end_utc]
    deduped, removed = dedupe_exact(in_window)
    export_by_id: dict[str, ContactRecord] = {}
    for r in deduped:
        export_by_id.setdefault(r.contact_id, r)  # base ID: marker meaning is explained or already UNRESOLVED

    base = dict(
        grain=grain, window_start_utc=_iso(window_start_utc), window_end_utc=_iso(window_end_utc),
        export_rows=len(export_records), export_rows_in_window=len(in_window),
        export_rows_outside_window=len(export_records) - len(in_window), export_exact_repeats_removed=removed,
        export_unique_contacts=len(export_by_id), timestamp_tolerance_seconds=timestamp_tolerance_seconds or 0.0,
        api_fetch_is_real_capture=None if api is None else api.captured,
    )
    if api is None or api.coverage is not CoverageState.COMPLETE or reasons:
        # Counts that need both sides are meaningless without them; report what is known.
        return ContactComparison(
            outcome=ComparisonOutcome.UNRESOLVED, unresolved_reasons=tuple(reasons),
            api_unique_contacts=0 if api is None else len({a.contact_id for a in api.records}),
            matched=0, export_only=0, api_only=0, skill_mismatches=0, start_time_mismatches=0, **base,
        )

    api_by_id: dict[str, ApiContact] = {}
    for a in api.records:
        if window_start_utc <= a.start_utc < window_end_utc:
            api_by_id.setdefault(a.contact_id, a)
    matched_ids = sorted(set(export_by_id) & set(api_by_id))
    export_only = sorted(set(export_by_id) - set(api_by_id))
    api_only = sorted(set(api_by_id) - set(export_by_id))
    skill_mismatches = start_mismatches = 0
    for cid in matched_ids:
        e, a = export_by_id[cid], api_by_id[cid]
        if resolution.resolved.get(e.skill_name) != a.skill_id:
            skill_mismatches += 1
        if abs(e.start_utc - a.start_utc) > tolerance:
            start_mismatches += 1
    per_skill: dict[str, Counter] = {}
    for e in export_by_id.values():
        per_skill.setdefault(resolution.resolved[e.skill_name], Counter())["export"] += 1
    for a in api_by_id.values():
        per_skill.setdefault(a.skill_id, Counter())["api"] += 1
    counts_agree = all(c.get("export", 0) == c.get("api", 0) for c in per_skill.values())
    clean = counts_agree and not (export_only or api_only or skill_mismatches or start_mismatches)
    outcome = ComparisonOutcome.MATCH if clean else ComparisonOutcome.MISMATCH
    return ContactComparison(
        outcome=outcome, unresolved_reasons=(), api_unique_contacts=len(api_by_id), matched=len(matched_ids),
        export_only=len(export_only), api_only=len(api_only), skill_mismatches=skill_mismatches,
        start_time_mismatches=start_mismatches,
        per_skill={k: {"export": v.get("export", 0), "api": v.get("api", 0)} for k, v in sorted(per_skill.items())},
        export_only_ids=tuple(export_only), api_only_ids=tuple(api_only), **base,
    )


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")
