#!/usr/bin/env python3
"""
Preflight input-shape validation for the CX1 MCP Container App (PBI-03).

Bicep itself (cxone-containerapp.bicep) has no portable, non-experimental
way to assert string shape at compile time — this script is that check,
meant to run in the pipeline against the ACTUAL resolved parameter values
before `deployCxoneMcp` is ever flipped to true, and rejecting exactly the
things docs/PBI-03-BE-implementation.md calls out: a missing/empty
required input, a repository string carrying a tag or digest, a digest
that isn't exactly 64 hex characters, and known placeholder/mutable values
("latest", "quickstart", an all-zero digest) standing in for a real
released image.

This validates SHAPE only — it cannot confirm the image manifest actually
exists in the registry, that the Container Apps Environment ID is real, or
that the pull identity is actually authorized. Those need real Azure
access (see docs/PBI-03-BE-implementation.md's acceptance evidence table).

Usage:
    python scripts/preflight_cxone_mcp.py \
        --registry-server myregistry.azurecr.io \
        --image-repository cx1-mcp \
        --image-sha256 <64 hex chars> \
        --image-pull-identity-id /subscriptions/.../userAssignedIdentities/... \
        --container-apps-environment-id /subscriptions/.../managedEnvironments/... \
        --target-port 8000

Exits 0 and prints nothing if every input is valid; otherwise exits 1 and
prints each problem on its own line.
"""

from __future__ import annotations

import argparse
import re
import sys

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ARM_RESOURCE_ID_RE = re.compile(r"^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/.+$", re.IGNORECASE)

# Known placeholder/mutable stand-ins that must never appear in a
# production input — an all-zero digest, "latest"/other floating tags, and
# discovery's own throwaway quickstart pattern (see discovery/README.md).
_PLACEHOLDER_REPOSITORY_MARKERS = ("quickstart", "placeholder")
_PLACEHOLDER_DIGESTS = {"0" * 64}


def validate_cxone_mcp_inputs(
    *,
    container_apps_environment_id: str,
    registry_server: str,
    image_repository: str,
    image_sha256: str,
    image_pull_identity_id: str,
    target_port: int,
) -> list[str]:
    """Returns a list of problem descriptions; empty means every input is
    shape-valid. Never raises — a caller always gets a list back."""
    errors: list[str] = []

    if not container_apps_environment_id:
        errors.append("containerAppsEnvironmentId is empty — WI 11711 input required before enabling deployment.")
    elif not _ARM_RESOURCE_ID_RE.match(container_apps_environment_id):
        errors.append(
            f"containerAppsEnvironmentId does not look like an ARM resource ID: {container_apps_environment_id!r}"
        )

    if not registry_server:
        errors.append("registryServer is empty.")

    if not image_repository:
        errors.append("imageRepository is empty.")
    else:
        if ":" in image_repository or "@" in image_repository:
            errors.append(
                f"imageRepository must not carry a tag or digest — the digest is supplied separately "
                f"via imageSha256: {image_repository!r}"
            )
        lowered = image_repository.lower()
        for marker in _PLACEHOLDER_REPOSITORY_MARKERS:
            if marker in lowered:
                errors.append(f"imageRepository looks like a placeholder ({marker!r} found): {image_repository!r}")

    if not image_sha256:
        errors.append("imageSha256 is empty.")
    else:
        if not _DIGEST_RE.match(image_sha256):
            errors.append(
                f"imageSha256 must be exactly 64 lowercase hex characters, got "
                f"{len(image_sha256)} chars: {image_sha256!r}"
            )
        elif image_sha256 in _PLACEHOLDER_DIGESTS:
            errors.append(f"imageSha256 is a known placeholder value, not a real released digest: {image_sha256!r}")

    if not image_pull_identity_id:
        errors.append("imagePullIdentityId is empty — WI 11711 input required before enabling deployment.")
    elif not _ARM_RESOURCE_ID_RE.match(image_pull_identity_id):
        errors.append(f"imagePullIdentityId does not look like an ARM resource ID: {image_pull_identity_id!r}")

    if image_pull_identity_id and image_pull_identity_id == container_apps_environment_id:
        errors.append("imagePullIdentityId must not be the same resource ID as containerAppsEnvironmentId.")

    if not (1 <= target_port <= 65535):
        errors.append(f"targetPort must be between 1 and 65535, got {target_port}.")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container-apps-environment-id", default="")
    parser.add_argument("--registry-server", default="")
    parser.add_argument("--image-repository", default="")
    parser.add_argument("--image-sha256", default="")
    parser.add_argument("--image-pull-identity-id", default="")
    parser.add_argument("--target-port", type=int, default=8000)
    args = parser.parse_args(argv)

    errors = validate_cxone_mcp_inputs(
        container_apps_environment_id=args.container_apps_environment_id,
        registry_server=args.registry_server,
        image_repository=args.image_repository,
        image_sha256=args.image_sha256,
        image_pull_identity_id=args.image_pull_identity_id,
        target_port=args.target_port,
    )
    if errors:
        for error in errors:
            print(f"PREFLIGHT FAILED: {error}", file=sys.stderr)
        return 1
    print("Preflight OK: all CX1 MCP Container App inputs are shape-valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
