"""
Reference calculations for mapped metrics, and dashboard/API comparison.

Formulas are the fixed, declared operations in MetricFormula.operation
(models.FORMULA_OPERATIONS) — never an arbitrary executable expression
string. Numeric field validation mirrors the same discipline PBI-01's
discovery work established: missing/null/malformed is UNKNOWN, never
silently zero; booleans and non-finite values are rejected; a numeric
string and its numeric equivalent mean the same thing.
"""

from __future__ import annotations

import math

from .models import (
    Comparison,
    ComparisonOutcome,
    CoverageState,
    FieldValueState,
    FormulaComponent,
    MetricFormula,
    MetricMapping,
    MetricObservation,
    ReportingWindow,
    ScopedObservations,
)


def parse_numeric_field(value: object, *, reject_negative: bool = True) -> tuple[float | None, FieldValueState]:
    """Returns (value, VALID) for an actually-present, valid numeric field,
    or (None, UNKNOWN) for anything absent/null/malformed. Booleans and
    non-finite values are rejected. Numeric zero and the string "0" mean
    the same thing."""
    if value is None or isinstance(value, bool):
        return None, FieldValueState.UNKNOWN
    if isinstance(value, (int, float)):
        num = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None, FieldValueState.UNKNOWN
        try:
            num = float(stripped)
        except ValueError:
            return None, FieldValueState.UNKNOWN
    else:
        return None, FieldValueState.UNKNOWN
    if num != num or num in (float("inf"), float("-inf")):  # NaN / inf
        return None, FieldValueState.UNKNOWN
    if reject_negative and num < 0:
        return None, FieldValueState.UNKNOWN
    return num, FieldValueState.VALID


def _unknown(mapping: MetricMapping, window: ReportingWindow, note: str) -> MetricObservation:
    return MetricObservation(
        metric_key=mapping.key, window=window, value=None, value_state=FieldValueState.UNKNOWN,
        unit=mapping.unit, notes=(note,),
    )


def _valid(mapping: MetricMapping, window: ReportingWindow, value: float, formula: MetricFormula) -> MetricObservation:
    if formula.rounding_ndigits is not None:
        value = round(value, formula.rounding_ndigits)
    return MetricObservation(
        metric_key=mapping.key, window=window, value=value, value_state=FieldValueState.VALID, unit=mapping.unit,
    )


def _component_values(component: FormulaComponent, scoped: ScopedObservations, *, reject_negative: bool) -> list[float | None]:
    if isinstance(component.source, str):
        raise ValueError(
            f"Component {component.name!r} references another metric key ({component.source!r}) — composite "
            "formulas referencing a prior MetricObservation are not supported by derive_metric; resolve and "
            "supply that metric's own FieldPath-based components directly, or extend this function deliberately."
        )
    field_path = component.source
    if field_path.endpoint_path != scoped.source_endpoint_path or field_path.api_version != scoped.source_api_version:
        # The component NAMES a specific endpoint/version — reading its
        # field from whatever rows happen to be in `scoped` regardless of
        # where they actually came from would silently attribute a value
        # to the wrong source the moment a mapping ever mixes endpoints.
        raise ValueError(
            f"Component {component.name!r} declares source {field_path.endpoint_path!r}@{field_path.api_version!r}, "
            f"but the scoped observations came from {scoped.source_endpoint_path!r}@{scoped.source_api_version!r} — "
            "refusing to read this field from a mismatched source."
        )
    field_name = field_path.response_field
    values: list[float | None] = []
    for row in scoped.rows:
        value, state = parse_numeric_field(row.raw.get(field_name), reject_negative=reject_negative)
        values.append(value if state is FieldValueState.VALID else None)
    return values


