"""
Non-secret configuration for the CXone transport/authentication client.

Nothing in this module ever holds a credential value — only the names of
where to find them (Key Vault secret names) and the endpoints/timeouts that
govern the transport. See credentials.py for how the four values are
actually retrieved.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Confirmed empirically (2026-09-24, ROMTECH tenant, see
# discovery/findings.md) — not guessed. Re-confirm before reusing against a
# different tenant.
DEFAULT_AUTH_URL = "https://cxone.niceincontact.com/auth/token"
DEFAULT_DISCOVERY_URL = "https://cxone.niceincontact.com/.well-known/cxone-configuration"
DEFAULT_API_VERSION = "v27.0"


@dataclass(frozen=True)
class SecretNames:
    """Key Vault secret names for the four CXone credentials. Configurable;
    the values themselves are never defaulted — only names, and names are
    not secrets."""

    client_id: str = "cxone-client-id"
    client_secret: str = "cxone-client-secret"
    access_key_id: str = "cxone-access-key-id"
    access_key_secret: str = "cxone-access-key-secret"


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry/backoff policy for transient (429/5xx/network) failures.

    These are implementation defaults, not discovered CXone limits — nothing
    about CXone's actual rate-limit behavior was confirmed during discovery
    (discovery/cxone_client.py deliberately never retries at all).
    """

    max_attempts: int = 3  # includes the initial attempt — so at most 2 retries
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0


@dataclass(frozen=True)
class CXoneConfig:
    # Key Vault
    vault_url: str
    secret_names: SecretNames = field(default_factory=SecretNames)
    # Distinct from the CXone application client ID (secret_names.client_id):
    # this selects which USER-ASSIGNED managed identity the container uses to
    # reach Key Vault. None means the system-assigned identity.
    azure_managed_identity_client_id: str | None = None

    # CXone endpoints
    api_version: str = DEFAULT_API_VERSION
    auth_url: str = DEFAULT_AUTH_URL
    discovery_url: str = DEFAULT_DISCOVERY_URL

    # Timeouts / deadlines
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 30.0
    # Governs the ENTIRE logical operation a public client call performs —
    # vault access, auth, discovery, the data call itself, retries, and one
    # 401-recovery replay all share this one budget, not one each.
    total_deadline_seconds: float = 60.0
    # Renew when the token is within this many seconds of its stated expiry.
    # Capped against the token's own lifetime for short-lived tokens (a
    # margin longer than the token's life would mean never trusting it).
    token_expiry_safety_margin_seconds: float = 30.0

    retry: RetryPolicy = field(default_factory=RetryPolicy)

    def __post_init__(self) -> None:
        if not self.vault_url:
            raise ValueError("vault_url is required")
        if not self.vault_url.startswith("https://"):
            raise ValueError("vault_url must be https")
        if self.total_deadline_seconds <= 0:
            raise ValueError("total_deadline_seconds must be positive")
        if self.token_expiry_safety_margin_seconds < 0:
            raise ValueError("token_expiry_safety_margin_seconds must not be negative")
