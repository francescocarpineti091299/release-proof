"""Synthetic assessment fixtures for engine tests (never part of the runtime package).

Derived from the WP0 freeze without mutating the recorded baseline. Policy, recovery and E12
closure evidence in these scenarios is simulated, not measured by a runner.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from releaseproof.core.projection.wp0 import (
    build_a4_signer_bound_assessment,
    build_wp0_baseline_assessment,
    load_freeze_snapshot,
)


class ScenarioKind(str, Enum):
    REAL_ASSESSMENT = "REAL_ASSESSMENT"
    DEMO_SCENARIO = "DEMO_SCENARIO"


@dataclass(frozen=True)
class ScenarioDescriptor:
    assessment_id: str
    title: str
    kind: ScenarioKind
    builder: Callable[[], dict[str, Any]]


def _ecdsa_bootloader_config(snap: dict[str, Any]) -> dict[str, Any]:
    return {
        "sign": "ECC256",
        "wolfboot_size_bytes": snap["ecdsa"]["bootloader_size_bytes"],
    }


def _mldsa_firmware_config(snap: dict[str, Any]) -> dict[str, Any]:
    return {
        "sign": "ML_DSA",
        "signed_image_size_bytes": snap["mldsa87"]["signed_image_size_bytes"],
    }


def _firmware_only_transition(assessment: dict[str, Any], snap: dict[str, Any]) -> None:
    """Single firmware step; bootloader stays on deployed ECDSA configuration."""
    boot_cfg = _ecdsa_bootloader_config(snap)
    assessment["profile"]["requirements"] = [
        req
        for req in assessment["profile"]["requirements"]
        if req["id"] != "REQ-BOOT-S0S1"
    ]
    assessment["allowed_change_set"] = {
        "modifiable_components": ["firmware"],
        "allowed_actions": ["UPDATE_FIRMWARE"],
    }
    assessment["derived_effects"] = [
        {
            "effect_id": "DE-AUTH-S2",
            "effect_type": "AUTHORIZATION_POLICY_UPDATE",
            "target_ref": "fw-boot",
            "affected_field": "authorization_path_states",
            "derivation_rule_ref": "RULE-AUTH-TRANSITION",
        }
    ]
    s0 = {
        "state_id": "S0",
        "snapshot_hash": "sha256:wp0-s0-ecdsa",
        "components": [
            {"component_id": "bootloader", "configuration": {"sign": "ECC256"}},
            {"component_id": "firmware", "configuration": {"sign": "ECC256"}},
        ],
        "authorization_path_states": {
            "fw-boot": {"policy": "CLASSICAL_ONLY", "accepted_schemes": ["ECDSA_P256"]}
        },
    }
    s2 = {
        "state_id": "S2",
        "snapshot_hash": "sha256:wp0-s2-firmware-only",
        "components": [
            {"component_id": "bootloader", "configuration": {"sign": "ECC256"}},
            {"component_id": "firmware", "configuration": {"sign": "ML_DSA"}},
        ],
        "authorization_path_states": {
            "fw-boot": {"policy": "UNKNOWN", "accepted_schemes": ["ML_DSA_87"]}
        },
    }
    assessment["transition_plan"]["plan_id"] = "PLAN-WP0-FIRMWARE-ONLY"
    assessment["transition_plan"]["version"] = "1.0-scenario"
    assessment["transition_plan"]["hash"] = "version-pin:plan-wp0-firmware-only"
    assessment["transition_plan"]["states"] = [s0, s2]
    assessment["transition_plan"]["steps"] = [
        {
            "step_id": "STEP-S0-S2",
            "from": "S0",
            "to": "S2",
            "actions": [
                {
                    "action_id": "ACT-FIRMWARE-S0S2",
                    "action_type": "UPDATE_FIRMWARE",
                    "component_ref": "firmware",
                    "parameters": {},
                    "derived_effect_refs": ["DE-AUTH-S2"],
                }
            ],
            "preconditions": [],
        }
    ]
    assessment["candidate_state"] = {
        "state_id": "S2",
        "snapshot_hash": "sha256:wp0-s2-firmware-only",
        "components": [
            {"component_id": "bootloader", "configuration": copy.deepcopy(boot_cfg)},
            {"component_id": "firmware", "configuration": _mldsa_firmware_config(snap)},
        ],
        "authorization_path_states": {
            "fw-boot": {"policy": "UNKNOWN", "accepted_schemes": ["ML_DSA_87"]}
        },
    }


def build_scenario_indeterminate() -> dict[str, Any]:
    """Migration INDETERMINATE: firmware-only plan, policy/recovery still unknown."""
    snap = load_freeze_snapshot()
    assessment = copy.deepcopy(build_wp0_baseline_assessment(snap))
    assessment["assessment_id"] = "SCENARIO-INDETERMINATE-20261001"
    _firmware_only_transition(assessment, snap)
    return assessment


def _maintenance_requirement() -> dict[str, Any]:
    return {
        "id": "REQ-MAINTENANCE-WINDOW",
        "risk_category": "UPDATE_ROLLBACK_RECOVERY",
        "applicable_phase": ["TRANSITION"],
        "critical_for_verdict": True,
        "criterion": (
            "Firmware update during declared maintenance window without uncontrolled interruption"
        ),
        "scope_status": "IN_SCOPE",
        "rule_refs": ["RULE-MAINTENANCE-WINDOW"],
        "acceptable_evidence_policy": {
            "required_evidence_groups": [
                {
                    "role": "HAZARD_OBSERVATION",
                    "min_satisfied": 1,
                    "accepted_combinations": [
                        {
                            "evidence_kind": ["MEASUREMENT"],
                            "source_role": ["TOOL"],
                            "authority_context": ["OBSERVED"],
                            "acquisition_mode": ["EMULATED"],
                            "review_status": ["AUTOMATIC"],
                        }
                    ],
                },
                {
                    "role": "CONDITION_CLOSURE",
                    "min_satisfied": 1,
                    "accepted_combinations": [
                        {
                            "evidence_kind": ["DECLARATION"],
                            "source_role": ["SYSTEM_OWNER"],
                            "authority_context": ["SIMULATED"],
                            "acquisition_mode": ["DOCUMENTARY"],
                            "review_status": ["CONFIRMED"],
                        }
                    ],
                },
            ],
            "operational_precondition_allowed": True,
        },
    }


def build_scenario_conditional() -> dict[str, Any]:
    """Transition CONDITIONAL: maintenance precondition admitted, closure evidence absent."""
    assessment = copy.deepcopy(build_scenario_indeterminate())
    assessment["assessment_id"] = "SCENARIO-CONDITIONAL-20261001"
    _strip_i4_unknown_evidence(assessment)
    _apply_scenario_policy_recovery_perimeter(assessment)
    _append_perimeter_declarations(assessment, closes_maintenance=False)
    _append_scenario_i4_closure_evidence(assessment)
    profile = assessment["profile"]
    profile["allowed_operational_preconditions"] = ["COND-MAINTENANCE-WINDOW"]
    profile["requirements"].append(_maintenance_requirement())
    assessment["transition_plan"]["steps"][0]["preconditions"] = [
        {
            "condition_id": "COND-MAINTENANCE-WINDOW",
            "condition_type": "OPERATIONAL_PRECONDITION",
            "requirement_id": "REQ-MAINTENANCE-WINDOW",
            "closure_action": "Controlled maintenance window",
            "acceptance_criterion": "No uncontrolled power loss during update",
        }
    ]
    return assessment


def _strip_i4_unknown_evidence(assessment: dict[str, Any]) -> None:
    """Remove freeze placeholders that block scenario E12 PASS for INV-I4."""
    assessment["evidence"] = [
        item
        for item in assessment.get("evidence") or []
        if item.get("id") not in {"EV-E12-WINDOW"}
    ]
    assessment["evidence_gaps"] = [
        gap
        for gap in assessment.get("evidence_gaps") or []
        if gap.get("requirement_id") != "INV-I4"
    ]


def _apply_scenario_policy_recovery_perimeter(assessment: dict[str, Any]) -> None:
    """Scenario-only declarations: close I2/I3 on transition and target (not freeze facts)."""
    assessment["observed_recovery_mode"] = "FIELD_SERVICE"
    policy = {"policy": "PQC_ONLY", "accepted_schemes": ["ML_DSA_87"]}
    assessment["candidate_state"]["authorization_path_states"]["fw-boot"] = copy.deepcopy(
        policy
    )
    final = assessment["transition_plan"]["states"][-1]
    final["authorization_path_states"]["fw-boot"] = copy.deepcopy(policy)


def _append_scenario_i4_closure_evidence(assessment: dict[str, Any]) -> None:
    assessment["evidence"].append(
        {
            "id": "EV-SCENARIO-NON-ATOMIC",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "SIMULATED",
            "acquisition_mode": "CATALOG_FACT",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "test_id": "E12",
            "run_id": "scenario-e12-closed",
            "artifact_refs": ["scenario-update-recovery.log"],
            "value": "PASS",
        }
    )


def _scenario_declaration(
    evidence_id: str,
    *,
    source_identity: str,
    content_hash: str,
    review_status: str = "CONFIRMED",
) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "evidence_kind": "DECLARATION",
        "source_role": "SYSTEM_OWNER",
        "authority_context": "SIMULATED",
        "acquisition_mode": "DOCUMENTARY",
        "review_status": review_status,
        "status": "VALID",
        "source_identity": source_identity,
        "content_hash": content_hash,
    }


def _append_perimeter_declarations(
    assessment: dict[str, Any],
    *,
    closes_maintenance: bool = True,
) -> None:
    """Document scenario-only policy and recovery. Not freeze measurements.

    A confirmed system-owner declaration also closes REQ-MAINTENANCE-WINDOW.
    The conditional copy keeps that closure absent.
    """
    review_status = "CONFIRMED" if closes_maintenance else "SCENARIO_NOTE"
    suffix = "20261001" if closes_maintenance else "20261001-open"
    assessment["evidence"].extend(
        [
            _scenario_declaration(
                "EV-SCENARIO-RECOVERY",
                source_identity="Scenario owner — field service available",
                content_hash=f"sha256:scenario-recovery-decl-{suffix}",
                review_status=review_status,
            ),
            _scenario_declaration(
                "EV-SCENARIO-POLICY",
                source_identity="Scenario owner — PQC-only boot path",
                content_hash=f"sha256:scenario-policy-decl-{suffix}",
                review_status=review_status,
            ),
        ]
    )


def build_scenario_compatible() -> dict[str, Any]:
    """COMPATIBLE within a declared scenario perimeter (not the freeze facts)."""
    assessment = copy.deepcopy(build_scenario_indeterminate())
    assessment["assessment_id"] = "SCENARIO-COMPATIBLE-20261001"
    _strip_i4_unknown_evidence(assessment)
    _apply_scenario_policy_recovery_perimeter(assessment)
    _append_perimeter_declarations(assessment)
    _append_scenario_i4_closure_evidence(assessment)
    return assessment


def list_scenario_descriptors() -> tuple[ScenarioDescriptor, ...]:
    return (
        ScenarioDescriptor(
            assessment_id="WP0-FREEZE-20261001",
            title="WP0 Freeze — nRF52840",
            kind=ScenarioKind.REAL_ASSESSMENT,
            builder=build_wp0_baseline_assessment,
        ),
        ScenarioDescriptor(
            assessment_id="SCENARIO-INDETERMINATE-20261001",
            title="Scenario — firmware-only migration gap",
            kind=ScenarioKind.DEMO_SCENARIO,
            builder=build_scenario_indeterminate,
        ),
        ScenarioDescriptor(
            assessment_id="SCENARIO-CONDITIONAL-20261001",
            title="Scenario — maintenance precondition open",
            kind=ScenarioKind.DEMO_SCENARIO,
            builder=build_scenario_conditional,
        ),
        ScenarioDescriptor(
            assessment_id="SCENARIO-COMPATIBLE-20261001",
            title="Scenario — perimetro dichiarato chiuso",
            kind=ScenarioKind.DEMO_SCENARIO,
            builder=build_scenario_compatible,
        ),
        ScenarioDescriptor(
            assessment_id="WP0-A4-SIGNER-BOUND-20261001",
            title="Scenario — signer bound refusal",
            kind=ScenarioKind.DEMO_SCENARIO,
            builder=build_a4_signer_bound_assessment,
        ),
    )


def build_assessment_by_id(assessment_id: str) -> dict[str, Any]:
    for item in list_scenario_descriptors():
        if item.assessment_id == assessment_id:
            return item.builder()
    raise KeyError(f"Unknown scenario assessment_id: {assessment_id}")


__all__ = [
    "ScenarioDescriptor",
    "ScenarioKind",
    "build_assessment_by_id",
    "build_scenario_compatible",
    "build_scenario_conditional",
    "build_scenario_indeterminate",
    "list_scenario_descriptors",
]
