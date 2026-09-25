"""
Verifies the mapping config loader keeps unconfirmed business decisions
unconfirmed (never a plausible-looking default), rejects malformed config
distinctly from unconfirmed business config, and that assert_ready_for_acceptance
actually blocks on what it claims to.
"""

from __future__ import annotations

import json

import pytest

from romtech_mcp.mapping.config import (
    CURRENT_SCHEMA_VERSION,
    MappingConfigError,
    load_mapping_config,
    parse_mapping_config,
    validate_mapping,
)
from romtech_mcp.mapping.models import MappingStatus
from romtech_mcp.mapping.windows import UnconfirmedConfigurationError

_MINIMAL_SOURCE = {
    "endpoint_path": "/skills/summary",
    "api_version": "v27.0",
    "param_start": "startDate",
    "param_end": "endDate",
    "response_array_key": "skillSummaries",
    "skill_id_field": "skillId",
}


def _base(**overrides) -> dict:
    data = {"schema_version": CURRENT_SCHEMA_VERSION, "source": dict(_MINIMAL_SOURCE)}
    data.update(overrides)
    return data


def test_minimal_config_loads_with_everything_unconfirmed_by_default() -> None:
    config = parse_mapping_config(_base())
    assert config.scope.confirmed is False
    assert config.timezone.confirmed is False
    assert config.timezone.iana_name is None
    assert config.sla.confirmed is False
    assert config.baseline.confirmed is False
    assert config.metrics == ()


def test_wrong_schema_version_is_rejected() -> None:
    with pytest.raises(MappingConfigError):
        parse_mapping_config(_base(schema_version=999))


def test_missing_source_section_is_rejected() -> None:
    with pytest.raises(MappingConfigError):
        parse_mapping_config({"schema_version": CURRENT_SCHEMA_VERSION})


def test_duplicate_metric_keys_are_rejected() -> None:
    metric = {"key": "aht", "dashboard_label": "AHT", "widget": "w", "definition_evidence": "e"}
    with pytest.raises(MappingConfigError):
        parse_mapping_config(_base(metrics=[metric, dict(metric)]))


def test_assert_ready_for_acceptance_blocks_on_unconfirmed_scope_and_timezone() -> None:
    config = parse_mapping_config(_base())
    with pytest.raises(UnconfirmedConfigurationError):
        config.assert_ready_for_acceptance()


def test_assert_ready_for_acceptance_passes_once_scope_and_timezone_confirmed() -> None:
    config = parse_mapping_config(
        _base(
            scope={"confirmed": True, "included_skill_ids": ["1"]},
            timezone={"iana_name": "UTC", "confirmed": True},
        )
    )
    config.assert_ready_for_acceptance()  # must not raise


def test_assert_ready_for_acceptance_can_require_sla_and_baseline() -> None:
    config = parse_mapping_config(
        _base(
            scope={"confirmed": True},
            timezone={"iana_name": "UTC", "confirmed": True},
        )
    )
    with pytest.raises(UnconfirmedConfigurationError):
        config.assert_ready_for_acceptance(require_sla=True)
    with pytest.raises(UnconfirmedConfigurationError):
        config.assert_ready_for_acceptance(require_baseline=True)


def test_string_confirmed_flag_is_rejected_not_coerced_truthy() -> None:
    """Reproduced defect: bool("false") is True in Python — a JSON string
    "false" for a confirmation flag must be rejected, not silently coerced."""
    with pytest.raises(MappingConfigError):
        parse_mapping_config(_base(scope={"confirmed": "false", "included_skill_ids": ["1"]}))


def test_confirmed_scope_with_no_skill_ids_fails_readiness() -> None:
    """Reproduced defect: confirmed=True with an empty skill list passed
    assert_ready_for_acceptance — a flipped flag with nothing behind it."""
    config = parse_mapping_config(
        _base(scope={"confirmed": True}, timezone={"iana_name": "UTC", "confirmed": True})
    )
    with pytest.raises(UnconfirmedConfigurationError):
        config.assert_ready_for_acceptance()


def test_load_mapping_config_missing_file_raises_mapping_config_error(tmp_path) -> None:
    with pytest.raises(MappingConfigError):
        load_mapping_config(tmp_path / "does-not-exist.json")


def test_load_mapping_config_invalid_json_raises_mapping_config_error(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(MappingConfigError):
        load_mapping_config(path)


def test_load_mapping_config_round_trips_through_a_real_file(tmp_path) -> None:
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(_base()), encoding="utf-8")
    config = load_mapping_config(path)
    assert config.source.endpoint_path == "/skills/summary"


# -- validate_mapping ----------------------------------------------------------


def _metric(**overrides) -> dict:
    m = {"key": "aht", "dashboard_label": "AHT", "widget": "w", "definition_evidence": "e"}
    m.update(overrides)
    return m


def test_unsupported_metric_without_reason_is_flagged() -> None:
    config = parse_mapping_config(_base(metrics=[_metric(status="unsupported")]))
    issues = validate_mapping(config)
    assert any(i.field == "unsupported_reason" for i in issues)


def test_unsupported_metric_with_reason_is_not_flagged() -> None:
    config = parse_mapping_config(_base(metrics=[_metric(status="unsupported", unsupported_reason="no field exists")]))
    issues = validate_mapping(config)
    assert not any(i.field == "unsupported_reason" for i in issues)


def test_candidate_status_without_formula_is_flagged() -> None:
    config = parse_mapping_config(_base(metrics=[_metric(status="candidate")]))
    issues = validate_mapping(config)
    assert any(i.field == "formula" for i in issues)


def test_validated_status_without_confirmer_is_flagged() -> None:
    formula = {"operation": "identity", "components": [{"name": "x", "source": {"endpoint_path": "/skills/summary", "api_version": "v27.0", "response_field": "x"}}]}
    config = parse_mapping_config(
        _base(metrics=[_metric(status="validated", formula=formula, evidence_refs=["ref"])])
    )
    issues = validate_mapping(config)
    assert any(i.field == "confirmer" for i in issues)


def test_formula_referencing_unknown_metric_key_is_flagged() -> None:
    formula = {"operation": "sum", "components": [{"name": "other", "source": "does-not-exist"}]}
    config = parse_mapping_config(_base(metrics=[_metric(status="candidate", formula=formula, evidence_refs=["ref"])]))
    issues = validate_mapping(config)
    assert any("unknown metric key" in i.message for i in issues)


def test_ratio_with_wrong_component_count_is_flagged() -> None:
    field = {"endpoint_path": "/skills/summary", "api_version": "v27.0", "response_field": "x"}
    formula = {"operation": "ratio", "components": [{"name": "only_one", "source": field}]}
    config = parse_mapping_config(_base(metrics=[_metric(status="candidate", formula=formula, evidence_refs=["ref"])]))
    issues = validate_mapping(config)
    assert any("ratio requires exactly 2" in i.message for i in issues)