def derive_metric(
    mapping: MetricMapping, scoped: ScopedObservations, window: ReportingWindow, *, reject_negative: bool = True
) -> MetricObservation:
    """Computes one metric's value for one window from already-scoped rows.
    Any contributing row with an invalid/missing field makes the WHOLE
    result unknown — never silently treated as if that row contributed
    zero. An empty scope (no in-scope rows at all) is likewise unknown, not
    zero: it could mean a real all-zero day, or it could mean the scope/
    fetch missed something; this harness does not guess which.

    Incomplete coverage (a requested skill ID never came back, an
    unverified pagination marker was seen, or the fetch itself was only
    partial/unknown) makes the WHOLE result unknown too — a sum/ratio over
    whatever rows happened to be present is not the same value as one over
    the full requested scope, and reporting it as if it were would let a
    genuinely incomplete fetch pass reconciliation by accident."""
    if mapping.formula is None:
        raise ValueError(f"Metric {mapping.key!r} has no declared formula — cannot derive a value")
    formula = mapping.formula

    if scoped.coverage is not CoverageState.COMPLETE:
        detail = f"missing IDs: {sorted(scoped.missing_ids)}" if scoped.missing_ids else f"coverage={scoped.coverage.value}"
        return _unknown(mapping, window, f"scope coverage is not complete ({detail}) — cannot compute a trustworthy value")

    if not scoped.rows:
        return _unknown(mapping, window, "no in-scope rows for this window")

    def values_for(component: FormulaComponent) -> list[float | None]:
        return _component_values(component, scoped, reject_negative=reject_negative)

    if formula.operation == "identity":
        if len(formula.components) != 1:
            raise ValueError("identity requires exactly one component")
        values = values_for(formula.components[0])
        if len(values) != 1:
            return _unknown(mapping, window, f"identity requires exactly one contributing row, got {len(values)}")
        if values[0] is None:
            return _unknown(mapping, window, "the single contributing row's field was invalid/missing")
        return _valid(mapping, window, values[0], formula)

    if formula.operation == "sum":
        total = 0.0
        for component in formula.components:
            values = values_for(component)
            if any(v is None for v in values):
                return _unknown(mapping, window, f"component {component.name!r} was invalid/missing on at least one in-scope row")
            total += sum(values)
        return _valid(mapping, window, total, formula)

    if formula.operation == "average":
        if len(formula.components) != 1:
            raise ValueError("average requires exactly one component")
        values = values_for(formula.components[0])
        if any(v is None for v in values):
            return _unknown(mapping, window, "at least one in-scope row's value was invalid/missing")
        return _valid(mapping, window, sum(values) / len(values), formula)

    if formula.operation in ("ratio", "weighted_average"):
        if len(formula.components) != 2:
            raise ValueError(f"{formula.operation} requires exactly 2 components")
        a_values = values_for(formula.components[0])
        b_values = values_for(formula.components[1])
        if any(v is None for v in a_values) or any(v is None for v in b_values):
            return _unknown(mapping, window, "at least one component was invalid/missing on an in-scope row")
        if formula.operation == "ratio":
            numerator = sum(a_values)  # type: ignore[arg-type]
            denominator = sum(b_values)  # type: ignore[arg-type]
        else:  # weighted_average: components = [value, weight]
            numerator = sum(v * w for v, w in zip(a_values, b_values))  # type: ignore[operator]
            denominator = sum(b_values)  # type: ignore[arg-type]
        if denominator == 0:
            if formula.denominator_zero_behavior == "zero":
                return _valid(mapping, window, 0.0, formula)
            suffix = " (explicitly configured as unresolved on a zero denominator)" if formula.denominator_zero_behavior == "unresolved" else ""
            return _unknown(mapping, window, f"denominator is zero{suffix}")
        return _valid(mapping, window, numerator / denominator, formula)

    raise ValueError(f"Unhandled formula operation {formula.operation!r}")  # pragma: no cover - guarded by MetricFormula.__post_init__


def _require_finite_number(value: object, name: str, *, allow_negative: bool) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number, got {value!r} ({type(value).__name__})")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    if not allow_negative and value < 0:
        raise ValueError(f"{name} must be non-negative, got {value!r}")


def compare_metric(
    metric_key: str, api_observation: MetricObservation, dashboard_value: float | None, *, unit: str, tolerance: float | None
) -> Comparison:
    """Never silently enlarges tolerance or changes scope to force a match
    — an out-of-tolerance result stays MISMATCH; a missing required input
    stays UNRESOLVED. If the dashboard value is exactly zero, percentage
    delta is null (division by zero has no meaningful percentage) but the
    absolute difference is still reported.

    Both `tolerance` and `dashboard_value` are validated as actual finite
    numbers — never a bool (a subclass of int in Python, so `True`/`False`
    would otherwise silently behave as 1/0 and pass math.isfinite/>=0
    checks) and never any other non-numeric type. A malformed value (e.g. a
    string from a hand-edited JSON file) raises ValueError, which the CLI
    turns into a recorded 'unresolved' result — never an uncaught TypeError
    from arithmetic on the wrong type, which would crash before any
    manifest is saved."""
    if tolerance is not None:
        _require_finite_number(tolerance, "tolerance", allow_negative=False)
    if dashboard_value is not None:
        _require_finite_number(dashboard_value, "dashboard_value", allow_negative=True)

    if api_observation.value_state is not FieldValueState.VALID or api_observation.value is None:
        return Comparison(
            metric_key=metric_key, dashboard_value=dashboard_value, api_value=None, unit=unit,
            absolute_delta=None, percentage_delta=None, tolerance=tolerance,
            outcome=ComparisonOutcome.UNRESOLVED,
            explanation="API-derived value is unknown/unresolved for this window — cannot compare"
            + (f" ({'; '.join(api_observation.notes)})" if api_observation.notes else ""),
        )

    if dashboard_value is None:
        return Comparison(
            metric_key=metric_key, dashboard_value=None, api_value=api_observation.value, unit=unit,
            absolute_delta=None, percentage_delta=None, tolerance=tolerance,
            outcome=ComparisonOutcome.UNRESOLVED,
            explanation="No dashboard value captured for this metric/period — cannot compare",
        )

    absolute_delta = api_observation.value - dashboard_value
    percentage_delta = None if dashboard_value == 0 else (absolute_delta / dashboard_value) * 100.0

    if tolerance is None:
        return Comparison(
            metric_key=metric_key, dashboard_value=dashboard_value, api_value=api_observation.value, unit=unit,
            absolute_delta=absolute_delta, percentage_delta=percentage_delta, tolerance=None,
            outcome=ComparisonOutcome.UNRESOLVED,
            explanation="No agreed tolerance configured for this metric — cannot classify match/mismatch",
        )

    if abs(absolute_delta) <= tolerance:
        outcome, explanation = ComparisonOutcome.MATCH, f"Within agreed tolerance ({tolerance})"
    else:
        outcome, explanation = ComparisonOutcome.MISMATCH, f"Absolute delta {absolute_delta} exceeds agreed tolerance {tolerance}"

    return Comparison(
        metric_key=metric_key, dashboard_value=dashboard_value, api_value=api_observation.value, unit=unit,
        absolute_delta=absolute_delta, percentage_delta=percentage_delta, tolerance=tolerance,
        outcome=outcome, explanation=explanation,
    )
