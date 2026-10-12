"""
Compare a Contact History export with API contact records (PBI-04 closure).

The comparison is only as good as its preconditions, so every one is explicit
and a missing one yields UNRESOLVED, never a quiet MATCH:

  - the grain being compared is stated (`grain`), and both sides use it;
  - every export skill name resolved to a skill ID (no unmatched/ambiguous);
  - the export has no unexplained conflicting repeated IDs (a named rule may explain team/agent
    differences ONLY; it never covers skill, start time or any other compared field, and every variant of a
    repeated ID is still compared with the API record);
  - a trailing '*' on a contact ID is accepted only under a named rule the export itself satisfies;
  - the API fetch is COMPLETE (pagination verified) and covers the window, and returns no contact ID
    twice with a different skill or start time (identical repeats are collapsed and counted; conflicting
    ones are UNRESOLVED, never resolved by taking the first record);
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

from .contact_history import (
    FIELD_LABELS, TEAM_OR_AGENT, ContactRecord, SkillResolution, dedupe_exact, differing_fields, summarize,
)
from .models import ComparisonOutcome, CoverageState

# Named rules. Each id stands for evidence recorded in docs/evidence/pbi-04/ziven-response-2026-10-08.md;
# free text is not accepted, and an unknown id is an error rather than a quiet pass.
REPEAT_RULE_TEAM_OR_AGENT_ONLY = "repeat-differs-in-team-or-agent-only"
MARKER_RULE_CHILD_LEG = "child-leg-master-contact"
REPEAT_RULES = (REPEAT_RULE_TEAM_OR_AGENT_ONLY,)
MARKER_RULES = (MARKER_RULE_CHILD_LEG,)
# Grains the code can truthfully compare: records are keyed by the contact's own ID, so a master interaction,
# routed leg or transfer comparison would be a mislabelled contact comparison.
SUPPORTED_GRAINS = ("contact",)
SCOPE_WINDOW_AS_STATED = "window_as_stated"  # the stated window is not assumed to be a full day
SCOPE_LABELLED_SUBSET = "labelled_subset"


@dataclass(frozen=True)
class ApiContact:
    contact_id: str
    skill_id: str
    start_utc: datetime


@dataclass(frozen=True)
class FetchProvenance:
    """What a live fetch actually did (set by contact_history_source.fetch_contacts). Coverage COMPLETE is derived
    from this, not asserted by a caller. Counts and bounds only: no raw rows, headers or credentials."""

    contract_version: str
    requested_start_utc: str
    requested_end_utc: str
    captured_at_utc: str
    pages: tuple  # one {"skip", "rows", "reported_total"} dict per page fetched
    reported_total: int | None
    rows_fetched: int
    issues: tuple[str, ...]
    filter_scope: str
    date_filter_semantics: str


@dataclass(frozen=True)
class ApiContactFetch:
    records: tuple[ApiContact, ...]
    coverage: CoverageState
    endpoint_path: str
    api_version: str
    captured: bool  # True = a real captured response; False = synthetic fixture (validates code, not the day)
    provenance: FetchProvenance | None = None  # present for a live fetch; None for an offline fixture


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
    conflict_rule: str | None = None
    id_marker_rule: str | None = None
    repeated_ids_explained_by_rule: int = 0
    child_leg_rows: int = 0  # rows marked '*' (counted, not collapsed: each keeps its own ID and master)
    api_exact_repeats_removed: int = 0  # API records identical to an earlier one in ID, skill and start
    api_records_outside_window: int = 0
    subset_label: str | None = None  # set only for an intentional subset comparison
    # What was compared, NOT whether anything was validated: the window exactly as the caller stated it, or an
    # intentional labelled subset. Validation is a separate acceptance status (needs outcome MATCH, a real
    # capture, established grain/timezone and owner acceptance); this field never implies it.
    comparison_scope: str = SCOPE_WINDOW_AS_STATED


def compare_contacts(
    export_records: tuple[ContactRecord, ...] | list[ContactRecord],
    resolution: SkillResolution,
    api: ApiContactFetch | None,
    *,
    window_start_utc: datetime,
    window_end_utc: datetime,
    grain: str | None,
    timestamp_tolerance_seconds: float | None,
    conflict_rule: str | None = None,
    id_marker_rule: str | None = None,
    subset_label: str | None = None,
) -> ContactComparison:
    if conflict_rule is not None and conflict_rule not in REPEAT_RULES:
        raise ValueError(f"unknown repeat rule {conflict_rule!r}; supported: {', '.join(REPEAT_RULES)}")
    if id_marker_rule is not None and id_marker_rule not in MARKER_RULES:
        raise ValueError(f"unknown ID-marker rule {id_marker_rule!r}; supported: {', '.join(MARKER_RULES)}")
    reasons: list[str] = []
    if window_end_utc <= window_start_utc:
        raise ValueError("window end must be after window start")
    if grain is None:
        reasons.append("the report/API grain (contact, routed leg, transfer or master interaction) is not established")
    elif grain not in SUPPORTED_GRAINS:
        reasons.append(
            f"grain {grain!r} is not supported: this comparison keys records by the contact's own ID, so only "
            f"{', '.join(SUPPORTED_GRAINS)} can be compared")
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
    explained = _repeat_conflicts(export_records, conflict_rule, reasons)
    marked = sum(1 for r in export_records if r.is_child_leg)
    if marked and id_marker_rule is None:
        reasons.append(
            f"{marked} export row(s) have a trailing '*' on the contact ID whose meaning is not established; "
            "it is not assumed to be ignorable")
    elif marked or id_marker_rule is not None:
        _check_child_leg_rule(summary, reasons)
    if api is None:
        reasons.append("no API records supplied")
    elif api.coverage is not CoverageState.COMPLETE:
        reasons.append("API fetch coverage is not verified complete (pagination/partial fetch)")
    api_repeats_removed = 0
    if api is not None and api.provenance is not None:
        prov = api.provenance
        if (_parse_iso(prov.requested_start_utc), _parse_iso(prov.requested_end_utc)) != (window_start_utc, window_end_utc):
            reasons.append(
                "the API fetch window recorded in its provenance differs from the comparison window "
                f"({prov.requested_start_utc} to {prov.requested_end_utc})")
        if prov.issues and api.coverage is CoverageState.COMPLETE:
            reasons.append("API fetch claims complete coverage but its provenance lists issues")
    if api is not None:
        # Checked over ALL returned records, in or out of the window, so a conflicting copy cannot hide.
        seen_api: dict[str, set[tuple]] = {}
        for a in api.records:
            variants = seen_api.setdefault(a.contact_id, set())
            if (a.skill_id, a.start_utc) in variants:
                api_repeats_removed += 1
            variants.add((a.skill_id, a.start_utc))
        api_conflicts = sum(1 for v in seen_api.values() if len(v) > 1)
        if api_conflicts:
            reasons.append(
                f"{api_conflicts} API contact ID(s) were returned more than once with a different skill or start "
                "time; the API grain is not one record per contact ID")

    in_window = [r for r in export_records if window_start_utc <= r.start_utc < window_end_utc]
    outside_export = len(export_records) - len(in_window)
    outside_api = 0 if api is None else sum(
        1 for a in api.records if not (window_start_utc <= a.start_utc < window_end_utc))
    if subset_label is None:
        # A full-day comparison cannot silently drop records; an intended subset must say so.
        if outside_export:
            reasons.append(
                f"{outside_export} export row(s) are outside the window and were not compared; use subset_label "
                "for an intentional subset (never full-day validation)")
        if outside_api:
            reasons.append(
                f"{outside_api} API record(s) are outside the window and were not compared; use subset_label "
                "for an intentional subset (never full-day validation)")
    deduped, removed = dedupe_exact(in_window)
    # Every surviving row stays in its ID's variant list; none is dropped for being second.
    variants_by_id: dict[str, list[ContactRecord]] = {}
    for r in deduped:
        variants_by_id.setdefault(r.own_contact_id, []).append(r)
    export_by_id = {cid: rows[0] for cid, rows in variants_by_id.items()}  # representative, for per-skill counts

    base = dict(
        grain=grain, window_start_utc=_iso(window_start_utc), window_end_utc=_iso(window_end_utc),
        export_rows=len(export_records), export_rows_in_window=len(in_window),
        export_rows_outside_window=len(export_records) - len(in_window), export_exact_repeats_removed=removed,
        export_unique_contacts=len(export_by_id), timestamp_tolerance_seconds=timestamp_tolerance_seconds or 0.0,
        api_fetch_is_real_capture=None if api is None else api.captured,
        conflict_rule=conflict_rule, id_marker_rule=id_marker_rule, repeated_ids_explained_by_rule=explained,
        child_leg_rows=marked, api_exact_repeats_removed=api_repeats_removed,
        api_records_outside_window=outside_api, subset_label=subset_label,
        comparison_scope=SCOPE_WINDOW_AS_STATED if subset_label is None else SCOPE_LABELLED_SUBSET,
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
        a = api_by_id[cid]
        # ALL variants of a repeated ID are checked, so an explained difference cannot hide a discrepancy.
        if any(resolution.resolved.get(e.skill_name) != a.skill_id for e in variants_by_id[cid]):
            skill_mismatches += 1
        if any(abs(e.start_utc - a.start_utc) > tolerance for e in variants_by_id[cid]):
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


def _repeat_conflicts(records, rule: str | None, reasons: list[str]) -> int:
    """Classifies repeated raw IDs whose rows differ in some kept field. Returns how many a named rule
    explains. Without the rule all of them are unexplained; with it, only team/agent-only differences are."""
    by_id: dict[str, list[ContactRecord]] = {}
    for r in records:
        by_id.setdefault(r.raw_contact_id, []).append(r)
    explained = 0
    unexplained = 0
    uncovered: set[str] = set()
    for rows in by_id.values():
        if len({r.comparable() for r in rows}) < 2:
            continue
        differing = differing_fields(rows)
        if rule is not None and differing <= TEAM_OR_AGENT:
            explained += 1
        else:
            unexplained += 1
            uncovered |= {FIELD_LABELS.get(f, f) for f in differing} if rule is not None else set()
    if unexplained and rule is None:
        reasons.append(f"{unexplained} repeated contact ID(s) have differing fields and are unexplained")
    elif unexplained:
        reasons.append(
            f"{unexplained} repeated contact ID(s) differ in fields the repeat rule does not cover "
            f"({', '.join(sorted(uncovered))}); the rule explains team/agent differences only")
    return explained


def _check_child_leg_rule(summary, reasons: list[str]) -> None:
    """MARKER_RULE_CHILD_LEG holds only if the export itself agrees: every '*' row has a Master Contact ID
    that is a different contact, no unmarked row does, and no ID appears both ways."""
    if summary.marked_rows_whose_master_is_not_a_different_contact:
        reasons.append(
            f"{summary.marked_rows_whose_master_is_not_a_different_contact} '*' row(s) are not a child leg under the "
            "rule: Master Contact ID is missing or equal to the row's own ID")
    if summary.unmarked_rows_whose_master_is_a_different_contact:
        reasons.append(
            f"{summary.unmarked_rows_whose_master_is_a_different_contact} row(s) have a different Master Contact ID "
            "but are not marked '*', so the child-leg rule does not describe this export")
    if summary.base_ids_seen_both_marked_and_unmarked:
        reasons.append(
            f"{summary.base_ids_seen_both_marked_and_unmarked} contact ID(s) appear both with and without '*'; "
            "the own ID is not unique")


def _parse_iso(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")
