"""Fail-closed validation, evidence handling and reproducible result identities."""

from __future__ import annotations

import copy

import pytest

from releaseproof.core.assurance.service import evaluate
from releaseproof.core.canonical.service import compute_canonical_hash
from releaseproof.core.domain.enums import AssessmentLifecycle, RequirementResultState
from releaseproof.core.domain.schemas import SemanticAssessmentResult
from releaseproof.core.evidence.trust_chain import trust_chain_from_evidence
from releaseproof.core.projection.wp0 import (
    build_a4_oversized_assessment,
    build_wp0_baseline_assessment,
)
from releaseproof.core.rules.service import run_evaluator
from releaseproof.core.validation import service as validation_service


def _requirement(result, identifier):
    return next(
        row for row in result.requirement_evaluation_results if row["requirement_id"] == identifier
    )


def _invariant(result, identifier):
    return next(
        row for row in result.invariant_evaluation_results if row["invariant_id"] == identifier
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("platform_model", []),
        ("profile", "not an object"),
        ("transition_plan", {"states": [None], "steps": "not an array"}),
        ("evidence", [{"evidence_kind": "MEASUREMENT"}]),
        ("derived_effects", [{}]),
    ],
)
def test_schema_errors_block_without_cross_object_or_emission_crashes(field, value):
    assessment = build_wp0_baseline_assessment()
    assessment[field] = value
    result = evaluate(assessment)
    assert result.lifecycle == AssessmentLifecycle.BLOCKED
    assert result.errors
    assert result.migration_verdict is None
    assert compute_canonical_hash(result.model_dump(mode="json")) == result.canonical_hash


def test_missing_contract_schema_is_not_silently_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(validation_service, "_SCHEMA_PATH", tmp_path / "missing.json")
    result = validation_service.validate_assessment(build_wp0_baseline_assessment())
    assert not result.ready
    assert "Schema" in result.errors[0]


@pytest.mark.parametrize("endpoint", ["from", "to"])
def test_orphan_plan_endpoint_blocks(endpoint):
    assessment = build_wp0_baseline_assessment()
    assessment["transition_plan"]["steps"][0][endpoint] = "missing"
    result = evaluate(assessment)
    assert result.lifecycle == AssessmentLifecycle.BLOCKED
    assert any("state_id inesistente" in error for error in result.errors)


@pytest.mark.parametrize("field", ["evidence", "derived_effects", "evidence_gaps"])
def test_duplicate_index_identifiers_block_instead_of_shadowing(field):
    assessment = build_wp0_baseline_assessment()
    assessment[field].append(copy.deepcopy(assessment[field][0]))
    result = evaluate(assessment)
    assert result.lifecycle == AssessmentLifecycle.BLOCKED
    assert any("duplicato" in error for error in result.errors)


def test_matching_snapshot_pin_does_not_allow_different_final_state_id():
    assessment = build_wp0_baseline_assessment()
    assessment["candidate_state"]["state_id"] = "different"
    assert not validation_service.validate_assessment(assessment).ready


@pytest.mark.parametrize("location", ["candidate_state", "deployed_state"])
def test_unknown_authorization_path_in_top_level_state_blocks(location):
    assessment = build_wp0_baseline_assessment()
    assessment[location]["authorization_path_states"]["missing"] = {
        "policy": "PQC_ONLY",
        "accepted_schemes": ["ML_DSA_87"],
    }
    assert not validation_service.validate_assessment(assessment).ready


def test_effect_for_one_path_does_not_explain_another_path_delta():
    assessment = build_wp0_baseline_assessment()
    assessment["platform_model"]["declared_surface_ids"].append("second-path")
    assessment["transition_plan"]["states"][1]["authorization_path_states"]["second-path"] = {
        "policy": "PQC_ONLY",
        "accepted_schemes": ["ML_DSA_87"],
    }
    result = validation_service.validate_assessment(assessment)
    assert not result.ready
    assert any("authorization_path:second-path" in error for error in result.errors)


def test_disallowed_action_on_modifiable_component_is_a_constraint_violation():
    assessment = build_wp0_baseline_assessment()
    assessment["allowed_change_set"]["allowed_actions"] = ["UPDATE_FIRMWARE"]
    result = evaluate(assessment)
    assert result.lifecycle == AssessmentLifecycle.COMPLETED
    assert _requirement(result, "REQ-CHANGE-SET")["state"] == RequirementResultState.VIOLATED


def test_a4_projection_updates_the_renamed_state_references():
    assessment = build_a4_oversized_assessment(measurement={"signed_image_size_bytes": 999999})
    assert assessment["transition_plan"]["steps"][-1]["to"] == "S2-A4"
    assert validation_service.validate_assessment(assessment).ready
    assert (
        _requirement(evaluate(assessment), "REQ-LAYOUT")["state"] == RequirementResultState.VIOLATED
    )


@pytest.mark.parametrize("status", ["INVALID", "REVOKED", None])
def test_invalid_evidence_cannot_satisfy_auth_negative(status):
    assessment = build_wp0_baseline_assessment()
    for item in assessment["evidence"]:
        if item.get("test_id") == "E03":
            if status is None:
                item.pop("status", None)
            else:
                item["status"] = status
    result = evaluate(assessment)
    assert _requirement(result, "REQ-AUTH-NEGATIVE")["state"] == RequirementResultState.UNKNOWN


