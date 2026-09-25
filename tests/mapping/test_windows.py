"""
Verifies timezone-aware window building rejects unconfirmed configuration,
never defaults to UTC, and converts local boundaries to UTC explicitly
(including across a DST transition, where a local day is NOT 24 UTC hours).
"""

from __future__ import annotations

from datetime import date

import pytest

from romtech_mcp.mapping.models import BaselineRules, TimezoneConfig
from romtech_mcp.mapping.windows import (
    TimezoneUnavailableError,
    UnconfirmedConfigurationError,
    build_reporting_day,
    build_sub_day_windows,
    build_windows,
    validate_timezone_available,
)

_CONFIRMED_NY = TimezoneConfig(iana_name="America/New_York", confirmed=True, confirmer="ziven", confirmed_date="2026-09-25")
_UNCONFIRMED = TimezoneConfig(iana_name="America/New_York", confirmed=False)


def test_unconfirmed_timezone_is_rejected() -> None:
    with pytest.raises(UnconfirmedConfigurationError):
        build_reporting_day(date(2026, 9, 23), _UNCONFIRMED)


def test_confirmed_timezone_builds_a_day_window() -> None:
    window = build_reporting_day(date(2026, 9, 23), _CONFIRMED_NY)
    assert window.local_start.isoformat() == "2026-09-23T00:00:00-04:00"
    assert window.local_end.isoformat() == "2026-09-24T00:00:00-04:00"
    # -04:00 EDT on 2026-09-23 -> UTC is local + 4 hours.
    assert window.utc_start.hour == 4
    assert (window.utc_end - window.utc_start).total_seconds() == 24 * 3600


def test_dst_transition_day_is_not_silently_24_hours() -> None:
    # 2026-11-01 is when US Eastern falls back from EDT to EST.
    window = build_reporting_day(date(2026, 11, 1), _CONFIRMED_NY)
    assert (window.utc_end - window.utc_start).total_seconds() == 25 * 3600


def test_unavailable_timezone_raises_a_clear_error(monkeypatch) -> None:
    import romtech_mcp.mapping.windows as windows_mod

    def raise_not_found(name):
        from zoneinfo import ZoneInfoNotFoundError

        raise ZoneInfoNotFoundError(name)

    monkeypatch.setattr(windows_mod, "ZoneInfo", raise_not_found)
    with pytest.raises(TimezoneUnavailableError):
        validate_timezone_available("Not/ARealZone")


def test_sub_day_windows_split_evenly() -> None:
    windows = build_sub_day_windows(date(2026, 9, 23), _CONFIRMED_NY, interval_width_minutes=360)  # 4 windows
    assert len(windows) == 4
    assert windows[0].local_start.hour == 0
    assert windows[-1].local_end == build_reporting_day(date(2026, 9, 23), _CONFIRMED_NY).local_end


def test_build_windows_rejects_unconfirmed_baseline() -> None:
    baseline = BaselineRules(confirmed=False, not_applicable=False)
    with pytest.raises(UnconfirmedConfigurationError):
        build_windows(date(2026, 9, 23), _CONFIRMED_NY, baseline)


def test_build_windows_not_applicable_baseline_returns_only_reference() -> None:
    baseline = BaselineRules(not_applicable=True)
    plan = build_windows(date(2026, 9, 23), _CONFIRMED_NY, baseline)
    assert plan.not_applicable is True
    assert plan.baseline == ()
    assert plan.reference is not None


def test_build_windows_uses_explicit_confirmed_reference_dates() -> None:
    baseline = BaselineRules(confirmed=True, reference_dates=("2026-09-16", "2026-09-09"))
    plan = build_windows(date(2026, 9, 23), _CONFIRMED_NY, baseline)
    assert [w.label for w in plan.baseline] == ["2026-09-16 (baseline)", "2026-09-09 (baseline)"]


def test_build_windows_uses_confirmed_weekday_lookback_rule() -> None:
    baseline = BaselineRules(confirmed=True, weekday_matching=True, lookback_count=2)
    plan = build_windows(date(2026, 9, 23), _CONFIRMED_NY, baseline)
    assert len(plan.baseline) == 2
    assert plan.baseline[0].local_start.date() == date(2026, 9, 16)
    assert plan.baseline[1].local_start.date() == date(2026, 9, 9)


def test_build_windows_confirmed_but_underspecified_baseline_is_rejected() -> None:
    baseline = BaselineRules(confirmed=True)  # confirmed, but no dates and no weekday_matching rule
    with pytest.raises(UnconfirmedConfigurationError):
        build_windows(date(2026, 9, 23), _CONFIRMED_NY, baseline)
