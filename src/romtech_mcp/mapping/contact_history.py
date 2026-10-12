"""
Contact History CSV export importer and analysis (PBI-04 closure).

Reads the report exports in place and keeps ONLY what a reconciliation needs:
contact/master IDs, media type, skill name, team, start time and the raw
duration text. Telephone fields and dispositions are never read. The Agent
column is read only to form an opaque, per-import salted token so that two rows
for one contact can be told apart without the name being kept: the token is
random between runs, is never written to evidence, and cannot be reversed to a
name. Nothing downstream (logs, manifests, evidence) can leak an agent name.

Nothing here decides what a "contact offered" or "contact handled" is. The
export's grain (contact, routed leg, transfer or master interaction) has to be
established separately; `summarize` just reports the counts the file supports.
Repeated IDs are classified, never silently dropped: exact repeats may be
removed ONLY through `dedupe_exact` under a stated export-overlap rule (with an
audit count); repeats whose fields differ stay flagged as conflicts.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REQUIRED_HEADERS = ("Contact ID", "Master Contact ID", "Media Type", "Skill", "Start Time:", "Duration")
_OPTIONAL_HEADERS = ("Team",)

# Parsed explicitly (never locale/day-month guessing): "10/1/2026 11:46:14 PM".
_START_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4}) (\d{1,2}):(\d{2}):(\d{2}) (AM|PM)$")


class ContactHistoryError(ValueError):
    """A file/row problem. Messages carry the file basename and line only,
    never a cell value (cells can hold personal data)."""


@dataclass(frozen=True)
class ContactRecord:
    source_file: str  # basename
    row_number: int  # 1-based data row (header excluded)
    contact_id: str  # digits only
    id_marker: str  # "*" if the export printed a trailing asterisk on the ID; its meaning is NOT established
    master_contact_id: str
    media_type: str
    skill_name: str  # raw, as exported
    team: str
    start_local: datetime  # naive: the export's displayed wall clock
    start_utc: datetime  # start_local interpreted in the declared source timezone
    duration_text: str  # retained verbatim: units/meaning not established
    agent_token: str = ""  # opaque per-import token of the Agent cell ("" = absent); equality only, never a name

    @property
    def own_contact_id(self) -> str:
        """The contact's own ID (digits only). A child leg has its own ID; it is never collapsed into the
        parent's, which is `master_contact_id`."""
        return self.contact_id

    @property
    def is_child_leg(self) -> bool:
        """True when the export printed the trailing '*'. Whether that is a child leg is a rule, not an
        assumption: see contact_history_reconcile.MARKER_RULE_CHILD_LEG and its evidence."""
        return bool(self.id_marker)

    @property
    def raw_contact_id(self) -> str:
        """The ID exactly as exported (digits plus any marker). Distinct raw IDs are what the
        export's own row identity is; whether `123*` and `123` are one contact is not established."""
        return self.contact_id + self.id_marker

    def selected_fields(self) -> tuple:
        """Every field this importer keeps except the agent token: repeats equal on these but not on the
        agent are repeats across SELECTED fields only, not exact repeats of the exported row."""
        return (self.raw_contact_id, self.master_contact_id, self.media_type, self.skill_name, self.team,
                self.start_utc, self.duration_text)

    def comparable(self) -> tuple:
        """Fields that must agree for two rows to be an EXACT repeat (selected fields plus the agent)."""
        return self.selected_fields() + (self.agent_token,)


@dataclass(frozen=True)
class FileSummary:
    basename: str
    sha256: str
    rows: int
    distinct_contact_ids: int


@dataclass(frozen=True)
class ContactHistoryImport:
    records: tuple[ContactRecord, ...]
    files: tuple[FileSummary, ...]
    source_timezone: str


def parse_start_time(text: str) -> datetime:
    m = _START_RE.match(text.strip())
    if not m:
        raise ValueError("start time is not in the M/D/YYYY h:mm:ss AM|PM format")
    month, day, year, hour, minute, second, meridiem = m.groups()
    hour_i = int(hour)
    if not 1 <= hour_i <= 12:
        raise ValueError("hour out of range")
    hour24 = hour_i % 12 + (12 if meridiem == "PM" else 0)
    return datetime(int(year), int(month), int(day), hour24, int(minute), int(second))


