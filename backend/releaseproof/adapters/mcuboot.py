"""MCUboot (Zephyr, nRF52840) live facts → V1.2 assessment (adapter ``mcuboot_v1_2``).

The change is a post-quantum migration (D06): whether the pinned MCUboot/imgtool can produce
and verify an ML-DSA image is *measured* by E02 (sign attempt), never assumed. See
``_common`` for the gating rules.

Requirement map (requirement ← decisive fact, coverage surface, group acquisition):

* REQ-PQC-VERIFIER (TARGET, critical) ← E02 ``pqc_signing`` (+ candidate ``boot_outcome``
  when a runner reports one). ``REJECTED`` → evidence ``UNSUPPORTED`` → VIOLATED. ``OK``
  only proves the tool signs; verification needs an observed candidate boot, otherwise the
  requirement is UNKNOWN. Group: SIGN_TOOL + EMULATED (the only generic failure tokens on
  those modes are the pqc row and a failed candidate boot).
* REQ-LAYOUT (TARGET+TRANSITION, critical) ← E05 ``layout_fit`` **on the candidate**. The
  catalog measures E05 on the deployed image; that row is informational
  (EV-E05-LAYOUT-DEPLOYED) and does not cover the candidate slot.
* REQ-BL-FIELD-UPDATE (TRANSITION/steps, critical; default plan) ← E11
  ``bootloader_field_update`` (STATIC_CONFIG, also the mode of D01 partition rows, hence
  coverage gating).
* REQ-AUTH-NEGATIVE (TRANSITION/plan, critical) ← E03 via RULE-AUTH-NEGATIVE (D05).
* REQ-RAM (TARGET, non-critical) ← never measured.
* REQ-MAINTENANCE-WINDOW (depot plan only) ← admitted precondition, OPEN_CONDITION.

No catalog test observes the candidate authorization policy, so it stays ``UNKNOWN``.
"""

from __future__ import annotations

import copy
from typing import Any

from releaseproof.adapters import _common as c
from releaseproof.contracts.profile import ChangeScenario, Profile
from releaseproof.contracts.runner import ArtifactEvent, Observation, TestResultEvent

ADAPTER_NAME = "mcuboot_v1_2"
FAMILY = "mcuboot"

MECH_DEPOT = "depot_physical_reflash"
_SUPPORTED_MECHANISMS = {MECH_DEPOT}

_FIELD_UPDATE = {"SUPPORTED": "PASS", "UNSUPPORTED": "UNSUPPORTED"}
_AUTH_NEGATIVE = {"REJECT": "REJECT", "ACCEPT": "ACCEPT"}
_CROSS_UPDATE = {"REJECTED": "REJECTED", "APPLIED": "APPLIED"}
_UPDATE = {"APPLIED": "APPLIED", "NOT_APPLIED": "NOT_APPLIED"}


