"""
Verifies requirements 2 and 3 from PBI-02: the token exchange uses both
credential pairs, discovery uses the tenant claim, API calls use the
discovered host and Bearer token, expiry-based and 401-triggered renewal
both work, and concurrent callers share one refresh.
"""

from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest

from romtech_mcp.cxone.client import CXoneClient
from romtech_mcp.cxone.errors import (
    AmbiguousCredentialRejectedError,
    ApiUserCredentialRejectedError,
    ApplicationCredentialRejectedError,
    CredentialClass,
    MalformedProtocolResponseError,
    TerminalAuthenticationError,
)

from .conftest import FakeClock, FakeCredentialProvider, FakeSleeper, make_id_token, zero_jitter


def _token_response(access_token: str, *, tenant_id: str = "tenant-123", expires_in: float = 3600) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": access_token,
            "id_token": make_id_token(tenant_id=tenant_id),
            "token_type": "Bearer",
            "expires_in": expires_in,
        },
    )


def _discovery_response(api_endpoint: str = "https://api-na1.niceincontact.com") -> httpx.Response:
    return httpx.Response(200, json={"area": "na1", "domain": "niceincontact.com", "api_endpoint": api_endpoint})


def _make_client(config, transport, *, clock=None, sleeper=None, credential_provider=None) -> CXoneClient:
    return CXoneClient(
        config,
        credential_provider or FakeCredentialProvider(),
        transport=transport,
        clock=clock or FakeClock(),
        sleeper=sleeper or FakeSleeper(),
        jitter=zero_jitter,
    )


# --------------------------------------------------------------------------
# Requirement 2: token exchange + discovery + API call shape
# --------------------------------------------------------------------------


async def test_token_request_uses_basic_app_creds_and_password_grant_api_user(base_config, credential_provider) -> None:
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith("https://cxone.niceincontact.com/auth/token"):
            seen["token"] = request
            return _token_response("access-token-1")
        if "cxone-configuration" in str(request.url):
            return _discovery_response()
        return httpx.Response(200, json={"skillSummaries": []})

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        await client.get("/incontactapi/services/v27.0/skills/summary")

    token_request = seen["token"]
    auth_header = token_request.headers["authorization"]
    expected_basic = base64.b64encode(b"test-client-id:test-client-secret").decode()
    assert auth_header == f"Basic {expected_basic}"

    body = token_request.read().decode()
    form = dict(pair.split("=") for pair in body.split("&"))
    assert form["grant_type"] == "password"
    assert form["username"] == "test-access-key-id"
    assert form["password"] == "test-access-key-secret"


async def test_discovery_uses_tenant_id_claim_from_id_token(base_config, credential_provider) -> None:
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response("access-token-1", tenant_id="tenant-xyz-789")
        if "cxone-configuration" in url:
            seen["discovery"] = request
            return _discovery_response()
        return httpx.Response(200, json={"skillSummaries": []})

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        await client.get("/incontactapi/services/v27.0/skills/summary")

    assert seen["discovery"].url.params["tenantId"] == "tenant-xyz-789"


async def test_api_call_uses_discovered_host_and_bearer_token(base_config, credential_provider) -> None:
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response("the-access-token")
        if "cxone-configuration" in url:
            return _discovery_response(api_endpoint="https://api-na1.niceincontact.com")
        seen["api"] = request
        return httpx.Response(200, json={"skillSummaries": []})

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        await client.get("/incontactapi/services/v27.0/skills/summary", params={"startDate": "2026-09-23"})

    api_request = seen["api"]
    assert str(api_request.url).startswith("https://api-na1.niceincontact.com/incontactapi/services/v27.0/skills/summary")
    assert api_request.headers["authorization"] == "Bearer the-access-token"


async def test_malformed_discovery_response_is_rejected(base_config, credential_provider) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response("access-token-1")
        return httpx.Response(200, json={"area": "na1"})  # missing api_endpoint

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        with pytest.raises(MalformedProtocolResponseError) as exc_info:
            await client.get("/incontactapi/services/v27.0/skills/summary")
    assert exc_info.value.reason_code == "missing_api_endpoint"


async def test_non_https_discovered_host_is_rejected(base_config, credential_provider) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response("access-token-1")
        return _discovery_response(api_endpoint="http://api-na1.niceincontact.com")  # not https

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        with pytest.raises(MalformedProtocolResponseError) as exc_info:
            await client.get("/incontactapi/services/v27.0/skills/summary")
    assert exc_info.value.reason_code == "non_https_api_endpoint"


