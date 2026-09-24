"""
Verifies the env-var -> CXoneConfig/AzureKeyVaultCredentialProvider bridge
that PBI-03's Container App environment variables are meant to drive.
"""

from __future__ import annotations

import pytest

from romtech_mcp.cxone.bootstrap import BootstrapError, build_credential_provider, build_cxone_config
from romtech_mcp.cxone.config import SecretNames


def test_missing_vault_uri_raises_bootstrap_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CXONE_VAULT_URI", raising=False)
    with pytest.raises(BootstrapError) as exc_info:
        build_cxone_config()
    assert exc_info.value.variable_name == "CXONE_VAULT_URI"


def test_blank_vault_uri_is_treated_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CXONE_VAULT_URI", "   ")
    with pytest.raises(BootstrapError):
        build_cxone_config()


def test_vault_uri_alone_uses_default_secret_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CXONE_VAULT_URI", "https://kv-romtech-dev.vault.azure.net")
    for name in (
        "CXONE_CLIENT_ID_SECRET_NAME",
        "CXONE_CLIENT_SECRET_SECRET_NAME",
        "CXONE_ACCESS_KEY_ID_SECRET_NAME",
        "CXONE_ACCESS_KEY_SECRET_SECRET_NAME",
    ):
        monkeypatch.delenv(name, raising=False)

    config = build_cxone_config()

    assert config.vault_url == "https://kv-romtech-dev.vault.azure.net"
    assert config.secret_names == SecretNames()  # matches cxone-containerapp.bicep's own defaults


def test_secret_name_overrides_are_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CXONE_VAULT_URI", "https://kv-romtech-dev.vault.azure.net")
    monkeypatch.setenv("CXONE_CLIENT_ID_SECRET_NAME", "custom-client-id-name")
    monkeypatch.setenv("CXONE_CLIENT_SECRET_SECRET_NAME", "custom-client-secret-name")
    monkeypatch.setenv("CXONE_ACCESS_KEY_ID_SECRET_NAME", "custom-access-key-id-name")
    monkeypatch.setenv("CXONE_ACCESS_KEY_SECRET_SECRET_NAME", "custom-access-key-secret-name")

    config = build_cxone_config()

    assert config.secret_names.client_id == "custom-client-id-name"
    assert config.secret_names.client_secret == "custom-client-secret-name"
    assert config.secret_names.access_key_id == "custom-access-key-id-name"
    assert config.secret_names.access_key_secret == "custom-access-key-secret-name"


def test_build_credential_provider_never_touches_key_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    """Construction alone must not call Key Vault — first deployment can't
    hard-fail on startup just because role-assignment propagation hasn't
    finished yet (docs/PBI-03-BE-implementation.md's first-deployment note)."""
    calls: list[str] = []

    class _TrackingSecretClient:
        def __init__(self, *, vault_url: str, credential: object) -> None:
            calls.append("SecretClient.__init__")

    class _TrackingCredential:
        def __init__(self, *, client_id: str | None = None) -> None:
            calls.append("ManagedIdentityCredential.__init__")

    monkeypatch.setattr("azure.keyvault.secrets.aio.SecretClient", _TrackingSecretClient)
    monkeypatch.setattr("azure.identity.aio.ManagedIdentityCredential", _TrackingCredential)
    monkeypatch.setenv("CXONE_VAULT_URI", "https://kv-romtech-dev.vault.azure.net")

    config = build_cxone_config()
    provider = build_credential_provider(config)

    assert calls == ["ManagedIdentityCredential.__init__", "SecretClient.__init__"]
    assert "get_secret" not in " ".join(calls)
    assert provider is not None
