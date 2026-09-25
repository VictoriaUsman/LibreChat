"""
Verifies numeric field validation (missing/null/malformed is UNKNOWN, never
zero), the fixed set of declared formula operations, denominator-zero
handling, and that comparisons never silently pass by widening tolerance.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from romtech_mcp.mapping.models import (
    ComparisonOutcome,
    FieldPath,
    FieldValueState,
    FormulaComponent,
    MetricFormula,
    MetricMapping,
    NormalizedRow,
    ReportingWindow,
    ScopedObservations,
    CoverageState,
)
from romtech_mcp.mapping.reconcile import compare_metric, derive_metric, parse_numeric_field


def _window() -> ReportingWindow:
    return ReportingWindow(
        label="2026-09-23",
        local_start=datetime(2026, 9, 23, tzinfo=timezone.utc),
        local_end=datetime(2026, 9, 24, tzinfo=timezone.utc),
        utc_start=datetime(2026, 9, 23, tzinfo=timezone.utc),
        utc_end=datetime(2026, 9, 24, tzinfo=timezone.utc),
    )


def _field(name: str) -> FieldPath:
    return FieldPath(endpoint_path="/skills/summary", api_version="v27.0", response_field=name)


def _scoped(rows: list[NormalizedRow], coverage: CoverageState = CoverageState.COMPLETE) -> ScopedObservations:
    ids = {r.skill_id for r in rows if r.skill_id is not None}
    return ScopedObservations(
        requested_ids=frozenset(ids), returned_ids=frozenset(ids), included_ids=frozenset(ids),
        excluded_ids=frozenset(), missing_ids=frozenset(), duplicate_ids=frozenset(), rows=rows, coverage=coverage,
        source_endpoint_path="/skills/summary", source_api_version="v27.0",
    )


def _mapping(formula: MetricFormula) -> MetricMapping:
    return MetricMapping(key="m", dashboard_label="Metric", widget="w", definition_evidence="e", formula=formula)


# -- parse_numeric_field ------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "not-a-number", float("nan"), float("inf"), True, False, {}])
def test_invalid_values_are_unknown(value) -> None:
    parsed, state = parse_numeric_field(value)
    assert state is FieldValueState.UNKNOWN
    assert parsed is None


def test_numeric_zero_and_string_zero_are_equal_and_valid() -> None:
    a, sa = parse_numeric_field(0)
    b, sb = parse_numeric_field("0")
    assert sa is sb is FieldValueState.VALID
    assert a == b == 0.0


def test_negative_is_rejected_by_default() -> None:
    parsed, state = parse_numeric_field(-1)
    assert state is FieldValueState.UNKNOWN
    assert parsed is None


def test_negative_allowed_when_not_rejected() -> None:
    parsed, state = parse_numeric_field(-1, reject_negative=False)
    assert state is FieldValueState.VALID
    assert parsed == -1.0


# -- derive_metric: sum -------------------------------------------------------


def test_sum_adds_across_in_scope_rows() -> None:
    rows = [NormalizedRow(skill_id="1", raw={"contactsOffered": 3}), NormalizedRow(skill_id="2", raw={"contactsOffered": 4})]
    formula = MetricFormula(operation="sum", components=(FormulaComponent("offered", _field("contactsOffered")),))
    obs = derive_metric(_mapping(formula), _scoped(rows), _window())
    assert obs.value_state is FieldValueState.VALID
    assert obs.value == 7.0


def test_sum_is_unknown_if_any_row_missing_the_field() -> None:
    rows = [NormalizedRow(skill_id="1", raw={"contactsOffered": 3}), NormalizedRow(skill_id="2", raw={})]
    formula = MetricFormula(operation="sum", components=(FormulaComponent("offered", _field("contactsOffered")),))
    obs = derive_metric(_mapping(formula), _scoped(rows), _window())
    assert obs.value_state is FieldValueState.UNKNOWN
    assert obs.value is None


def test_incomplete_coverage_is_unknown_not_a_computed_match() -> None:
    """Reproduced defect: derive_metric ignored scoped.coverage/missing_ids
    entirely — a fetch missing a requested skill still reported a value."""
    rows = [NormalizedRow(skill_id="1", raw={"contactsOffered": 3})]
    scoped = ScopedObservations(
        requested_ids=frozenset({"1", "2"}), returned_ids=frozenset({"1"}), included_ids=frozenset({"1"}),
        excluded_ids=frozenset(), missing_ids=frozenset({"2"}), duplicate_ids=frozenset(), rows=rows,
        coverage=CoverageState.PARTIAL, source_endpoint_path="/skills/summary", source_api_version="v27.0",
    )
    formula = MetricFormula(operation="sum", components=(FormulaComponent("offered", _field("contactsOffered")),))
    obs = derive_metric(_mapping(formula), scoped, _window())
    assert obs.value_state is FieldValueState.UNKNOWN


def test_formula_component_from_a_different_source_is_rejected() -> None:
    """Reproduced defect: a component naming a different endpoint/API
    version still silently read the current response's field."""
    rows = [NormalizedRow(skill_id="1", raw={"contactsOffered": 10})]
    scoped = _scoped(rows)  # source is /skills/summary @ v27.0
    wrong_source = FieldPath(endpoint_path="/other/endpoint", api_version="v1.0", response_field="contactsOffered")
    formula = MetricFormula(operation="sum", components=(FormulaComponent("offered", wrong_source),))
    with pytest.raises(ValueError, match="mismatched source"):
        derive_metric(_mapping(formula), scoped, _window())