def build_mcuboot_v1_2_assessment(
    *,
    profile: Profile,
    change: ChangeScenario,
    plan_id: str,
    run_id: str,
    evidence_run_id: str,
    created_at: str,
    observations: list[Observation],
    artifacts: list[ArtifactEvent],
    test_results: list[TestResultEvent],
) -> dict[str, Any]:
    """Project one MCUboot LIVE run into a READY V1.2 assessment for ``plan_id``."""
    c.check_inputs(
        profile=profile,
        change=change,
        family=FAMILY,
        run_id=run_id,
        evidence_run_id=evidence_run_id,
        created_at=created_at,
    )
    mechanism = c.resolve_mechanism(change, plan_id, _SUPPORTED_MECHANISMS)
    facts = c.Facts(observations, artifacts, test_results)
    ev = c.EvidenceSet(facts, evidence_run_id)

    # ---------------------------------------------------------------- I1 inputs
    boots = c.boot_rows(
        ev,
        [("EV-E01-BOOT", "E01", "NOT_BOOTABLE"), ("EV-E02-BOOT", "E02", "FAIL")],
    )
    for test_id, label in (("E01", "deployed"), ("E02", "candidate")):
        if boots[test_id] == c.UNKNOWN:
            ev.missing_gap(
                f"GAP-{test_id}-BOOT",
                "INV-I1",
                test_id,
                "boot_outcome",
                critical=True,
                requested=f"{test_id} {label} image boot observed in emulation",
            )

    # ---------------------------------------------------------------- D01
    bl_commit = ev.add_identity_fact("EV-PIN-MCUBOOT", "D01", "bootloader_commit")
    c.check_pin(bl_commit, profile.bootloader.commit, "MCUboot")
    ev.add_identity_fact("EV-PIN-ZEPHYR", "D01", "zephyr_commit")
    partition = facts.get("D01", "partition_layout")
    layout = partition.value if partition is not None and isinstance(partition.value, dict) else {}
    slot0 = layout.get("slot0_size")
    if partition is not None and c.is_int(slot0):
        part_value = {k: v for k, v in layout.items() if k != "signed_artifact_size"}
        part_value["boot_slot_capacity"] = slot0
        ev.add(ev.observed("EV-LAYOUT-PARTITION", partition, part_value))
    key_types = facts.get("D01", "imgtool_key_types")
    if key_types is not None and isinstance(key_types.value, list):
        ev.add(
            ev.observed(
                "EV-D01-IMGTOOL-KEYTYPES", key_types, {"imgtool_key_types": key_types.value}
            )
        )

    # ---------------------------------------------------------------- E11
    field_update = ev.add_enum_fact(
        "EV-E11-BL-FIELD-UPDATE", "E11", "bootloader_field_update", _FIELD_UPDATE
    )
    e11 = facts.get("E11", "bootloader_field_update")
    if field_update is not None and e11 is not None:
        ev.cover(c.SURFACE_BL_UPDATE, e11, subject="STEP-S0-S1", scope="E11 partition map")

    # ---------------------------------------------------------------- E01 statics, E08
    bl_size = ev.add_dict_fact("EV-BOOTLOADER-SIZE-G1", "E01", "bootloader_size_bytes")
    fw_size = ev.add_dict_fact("EV-E01-SIGNED-SIZE", "E01", "signed_image_size_bytes")
    key = ev.add_dict_fact("EV-E01-PUBKEY", "E01", "public_key_sha256")
    ev.add_scalar_fact("EV-E01-VERSION", "E01", "observed_version")
    ev.add_enum_fact("EV-E08-UPDATE", "E08", "update_outcome", _UPDATE)

    # ---------------------------------------------------------------- E05
    _layout(ev, facts, slot0)

    # ---------------------------------------------------------------- E03 / X01
    auth = ev.add_enum_fact("EV-E03-PANIC", "E03", "auth_negative", _AUTH_NEGATIVE)
    e03 = facts.get("E03", "auth_negative")
    if auth is not None and e03 is not None:
        ev.cover(c.SURFACE_VERIFIER_NEGATIVE, e03, subject="S0", scope="E03 tampered update")
    else:
        ev.missing_gap(
            "GAP-E03-AUTH-NEGATIVE",
            "REQ-AUTH-NEGATIVE",
            "E03",
            "auth_negative",
            critical=True,
            requested="E03 tampered update rejection observed on the deployed MCUboot",
        )
    ev.add_enum_fact("EV-X01-CROSS-UPDATE", "X01", "cross_update_outcome", _CROSS_UPDATE)

    # ---------------------------------------------------------------- E02 PQC signing
    signing = _pqc_signing(ev, facts, boots["E02"])
    c.e12_placeholder(ev)

    # ---------------------------------------------------------------- states
    classical = {"policy": "CLASSICAL_ONLY", "accepted_schemes": [change.from_scheme]}
    candidate_policy = {"policy": "UNKNOWN", "accepted_schemes": [change.to_scheme]}
    ev.gap(
        "GAP-CANDIDATE-AUTH-POLICY",
        "INV-I3",
        "No test observes which signatures a PQC MCUboot would accept",
        critical=True,
        requested="Candidate bootloader rejects a classically signed image",
    )
    s0_bl: dict[str, Any] = {"sign": change.from_scheme}
    if c.is_int(bl_size):
        s0_bl["bootloader_size_bytes"] = bl_size
    if isinstance(key, str):
        s0_bl["public_key_sha256"] = key
    sha = facts.artifact_sha(facts.get("E01", "bootloader_size_bytes"))
    if sha:
        s0_bl["artifact_sha256"] = sha
    s0_fw: dict[str, Any] = {"sign": change.from_scheme}
    if c.is_int(fw_size):
        s0_fw["signed_image_size_bytes"] = fw_size
    sha = facts.artifact_sha(facts.get("E01", "signed_image_size_bytes"))
    if sha:
        s0_fw["artifact_sha256"] = sha
    s2_bl: dict[str, Any] = {"sign": change.to_scheme}
    s2_fw: dict[str, Any] = {"sign": change.to_scheme}
    if signing is not None:
        s2_fw["pqc_signing_result"] = signing
        sha = facts.artifact_sha(facts.get("E02", "pqc_signing"))
        if sha:
            s2_fw["signing_record_sha256"] = sha

    s0 = c.system_state("S0", bootloader=s0_bl, firmware=s0_fw, path_state=classical)
    s1 = c.system_state("S1", bootloader=s2_bl, firmware=s0_fw, path_state=candidate_policy)
    s2 = c.system_state("S2", bootloader=s2_bl, firmware=s2_fw, path_state=candidate_policy)

    bl_mechanism = "mcuboot_field_update" if mechanism == c.DEFAULT_PLAN else MECH_DEPOT
    steps: list[dict[str, Any]] = [
        {
            "step_id": "STEP-S0-S1",
            "from": "S0",
            "to": "S1",
            "actions": [
                c.action(
                    "ACT-BOOTLOADER-S0S1", "UPDATE_BOOTLOADER", "bootloader",
                    effects=["DE-AUTH-S1"], mechanism=bl_mechanism,
                )
            ],
            "preconditions": [],
        },
        {
            "step_id": "STEP-S1-S2",
            "from": "S1",
            "to": "S2",
            "actions": [
                c.action(
                    "ACT-FIRMWARE-S1S2", "UPDATE_FIRMWARE", "firmware", effects=["DE-AUTH-S2"]
                )
            ],
            "preconditions": [],
        },
    ]
    requirements = [
        c.layout_requirement(),
        _pqc_verifier_requirement(change.to_scheme),
        c.auth_negative_requirement(),
        c.ram_requirement(),
    ]
    observed_recovery = "UNKNOWN"
    allowed_preconditions: list[str] = []
    if mechanism == c.DEFAULT_PLAN:
        requirements.insert(1, _field_update_requirement())
        if field_update is None:
            ev.missing_gap(
                "GAP-E11-BL-FIELD-UPDATE",
                "REQ-BL-FIELD-UPDATE",
                "E11",
                "bootloader_field_update",
                critical=True,
                requested="E11 bootloader field-update capability of the built configuration",
            )
        ev.gap(
            "GAP-RECOVERY-MODE",
            "INV-I2",
            "Recovery after a failed over-the-air MCUboot replacement was not observed",
            critical=True,
            requested="Observed recovery mode after an interrupted bootloader update",
        )
    else:
        requirements.insert(1, _field_update_requirement(scope="NOT_APPLICABLE"))
        requirements.append(
            c.maintenance_requirement(
                "MCUboot re-flash by debug probe happens in a controlled depot procedure "
                "without uncontrolled interruption"
            )
        )
        steps[0]["preconditions"] = [c.maintenance_precondition("Controlled depot re-flash")]
        allowed_preconditions = [c.COND_MAINTENANCE]
        observed_recovery = "DEPOT_PHYSICAL_REFLASH"
        ev.add(
            c.recovery_declaration(
                profile=profile, change=change, plan_id=plan_id, mode=observed_recovery
            )
        )
        c.maintenance_gap(ev)
    c.standard_gaps(ev, include_e10=False)

    pin = bl_commit or profile.bootloader.commit
    plan = c.plan_ref(profile, change, plan_id)
    plan.update({"states": [s0, s1, s2], "steps": steps})
    return {
        "assessment_id": f"RP-ASSESS-{run_id}",
        "contract_version": "1.2",
        "created_at": created_at,
        "lifecycle": "READY",
        "observed_recovery_mode": observed_recovery,
        "profile": {
            **c.profile_ref(profile),
            "acceptable_recovery_modes": list(c.ACCEPTABLE_RECOVERY_MODES),
            "allowed_operational_preconditions": allowed_preconditions,
            "requirements": requirements,
        },
        "platform_model": c.platform_model(
            platform_id="PLATFORM-NRF52840-MCUBOOT",
            version=profile.version,
            pin=f"version-pin:mcuboot-{pin[:12]}",
            bootloader_mutability=c.mutability_from_field_update(field_update),
        ),
        "deployed_state": copy.deepcopy(s0),
        "candidate_state": copy.deepcopy(s2),
        "allowed_change_set": {
            "modifiable_components": ["bootloader", "firmware"],
            "allowed_actions": ["UPDATE_BOOTLOADER", "UPDATE_FIRMWARE"],
        },
        "derived_effects": c.auth_effects(),
        "transition_plan": plan,
        "evidence": ev.evidence(),
        "evidence_gaps": ev.gaps,
        "coverage_assertions": ev.coverage,
        "ruleset_ref": dict(c.RULESET_REF),
    }


