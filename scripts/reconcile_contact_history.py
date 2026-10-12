#!/usr/bin/env python3
"""
Offline Contact History reconciliation (PBI-04 closure).

Imports one or more report exports IN PLACE (nothing is copied; telephone and
agent columns are never read), summarizes them, resolves skill names against an
inventory file, and - when API contact records are supplied - compares the two.

API input is a captured/synthetic JSON file (--api-fixture). There is no --live
mode: no contact-detail endpoint has been verified (URL, version, filter
semantics, pagination, fields, retention), and this script will not guess one.
Add it only after that discovery.

Outputs (in --output-dir, sanitized: counts, hashes, skill names; no phone
numbers, agent names or per-contact IDs):
  manifest.json   inputs (basename, SHA-256, rows), code revision/dirty state,
                  assumptions, confirmation note, comparison status
  summary.json    import summary + skill resolution + comparison counts

Exit codes: 0 ok (import-only, or comparison MATCH); 1 MISMATCH; 2 UNRESOLVED or
inputs/usage invalid. Acceptance status is derived separately and is NEVER implied
by a clean exit; this script never changes any confirmation flag.

Usage:
    python scripts/reconcile_contact_history.py \\
        --report "ContactHistory (20).csv" --report "ContactHistory (21).csv" --report "ContactHistory (22).csv" \\
        --source-timezone UTC --window-start 2026-10-01T00:00:00Z --window-end 2026-10-02T00:00:00Z \\
        --skills Skills.csv --source-confirmation "User confirmed the three files are the full day" \\
        --import-only --output-dir docs/evidence/pbi-04
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from romtech_mcp.mapping.contact_history import (
    ContactHistoryError, dedupe_exact, load_contact_history, load_skill_inventory, resolve_skills, summarize,
)
from romtech_mcp.mapping.contact_history_reconcile import (
    MARKER_RULES, REPEAT_RULES, ApiContact, ApiContactFetch, compare_contacts,
)
from romtech_mcp.mapping.models import ComparisonOutcome, CoverageState


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5,
                             cwd=Path(__file__).resolve().parent)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _parse_utc(text: str) -> datetime:
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise argparse.ArgumentTypeError(f"{text!r} needs a UTC offset (e.g. ...Z)")
    return dt.astimezone(timezone.utc)


def _strict_bool(value: object) -> bool:
    """A real JSON boolean only: bool("false") is True, which would mark a synthetic fixture as a real capture."""
    if not isinstance(value, bool):
        raise ValueError("captured must be a JSON boolean")
    return value


def _load_api_fixture(path: Path) -> ApiContactFetch:
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        coverage = CoverageState(raw["coverage"])
        records = tuple(
            ApiContact(str(r["contactId"]), str(r["skillId"]), _parse_utc(r["startUtc"])) for r in raw["records"]
        )
        return ApiContactFetch(
            records=records, coverage=coverage, endpoint_path=raw["endpoint_path"], api_version=raw["api_version"],
            captured=_strict_bool(raw["captured"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise ContactHistoryError(f"{path.name}: not a valid API fixture ({type(exc).__name__})") from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report", action="append", type=Path, required=True, help="report CSV (repeatable)")
    p.add_argument("--source-timezone", required=True, help="IANA zone the export's displayed times are in (explicit; use UTC only if that is the claim)")
    p.add_argument("--timezone-evidence", help="where the timezone claim comes from; without it the run is labelled an assumption")
    p.add_argument("--window-start", type=_parse_utc, required=True)
    p.add_argument("--window-end", type=_parse_utc, required=True)
    p.add_argument("--skills", type=Path, required=True, help="skill inventory CSV ('Skill ID', 'Skill Name')")
    p.add_argument("--source-confirmation", required=True, help="who confirmed the files are complete, as stated")
    p.add_argument("--api-fixture", type=Path, help="captured/synthetic API contact records (JSON)")
    p.add_argument("--import-only", action="store_true", help="import and summarize; no comparison attempted")
    p.add_argument("--grain", help="established comparison grain (e.g. contact); omitted -> comparison is UNRESOLVED")
    p.add_argument("--timestamp-tolerance-seconds", type=float, help="declared up front; 0 = exact")
    p.add_argument("--id-marker-rule", choices=MARKER_RULES,
                   help="named rule for a trailing '*' on contact IDs; the export must satisfy it or the run is UNRESOLVED")
    p.add_argument("--repeat-rule", choices=REPEAT_RULES,
                   help="named rule explaining repeated IDs that differ in team/agent only; covers nothing else")
    p.add_argument("--subset-label", help="label an INTENTIONAL subset comparison (rows outside the window are then "
                   "allowed); the result is never full-day validation")
    p.add_argument("--output-dir", type=Path, required=True)
    return p


def run(args: argparse.Namespace) -> int:
    try:
        imported = load_contact_history(args.report, source_timezone=args.source_timezone)
        inventory = load_skill_inventory(args.skills)
        api = _load_api_fixture(args.api_fixture) if args.api_fixture else None
    except (ContactHistoryError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    summary = summarize(imported.records)
    deduped, removed = dedupe_exact(imported.records)
    resolution = resolve_skills({r.skill_name for r in imported.records}, inventory)

    comparison = None
    status = "not_run (import only)"
    exit_code = 0
    if not args.import_only:
        comparison = compare_contacts(
            imported.records, resolution, api, window_start_utc=args.window_start, window_end_utc=args.window_end,
            grain=args.grain, timestamp_tolerance_seconds=args.timestamp_tolerance_seconds,
            conflict_rule=args.repeat_rule, id_marker_rule=args.id_marker_rule, subset_label=args.subset_label,
        )
        status = comparison.outcome.value
        exit_code = {ComparisonOutcome.MATCH: 0, ComparisonOutcome.MISMATCH: 1}.get(comparison.outcome, 2)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    inventory_hash = hashlib.sha256(args.skills.read_bytes()).hexdigest()
    dirty = _git("status", "--porcelain")
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_revision": _git("rev-parse", "--short", "HEAD"),
        "code_dirty": None if dirty is None else bool(dirty),
        "inputs": [dataclasses.asdict(f) for f in imported.files],
        "skill_inventory": {"basename": args.skills.name, "sha256": inventory_hash, "entries": len(inventory)},
        "source_confirmation": args.source_confirmation,
        "source_timezone": args.source_timezone,
        "timezone_basis": "evidence: " + args.timezone_evidence if args.timezone_evidence else "ASSUMPTION - not established",
        "window_utc": [args.window_start.isoformat(), args.window_end.isoformat()],
        "grain": args.grain,
        "rules": {"id_marker_rule": args.id_marker_rule, "repeat_rule": args.repeat_rule},
        "api_input": None if api is None else {
            "basename": args.api_fixture.name, "endpoint_path": api.endpoint_path, "api_version": api.api_version,
            "real_capture": api.captured, "coverage": api.coverage.value,
        },
        "comparison_status": status,
        "acceptance_grade": False,
        "acceptance_note": ("Never implied by this script. Requires an established grain, a real captured API "
                            "response, a timezone evidence statement, owner acceptance, and unchanged production "
                            "confirmation flags."),
        "not_recorded": ["report generation time", "report filters", "source email date"],
    }
    body: dict[str, Any] = {
        "run_id": run_id,
        "import": dataclasses.asdict(summary),
        "exact_repeats_removed_by_overlap_rule": removed,  # identical in every kept field, agent token included
        "records_after_exact_dedupe": len(deduped),
        "skill_resolution": {
            "resolved": resolution.resolved, "unmatched": list(resolution.unmatched),
            "ambiguous": list(resolution.ambiguous),
        },
    }
    if comparison is not None:
        c = dataclasses.asdict(comparison)
        c.pop("export_only_ids"), c.pop("api_only_ids")  # identities stay out of committed evidence
        c["outcome"] = comparison.outcome.value
        body["comparison"] = c
    (out / f"manifest-{run_id}.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    (out / f"summary-{run_id}.json").write_text(json.dumps(body, indent=2, default=str), encoding="utf-8")
    print(f"run {run_id}: {len(imported.records)} rows, comparison {status}; evidence in {out}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