def test_invalid_boot_evidence_cannot_finalize_i1():
    assessment = build_wp0_baseline_assessment()
    for item in assessment["evidence"]:
        if item.get("test_id") in {"E01", "E02"}:
            item["status"] = "INVALID"
    result = evaluate(assessment)
    assert result.lifecycle == AssessmentLifecycle.INCOMPLETE
    assert any("INV-I1" in error for error in result.errors)


@pytest.mark.parametrize("reverse", [False, True])
def test_contradictory_e12_evidence_is_not_first_row_wins(reverse):
    assessment = build_wp0_baseline_assessment()
    original = next(item for item in assessment["evidence"] if item.get("test_id") == "E12")
    original["value"] = "PASS"
    contrary = {**original, "id": "EV-E12-FAIL", "value": "FAIL"}
    assessment["evidence"].append(contrary)
    if reverse:
        assessment["evidence"].reverse()
    result = evaluate(assessment)
    assert _invariant(result, "INV-I4")["state"] == RequirementResultState.VIOLATED


def test_structured_e12_fact_does_not_crash_the_invariant_evaluator():
    assessment = build_wp0_baseline_assessment()
    next(item for item in assessment["evidence"] if item.get("test_id") == "E12")["value"] = {
        "result": "PASS"
    }
    result = evaluate(assessment)
    assert result.lifecycle == AssessmentLifecycle.INCOMPLETE


@pytest.mark.parametrize("reverse", [False, True])
def test_all_authorization_paths_are_checked_regardless_of_map_order(reverse):
    assessment = build_wp0_baseline_assessment()
    assessment["platform_model"]["authorization_paths"].append({"path_id": "second-path"})
    paths = {
        "fw-boot": {"policy": "PQC_ONLY", "accepted_schemes": ["ML_DSA_87"]},
        "second-path": {"policy": "CLASSICAL_ONLY", "accepted_schemes": ["ECDSA_P256"]},
    }
    if reverse:
        paths = dict(reversed(list(paths.items())))
    assessment["candidate_state"]["authorization_path_states"] = paths
    result = evaluate(assessment)
    assert _invariant(result, "INV-I3")["state"] == RequirementResultState.VIOLATED


def test_missing_declared_authorization_path_stays_unknown():
    assessment = build_wp0_baseline_assessment()
    assessment["platform_model"]["authorization_paths"].append({"path_id": "second-path"})
    assessment["candidate_state"]["authorization_path_states"]["fw-boot"]["policy"] = "PQC_ONLY"
    assert _invariant(evaluate(assessment), "INV-I3")["state"] == RequirementResultState.UNKNOWN


@pytest.mark.parametrize("size", ["not-a-number", {}, True, -1, 0.5])
def test_malformed_layout_operands_stay_unknown_without_coercion_or_crashes(size):
    assessment = build_wp0_baseline_assessment()
    next(item for item in assessment["evidence"] if item["id"] == "EV-E05-LAYOUT-G2")["value"] = {
        "signed_artifact_size": size
    }
    result = evaluate(assessment)
    assert _requirement(result, "REQ-LAYOUT")["state"] == RequirementResultState.UNKNOWN


@pytest.mark.parametrize("operand", ["123", True, -1, float("nan"), float("inf"), {}, []])
def test_leq_rejects_invalid_capacity_operands(operand):
    result = run_evaluator(
        "LEQ", context={"signed_artifact_size": operand, "boot_slot_capacity": 200}
    )
    assert result["status"] == "UNKNOWN"


def test_missing_trust_chain_evidence_does_not_assert_zero_size_fits_zero_capacity():
    chain = trust_chain_from_evidence([])
    image = next(node for node in chain["nodes"] if node["node_id"] == "signed_image")
    assert image["status"] == "UNKNOWN"
    assert image["evidence_ids"] == []
    assert image["detail"]["signed_image_size_bytes"] is None


def test_unrelated_static_artifact_does_not_replace_missing_layout_measurements():
    assessment = build_wp0_baseline_assessment()
    assessment["evidence"] = [
        item for item in assessment["evidence"] if item.get("test_id") != "E05"
    ]
    result = evaluate(assessment)
    assert _requirement(result, "REQ-LAYOUT")["state"] == RequirementResultState.UNKNOWN


def test_scenario_named_evidence_does_not_magically_close_recovery_gaps():
    chain = trust_chain_from_evidence(
        [{"id": "EV-SCENARIO-RECOVERY", "status": "VALID", "evidence_kind": "DECLARATION"}]
    )
    recovery = next(node for node in chain["nodes"] if node["node_id"] == "recovery")
    assert recovery["status"] == "GAP"
    assert recovery["gap_ids"]


def test_serialized_result_is_the_document_covered_by_its_canonical_hash():
    result = evaluate(build_wp0_baseline_assessment())
    document = result.model_dump(mode="json")
    assert document["candidate_state_assurance"] == {"verdict": result.candidate_verdict.value}
    assert compute_canonical_hash(document) == result.canonical_hash
    assert SemanticAssessmentResult.model_validate(document) == result
    document["candidate_state_assurance"]["verdict"] = "COMPATIBLE"
    assert compute_canonical_hash(document) != result.canonical_hash
