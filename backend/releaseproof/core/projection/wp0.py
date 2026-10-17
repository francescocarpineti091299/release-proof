"""Build assessments from the WP0 freeze snapshot."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from releaseproof.core.evidence.map import (
    evidence_from_wp0_runs,
    evidence_gaps_for_wp0,
    layout_measurement,
)
from releaseproof.core.paths import CONTRACT_PACK

_PACK = CONTRACT_PACK
SNAPSHOT_PATH = _PACK / "examples" / "wp0_freeze_snapshot_v1_2.json"


def load_freeze_snapshot(path: Path | None = None) -> dict[str, Any]:
    target = path or SNAPSHOT_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def build_wp0_baseline_assessment(snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Project the frozen nRF52840 facts into a READY assessment with an honest transition plan."""
    snap = snapshot or load_freeze_snapshot()
    evidence = evidence_from_wp0_runs(snap)

    assessment: dict[str, Any] = {
        "assessment_id": "WP0-FREEZE-20261001",
        "contract_version": "1.2",
        "created_at": "2026-10-01T08:00:00Z",
        "lifecycle": "READY",
        "observed_recovery_mode": "UNKNOWN",
        "profile": {
            "id": "PROFILE-WP0-NRF52840",
            "version": "1.0",
            "hash": "version-pin:profile-wp0-nrf52840",
            "acceptable_recovery_modes": ["FIELD_SERVICE", "DEPOT_PHYSICAL_REFLASH"],
            "allowed_operational_preconditions": [],
            "requirements": [
                {
                    "id": "REQ-LAYOUT",
                    "risk_category": "LAYOUT_STORAGE",
                    "applicable_phase": ["TARGET", "TRANSITION"],
                    "critical_for_verdict": True,
                    "criterion": "Signed factory image fits boot partition",
                    "scope_status": "IN_SCOPE",
                    "rule_refs": ["RULE-LAYOUT"],
                    "acceptable_evidence_policy": {
                        "required_evidence_groups": [
                            {
                                "role": "PRIMARY",
                                "min_satisfied": 1,
                                "accepted_combinations": [
                                    {
                                        "evidence_kind": ["MEASUREMENT"],
                                        "source_role": ["TOOL"],
                                        "authority_context": ["OBSERVED"],
                                        "acquisition_mode": ["STATIC_ARTIFACT", "STATIC_ANALYSIS"],
                                        "review_status": ["AUTOMATIC"],
                                    }
                                ],
                            }
                        ]
                    },
                },
                {
                    "id": "REQ-BOOT-S0S1",
                    "risk_category": "UPDATE_ROLLBACK_RECOVERY",
                    "applicable_phase": ["TRANSITION"],
                    "applicable_subject_types": ["TRANSITION_STEP"],
                    "critical_for_verdict": True,
                    "criterion": (
                        "Declared transition requires bootloader self-update. "
                        "Unsupported on this board blocks the transition verdict, "
                        "not the candidate."
                    ),
                    "scope_status": "IN_SCOPE",
                    "rule_refs": ["RULE-BOOT-S0S1"],
                    "acceptable_evidence_policy": {
                        "required_evidence_groups": [
                            {
                                "role": "PRIMARY",
                                "min_satisfied": 1,
                                "accepted_combinations": [
                                    {
                                        "evidence_kind": ["MEASUREMENT"],
                                        "source_role": ["TOOL"],
                                        "authority_context": ["OBSERVED"],
                                        "acquisition_mode": ["SOURCE_INSPECTION", "EMULATED"],
                                        "review_status": ["AUTOMATIC"],
                                    }
                                ],
                            }
                        ]
                    },
                },
                {
                    "id": "REQ-AUTH-NEGATIVE",
                    "risk_category": "AUTHENTICITY_SIGNATURE",
                    "applicable_phase": ["TARGET"],
                    "critical_for_verdict": False,
                    "criterion": (
                        "Transitional verifier rejects factory image with wrong signing key (E03)"
                    ),
                    "scope_status": "IN_SCOPE",
                    "rule_refs": ["RULE-AUTH-NEGATIVE"],
                    "acceptable_evidence_policy": {
                        "required_evidence_groups": [
                            {
                                "role": "PRIMARY",
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
                            }
                        ]
                    },
                },
                {
                    "id": "REQ-RAM",
                    "risk_category": "RUNTIME_RESOURCES",
                    "applicable_phase": ["TARGET"],
                    "critical_for_verdict": False,
                    "criterion": "RAM/stack within budget",
                    "scope_status": "IN_SCOPE",
                    "rule_refs": ["RULE-RAM"],
                    "acceptable_evidence_policy": {
                        "required_evidence_groups": [
                            {
                                "role": "PRIMARY",
                                "min_satisfied": 1,
                                "accepted_combinations": [
                                    {
                                        "evidence_kind": ["MEASUREMENT"],
                                        "source_role": ["TOOL"],
                                        "authority_context": ["OBSERVED"],
                                        "acquisition_mode": ["STATIC_ANALYSIS"],
                                        "review_status": ["AUTOMATIC"],
                                    }
                                ],
                            }
                        ]
                    },
                },
            ],
        },
        "platform_model": {
            "id": "PLATFORM-NRF52840-WOLFBOOT",
            "version": "1.0",
            "hash": f"version-pin:wolfboot-{snap['wolfboot_commit'][:12]}",
            "declared_surface_ids": ["fw-boot", "fw-update", "recovery"],
            "components": [
                {
                    "component_id": "bootloader",
                    "component_type": "SECURE_BOOTLOADER",
                    "mutability": "UPDATABLE",
                },
                {
                    "component_id": "firmware",
                    "component_type": "APPLICATION_FIRMWARE",
                    "mutability": "UPDATABLE",
                },
            ],
            "authorization_paths": [
                {
                    "path_id": "fw-boot",
                    "purpose": "FIRMWARE_BOOT",
                    "authorization_mode": "UNKNOWN",
                    "component_refs": ["bootloader"],
                }
            ],
            "recovery_modes": ["FIELD_SERVICE", "DEPOT_PHYSICAL_REFLASH", "UNKNOWN"],
        },
        "deployed_state": {
            "state_id": "S0",
            "snapshot_hash": "sha256:wp0-s0-ecdsa",
            "components": [
                {
                    "component_id": "bootloader",
                    "configuration": {
                        "sign": "ECC256",
                        "wolfboot_size_bytes": snap["ecdsa"]["bootloader_size_bytes"],
                    },
                },
                {
                    "component_id": "firmware",
                    "configuration": {
                        "sign": "ECC256",
                        "signed_image_size_bytes": snap["ecdsa"]["signed_image_size_bytes"],
                    },
                },
            ],
            "authorization_path_states": {
                "fw-boot": {"policy": "CLASSICAL_ONLY", "accepted_schemes": ["ECDSA_P256"]}
            },
        },
        "candidate_state": {
            "state_id": "S2",
            "snapshot_hash": "sha256:wp0-s2-mldsa87",
            "components": [
                {
                    "component_id": "bootloader",
                    "configuration": {
                        "sign": "ML_DSA",
                        "ml_dsa_level": 5,
                        "wolfboot_size_bytes": snap["mldsa87"]["bootloader_size_bytes"],
                    },
                },
                {
                    "component_id": "firmware",
                    "configuration": {
                        "sign": "ML_DSA",
                        "signed_image_size_bytes": snap["mldsa87"]["signed_image_size_bytes"],
                    },
                },
            ],
            "authorization_path_states": {
                "fw-boot": {"policy": "UNKNOWN", "accepted_schemes": ["ML_DSA_87"]}
            },
        },
        "allowed_change_set": {
            "modifiable_components": ["bootloader", "firmware"],
            "allowed_actions": ["UPDATE_BOOTLOADER", "UPDATE_FIRMWARE"],
        },
        "derived_effects": [
            {
                "effect_id": "DE-AUTH-S1",
                "effect_type": "AUTHORIZATION_POLICY_UPDATE",
                "target_ref": "fw-boot",
                "affected_field": "authorization_path_states",
                "derivation_rule_ref": "RULE-AUTH-TRANSITION",
            },
            {
                "effect_id": "DE-AUTH-S2",
                "effect_type": "AUTHORIZATION_POLICY_UPDATE",
                "target_ref": "fw-boot",
                "affected_field": "authorization_path_states",
                "derivation_rule_ref": "RULE-AUTH-TRANSITION",
            },
        ],
        "transition_plan": {
            "plan_id": "PLAN-WP0-S0-S2",
            "version": "1.0",
            "hash": "version-pin:plan-wp0-s0-s2",
            "states": [
                {
                    "state_id": "S0",
                    "snapshot_hash": "sha256:wp0-s0-ecdsa",
                    "components": [
                        {
                            "component_id": "bootloader",
                            "configuration": {"sign": "ECC256"},
                        },
                        {
                            "component_id": "firmware",
                            "configuration": {"sign": "ECC256"},
                        },
                    ],
                    "authorization_path_states": {
                        "fw-boot": {"policy": "CLASSICAL_ONLY", "accepted_schemes": ["ECDSA_P256"]}
                    },
                },
                {
                    "state_id": "S1",
                    "snapshot_hash": "sha256:wp0-s1-transitional",
                    "components": [
                        {
                            "component_id": "bootloader",
                            "configuration": {"sign": "ML_DSA", "ml_dsa_level": 5},
                        },
                        {
                            "component_id": "firmware",
                            "configuration": {"sign": "ECC256"},
                        },
                    ],
                    "authorization_path_states": {
                        "fw-boot": {"policy": "UNKNOWN", "accepted_schemes": []}
                    },
                },
                {
                    "state_id": "S2",
                    "snapshot_hash": "sha256:wp0-s2-mldsa87",
                    "components": [
                        {
                            "component_id": "bootloader",
                            "configuration": {"sign": "ML_DSA", "ml_dsa_level": 5},
                        },
                        {
                            "component_id": "firmware",
                            "configuration": {"sign": "ML_DSA"},
                        },
                    ],
                    "authorization_path_states": {
                        "fw-boot": {"policy": "UNKNOWN", "accepted_schemes": ["ML_DSA_87"]}
                    },
                },
            ],
            "steps": [
                {
                    "step_id": "STEP-S0-S1",
                    "from": "S0",
                    "to": "S1",
                    "actions": [
                        {
                            "action_id": "ACT-BOOTLOADER-S0S1",
                            "action_type": "UPDATE_BOOTLOADER",
                            "component_ref": "bootloader",
                            "parameters": {"mechanism": "bootloader_self_update"},
                            "derived_effect_refs": ["DE-AUTH-S1"],
                        }
                    ],
                    "preconditions": [],
                },
                {
                    "step_id": "STEP-S1-S2",
                    "from": "S1",
                    "to": "S2",
                    "actions": [
                        {
                            "action_id": "ACT-FIRMWARE-S1S2",
                            "action_type": "UPDATE_FIRMWARE",
                            "component_ref": "firmware",
                            "parameters": {},
                            "derived_effect_refs": ["DE-AUTH-S2"],
                        }
                    ],
                    "preconditions": [],
                },
            ],
        },
        "evidence": evidence,
        "evidence_gaps": evidence_gaps_for_wp0(),
        "coverage_assertions": [],
        "ruleset_ref": {
            "id": "RULESET-V1.2",
            "version": "1.2",
            "hash": "version-pin:ruleset-v1.2",
        },
    }
    assessment["platform_model"]["authorization_paths"][0]["authorization_mode"] = "UNKNOWN"
    return assessment


