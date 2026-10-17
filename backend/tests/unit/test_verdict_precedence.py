"""Verdict precedence and WP0 projection integration tests."""

from __future__ import annotations

from releaseproof.core.assurance.service import evaluate
from releaseproof.core.domain.enums import AssessmentLifecycle, RequirementResultState, Verdict
from releaseproof.core.projection.wp0 import (
    build_a4_oversized_assessment,
    build_a4_signer_bound_assessment,
    build_wp0_baseline_assessment,
)
from releaseproof.core.validation.service import validate_assessment
from tests.unit.test_sv_conformance import _load_base, _satisfy_supporting_requirements


def test_violation_beats_unknown_on_migration() -> None:
    data = _load_base()
    _satisfy_supporting_requirements(data)
    data["observed_recovery_mode"] = "UNKNOWN"
    data["allowed_change_set"]["modifiable_components"] = ["firmware"]
    evaluated = evaluate(data)
    assert evaluated.lifecycle == AssessmentLifecycle.COMPLETED
    assert evaluated.migration_verdict == Verdict.INCOMPATIBLE
    unknowns = [
        item
        for item in evaluated.invariant_evaluation_results
        if item["critical_for_verdict"] and item["state"] == RequirementResultState.UNKNOWN
    ]
    assert unknowns


def test_target_invariant_unknown_affects_candidate_verdict() -> None:
    data = _load_base()
    _satisfy_supporting_requirements(data)
    data["candidate_state"]["authorization_path_states"]["fw-boot"]["policy"] = "UNKNOWN"
    evaluated = evaluate(data)
    assert evaluated.candidate_verdict == Verdict.INDETERMINATE


def test_wp0_baseline_projection_ready() -> None:
    assessment = build_wp0_baseline_assessment()
    validation = validate_assessment(assessment)
    assert validation.ready is True


def test_wp0_baseline_verdicts() -> None:
    assessment = build_wp0_baseline_assessment()
    evaluated = evaluate(assessment)
    assert evaluated.lifecycle == AssessmentLifecycle.COMPLETED
    assert evaluated.candidate_verdict == Verdict.INDETERMINATE
    assert evaluated.transition_verdict == Verdict.INCOMPATIBLE
    assert evaluated.migration_verdict == Verdict.INCOMPATIBLE
    boot_req = [
        item
        for item in evaluated.requirement_evaluation_results
        if item["requirement_id"] == "REQ-BOOT-S0S1"
    ]
    assert boot_req
    assert all(item["state"] == RequirementResultState.VIOLATED for item in boot_req)
    assert {item["phase"] for item in boot_req} == {"TRANSITION"}
    assert "EV-A4-SIGNER-BOUND" not in {item["id"] for item in assessment["evidence"]}
    by_id = {item["invariant_id"]: item["state"] for item in evaluated.invariant_evaluation_results}
    assert by_id["INV-I1"] == RequirementResultState.SATISFIED
    assert by_id["INV-I2"] == RequirementResultState.UNKNOWN
    assert by_id["INV-I3"] == RequirementResultState.UNKNOWN
    assert by_id["INV-I4"] == RequirementResultState.UNKNOWN
    layout = [
        item
        for item in evaluated.requirement_evaluation_results
        if item["requirement_id"] == "REQ-LAYOUT" and item["phase"] == "TARGET"
    ]
    assert layout
    assert all(item["state"] == RequirementResultState.SATISFIED for item in layout)


def test_wp0_missing_bootloader_action_blocked() -> None:
    assessment = build_wp0_baseline_assessment()
    assessment["transition_plan"]["steps"][0]["actions"] = []
    result = validate_assessment(assessment)
    assert result.lifecycle == AssessmentLifecycle.BLOCKED


def test_a4_without_artifact_measurement_is_refused() -> None:
    try:
        build_a4_oversized_assessment()
    except ValueError as exc:
        assert "artifact" in str(exc)
    else:
        raise AssertionError("synthetic A4 size must not be loaded from the freeze")


def test_leq_unit_fixture_oversized_is_incompatible() -> None:
    """In-memory size. Not a freeze fact and not a signed artifact."""
    evaluated = evaluate(
        build_a4_oversized_assessment(
            measurement={
                "signed_image_size_bytes": 262401,
                "run_id": "unit-leq",
                "artifact_name": "unit-oversized.bin",
            }
        )
    )
    assert evaluated.lifecycle == AssessmentLifecycle.COMPLETED
    assert evaluated.candidate_verdict == Verdict.INCOMPATIBLE
    layout = [
        item
        for item in evaluated.requirement_evaluation_results
        if item["requirement_id"] == "REQ-LAYOUT" and item["phase"] == "TARGET"
    ]
    assert layout
    assert all(item["state"] == RequirementResultState.VIOLATED for item in layout)


def test_signer_refusal_is_separate_incompatible_assessment() -> None:
    """Signer operands only. The booting candidate image stays on the baseline."""
    baseline = evaluate(build_wp0_baseline_assessment())
    signer_assessment = build_a4_signer_bound_assessment()
    bound_evidence = next(
        item for item in signer_assessment["evidence"] if item["id"] == "EV-A4-SIGNER-BOUND"
    )
    assert "signed_artifact_size" not in bound_evidence["value"]
    assert bound_evidence["value"]["signing_result"] == "REJECTED"
    evaluated = evaluate(signer_assessment)
    assert baseline.candidate_verdict == Verdict.INDETERMINATE
    assert evaluated.lifecycle == AssessmentLifecycle.COMPLETED
    assert evaluated.candidate_verdict == Verdict.INCOMPATIBLE
    assert evaluated.transition_verdict == Verdict.INCOMPATIBLE
    bound = [
        item
        for item in evaluated.requirement_evaluation_results
        if item["requirement_id"] == "REQ-SIGN-BOUND"
    ]
    assert bound
    assert {item["phase"] for item in bound} == {"TARGET"}
    assert all(item["state"] == RequirementResultState.VIOLATED for item in bound)
    layout = [
        item
        for item in evaluated.requirement_evaluation_results
        if item["requirement_id"] == "REQ-LAYOUT" and item["phase"] == "TARGET"
    ]
    assert all(item["state"] == RequirementResultState.SATISFIED for item in layout)
