"""
Typed models for the dashboard/API metric mapping (PBI-04).

Every "unconfirmed" default here is deliberate: a business decision (scope,
timezone, SLA, baseline) that hasn't actually been confirmed with Ziven must
be represented as unconfirmed, never silently defaulted to something that
looks plausible. config.py enforces that unconfirmed inputs cannot be used
for an acceptance-grade calculation; these models just make the state
representable in the first place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MetricAvailability(str, Enum):
    """Whether a metric can be reproduced from historical data, only from a
    live/current snapshot, both (with separately validated contracts), or
    the question hasn't been answered yet. A date parameter accepted by an
    endpoint is NOT by itself evidence of historical semantics."""

    HISTORICAL = "historical"
    LIVE_ONLY = "live_only"
    BOTH = "both"
    UNCONFIRMED = "unconfirmed"


class MappingStatus(str, Enum):
    UNCONFIRMED = "unconfirmed"
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    UNSUPPORTED = "unsupported"


class FieldValueState(str, Enum):
    """A validated field's state — never conflate "missing" with "zero".
    Zero is only ever VALID, for a field that was actually present and
    passed numeric validation."""

    VALID = "valid"
    UNKNOWN = "unknown"  # absent, null, malformed, or otherwise unvalidated


class CoverageState(str, Enum):
    """Whether a fetch actually covered everything it was scoped to."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"
    UNKNOWN = "unknown"  # e.g. pagination completeness could not be established


