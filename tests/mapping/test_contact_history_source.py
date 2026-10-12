"""Synthetic transport only: no live CXone call, no real credentials, no customer data."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from romtech_mcp.cxone.client import CXoneClient
from romtech_mcp.cxone.credentials import EnvFileCredentialProvider
from romtech_mcp.cxone.errors import CredentialLoadError
from romtech_mcp.mapping.contact_history import load_contact_history, resolve_skills
from romtech_mcp.mapping.contact_history_reconcile import ApiContact, ApiContactFetch, compare_contacts
from romtech_mcp.mapping.contact_history_source import ContactEndpointContract, fetch_contacts
from romtech_mcp.mapping.models import ComparisonOutcome, CoverageState
from tests.cxone.conftest import FakeClock, FakeCredentialProvider, FakeSleeper, make_id_token, zero_jitter

from .test_contact_history import cli_args, line, write_csv

W0 = datetime(2026, 10, 1, 4, 0, tzinfo=timezone.utc)
W1 = datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)
PATH = "/incontactapi/services/v27.0/contacts"
SMALL = ContactEndpointContract(page_size=2, max_pages=5)  # small pages so paging is exercised cheaply


def row(cid, skill="11", start="2026-10-01T10:00:00Z", **extra):
    return {"contactId": cid, "skillId": skill, "contactStartDate": start, **extra}


def make_client(config, pages, *, record=None, status=200, after=None):
    """`pages` maps skip -> response body (dict) or a callable returning an httpx.Response."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return httpx.Response(200, json={"access_token": "tok", "id_token": make_id_token(), "expires_in": 3600})
        if "cxone-configuration" in url:
            return httpx.Response(200, json={"api_endpoint": "https://api-na1.niceincontact.com"})
        assert request.url.path == PATH
        params = dict(request.url.params)
        if record is not None:
            record.append(params)
        body = pages.get(int(params["skip"]))
        if callable(body):
            return body()
        if body is None:
            return httpx.Response(status, json={"contacts": [], "totalRecords": 0})
        return httpx.Response(200, json=body)

    return CXoneClient(config, FakeCredentialProvider(), transport=httpx.MockTransport(handler), clock=FakeClock(),
                       sleeper=FakeSleeper(), jitter=zero_jitter)


async def test_full_pagination_is_validated_and_complete_coverage_is_derived(base_config):
    seen: list[dict] = []
    pages = {0: {"contacts": [row("1"), row("2")], "totalRecords": 5},
             2: {"contacts": [row("3"), row("4")], "totalRecords": 5},
             4: {"contacts": [row("5")], "totalRecords": 5}}
    async with make_client(base_config, pages, record=seen) as client:
        fetch = await fetch_contacts(client, W0, W1, contract=SMALL)
    assert fetch.coverage is CoverageState.COMPLETE and fetch.captured is True
    assert [r.contact_id for r in fetch.records] == ["1", "2", "3", "4", "5"]
    p = fetch.provenance
    assert (p.reported_total, p.rows_fetched, p.issues) == (5, 5, ())
    assert [pg["skip"] for pg in p.pages] == [0, 2, 4] and p.contract_version.startswith("contacts-v27.0")
    assert (p.requested_start_utc, p.requested_end_utc) == ("2026-10-01T04:00:00Z", "2026-10-02T04:00:00Z")
    assert "unverified" in p.date_filter_semantics and "client-side" in p.filter_scope
    assert seen[0] == {"startDate": "2026-10-01T04:00:00Z", "endDate": "2026-10-02T04:00:00Z", "top": "2",
                       "skip": "0", "fields": "contactId,skillId,contactStartDate"}


async def test_exact_multiple_of_page_size_stops_without_an_extra_request(base_config):
    seen: list[dict] = []
    pages = {0: {"contacts": [row("1"), row("2")], "totalRecords": 2}}
    async with make_client(base_config, pages, record=seen) as client:
        fetch = await fetch_contacts(client, W0, W1, contract=SMALL)
    assert fetch.coverage is CoverageState.COMPLETE and len(seen) == 1


@pytest.mark.parametrize("name,pages", [
    ("total changes", {0: {"contacts": [row("1"), row("2")], "totalRecords": 4}, 2: {"contacts": [row("3")], "totalRecords": 5}}),
    ("count short of total", {0: {"contacts": [row("1"), row("2")], "totalRecords": 4}, 2: {"contacts": [row("3")], "totalRecords": 4}}),
    ("empty before total", {0: {"contacts": [row("1"), row("2")], "totalRecords": 9}, 2: {"contacts": [], "totalRecords": 9}}),
    ("repeated id across pages", {0: {"contacts": [row("1"), row("2")], "totalRecords": 4}, 2: {"contacts": [row("2"), row("3")], "totalRecords": 4}}),
    ("missing array", {0: {"totalRecords": 2}}),
    ("total missing", {0: {"contacts": [row("1")]}}),
    ("total is a bool", {0: {"contacts": [row("1")], "totalRecords": True}}),
    ("null id", {0: {"contacts": [row(None)], "totalRecords": 1}}),
    ("non-numeric skill", {0: {"contacts": [row("1", skill="abc")], "totalRecords": 1}}),
    ("naive timestamp", {0: {"contacts": [row("1", start="2026-10-01T10:00:00")], "totalRecords": 1}}),
    ("bad timestamp", {0: {"contacts": [row("1", start="yesterday")], "totalRecords": 1}}),
    ("oversized page", {0: {"contacts": [row("1"), row("2"), row("3")], "totalRecords": 3}}),
    ("row not an object", {0: {"contacts": ["x"], "totalRecords": 1}}),
])
async def test_any_validation_failure_is_incomplete_never_complete(base_config, name, pages):
    async with make_client(base_config, pages) as client:
        fetch = await fetch_contacts(client, W0, W1, contract=SMALL)
    assert fetch.coverage is CoverageState.UNKNOWN and fetch.provenance.issues, name


