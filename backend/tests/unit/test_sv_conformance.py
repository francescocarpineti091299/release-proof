"""Conformance tests for semantic validation cases SV01–SV15."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema

from releaseproof.core.assurance.service import evaluate
from releaseproof.core.canonical.service import compute_canonical_hash
from releaseproof.core.domain.enums import AssessmentLifecycle, RequirementResultState, Verdict
from releaseproof.core.validation.service import validate_assessment

ROOT = Path(__file__).resolve().parents[3] / "contract"
EXAMPLES = ROOT / "PQC_Engineering_Pack_V1_2" / "examples"


def _load_base() -> dict[str, Any]:
    return json.loads((EXAMPLES / "minimal_valid_assessment_v1_2.json").read_text(encoding="utf-8"))


def _declaration(evidence_id: str) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "evidence_kind": "DECLARATION",
        "source_role": "SYSTEM_OWNER",
        "authority_context": "SIMULATED",
        "acquisition_mode": "DOCUMENTARY",
        "review_status": "CONFIRMED",
        "status": "VALID",
        "source_identity": "Owner",
    }


def _catalog_fact(evidence_id: str, test_id: str, value: str) -> dict[str, Any]:
    """Fact used only by the invariant catalog, not by requirement evidence groups."""
    return {
        "id": evidence_id,
        "evidence_kind": "MEASUREMENT",
        "source_role": "TOOL",
        "authority_context": "SIMULATED",
        "acquisition_mode": "CATALOG_FACT",
        "review_status": "AUTOMATIC",
        "status": "VALID",
        "value": value,
        "test_id": test_id,
        "run_id": "RUN-1",
        "artifact_refs": ["ART-1"],
    }


def _measurement(
    evidence_id: str,
    *,
    acquisition_mode: str,
    value: str,
) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "evidence_kind": "MEASUREMENT",
        "source_role": "TOOL",
        "authority_context": "SIMULATED",
        "acquisition_mode": acquisition_mode,
        "review_status": "AUTOMATIC",
        "status": "VALID",
        "value": value,
        "test_id": "E05",
        "run_id": "RUN-1",
        "artifact_refs": ["ART-1"],
    }


def _cover_trust(data: dict[str, Any]) -> None:
    data["coverage_assertions"] = [
        {
            "assertion_id": "CA-1",
            "claimed_items": ["fw-boot"],
            "subject": "auth",
            "scope": "demo",
            "source_role": "SYSTEM_OWNER",
            "authority_context": "SIMULATED",
            "source_ref": "DECL-1",
            "timestamp": "2026-09-30T12:00:00Z",
            "review_status": "CONFIRMED",
            "content_hash": "sha256:decl",
        }
    ]


def _satisfy_supporting_requirements(data: dict[str, Any]) -> None:
    """Satisfy trust, layout and power so one mutation stays isolated."""
    _cover_trust(data)
    data["observed_recovery_mode"] = "FIELD_SERVICE"
    data["evidence"] = [
        _declaration("EV-TRUST"),
        _measurement("EV-LAYOUT", acquisition_mode="STATIC_ANALYSIS", value="PASS"),
        _measurement("EV-HAZARD", acquisition_mode="EMULATED", value="FAIL"),
        _declaration("EV-POWER"),
        _catalog_fact("EV-BOOT", "E02", "BOOT_OK"),
        _catalog_fact("EV-WINDOW", "E12", "PASS"),
    ]


def test_ruleset_requires_i1_through_i4() -> None:
    pack = ROOT / "PQC_Engineering_Pack_V1_2"
    ruleset = json.loads((pack / "examples" / "ruleset_v1_2.json").read_text(encoding="utf-8"))
    schema = json.loads((pack / "schemas" / "ruleset_v1_2.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(ruleset)
    assert ruleset["required_invariants"] == ["INV-I1", "INV-I2", "INV-I3", "INV-I4"]


def test_minimal_fixture_is_ready() -> None:
    result = validate_assessment(_load_base())
    assert result.ready is True
    assert result.lifecycle == AssessmentLifecycle.READY


def test_sv01_final_state_mismatch_blocked() -> None:
    data = _load_base()
    data["candidate_state"]["snapshot_hash"] = "sha256:wrong"
    result = validate_assessment(data)
    assert result.lifecycle == AssessmentLifecycle.BLOCKED
    assert result.errors


def test_sv02_orphan_component_blocked() -> None:
    data = _load_base()
    data["transition_plan"]["steps"][0]["actions"][0]["component_ref"] = "missing"
    result = validate_assessment(data)
    assert result.lifecycle == AssessmentLifecycle.BLOCKED


def test_sv03_outside_change_set_incompatible() -> None:
    data = _load_base()
    _satisfy_supporting_requirements(data)
    data["allowed_change_set"]["modifiable_components"] = ["firmware"]
    evaluated = evaluate(data)
    assert evaluated.lifecycle == AssessmentLifecycle.COMPLETED
    assert evaluated.migration_verdict == Verdict.INCOMPATIBLE
    assert evaluated.explanation_graph["nodes"]


def test_sv04_unknown_gap_produces_indeterminate() -> None:
    data = _load_base()
    _satisfy_supporting_requirements(data)
    data["evidence"] = [item for item in data["evidence"] if item["evidence_kind"] != "DECLARATION"]
    data["evidence_gaps"] = [
        {
            "gap_id": "GAP-TRUST",
            "requirement_id": "REQ-TRUST",
            "gap_type": "UNKNOWN_FACT",
            "reason": "Manca il fatto di copertura",
            "critical": True,
            "requested_evidence": "CoverageAssertion del titolare",
        }
    ]
    evaluated = evaluate(data)
    trust = [
        item
        for item in evaluated.requirement_evaluation_results
        if item["requirement_id"] == "REQ-TRUST" and item["phase"] == "TARGET"
    ]
    assert trust
    assert trust[0]["state"] == RequirementResultState.UNKNOWN
    assert "GAP-TRUST" in trust[0]["gap_refs"]
    assert evaluated.lifecycle == AssessmentLifecycle.COMPLETED
    assert evaluated.migration_verdict == Verdict.INDETERMINATE


def test_sv05_disallowed_precondition_is_incompatible() -> None:
    data = _load_base()
    _satisfy_supporting_requirements(data)
    data["profile"]["allowed_operational_preconditions"] = []
    data["evidence"] = [item for item in data["evidence"] if item["evidence_kind"] != "DECLARATION"]
    evaluated = evaluate(data)
    power = [
        item
        for item in evaluated.requirement_evaluation_results
        if item["requirement_id"] == "REQ-POWER"
    ]
    assert power
    assert all(item["state"] == RequirementResultState.VIOLATED for item in power)
    assert evaluated.lifecycle == AssessmentLifecycle.COMPLETED
    assert evaluated.migration_verdict == Verdict.INCOMPATIBLE


def test_sv06_target_unknown_blocks_candidate_compatible() -> None:
    data = _load_base()
    _satisfy_supporting_requirements(data)
    data["evidence"] = [item for item in data["evidence"] if item["evidence_kind"] != "DECLARATION"]
    data["evidence_gaps"] = [
        {
            "gap_id": "GAP-TRUST",
            "requirement_id": "REQ-TRUST",
            "reason": "Fatto target sconosciuto",
            "requested_evidence": "Dichiarazione di copertura",
        }
    ]
    evaluated = evaluate(data)
    assert evaluated.candidate_verdict == Verdict.INDETERMINATE
    assert evaluated.candidate_verdict != Verdict.COMPATIBLE


def test_sv07_coverage_unknown_surface_blocked() -> None:
    data = _load_base()
    data["coverage_assertions"] = [
        {
            "assertion_id": "CA-1",
            "claimed_items": ["not-a-surface"],
            "subject": "x",
            "scope": "x",
            "source_role": "SYSTEM_OWNER",
            "authority_context": "SIMULATED",
            "source_ref": "r",
            "timestamp": "2026-09-30T12:00:00Z",
            "review_status": "CONFIRMED",
            "content_hash": "sha256:x",
        }
    ]
    result = validate_assessment(data)
    assert result.lifecycle == AssessmentLifecycle.BLOCKED


def test_sv08_unexplained_delta_blocked() -> None:
    data = _load_base()
    data["transition_plan"]["steps"][0]["actions"][0]["derived_effect_refs"] = []
    result = validate_assessment(data)
    assert result.lifecycle == AssessmentLifecycle.BLOCKED


def test_sv09_spoofed_allowed_by_profile_blocked() -> None:
    data = _load_base()
    data["transition_plan"]["steps"][0]["preconditions"][0]["allowed_by_profile"] = False
    result = validate_assessment(data)
    assert result.lifecycle == AssessmentLifecycle.BLOCKED


def test_sv10_missing_invariant_result_incomplete() -> None:
    data = _load_base()
    data["invariants"] = []
    evaluated = evaluate(data)
    assert evaluated.lifecycle == AssessmentLifecycle.INCOMPLETE
    assert evaluated.migration_verdict is None
    assert any("INV-I1" in error for error in evaluated.errors)


def test_omitted_i3_is_still_evaluated() -> None:
    data = _load_base()
    data["invariants"] = []
    _satisfy_supporting_requirements(data)
    evaluated = evaluate(data)
    ids = {item["invariant_id"] for item in evaluated.invariant_evaluation_results}
    assert {"INV-I1", "INV-I2", "INV-I3", "INV-I4"} <= ids
    assert evaluated.lifecycle == AssessmentLifecycle.COMPLETED


def test_sv11_closure_without_hazard_is_not_satisfied() -> None:
    data = _load_base()
    _satisfy_supporting_requirements(data)
    data["evidence"] = [item for item in data["evidence"] if item["id"] != "EV-HAZARD"]
    evaluated = evaluate(data)
    power = [
        item
        for item in evaluated.requirement_evaluation_results
        if item["requirement_id"] == "REQ-POWER"
    ]
    assert power
    assert all(item["state"] != RequirementResultState.SATISFIED for item in power)
    assert evaluated.lifecycle == AssessmentLifecycle.COMPLETED
    assert evaluated.transition_verdict == Verdict.CONDITIONAL


def test_sv12_canonical_hash_key_order() -> None:
    left = compute_canonical_hash({"b": 2, "a": 1})
    right = compute_canonical_hash({"a": 1, "b": 2})
    assert left == right


def test_sv13_step_scope_is_not_aggregated_as_state() -> None:
    data = _load_base()
    _satisfy_supporting_requirements(data)
    data["profile"]["requirements"].append(
        {
            "id": "REQ-STEP",
            "risk_category": "UPDATE_ROLLBACK_RECOVERY",
            "applicable_phase": ["TRANSITION"],
            "applicable_subject_types": ["TRANSITION_STEP"],
            "critical_for_verdict": True,
            "criterion": "Step only",
            "scope_status": "IN_SCOPE",
            "rule_refs": ["RULE-STEP"],
            "acceptable_evidence_policy": {
                "required_evidence_groups": [
                    {
                        "role": "PRIMARY",
                        "min_satisfied": 1,
                        "accepted_combinations": [
                            {
                                "evidence_kind": ["DECLARATION"],
                                "source_role": ["OEM"],
                                "authority_context": ["SIMULATED"],
                                "acquisition_mode": ["DOCUMENTARY"],
                                "review_status": ["CONFIRMED"],
                            }
                        ],
                    }
                ]
            },
        }
    )
    data["evidence_gaps"] = [
        {
            "gap_id": "GAP-STEP",
            "requirement_id": "REQ-STEP",
            "reason": "Il passo non è valutato come stato",
            "requested_evidence": "Evidence del passo",
        }
    ]
    evaluated = evaluate(data)
    step_results = [
        item
        for item in evaluated.requirement_evaluation_results
        if item["requirement_id"] == "REQ-STEP"
    ]
    assert step_results
    assert all(item["subject_type"] == "TRANSITION_STEP" for item in step_results)
    assert evaluated.transition_verdict == Verdict.INDETERMINATE
    layout_states = [
        item
        for item in evaluated.requirement_evaluation_results
        if item["requirement_id"] == "REQ-LAYOUT" and item["subject_type"] == "STATE"
    ]
    assert layout_states
    assert all(item["state"] == RequirementResultState.SATISFIED for item in layout_states)


def test_sv14_recovery_violation_incompatible() -> None:
    data = _load_base()
    _satisfy_supporting_requirements(data)
    data["observed_recovery_mode"] = "DEPOT_PHYSICAL_REFLASH"
    evaluated = evaluate(data)
    assert evaluated.lifecycle == AssessmentLifecycle.COMPLETED
    assert evaluated.migration_verdict == Verdict.INCOMPATIBLE


def test_sv15_declaration_path_has_source_and_no_test() -> None:
    data = copy.deepcopy(_load_base())
    _cover_trust(data)
    data["invariants"] = []
    data["observed_recovery_mode"] = "FIELD_SERVICE"
    data["profile"]["requirements"] = [data["profile"]["requirements"][0]]
    data["evidence"] = [
        _declaration("EV-DECL"),
        _catalog_fact("EV-BOOT", "E02", "BOOT_OK"),
        _catalog_fact("EV-WINDOW", "E12", "PASS"),
    ]
    evaluated = evaluate(data)
    assert evaluated.lifecycle == AssessmentLifecycle.COMPLETED
    assert evaluated.migration_verdict == Verdict.COMPATIBLE
    kinds = {node.get("type") for node in evaluated.explanation_graph.get("nodes", [])}
    assert "SOURCE" in kinds
    assert "RULE" in kinds
    assert "TEST" not in kinds


def test_none_recovery_is_incompatible() -> None:
    data = _load_base()
    _satisfy_supporting_requirements(data)
    data["observed_recovery_mode"] = "NONE"
    evaluated = evaluate(data)
    assert evaluated.migration_verdict == Verdict.INCOMPATIBLE


def test_noncritical_violation_stays_a_finding() -> None:
    data = _load_base()
    _satisfy_supporting_requirements(data)
    data["profile"]["requirements"][2]["critical_for_verdict"] = False
    for item in data["evidence"]:
        if item["id"] == "EV-LAYOUT":
            item["value"] = "FAIL"
    evaluated = evaluate(data)
    layout = [
        item
        for item in evaluated.requirement_evaluation_results
        if item["requirement_id"] == "REQ-LAYOUT"
    ]
    assert layout
    assert all(item["state"] == RequirementResultState.VIOLATED for item in layout)
    assert evaluated.findings
    assert evaluated.migration_verdict != Verdict.INCOMPATIBLE
