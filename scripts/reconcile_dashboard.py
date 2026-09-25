#!/usr/bin/env python3
"""
CLI for dashboard/API metric reconciliation (PBI-04).

Two fetch modes:
  --fixture PATH   Offline: reads pre-captured API response bodies per
                   window label from a JSON file. No network call, no
                   credentials — validates the harness against synthetic or
                   previously-captured data.
  --live           Online: builds a Key Vault credential provider and a
                   CXoneClient (PBI-02 — its bounded retry/backoff/deadline
                   policy governs every call; this script adds no retry
                   logic of its own) and fetches the reference window
                   directly from CXone.

Either way this writes a run manifest plus per-metric results to
--output-dir, and exits nonzero if any REQUIRED comparison (a candidate/
validated, historically-available metric with a dashboard value supplied
via --dashboard-values) came back MISMATCH or UNRESOLVED. A clean exit here
is evidence the harness ran end to end for the given inputs — it is NOT,
by itself, acceptance evidence; docs/PBI-04-BE-mapping.md's checklist is
what actually closes this PBI.

By default this refuses to run against unconfirmed scope/timezone
configuration (see MappingConfig.assert_ready_for_acceptance) — pass
--exploratory to run anyway for early harness validation. Every exploratory
run is stamped in its own manifest as non-acceptance-grade.

Usage:
    python scripts/reconcile_dashboard.py \\
        --config config/cxone-dashboard-mapping.json \\
        --reference-date 2026-09-23 \\
        --fixture fixtures/2026-09-23.json \\
        --dashboard-values dashboard/2026-09-23.json \\
        --output-dir reconcile_runs

    python scripts/reconcile_dashboard.py \\
        --config config/cxone-dashboard-mapping.json \\
        --reference-date 2026-09-23 --live \\
        --vault-url https://kv-romtech-test.vault.azure.net \\
        --dashboard-values dashboard/2026-09-23.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from romtech_mcp.mapping.config import MappingConfig, MappingConfigError, load_mapping_config, validate_mapping
from romtech_mcp.mapping.models import (
    ComparisonOutcome,
    CoverageState,
    MappingStatus,
    MetricAvailability,
    ReportingWindow,
    SourceObservation,
    ValidationIssue,
)
from romtech_mcp.mapping.reconcile import compare_metric, derive_metric
from romtech_mcp.mapping.scope import UnsupportedTeamScopeError, select_scope
from romtech_mcp.mapping.source import ReportingSource, SourceFetchError, normalize_response_body
from romtech_mcp.mapping.windows import UnconfirmedConfigurationError, build_reporting_day


def _git(*args: str) -> str | None:
    """Best-effort only — a hung/missing git must never take the run down.
    subprocess.run(timeout=...) raises TimeoutExpired, a SubprocessError,
    NOT an OSError; catch both (a lesson from PBI-03's own review)."""
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5,
                              cwd=Path(__file__).resolve().parent)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _git_commit() -> str | None:
    return _git("rev-parse", "--short", "HEAD") or None


def _git_dirty() -> bool | None:
    status = _git("status", "--porcelain")
    return None if status is None else bool(status)


