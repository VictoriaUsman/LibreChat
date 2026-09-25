"""
Verifies client-side scope selection: the server ignores skillId filters
(discovery-confirmed), so every ID bucket (requested/returned/included/
excluded/missing/duplicate) must be tracked from the full, unfiltered
response — never assumed from what the server "should" have filtered.
"""

from __future__ import annotations

from romtech_mcp.mapping.models import CoverageState, NormalizedRow, ScopeConfig
from romtech_mcp.mapping.scope import UnsupportedTeamScopeError, select_scope as _select_scope_raw


def select_scope(rows, scope, *, source_coverage):
    return _select_scope_raw(
        rows, scope, source_coverage=source_coverage,
        source_endpoint_path="/skills/summary", source_api_version="v27.0",
    )


def _row(skill_id: str | None) -> NormalizedRow:
    return NormalizedRow(skill_id=skill_id, raw={"skillId": skill_id})


def test_included_ids_are_selected_and_others_dropped() -> None:
    rows = [_row("1"), _row("2"), _row("3")]
    scope = ScopeConfig(included_skill_ids=("1", "2"))
    result = select_scope(rows, scope, source_coverage=CoverageState.COMPLETE)
    assert {r.skill_id for r in result.rows} == {"1", "2"}
    assert result.included_ids == {"1", "2"}


def test_excluded_ids_are_removed_even_if_requested() -> None:
    rows = [_row("1"), _row("2")]
    scope = ScopeConfig(included_skill_ids=("1", "2"), excluded_skill_ids=("2",))
    result = select_scope(rows, scope, source_coverage=CoverageState.COMPLETE)
    assert result.included_ids == {"1"}
    assert result.excluded_ids == {"2"}


def test_missing_requested_id_is_tracked_and_downgrades_coverage() -> None:
    rows = [_row("1")]
    scope = ScopeConfig(included_skill_ids=("1", "2"))
    result = select_scope(rows, scope, source_coverage=CoverageState.COMPLETE)
    assert result.missing_ids == {"2"}
    assert result.coverage == CoverageState.PARTIAL


def test_empty_inclusion_list_means_no_inclusion_filter() -> None:
    rows = [_row("1"), _row("2")]
    scope = ScopeConfig()  # no included_skill_ids set at all
    result = select_scope(rows, scope, source_coverage=CoverageState.COMPLETE)
    assert result.included_ids == {"1", "2"}
    assert result.missing_ids == frozenset()


def test_unattributable_row_is_never_counted_as_in_scope() -> None:
    rows = [_row(None), _row("1")]
    scope = ScopeConfig(included_skill_ids=("1",))
    result = select_scope(rows, scope, source_coverage=CoverageState.COMPLETE)
    assert result.included_ids == {"1"}
    assert None not in result.returned_ids


def test_duplicate_skill_id_is_detected_and_not_double_counted() -> None:
    rows = [_row("1"), _row("1")]
    scope = ScopeConfig(included_skill_ids=("1",))
    result = select_scope(rows, scope, source_coverage=CoverageState.COMPLETE)
    assert result.duplicate_ids == {"1"}
    assert len(result.rows) == 1  # only the first occurrence is kept for calculation


def test_team_scope_is_a_hard_block_not_a_silent_skill_only_filter() -> None:
    """Reproduced defect: select_scope accepted configured team_ids but
    filtered only skills, silently ignoring the team requirement."""
    import pytest

    rows = [_row("1")]
    scope = ScopeConfig(included_skill_ids=("1",), team_ids=("team-1",))
    with pytest.raises(UnsupportedTeamScopeError):
        select_scope(rows, scope, source_coverage=CoverageState.COMPLETE)


def test_conflicting_duplicate_values_downgrade_coverage() -> None:
    """Reproduced defect: values 10 and 999 for the same skill silently
    kept 10 and reported complete coverage, letting a mismatch through."""
    rows = [NormalizedRow(skill_id="1", raw={"skillId": "1", "contactsOffered": 10}),
            NormalizedRow(skill_id="1", raw={"skillId": "1", "contactsOffered": 999})]
    scope = ScopeConfig(included_skill_ids=("1",))
    result = select_scope(rows, scope, source_coverage=CoverageState.COMPLETE)
    assert result.duplicate_ids == {"1"}
    assert result.coverage != CoverageState.COMPLETE


def test_unknown_source_coverage_is_never_upgraded_by_scoping() -> None:
    rows = [_row("1")]
    scope = ScopeConfig(included_skill_ids=("1",))
    result = select_scope(rows, scope, source_coverage=CoverageState.UNKNOWN)
    assert result.coverage == CoverageState.UNKNOWN
