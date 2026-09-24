"""
Verifies requirement 6 from PBI-02: logs and outward exception text never
contain secrets, tokens, raw response payloads, or upstream descriptions —
including nested failures (an SDK exception wrapped and re-raised).
"""

from __future__ import annotations

import logging

import httpx
import pytest

from romtech_mcp.cxone.client import CXoneClient
from romtech_mcp.cxone.credentials import AzureKeyVaultCredentialProvider
from romtech_mcp.cxone.errors import (
    ApplicationCredentialRejectedError,
    CredentialLoadError,
    TerminalAuthenticationError,
)
from romtech_mcp.cxone.safe_logging import log_event

from .conftest import FakeClock, FakeCredentialProvider, FakeSleeper, make_id_token, zero_jitter

SECRET_CLIENT_SECRET = "sk-super-secret-client-value-DO-NOT-LEAK"
SECRET_ACCESS_KEY_SECRET = "ak-super-secret-access-value-DO-NOT-LEAK"
SECRET_ACCESS_TOKEN = "eyFAKE.ACCESS.TOKEN-DO-NOT-LEAK"
SECRET_ERROR_DESCRIPTION = "upstream said: password was literally 'hunter2', DO-NOT-LEAK"

ALL_SECRETS = [
    SECRET_CLIENT_SECRET,
    SECRET_ACCESS_KEY_SECRET,
    SECRET_ACCESS_TOKEN,
    SECRET_ERROR_DESCRIPTION,
]


def _assert_no_secrets(text: str) -> None:
    for secret in ALL_SECRETS:
        assert secret not in text


# -- log_event's allowlist enforcement --------------------------------------


def test_log_event_rejects_unknown_field_names(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("test.safe_logging")
    with pytest.raises(ValueError):
        log_event(logger, logging.INFO, "some_event", access_token="should-never-be-a-valid-field")


def test_log_event_rejects_non_scalar_values() -> None:
    logger = logging.getLogger("test.safe_logging")
    with pytest.raises(ValueError):
        log_event(logger, logging.INFO, "some_event", stage=object())


def test_log_event_allows_and_formats_allowlisted_scalars(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("test.safe_logging")
    caplog.set_level(logging.INFO, logger="test.safe_logging")
    log_event(logger, logging.INFO, "authenticated", generation=1, status_code=200)
    assert "event=authenticated" in caplog.text
    assert "generation=1" in caplog.text
    assert "status_code=200" in caplog.text


# -- end-to-end: no secret ever reaches a log record or an exception's text --


async def test_full_flow_never_logs_or_raises_planted_secrets(
    base_config, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="romtech_mcp.cxone.client")
    credential_provider = FakeCredentialProvider(
        secrets={
            "client_id": "app-client-id",
            "client_secret": SECRET_CLIENT_SECRET,
            "access_key_id": "api-user-key-id",
            "access_key_secret": SECRET_ACCESS_KEY_SECRET,
        }
    )
    token_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            token_calls["n"] += 1
            return httpx.Response(
                200,
                json={"access_token": SECRET_ACCESS_TOKEN, "id_token": make_id_token(), "expires_in": 3600},
            )
        if "cxone-configuration" in url:
            return httpx.Response(200, json={"api_endpoint": "https://api-na1.niceincontact.com"})
        return httpx.Response(401)  # forces the 401 -> terminal path, which logs

    client = CXoneClient(
        base_config,
        credential_provider,
        transport=httpx.MockTransport(handler),
        clock=FakeClock(),
        sleeper=FakeSleeper(),
        jitter=zero_jitter,
    )
    caught: TerminalAuthenticationError | None = None
    async with client:
        try:
            await client.get("/x")
        except TerminalAuthenticationError as exc:
            caught = exc

    assert caught is not None
    _assert_no_secrets(str(caught))
    _assert_no_secrets(repr(caught))
    _assert_no_secrets(caplog.text)


async def test_credential_load_error_never_leaks_across_nested_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A nested failure: the Azure SDK raises its own exception (whose text
    could contain request/response detail), which credentials.py must
    convert to CredentialLoadError WITHOUT propagating that text."""

    class _ExplodingSecretClient:
        def __init__(self, *, vault_url: str, credential: object) -> None:
            pass

        async def get_secret(self, name: str):
            raise RuntimeError(f"Azure SDK internal detail: {SECRET_CLIENT_SECRET}")

        async def close(self) -> None:
            pass

    class _FakeCred:
        def __init__(self, *, client_id: str | None = None) -> None:
            pass

        async def close(self) -> None:
            pass

    monkeypatch.setattr("azure.keyvault.secrets.aio.SecretClient", _ExplodingSecretClient)
    monkeypatch.setattr("azure.identity.aio.ManagedIdentityCredential", _FakeCred)

    caplog.set_level(logging.DEBUG)
    provider = AzureKeyVaultCredentialProvider(vault_url="https://kv-romtech-dev.vault.azure.net")
    with pytest.raises(CredentialLoadError) as exc_info:
        await provider.get_secret("cxone-client-secret", logical_name="client_secret")

    _assert_no_secrets(str(exc_info.value))
    _assert_no_secrets(repr(exc_info.value))
    _assert_no_secrets(caplog.text)


async def test_credential_rejection_error_never_leaks_upstream_description(
    base_config, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="romtech_mcp.cxone.client")

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith("https://cxone.niceincontact.com/auth/token"):
            return httpx.Response(400, json={"error": "invalid_client", "error_description": SECRET_ERROR_DESCRIPTION})
        return httpx.Response(200)

    client = CXoneClient(
        base_config,
        FakeCredentialProvider(),
        transport=httpx.MockTransport(handler),
        clock=FakeClock(),
        sleeper=FakeSleeper(),
        jitter=zero_jitter,
    )
    async with client:
        with pytest.raises(ApplicationCredentialRejectedError) as exc_info:
            await client.get("/x")

    _assert_no_secrets(str(exc_info.value))
    _assert_no_secrets(repr(exc_info.value))
    _assert_no_secrets(caplog.text)
