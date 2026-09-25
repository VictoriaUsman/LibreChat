"""Verifies the model-level invariants that guard against silently building
an invalid formula or window, independent of any loader/business logic."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from romtech_mcp.mapping.models import FormulaComponent, MetricFormula, ReportingWindow


def test_formula_rejects_unknown_operation() -> None:
    with pytest.raises(ValueError):
        MetricFormula(operation="subtract_and_hope", components=(FormulaComponent("x", "y"),))


def test_formula_rejects_unknown_denominator_zero_behavior() -> None:
    with pytest.raises(ValueError):
        MetricFormula(operation="sum", components=(), denominator_zero_behavior="explode")


def test_window_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError):
        ReportingWindow(
            label="x",
            local_start=datetime(2026, 9, 23),
            local_end=datetime(2026, 9, 24, tzinfo=timezone.utc),
            utc_start=datetime(2026, 9, 23, tzinfo=timezone.utc),
            utc_end=datetime(2026, 9, 24, tzinfo=timezone.utc),
        )


def test_window_rejects_non_increasing_bounds() -> None:
    with pytest.raises(ValueError):
        ReportingWindow(
            label="x",
            local_start=datetime(2026, 9, 24, tzinfo=timezone.utc),
            local_end=datetime(2026, 9, 23, tzinfo=timezone.utc),
            utc_start=datetime(2026, 9, 23, tzinfo=timezone.utc),
            utc_end=datetime(2026, 9, 24, tzinfo=timezone.utc),
        )
