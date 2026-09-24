#!/usr/bin/env python3
"""
Pipeline entry point for PBI-03's preflight check. Resolves an environment's
.bicepparam file to its actual deployment parameter VALUES (via
`az bicep build-params`) — the same values `az deployment group create`
would use — and runs validate_cxone_mcp_inputs() against exactly those,
not against hand-typed CLI flags that could drift from the real file.

If deployCxoneMcp resolves to false, there is nothing to validate (the
Container App module never deploys), so this exits 0 immediately without
needing any of the other cxone* parameters to be filled in.

Usage (wired into ROMTechMCP.pipelines/{dev,test,prod}.yml, before the
what-if/create stages):
    python scripts/preflight_from_bicepparam.py --bicepparam-file ROMTechMCP.bicep/main.dev.bicepparam

Exits 0 (and prints what it decided) when there's nothing to block
deployment; exits 1 with each problem on its own line otherwise — the
pipeline step must fail the build on a nonzero exit.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from preflight_cxone_mcp import validate_cxone_mcp_inputs  # noqa: E402


class ResolutionError(RuntimeError):
    """The bicepparam file couldn't be resolved to concrete values at all —
    distinct from the values resolving fine but failing validation."""


def resolve_bicepparam(bicepparam_file: Path) -> dict[str, object]:
    """Returns {parameter_name: value} for every parameter in the file,
    exactly as `az deployment group create --parameters @<this>` would see
    them — not a hand-parsed guess at the .bicepparam syntax."""
    result = subprocess.run(
        ["az", "bicep", "build-params", "--file", str(bicepparam_file), "--stdout"],
        capture_output=True,
        text=True,
        shell=(sys.platform == "win32"),
    )
    if result.returncode != 0:
        raise ResolutionError(
            f"az bicep build-params failed for {bicepparam_file}: {result.stderr.strip()[:1000]}"
        )
    try:
        outer = json.loads(result.stdout)
        params = json.loads(outer["parametersJson"])["parameters"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise ResolutionError(f"Unexpected az bicep build-params output shape: {exc}") from exc
    return {name: entry["value"] for name, entry in params.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bicepparam-file", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        values = resolve_bicepparam(args.bicepparam_file)
    except ResolutionError as exc:
        print(f"PREFLIGHT FAILED (could not resolve parameters): {exc}", file=sys.stderr)
        return 1

    if not values.get("deployCxoneMcp"):
        print("deployCxoneMcp is false — CX1 MCP is not being deployed, nothing to preflight.")
        return 0

    errors = validate_cxone_mcp_inputs(
        container_apps_environment_id=str(values.get("cxoneContainerAppsEnvironmentId", "")),
        registry_server=str(values.get("cxoneRegistryServer", "")),
        image_repository=str(values.get("cxoneImageRepository", "")),
        image_sha256=str(values.get("cxoneImageSha256", "")),
        image_pull_identity_id=str(values.get("cxoneImagePullIdentityId", "")),
        target_port=int(values.get("cxoneTargetPort", 0)),
    )
    if errors:
        print(f"PREFLIGHT FAILED for {args.bicepparam_file} (deployCxoneMcp=true):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Preflight OK: {args.bicepparam_file}'s resolved CX1 MCP inputs are shape-valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