def test_no_in_scope_rows_is_unknown_not_zero() -> None:
    formula = MetricFormula(operation="sum", components=(FormulaComponent("offered", _field("contactsOffered")),))
    obs = derive_metric(_mapping(formula), _scoped([]), _window())
    assert obs.value_state is FieldValueState.UNKNOWN


# -- derive_metric: ratio / weighted_average ----------------------------------


def test_ratio_computes_sum_over_sum() -> None:
    rows = [
        NormalizedRow(skill_id="1", raw={"handled": 8, "offered": 10}),
        NormalizedRow(skill_id="2", raw={"handled": 2, "offered": 10}),
    ]
    formula = MetricFormula(
        operation="ratio",
        components=(FormulaComponent("handled", _field("handled")), FormulaComponent("offered", _field("offered"))),
    )
    obs = derive_metric(_mapping(formula), _scoped(rows), _window())
    assert obs.value_state is FieldValueState.VALID
    assert obs.value == pytest.approx(10 / 20)


def test_ratio_zero_denominator_defaults_to_unknown_not_zero_or_error() -> None:
    rows = [NormalizedRow(skill_id="1", raw={"handled": 0, "offered": 0})]
    formula = MetricFormula(
        operation="ratio",
        components=(FormulaComponent("handled", _field("handled")), FormulaComponent("offered", _field("offered"))),
        denominator_zero_behavior="null",
    )
    obs = derive_metric(_mapping(formula), _scoped(rows), _window())
    assert obs.value_state is FieldValueState.UNKNOWN


def test_ratio_zero_denominator_can_be_configured_as_zero() -> None:
    rows = [NormalizedRow(skill_id="1", raw={"handled": 0, "offered": 0})]
    formula = MetricFormula(
        operation="ratio",
        components=(FormulaComponent("handled", _field("handled")), FormulaComponent("offered", _field("offered"))),
        denominator_zero_behavior="zero",
    )
    obs = derive_metric(_mapping(formula), _scoped(rows), _window())
    assert obs.value_state is FieldValueState.VALID
    assert obs.value == 0.0


def test_weighted_average_weights_correctly() -> None:
    rows = [
        NormalizedRow(skill_id="1", raw={"aht": 100, "count": 1}),
        NormalizedRow(skill_id="2", raw={"aht": 200, "count": 3}),
    ]
    formula = MetricFormula(
        operation="weighted_average",
        components=(FormulaComponent("aht", _field("aht")), FormulaComponent("count", _field("count"))),
    )
    obs = derive_metric(_mapping(formula), _scoped(rows), _window())
    # (100*1 + 200*3) / (1+3) = 700/4 = 175 -- NOT the naive unweighted average of 150.
    assert obs.value == pytest.approx(175.0)


def test_average_is_unweighted_mean() -> None:
    rows = [NormalizedRow(skill_id="1", raw={"aht": 100}), NormalizedRow(skill_id="2", raw={"aht": 200})]
    formula = MetricFormula(operation="average", components=(FormulaComponent("aht", _field("aht")),))
    obs = derive_metric(_mapping(formula), _scoped(rows), _window())
    assert obs.value == pytest.approx(150.0)


