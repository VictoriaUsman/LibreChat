"""
Bridges the Container App's environment variables (see
ROMTechMCP.bicep/cxone-containerapp.bicep) to a CXoneConfig and an
AzureKeyVaultCredentialProvider.

PBI-02's CXoneConfig/AzureKeyVaultCredentialProvider deliberately do NOT
read the process environment themselves — they take explicit constructor
arguments so their tests never depend on it. This module is the one place
that bridges "what the deployed container's env vars say" to those
objects; PBI-03 is what defines and sets those env vars in the first
place.

Nothing here ever calls Key Vault. build_cxone_config() and
build_credential_provider() only construct objects — the first real
secret retrieval happens later, whenever the CXoneClient actually
authenticates (its normal, already-lazy behavior). That matters at first
deployment: the Container App's system identity's Key Vault role
assignment can take time to propagate after the app itself is created
(cxone-keyvault-access.bicep depends on the app's principal ID existing
first), so nothing in startup should hard-fail because that propagation
hasn't finished yet — only an actual attempt to use the client would.
"""

from __future__ import annotations

import os

from .config import CXoneConfig, SecretNames
from .credentials import AzureKeyVaultCredentialProvider


class BootstrapError(RuntimeError):
    """A required environment variable was missing or empty at startup.
    Never wraps or includes a secret value — there are none at this
    stage, only variable NAMES, which are non-secret configuration."""

    def __init__(self, variable_name: str) -> None:
        self.variable_name = variable_name
        super().__init__(f"Required environment variable {variable_name} is not set.")


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise BootstrapError(name)
    return value


def _optional_env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def build_cxone_config() -> CXoneConfig:
    """Reads CXONE_VAULT_URI (required) and the four optional
    *_SECRET_NAME overrides, falling back to SecretNames' own defaults —
    matching cxone-containerapp.bicep's parameter defaults exactly, so an
    unset env var and an explicitly-default one behave identically."""
    vault_uri = _require_env("CXONE_VAULT_URI")
    default_names = SecretNames()
    secret_names = SecretNames(
        client_id=_optional_env("CXONE_CLIENT_ID_SECRET_NAME", default_names.client_id),
        client_secret=_optional_env("CXONE_CLIENT_SECRET_SECRET_NAME", default_names.client_secret),
        access_key_id=_optional_env("CXONE_ACCESS_KEY_ID_SECRET_NAME", default_names.access_key_id),
        access_key_secret=_optional_env("CXONE_ACCESS_KEY_SECRET_SECRET_NAME", default_names.access_key_secret),
    )
    return CXoneConfig(vault_url=vault_uri, secret_names=secret_names)


def build_credential_provider(config: CXoneConfig) -> AzureKeyVaultCredentialProvider:
    """Constructs the provider only — does not touch Key Vault. Uses the
    Container App's SYSTEM identity always (azure_managed_identity_client_id
    is None unless explicitly configured for a user-assigned identity,
    which this deployment does not use for runtime — see
    cxone-containerapp.bicep's identitySettings)."""
    return AzureKeyVaultCredentialProvider(
        vault_url=config.vault_url,
        azure_managed_identity_client_id=config.azure_managed_identity_client_id,
    )
