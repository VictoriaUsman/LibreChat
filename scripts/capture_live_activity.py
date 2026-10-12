#!/usr/bin/env python3
"""
Read-only paired-observation capture for the live `GET /skills/activity` endpoint.

Run this while someone reads the dashboard widget at the same moment, then compare. It records, for a stated skill list,
the summed `inSLA`/`outSLA`, queue and agent counts, the source's own `lastPollTime`, and this machine's receive time. It
repeats `--samples` times `--interval-seconds` apart so a widget refresh can be matched to a poll. It never sets
`live.verified` and never interprets the fields; the person comparing records the widget values next to it.

Skill list: `--skills-json` (a file with a list of objects having `skill_id`, e.g. the CS scope evidence file's
`set_a_cs_widget_29`) or repeated `--skill-id`. Credentials: `--credentials-env-file` (development only) or Key Vault.

Output: one JSON file with counts and timestamps only (no agent, customer or credential data).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from romtech_mcp.mapping.live_activity import ActivityCapture, fetch_activity, summarize


def _skill_ids(args: argparse.Namespace) -> tuple[str, ...]:
    ids: list[str] = [str(s) for s in args.skill_id or []]
    if args.skills_json:
        raw = json.loads(args.skills_json.read_text(encoding="utf-8"))
        rows = raw["set_a_cs_widget_29"] if isinstance(raw, dict) and "set_a_cs_widget_29" in raw else raw
        ids += [str(r["skill_id"]) for r in rows if isinstance(r, dict) and r.get("skill_id")]
    ids = sorted(set(ids))
    if not ids:
        raise ValueError("no skill IDs given")
    return tuple(ids)


async def run_samples(client, ids: tuple[str, ...], samples: int, interval: float, sleep=asyncio.sleep) -> list[dict]:
    out: list[dict] = []
    for i in range(samples):
        if i:
            await sleep(interval)
        cap: ActivityCapture = await fetch_activity(client)
        out.append({
            "sample": i + 1, "captured_at_utc": cap.captured_at_utc, "request_started_utc": cap.request_started_utc,
            "last_poll_time": cap.last_poll_time, "total_records": cap.total_records, "complete": cap.complete,
            "issues": list(cap.issues), "summary": summarize(cap, ids),
        })
    return out


def build_client(args: argparse.Namespace):
    from romtech_mcp.cxone.client import CXoneClient
    from romtech_mcp.cxone.config import CXoneConfig

    if args.credentials_env_file is not None:
        if not args.credentials_env_file.is_file():
            raise ValueError("credentials env file not found")
        from romtech_mcp.cxone.credentials import EnvFileCredentialProvider

        return CXoneClient(CXoneConfig(vault_url="https://dev-env-file-credentials.invalid"),
                           EnvFileCredentialProvider(args.credentials_env_file))
    from romtech_mcp.cxone.bootstrap import BootstrapError, build_credential_provider, build_cxone_config

    try:
        config = build_cxone_config()
    except BootstrapError as exc:
        raise ValueError(f"live capture needs credentials: {exc}") from None
    return CXoneClient(config, build_credential_provider(config))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--skills-json", type=Path)
    p.add_argument("--skill-id", action="append")
    p.add_argument("--credentials-env-file", type=Path)
    p.add_argument("--samples", type=int, default=3)
    p.add_argument("--interval-seconds", type=float, default=60.0)
    p.add_argument("--label", default="", help="free text identifying the scope/window the person compares against")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if not 1 <= args.samples <= 20 or args.interval_seconds < 5:
        print("error: --samples must be 1-20 and --interval-seconds at least 5", file=sys.stderr)
        return 2
    try:
        ids = _skill_ids(args)
        client = build_client(args)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    async def go() -> list[dict]:
        async with client:
            return await run_samples(client, ids, args.samples, args.interval_seconds)

    samples = asyncio.run(go())
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "mode": "real_read_only_paired_capture",
        "endpoint": "/skills/activity", "label": args.label, "skill_ids": list(ids), "samples": samples,
        "acceptance_grade": False,
        "note": "Counts and timestamps only. Field meanings and equivalence with the dashboard widgets are NOT verified by "
                "this file; the widget values observed at the same moments must be recorded beside it.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    ok = all(s["complete"] for s in samples)
    print(f"{len(samples)} sample(s), {len(ids)} skills, complete={ok}; wrote {args.output.name}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