def to_utc(local: datetime, zone: ZoneInfo) -> datetime:
    """Interprets a naive wall-clock time in `zone`. A nonexistent (spring-forward) or ambiguous
    (fall-back) local time is rejected, never resolved by inventing a fold."""
    first = local.replace(tzinfo=zone, fold=0)
    second = local.replace(tzinfo=zone, fold=1)
    # Gap first: inside a spring-forward gap the two folds ALSO have different offsets.
    if first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != local:
        raise ValueError("local time does not exist (DST gap)")
    if first.utcoffset() != second.utcoffset():
        raise ValueError("local time is ambiguous (repeated hour)")
    return first.astimezone(timezone.utc)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_contact_history(paths: list[Path], *, source_timezone: str) -> ContactHistoryImport:
    """`source_timezone` is REQUIRED and explicit (use "UTC" only when that is what is being
    asserted); it is never defaulted."""
    if not paths:
        raise ContactHistoryError("no report files given")
    try:
        zone = ZoneInfo(source_timezone)
    except Exception:
        raise ContactHistoryError(f"unknown source timezone {source_timezone!r}") from None
    records: list[ContactRecord] = []
    summaries: list[FileSummary] = []
    salt = os.urandom(16)  # per import, never stored: tokens are comparable within a run only

    def agent_token(text: str) -> str:
        normalized = " ".join(text.split()).casefold()
        return hmac.new(salt, normalized.encode("utf-8"), "sha256").hexdigest()[:12] if normalized else ""

    for path in paths:
        name = path.name
        file_records: list[ContactRecord] = []
        try:
            handle = path.open(encoding="utf-8-sig", newline="")
        except OSError:
            raise ContactHistoryError(f"{name}: cannot be opened") from None
        with handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                raise ContactHistoryError(f"{name}: file is empty") from None
            index = {h.strip(): i for i, h in enumerate(header) if h.strip()}
            missing = [h for h in REQUIRED_HEADERS if h not in index]
            if missing:
                raise ContactHistoryError(f"{name}: missing required column(s): {', '.join(missing)}")
            for row_number, row in enumerate(reader, start=1):
                if not any(c.strip() for c in row):
                    continue  # blank line
                if len(row) != len(header):
                    raise ContactHistoryError(
                        f"{name}: data row {row_number} has {len(row)} fields, expected {len(header)}")

                def cell(column: str) -> str:
                    return row[index[column]].strip() if column in index else ""

                contact_id, master = cell("Contact ID"), cell("Master Contact ID")
                marker = "*" if contact_id.endswith("*") else ""
                contact_id = contact_id[: len(contact_id) - len(marker)]
                if not contact_id.isdigit():
                    raise ContactHistoryError(f"{name}: data row {row_number}: contact ID is missing or not numeric")
                if master and not master.isdigit():
                    raise ContactHistoryError(f"{name}: data row {row_number}: master contact ID is not numeric")
                if not cell("Skill"):
                    raise ContactHistoryError(f"{name}: data row {row_number}: skill is empty")
                try:
                    local = parse_start_time(cell("Start Time:"))
                    utc = to_utc(local, zone)
                except ValueError as exc:
                    raise ContactHistoryError(f"{name}: data row {row_number}: start time rejected ({exc})") from None
                file_records.append(ContactRecord(
                    source_file=name, row_number=row_number, contact_id=contact_id, id_marker=marker, master_contact_id=master,
                    media_type=cell("Media Type"), skill_name=cell("Skill"), team=cell("Team"),
                    start_local=local, start_utc=utc, duration_text=cell("Duration"),
                    agent_token=agent_token(cell("Agent")),
                ))
        summaries.append(FileSummary(
            basename=name, sha256=file_sha256(path), rows=len(file_records),
            distinct_contact_ids=len({r.raw_contact_id for r in file_records}),
        ))
        records.extend(file_records)
    return ContactHistoryImport(records=tuple(records), files=tuple(summaries), source_timezone=source_timezone)


# ----------------------------------------------------------------------------- analysis
@dataclass(frozen=True)
class SkillCount:
    skill_name: str
    rows: int
    distinct_contacts: int


