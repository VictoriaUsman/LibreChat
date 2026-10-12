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
from romtech_mcp.mapping.contact_history_reconcile import (
    SUPPORTED_GRAINS, MARKER_RULE_CHILD_LEG, REPEAT_RULE_TEAM_OR_AGENT_ONLY, ApiContact, ApiContactFetch, compare_contacts,
)
from romtech_mcp.mapping.models import ComparisonOutcome, CoverageState

HEADER = ["Contact ID", "Master Contact ID", "Media Type", "Skill", "Agent", "Team", "DNIS/To", "ANI/From",
          "Phone Type", "Start Time:", "Duration", "Logged", "Primary Disposition", "Additional Disposition", ""]
SECRET_AGENT, SECRET_PHONE = "Agent Smith-Canary", "+15550001234"
W_START = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
W_END = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)


def line(cid, master, skill, start, *, duration="0:30", team="Team A", media="Phone", agent=SECRET_AGENT):
    cells = [cid, master, media, skill, agent, team, SECRET_PHONE, SECRET_PHONE, "Land line", start, duration,
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
    # a documented rule covers team/agent differences only; it can never explain away a skill difference
    with_rule = run_compare(recs, res, fetch, conflict_rule=REPEAT_RULE_TEAM_OR_AGENT_ONLY)
    assert with_rule.outcome is ComparisonOutcome.UNRESOLVED and any("skill_name" in r for r in with_rule.unresolved_reasons)


def test_conflicting_api_duplicates_are_unresolved_not_first_record_wins(clean):
    """Regression: only the first API record per contact ID was kept, so a second record with another skill
    (or start) still produced MATCH."""
    recs, res, good = clean
    other_skill = list(good) + [ApiContact("1", "12", t(0))]
    other_start = list(good) + [ApiContact("1", "11", t(0, 5))]
    for records in (other_skill, other_start, other_skill[::-1]):  # order must not matter
        c = run_compare(recs, res, api(records))
        assert c.outcome is ComparisonOutcome.UNRESOLVED and any("API contact ID" in r for r in c.unresolved_reasons)
    outside = list(good) + [ApiContact("1", "12", datetime(2026, 10, 3, tzinfo=timezone.utc))]  # out-of-window copy
    assert run_compare(recs, res, api(outside)).outcome is ComparisonOutcome.UNRESOLVED


def test_identical_api_duplicates_are_collapsed_and_counted(clean):
    recs, res, good = clean
    c = run_compare(recs, res, api(list(good) + [good[0]]))
    assert c.outcome is ComparisonOutcome.MATCH and c.api_exact_repeats_removed == 1 and c.api_unique_contacts == 3


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
    p = write_csv(tmp_path / "m.csv", [line("1*", "9", "Alpha", "10/1/2026 1:00:00 AM")])
    recs = load_contact_history([p], source_timezone="UTC").records
    res = resolve_skills({"Alpha"}, {"Alpha": ["11"]})
    fetch = api([ApiContact("1", "11", t(1))])
    c = run_compare(recs, res, fetch)
    assert c.outcome is ComparisonOutcome.UNRESOLVED and any("'*'" in r for r in c.unresolved_reasons)
    ok = run_compare(recs, res, fetch, id_marker_rule=MARKER_RULE_CHILD_LEG)
    assert ok.outcome is ComparisonOutcome.MATCH and ok.child_leg_rows == 1 and ok.id_marker_rule == MARKER_RULE_CHILD_LEG


# ------------------------------------------- review fixes: repeats and the child-leg rule
def _one(tmp_path, rows, name="r.csv"):
    return load_contact_history([write_csv(tmp_path / name, rows)], source_timezone="UTC").records


ALPHA_BETA = ({"Alpha", "Beta"}, {"Alpha": ["11"], "Beta": ["12"]})


def test_a_rule_never_hides_a_conflicting_skill_on_a_repeated_id(tmp_path):
    """Regression: any documented rule used to bypass the conflict check and the first row won, so a second
    row with a different skill produced MATCH."""
    recs = _one(tmp_path, [line("1", "1", "Alpha", "10/1/2026 1:00:00 AM"), line("1", "1", "Beta", "10/1/2026 1:00:00 AM")])
    res = resolve_skills(*ALPHA_BETA)
    for api_skill in ("11", "12"):  # whichever row the API agrees with, the other one is a discrepancy
        c = run_compare(recs, res, api([ApiContact("1", api_skill, t(1))]), conflict_rule=REPEAT_RULE_TEAM_OR_AGENT_ONLY)
        assert c.outcome is not ComparisonOutcome.MATCH


def test_a_rule_never_hides_a_conflicting_start_time_on_a_repeated_id(tmp_path):
    recs = _one(tmp_path, [line("1", "1", "Alpha", "10/1/2026 1:00:00 AM"), line("1", "1", "Alpha", "10/1/2026 1:05:00 AM")])
    c = run_compare(recs, resolve_skills({"Alpha"}, {"Alpha": ["11"]}), api([ApiContact("1", "11", t(1))]),
                    conflict_rule=REPEAT_RULE_TEAM_OR_AGENT_ONLY)
    assert c.outcome is ComparisonOutcome.UNRESOLVED and any("start_utc" in r for r in c.unresolved_reasons)


def test_team_and_agent_only_repeats_are_explained_only_by_the_named_rule(tmp_path):
    recs = _one(tmp_path, [
        line("1", "1", "Alpha", "10/1/2026 1:00:00 AM", team="Team A", agent="Agent One"),
        line("1", "1", "Alpha", "10/1/2026 1:00:00 AM", team="Team B", agent="Agent Two"),  # refusal: next team
        line("2", "2", "Alpha", "10/1/2026 2:00:00 AM", agent="Agent One"),
        line("2", "2", "Alpha", "10/1/2026 2:00:00 AM", agent="Agent Two"),  # same team, other agent
    ])
    res = resolve_skills({"Alpha"}, {"Alpha": ["11"]})
    fetch = api([ApiContact("1", "11", t(1)), ApiContact("2", "11", t(2))])
    without = run_compare(recs, res, fetch)
    assert without.outcome is ComparisonOutcome.UNRESOLVED and any("unexplained" in r for r in without.unresolved_reasons)
    with_rule = run_compare(recs, res, fetch, conflict_rule=REPEAT_RULE_TEAM_OR_AGENT_ONLY)
    assert with_rule.outcome is ComparisonOutcome.MATCH and with_rule.export_unique_contacts == 2
    assert with_rule.repeated_ids_explained_by_rule == 2 and with_rule.conflict_rule == REPEAT_RULE_TEAM_OR_AGENT_ONLY
    with pytest.raises(ValueError):
        run_compare(recs, res, fetch, conflict_rule="any free text")


def test_agent_only_repeats_are_not_called_exact_and_no_agent_name_survives(tmp_path):
    recs = _one(tmp_path, [
        line("1", "1", "Alpha", "10/1/2026 1:00:00 AM", agent="Agent One"),
        line("1", "1", "Alpha", "10/1/2026 1:00:00 AM", agent="Agent One"),   # identical in every column
        line("2", "2", "Alpha", "10/1/2026 2:00:00 AM", agent="Agent One"),
        line("2", "2", "Alpha", "10/1/2026 2:00:00 AM", agent="Agent Two"),   # same selected fields, other agent
    ])
    s = summarize(recs)
    assert s.exact_repeat_rows == 1  # only the genuinely identical pair
    assert s.repeats_differing_only_in_agent == 1
    assert s.conflicting_repeated_ids == 1 and s.conflict_fields == {"agent": 1}
    assert s.repeated_ids_differing_only_in_team_or_agent == 1
    kept, removed = dedupe_exact(recs)
    assert removed == 1 and len(kept) == 3  # the agent-only repeat is kept, not silently merged
    dumped = repr(recs) + repr(s)
    assert "Agent One" not in dumped and "Agent Two" not in dumped


def test_child_leg_rule_preserves_own_id_and_master_and_requires_master_to_differ(tmp_path):
    recs = _one(tmp_path, [
        line("10", "10", "Alpha", "10/1/2026 1:00:00 AM"),    # parent: master is itself
        line("11*", "10", "Alpha", "10/1/2026 1:01:00 AM"),   # child leg: own ID 11, master 10
    ])
    parent, child = recs
    assert (parent.is_child_leg, parent.own_contact_id, parent.master_contact_id) == (False, "10", "10")
    assert (child.is_child_leg, child.own_contact_id, child.master_contact_id, child.raw_contact_id) == (True, "11", "10", "11*")
    res = resolve_skills({"Alpha"}, {"Alpha": ["11"]})
    fetch = api([ApiContact("10", "11", t(1)), ApiContact("11", "11", t(1, 1))])
    c = run_compare(recs, res, fetch, id_marker_rule=MARKER_RULE_CHILD_LEG)
    assert c.outcome is ComparisonOutcome.MATCH and c.matched == 2 and c.child_leg_rows == 1  # never collapsed into the parent


@pytest.mark.parametrize("rows,fragment", [
    ([line("1*", "1", "Alpha", "10/1/2026 1:00:00 AM")], "child leg"),                 # marked, master is itself
    ([line("1*", "", "Alpha", "10/1/2026 1:00:00 AM")], "child leg"),                  # marked, no master
    ([line("1", "5", "Alpha", "10/1/2026 1:00:00 AM")], "not marked"),                 # unmarked row with another master
    ([line("1*", "5", "Alpha", "10/1/2026 1:00:00 AM"), line("1", "1", "Alpha", "10/1/2026 1:00:00 AM")], "both"),
])
def test_child_leg_rule_is_unresolved_when_the_export_contradicts_it(tmp_path, rows, fragment):
    recs = _one(tmp_path, rows)
    c = run_compare(recs, resolve_skills({"Alpha"}, {"Alpha": ["11"]}), api([ApiContact("1", "11", t(1))]),
                    id_marker_rule=MARKER_RULE_CHILD_LEG)
    assert c.outcome is ComparisonOutcome.UNRESOLVED and any(fragment in r for r in c.unresolved_reasons), c.unresolved_reasons


def test_free_text_rule_acknowledgements_are_rejected(tmp_path, exports, script):
    recs = _one(tmp_path, [line("1*", "9", "Alpha", "10/1/2026 1:00:00 AM")])
    with pytest.raises(ValueError):
        run_compare(recs, resolve_skills({"Alpha"}, {"Alpha": ["11"]}), api([ApiContact("1", "11", t(1))]),
                    id_marker_rule="the star means something")
    for flag in ("--id-marker-rule", "--repeat-rule"):
        with pytest.raises(SystemExit) as e:
            script.main(cli_args(tmp_path, exports, flag, "free text"))
        assert e.value.code == 2


# ------------------------------------- review: dropped records, unsupported grains, capture provenance
def test_out_of_window_export_records_make_the_comparison_unresolved_not_a_match(tmp_path):
    """Regression: one export record outside the window was filtered away and an empty API result returned MATCH."""
    recs = _one(tmp_path, [line("1", "1", "Alpha", "9/30/2026 11:00:00 PM")])  # before the window
    res = resolve_skills({"Alpha"}, {"Alpha": ["11"]})
    c = run_compare(recs, res, api([]))
    assert c.outcome is ComparisonOutcome.UNRESOLVED and c.export_rows_outside_window == 1
    assert any("outside the window" in r for r in c.unresolved_reasons)


def test_out_of_window_api_records_are_not_silently_dropped_either(clean):
    recs, res, good = clean
    c = run_compare(recs, res, api(list(good) + [ApiContact("9", "11", datetime(2026, 10, 3, tzinfo=timezone.utc))]))
    assert c.outcome is ComparisonOutcome.UNRESOLVED and c.api_records_outside_window == 1
    assert any("API record" in r and "outside the window" in r for r in c.unresolved_reasons)


def test_an_explicitly_labelled_subset_may_compare_but_is_never_full_day_validation(clean):
    recs, res, good = clean
    c = run_compare(recs, res, api(good), window_start_utc=t(0, 1), window_end_utc=t(23, 59), subset_label="09:00 only")
    assert c.subset_label == "09:00 only" and c.full_day_validation is False
    assert run_compare(recs, res, api(good)).full_day_validation is True


@pytest.mark.parametrize("grain", ["master interaction", "routed leg", "transfer", "", "Contact "])
def test_only_implemented_grains_are_accepted(clean, grain):
    recs, res, good = clean
    assert SUPPORTED_GRAINS == ("contact",)
    c = run_compare(recs, res, api(good), grain=grain)
    assert c.outcome is ComparisonOutcome.UNRESOLVED and any("grain" in r for r in c.unresolved_reasons)


@pytest.mark.parametrize("captured", ["false", "true", "False", 0, 1, None, "yes"])
def test_captured_must_be_a_real_json_boolean(tmp_path, script, captured):
    p = write_csv(tmp_path / "m.csv", [line("1", "1", "Alpha", "10/1/2026 1:00:00 AM")])
    fixture = tmp_path / "api.json"
    fixture.write_text(json.dumps({"coverage": "complete", "endpoint_path": "/synthetic", "api_version": "v0",
                                   "captured": captured, "records": []}), encoding="utf-8")
    assert script.main(cli_args(tmp_path, [p], "--grain", "contact", "--timestamp-tolerance-seconds", "0",
                                fixture=fixture)) == 2  # rejected as invalid input, never coerced


def test_a_real_json_boolean_is_accepted_for_captured(tmp_path, script):
    p = write_csv(tmp_path / "m.csv", [line("1", "1", "Alpha", "10/1/2026 1:00:00 AM")])
    fixture = tmp_path / "api.json"
    fixture.write_text(json.dumps({"coverage": "complete", "endpoint_path": "/synthetic", "api_version": "v0",
                                   "captured": False, "records": [{"contactId": "1", "skillId": "11",
                                                                   "startUtc": "2026-10-01T01:00:00Z"}]}), encoding="utf-8")
    assert script.main(cli_args(tmp_path, [p], "--grain", "contact", "--timestamp-tolerance-seconds", "0",
                                fixture=fixture)) == 0
