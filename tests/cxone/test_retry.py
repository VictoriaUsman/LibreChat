"""
Verifies requirement 5 from PBI-02: 429/5xx retry with bounded attempts,
Retry-After and the overall deadline are both honored, and exhausted
retries / malformed JSON / timeouts / 403 all terminate predictably.
"""

from __future__ import annotations

import httpx
import pytest

from romtech_mcp.cxone.client import CXoneClient
from romtech_mcp.cxone.config import RetryPolicy
from romtech_mcp.cxone.errors import (
    DeadlineExceededError,
    MalformedProtocolResponseError,
    ThrottlingExhaustedError,
    TransientServerExhaustedError,
)

from .conftest import FakeClock, FakeCredentialProvider, FakeSleeper, make_id_token, zero_jitter


def _token_response(access_token: str = "tok", expires_in: float = 3600) -> httpx.Response:
    return httpx.Response(
        200,
        json={"access_token": access_token, "id_token": make_id_token(), "expires_in": expires_in},
    )


def _discovery_response() -> httpx.Response:
    return httpx.Response(200, json={"api_endpoint": "https://api-na1.niceincontact.com"})


def _make_client(config, transport, *, clock=None, sleeper=None) -> CXoneClient:
    return CXoneClient(
        config,
        FakeCredentialProvider(),
        transport=transport,
        clock=clock or FakeClock(),
        sleeper=sleeper or FakeSleeper(),
        jitter=zero_jitter,
    )


async def test_429_retries_then_succeeds_within_bounded_attempts(base_config) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429)
        return httpx.Response(200, json={"skillSummaries": []})

    sleeper = FakeSleeper()
    client = _make_client(base_config, httpx.MockTransport(handler), sleeper=sleeper)
    async with client:
        response = await client.get("/x")
    assert response.status_code == 200
    assert calls["n"] == 3  # max_attempts=3 in base_config: 2 failures then success, within budget
    assert len(sleeper.sleeps) == 2


async def test_429_exhausts_retries_and_raises_throttling_error(base_config) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        calls["n"] += 1
        return httpx.Response(429)

    client = _make_client(base_config, httpx.MockTransport(handler), sleeper=FakeSleeper())
    async with client:
        with pytest.raises(ThrottlingExhaustedError) as exc_info:
            await client.get("/x")
    assert calls["n"] == 3  # exactly max_attempts, not unbounded
    assert exc_info.value.attempt_count == 3


async def test_5xx_retries_then_exhausts(base_config) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        calls["n"] += 1
        return httpx.Response(503)

    client = _make_client(base_config, httpx.MockTransport(handler), sleeper=FakeSleeper())
    async with client:
        with pytest.raises(TransientServerExhaustedError) as exc_info:
            await client.get("/x")
    assert calls["n"] == 3
    assert exc_info.value.status_code == 503


async def test_network_error_is_retried_as_transient(base_config) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("simulated connect failure", request=request)
        return httpx.Response(200, json={"skillSummaries": []})

    client = _make_client(base_config, httpx.MockTransport(handler), sleeper=FakeSleeper())
    async with client:
        response = await client.get("/x")
    assert response.status_code == 200
    assert calls["n"] == 2


async def test_retry_after_seconds_is_honored(base_config) -> None:
    sleeper = FakeSleeper()
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json={"skillSummaries": []})

    client = _make_client(base_config, httpx.MockTransport(handler), sleeper=sleeper)
    async with client:
        await client.get("/x")
    assert sleeper.sleeps == [7.0]  # exact Retry-After value, not the exponential default