class ComparisonOutcome(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNRESOLVED = "unresolved"  # required inputs were unknown/unconfirmed — never silently skipped


# --------------------------------------------------------------------------
# Source field / formula declarations
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldPath:
    """Where one value comes from in a validated API response. `response_field`
    is the field name within one normalized row — this harness's one
    confirmed endpoint shape returns one aggregated row per skill per
    requested window, not per-interval buckets, so there is no deeper path
    syntax to support until a different shape is actually confirmed."""

    endpoint_path: str
    api_version: str
    response_field: str


@dataclass(frozen=True)
class FormulaComponent:
    """One named input to a declared formula. `source` is either a FieldPath
    (a raw API field) or another metric's key (a composite metric) — never
    an arbitrary executable expression string."""

    name: str
    source: FieldPath | str


# The fixed, closed set of formula operations this harness knows how to
# compute. Adding a new dashboard formula means adding a named operation
# here, reviewed like any other code change — not accepting an arbitrary
# expression string that could execute anything.
FORMULA_OPERATIONS = frozenset({"identity", "sum", "ratio", "weighted_average", "average"})


@dataclass(frozen=True)
class MetricFormula:
    operation: str
    components: tuple[FormulaComponent, ...]
    # "null": a zero denominator makes the metric UNKNOWN, not zero or 100%.
    # "zero": treated as zero (rare; must be an explicitly confirmed rule).
    # "unresolved": always reported as unresolved, never computed.
    denominator_zero_behavior: str = "null"
    rounding_ndigits: int | None = None

    def __post_init__(self) -> None:
        if self.operation not in FORMULA_OPERATIONS:
            raise ValueError(f"Unknown formula operation {self.operation!r}; must be one of {sorted(FORMULA_OPERATIONS)}")
        if self.denominator_zero_behavior not in {"null", "zero", "unresolved"}:
            raise ValueError(f"Unknown denominator_zero_behavior {self.denominator_zero_behavior!r}")


# --------------------------------------------------------------------------
# Metric mapping contract (one row per dashboard metric)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricMapping:
    key: str
    dashboard_label: str
    widget: str
    definition_evidence: str

    source: FieldPath | None = None
    request_params: dict[str, str] = field(default_factory=dict)

    unit: str = "unconfirmed"
    value_type: str = "unconfirmed"
    grain: str = "unconfirmed"

    availability: MetricAvailability = MetricAvailability.UNCONFIRMED
    availability_evidence: str = ""

    scope_join_keys: tuple[str, ...] = ()
    team_attribution_supported: bool = False
    team_attribution_evidence: str = ""

    formula: MetricFormula | None = None

    sla_reference: str | None = None
    baseline_reference: str | None = None

    status: MappingStatus = MappingStatus.UNCONFIRMED
    evidence_refs: tuple[str, ...] = ()
    confirmer: str | None = None
    confirmed_date: str | None = None
    limitations: tuple[str, ...] = ()
    unsupported_reason: str | None = None


@dataclass(frozen=True)
class ValidationIssue:
    metric_key: str
    field: str
    message: str
    severity: str = "error"  # "error" | "warning"


# --------------------------------------------------------------------------
# Business configuration (scope / timezone / SLA / baseline) — each one
# individually confirmable, so a decision that IS confirmed can be used even
# while another is still pending.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ScopeConfig:
    included_skill_ids: tuple[str, ...] = ()
    excluded_skill_ids: tuple[str, ...] = ()
    excluded_skill_reasons: dict[str, str] = field(default_factory=dict)
    team_ids: tuple[str, ...] = ()
    # "intersection" | "union" | "unconfirmed" — whether skill+team scope
    # selection means both must match or either is sufficient.
    skill_team_relationship: str = "unconfirmed"
    confirmed: bool = False
    confirmer: str | None = None
    confirmed_date: str | None = None


@dataclass(frozen=True)
class TimezoneConfig:
    iana_name: str | None = None
    confirmed: bool = False
    confirmer: str | None = None
    confirmed_date: str | None = None


@dataclass(frozen=True)
class SlaConfig:
    per_skill_thresholds_seconds: dict[str, float] = field(default_factory=dict)
    target_percentage: float | None = None
    numerator_field: str | None = None
    denominator_field: str | None = None
    short_abandon_seconds: float | None = None
    exclusions: tuple[str, ...] = ()
    confirmed: bool = False
    not_applicable: bool = False
    confirmer: str | None = None
    confirmed_date: str | None = None


@dataclass(frozen=True)
class BaselineRules:
    reference_dates: tuple[str, ...] = ()
    weekday_matching: bool = False
    lookback_count: int = 0
    interval_width_minutes: int | None = None
    aggregation: str = "unconfirmed"
    holiday_exclusions: tuple[str, ...] = ()
    zero_missing_day_handling: str = "unconfirmed"
    minimum_valid_samples: int = 0
    confirmed: bool = False
    not_applicable: bool = False
    confirmer: str | None = None
    confirmed_date: str | None = None


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceEndpointConfig:
    """Where the mapping harness reads reporting data from. Discovery is a
    lead, not a confirmed schema for THIS purpose — `verified` records
    whether these specific values have actually been checked against a real
    response for this endpoint, independent of what discovery found for its
    own (different) purpose."""

    endpoint_path: str
    api_version: str
    param_start: str
    param_end: str
    response_array_key: str | None
    skill_id_field: str
    verified: bool = False


@dataclass(frozen=True)
class ReportingWindow:
    """A confirmed-timezone local window and its explicit UTC translation.
    Internally `[start, end)` — end is exclusive."""

    label: str
    local_start: datetime
    local_end: datetime
    utc_start: datetime
    utc_end: datetime

    def __post_init__(self) -> None:
        if self.local_start.tzinfo is None or self.utc_start.tzinfo is None:
            raise ValueError("ReportingWindow requires timezone-aware datetimes")
        if self.local_end <= self.local_start:
            raise ValueError("local_end must be after local_start")
        if self.utc_end <= self.utc_start:
            raise ValueError("utc_end must be after utc_start")


# --------------------------------------------------------------------------
# Fetched / scoped / derived observations
# --------------------------------------------------------------------------


@dataclass
class NormalizedRow:
    """One row from a validated API response. `skill_id` is None if the
    configured skill-id field was absent — that row can never silently
    count as in-scope."""

    skill_id: str | None
    raw: dict[str, Any]


@dataclass
class SourceObservation:
    """Provenance-carrying result of one fetch for one window. `coverage`
    reflects whether pagination (if any) was known to be complete — unknown
    pagination makes the whole fetch's coverage UNKNOWN, never assumed
    complete."""

    window: ReportingWindow
    endpoint_path: str
    api_version: str
    request_params: dict[str, str]
    requested_at_utc: datetime
    rows: list[NormalizedRow] = field(default_factory=list)
    coverage: CoverageState = CoverageState.UNKNOWN
    issues: list[ValidationIssue] = field(default_factory=list)
    attempt_count: int = 1


@dataclass
class ScopedObservations:
    """select_scope()'s result — every ID bucket tracked explicitly so a
    caller can tell "everything we asked for came back and was in scope"
    from "some IDs never appeared" without re-deriving it from raw rows."""

    requested_ids: frozenset[str]
    returned_ids: frozenset[str]
    included_ids: frozenset[str]
    excluded_ids: frozenset[str]
    missing_ids: frozenset[str]
    duplicate_ids: frozenset[str]
    rows: list[NormalizedRow]
    coverage: CoverageState
    # Which endpoint/version these rows actually came from — carried
    # through so a formula component naming a DIFFERENT endpoint/version
    # can be rejected rather than silently read from the wrong source.
    source_endpoint_path: str
    source_api_version: str


@dataclass
class MetricObservation:
    metric_key: str
    window: ReportingWindow
    value: float | None
    value_state: FieldValueState
    unit: str
    components_used: dict[str, float | None] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


@dataclass
class Comparison:
    metric_key: str
    dashboard_value: float | None
    api_value: float | None
    unit: str
    absolute_delta: float | None
    percentage_delta: float | None
    tolerance: float | None
    outcome: ComparisonOutcome
    explanation: str