async def test_page_limit_is_enforced(base_config):
    contract = ContactEndpointContract(page_size=1, max_pages=2)
    pages = {0: {"contacts": [row("1")], "totalRecords": 9}, 1: {"contacts": [row("2")], "totalRecords": 9}}
    async with make_client(base_config, pages) as client:
        fetch = await fetch_contacts(client, W0, W1, contract=contract)
    assert fetch.coverage is CoverageState.UNKNOWN and "page_limit_exceeded" in fetch.provenance.issues


async def test_later_page_outage_returns_a_partial_incomplete_result(base_config):
    pages = {0: {"contacts": [row("1"), row("2")], "totalRecords": 4}, 2: lambda: httpx.Response(503)}
    async with make_client(base_config, pages) as client:
        fetch = await fetch_contacts(client, W0, W1, contract=SMALL)
    assert fetch.coverage is CoverageState.UNKNOWN and len(fetch.records) == 2  # the subset is flagged, not hidden
    assert any(i.startswith("fetch_failed_on_page_2") for i in fetch.provenance.issues)


@pytest.mark.parametrize("status", [400, 404, 403])
async def test_non_success_status_is_incomplete(base_config, status):
    pages = {0: lambda: httpx.Response(status, json={"error": "x"})}
    async with make_client(base_config, pages) as client:
        fetch = await fetch_contacts(client, W0, W1, contract=SMALL)
    assert fetch.coverage is CoverageState.UNKNOWN and fetch.records == ()


async def test_not_json_page_is_incomplete(base_config):
    pages = {0: lambda: httpx.Response(200, content=b"<html>not json</html>")}
    async with make_client(base_config, pages) as client:
        fetch = await fetch_contacts(client, W0, W1, contract=SMALL)
    assert fetch.coverage is CoverageState.UNKNOWN and "page_1_not_json" in fetch.provenance.issues


async def test_diagnostics_never_carry_credentials_headers_or_response_fields(base_config):
    canary = "CANARY-CUSTOMER-FIELD-9f3"
    pages = {0: {"contacts": [row(None, canary=canary, phone="+15550001234")], "totalRecords": 1}}
    async with make_client(base_config, pages) as client:
        fetch = await fetch_contacts(client, W0, W1, contract=SMALL)
    blob = json.dumps([fetch.provenance.issues, fetch.provenance.pages, fetch.provenance.__repr__()])
    for forbidden in (canary, "+15550001234", "Bearer", "tok", "test-client-secret", "test-access-key-secret"):
        assert forbidden not in blob, forbidden


async def test_naive_or_inverted_window_is_rejected_locally(base_config):
    async with make_client(base_config, {}) as client:
        with pytest.raises(ValueError):
            await fetch_contacts(client, datetime(2026, 10, 1), W1, contract=SMALL)
        with pytest.raises(ValueError):
            await fetch_contacts(client, W1, W0, contract=SMALL)


async def test_live_fetch_feeds_the_comparison_and_a_partial_fetch_is_unresolved(base_config, tmp_path):
    p = write_csv(tmp_path / "e.csv", [line("1", "1", "Alpha", "10/1/2026 6:00:00 AM"), line("2", "2", "Alpha", "10/1/2026 7:00:00 AM")])
    recs = load_contact_history([p], source_timezone="America/New_York").records
    res = resolve_skills({"Alpha"}, {"Alpha": ["11"]})
    ok_pages = {0: {"contacts": [row("1", start="2026-10-01T10:00:00Z"), row("2", start="2026-10-01T11:00:00Z")], "totalRecords": 2}}
    async with make_client(base_config, ok_pages) as client:
        fetch = await fetch_contacts(client, W0, W1, contract=SMALL)
    c = compare_contacts(recs, res, fetch, window_start_utc=W0, window_end_utc=W1, grain="contact", timestamp_tolerance_seconds=0)
    assert c.outcome is ComparisonOutcome.MATCH and c.api_fetch_is_real_capture is True
    partial = {0: {"contacts": [row("1", start="2026-10-01T10:00:00Z")], "totalRecords": 2}}
    async with make_client(base_config, partial) as client:
        short = await fetch_contacts(client, W0, W1, contract=SMALL)
    c2 = compare_contacts(recs, res, short, window_start_utc=W0, window_end_utc=W1, grain="contact", timestamp_tolerance_seconds=0)
    assert c2.outcome is ComparisonOutcome.UNRESOLVED and any("coverage" in r for r in c2.unresolved_reasons)


