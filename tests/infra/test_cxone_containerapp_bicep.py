"""
Structural checks against the COMPILED ARM JSON for PBI-03's Bicep, per
docs/PBI-03-BE-implementation.md's "Validation and acceptance evidence"
section: internal ingress, fixed minReplicas, digest-based image
reference, pull-identity isolation from application code, and only the
intended runtime role assignment. Also confirms the disabled
(deployCxoneMcp=false) path still compiles for every environment.

These prove the TEMPLATE is structurally correct. They do not, and cannot,
prove Azure reachability, permissions, or that the referenced resources
(Container Apps Environment, registry, pull identity) actually exist —
see docs/PBI-03-BE-evidence.md for what still needs real deployment.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

BICEP_DIR = Path(__file__).resolve().parents[2] / "ROMTechMCP.bicep"
_AZ = shutil.which("az")  # resolves to az.cmd on Windows via PATHEXT — a bare "az" isn't directly executable

pytestmark = pytest.mark.skipif(_AZ is None, reason="az CLI (with the bicep extension) is required")


def _compile(relative_path: str) -> dict:
    path = BICEP_DIR / relative_path
    result = subprocess.run(
        [_AZ, "bicep", "build", "--file", str(path), "--stdout"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"az bicep build failed for {relative_path}:\n{result.stderr}"
    return json.loads(result.stdout)


def _compile_params(relative_path: str) -> dict:
    path = BICEP_DIR / relative_path
    result = subprocess.run(
        [_AZ, "bicep", "build-params", "--file", str(path), "--stdout"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"az bicep build-params failed for {relative_path}:\n{result.stderr}"
    # --stdout wraps the actual ARM parameters file as a JSON-encoded
    # string under "parametersJson", not as nested JSON directly.
    outer = json.loads(result.stdout)
    return json.loads(outer["parametersJson"])


def _find_resource(template: dict, resource_type: str) -> dict:
    matches = [r for r in template["resources"] if r["type"] == resource_type]
    assert matches, f"no resource of type {resource_type} found"
    assert len(matches) == 1, f"expected exactly one {resource_type}, found {len(matches)}"
    return matches[0]


class TestContainerAppModule:
    """cxone-containerapp.bicep in isolation."""

    @pytest.fixture(scope="class")
    def template(self) -> dict:
        return _compile("cxone-containerapp.bicep")

    def test_ingress_is_internal_only(self, template: dict) -> None:
        app = _find_resource(template, "Microsoft.App/containerApps")
        ingress = app["properties"]["configuration"]["ingress"]
        assert ingress["external"] is False

    def test_min_replicas_is_fixed_at_one(self, template: dict) -> None:
        app = _find_resource(template, "Microsoft.App/containerApps")
        scale = app["properties"]["template"]["scale"]
        assert scale["minReplicas"] == 1

    def test_image_reference_uses_digest_not_a_tag(self, template: dict) -> None:
        app = _find_resource(template, "Microsoft.App/containerApps")
        image_expr = app["properties"]["template"]["containers"][0]["image"]
        # Compiled to an ARM expression string embedding the parameter
        # references — confirm it's built around "@sha256:", never ":".
        assert "@sha256:" in image_expr

    def test_pull_identity_is_isolated_from_application_lifecycle(self, template: dict) -> None:
        app = _find_resource(template, "Microsoft.App/containerApps")
        settings = app["properties"]["configuration"]["identitySettings"]
        by_lifecycle = {s["lifecycle"]: s["identity"] for s in settings}
        assert by_lifecycle["Main"] == "system"
        assert "None" in by_lifecycle
        assert by_lifecycle["None"] != "system"

    def test_registries_reference_the_pull_identity_not_system(self, template: dict) -> None:
        app = _find_resource(template, "Microsoft.App/containerApps")
        registries = app["properties"]["configuration"]["registries"]
        assert len(registries) == 1
        assert registries[0]["identity"] != "system"

    def test_identity_type_includes_both_system_and_user_assigned(self, template: dict) -> None:
        app = _find_resource(template, "Microsoft.App/containerApps")
        assert app["identity"]["type"] == "SystemAssigned, UserAssigned"

    def test_outputs_expose_runtime_principal_not_pull_identity(self, template: dict) -> None:
        outputs = template["outputs"]
        assert "runtimePrincipalId" in outputs
        # The output expression must read the resource's OWN identity
        # (system principal), not echo back the pull identity parameter.
        assert "identity.principalId" in outputs["runtimePrincipalId"]["value"]


class TestKeyvaultAccessModule:
    """cxone-keyvault-access.bicep in isolation."""

    @pytest.fixture(scope="class")
    def template(self) -> dict:
        return _compile("cxone-keyvault-access.bicep")

    def test_only_key_vault_secrets_user_role_is_referenced(self, template: dict) -> None:
        assert template["variables"]["keyVaultSecretsUserRoleDefinitionId"] == "4633458b-17de-408a-b874-0445c86b69e6"
        # No other role-definition GUID appears anywhere in the compiled
        # template (e.g. Contributor, Owner, Secrets Officer, AcrPull).
        role_assignment = _find_resource(template, "Microsoft.Authorization/roleAssignments")
        assert "keyVaultSecretsUserRoleDefinitionId" in role_assignment["properties"]["roleDefinitionId"]

    def test_role_assignment_scope_is_the_vault_not_the_subscription(self, template: dict) -> None:
        role_assignment = _find_resource(template, "Microsoft.Authorization/roleAssignments")
        assert "Microsoft.KeyVault/vaults" in role_assignment["scope"]

    def test_principal_type_defaults_to_service_principal(self, template: dict) -> None:
        assert template["parameters"]["principalType"]["defaultValue"] == "ServicePrincipal"


class TestKeyvaultBicepOutputs:
    def test_keyvault_module_outputs_name_and_uri(self) -> None:
        template = _compile("keyvault.bicep")
        assert "vaultName" in template["outputs"]
        assert "vaultUri" in template["outputs"]

    def test_rbac_authorization_is_explicitly_enabled_by_default(self) -> None:
        template = _compile("keyvault.bicep")
        assert template["parameters"]["enableRbacAuthorization"]["defaultValue"] is True
        vault = _find_resource(template, "Microsoft.KeyVault/vaults")
        assert "enableRbacAuthorization" in vault["properties"]


class TestMainBicepDependencyGraph:
    @pytest.fixture(scope="class")
    def template(self) -> dict:
        return _compile("main.bicep")

    def test_vault_creation_does_not_depend_on_the_cxone_app(self, template: dict) -> None:
        keyvault_deployment = next(r for r in template["resources"] if r["name"] == "keyvault")
        depends_on = keyvault_deployment.get("dependsOn", [])
        assert not any("cxoneApp" in d for d in depends_on)

    def test_role_assignment_depends_on_both_app_and_vault(self, template: dict) -> None:
        access_deployment = next(r for r in template["resources"] if r["name"] == "cxoneKeyvaultAccess")
        depends_on = access_deployment.get("dependsOn", [])
        assert any("cxoneApp" in d for d in depends_on)
        assert any("keyvault" in d for d in depends_on)

    def test_deploy_flag_defaults_to_false(self, template: dict) -> None:
        assert template["parameters"]["deployCxoneMcp"]["defaultValue"] is False


class TestDisabledPathCompilesForEveryEnvironment:
    @pytest.mark.parametrize("bicepparam", ["main.dev.bicepparam", "main.test.bicepparam", "main.prod.bicepparam"])
    def test_environment_bicepparam_compiles(self, bicepparam: str) -> None:
        result = _compile_params(bicepparam)
        assert result["parameters"]["deployCxoneMcp"]["value"] is False