# --------------------------------------------------------------------------- helpers


def _layout(ev: c.EvidenceSet, facts: c.Facts, slot0: Any) -> None:
    fit = facts.get("E05", "layout_fit")
    value = fit.value if fit is not None and isinstance(fit.value, dict) else {}
    signed = value.get("signed_artifact_size")
    capacity = value.get("boot_slot_capacity")
    on_candidate = fit is not None and fit.subject == "candidate_state"
    if fit is not None and c.is_int(signed):
        row_value = {"signed_artifact_size": signed}
        if c.is_int(capacity):
            row_value["boot_slot_capacity"] = capacity
        evidence_id = "EV-E05-LAYOUT-CANDIDATE" if on_candidate else "EV-E05-LAYOUT-DEPLOYED"
        ev.add(ev.observed(evidence_id, fit, row_value))
    capacities = {v for v in (capacity, slot0) if c.is_int(v)}
    if on_candidate and c.is_int(signed) and len(capacities) == 1:
        ev.cover(c.SURFACE_BOOT_SLOT, fit, subject="S2", scope="E05 layout_fit")  # type: ignore[arg-type]
        return
    if len(capacities) > 1 and on_candidate:
        reason = f"Slot capacity disagrees between D01 slot0 ({slot0}) and E05 ({capacity})"
    elif fit is not None and not on_candidate:
        reason = (
            "E05 measured the deployed image only; no ML-DSA signed candidate image was "
            "measured against the slot"
        )
    else:
        reason = ev.facts.why_missing("E05", "layout_fit")
    ev.gap(
        "GAP-E05-CANDIDATE-LAYOUT",
        "REQ-LAYOUT",
        reason,
        critical=True,
        requested="E05 signed candidate (ML-DSA) image size against slot 0",
    )