async def test_comparison_rejects_a_fetch_whose_recorded_window_differs(base_config, tmp_path):
    p = write_csv(tmp_path / "e.csv", [line("1", "1", "Alpha", "10/1/2026 6:00:00 AM")])
    recs = load_contact_history([p], source_timezone="America/New_York").records
    res = resolve_skills({"Alpha"}, {"Alpha": ["11"]})
    pages = {0: {"contacts": [row("1")], "totalRecords": 1}}
    async with make_client(base_config, pages) as client:
        fetch = await fetch_contacts(client, W0, W1, contract=SMALL)
    other = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)  # a different comparison window than was fetched
    c = compare_contacts(recs, res, fetch, window_start_utc=other, window_end_utc=W1, grain="contact", timestamp_tolerance_seconds=0)
    assert c.outcome is ComparisonOutcome.UNRESOLVED and any("fetch window" in r for r in c.unresolved_reasons)


# ----------------------------------------------------------- development credential provider
async def test_env_file_provider_reads_in_memory_and_errors_carry_no_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text("CXONE_CLIENT_ID=id-1\nCXONE_CLIENT_SECRET='s3cret-value'\nCXONE_ACCESS_KEY_ID=k\n# c\n", encoding="utf-8")
    provider = EnvFileCredentialProvider(env)
    assert await provider.get_secret("x", logical_name="client_secret") == "s3cret-value"
    with pytest.raises(CredentialLoadError) as err:
        await provider.get_secret("x", logical_name="access_key_secret")  # not in the file
    assert "s3cret-value" not in repr(err.value) and "CXONE_ACCESS_KEY_SECRET" in repr(err.value)
    await provider.aclose()
    with pytest.raises(CredentialLoadError):
        await provider.get_secret("x", logical_name="client_id")  # cleared on close


# ------------------------------------------------------------------------------------ CLI
@pytest.fixture
def script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("reconcile_contact_history_live",
                                                  Path(__file__).resolve().parents[2] / "scripts" / "reconcile_contact_history.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def live_args(tmp_path, exports, *extra):
    base = cli_args(tmp_path, exports, "--grain", "contact", "--timestamp-tolerance-seconds", "0", *extra)
    base[base.index("--source-timezone") + 1] = "America/New_York"
    base[base.index("--window-start") + 1] = "2026-10-01T04:00:00Z"
    base[base.index("--window-end") + 1] = "2026-10-02T04:00:00Z"
    return base


def test_live_is_mutually_exclusive_with_fixture_and_import_only(tmp_path, script):
    p = write_csv(tmp_path / "m.csv", [line("1", "1", "Alpha", "10/1/2026 6:00:00 AM")])
    for other in (["--import-only"], ["--api-fixture", str(tmp_path / "x.json")]):
        with pytest.raises(SystemExit) as e:
            script.main(live_args(tmp_path, [p], "--live", *other))
        assert e.value.code == 2


def test_cli_live_records_provenance_and_never_claims_acceptance(tmp_path, script, monkeypatch):
    p = write_csv(tmp_path / "m.csv", [line("1", "1", "Alpha", "10/1/2026 6:00:00 AM")])
    from romtech_mcp.mapping.contact_history_reconcile import FetchProvenance

    def fake_fetch(args):
        return ApiContactFetch(
            (ApiContact("1", "11", datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)),), CoverageState.COMPLETE,
            "/incontactapi/services/v27.0/contacts", "v27.0", True,
            FetchProvenance("contacts-v27.0-test", "2026-10-01T04:00:00Z", "2026-10-02T04:00:00Z", "2026-10-12T12:00:00Z",
                            ({"skip": 0, "rows": 1, "reported_total": 1},), 1, 1, (), "none", "unverified"))

    monkeypatch.setattr(script, "fetch_live", fake_fetch)
    assert script.main(live_args(tmp_path, [p], "--live")) == 0
    out = tmp_path / "out"
    manifest = json.loads(next(out.glob("manifest-*.json")).read_text(encoding="utf-8"))
    assert manifest["api_input"]["source"] == "live" and manifest["api_input"]["real_capture"] is True
    assert manifest["api_input"]["provenance"]["rows_fetched"] == 1 and manifest["acceptance_grade"] is False
    assert manifest["comparison_status"] == "match"


def test_cli_live_without_a_credentials_source_fails_clearly(tmp_path, script, monkeypatch, capsys):
    p = write_csv(tmp_path / "m.csv", [line("1", "1", "Alpha", "10/1/2026 6:00:00 AM")])
    monkeypatch.delenv("CXONE_VAULT_URI", raising=False)
    assert script.main(live_args(tmp_path, [p], "--live")) == 2
    assert "credentials" in capsys.readouterr().err
    assert script.main(live_args(tmp_path, [p], "--live", "--credentials-env-file", str(tmp_path / "missing.env"))) == 2
