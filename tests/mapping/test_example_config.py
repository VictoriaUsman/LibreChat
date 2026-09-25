"""Regression: config/cxone-dashboard-mapping.example.json must always
load cleanly and contain no structural validation errors — it's the
starting point anyone copies to build a real config, so schema drift here
would silently break that."""

from __future__ import annotations

from pathlib import Path

from romtech_mcp.mapping.config import load_mapping_config, validate_mapping

_EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "config" / "cxone-dashboard-mapping.example.json"


def test_example_config_loads_and_validates_cleanly() -> None:
    config = load_mapping_config(_EXAMPLE_PATH)
    assert config.scope.confirmed is False
    assert config.timezone.confirmed is False
    issues = validate_mapping(config)
    assert [i for i in issues if i.severity == "error"] == []