def _load_json_file(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _fetch_offline(fixture: dict[str, Any], window: ReportingWindow, endpoint) -> SourceObservation:
    body = fixture.get(window.label)
    request_params = {endpoint.param_start: window.utc_start.isoformat(), endpoint.param_end: window.utc_end.isoformat()}
    if body is None:
        return SourceObservation(
            window=window, endpoint_path=endpoint.endpoint_path, api_version=endpoint.api_version,
            request_params=request_params, requested_at_utc=datetime.now(timezone.utc), rows=[],
            coverage=CoverageState.UNKNOWN,
            issues=[ValidationIssue(metric_key="<source>", field="fixture", message=f"no fixture entry for window {window.label!r}")],
        )
    rows, coverage, issues = normalize_response_body(body, endpoint)
    return SourceObservation(
        window=window, endpoint_path=endpoint.endpoint_path, api_version=endpoint.api_version,
        request_params=request_params, requested_at_utc=datetime.now(timezone.utc), rows=rows,
        coverage=coverage, issues=issues,
    )


async def _fetch_live(config: MappingConfig, window: ReportingWindow, *, vault_url: str, managed_identity_client_id: str | None) -> SourceObservation:
    # Imported lazily: the azure SDKs are only required for --live, matching
    # cxone/credentials.py's own lazy-import discipline for the same reason.
    from romtech_mcp.cxone.config import CXoneConfig
    from romtech_mcp.cxone.client import CXoneClient
    from romtech_mcp.cxone.credentials import AzureKeyVaultCredentialProvider

    cxone_config = CXoneConfig(vault_url=vault_url, api_version=config.source.api_version,
                                azure_managed_identity_client_id=managed_identity_client_id)
    credentials = AzureKeyVaultCredentialProvider(vault_url=vault_url, azure_managed_identity_client_id=managed_identity_client_id)
    client = CXoneClient(cxone_config, credentials)
    try:
        source = ReportingSource(client, config.source)
        return await source.fetch_window(window)
    finally:
        await client.aclose()


def _write_failure_manifest(
    run_id: str, generated_at_utc: str, args: argparse.Namespace, config: MappingConfig, fetch_mode: str,
    window: ReportingWindow, exc: SourceFetchError,
) -> Path:
    manifest = {
        "run_id": run_id,
        "generated_at_utc": generated_at_utc,
        "commit": _git_commit(),
        "dirty_tree": _git_dirty(),
        "exploratory": args.exploratory,
        "fetch_mode": fetch_mode,
        "config_path": str(args.config),
        "reference_date": args.reference_date,
        "window": {"label": window.label, "utc_start": window.utc_start.isoformat(), "utc_end": window.utc_end.isoformat()},
        "resolved": False,
        "reason": "fetch_failed",
        "fetch_error": {"endpoint_path": exc.endpoint_path, "window_label": exc.window_label, "cause": exc.cause_repr},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f"reconcile_{args.reference_date}_{run_id}.json"
    path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"Saved failure manifest to {path}", file=sys.stderr)
    return path


def _run(args: argparse.Namespace) -> int:
    run_id = uuid.uuid4().hex[:12]
    generated_at_utc = datetime.now(timezone.utc).isoformat()

    try:
        config = load_mapping_config(args.config)
    except MappingConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2

    mapping_issues = validate_mapping(config)
    for issue in mapping_issues:
        stream = sys.stderr if issue.severity == "error" else sys.stdout
        print(f"MAPPING {issue.severity.upper()}: {issue.metric_key}.{issue.field}: {issue.message}", file=stream)
    if any(i.severity == "error" for i in mapping_issues):
        print("Refusing to reconcile: the mapping file itself has unresolved structural errors.", file=sys.stderr)
        return 2

    # A metric that will actually be reconciled (not unsupported/live-only)
    # and declares an sla_reference/baseline_reference depends on that
    # configuration being confirmed too — checking readiness with the
    # defaults (require_sla=False, require_baseline=False) regardless of
    # what the mapping actually needs would let a dependent metric run
    # against unconfirmed SLA/baseline rules.
    reconcilable = [
        m for m in config.metrics
        if m.status != MappingStatus.UNSUPPORTED and m.availability != MetricAvailability.LIVE_ONLY
    ]
    require_sla = any(m.sla_reference for m in reconcilable)
    require_baseline = any(m.baseline_reference for m in reconcilable)

    if not args.exploratory:
        try:
            config.assert_ready_for_acceptance(require_sla=require_sla, require_baseline=require_baseline)
        except UnconfirmedConfigurationError as exc:
            print(f"NOT READY: {exc}", file=sys.stderr)
            print("Pass --exploratory to run anyway for harness validation (non-acceptance-grade).", file=sys.stderr)
            return 2

    reference_date = date.fromisoformat(args.reference_date)
    window = build_reporting_day(
        reference_date, config.timezone, label=reference_date.isoformat(), allow_unconfirmed=args.exploratory
    )

    fetch_mode = "live" if args.live else "fixture"
    try:
        if args.live:
            observation = asyncio.run(
                _fetch_live(config, window, vault_url=args.vault_url, managed_identity_client_id=args.azure_managed_identity_client_id)
            )
        else:
            fixture = _load_json_file(args.fixture)
            observation = _fetch_offline(fixture, window, config.source)
    except SourceFetchError as exc:
        # Never crash without saving evidence — a fetch failure (throttled,
        # errored, deadline-exceeded — all already retried per CXoneClient's
        # own bounded policy before this was raised) still gets a manifest.
        _write_failure_manifest(run_id, generated_at_utc, args, config, fetch_mode, window, exc)
        print(f"FETCH FAILED: {exc}", file=sys.stderr)
        return 1

    try:
        scoped = select_scope(
            observation.rows, config.scope, source_coverage=observation.coverage,
            source_endpoint_path=observation.endpoint_path, source_api_version=observation.api_version,
        )
    except UnsupportedTeamScopeError as exc:
        print(f"NOT READY: {exc}", file=sys.stderr)
        return 2

    dashboard_values_given = args.dashboard_values is not None
    dashboard_values = _load_json_file(args.dashboard_values)
    tolerances = _load_json_file(args.tolerances)

    results: list[dict[str, Any]] = []
    required_failure = False

    for metric in config.metrics:
        entry: dict[str, Any] = {"metric_key": metric.key, "dashboard_label": metric.dashboard_label, "status": metric.status.value}

        if metric.status == MappingStatus.UNSUPPORTED:
            entry.update(outcome="unsupported", reason=metric.unsupported_reason or "no reason recorded")
            results.append(entry)
            continue

        if metric.availability == MetricAvailability.LIVE_ONLY:
            entry.update(outcome="historical_not_applicable",
                         reason="metric is live_only — no historical reconciliation attempted")
            results.append(entry)
            continue

        if metric.status == MappingStatus.UNCONFIRMED or metric.availability == MetricAvailability.UNCONFIRMED:
            entry.update(outcome="unresolved", reason="metric status/availability not yet confirmed")
            results.append(entry)
            if dashboard_values_given:
                required_failure = True
            continue

        if metric.formula is None:
            entry.update(outcome="unresolved", reason="no formula declared for this metric")
            results.append(entry)
            if dashboard_values_given:
                required_failure = True
            continue

        try:
            observation_value = derive_metric(metric, scoped, window)
        except ValueError as exc:
            entry.update(outcome="unresolved", reason=f"formula error: {exc}")
            results.append(entry)
            if dashboard_values_given:
                required_failure = True
            continue

        entry["api_value"] = observation_value.value
        entry["api_value_state"] = observation_value.value_state.value
        entry["api_notes"] = list(observation_value.notes)

        if not dashboard_values_given:
            entry["outcome"] = "extracted_only"
            results.append(entry)
            continue

        dashboard_value = dashboard_values.get(metric.key)
        tolerance = tolerances.get(metric.key)
        try:
            comparison = compare_metric(metric.key, observation_value, dashboard_value, unit=metric.unit, tolerance=tolerance)
        except ValueError as exc:
            entry.update(outcome="unresolved", reason=f"invalid comparison input: {exc}")
            results.append(entry)
            required_failure = True
            continue
        entry.update(
            dashboard_value=comparison.dashboard_value,
            absolute_delta=comparison.absolute_delta,
            percentage_delta=comparison.percentage_delta,
            tolerance=comparison.tolerance,
            outcome=comparison.outcome.value,
            explanation=comparison.explanation,
        )
        if comparison.outcome is not ComparisonOutcome.MATCH:
            required_failure = True
        results.append(entry)

    manifest = {
        "run_id": run_id,
        "generated_at_utc": generated_at_utc,
        "commit": _git_commit(),
        "dirty_tree": _git_dirty(),
        "exploratory": args.exploratory,
        "fetch_mode": fetch_mode,
        "config_path": str(args.config),
        "config_schema_version": config.schema_version,
        "reference_date": args.reference_date,
        "window": {
            "label": window.label,
            "local_start": window.local_start.isoformat(),
            "local_end": window.local_end.isoformat(),
            "utc_start": window.utc_start.isoformat(),
            "utc_end": window.utc_end.isoformat(),
        },
        "source": {
            "endpoint_path": observation.endpoint_path,
            "api_version": observation.api_version,
            "request_params": observation.request_params,
            "requested_at_utc": observation.requested_at_utc.isoformat(),
            "coverage": observation.coverage.value,
            "issues": [i.__dict__ for i in observation.issues],
        },
        "scope": {
            "requested_ids": sorted(scoped.requested_ids),
            "returned_ids": sorted(scoped.returned_ids),
            "included_ids": sorted(scoped.included_ids),
            "excluded_ids": sorted(scoped.excluded_ids),
            "missing_ids": sorted(scoped.missing_ids),
            "duplicate_ids": sorted(scoped.duplicate_ids),
            "coverage": scoped.coverage.value,
        },
        "mapping_issues": [i.__dict__ for i in mapping_issues],
        "results": results,
        "dashboard_values_supplied": dashboard_values_given,
        "required_failure": required_failure,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / f"reconcile_{args.reference_date}_{run_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    print(json.dumps(manifest, indent=2, default=str))
    print(f"\nSaved run manifest to {manifest_path}")
    if args.exploratory:
        print("EXPLORATORY RUN — not acceptance evidence (unconfirmed configuration).", file=sys.stderr)
    if required_failure:
        print("UNRESOLVED/MISMATCH among required comparisons — see results above.", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True, help="Path to the dashboard-mapping JSON config.")
    parser.add_argument("--reference-date", required=True, help="YYYY-MM-DD, in the confirmed business timezone.")
    parser.add_argument("--live", action="store_true", help="Fetch from CXone directly instead of a fixture file.")
    parser.add_argument("--fixture", type=Path, help="Offline mode: JSON file mapping window label -> raw response body.")
    parser.add_argument("--vault-url", help="Live mode: Key Vault URL for CXone credentials.")
    parser.add_argument("--azure-managed-identity-client-id", help="Live mode: user-assigned identity client ID, if not system-assigned.")
    parser.add_argument("--dashboard-values", type=Path, help="JSON file mapping metric key -> captured dashboard value.")
    parser.add_argument("--tolerances", type=Path, help="JSON file mapping metric key -> agreed absolute tolerance.")
    parser.add_argument("--output-dir", type=Path, default=Path("reconcile_runs"), help="Where to write the run manifest.")
    parser.add_argument("--exploratory", action="store_true",
                         help="Run even with unconfirmed scope/timezone configuration (non-acceptance-grade).")
    args = parser.parse_args(argv)

    if args.live and not args.vault_url:
        parser.error("--live requires --vault-url")
    if not args.live and not args.fixture:
        parser.error("either --live or --fixture is required")

    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