async def test_retry_after_exceeding_deadline_fails_fast_not_late(base_config) -> None:
    """A Retry-After longer than the remaining deadline must fail
    immediately, not sleep the full (truncated) amount and then fail
    anyway — the spec explicitly calls this out."""
    from romtech_mcp.cxone.config import CXoneConfig, SecretNames

    config = CXoneConfig(
        vault_url=base_config.vault_url,
        secret_names=SecretNames(),
        total_deadline_seconds=5.0,  # short deadline
        retry=RetryPolicy(max_attempts=3, base_delay_seconds=1.0, max_delay_seconds=30.0),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        return httpx.Response(429, headers={"Retry-After": "3600"})  # far longer than the 5s deadline

    sleeper = FakeSleeper()
    client = _make_client(config, httpx.MockTransport(handler), sleeper=sleeper)
    async with client:
        with pytest.raises(DeadlineExceededError):
            await client.get("/x")
    assert sleeper.sleeps == []  # never actually slept the 3600s


async def test_deadline_exceeded_before_first_retry_check_terminates(base_config) -> None:
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            clock.advance(1000)  # blow the deadline mid-authentication
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        return httpx.Response(200, json={"skillSummaries": []})

    client = _make_client(base_config, httpx.MockTransport(handler), clock=clock, sleeper=FakeSleeper(clock))
    async with client:
        with pytest.raises(DeadlineExceededError):
            await client.get("/x")


async def test_malformed_json_terminates_predictably(base_config) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith("https://cxone.niceincontact.com/auth/token"):
            return httpx.Response(200, content=b"not json at all")
        return httpx.Response(200)

    client = _make_client(base_config, httpx.MockTransport(handler), sleeper=FakeSleeper())
    async with client:
        with pytest.raises(MalformedProtocolResponseError) as exc_info:
            await client.get("/x")
    assert exc_info.value.reason_code == "invalid_json"


async def test_read_timeout_is_retried_then_exhausts(base_config) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        raise httpx.ReadTimeout("simulated read timeout", request=request)

    client = _make_client(base_config, httpx.MockTransport(handler), sleeper=FakeSleeper())
    async with client:
        with pytest.raises(TransientServerExhaustedError) as exc_info:
            await client.get("/x")
    assert exc_info.value.reason_code == "network_error"


async def test_slow_vault_access_is_bounded_by_the_overall_deadline(base_config) -> None:
    """Vault access shares the same total deadline as auth/discovery/API —
    a credential provider that never returns must not hang the client
    forever; it should be cut off once the deadline is exhausted."""
    import asyncio

    from romtech_mcp.cxone.config import CXoneConfig, SecretNames

    config = CXoneConfig(
        vault_url=base_config.vault_url,
        secret_names=SecretNames(),
        total_deadline_seconds=0.2,  # short on purpose: only the mechanism is under test, not real timing
    )

    class _HangingCredentialProvider:
        async def get_secret(self, secret_name: str, *, logical_name: str) -> str:
            await asyncio.sleep(3600)  # would hang forever without the deadline wrap
            return "unreachable"

        async def aclose(self) -> None:
            pass

    client = CXoneClient(
        config,
        _HangingCredentialProvider(),
        transport=httpx.MockTransport(lambda r: httpx.Response(200)),
        clock=FakeClock(),
        sleeper=FakeSleeper(),
        jitter=zero_jitter,
    )
    async with client:
        with pytest.raises(DeadlineExceededError):
            await asyncio.wait_for(client.get("/x"), timeout=2)  # outer safety net for the test itself


async def test_slow_in_flight_request_does_not_complete_past_the_deadline(base_config) -> None:
    """A response that would otherwise arrive successfully must not be
    honored once it has taken longer than the deadline it was governed
    by — a deadline check only before the await isn't enough on its own."""
    import time

    from romtech_mcp.cxone.config import CXoneConfig, RetryPolicy, SecretNames
    from romtech_mcp.cxone.errors import DeadlineExceededError

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        import asyncio as _asyncio

        await _asyncio.sleep(0.125)
        return httpx.Response(200, json={"skillSummaries": []})

    config = CXoneConfig(
        vault_url=base_config.vault_url,
        secret_names=SecretNames(),
        total_deadline_seconds=0.03,
        retry=RetryPolicy(max_attempts=1),
    )
    client = _make_client(config, httpx.MockTransport(handler), sleeper=FakeSleeper())
    async with client:
        t0 = time.monotonic()
        with pytest.raises(DeadlineExceededError):
            await client.get("/x")
        assert time.monotonic() - t0 < 0.125  # cut off near the 30ms deadline, not after the full 125ms


async def test_lock_wait_is_also_bounded_by_the_caller_s_own_deadline(base_config) -> None:
    """A caller queued behind a slow concurrent authentication cycle must
    not wait past its OWN remaining deadline just because asyncio.Lock has
    no timeout of its own."""
    import asyncio as _asyncio

    from romtech_mcp.cxone.config import CXoneConfig, SecretNames
    from romtech_mcp.cxone.errors import DeadlineExceededError

    release_slow_caller = _asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            await release_slow_caller.wait()  # holds the auth lock until the test lets it go
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        return httpx.Response(200, json={"skillSummaries": []})

    # Both callers share one client (one lock) but the test drives each
    # call's own Deadline directly rather than through get(), since get()
    # always uses config.total_deadline_seconds for both.
    client = _make_client(base_config, httpx.MockTransport(handler), sleeper=FakeSleeper())
    slow_config = CXoneConfig(vault_url=base_config.vault_url, secret_names=SecretNames(), total_deadline_seconds=10.0)
    fast_config = CXoneConfig(vault_url=base_config.vault_url, secret_names=SecretNames(), total_deadline_seconds=0.05)

    from romtech_mcp.cxone.client import Deadline

    slow_deadline = Deadline(client._clock, slow_config.total_deadline_seconds)
    fast_deadline = Deadline(client._clock, fast_config.total_deadline_seconds)

    async def slow_caller() -> None:
        await client._ensure_auth(slow_deadline)  # acquires the lock first, then blocks in the handler

    async def fast_caller() -> None:
        await _asyncio.sleep(0.01)  # let the slow caller grab the lock first
        with pytest.raises(DeadlineExceededError):
            await client._ensure_auth(fast_deadline)
        release_slow_caller.set()

    async with client:
        await _asyncio.wait_for(_asyncio.gather(slow_caller(), fast_caller()), timeout=2)