async def test_relative_path_required_absolute_url_refused(base_config, credential_provider) -> None:
    client = _make_client(base_config, httpx.MockTransport(lambda r: httpx.Response(200)), credential_provider=credential_provider)
    async with client:
        with pytest.raises(ValueError):
            await client.get("https://evil.example.com/steal")


# --------------------------------------------------------------------------
# Requirement 3: expiry-based renewal, one-shot 401 recovery, concurrency
# --------------------------------------------------------------------------


async def test_locally_expired_token_is_renewed(base_config, credential_provider) -> None:
    token_calls = {"n": 0}
    clock = FakeClock()
    sleeper = FakeSleeper(clock)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            token_calls["n"] += 1
            return _token_response(f"token-{token_calls['n']}", expires_in=100)
        if "cxone-configuration" in url:
            return _discovery_response()
        return httpx.Response(200, json={"skillSummaries": []})

    client = _make_client(base_config, httpx.MockTransport(handler), clock=clock, sleeper=sleeper, credential_provider=credential_provider)
    async with client:
        await client.get("/x")
        assert token_calls["n"] == 1
        clock.advance(100 - 30 + 1)  # past expiry minus the 30s safety margin
        await client.get("/x")
        assert token_calls["n"] == 2


async def test_premature_401_renews_once_and_replays(base_config, credential_provider) -> None:
    token_calls = {"n": 0}
    api_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            token_calls["n"] += 1
            return _token_response(f"token-{token_calls['n']}", expires_in=3600)
        if "cxone-configuration" in url:
            return _discovery_response()
        api_calls["n"] += 1
        if api_calls["n"] == 1:
            return httpx.Response(401)  # server rejects the still-locally-fresh token
        assert request.headers["authorization"] == "Bearer token-2"  # replay uses the RENEWED token
        return httpx.Response(200, json={"skillSummaries": []})

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        response = await client.get("/x")

    assert response.status_code == 200
    assert token_calls["n"] == 2  # initial auth + exactly one recovery re-auth
    assert api_calls["n"] == 2  # original attempt (401) + exactly one replay


async def test_second_401_after_replay_is_terminal(base_config, credential_provider) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response("token-x", expires_in=3600)
        if "cxone-configuration" in url:
            return _discovery_response()
        return httpx.Response(401)  # every API call is rejected, even after "renewal"

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        with pytest.raises(TerminalAuthenticationError) as exc_info:
            await client.get("/x")
    assert exc_info.value.attempt_count == 2


async def test_403_is_not_treated_as_expiry_and_is_not_retried(base_config, credential_provider) -> None:
    from romtech_mcp.cxone.errors import AuthorizationError

    token_calls = {"n": 0}
    api_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            token_calls["n"] += 1
            return _token_response("token-x", expires_in=3600)
        if "cxone-configuration" in url:
            return _discovery_response()
        api_calls["n"] += 1
        return httpx.Response(403)

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        with pytest.raises(AuthorizationError):
            await client.get("/x")
    assert token_calls["n"] == 1  # no re-authentication triggered by a 403
    assert api_calls["n"] == 1  # no retry of a 403


async def test_concurrent_expiry_causes_exactly_one_refresh(base_config, credential_provider) -> None:
    token_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            token_calls["n"] += 1
            return _token_response(f"token-{token_calls['n']}", expires_in=3600)
        if "cxone-configuration" in url:
            return _discovery_response()
        return httpx.Response(200, json={"skillSummaries": []})

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        results = await asyncio.gather(client.get("/x"), client.get("/y"), client.get("/z"))

    assert all(r.status_code == 200 for r in results)
    assert token_calls["n"] == 1  # three concurrent callers, one shared authentication cycle


