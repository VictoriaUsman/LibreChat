"""
Credential retrieval for the four CXone secrets.

Production uses AzureKeyVaultCredentialProvider (managed identity + Key
Vault, no environment-variable fallback, ever). Tests inject a fake
implementation of the same Protocol — see tests/cxone/conftest.py — so
nothing here needs Azure to be reachable to be exercised.
"""

from __future__ import annotations

from typing import Protocol

from .errors import CredentialLoadError


class CredentialProvider(Protocol):
    """Anything that can produce the four CXone secrets by (Key Vault)
    secret name. Implementations are expected to raise CredentialLoadError
    themselves — see AzureKeyVaultCredentialProvider — rather than letting
    an SDK-specific exception (with its message text) escape."""

    async def get_secret(self, secret_name: str, *, logical_name: str) -> str: ...

    async def aclose(self) -> None: ...


class AzureKeyVaultCredentialProvider:
    """Reads secrets through azure.identity's ManagedIdentityCredential and
    azure.keyvault.secrets' SecretClient — both async. Always fetches the
    CURRENT (latest) version, so a secret rotation in Key Vault takes effect
    on the next authentication cycle without rebuilding or restarting the
    container. Never logs a secret value, a fetched version URL, or the
    underlying SDK exception's text — only the logical/secret NAME, which
    is non-secret configuration, not a value.
    """

    def __init__(self, *, vault_url: str, azure_managed_identity_client_id: str | None = None) -> None:
        # Imported here, not at module level, so importing this package
        # doesn't hard-require the azure SDKs to be installed for callers
        # that only need the fake/testing path (e.g. discovery tooling).
        from azure.identity.aio import ManagedIdentityCredential
        from azure.keyvault.secrets.aio import SecretClient

        self._credential = ManagedIdentityCredential(client_id=azure_managed_identity_client_id)
        self._client = SecretClient(vault_url=vault_url, credential=self._credential)

    async def get_secret(self, secret_name: str, *, logical_name: str) -> str:
        try:
            secret = await self._client.get_secret(secret_name)
        except Exception:
            # Deliberately broad and deliberately swallows the original
            # exception's text — could be a 404 (missing), 403 (identity
            # lacks Key Vault Secrets User), a disabled-secret rejection, a
            # network failure, or something else. All of those collapse to
            # "retrieval_failed" here: which SDK exception subtype maps to
            # which of missing/disabled/access-denied has not been
            # empirically confirmed against this vault, so this doesn't
            # guess a finer-grained reason_code than the evidence supports.
            raise CredentialLoadError(
                logical_name=logical_name, secret_name=secret_name, reason_code="retrieval_failed"
            ) from None
        value = secret.value
        if not value:
            raise CredentialLoadError(logical_name=logical_name, secret_name=secret_name, reason_code="empty")
        return value

    async def aclose(self) -> None:
        await self._client.close()
        await self._credential.close()