@dataclass(frozen=True)
class ContactHistorySummary:
    raw_rows: int
    distinct_contact_ids: int
    distinct_master_contact_ids: int
    exact_repeat_rows: int  # rows identical to an earlier row in EVERY kept field including the agent token
    exact_repeats_within_a_file: int
    exact_repeats_across_files: int
    repeated_ids_total: int  # contact IDs that appear more than once
    conflicting_repeated_ids: int  # repeated IDs whose rows differ in some compared field
    conflict_fields: dict[str, int]  # which fields differ -> number of conflicting IDs
    masters_with_multiple_contacts: int
    contacts_under_multiple_skills: int
    media_types: dict[str, int]
    per_skill: tuple[SkillCount, ...]
    earliest_start_utc: str | None
    latest_start_utc: str | None
    sum_of_per_skill_distinct_contacts: int  # may exceed distinct_contact_ids; never a global count
    marked_id_rows: int  # rows whose exported ID carries a trailing "*" (meaning not established)
    distinct_base_contact_ids: int  # digits only, marker ignored
    base_ids_seen_both_marked_and_unmarked: int
    shared_contact_ids_between_files: dict[str, int] = field(default_factory=dict)  # "a|b" -> count
    repeats_differing_only_in_agent: int = 0  # repeat rows equal in every selected field but not the agent
    repeated_ids_differing_only_in_team_or_agent: int = 0
    marked_rows_whose_master_is_not_a_different_contact: int = 0  # '*' rows with no master or master == own ID
    unmarked_rows_whose_master_is_a_different_contact: int = 0  # unmarked rows that look like child legs
    rows_with_agent_token: int = 0  # 0 means the Agent column was absent or empty, so agent differences are invisible


_FIELDS = ("id_marker", "master_contact_id", "media_type", "skill_name", "team", "start_utc", "duration_text",
           "agent_token")
FIELD_LABELS = {"agent_token": "agent"}
TEAM_OR_AGENT = frozenset({"team", "agent_token"})


def differing_fields(rows: list[ContactRecord]) -> frozenset[str]:
    """Names (attribute names) of the kept fields that are not identical across `rows`."""
    return frozenset(f for f in _FIELDS if len({getattr(r, f) for r in rows}) > 1)


def summarize(records: tuple[ContactRecord, ...] | list[ContactRecord]) -> ContactHistorySummary:
    by_id: dict[str, list[ContactRecord]] = defaultdict(list)
    for r in records:
        by_id[r.raw_contact_id].append(r)
    markers_by_base: dict[str, set[str]] = defaultdict(set)
    for r in records:
        markers_by_base[r.contact_id].add(r.id_marker)
    seen_exact: dict[tuple, ContactRecord] = {}
    seen_selected: set[tuple] = set()
    exact_within = exact_across = agent_only = 0
    for r in records:
        key = r.comparable()
        if key in seen_exact:
            if seen_exact[key].source_file == r.source_file:
                exact_within += 1
            else:
                exact_across += 1
        else:
            if r.selected_fields() in seen_selected:
                agent_only += 1
            seen_exact[key] = r
            seen_selected.add(r.selected_fields())
    conflicts = team_or_agent_only = 0
    conflict_fields: Counter[str] = Counter()
    for rows in by_id.values():
        if len({r.comparable() for r in rows}) > 1:
            conflicts += 1
            differing = differing_fields(rows)
            team_or_agent_only += differing <= TEAM_OR_AGENT
            for f in differing:
                conflict_fields[FIELD_LABELS.get(f, f)] += 1
    masters: dict[str, set[str]] = defaultdict(set)
    for r in records:
        if r.master_contact_id:
            masters[r.master_contact_id].add(r.raw_contact_id)
    skills_per_contact: dict[str, set[str]] = defaultdict(set)
    per_skill_rows: Counter[str] = Counter()
    per_skill_contacts: dict[str, set[str]] = defaultdict(set)
    for r in records:
        skills_per_contact[r.raw_contact_id].add(r.skill_name)
        per_skill_rows[r.skill_name] += 1
        per_skill_contacts[r.skill_name].add(r.raw_contact_id)
    files = sorted({r.source_file for r in records})
    shared: dict[str, int] = {}
    ids_by_file = {f: {r.raw_contact_id for r in records if r.source_file == f} for f in files}
    for i, a in enumerate(files):
        for b in files[i + 1:]:
            n = len(ids_by_file[a] & ids_by_file[b])
            if n:
                shared[f"{a}|{b}"] = n
    starts = [r.start_utc for r in records]
    per_skill = tuple(
        SkillCount(name, per_skill_rows[name], len(per_skill_contacts[name]))
        for name in sorted(per_skill_rows)
    )
    return ContactHistorySummary(
        raw_rows=len(records), distinct_contact_ids=len(by_id),
        distinct_master_contact_ids=len({r.master_contact_id for r in records if r.master_contact_id}),
        exact_repeat_rows=exact_within + exact_across, exact_repeats_within_a_file=exact_within,
        exact_repeats_across_files=exact_across,
        repeated_ids_total=sum(1 for rows in by_id.values() if len(rows) > 1),
        conflicting_repeated_ids=conflicts, conflict_fields=dict(conflict_fields),
        masters_with_multiple_contacts=sum(1 for ids in masters.values() if len(ids) > 1),
        contacts_under_multiple_skills=sum(1 for s in skills_per_contact.values() if len(s) > 1),
        media_types=dict(Counter(r.media_type for r in records)), per_skill=per_skill,
        earliest_start_utc=min(starts).isoformat().replace("+00:00", "Z") if starts else None,
        latest_start_utc=max(starts).isoformat().replace("+00:00", "Z") if starts else None,
        sum_of_per_skill_distinct_contacts=sum(s.distinct_contacts for s in per_skill),
        shared_contact_ids_between_files=shared,
        marked_id_rows=sum(1 for r in records if r.id_marker),
        distinct_base_contact_ids=len(markers_by_base),
        base_ids_seen_both_marked_and_unmarked=sum(1 for m in markers_by_base.values() if len(m) > 1),
        repeats_differing_only_in_agent=agent_only, repeated_ids_differing_only_in_team_or_agent=team_or_agent_only,
        marked_rows_whose_master_is_not_a_different_contact=sum(
            1 for r in records if r.is_child_leg and (not r.master_contact_id or r.master_contact_id == r.own_contact_id)),
        unmarked_rows_whose_master_is_a_different_contact=sum(
            1 for r in records
            if not r.is_child_leg and r.master_contact_id and r.master_contact_id != r.own_contact_id),
        rows_with_agent_token=sum(1 for r in records if r.agent_token),
    )