async def test_late_401_reuses_newer_token_instead_of_a_second_reauth(base_config, credential_provider) -> None:
    """Both callers hold a token from generation 1 and both get a 401 on
    their first API attempt (simulating the server having invalidated it
    for everyone). Whichever recovers first bumps to generation 2; the
    other must reuse that, not trigger a third authentication cycle."""
    token_calls = {"n": 0}
    priming_done = False
    rejected_token: dict[str, str | None] = {"value": None}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal priming_done
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            token_calls["n"] += 1
            return _token_response(f"token-gen-{token_calls['n']}", expires_in=3600)
        if "cxone-configuration" in url:
            return _discovery_response()
        if request.url.path == "/prime":
            priming_done = True
            return httpx.Response(200, json={"skillSummaries": []})
        # Only /x and /y, after priming, are subject to the "reject
        # whichever token generation was active at priming time" rule.
        used_token = request.headers["authorization"].removeprefix("Bearer ")
        if rejected_token["value"] is None:
            rejected_token["value"] = used_token
        if used_token == rejected_token["value"]:
            return httpx.Response(401)
        return httpx.Response(200, json={"skillSummaries": []})

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        # Prime a shared generation-1 token first, so both subsequent calls
        # start from the SAME token and can both be rejected by it.
        await client.get("/prime")
        assert priming_done is True
        assert token_calls["n"] == 1

        results = await asyncio.gather(client.get("/x"), client.get("/y"))

    assert all(r.status_code == 200 for r in results)
    # Exactly one recovery authentication for both concurrent 401s combined
    # (1 priming + 1 recovery = 2), never a separate third re-auth.
    assert token_calls["n"] == 2


# --------------------------------------------------------------------------
# Requirement 4: distinct, safe credential-rejection classification
# --------------------------------------------------------------------------


async def test_invalid_client_maps_to_application_credential_class(base_config, credential_provider) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith("https://cxone.niceincontact.com/auth/token"):
            return httpx.Response(400, json={"error": "invalid_client", "error_description": "bad app secret, do not leak this"})
        return httpx.Response(200)

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        with pytest.raises(ApplicationCredentialRejectedError) as exc_info:
            await client.get("/x")
    assert exc_info.value.credential_class == CredentialClass.APPLICATION
    assert "bad app secret" not in str(exc_info.value)


async def test_invalid_grant_maps_to_api_user_credential_class(base_config, credential_provider) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith("https://cxone.niceincontact.com/auth/token"):
            return httpx.Response(400, json={"error": "invalid_grant", "error_description": "bad access key, do not leak this"})
        return httpx.Response(200)

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        with pytest.raises(ApiUserCredentialRejectedError) as exc_info:
            await client.get("/x")
    assert exc_info.value.credential_class == CredentialClass.API_USER
    assert "bad access key" not in str(exc_info.value)


async def test_unmapped_oauth_error_code_is_reported_as_ambiguous_not_guessed(base_config, credential_provider) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith("https://cxone.niceincontact.com/auth/token"):
            return httpx.Response(400, json={"error": "unsupported_grant_type"})
        return httpx.Response(200)

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        with pytest.raises(AmbiguousCredentialRejectedError) as exc_info:
            await client.get("/x")
    assert exc_info.value.credential_class == CredentialClass.UNKNOWN


async def test_rejection_with_no_parseable_error_code_is_ambiguous_not_guessed(base_config, credential_provider) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith("https://cxone.niceincontact.com/auth/token"):
            return httpx.Response(401, content=b"not even json")
        return httpx.Response(200)

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        with pytest.raises(AmbiguousCredentialRejectedError) as exc_info:
            await client.get("/x")
    assert exc_info.value.credential_class == CredentialClass.UNKNOWN


async def test_permanent_credential_rejection_does_not_trigger_a_retry_loop(base_config, credential_provider) -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith("https://cxone.niceincontact.com/auth/token"):
            attempts["n"] += 1
            return httpx.Response(400, json={"error": "invalid_client"})
        return httpx.Response(200)

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    async with client:
        with pytest.raises(ApplicationCredentialRejectedError):
            await client.get("/x")
    assert attempts["n"] == 1  # a permanent 4xx rejection is not retried like a 429/5xx would be


# --------------------------------------------------------------------------
# Requirement 7: closing the client releases its resources
# --------------------------------------------------------------------------


async def test_aclose_closes_http_client_and_credential_provider(base_config, credential_provider) -> None:
    client = _make_client(base_config, httpx.MockTransport(lambda r: httpx.Response(200)), credential_provider=credential_provider)
    await client.aclose()
    assert client._http.is_closed
    assert credential_provider.closed is True


async def test_context_manager_closes_on_exit_even_after_exception(base_config, credential_provider) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith("https://cxone.niceincontact.com/auth/token"):
            return httpx.Response(500)
        return httpx.Response(200)

    client = _make_client(base_config, httpx.MockTransport(handler), credential_provider=credential_provider)
    with pytest.raises(Exception):
        async with client:
            await client.get("/x")
    assert client._http.is_closed
    assert credential_provider.closed is True
