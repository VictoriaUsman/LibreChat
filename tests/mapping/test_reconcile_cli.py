"""
End-to-end test of scripts/reconcile_dashboard.py in offline fixture mode —
no network call, no credentials. Verifies the whole pipeline (config load ->
window build -> fixture fetch -> scope -> derive -> compare -> manifest)
wires together, and that unconfirmed configuration is refused by default
but permitted with --exploratory.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "reconcile_dashboard.py"
_spec = importlib.util.spec_from_file_location("reconcile_dashboard", _SCRIPT_PATH)
reconcile_dashboard = importlib.util.module_from_spec(_spec)
sys.modules["reconcile_dashboard"] = reconcile_dashboard
_spec.loader.exec_module(reconcile_dashboard)  # type: ignore[union-attr]


def _write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _config_dict(**overrides) -> dict:
    data = {
        "schema_version": 1,
        "source": {
            "endpoint_path": "/skills/summary", "api_version": "v27.0", "param_start": "startDate",
            "param_end": "endDate", "response_array_key": "skillSummaries", "skill_id_field": "skillId",
        },
        "scope": {"included_skill_ids": ["1"], "confirmed": True},
        "timezone": {"iana_name": "UTC", "confirmed": True},
        "metrics": [
            {
                "key": "offered", "dashboard_label": "Contacts Offered", "widget": "w", "definition_evidence": "e",
                "status": "candidate", "availability": "historical", "evidence_refs": ["ref"],
                "formula": {
                    "operation": "sum",
                    "components": [{"name": "offered", "source": {"endpoint_path": "/skills/summary", "api_version": "v27.0", "response_field": "contactsOffered"}}],
                },
            }
        ],
    }
    data.update(overrides)
    return data


def test_exploratory_fixture_run_matches_dashboard_value(tmp_path: Path) -> None:
    config_path = _write_json(tmp_path / "config.json", _config_dict())
    fixture_path = _write_json(tmp_path / "fixture.json", {
        "2026-09-23": {"skillSummaries": [{"skillId": "1", "contactsOffered": 42}]},
    })
    dashboard_path = _write_json(tmp_path / "dashboard.json", {"offered": 42})
    tolerances_path = _write_json(tmp_path / "tolerances.json", {"offered": 1})

    exit_code = reconcile_dashboard.main([
        "--config", str(config_path), "--reference-date", "2026-09-23", "--fixture", str(fixture_path),
        "--dashboard-values", str(dashboard_path), "--tolerances", str(tolerances_path),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert exit_code == 0
    manifests = list((tmp_path / "out").glob("*.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["results"][0]["outcome"] == "match"
    assert manifest["required_failure"] is False


@pytest.mark.parametrize("field", ["dashboard_value", "tolerance"])
@pytest.mark.parametrize("invalid", [True, False, "1", "invalid", float("nan"), float("inf"), float("-inf")])
def test_invalid_comparison_input_saves_unresolved_manifest(tmp_path: Path, field: str, invalid) -> None:
    config_path = _write_json(tmp_path / "config.json", _config_dict())
    fixture_path = _write_json(tmp_path / "fixture.json", {
        "2026-09-23": {"skillSummaries": [{"skillId": "1", "contactsOffered": 1}]},
    })
    dashboard_path = _write_json(tmp_path / "dashboard.json", {
        "offered": invalid if field == "dashboard_value" else 0,
    })
    tolerances_path = _write_json(tmp_path / "tolerances.json", {
        "offered": invalid if field == "tolerance" else 0,
    })

    exit_code = reconcile_dashboard.main([
        "--config", str(config_path), "--reference-date", "2026-09-23", "--fixture", str(fixture_path),
        "--dashboard-values", str(dashboard_path), "--tolerances", str(tolerances_path),
        "--output-dir", str(tmp_path / "out"),
    ])

    assert exit_code == 1
    manifests = list((tmp_path / "out").glob("*.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["required_failure"] is True
    result = manifest["results"][0]
    assert result["outcome"] == "unresolved"
    assert result["api_value"] == 1
    assert f"{field} must be a finite number" in result["reason"]


def test_mismatch_is_a_nonzero_exit(tmp_path: Path) -> None:
    config_path = _write_json(tmp_path / "config.json", _config_dict())
    fixture_path = _write_json(tmp_path / "fixture.json", {
        "2026-09-23": {"skillSummaries": [{"skillId": "1", "contactsOffered": 42}]},
    })
    dashboard_path = _write_json(tmp_path / "dashboard.json", {"offered": 999})

    exit_code = reconcile_dashboard.main([
        "--config", str(config_path), "--reference-date", "2026-09-23", "--fixture", str(fixture_path),
        "--dashboard-values", str(dashboard_path), "--output-dir", str(tmp_path / "out"),
    ])
    assert exit_code == 1


def test_dependent_metric_requires_sla_confirmation(tmp_path: Path) -> None:
    """Reproduced defect: the CLI called assert_ready_for_acceptance() with
    the defaults (require_sla=False), so a metric referencing an
    unconfirmed SLA still ran."""
    config = _config_dict()
    config["metrics"][0]["sla_reference"] = "aht_sla"
    config_path = _write_json(tmp_path / "config.json", config)
    fixture_path = _write_json(tmp_path / "fixture.json", {
        "2026-09-23": {"skillSummaries": [{"skillId": "1", "contactsOffered": 10}]},
    })

    exit_code = reconcile_dashboard.main([
        "--config", str(config_path), "--reference-date", "2026-09-23", "--fixture", str(fixture_path),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert exit_code == 2


def test_unconfirmed_config_is_refused_without_exploratory(tmp_path: Path) -> None:
    config_path = _write_json(tmp_path / "config.json", _config_dict(scope={"included_skill_ids": ["1"]}, timezone={}))
    fixture_path = _write_json(tmp_path / "fixture.json", {})

    exit_code = reconcile_dashboard.main([
        "--config", str(config_path), "--reference-date", "2026-09-23", "--fixture", str(fixture_path),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert exit_code == 2


def test_unconfirmed_config_runs_with_exploratory_flag(tmp_path: Path) -> None:
    config_path = _write_json(tmp_path / "config.json", _config_dict(scope={"included_skill_ids": ["1"]}, timezone={"iana_name": "UTC", "confirmed": False}))
    fixture_path = _write_json(tmp_path / "fixture.json", {
        "2026-09-23": {"skillSummaries": [{"skillId": "1", "contactsOffered": 10}]},
    })

    exit_code = reconcile_dashboard.main([
        "--config", str(config_path), "--reference-date", "2026-09-23", "--fixture", str(fixture_path),
        "--output-dir", str(tmp_path / "out"), "--exploratory",
    ])
    assert exit_code == 0  # no dashboard values supplied -> extraction-only, nothing required to fail


def test_extraction_only_run_without_dashboard_values_is_not_a_failure(tmp_path: Path) -> None:
    config_path = _write_json(tmp_path / "config.json", _config_dict())
    fixture_path = _write_json(tmp_path / "fixture.json", {
        "2026-09-23": {"skillSummaries": [{"skillId": "1", "contactsOffered": 10}]},
    })

    exit_code = reconcile_dashboard.main([
        "--config", str(config_path), "--reference-date", "2026-09-23", "--fixture", str(fixture_path),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert exit_code == 0
    manifest = json.loads(next((tmp_path / "out").glob("*.json")).read_text(encoding="utf-8"))
    assert manifest["results"][0]["outcome"] == "extracted_only"


def test_malformed_mapping_config_is_refused(tmp_path: Path) -> None:
    bad = _config_dict()
    bad["metrics"][0]["status"] = "unsupported"  # unsupported with no reason -> structural error
    config_path = _write_json(tmp_path / "config.json", bad)
    fixture_path = _write_json(tmp_path / "fixture.json", {})

    exit_code = reconcile_dashboard.main([
        "--config", str(config_path), "--reference-date", "2026-09-23", "--fixture", str(fixture_path),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert exit_code == 2


def test_live_without_vault_url_is_a_usage_error(tmp_path: Path, capsys) -> None:
    config_path = _write_json(tmp_path / "config.json", _config_dict())
    with pytest.raises(SystemExit) as excinfo:
        reconcile_dashboard.main(["--config", str(config_path), "--reference-date", "2026-09-23", "--live"])
    assert excinfo.value.code == 2


async def _raise_source_fetch_error(*args, **kwargs):
    from romtech_mcp.cxone.errors import AuthStage, ThrottlingExhaustedError
    from romtech_mcp.mapping.source import SourceFetchError

    raise SourceFetchError(
        endpoint_path="/skills/summary", window_label="2026-09-23",
        cause=ThrottlingExhaustedError(stage=AuthStage.API_REQUEST, reason_code="retries_exhausted", attempt_count=3),
    )


def test_live_fetch_failure_writes_a_failure_manifest_and_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_json(tmp_path / "config.json", _config_dict())
    monkeypatch.setattr(reconcile_dashboard, "_fetch_live", _raise_source_fetch_error)

    exit_code = reconcile_dashboard.main([
        "--config", str(config_path), "--reference-date", "2026-09-23", "--live",
        "--vault-url", "https://kv-romtech-test.vault.azure.net", "--output-dir", str(tmp_path / "out"),
    ])

    assert exit_code == 1
    manifest = json.loads(next((tmp_path / "out").glob("*.json")).read_text(encoding="utf-8"))
    assert manifest["resolved"] is False
    assert manifest["reason"] == "fetch_failed"
    assert "ThrottlingExhaustedError" in manifest["fetch_error"]["cause"]


def test_neither_live_nor_fixture_is_a_usage_error(tmp_path: Path) -> None:
    config_path = _write_json(tmp_path / "config.json", _config_dict())
    with pytest.raises(SystemExit) as excinfo:
        reconcile_dashboard.main(["--config", str(config_path), "--reference-date", "2026-09-23"])
    assert excinfo.value.code == 2