def build_a4_oversized_assessment(
    snapshot: dict[str, Any] | None = None,
    measurement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """What-if A4 from a signed-image size read off an artifact.

    A number that was not read from a file is not a freeze fact. Callers that
    pass ``measurement`` directly are exercising LEQ. The snapshot is used only
    when ``measured_from_artifact`` is true.
    """
    snap = snapshot or load_freeze_snapshot()
    oversized = measurement if measurement is not None else (snap.get("a4_oversized") or {})
    if measurement is None and not oversized.get("measured_from_artifact"):
        raise ValueError("A4 requires a signed artifact measurement")
    if "signed_image_size_bytes" not in oversized:
        raise ValueError("A4 measurement has no signed_image_size_bytes")
    assessment = build_wp0_baseline_assessment(snap)
    assessment = copy.deepcopy(assessment)
    assessment["assessment_id"] = "WP0-A4-OVERSIZED-20261001"
    signed_size = int(oversized["signed_image_size_bytes"])
    partition = int(snap["partition_size_bytes"])
    assessment["candidate_state"]["state_id"] = "S2-A4"
    assessment["candidate_state"]["snapshot_hash"] = "sha256:wp0-s2-a4-oversized"
    assessment["candidate_state"]["components"][1]["configuration"]["signed_image_size_bytes"] = (
        signed_size
    )
    assessment["transition_plan"]["plan_id"] = "PLAN-WP0-S0-S2-A4"
    assessment["transition_plan"]["version"] = "1.1"
    assessment["transition_plan"]["hash"] = "version-pin:plan-wp0-s0-s2-a4"
    final = assessment["transition_plan"]["states"][-1]
    final_hash = "sha256:wp0-s2-a4-oversized"
    final["state_id"] = "S2-A4"
    for step in assessment["transition_plan"]["steps"]:
        if step["from"] == "S2":
            step["from"] = "S2-A4"
        if step["to"] == "S2":
            step["to"] = "S2-A4"
    final["snapshot_hash"] = final_hash
    final["components"][1]["configuration"]["signed_image_size_bytes"] = signed_size
    assessment["candidate_state"] = copy.deepcopy(final)
    assessment["candidate_state"]["snapshot_hash"] = final_hash

    assessment["evidence"] = [
        item for item in assessment["evidence"] if item.get("id") != "EV-E05-LAYOUT-G2"
    ]
    assessment["evidence"].append(
        layout_measurement(
            "EV-E05-LAYOUT-A4",
            signed_artifact_size=signed_size,
            boot_slot_capacity=partition,
            run_id=oversized.get("run_id"),
            acquisition_mode="STATIC_ARTIFACT",
        )
    )
    artifact_name = str(oversized.get("artifact_name") or "signed-image.bin")
    assessment["evidence"][-1]["artifact_refs"] = [artifact_name]
    return assessment


def build_a4_signer_bound_assessment(
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Separate assessment for the G2 signer refusal.

    The baseline candidate image is left unchanged. The new requirement compares
    the two sizes printed by the signer. It does not invent a signed file.
    """
    snap = snapshot or load_freeze_snapshot()
    bound = snap.get("a4_oversized") or {}
    if not bound.get("sign_refused"):
        raise ValueError("A4 signer bound requires a recorded sign refusal")
    requested = bound.get("requested_image_size_bytes")
    maximum = bound.get("max_signable_image_size_bytes")
    if (
        bound.get("signing_result") != "REJECTED"
        or not isinstance(requested, int)
        or not isinstance(maximum, int)
    ):
        raise ValueError("A4 signer bound is missing the signer operands")

    assessment = copy.deepcopy(build_wp0_baseline_assessment(snap))
    assessment["assessment_id"] = "WP0-A4-SIGNER-BOUND-20261001"
    assessment["profile"]["requirements"].append(_sign_bound_requirement())
    assessment["evidence"].append(
        {
            "id": "EV-A4-SIGNER-BOUND",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "SIGN_TOOL",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "test_id": "A4",
            "run_id": bound.get("run_id"),
            "artifact_refs": ["sign.log"],
            "source_identity": snap.get("wolfboot_commit"),
            "value": {
                "requested_image_size": requested,
                "max_signable_image_size": maximum,
                "signing_result": "REJECTED",
                "image_header_size_bytes": bound.get("image_header_size_bytes"),
                "unsigned_payload_size_bytes": bound.get("unsigned_payload_size_bytes"),
            },
        }
    )
    return assessment


def _sign_bound_requirement() -> dict[str, Any]:
    return {
        "id": "REQ-SIGN-BOUND",
        "risk_category": "LAYOUT_STORAGE",
        "applicable_phase": ["TARGET"],
        "critical_for_verdict": True,
        "criterion": (
            "Requested header-plus-firmware image is within the maximum "
            "the G2 signer accepted on this commit"
        ),
        "scope_status": "IN_SCOPE",
        "rule_refs": ["RULE-SIGN-BOUND"],
        "acceptable_evidence_policy": {
            "required_evidence_groups": [
                {
                    "role": "PRIMARY",
                    "min_satisfied": 1,
                    "accepted_combinations": [
                        {
                            "evidence_kind": ["MEASUREMENT"],
                            "source_role": ["TOOL"],
                            "authority_context": ["OBSERVED"],
                            "acquisition_mode": ["SIGN_TOOL"],
                            "review_status": ["AUTOMATIC"],
                        }
                    ],
                }
            ]
        },
    }


__all__ = [
    "build_a4_oversized_assessment",
    "build_a4_signer_bound_assessment",
    "build_wp0_baseline_assessment",
    "load_freeze_snapshot",
]
