from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import pytest

from romtech_mcp.cxone.config import CXoneConfig, RetryPolicy, SecretNames
from romtech_mcp.cxone.credentials import CredentialProvider
from romtech_mcp.cxone.errors import CredentialLoadError


def make_id_token(*, tenant_id: str | None = "tenant-123", extra_claims: dict | None = None) -> str:
    """Builds a syntactically-valid (but unsigned/fake) JWT with the given
    tenantId claim, matching the shape _decode_jwt_payload_unverified reads.
    Never a real token — used only to drive the fake token endpoint."""
    header = {"alg": "none", "typ": "JWT"}
    payload = dict(extra_claims or {})
    if tenant_id is not None:
        payload["tenantId"] = tenant_id

    def b64(obj: dict) -> str:
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{b64(header)}.{b64(payload)}.fake-signature-not-real"


class FakeClock:
    """Fully controllable clock: monotonic() and now_utc() only advance
    when the test explicitly calls .advance() — no real time ever passes."""

    def __init__(self, start_monotonic: float = 1000.0, start_utc: datetime | None = None) -> None:
        self._monotonic = start_monotonic
        self._utc = start_utc or datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self._monotonic

    def now_utc(self) -> datetime:
        return self._utc

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._monotonic += seconds
        self._utc += timedelta(seconds=seconds)


class FakeSleeper:
    """Records every requested sleep instead of actually sleeping, and
    advances the paired FakeClock by the same amount so deadline/expiry
    math sees time as having passed."""

    def __init__(self, clock: FakeClock | None = None) -> None:
        self.sleeps: list[float] = []
        self._clock = clock

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if self._clock is not None:
            self._clock.advance(seconds)


def zero_jitter() -> float:
    return 0.0


class FakeCredentialProvider:
    """In-memory stand-in for AzureKeyVaultCredentialProvider. `secrets`
    maps LOGICAL name (client_id/client_secret/access_key_id/access_key_secret)
    to value; `missing`/`empty` force specific logical names to fail the
    way a real Key Vault retrieval failure or an empty secret would."""

    def __init__(
        self,
        secrets: dict[str, str] | None = None,
        *,
        fail_logical_names: set[str] | None = None,
        empty_logical_names: set[str] | None = None,
    ) -> None:
        self.secrets = secrets or {
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "access_key_id": "test-access-key-id",
            "access_key_secret": "test-access-key-secret",
        }
        self._fail = fail_logical_names or set()
        self._empty = empty_logical_names or set()
        self.requested_secret_names: list[str] = []
        self.closed = False

    async def get_secret(self, secret_name: str, *, logical_name: str) -> str:
        self.requested_secret_names.append(secret_name)
        if logical_name in self._fail:
            raise CredentialLoadError(logical_name=logical_name, secret_name=secret_name, reason_code="retrieval_failed")
        if logical_name in self._empty:
            raise CredentialLoadError(logical_name=logical_name, secret_name=secret_name, reason_code="empty")
        return self.secrets[logical_name]

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def credential_provider() -> CredentialProvider:
    return FakeCredentialProvider()


@pytest.fixture
def base_config() -> CXoneConfig:
    return CXoneConfig(
        vault_url="https://kv-romtech-test.vault.azure.net",
        secret_names=SecretNames(),
        total_deadline_seconds=60.0,
        token_expiry_safety_margin_seconds=30.0,
        retry=RetryPolicy(max_attempts=3, base_delay_seconds=1.0, max_delay_seconds=30.0),
    )