def dedupe_exact(records: tuple[ContactRecord, ...] | list[ContactRecord]) -> tuple[tuple[ContactRecord, ...], int]:
    """Removes ONLY rows that exactly repeat an earlier row in every kept field, the agent token included
    (the documented export-overlap rule); a repeat that differs only in agent is kept. Returns (kept records, removed count) so the removal stays auditable.
    Repeated IDs whose fields differ are NOT touched: they remain conflicts to be explained."""
    seen: set[tuple] = set()
    kept: list[ContactRecord] = []
    for r in records:
        key = r.comparable()
        if key in seen:
            continue
        seen.add(key)
        kept.append(r)
    return tuple(kept), len(records) - len(kept)


# ----------------------------------------------------------------------- skill mapping
def _norm(name: str) -> str:
    return " ".join(name.split()).casefold()


@dataclass(frozen=True)
class SkillResolution:
    resolved: dict[str, str]  # raw report name -> skill ID
    unmatched: tuple[str, ...]  # no inventory entry
    ambiguous: tuple[str, ...]  # inventory has several entries for the normalized name

    @property
    def complete(self) -> bool:
        return not self.unmatched and not self.ambiguous


def load_skill_inventory(path: Path) -> dict[str, list[str]]:
    """Skill name -> list of skill IDs from a Skills.csv-shaped file ('Skill ID', 'Skill Name'
    columns). Raw names are the keys; collisions are kept as multiple IDs, not overwritten."""
    inventory: dict[str, list[str]] = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "Skill ID" not in reader.fieldnames or "Skill Name" not in reader.fieldnames:
            raise ContactHistoryError(f"{path.name}: needs 'Skill ID' and 'Skill Name' columns")
        for row in reader:
            sid, name = (row.get("Skill ID") or "").strip(), (row.get("Skill Name") or "").strip()
            if sid and name:
                inventory[name].append(sid)
    return dict(inventory)


def resolve_skills(report_skill_names: set[str], inventory: dict[str, list[str]]) -> SkillResolution:
    """Exact match after whitespace/case normalization. Never fuzzy. A normalized name that maps to
    more than one inventory ID (or two inventory names that collapse together) is ambiguous."""
    by_norm: dict[str, set[str]] = defaultdict(set)
    for name, ids in inventory.items():
        by_norm[_norm(name)].update(ids)
    resolved: dict[str, str] = {}
    unmatched: list[str] = []
    ambiguous: list[str] = []
    for raw in sorted(report_skill_names):
        ids = by_norm.get(_norm(raw), set())
        if not ids:
            unmatched.append(raw)
        elif len(ids) > 1:
            ambiguous.append(raw)
        else:
            resolved[raw] = next(iter(ids))
    return SkillResolution(resolved=resolved, unmatched=tuple(unmatched), ambiguous=tuple(ambiguous))
