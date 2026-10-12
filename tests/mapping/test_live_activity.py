"""Synthetic transport only: no live CXone call, no real credentials, no agent or customer data."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from romtech_mcp.cxone.client import CXoneClient
from romtech_mcp.mapping.live_activity import COUNT_FIELDS, fetch_activity, summarize
from tests.cxone.conftest import FakeClock, FakeCredentialProvider, FakeSleeper, make_id_token, zero_jitter

PATH = "/incontactapi/services/v27.0/skills/activity"


def row(sid, in_sla=0, out_sla=0, **extra):
    base = {f: 0 for f in COUNT_FIELDS}
    base.update(skillId=sid, mediaTypeName="Phone Call", serviceLevel=100, inSLA=in_sla, outSLA=out_sla, serverTime="2026-03-24T18:56:57.540Z")
    base.update(extra)
    return base


def make_client(config, body=None, *, status=200, raw=None):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return httpx.Response(200, json={"access_token": "tok", "id_token": make_id_token(), "expires_in": 3600})
        if "cxone-configuration" in url:
            return httpx.Response(200, json={"api_endpoint": "https://api-na1.niceincontact.com"})
        assert request.url.path == PATH
        if raw is not None:
            return httpx.Response(status, content=raw)
        return httpx.Response(status, json=body)

    return CXoneClient(config, FakeCredentialProvider(), transport=httpx.MockTransport(handler), clock=FakeClock(),
                       sleeper=FakeSleeper(), jitter=zero_jitter)


GOOD = {"lastPollTime": "2026-10-12T16:00:03.313Z", "totalRecords": 3,
        "skillActivity": [row(1, 5, 2, agentsLoggedIn=4, queueCount=1), row(2, 3, 3, agentsLoggedIn=2), row(3, 9, 9)]}


async def test_valid_response_is_captured_with_both_timestamps(base_config):
    async with make_client(base_config, GOOD) as client:
        cap = await fetch_activity(client)
    assert cap.complete and cap.last_poll_time == "2026-10-12T16:00:03.313Z" and cap.total_records == 3
    assert cap.captured_at_utc.endswith("Z") and cap.request_started_utc.endswith("Z")


async def test_summary_sums_only_the_requested_skills_and_names_the_missing_ones(base_config):
    async with make_client(base_config, GOOD) as client:
        cap = await fetch_activity(client)
    s = summarize(cap, ("1", "2", "99"))
    assert s["skills_present"] == 2 and s["skills_missing"] == ["99"]  # a missing skill is visible, not counted as zero
    assert s["totals"]["inSLA"] == 8 and s["totals"]["outSLA"] == 5 and s["totals"]["agentsLoggedIn"] == 6
    assert s["in_plus_out_sla"] == 13 and s["sla_percent_from_counts"] == round(100 * 8 / 13, 2)


async def test_no_sla_activity_gives_no_percentage_not_zero_or_hundred(base_config):
    async with make_client(base_config, {**GOOD, "skillActivity": [row(1), row(2), row(3)]}) as client:
        cap = await fetch_activity(client)
    assert summarize(cap, ("1", "2"))["sla_percent_from_counts"] is None


@pytest.mark.parametrize("name,body", [
    ("missing array", {"lastPollTime": "x", "totalRecords": 0}),
    ("missing total", {"lastPollTime": "x", "skillActivity": [row(1)]}),
    ("count differs from total", {"lastPollTime": "x", "totalRecords": 5, "skillActivity": [row(1)]}),
    ("missing poll time", {"totalRecords": 1, "skillActivity": [row(1)]}),
    ("repeated skill", {"lastPollTime": "x", "totalRecords": 2, "skillActivity": [row(1), row(1)]}),
    ("non-integer skill id", {"lastPollTime": "x", "totalRecords": 1, "skillActivity": [row("1")]}),
    ("negative count", {"lastPollTime": "x", "totalRecords": 1, "skillActivity": [row(1, in_sla=-1)]}),
    ("bool count", {"lastPollTime": "x", "totalRecords": 1, "skillActivity": [row(1, in_sla=True)]}),
    ("missing count field", {"lastPollTime": "x", "totalRecords": 1, "skillActivity": [{"skillId": 1, "mediaTypeName": "Phone Call"}]}),
])
async def test_any_irregularity_is_recorded_as_an_issue_never_a_silent_pass(base_config, name, body):
    async with make_client(base_config, body) as client:
        cap = await fetch_activity(client)
    assert not cap.complete and cap.issues, name


async def test_http_error_and_non_json_are_incomplete(base_config):
    async with make_client(base_config, {"error": "x"}, status=403) as client:
        assert not (await fetch_activity(client)).complete
    async with make_client(base_config, raw=b"<html/>") as client:
        cap = await fetch_activity(client)
    assert cap.issues == ("not_json",) and cap.rows == ()


async def test_capture_never_keeps_per_row_server_time_or_extra_fields(base_config):
    body = {**GOOD, "skillActivity": [row(1, agentName="CANARY-AGENT", emailFromAddress="x@y.example")]}
    body["totalRecords"] = 1
    async with make_client(base_config, body) as client:
        cap = await fetch_activity(client)
    blob = repr(cap)
    assert "CANARY-AGENT" not in blob and "x@y.example" not in blob and "2026-03-24" not in blob


# ------------------------------------------------------------------------------------ CLI
@pytest.fixture
def script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("capture_live_activity",
                                                  Path(__file__).resolve().parents[2] / "scripts" / "capture_live_activity.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def test_run_samples_repeats_with_the_interval_and_records_each_poll_time(base_config, script):
    polls = iter(["2026-10-12T16:00:00Z", "2026-10-12T16:01:30Z"])
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://cxone.niceincontact.com/auth/token"):
            return httpx.Response(200, json={"access_token": "tok", "id_token": make_id_token(), "expires_in": 3600})
        if "cxone-configuration" in url:
            return httpx.Response(200, json={"api_endpoint": "https://api-na1.niceincontact.com"})
        return httpx.Response(200, json={**GOOD, "lastPollTime": next(polls)})

    client = CXoneClient(base_config, FakeCredentialProvider(), transport=httpx.MockTransport(handler), clock=FakeClock(),
                         sleeper=FakeSleeper(), jitter=zero_jitter)

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async with client:
        out = await script.run_samples(client, ("1", "2"), 2, 60.0, sleep=fake_sleep)
    assert sleeps == [60.0] and [s["last_poll_time"] for s in out] == ["2026-10-12T16:00:00Z", "2026-10-12T16:01:30Z"]
    assert all(s["complete"] for s in out) and out[0]["summary"]["totals"]["inSLA"] == 8


def test_cli_rejects_bad_arguments_and_missing_credentials(tmp_path, script, monkeypatch, capsys):
    out = tmp_path / "o.json"
    assert script.main(["--skill-id", "1", "--samples", "0", "--output", str(out)]) == 2
    assert script.main(["--skill-id", "1", "--interval-seconds", "1", "--output", str(out)]) == 2
    assert script.main(["--output", str(out)]) == 2  # no skills
    monkeypatch.delenv("CXONE_VAULT_URI", raising=False)
    assert script.main(["--skill-id", "1", "--output", str(out)]) == 2
    assert "credentials" in capsys.readouterr().err
    assert script.main(["--skill-id", "1", "--credentials-env-file", str(tmp_path / "missing.env"), "--output", str(out)]) == 2
    assert not out.exists()


def test_skill_ids_load_from_the_scope_evidence_shape(tmp_path, script):
    f = tmp_path / "scope.json"
    f.write_text(json.dumps({"set_a_cs_widget_29": [{"skill_id": "5"}, {"skill_id": "4"}, {"ziven_name": "x"}]}), encoding="utf-8")
    import argparse
    ns = argparse.Namespace(skill_id=["9", "4"], skills_json=f)
    assert script._skill_ids(ns) == ("4", "5", "9")
