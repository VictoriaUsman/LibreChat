"""
Verifies the reporting adapter: it makes exactly one logical call per window
through PBI-02's CXoneClient (so 429/5xx retry, Retry-After and the shared
deadline are the client's, reused rather than reimplemented), wraps any
CXoneError in a sanitized SourceFetchError at the try/except boundary, and
validates/normalizes the response shape rather than trusting it blindly.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from romtech_mcp.cxone.client import CXoneClient
from romtech_mcp.cxone.errors import ThrottlingExhaustedError
from romtech_mcp.mapping.models import CoverageState, ReportingWindow, SourceEndpointConfig
from romtech_mcp.mapping.source import ReportingSource, SourceFetchError, normalize_response_body

from tests.cxone.conftest import FakeClock, FakeCredentialProvider, FakeSleeper, make_id_token, zero_jitter


def _window() -> ReportingWindow:
    return ReportingWindow(
        label="2026-09-23",
        local_start=datetime(2026, 9, 23, tzinfo=timezone.utc),
        local_end=datetime(2026, 9, 24, tzinfo=timezone.utc),
        utc_start=datetime(2026, 9, 23, tzinfo=timezone.utc),
        utc_end=datetime(2026, 9, 24, tzinfo=timezone.utc),
    )


def _endpoint(**overrides) -> SourceEndpointConfig:
    defaults = dict(
        endpoint_path="/skills/summary", api_version="v27.0", param_start="startDate", param_end="endDate",
        response_array_key="skillSummaries", skill_id_field="skillId",
    )
    defaults.update(overrides)
    return SourceEndpointConfig(**defaults)


def _token_response() -> httpx.Response:
    return httpx.Response(200, json={"access_token": "tok", "id_token": make_id_token(), "expires_in": 3600})


def _discovery_response() -> httpx.Response:
    return httpx.Response(200, json={"api_endpoint": "https://api-na1.niceincontact.com"})


def _client(handler, base_config, *, sleeper=None) -> CXoneClient:
    return CXoneClient(
        base_config, FakeCredentialProvider(), transport=httpx.MockTransport(handler),
        clock=FakeClock(), sleeper=sleeper or FakeSleeper(), jitter=zero_jitter,
    )


async def test_fetch_window_normalizes_rows_and_builds_params(base_config) -> None:
    seen_params = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        seen_params.update(dict(request.url.params))
        return httpx.Response(200, json={"skillSummaries": [{"skillId": "1", "contactsOffered": 5}]})

    client = _client(handler, base_config)
    source = ReportingSource(client, _endpoint())
    async with client:
        obs = await source.fetch_window(_window())

    assert obs.coverage == CoverageState.COMPLETE
    assert len(obs.rows) == 1
    assert obs.rows[0].skill_id == "1"
    assert obs.rows[0].raw["contactsOffered"] == 5
    assert seen_params["startDate"] == _window().utc_start.isoformat()
    assert seen_params["endDate"] == _window().utc_end.isoformat()


async def test_row_missing_skill_id_field_is_flagged_but_kept(base_config) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        return httpx.Response(200, json={"skillSummaries": [{"contactsOffered": 5}]})

    client = _client(handler, base_config)
    source = ReportingSource(client, _endpoint())
    async with client:
        obs = await source.fetch_window(_window())

    assert obs.rows[0].skill_id is None
    assert any("skillId" in i.field for i in obs.issues)


async def test_non_dict_row_is_dropped_and_flagged(base_config) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        return httpx.Response(200, json={"skillSummaries": ["not-an-object", {"skillId": "1"}]})

    client = _client(handler, base_config)
    source = ReportingSource(client, _endpoint())
    async with client:
        obs = await source.fetch_window(_window())

    assert len(obs.rows) == 1
    assert any("not an object" in i.message for i in obs.issues)


async def test_missing_response_array_key_is_unknown_coverage(base_config) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        return httpx.Response(200, json={"somethingElse": []})

    client = _client(handler, base_config)
    source = ReportingSource(client, _endpoint())
    async with client:
        obs = await source.fetch_window(_window())

    assert obs.coverage == CoverageState.UNKNOWN
    assert obs.rows == []


async def test_invalid_json_body_is_unknown_coverage_not_a_crash(base_config) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        return httpx.Response(200, content=b"not json")

    client = _client(handler, base_config)
    source = ReportingSource(client, _endpoint())
    async with client:
        obs = await source.fetch_window(_window())

    assert obs.coverage == CoverageState.UNKNOWN
    assert obs.rows == []


async def test_unverified_pagination_marker_downgrades_coverage(base_config) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        return httpx.Response(200, json={"skillSummaries": [{"skillId": "1"}], "nextLink": "https://.../page2"})

    client = _client(handler, base_config)
    source = ReportingSource(client, _endpoint())
    async with client:
        obs = await source.fetch_window(_window())

    assert obs.coverage == CoverageState.UNKNOWN
    assert any("nextLink" in i.field for i in obs.issues)


async def test_cxone_error_is_wrapped_in_a_sanitized_source_fetch_error(base_config) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        return httpx.Response(429)  # exhausts retries -> ThrottlingExhaustedError

    client = _client(handler, base_config)
    source = ReportingSource(client, _endpoint())
    async with client:
        with pytest.raises(SourceFetchError) as excinfo:
            await source.fetch_window(_window())

    assert "ThrottlingExhaustedError" in excinfo.value.cause_repr


def test_normalize_response_body_works_standalone_for_offline_fixture_mode() -> None:
    """scripts/reconcile_dashboard.py's fixture path reuses this directly,
    without a CXoneClient/network call, so offline and live fetches
    validate identically."""
    rows, coverage, issues = normalize_response_body(
        {"skillSummaries": [{"skillId": "1", "contactsOffered": 5}]}, _endpoint()
    )
    assert coverage == CoverageState.COMPLETE
    assert rows[0].skill_id == "1"
    assert issues == []


async def test_client_retries_are_reused_not_reimplemented(base_config) -> None:
    """The adapter makes exactly ONE logical call — retries on 429 are the
    client's own bounded policy, not a second retry loop stacked on top."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return _token_response()
        if "cxone-configuration" in url:
            return _discovery_response()
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(429)
        return httpx.Response(200, json={"skillSummaries": []})

    client = _client(handler, base_config)
    source = ReportingSource(client, _endpoint())
    async with client:
        obs = await source.fetch_window(_window())

    assert obs.coverage == CoverageState.COMPLETE
    assert calls["n"] == 2  # one 429 retried by the client, then success — not re-fetched by the adapter
