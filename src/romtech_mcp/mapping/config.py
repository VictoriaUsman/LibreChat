"""
Loads the versioned, non-secret dashboard-mapping JSON configuration
(scope, timezone, SLA, baseline, source endpoint, and the metric mapping
rows themselves) into the typed models in models.py.

Deliberately separate from cxone/config.py, whose only job is transport/
authentication settings — this module owns business mapping configuration,
which has nothing to do with how the client authenticates.

An unanswered business decision loads as unconfirmed (models.py's own
defaults), not a plausible-looking default value. assert_ready_for_acceptance
is the one place that turns "unconfirmed" into a hard failure — everything
before that point (loading, inventory exploration, harness tests) is allowed
to work with unconfirmed configuration on purpose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import (
    BaselineRules,
    FieldPath,
    FormulaComponent,
    MetricAvailability,
    MetricFormula,
    MetricMapping,
    MappingStatus,
    ScopeConfig,
    SlaConfig,
    SourceEndpointConfig,
    TimezoneConfig,
    ValidationIssue,
)

CURRENT_SCHEMA_VERSION = 1


class MappingConfigError(RuntimeError):
    """The configuration file itself is malformed — a schema problem, not a
    business decision being unconfirmed (see UnconfirmedConfigurationError
    in windows.py for that distinct case)."""


@dataclass(frozen=True)
class MappingConfig:
    schema_version: int
    source: SourceEndpointConfig
    scope: ScopeConfig
    timezone: TimezoneConfig
    sla: SlaConfig
    baseline: BaselineRules
    metrics: tuple[MetricMapping, ...] = ()

    def metric(self, key: str) -> MetricMapping:
        for m in self.metrics:
            if m.key == key:
                return m
        raise KeyError(f"No metric mapping with key {key!r}")

    def assert_ready_for_acceptance(self, *, require_sla: bool = False, require_baseline: bool = False) -> None:
        """Raises UnconfirmedConfigurationError (imported lazily to avoid a
        config<->windows import cycle) if a business decision required for
        an acceptance-grade calculation hasn't actually been confirmed.
        Exploratory work (inventory fetches, harness tests) should call
        neither this nor derive_metric with confirmed=True expectations —
        see the source/scope modules for what still works unconditionally.
        """
        from .windows import UnconfirmedConfigurationError

        problems: list[str] = []
        if not self.scope.confirmed:
            problems.append("skill/team scope is not confirmed")
        elif not self.scope.included_skill_ids:
            # confirmed=True with an empty list is not "confirmed to include
            # everything" — nothing in ScopeConfig's contract says that; far
            # more likely it's a confirmation flag flipped without anyone
            # actually filling in the skill list. An empty inclusion list is
            # only meaningful as select_scope's own "no filter" pure-function
            # default, never as a genuine business decision.
            problems.append("scope is marked confirmed but included_skill_ids is empty")
        if not self.timezone.confirmed or not self.timezone.iana_name:
            problems.append("business reporting timezone is not confirmed")
        if require_sla and not (self.sla.confirmed or self.sla.not_applicable):
            problems.append("SLA configuration is not confirmed and not marked not_applicable")
        if require_baseline and not (self.baseline.confirmed or self.baseline.not_applicable):
            problems.append("baseline configuration is not confirmed and not marked not_applicable")
        if problems:
            raise UnconfirmedConfigurationError(
                "Cannot run an acceptance-grade calculation with unconfirmed configuration: "
                + "; ".join(problems)
            )


def _get(d: dict[str, Any], key: str, default: Any = None) -> Any:
    return d.get(key, default)


def _require_bool(d: dict[str, Any], key: str, default: bool) -> bool:
    """`bool("false")` is True — Python's own truthy-string trap. A
    confirmation flag loaded from JSON must be an actual JSON boolean
    (true/false), never a string, int, or other truthy/falsy value that
    would silently misrepresent an unconfirmed decision as confirmed."""
    value = d.get(key, default)
    if not isinstance(value, bool):
        raise MappingConfigError(f"{key!r} must be a JSON boolean (true/false), got {value!r}")
    return value


def _parse_source(d: dict[str, Any]) -> SourceEndpointConfig:
    return SourceEndpointConfig(
        endpoint_path=d["endpoint_path"],
        api_version=d["api_version"],
        param_start=d["param_start"],
        param_end=d["param_end"],
        response_array_key=_get(d, "response_array_key"),
        skill_id_field=d["skill_id_field"],
        verified=_require_bool(d, "verified", False),
    )


def _parse_scope(d: dict[str, Any]) -> ScopeConfig:
    return ScopeConfig(
        included_skill_ids=tuple(_get(d, "included_skill_ids", ())),
        excluded_skill_ids=tuple(_get(d, "excluded_skill_ids", ())),
        excluded_skill_reasons=dict(_get(d, "excluded_skill_reasons", {})),
        team_ids=tuple(_get(d, "team_ids", ())),
        skill_team_relationship=_get(d, "skill_team_relationship", "unconfirmed"),
        confirmed=_require_bool(d, "confirmed", False),
        confirmer=_get(d, "confirmer"),
        confirmed_date=_get(d, "confirmed_date"),
    )


def _parse_timezone(d: dict[str, Any]) -> TimezoneConfig:
    return TimezoneConfig(
        iana_name=_get(d, "iana_name"),
        confirmed=_require_bool(d, "confirmed", False),
        confirmer=_get(d, "confirmer"),
        confirmed_date=_get(d, "confirmed_date"),
    )


def _parse_sla(d: dict[str, Any]) -> SlaConfig:
    return SlaConfig(
        per_skill_thresholds_seconds=dict(_get(d, "per_skill_thresholds_seconds", {})),
        target_percentage=_get(d, "target_percentage"),
        numerator_field=_get(d, "numerator_field"),
        denominator_field=_get(d, "denominator_field"),
        short_abandon_seconds=_get(d, "short_abandon_seconds"),
        exclusions=tuple(_get(d, "exclusions", ())),
        confirmed=_require_bool(d, "confirmed", False),
        not_applicable=_require_bool(d, "not_applicable", False),
        confirmer=_get(d, "confirmer"),
        confirmed_date=_get(d, "confirmed_date"),
    )


def _parse_baseline(d: dict[str, Any]) -> BaselineRules:
    return BaselineRules(
        reference_dates=tuple(_get(d, "reference_dates", ())),
        weekday_matching=_require_bool(d, "weekday_matching", False),
        lookback_count=int(_get(d, "lookback_count", 0)),
        interval_width_minutes=_get(d, "interval_width_minutes"),
        aggregation=_get(d, "aggregation", "unconfirmed"),
        holiday_exclusions=tuple(_get(d, "holiday_exclusions", ())),
        zero_missing_day_handling=_get(d, "zero_missing_day_handling", "unconfirmed"),
        minimum_valid_samples=int(_get(d, "minimum_valid_samples", 0)),
        confirmed=_require_bool(d, "confirmed", False),
        not_applicable=_require_bool(d, "not_applicable", False),
        confirmer=_get(d, "confirmer"),
        confirmed_date=_get(d, "confirmed_date"),
    )


def _parse_field_path(d: dict[str, Any] | None) -> FieldPath | None:
    if d is None:
        return None
    return FieldPath(endpoint_path=d["endpoint_path"], api_version=d["api_version"], response_field=d["response_field"])


def _parse_formula(d: dict[str, Any] | None) -> MetricFormula | None:
    if d is None:
        return None
    components = []
    for c in d.get("components", []):
        source_raw = c["source"]
        source: FieldPath | str = _parse_field_path(source_raw) if isinstance(source_raw, dict) else source_raw
        components.append(FormulaComponent(name=c["name"], source=source))
    return MetricFormula(
        operation=d["operation"],
        components=tuple(components),
        denominator_zero_behavior=_get(d, "denominator_zero_behavior", "null"),
        rounding_ndigits=_get(d, "rounding_ndigits"),
    )


def _parse_metric(d: dict[str, Any]) -> MetricMapping:
    try:
        return MetricMapping(
            key=d["key"],
            dashboard_label=d["dashboard_label"],
            widget=d["widget"],
            definition_evidence=d["definition_evidence"],
            source=_parse_field_path(_get(d, "source")),
            request_params=dict(_get(d, "request_params", {})),
            unit=_get(d, "unit", "unconfirmed"),
            value_type=_get(d, "value_type", "unconfirmed"),
            grain=_get(d, "grain", "unconfirmed"),
            availability=MetricAvailability(_get(d, "availability", "unconfirmed")),
            availability_evidence=_get(d, "availability_evidence", ""),
            scope_join_keys=tuple(_get(d, "scope_join_keys", ())),
            team_attribution_supported=_require_bool(d, "team_attribution_supported", False),
            team_attribution_evidence=_get(d, "team_attribution_evidence", ""),
            formula=_parse_formula(_get(d, "formula")),
            sla_reference=_get(d, "sla_reference"),
            baseline_reference=_get(d, "baseline_reference"),
            status=MappingStatus(_get(d, "status", "unconfirmed")),
            evidence_refs=tuple(_get(d, "evidence_refs", ())),
            confirmer=_get(d, "confirmer"),
            confirmed_date=_get(d, "confirmed_date"),
            limitations=tuple(_get(d, "limitations", ())),
            unsupported_reason=_get(d, "unsupported_reason"),
        )
    except KeyError as exc:
        raise MappingConfigError(f"Metric mapping missing required field {exc}") from exc
    except ValueError as exc:
        raise MappingConfigError(f"Metric mapping {d.get('key', '<unknown>')!r} invalid: {exc}") from exc


def parse_mapping_config(data: dict[str, Any]) -> MappingConfig:
    schema_version = data.get("schema_version")
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise MappingConfigError(
            f"Unsupported schema_version {schema_version!r}; expected {CURRENT_SCHEMA_VERSION}"
        )
    try:
        source = _parse_source(data["source"])
        scope = _parse_scope(data.get("scope", {}))
        timezone = _parse_timezone(data.get("timezone", {}))
        sla = _parse_sla(data.get("sla", {}))
        baseline = _parse_baseline(data.get("baseline", {}))
    except KeyError as exc:
        raise MappingConfigError(f"Missing required configuration section/field: {exc}") from exc

    metrics = tuple(_parse_metric(m) for m in data.get("metrics", []))
    keys_seen: set[str] = set()
    for m in metrics:
        if m.key in keys_seen:
            raise MappingConfigError(f"Duplicate metric key {m.key!r}")
        keys_seen.add(m.key)

    return MappingConfig(
        schema_version=schema_version, source=source, scope=scope, timezone=timezone,
        sla=sla, baseline=baseline, metrics=metrics,
    )


def load_mapping_config(path: str | Path) -> MappingConfig:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise MappingConfigError(f"Mapping config file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise MappingConfigError(f"Mapping config file {path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise MappingConfigError(f"Mapping config file {path} must contain a JSON object")
    return parse_mapping_config(raw)


def validate_mapping(config: MappingConfig) -> list[ValidationIssue]:
    """Structural/internal-consistency checks on the mapping contract
    itself — not a business-correctness check (that needs Ziven's
    confirmation and reconciliation, see reconcile.py). Every issue found
    here is a defect in the mapping file, not a "results are wrong" signal.
    """
    issues: list[ValidationIssue] = []
    metric_keys = {m.key for m in config.metrics}

    for m in config.metrics:
        if m.status == MappingStatus.UNSUPPORTED and not m.unsupported_reason:
            issues.append(ValidationIssue(m.key, "unsupported_reason", "unsupported metric has no reason recorded"))
        if m.status in (MappingStatus.CANDIDATE, MappingStatus.VALIDATED) and m.formula is None:
            issues.append(ValidationIssue(m.key, "formula", f"status={m.status.value} but no formula is declared"))
        if m.status in (MappingStatus.CANDIDATE, MappingStatus.VALIDATED) and not m.evidence_refs:
            issues.append(
                ValidationIssue(m.key, "evidence_refs", f"status={m.status.value} but no evidence_refs recorded",
                                severity="warning")
            )
        if m.availability == MetricAvailability.BOTH and not m.availability_evidence:
            issues.append(
                ValidationIssue(m.key, "availability_evidence",
                                "availability=both must document evidence for BOTH contracts separately")
            )
        if m.formula is not None:
            for component in m.formula.components:
                if isinstance(component.source, str) and component.source not in metric_keys:
                    issues.append(
                        ValidationIssue(m.key, "formula.components",
                                        f"component {component.name!r} references unknown metric key {component.source!r}")
                    )
        if m.formula is not None and m.formula.operation == "ratio" and len(m.formula.components) != 2:
            issues.append(
                ValidationIssue(m.key, "formula.components", "operation=ratio requires exactly 2 components")
            )
        if m.status == MappingStatus.VALIDATED and (not m.confirmer or not m.confirmed_date):
            issues.append(ValidationIssue(m.key, "confirmer", "status=validated but no confirmer/confirmed_date recorded"))

    return issues