def _pqc_signing(ev: c.EvidenceSet, facts: c.Facts, candidate_boot: str) -> str | None:
    """E02 sign attempt → EV-E02-PQC-SIGN; returns the raw signing_result when decisive."""
    obs = facts.get("E02", "pqc_signing")
    raw = obs.value if obs is not None and isinstance(obs.value, dict) else {}
    result = raw.get("signing_result")
    if obs is None or result not in {"OK", "REJECTED"}:
        if obs is not None:
            ev.add(ev.not_observed("EV-E02-PQC-SIGN", "E02", obs))
        ev.missing_gap(
            "GAP-E02-PQC-VERIFIER",
            "REQ-PQC-VERIFIER",
            "E02",
            "pqc_signing",
            critical=True,
            requested="E02 ML-DSA sign attempt with the pinned imgtool",
        )
        return None
    row = ev.observed("EV-E02-PQC-SIGN", obs, "UNSUPPORTED" if result == "REJECTED" else "SIGNED")
    tool, algorithm = raw.get("tool"), raw.get("algorithm")
    if tool or algorithm:
        row["source_identity"] = f"{tool or obs.parser}:{algorithm or 'unknown-algorithm'}"
    ev.add(row)
    if result == "REJECTED":
        ev.cover(c.SURFACE_CANDIDATE_PQC, obs, subject="S2", scope="E02 pqc_signing refused")
    elif candidate_boot in {"BOOT_OK", "FAIL"}:
        boot = facts.get("E02", "boot_outcome")
        ev.cover(c.SURFACE_CANDIDATE_PQC, boot or obs, subject="S2", scope="E02 sign + boot")
    else:
        ev.gap(
            "GAP-E02-PQC-VERIFIER",
            "REQ-PQC-VERIFIER",
            "The pinned imgtool produced an ML-DSA signature, but no candidate boot "
            "(on-target verification) was observed",
            critical=True,
            requested="E02 candidate MCUboot verifies and boots the ML-DSA signed image",
        )
    return result


def _field_update_requirement(scope: str = "IN_SCOPE") -> dict[str, Any]:
    criterion = (
        "STEP-S0-S1 replaces MCUboot in the field; E11 must show the built configuration "
        "provides a bootloader update path. Unsupported blocks the transition."
    )
    if scope != "IN_SCOPE":
        criterion = (
            "Not applicable: this plan re-flashes MCUboot at a depot, so no field "
            "bootloader update path is required."
        )
    return c.requirement(
        "REQ-BL-FIELD-UPDATE",
        risk="UPDATE_ROLLBACK_RECOVERY",
        phases=["TRANSITION"],
        subject_types=["TRANSITION_STEP"],
        critical=True,
        criterion=criterion,
        rule="RULE-BL-FIELD-UPDATE",
        acquisition=["STATIC_CONFIG"],
        surfaces=[c.SURFACE_BL_UPDATE],
        scope=scope,
    )


def _pqc_verifier_requirement(to_scheme: str) -> dict[str, Any]:
    return c.requirement(
        "REQ-PQC-VERIFIER",
        risk="AUTHENTICITY_SIGNATURE",
        phases=["TARGET"],
        critical=True,
        criterion=(
            f"The pinned MCUboot tooling produces a {to_scheme} signed image and the candidate "
            "bootloader verifies it (E02)"
        ),
        rule="RULE-PQC-VERIFIER",
        acquisition=["SIGN_TOOL", "EMULATED"],
        surfaces=[c.SURFACE_CANDIDATE_PQC],
    )


__all__ = ["ADAPTER_NAME", "build_mcuboot_v1_2_assessment"]
