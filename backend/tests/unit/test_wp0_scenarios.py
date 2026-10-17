"""Phase 3 demo scenarios: verdicts and validation without mutating the freeze baseline."""

from __future__ import annotations

from rp_scenarios import (
    ScenarioKind,
    build_assessment_by_id,
    build_scenario_compatible,
    build_scenario_conditional,
    build_scenario_indeterminate,
    list_scenario_descriptors,
)

from releaseproof.core.assurance.service import evaluate
from releaseproof.core.domain.enums import AssessmentLifecycle, RequirementResultState, Verdict
from releaseproof.core.golden.baseline import verify_baseline_golden
from releaseproof.core.projection.wp0 import (
    build_a4_signer_bound_assessment,
    build_wp0_baseline_assessment,
)
from releaseproof.core.validation.service import validate_assessment


def test_freeze_baseline_unchanged() -> None:
    ok, err = verify_baseline_golden()
    assert ok, err
    result = evaluate(build_wp0_baseline_assessment())
    assert result.migration_verdict == Verdict.INCOMPATIBLE
    assert result.transition_verdict == Verdict.INCOMPATIBLE
    assert result.candidate_verdict == Verdict.INDETERMINATE


def test_scenario_indeterminate_firmware_only() -> None:
    assessment = build_scenario_indeterminate()
    validation = validate_assessment(assessment)
    assert validation.ready
    result = evaluate(assessment)
    assert result.lifecycle == AssessmentLifecycle.COMPLETED
    assert result.migration_verdict == Verdict.INDETERMINATE
    assert result.transition_verdict == Verdict.INDETERMINATE
    assert result.candidate_verdict == Verdict.INDETERMINATE
    boot = [
        r for r in result.requirement_evaluation_results if r["requirement_id"] == "REQ-BOOT-S0S1"
    ]
    assert not boot


def test_scenario_conditional_maintenance_open() -> None:
    assessment = build_scenario_conditional()
    assert validate_assessment(assessment).ready
    result = evaluate(assessment)
    assert result.transition_verdict == Verdict.CONDITIONAL
    assert result.candidate_verdict == Verdict.COMPATIBLE
    assert result.migration_verdict == Verdict.CONDITIONAL
    open_req = [
        r
        for r in result.requirement_evaluation_results
        if r["requirement_id"] == "REQ-MAINTENANCE-WINDOW"
        and r["state"] == RequirementResultState.OPEN_CONDITION
    ]
    assert open_req
    auth = [
        r
        for r in result.requirement_evaluation_results
        if r["requirement_id"] == "REQ-AUTH-NEGATIVE"
    ]
    assert auth and all(r["state"] == RequirementResultState.SATISFIED for r in auth)
    assert all(r["evidence_refs"] == ["EV-E03-PANIC"] for r in auth)
    assert not any(item["id"] == "EV-HAZARD-MAINTENANCE" for item in assessment["evidence"])


def test_scenario_compatible_declared_perimeter() -> None:
    assessment = build_scenario_compatible()
    assert validate_assessment(assessment).ready
    result = evaluate(assessment)
    assert result.migration_verdict == Verdict.COMPATIBLE
    assert result.transition_verdict == Verdict.COMPATIBLE
    assert result.candidate_verdict == Verdict.COMPATIBLE
    for inv_id in ("INV-I2", "INV-I3", "INV-I4"):
        transition = [
            i
            for i in result.invariant_evaluation_results
            if i["invariant_id"] == inv_id and i["phase"] == "TRANSITION"
        ]
        assert transition and transition[0]["state"] == RequirementResultState.SATISFIED


def test_a4_signer_bound_incompatible() -> None:
    result = evaluate(build_a4_signer_bound_assessment())
    assert result.migration_verdict == Verdict.INCOMPATIBLE
    assert result.candidate_verdict == Verdict.INCOMPATIBLE


def test_scenario_catalog_and_build_by_id() -> None:
    ids = {item.assessment_id for item in list_scenario_descriptors()}
    assert "WP0-FREEZE-20261001" in ids
    assert "SCENARIO-INDETERMINATE-20261001" in ids
    real = [d for d in list_scenario_descriptors() if d.kind == ScenarioKind.REAL_ASSESSMENT]
    assert len(real) == 1
    built = build_assessment_by_id("SCENARIO-COMPATIBLE-20261001")
    assert built["assessment_id"] == "SCENARIO-COMPATIBLE-20261001"