def test_identity_requires_exactly_one_row() -> None:
    rows = [NormalizedRow(skill_id="1", raw={"x": 5}), NormalizedRow(skill_id="2", raw={"x": 5})]
    formula = MetricFormula(operation="identity", components=(FormulaComponent("x", _field("x")),))
    obs = derive_metric(_mapping(formula), _scoped(rows), _window())
    assert obs.value_state is FieldValueState.UNKNOWN
    assert "exactly one" in obs.notes[0]


def test_rounding_is_applied() -> None:
    rows = [NormalizedRow(skill_id="1", raw={"aht": 100}), NormalizedRow(skill_id="2", raw={"aht": 201})]
    formula = MetricFormula(operation="average", components=(FormulaComponent("aht", _field("aht")),), rounding_ndigits=1)
    obs = derive_metric(_mapping(formula), _scoped(rows), _window())
    assert obs.value == 150.5


# -- compare_metric ------------------------------------------------------------


def _valid_obs(value: float) -> "object":
    from romtech_mcp.mapping.models import MetricObservation

    return MetricObservation(metric_key="m", window=_window(), value=value, value_state=FieldValueState.VALID, unit="count")


def test_match_within_tolerance() -> None:
    result = compare_metric("m", _valid_obs(100.0), 99.5, unit="count", tolerance=1.0)
    assert result.outcome is ComparisonOutcome.MATCH


def test_mismatch_outside_tolerance_is_never_silently_widened() -> None:
    result = compare_metric("m", _valid_obs(110.0), 100.0, unit="count", tolerance=1.0)
    assert result.outcome is ComparisonOutcome.MISMATCH
    assert result.absolute_delta == 10.0


def test_missing_tolerance_is_unresolved_not_a_silent_pass() -> None:
    result = compare_metric("m", _valid_obs(110.0), 100.0, unit="count", tolerance=None)
    assert result.outcome is ComparisonOutcome.UNRESOLVED


def test_unknown_api_value_is_unresolved() -> None:
    from romtech_mcp.mapping.models import MetricObservation

    obs = MetricObservation(metric_key="m", window=_window(), value=None, value_state=FieldValueState.UNKNOWN, unit="count")
    result = compare_metric("m", obs, 100.0, unit="count", tolerance=1.0)
    assert result.outcome is ComparisonOutcome.UNRESOLVED


def test_infinite_tolerance_is_rejected_not_a_silent_match() -> None:
    """Reproduced defect: Infinity permitted mismatched values to report
    MATCH, since abs(delta) <= inf is always true."""
    with pytest.raises(ValueError, match="finite"):
        compare_metric("m", _valid_obs(110.0), 0.0, unit="count", tolerance=float("inf"))


def test_negative_tolerance_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        compare_metric("m", _valid_obs(110.0), 100.0, unit="count", tolerance=-1.0)


def test_boolean_tolerance_is_rejected_not_treated_as_one() -> None:
    """Reproduced defect: bool is a subclass of int, so tolerance=True
    passed math.isfinite/>=0 checks and behaved as tolerance=1."""
    with pytest.raises(ValueError, match="finite number"):
        compare_metric("m", _valid_obs(101.0), 100.0, unit="count", tolerance=True)


def test_boolean_dashboard_value_is_rejected_not_treated_as_numeric() -> None:
    """Reproduced defect: dashboard_value=True was treated as numeric 1
    with no type validation at all."""
    with pytest.raises(ValueError, match="finite number"):
        compare_metric("m", _valid_obs(1.0), True, unit="count", tolerance=1.0)


def test_string_dashboard_value_raises_value_error_not_uncaught_type_error() -> None:
    """Reproduced defect: a string dashboard value raised an uncaught
    TypeError from arithmetic, not a recorded/catchable ValueError."""
    with pytest.raises(ValueError, match="finite number"):
        compare_metric("m", _valid_obs(1.0), "42", unit="count", tolerance=1.0)


def test_zero_dashboard_value_gives_null_percentage_but_keeps_absolute_delta() -> None:
    result = compare_metric("m", _valid_obs(5.0), 0.0, unit="count", tolerance=1.0)
    assert result.percentage_delta is None
    assert result.absolute_delta == 5.0
    assert result.outcome is ComparisonOutcome.MISMATCH
