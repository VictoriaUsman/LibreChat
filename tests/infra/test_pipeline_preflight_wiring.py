"""
Confirms the CxoneMcpPreflight stage is actually wired into each
environment's pipeline, and runs BEFORE the what-if/create stages —
addressing the review finding that enabling deployCxoneMcp bypassed
scripts/preflight_cxone_mcp.py entirely because nothing in the pipeline
ever called it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PIPELINES_DIR = Path(__file__).resolve().parents[2] / "ROMTechMCP.pipelines"


@pytest.mark.parametrize("pipeline_file", ["dev.yml", "test.yml", "prod.yml"])
def test_preflight_stage_runs_before_whatif_and_create(pipeline_file: str) -> None:
    text = (PIPELINES_DIR / pipeline_file).read_text(encoding="utf-8")
    preflight_pos = text.index("stage: CxoneMcpPreflight")
    whatif_pos = text.index("insert-stage-bicep-whatif.yml@templates")
    create_pos = text.index("insert-stage-bicep-create.yml@templates")
    assert preflight_pos < whatif_pos < create_pos


@pytest.mark.parametrize("pipeline_file", ["dev.yml", "test.yml", "prod.yml"])
def test_preflight_step_invokes_the_bicepparam_wrapper_with_this_environments_file(pipeline_file: str) -> None:
    text = (PIPELINES_DIR / pipeline_file).read_text(encoding="utf-8")
    assert "scripts/preflight_from_bicepparam.py" in text
    # Uses the SAME variables the whatif/create stages below it are
    # already called with — not a hand-typed, potentially-drifted path.
    assert "--bicepparam-file $(bicepWorkingDirectory)/$(bicepParamFile)" in text
