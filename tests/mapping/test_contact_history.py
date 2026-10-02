"""Synthetic fixtures only: no real phone numbers, agent names or customer data."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from romtech_mcp.mapping.contact_history import (
    ContactHistoryError, dedupe_exact, load_contact_history, load_skill_inventory, parse_start_time,
    resolve_skills, summarize,
)
from romtech_mcp.mapping.contact_history_reconcile import ApiContact, ApiContactFetch, compare_contacts
from romtech_mcp.mapping.models import ComparisonOutcome, CoverageState

HEADER = ["Contact ID", "Master Contact ID", "Media Type", "Skill", "Agent", "Team", "DNIS/To", "ANI/From",
          "Phone Type", "Start Time:", "Duration", "Logged", "Primary Disposition", "Additional Disposition", ""]
SECRET_AGENT, SECRET_PHONE = "Agent Smith-Canary", "+15550001234"
W_START = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
W_END = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)


def line(cid, master, skill, start, *, duration="0:30", team="Team A", media="Phone"):
    cells = [cid, master, media, skill, SECRET_AGENT, team, SECRET_PHONE, SECRET_PHONE, "Land line", start, duration,
             "", "Resolved", "", ""]
    return ",".join(f'"{c}"' if "," in c else c for c in cells)


def write_csv(path: Path, rows: list[str], header=HEADER, bom=True) -> Path:
    path.write_text("\n".join([",".join(header), *rows]) + "\n", encoding="utf-8-sig" if bom else "utf-8")
    return path


def write_skills(path: Path, entries: list[tuple[str, str]]) -> Path:
    path.write_text("Skill ID,Skill Name,Status\n" + "\n".join(f'{i},"{n}",Active' for i, n in entries) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def exports(tmp_path):
    a = write_csv(tmp_path / "a.csv", [
        line("1001", "9001", "Alpha", "10/1/2026 12:00:00 AM"),
        line("1002", "9001", "Beta", "10/1/2026 9:15:00 AM"),  # same master, other skill
        line("1003", "9003", 'Alpha, Spanish', "10/1/2026 11:59:59 PM", duration="12:05"),  # quoted comma in skill
        line("1004", "9004", "Alpha", "10/1/2026 1:00:00 PM"),
        line("1004", "9004", "Alpha", "10/1/2026 1:00:00 PM"),  # exact repeat within the file
    ])
    b = write_csv(tmp_path / "b.csv", [
        line("1004", "9004", "Alpha", "10/1/2026 1:00:00 PM"),  # exact repeat across files
        line("1005", "9005", "Alpha", "10/1/2026 2:00:00 PM"),
        line("1005", "9005", "Beta", "10/1/2026 2:00:00 PM"),  # conflicting repeat (skill differs)
    ])
    return [a, b]


# ------------------------------------------------------------------------ importer
def test_import_parses_bom_quotes_trailing_column_and_keeps_provenance(exports):
    imp = load_contact_history(exports, source_timezone="UTC")
    assert [f.rows for f in imp.files] == [5, 3] and [f.basename for f in imp.files] == ["a.csv", "b.csv"]
    assert all(len(f.sha256) == 64 for f in imp.files)
    r = imp.records[2]
    assert (r.source_file, r.row_number, r.skill_name, r.duration_text) == ("a.csv", 3, "Alpha, Spanish", "12:05")
    assert r.contact_id == "1003" and isinstance(r.contact_id, str)


def test_personal_columns_are_never_read_into_records(exports):
    imp = load_contact_history(exports, source_timezone="UTC")
    dumped = repr(imp) + repr(summarize(imp.records))
    assert SECRET_AGENT not in dumped and SECRET_PHONE not in dumped


def test_summary_counts_repeats_conflicts_and_relationships(exports):
    s = summarize(load_contact_history(exports, source_timezone="UTC").records)
    assert s.raw_rows == 8 and s.distinct_contact_ids == 5 and s.distinct_master_contact_ids == 4
    assert (s.exact_repeats_within_a_file, s.exact_repeats_across_files, s.exact_repeat_rows) == (1, 1, 2)
    assert s.repeated_ids_total == 2 and s.conflicting_repeated_ids == 1 and s.conflict_fields == {"skill_name": 1}
    assert s.masters_with_multiple_contacts == 1  # master 9001 -> contacts 1001 and 1002
    assert s.contacts_under_multiple_skills == 1  # 1005 under Alpha and Beta
    assert s.shared_contact_ids_between_files == {"a.csv|b.csv": 1}
    by_skill = {c.skill_name: c for c in s.per_skill}
    assert by_skill["Alpha"].rows == 5 and by_skill["Alpha"].distinct_contacts == 3
    # per-skill distinct counts add up to MORE than the global distinct count: never a global count
    assert s.sum_of_per_skill_distinct_contacts > s.distinct_contact_ids
    assert s.media_types == {"Phone": 8}


def test_dedupe_removes_only_exact_repeats_and_keeps_conflicts(exports):
    imp = load_contact_history(exports, source_timezone="UTC")
    kept, removed = dedupe_exact(imp.records)
    assert removed == 2 and len(kept) == 6
    assert sum(1 for r in kept if r.contact_id == "1005") == 2  # conflicting repeat is untouched


def test_start_time_is_parsed_explicitly_not_by_locale():
    assert parse_start_time("10/1/2026 11:46:14 PM") == datetime(2026, 10, 1, 23, 46, 14)
    assert parse_start_time("1/10/2026 12:00:00 AM") == datetime(2026, 1, 10, 0, 0, 0)  # month first, always
    for bad in ("2026-10-01 23:46:14", "13/1/2026 1:00:00 AM", "10/1/2026 13:00:00 PM", "10/1/2026 1:00 PM", ""):
        with pytest.raises(ValueError):
            parse_start_time(bad)


@pytest.mark.parametrize("rows,fragment", [
    ([line("", "1", "Alpha", "10/1/2026 1:00:00 PM")], "contact ID"),
    ([line("12a", "1", "Alpha", "10/1/2026 1:00:00 PM")], "contact ID"),
    ([line("1", "x", "Alpha", "10/1/2026 1:00:00 PM")], "master contact ID"),
    ([line("1", "1", "", "10/1/2026 1:00:00 PM")], "skill is empty"),
    ([line("1", "1", "Alpha", "not a date")], "start time rejected"),
    (["1,2,3"], "fields, expected"),
])
def test_malformed_rows_fail_with_file_and_row_but_no_cell_values(tmp_path, rows, fragment):
    path = write_csv(tmp_path / "bad.csv", rows)
    with pytest.raises(ContactHistoryError) as exc:
        load_contact_history([path], source_timezone="UTC")
    msg = str(exc.value)
    assert "bad.csv" in msg and fragment in msg and "not a date" not in msg and SECRET_AGENT not in msg


def test_missing_required_headers_empty_file_and_unknown_timezone(tmp_path, exports):
    no_skill = write_csv(tmp_path / "h.csv", [], header=[h for h in HEADER if h != "Skill"])
    with pytest.raises(ContactHistoryError, match="Skill"):
        load_contact_history([no_skill], source_timezone="UTC")
    empty = tmp_path / "e.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ContactHistoryError, match="empty"):
        load_contact_history([empty], source_timezone="UTC")
    with pytest.raises(ContactHistoryError, match="timezone"):
        load_contact_history(exports, source_timezone="Mars/Base")
    with pytest.raises(ContactHistoryError):
        load_contact_history([], source_timezone="UTC")
    header_only = write_csv(tmp_path / "ho.csv", [])
    assert load_contact_history([header_only], source_timezone="UTC").records == ()
    assert summarize(()).raw_rows == 0 and summarize(()).earliest_start_utc is None


def test_utc_and_eastern_interpretations_give_different_instants(tmp_path):
    p = write_csv(tmp_path / "t.csv", [line("1", "1", "Alpha", "10/1/2026 11:30:00 PM")])
    utc = load_contact_history([p], source_timezone="UTC").records[0].start_utc
    est = load_contact_history([p], source_timezone="America/New_York").records[0].start_utc
    assert utc == datetime(2026, 10, 1, 23, 30, tzinfo=timezone.utc)
    assert est == datetime(2026, 10, 2, 3, 30, tzinfo=timezone.utc)  # 23:30 EDT is the next UTC day


def test_ambiguous_and_nonexistent_local_times_are_rejected_not_guessed(tmp_path):
    fall = write_csv(tmp_path / "f.csv", [line("1", "1", "Alpha", "11/1/2026 1:30:00 AM")])
    with pytest.raises(ContactHistoryError, match="ambiguous"):
        load_contact_history([fall], source_timezone="America/New_York")
    spring = write_csv(tmp_path / "s.csv", [line("1", "1", "Alpha", "3/8/2026 2:30:00 AM")])
    with pytest.raises(ContactHistoryError, match="does not exist"):
        load_contact_history([spring], source_timezone="America/New_York")


# --------------------------------------------------------------------- skill mapping
def test_skill_resolution_exact_after_normalization_never_fuzzy(tmp_path):
    inv = load_skill_inventory(write_skills(tmp_path / "s.csv", [("11", "Alpha"), ("12", "Beta  Two"), ("13", "Gamma"), ("14", "gamma ")]))
    res = resolve_skills({"alpha", "Beta Two", "Gamma", "Delta", "Alph"}, inv)
    assert res.resolved == {"alpha": "11", "Beta Two": "12"}  # whitespace/case normalized
    assert res.unmatched == ("Alph", "Delta")  # no fuzzy matching
    assert res.ambiguous == ("Gamma",)  # two inventory names collapse together
    assert not res.complete


def test_duplicate_inventory_names_are_ambiguous_and_headers_checked(tmp_path):
    inv = load_skill_inventory(write_skills(tmp_path / "s.csv", [("11", "Alpha"), ("12", "Alpha")]))
    assert resolve_skills({"Alpha"}, inv).ambiguous == ("Alpha",)
    bad = tmp_path / "b.csv"
    bad.write_text("Name,Id\nA,1\n", encoding="utf-8")
    with pytest.raises(ContactHistoryError):
        load_skill_inventory(bad)


# ------------------------------------------------------------------------- comparison
def api(records, coverage=CoverageState.COMPLETE, captured=False):
    return ApiContactFetch(tuple(records), coverage, "/synthetic", "v0", captured)


def t(h, m=0):
    return datetime(2026, 10, 1, h, m, tzinfo=timezone.utc)


@pytest.fixture
def clean(tmp_path):
    p = write_csv(tmp_path / "c.csv", [
        line("1", "1", "Alpha", "10/1/2026 12:00:00 AM"),
        line("2", "2", "Beta", "10/1/2026 9:00:00 AM"),
        line("2", "2", "Beta", "10/1/2026 9:00:00 AM"),  # exact overlap repeat
        line("3", "3", "Alpha", "10/1/2026 11:59:59 PM"),
    ])
    recs = load_contact_history([p], source_timezone="UTC").records
    res = resolve_skills({r.skill_name for r in recs}, {"Alpha": ["11"], "Beta": ["12"]})
    good = [ApiContact("1", "11", t(0)), ApiContact("2", "12", t(9)), ApiContact("3", "11", datetime(2026, 10, 1, 23, 59, 59, tzinfo=timezone.utc))]
    return recs, res, good


def run_compare(recs, res, fetch, **kw):
    args = dict(window_start_utc=W_START, window_end_utc=W_END, grain="contact", timestamp_tolerance_seconds=0)
    args.update(kw)
    return compare_contacts(recs, res, fetch, **args)


def test_match_requires_identity_skill_time_and_per_skill_counts_to_agree(clean):
    recs, res, good = clean
    c = run_compare(recs, res, api(good))
    assert c.outcome is ComparisonOutcome.MATCH and c.matched == 3
    assert c.export_exact_repeats_removed == 1 and c.export_unique_contacts == 3
    assert c.per_skill == {"11": {"export": 2, "api": 2}, "12": {"export": 1, "api": 1}}
    assert "not compared" in c.duration
    assert c.api_fetch_is_real_capture is False  # a synthetic fixture validates the code, not the day


@pytest.mark.parametrize("mutate,field", [
    (lambda g: g[:-1], "export_only"),  # API is missing a contact
    (lambda g: g + [ApiContact("9", "11", t(5))], "api_only"),
    (lambda g: [ApiContact("1", "12", t(0))] + g[1:], "skill_mismatches"),
    (lambda g: [ApiContact("1", "11", t(0, 1))] + g[1:], "start_time_mismatches"),
])
def test_differences_are_mismatches_with_zero_tolerance(clean, mutate, field):
    recs, res, good = clean
    c = run_compare(recs, res, api(mutate(list(good))))
    assert c.outcome is ComparisonOutcome.MISMATCH and getattr(c, field) >= 1


def test_declared_timestamp_tolerance_is_honoured(clean):
    recs, res, good = clean
    shifted = [ApiContact("1", "11", t(0, 1))] + good[1:]
    assert run_compare(recs, res, api(shifted), timestamp_tolerance_seconds=60).outcome is ComparisonOutcome.MATCH
    assert run_compare(recs, res, api(shifted), timestamp_tolerance_seconds=59).outcome is ComparisonOutcome.MISMATCH


def test_window_is_half_open_and_outside_rows_are_counted_not_silently_dropped(clean):
    recs, res, good = clean
    c = run_compare(recs, res, api(good), window_start_utc=t(0, 1), window_end_utc=t(23, 59))
    assert c.export_rows_outside_window == 2 and c.export_rows_in_window == 2  # 00:00:00 and 23:59:59 excluded
    boundary = run_compare(recs, res, api(good), window_start_utc=t(0), window_end_utc=datetime(2026, 10, 2, tzinfo=timezone.utc))
    assert boundary.export_rows_outside_window == 0


def test_eastern_day_selection_is_not_the_utc_day(tmp_path):
    p = write_csv(tmp_path / "e.csv", [line("1", "1", "Alpha", "10/1/2026 11:30:00 PM")])
    recs = load_contact_history([p], source_timezone="America/New_York").records  # 2026-10-02T03:30Z
    res = resolve_skills({"Alpha"}, {"Alpha": ["11"]})
    utc_day = run_compare(recs, res, api([]))
    assert utc_day.export_rows_in_window == 0  # not part of the UTC calendar day October 1
    eastern = run_compare(recs, res, api([ApiContact("1", "11", datetime(2026, 10, 2, 3, 30, tzinfo=timezone.utc))]),
                          window_start_utc=datetime(2026, 10, 1, 4, tzinfo=timezone.utc),
                          window_end_utc=datetime(2026, 10, 2, 4, tzinfo=timezone.utc))
    assert eastern.outcome is ComparisonOutcome.MATCH


def test_empty_results_on_both_sides_do_not_count_as_a_successful_comparison_of_data(clean):
    recs, res, good = clean
    c = run_compare((), res, api([]))
    assert c.matched == 0 and c.export_unique_contacts == 0  # vacuous match is visible as zero matched


@pytest.mark.parametrize("kw,fragment", [
    ({"grain": None}, "grain"),
    ({"timestamp_tolerance_seconds": None}, "tolerance"),
])
def test_missing_preconditions_are_unresolved_never_match(clean, kw, fragment):
    recs, res, good = clean
    c = run_compare(recs, res, api(good), **kw)
    assert c.outcome is ComparisonOutcome.UNRESOLVED and any(fragment in r for r in c.unresolved_reasons)


def test_no_api_data_partial_coverage_and_unmatched_skills_are_unresolved(clean):
    recs, res, good = clean
    assert run_compare(recs, res, None).outcome is ComparisonOutcome.UNRESOLVED
    partial = run_compare(recs, res, api(good, coverage=CoverageState.UNKNOWN))
    assert partial.outcome is ComparisonOutcome.UNRESOLVED and any("coverage" in r for r in partial.unresolved_reasons)
    unmapped = resolve_skills({"Alpha", "Beta"}, {"Alpha": ["11"]})
    c = run_compare(recs, unmapped, api(good))
    assert c.outcome is ComparisonOutcome.UNRESOLVED and any("unmatched" in r for r in c.unresolved_reasons)


def test_conflicting_repeated_ids_are_unresolved_until_explained(tmp_path):
    p = write_csv(tmp_path / "x.csv", [line("1", "1", "Alpha", "10/1/2026 1:00:00 AM"),
                                       line("1", "1", "Beta", "10/1/2026 1:00:00 AM")])
    recs = load_contact_history([p], source_timezone="UTC").records
    res = resolve_skills({"Alpha", "Beta"}, {"Alpha": ["11"], "Beta": ["12"]})
    fetch = api([ApiContact("1", "11", t(1))])
    c = run_compare(recs, res, fetch)
    assert c.outcome is ComparisonOutcome.UNRESOLVED and any("unexplained" in r for r in c.unresolved_reasons)
    assert run_compare(recs, res, fetch, overlap_rule_documented=True).outcome is not ComparisonOutcome.UNRESOLVED


def test_inverted_window_and_negative_tolerance_are_rejected(clean):
    recs, res, good = clean
    with pytest.raises(ValueError):
        run_compare(recs, res, api(good), window_start_utc=W_END, window_end_utc=W_START)
    with pytest.raises(ValueError):
        run_compare(recs, res, api(good), timestamp_tolerance_seconds=-1)


# ----------------------------------------------------------------------------- CLI
def cli_args(tmp_path, exports, *extra, fixture=None):
    skills = write_skills(tmp_path / "skills.csv", [("11", "Alpha"), ("12", "Beta"), ("13", "Alpha, Spanish")])
    args = []
    for e in exports:
        args += ["--report", str(e)]
    args += ["--source-timezone", "UTC", "--window-start", "2026-10-01T00:00:00Z", "--window-end", "2026-10-02T00:00:00Z",
             "--skills", str(skills), "--source-confirmation", "synthetic test", "--output-dir", str(tmp_path / "out")]
    if fixture:
        args += ["--api-fixture", str(fixture)]
    return args + list(extra)


@pytest.fixture
def script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("reconcile_contact_history",
                                                  Path(__file__).resolve().parents[2] / "scripts" / "reconcile_contact_history.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_outputs(tmp_path):
    out = tmp_path / "out"
    return (json.loads(next(out.glob("manifest-*.json")).read_text(encoding="utf-8")),
            json.loads(next(out.glob("summary-*.json")).read_text(encoding="utf-8")))


def test_cli_import_only_writes_sanitized_evidence_and_never_claims_acceptance(tmp_path, exports, script, capsys):
    code = script.main(cli_args(tmp_path, exports, "--import-only"))
    assert code == 0
    manifest, summary = read_outputs(tmp_path)
    assert manifest["comparison_status"].startswith("not_run") and manifest["acceptance_grade"] is False
    assert manifest["timezone_basis"].startswith("ASSUMPTION") and manifest["source_confirmation"] == "synthetic test"
    assert [i["basename"] for i in manifest["inputs"]] == ["a.csv", "b.csv"] and manifest["skill_inventory"]["sha256"]
    assert summary["import"]["raw_rows"] == 8 and summary["skill_resolution"]["unmatched"] == []
    blob = json.dumps(manifest) + json.dumps(summary) + capsys.readouterr().out
    assert SECRET_AGENT not in blob and SECRET_PHONE not in blob


def test_cli_without_api_data_is_unresolved_and_exits_nonzero(tmp_path, exports, script):
    assert script.main(cli_args(tmp_path, exports, "--grain", "contact", "--timestamp-tolerance-seconds", "0")) == 2
    manifest, summary = read_outputs(tmp_path)
    assert manifest["comparison_status"] == "unresolved" and summary["comparison"]["outcome"] == "unresolved"
    assert manifest["acceptance_grade"] is False


def test_cli_exit_codes_for_match_and_mismatch_and_identities_stay_out_of_evidence(tmp_path, script):
    p = write_csv(tmp_path / "m.csv", [line("1", "1", "Alpha", "10/1/2026 1:00:00 AM")])
    fixture = tmp_path / "api.json"

    def write(records):
        fixture.write_text(json.dumps({"coverage": "complete", "endpoint_path": "/synthetic", "api_version": "v0",
                                       "captured": False, "records": records}), encoding="utf-8")

    write([{"contactId": "1", "skillId": "11", "startUtc": "2026-10-01T01:00:00Z"}])
    flags = ("--grain", "contact", "--timestamp-tolerance-seconds", "0")
    assert script.main(cli_args(tmp_path, [p], *flags, fixture=fixture)) == 0
    write([{"contactId": "777", "skillId": "11", "startUtc": "2026-10-01T01:00:00Z"}])
    assert script.main(cli_args(tmp_path, [p], *flags, fixture=fixture)) == 1
    _, summary = max(((m, s) for m, s in [read_outputs(tmp_path)]), key=lambda x: 0)
    assert "export_only_ids" not in summary["comparison"] and "777" not in json.dumps(summary)


def test_cli_rejects_bad_inputs_with_exit_2(tmp_path, script, capsys):
    bad = write_csv(tmp_path / "bad.csv", [line("x", "1", "Alpha", "10/1/2026 1:00:00 AM")])
    assert script.main(cli_args(tmp_path, [bad], "--import-only")) == 2
    assert "bad.csv" in capsys.readouterr().err


# ------------------------------------------------------- trailing "*" on exported contact IDs
def test_trailing_asterisk_is_kept_as_a_marker_not_silently_stripped(tmp_path):
    p = write_csv(tmp_path / "m.csv", [
        line("1001*", "9001", "Alpha", "10/1/2026 1:00:00 AM"),
        line("1001", "9001", "Alpha", "10/1/2026 1:00:00 AM"),
        line("1002*", "9002", "Alpha", "10/1/2026 2:00:00 AM"),
    ])
    imp = load_contact_history([p], source_timezone="UTC")
    assert [(r.contact_id, r.id_marker, r.raw_contact_id) for r in imp.records] == [
        ("1001", "*", "1001*"), ("1001", "", "1001"), ("1002", "*", "1002*")]
    s = summarize(imp.records)
    assert s.distinct_contact_ids == 3 and s.distinct_base_contact_ids == 2  # raw vs digits-only
    assert s.marked_id_rows == 2 and s.base_ids_seen_both_marked_and_unmarked == 1
    assert s.exact_repeat_rows == 0  # "1001*" and "1001" are not an exact repeat
    assert s.conflicting_repeated_ids == 0 and imp.files[0].distinct_contact_ids == 3


def test_bare_asterisk_or_other_suffixes_are_still_rejected(tmp_path):
    for bad in ("*", "12**", "12x*", "*12"):
        p = write_csv(tmp_path / "b.csv", [line(bad, "1", "Alpha", "10/1/2026 1:00:00 AM")])
        with pytest.raises(ContactHistoryError, match="contact ID"):
            load_contact_history([p], source_timezone="UTC")


def test_marked_ids_make_the_comparison_unresolved_until_the_meaning_is_documented(tmp_path):
    p = write_csv(tmp_path / "m.csv", [line("1*", "1", "Alpha", "10/1/2026 1:00:00 AM")])
    recs = load_contact_history([p], source_timezone="UTC").records
    res = resolve_skills({"Alpha"}, {"Alpha": ["11"]})
    fetch = api([ApiContact("1", "11", t(1))])
    c = run_compare(recs, res, fetch)
    assert c.outcome is ComparisonOutcome.UNRESOLVED and any("'*'" in r for r in c.unresolved_reasons)
    assert run_compare(recs, res, fetch, id_marker_explained=True).outcome is ComparisonOutcome.MATCH
