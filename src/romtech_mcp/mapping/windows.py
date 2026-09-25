"""
Timezone-aware reporting windows.

Every window here is built from a CONFIRMED business timezone and confirmed
baseline rules — never a default, and never UTC unless UTC was itself the
explicitly confirmed answer. Internally `[start, end)`: a window's end is
exclusive, matching ReportingWindow's own invariant. Converting local
boundaries to UTC is always explicit; nothing here ever assumes a local day
is exactly 24 UTC hours (DST transitions make that false twice a year).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import BaselineRules, ReportingWindow, TimezoneConfig


class UnconfirmedConfigurationError(RuntimeError):
    """Raised when window-building is asked to use a business decision
    (timezone, baseline) that hasn't actually been confirmed. Distinct from
    a bug: this is the expected result of trying to derive acceptance-grade
    windows before Ziven has answered the open questions."""


class TimezoneUnavailableError(RuntimeError):
    """The confirmed IANA timezone name can't actually be loaded — most
    likely the platform's tzdata is missing (common on a bare Windows
    install without the `tzdata` package). Never silently falls back to
    UTC or a naive datetime."""


def validate_timezone_available(iana_name: str) -> None:
    """Raises TimezoneUnavailableError with a clear, actionable message
    instead of letting zoneinfo's own exception (which doesn't mention the
    tzdata-package fix) surface directly."""
    try:
        ZoneInfo(iana_name)
    except ZoneInfoNotFoundError as exc:
        raise TimezoneUnavailableError(
            f"IANA timezone {iana_name!r} could not be loaded — the platform's tzdata "
            "database is likely missing. On Windows, ensure the 'tzdata' package "
            "(PyPI) is installed; it's a declared dependency of this project."
        ) from exc


def _require_confirmed_timezone(tz: TimezoneConfig, *, allow_unconfirmed: bool = False) -> ZoneInfo:
    if not tz.iana_name or (not tz.confirmed and not allow_unconfirmed):
        raise UnconfirmedConfigurationError(
            "Business reporting timezone is not confirmed — cannot build a reporting "
            "window from it. See docs/PBI-04-BE-mapping.md's configuration decisions. "
            "(Pass allow_unconfirmed=True only for an explicitly non-acceptance-grade, "
            "exploratory harness run — never for acceptance evidence.)"
        )
    validate_timezone_available(tz.iana_name)
    return ZoneInfo(tz.iana_name)


def build_reporting_day(
    reference_date: date, tz: TimezoneConfig, *, label: str | None = None, allow_unconfirmed: bool = False
) -> ReportingWindow:
    """One local calendar day `[local midnight, next local midnight)` in the
    confirmed business timezone, translated to UTC. Uses each boundary's own
    UTC offset — a DST-transition day is NOT silently treated as 24 hours.

    `allow_unconfirmed` exists ONLY for explicitly-labeled exploratory
    harness runs (e.g. the CLI's --exploratory flag) that still need a
    timezone NAME to build a window at all — it does not make the result
    acceptance evidence, and every caller using it must say so wherever the
    result is reported."""
    zone = _require_confirmed_timezone(tz, allow_unconfirmed=allow_unconfirmed)
    local_start = datetime(reference_date.year, reference_date.month, reference_date.day, tzinfo=zone)
    local_end = local_start + timedelta(days=1)
    return ReportingWindow(
        label=label or reference_date.isoformat(),
        local_start=local_start,
        local_end=local_end,
        utc_start=local_start.astimezone(ZoneInfo("UTC")),
        utc_end=local_end.astimezone(ZoneInfo("UTC")),
    )


def build_sub_day_windows(
    reference_date: date, tz: TimezoneConfig, *, interval_width_minutes: int
) -> list[ReportingWindow]:
    """Splits one local calendar day into equal-width windows — only used
    when a confirmed baseline rule specifies a sub-day interval width
    (discovery confirmed the reporting endpoint has no interval/bucketing
    parameter of its own; any narrower granularity here comes from making
    separate whole-window requests, not from the endpoint sub-dividing one
    response)."""
    if interval_width_minutes <= 0:
        raise ValueError("interval_width_minutes must be positive")
    day = build_reporting_day(reference_date, tz)
    step = timedelta(minutes=interval_width_minutes)
    windows: list[ReportingWindow] = []
    local_cursor = day.local_start
    index = 0
    while local_cursor < day.local_end:
        local_next = min(local_cursor + step, day.local_end)
        windows.append(
            ReportingWindow(
                label=f"{reference_date.isoformat()}#{index}",
                local_start=local_cursor,
                local_end=local_next,
                utc_start=local_cursor.astimezone(ZoneInfo("UTC")),
                utc_end=local_next.astimezone(ZoneInfo("UTC")),
            )
        )
        local_cursor = local_next
        index += 1
    return windows


@dataclass(frozen=True)
class BaselinePlan:
    """build_windows()'s result: the reference window plus its baseline
    comparison windows, kept distinct rather than merged into one flat list
    so a caller can't accidentally average the reference day into its own
    baseline."""

    reference: ReportingWindow
    baseline: tuple[ReportingWindow, ...]
    not_applicable: bool = False


def build_windows(reference_date: date, tz: TimezoneConfig, baseline: BaselineRules) -> BaselinePlan:
    """Builds the reference day's window plus its confirmed baseline
    comparison windows. Raises UnconfirmedConfigurationError if the
    timezone or baseline rules aren't confirmed — unless the baseline is
    explicitly marked not_applicable, in which case only the reference
    window is built (matching "a dashboard without a baseline records
    confirmed not_applicable, not an invented rule")."""
    reference = build_reporting_day(reference_date, tz, label=f"{reference_date.isoformat()} (reference)")

    if baseline.not_applicable:
        return BaselinePlan(reference=reference, baseline=(), not_applicable=True)

    if not baseline.confirmed:
        raise UnconfirmedConfigurationError(
            "Baseline rules are not confirmed and not marked not_applicable — cannot "
            "build baseline comparison windows. See docs/PBI-04-BE-mapping.md."
        )

    if baseline.reference_dates:
        # Explicit confirmed dates take precedence over any derived rule —
        # "eight prior same-weekday dates ... UTC were discovery/
        # implementation starting points, not confirmed business rules."
        dates = [date.fromisoformat(d) for d in baseline.reference_dates]
    elif baseline.weekday_matching and baseline.lookback_count > 0:
        dates = [reference_date - timedelta(weeks=i) for i in range(1, baseline.lookback_count + 1)]
    else:
        raise UnconfirmedConfigurationError(
            "Baseline is confirmed but specifies neither explicit reference_dates nor "
            "weekday_matching+lookback_count — nothing to build."
        )

    baseline_windows = tuple(
        build_reporting_day(d, tz, label=f"{d.isoformat()} (baseline)") for d in dates
    )
    return BaselinePlan(reference=reference, baseline=baseline_windows)
