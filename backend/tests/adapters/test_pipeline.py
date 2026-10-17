"""The orchestrator chain (adapter → evaluate → gap plan → dossier → evidence index) runs."""

from __future__ import annotations

import pytest
from adapter_facts import CREATED_AT, RUN_ID, mcuboot_run, wolfboot_run

from releaseproof.adapters import evidence_index, get_adapter
from releaseproof.core.assurance.service import evaluate
from releaseproof.core.dossier.service import render_dossier_markdown
from releaseproof.core.planner.service import build_gap_plan
from releaseproof.profiles.registry import get_profile

CASES = [
    ("nrf52840-wolfboot-pqc", "bootloader_self_update", wolfboot_run),
    ("nrf52840-wolfboot-pqc", "field_service_reflash", wolfboot_run),
    ("nrf52840-wolfboot-pqc", "staged_hybrid_dual_signature", wolfboot_run),
    ("nrf52840-mcuboot-pqc", "mcuboot_field_update", mcuboot_run),
    ("nrf52840-mcuboot-pqc", "depot_reflash_mcuboot", mcuboot_run),
]


@pytest.mark.parametrize(("profile_id", "plan_id", "factory"), CASES)
def test_pipeline(profile_id, plan_id, factory):
    profile = get_profile(profile_id)
    run = factory()
    assessment = get_adapter(profile.assessment_adapter)(
        profile=profile,
        change=profile.changes[0],
        plan_id=plan_id,
        run_id=RUN_ID,
        evidence_run_id=RUN_ID,
        created_at=CREATED_AT,
        **run.kwargs(),
    )
    result = evaluate(assessment).model_dump(mode="json")
    assert result["lifecycle"] == "COMPLETED"
    plan = build_gap_plan(assessment, result)
    assert any(item["source_id"] == "GAP-E12-NON-ATOMIC" for item in plan)
    dossier = render_dossier_markdown(assessment, result, gap_plan=plan)
    assert result["assessment_id"] in dossier
    rows = evidence_index(assessment, run.observations, run.artifacts)
    assert len(rows) == len(assessment["evidence"])
