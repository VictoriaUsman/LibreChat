"""
Verifies scripts/preflight_cxone_mcp.py rejects exactly what
docs/PBI-03-BE-implementation.md's "Validation and acceptance evidence"
section calls out, and accepts a shape-valid set of inputs.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from preflight_cxone_mcp import validate_cxone_mcp_inputs  # noqa: E402

VALID_DIGEST = "a" * 64
VALID_ENV_ID = "/subscriptions/sub-id/resourceGroups/rg-dev-shared/providers/Microsoft.App/managedEnvironments/env"
VALID_PULL_IDENTITY_ID = (
    "/subscriptions/sub-id/resourceGroups/rg-dev-shared/providers/Microsoft.ManagedIdentity/"
    "userAssignedIdentities/cxone-mcp-pull"
)


def _valid_kwargs(**overrides: object) -> dict:
    base = dict(
        container_apps_environment_id=VALID_ENV_ID,
        registry_server="myregistry.azurecr.io",
        image_repository="cx1-mcp",
        image_sha256=VALID_DIGEST,
        image_pull_identity_id=VALID_PULL_IDENTITY_ID,
        target_port=8000,
    )
    base.update(overrides)
    return base


def test_fully_valid_inputs_produce_no_errors() -> None:
    assert validate_cxone_mcp_inputs(**_valid_kwargs()) == []


def test_missing_required_inputs_are_each_rejected() -> None:
    for field in (
        "container_apps_environment_id",
        "registry_server",
        "image_repository",
        "image_sha256",
        "image_pull_identity_id",
    ):
        errors = validate_cxone_mcp_inputs(**_valid_kwargs(**{field: ""}))
        assert errors, f"expected an error for empty {field}"


def test_repository_with_tag_is_rejected() -> None:
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(image_repository="cx1-mcp:latest"))
    assert any("tag or digest" in e for e in errors)


def test_repository_with_embedded_digest_is_rejected() -> None:
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(image_repository=f"cx1-mcp@sha256:{VALID_DIGEST}"))
    assert any("tag or digest" in e for e in errors)


def test_quickstart_placeholder_repository_is_rejected() -> None:
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(image_repository="k8se/quickstart"))
    assert any("placeholder" in e for e in errors)


def test_digest_with_wrong_length_is_rejected() -> None:
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(image_sha256="a" * 63))
    assert any("64" in e for e in errors)


def test_digest_with_uppercase_hex_is_rejected() -> None:
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(image_sha256="A" * 64))
    assert any("64" in e for e in errors)


def test_digest_with_non_hex_characters_is_rejected() -> None:
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(image_sha256="g" * 64))
    assert any("64" in e for e in errors)


def test_all_zero_placeholder_digest_is_rejected() -> None:
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(image_sha256="0" * 64))
    assert any("placeholder" in e for e in errors)


def test_non_arm_resource_id_inputs_are_rejected() -> None:
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(container_apps_environment_id="just-a-guess"))
    assert any("resource ID" in e for e in errors)
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(image_pull_identity_id="also-a-guess"))
    assert any("resource ID" in e for e in errors)


def test_pull_identity_cannot_equal_environment_id() -> None:
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(image_pull_identity_id=VALID_ENV_ID))
    assert any("must not be the same" in e for e in errors)


def test_invalid_port_is_rejected() -> None:
    for bad_port in (0, -1, 70000):
        errors = validate_cxone_mcp_inputs(**_valid_kwargs(target_port=bad_port))
        assert any("targetPort" in e for e in errors), f"port {bad_port} should be rejected"


def test_whitespace_only_repository_is_treated_as_empty() -> None:
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(image_repository="   "))
    assert any("imageRepository is empty" in e for e in errors)


def test_registry_server_with_url_scheme_is_rejected() -> None:
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(registry_server="https://myregistry.azurecr.io"))
    assert any("not a URL" in e for e in errors)


def test_registry_server_with_path_is_rejected() -> None:
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(registry_server="myregistry.azurecr.io/extra"))
    assert any("must not contain a path" in e for e in errors)


def test_digest_with_trailing_newline_is_rejected() -> None:
    """`$` in Python regex matches before a trailing newline even under
    `.match()`, so a naive `^[0-9a-f]{64}$` + `.match()` combination
    silently accepts a digest with a trailing "\n" — this must use
    `.fullmatch()` (or an equivalently strict check) instead."""
    errors = validate_cxone_mcp_inputs(**_valid_kwargs(image_sha256=VALID_DIGEST + "\n"))
    assert errors


def test_leading_or_trailing_whitespace_on_an_otherwise_valid_field_is_rejected() -> None:
    for field in ("container_apps_environment_id", "image_pull_identity_id"):
        wrapped = f" {_valid_kwargs()[field]} "
        errors = validate_cxone_mcp_inputs(**_valid_kwargs(**{field: wrapped}))
        assert any("whitespace" in e for e in errors), f"expected a whitespace error for {field}"
