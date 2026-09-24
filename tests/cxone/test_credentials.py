"""
Verifies requirement 1 from PBI-02: all four secrets are requested,
production construction uses managed identity (never env-var fallback),
and missing/empty values fail safely.
"""

from __future__ import annotations

import pytest

from romtech_mcp.cxone.credentials import AzureKeyVaultCredentialProvider
from romtech_mcp.cxone.errors import CredentialLoadError

from .conftest import FakeCredentialProvider


async def test_all_four_secrets_requested_by_logical_name() -> None:
    provider = FakeCredentialProvider()
    for logical_name, secret_name in (
        ("client_id", "cxone-client-id"),
        ("client_secret", "cxone-client-secret"),
        ("access_key_id", "cxone-access-key-id"),
        ("access_key_secret", "cxone-access-key-secret"),
    ):
        value = await provider.get_secret(secret_name, logical_name=logical_name)
        assert value == provider.secrets[logical_name]
    assert provider.requested_secret_names == [
        "cxone-client-id",
        "cxone-client-secret",
        "cxone-access-key-id",
        "cxone-access-key-secret",
    ]


async def test_missing_secret_fails_safely_not_silently() -> None:
    provider = FakeCredentialProvider(fail_logical_names={"client_secret"})
    with pytest.raises(CredentialLoadError) as exc_info:
        await provider.get_secret("cxone-client-secret", logical_name="client_secret")
    err = exc_info.value
    assert err.logical_name == "client_secret"
    assert err.secret_name == "cxone-client-secret"
    assert err.reason_code == "retrieval_failed"


async def test_empty_secret_value_is_rejected() -> None:
    provider = FakeCredentialProvider(empty_logical_names={"access_key_secret"})
    with pytest.raises(CredentialLoadError) as exc_info:
        await provider.get_secret("cxone-access-key-secret", logical_name="access_key_secret")
    assert exc_info.value.reason_code == "empty"
    assert exc_info.value.logical_name == "access_key_secret"


# -- AzureKeyVaultCredentialProvider: managed identity, no env fallback -----


class _FakeSecretValue:
    def __init__(self, value: str | None) -> None:
        self.value = value


class _FakeAsyncSecretClient:
    """Stands in for azure.keyvault.secrets.aio.SecretClient."""

    def __init__(self, *, vault_url: str, credential: object) -> None:
        self.vault_url = vault_url
        self.credential = credential
        self.requested_names: list[str] = []
        self.closed = False
        self.values: dict[str, str | None] = {}
        self.raise_for: set[str] = set()

    async def get_secret(self, name: str) -> _FakeSecretValue:
        self.requested_names.append(name)
        if name in self.raise_for:
            raise RuntimeError(f"simulated Key Vault SDK failure containing SENSITIVE-{name}-DETAIL")
        return _FakeSecretValue(self.values.get(name))

    async def close(self) -> None:
        self.closed = True


class _FakeManagedIdentityCredential:
    def __init__(self, *, client_id: str | None = None) -> None:
        self.client_id = client_id
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _install_fake_azure_sdk(monkeypatch: pytest.MonkeyPatch) -> _FakeAsyncSecretClient:
    """Patches the SDK classes at their real module locations — credentials.py
    imports them lazily inside the constructor, from exactly these paths."""
    holder: dict[str, _FakeAsyncSecretClient] = {}

    class _Factory:
        def __new__(cls, *, vault_url: str, credential: object) -> _FakeAsyncSecretClient:
            client = _FakeAsyncSecretClient(vault_url=vault_url, credential=credential)
            holder["client"] = client
            return client

    monkeypatch.setattr("azure.keyvault.secrets.aio.SecretClient", _Factory)
    monkeypatch.setattr("azure.identity.aio.ManagedIdentityCredential", _FakeManagedIdentityCredential)
    return holder  # populated once the provider is constructed


async def test_key_vault_provider_uses_managed_identity_and_current_version(monkeypatch: pytest.MonkeyPatch) -> None:
    holder = _install_fake_azure_sdk(monkeypatch)
    provider = AzureKeyVaultCredentialProvider(
        vault_url="https://kv-romtech-dev.vault.azure.net", azure_managed_identity_client_id="my-uami-client-id"
    )
    client: _FakeAsyncSecretClient = holder["client"]
    client.values["cxone-client-id"] = "real-client-id-value"

    value = await provider.get_secret("cxone-client-id", logical_name="client_id")

    assert value == "real-client-id-value"
    # No version suffix/param anywhere — always the current version.
    assert client.requested_names == ["cxone-client-id"]
    assert isinstance(provider._credential, _FakeManagedIdentityCredential)
    assert provider._credential.client_id == "my-uami-client-id"


async def test_key_vault_provider_never_falls_back_to_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holder = _install_fake_azure_sdk(monkeypatch)
    monkeypatch.setenv("CXONE_CLIENT_ID", "an-env-value-that-must-never-be-used")
    provider = AzureKeyVaultCredentialProvider(vault_url="https://kv-romtech-dev.vault.azure.net")
    client: _FakeAsyncSecretClient = holder["client"]
    client.raise_for.add("cxone-client-id")  # vault retrieval fails

    with pytest.raises(CredentialLoadError) as exc_info:
        await provider.get_secret("cxone-client-id", logical_name="client_id")

    # Fails safely rather than silently reading the environment variable.
    assert exc_info.value.reason_code == "retrieval_failed"
    assert "an-env-value-that-must-never-be-used" not in str(exc_info.value)


async def test_key_vault_provider_error_never_leaks_sdk_exception_text(monkeypatch: pytest.MonkeyPatch) -> None:
    holder = _install_fake_azure_sdk(monkeypatch)
    provider = AzureKeyVaultCredentialProvider(vault_url="https://kv-romtech-dev.vault.azure.net")
    client: _FakeAsyncSecretClient = holder["client"]
    client.raise_for.add("cxone-access-key-secret")

    with pytest.raises(CredentialLoadError) as exc_info:
        await provider.get_secret("cxone-access-key-secret", logical_name="access_key_secret")

    assert "SENSITIVE-cxone-access-key-secret-DETAIL" not in str(exc_info.value)
    assert "simulated Key Vault SDK failure" not in str(exc_info.value)


async def test_key_vault_provider_rejects_empty_secret_value(monkeypatch: pytest.MonkeyPatch) -> None:
    holder = _install_fake_azure_sdk(monkeypatch)
    provider = AzureKeyVaultCredentialProvider(vault_url="https://kv-romtech-dev.vault.azure.net")
    client: _FakeAsyncSecretClient = holder["client"]
    client.values["cxone-client-secret"] = ""  # exists, but empty

    with pytest.raises(CredentialLoadError) as exc_info:
        await provider.get_secret("cxone-client-secret", logical_name="client_secret")
    assert exc_info.value.reason_code == "empty"


async def test_key_vault_provider_aclose_closes_both_sdk_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    holder = _install_fake_azure_sdk(monkeypatch)
    provider = AzureKeyVaultCredentialProvider(vault_url="https://kv-romtech-dev.vault.azure.net")
    await provider.aclose()
    client: _FakeAsyncSecretClient = holder["client"]
    assert client.closed is True
    assert provider._credential.closed is True
