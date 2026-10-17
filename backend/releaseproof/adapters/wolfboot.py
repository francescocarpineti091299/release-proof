"""wolfBoot (nRF52840) live facts → V1.2 assessment (adapter ``wolfboot_v1_2``).

Structure follows the reference freeze builder (``core/projection/wp0.py``): the same
requirements family, platform, S0 → S1 → S2 plan, derived effects and ruleset, and the same
evidence ids where the meaning matches (EV-E01-BOOT, EV-E02-BOOT, EV-E03-PANIC,
EV-E05-LAYOUT-G2, EV-LAYOUT-PARTITION, EV-E04-HEADER-SPAN, EV-E11-SELF-UPDATE,
EV-PIN-WOLFBOOT, EV-E12-WINDOW, EV-BOOTLOADER-SIZE-G1/G2) so ``merge_trust_chain`` and UI
labels keep working. Every value comes from a live observation; nothing is copied from the
freeze. See ``_common`` for the gating rules that keep missing facts out of SATISFIED.

Requirement map (requirement ← decisive fact, coverage surface, group acquisition):

* REQ-LAYOUT (TARGET+TRANSITION, critical) ← E05 ``layout_fit`` on the candidate, with the
  slot capacity from D01 ``partition_layout`` (or E05 when D01 is absent); RULE-LAYOUT/LEQ.
  Not covered when sizes are missing or the two capacity sources disagree.
* REQ-CANDIDATE-BOOT (TARGET, critical) ← E02 ``boot_outcome``. Without it a candidate
  that never booted could be COMPATIBLE.
* REQ-BOOT-S0S1 (TRANSITION/steps, critical) ← E11 ``bootloader_field_update``;
  SOURCE_INSPECTION only (the freeze group also accepted EMULATED, which would let any
  emulated failure violate it and any emulated row satisfy it).
* REQ-AUTH-NEGATIVE (TRANSITION/plan, critical) ← E03 via RULE-AUTH-NEGATIVE (D05).
* REQ-RAM (TARGET, non-critical) ← never measured; stays UNKNOWN with GAP-E07-RAM.
* REQ-HYBRID-BUILD (staged hybrid plan only) ← O05 ``dual_signature_build``; BUILD only.
* REQ-MAINTENANCE-WINDOW (field-service plan only) ← admitted precondition, OPEN_CONDITION.

Informational rows (no requirement): D01 pins, E01/E02 sizes/version/key, E04, E08, X01,
P01. X01/E08/P01 keep their raw CAPS values, which are not generic failure tokens.

Candidate policy (INV-I3): ``PQC_ONLY`` only when P01 observed REJECT (the candidate
bootloader refused an ECDSA image); otherwise ``UNKNOWN``. S1 carries the same bootloader
as S2 in the bootloader-first plans, so it gets the same policy. The hybrid S1 policy stays
``UNKNOWN``: AND/OR is not observable from O05 (V12-12, no invented hybrid).
"""

from __future__ import annotations

import copy
from typing import Any

from releaseproof.adapters import _common as c
from releaseproof.contracts.profile import ChangeScenario, Profile
from releaseproof.contracts.runner import ArtifactEvent, Observation, TestResultEvent
from releaseproof.contracts.services import AdapterError

ADAPTER_NAME = "wolfboot_v1_2"
FAMILY = "wolfboot"

MECH_FIELD_SERVICE = "field_service_reflash"
MECH_HYBRID = "hybrid_dual_signature"
_SUPPORTED_MECHANISMS = {MECH_FIELD_SERVICE, MECH_HYBRID}

_SCHEME_CONFIG: dict[str, dict[str, Any]] = {
    "ECDSA_P256": {"sign": "ECC256"},
    "ML_DSA_44": {"sign": "ML_DSA", "ml_dsa_level": 2},
    "ML_DSA_65": {"sign": "ML_DSA", "ml_dsa_level": 3},
    "ML_DSA_87": {"sign": "ML_DSA", "ml_dsa_level": 5},
}

_FIELD_UPDATE = {"SUPPORTED": "PASS", "UNSUPPORTED": "UNSUPPORTED"}
_AUTH_NEGATIVE = {"REJECT": "REJECT", "ACCEPT": "ACCEPT"}
_CROSS_UPDATE = {"REJECTED": "REJECTED", "APPLIED": "APPLIED"}
_CLASSICAL_ON_CANDIDATE = {"REJECT": "REJECT", "ACCEPT": "ACCEPT"}
_UPDATE = {"APPLIED": "APPLIED", "NOT_APPLIED": "NOT_APPLIED"}


def build_wolfboot_v1_2_assessment(
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
    """Project one wolfBoot LIVE run into a READY V1.2 assessment for ``plan_id``."""
    c.check_inputs(
        profile=profile,
        change=change,
        family=FAMILY,
        run_id=run_id,
        evidence_run_id=evidence_run_id,
        created_at=created_at,
    )
    mechanism = c.resolve_mechanism(change, plan_id, _SUPPORTED_MECHANISMS)
    from_cfg = _scheme(change.from_scheme)
    to_cfg = _scheme(change.to_scheme)

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
    e02_boot = facts.get("E02", "boot_outcome")
    if boots["E02"] in {"BOOT_OK", "FAIL"} and e02_boot is not None:
        ev.cover(c.SURFACE_CANDIDATE_BOOT, e02_boot, subject="S2", scope="E02 boot_outcome")
    else:
        ev.missing_gap(
            "GAP-E02-CANDIDATE-BOOT",
            "REQ-CANDIDATE-BOOT",
            "E02",
            "boot_outcome",
            critical=True,
            requested="E02 candidate ML-DSA image boots in emulation",
        )

    # ---------------------------------------------------------------- D01
    bl_commit = ev.add_identity_fact("EV-PIN-WOLFBOOT", "D01", "bootloader_commit")
    c.check_pin(bl_commit, profile.bootloader.commit, "wolfBoot")
    crypto = ev.add_identity_fact("EV-PIN-WOLFCRYPT", "D01", "crypto_commit")
    pinned_crypto = profile.toolchain.get("wolfcrypt_commit")
    if pinned_crypto:
        c.check_pin(crypto, pinned_crypto, "wolfCrypt")

    # ---------------------------------------------------------------- E11
    field_update = ev.add_enum_fact(
        "EV-E11-SELF-UPDATE", "E11", "bootloader_field_update", _FIELD_UPDATE
    )
    e11 = facts.get("E11", "bootloader_field_update")
    if field_update is not None and e11 is not None:
        ev.cover(c.SURFACE_BL_UPDATE, e11, subject="STEP-S0-S1", scope="E11 source inspection")

    # ---------------------------------------------------------------- E01 / E02 statics
    bl_g1 = ev.add_dict_fact("EV-BOOTLOADER-SIZE-G1", "E01", "bootloader_size_bytes")
    fw_g1 = ev.add_dict_fact("EV-E01-SIGNED-SIZE", "E01", "signed_image_size_bytes")
    key_g1 = ev.add_dict_fact("EV-E01-PUBKEY", "E01", "public_key_sha256")
    ev.add_scalar_fact("EV-E01-VERSION", "E01", "observed_version")
    bl_g2 = ev.add_dict_fact("EV-BOOTLOADER-SIZE-G2", "E02", "bootloader_size_bytes")
    fw_g2 = ev.add_dict_fact("EV-E02-SIGNED-SIZE", "E02", "signed_image_size_bytes")
    key_g2 = ev.add_dict_fact("EV-E02-PUBKEY", "E02", "public_key_sha256")
    ev.add_scalar_fact("EV-E02-VERSION", "E02", "observed_version")
    ev.add_enum_fact("EV-E08-UPDATE", "E08", "update_outcome", _UPDATE)

    # ---------------------------------------------------------------- E04 / E05 layout
    header = facts.get("E04", "image_header")
    if header is not None and isinstance(header.value, dict):
        ev.add(
            ev.observed(
                "EV-E04-HEADER-SPAN",
                header,
                {
                    "image_header_size_bytes": header.value.get("image_header_size_bytes"),
                    "header_span_measured_bytes": header.value.get("header_span_bytes"),
                },
            )
        )
    _layout(ev, facts)

    # ---------------------------------------------------------------- E03 / X01 / P01 / O05
    auth = ev.add_enum_fact("EV-E03-PANIC", "E03", "auth_negative", _AUTH_NEGATIVE)
    e03 = facts.get("E03", "auth_negative")
    if auth is not None and e03 is not None:
        ev.cover(c.SURFACE_VERIFIER_NEGATIVE, e03, subject="S0", scope="E03 tampered image")
    else:
        ev.missing_gap(
            "GAP-E03-AUTH-NEGATIVE",
            "REQ-AUTH-NEGATIVE",
            "E03",
            "auth_negative",
            critical=True,
            requested="E03 tampered image rejection observed on the deployed verifier",
        )
    ev.add_enum_fact("EV-X01-CROSS-UPDATE", "X01", "cross_update_outcome", _CROSS_UPDATE)
    p01 = ev.add_enum_fact(
        "EV-P01-CLASSICAL-REJECT", "P01", "classical_image_on_candidate", _CLASSICAL_ON_CANDIDATE
    )
    hybrid = _dual_build(ev, facts)
    c.e12_placeholder(ev)

    if field_update is None:
        ev.missing_gap(
            "GAP-E11-SELF-UPDATE",
            "REQ-BOOT-S0S1",
            "E11",
            "bootloader_field_update",
            critical=True,
            requested="E11 bootloader self-update capability on the pinned port",
        )

    # ---------------------------------------------------------------- policy
    if p01 == "REJECT":
        candidate_policy = {"policy": "PQC_ONLY", "accepted_schemes": [change.to_scheme]}
    else:
        candidate_policy = {"policy": "UNKNOWN", "accepted_schemes": [change.to_scheme]}
        reason = facts.why_missing("P01", "classical_image_on_candidate")
        if p01 == "ACCEPT":
            reason = "P01 observed the candidate bootloader ACCEPT an ECDSA image; none derived"
        ev.gap(
            "GAP-P01-AUTH-POLICY",
            "INV-I3",
            reason,
            critical=True,
            requested="P01 candidate bootloader rejects a classically signed image",
        )

    # ---------------------------------------------------------------- states
    s0_bl = _config(
        from_cfg, size=bl_g1, key=key_g1, sha=_sha(facts, "E01", "bootloader_size_bytes")
    )
    s0_fw = _config(from_cfg, image=fw_g1, sha=_sha(facts, "E01", "signed_image_size_bytes"))
    s2_bl = _config(
        to_cfg, size=bl_g2, key=key_g2, sha=_sha(facts, "E02", "bootloader_size_bytes")
    )
    s2_fw = _config(to_cfg, image=fw_g2, sha=_sha(facts, "E02", "signed_image_size_bytes"))
    classical = {"policy": "CLASSICAL_ONLY", "accepted_schemes": [change.from_scheme]}

    s0 = c.system_state("S0", bootloader=s0_bl, firmware=s0_fw, path_state=classical)
    s2 = c.system_state("S2", bootloader=s2_bl, firmware=s2_fw, path_state=candidate_policy)

    requirements = [
        c.layout_requirement(),
        _candidate_boot_requirement(),
        c.auth_negative_requirement(),
        c.ram_requirement(),
    ]
    observed_recovery = "UNKNOWN"
    allowed_preconditions: list[str] = []

    if mechanism == MECH_HYBRID:
        s1_bl = {**copy.deepcopy(from_cfg), **_secondary(to_cfg)}
        if hybrid is not None:
            s1_bl["dual_signature_build"] = facts.value("O05", "dual_signature_build")
        s1_fw = {"sign": f"{from_cfg['sign']}+{to_cfg['sign']}", "dual_signed": True}
        s1_path = {
            "policy": "UNKNOWN",
            "accepted_schemes": [change.from_scheme, change.to_scheme],
        }
        s1 = c.system_state("S1", bootloader=s1_bl, firmware=s1_fw, path_state=s1_path)
        steps = [
            {
                "step_id": "STEP-S0-S1",
                "from": "S0",
                "to": "S1",
                "actions": [
                    c.action(
                        "ACT-FIRMWARE-S0S1", "UPDATE_FIRMWARE", "firmware",
                        effects=[], signature="dual",
                    ),
                    c.action(
                        "ACT-BOOTLOADER-S0S1", "UPDATE_BOOTLOADER", "bootloader",
                        effects=["DE-AUTH-S1"], mechanism="bootloader_self_update",
                        target="hybrid_dual_signature",
                    ),
                ],
                "preconditions": [],
            },
            {
                "step_id": "STEP-S1-S2",
                "from": "S1",
                "to": "S2",
                "actions": [
                    c.action(
                        "ACT-BOOTLOADER-S1S2", "UPDATE_BOOTLOADER", "bootloader",
                        effects=["DE-AUTH-S2"], mechanism="bootloader_self_update",
                    ),
                    c.action(
                        "ACT-FIRMWARE-S1S2", "UPDATE_FIRMWARE", "firmware",
                        effects=["DE-AUTH-S2"],
                    ),
                ],
                "preconditions": [],
            },
        ]
        requirements.insert(1, _self_update_requirement())
        requirements.append(_hybrid_build_requirement())
        if hybrid is None:
            ev.missing_gap(
                "GAP-O05-DUAL-BUILD",
                "REQ-HYBRID-BUILD",
                "O05",
                "dual_signature_build",
                critical=True,
                requested="O05 dual-signature bootloader builds and boots on the pinned commit",
            )
    else:
        s1 = c.system_state("S1", bootloader=s2_bl, firmware=s0_fw, path_state=candidate_policy)
        bl_mechanism = (
            "bootloader_self_update" if mechanism == c.DEFAULT_PLAN else MECH_FIELD_SERVICE
        )
        steps = [
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
                        "ACT-FIRMWARE-S1S2", "UPDATE_FIRMWARE", "firmware",
                        effects=["DE-AUTH-S2"],
                    )
                ],
                "preconditions": [],
            },
        ]
        if mechanism == c.DEFAULT_PLAN:
            requirements.insert(1, _self_update_requirement())
        else:
            requirements.insert(1, _self_update_requirement(scope="NOT_APPLICABLE"))
            requirements.append(
                c.maintenance_requirement(
                    "Bootloader re-flash through the debug port happens in a controlled "
                    "field-service maintenance window without uncontrolled interruption"
                )
            )
            steps[0]["preconditions"] = [
                c.maintenance_precondition("Planned field-service maintenance window")
            ]
            allowed_preconditions = [c.COND_MAINTENANCE]
            observed_recovery = "FIELD_SERVICE"
            ev.add(
                c.recovery_declaration(
                    profile=profile, change=change, plan_id=plan_id, mode=observed_recovery
                )
            )
            c.maintenance_gap(ev)
            # E11 is not consulted by this plan; its gap would only be noise.
            ev.gaps = [g for g in ev.gaps if g["requirement_id"] != "REQ-BOOT-S0S1"]

    if observed_recovery == "UNKNOWN":
        ev.gap(
            "GAP-RECOVERY-MODE",
            "INV-I2",
            "Recovery after a failed over-the-air bootloader update was not observed",
            critical=True,
            requested="Observed recovery mode after an interrupted bootloader update",
        )
    c.standard_gaps(ev, include_e10=True)

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
            platform_id="PLATFORM-NRF52840-WOLFBOOT",
            version=profile.version,
            pin=f"version-pin:wolfboot-{pin[:12]}",
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


def _scheme(scheme: str) -> dict[str, Any]:
    try:
        return copy.deepcopy(_SCHEME_CONFIG[scheme])
    except KeyError as exc:
        raise AdapterError(f"wolfBoot adapter has no build mapping for scheme {scheme}") from exc


def _secondary(to_cfg: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"sign_secondary": to_cfg["sign"]}
    if "ml_dsa_level" in to_cfg:
        out["ml_dsa_level"] = to_cfg["ml_dsa_level"]
    return out


def _sha(facts: c.Facts, test_id: str, fact: str) -> str | None:
    return facts.artifact_sha(facts.get(test_id, fact))


def _config(
    scheme_cfg: dict[str, Any],
    *,
    size: Any = None,
    image: Any = None,
    key: Any = None,
    sha: str | None = None,
) -> dict[str, Any]:
    cfg = copy.deepcopy(scheme_cfg)
    if c.is_int(size):
        cfg["wolfboot_size_bytes"] = size
    if c.is_int(image):
        cfg["signed_image_size_bytes"] = image
    if isinstance(key, str):
        cfg["public_key_sha256"] = key
    if sha:
        cfg["artifact_sha256"] = sha
    return cfg


def _layout(ev: c.EvidenceSet, facts: c.Facts) -> None:
    """E05 rows for LEQ. Capacity: D01 pinned config, else the E05 measurement itself."""
    fit = facts.get("E05", "layout_fit")
    fit_value = fit.value if fit is not None and isinstance(fit.value, dict) else {}
    signed = fit_value.get("signed_artifact_size")
    e05_capacity = fit_value.get("boot_slot_capacity")
    partition = facts.get("D01", "partition_layout")
    layout = partition.value if partition is not None and isinstance(partition.value, dict) else {}
    d01_capacity = layout.get("partition_size_bytes")

    if fit is not None and fit_value and c.is_int(signed):
        value: dict[str, Any] = {"signed_artifact_size": signed}
        if c.is_int(e05_capacity):
            value["boot_slot_capacity"] = e05_capacity
        ev.add(ev.observed("EV-E05-LAYOUT-G2", fit, value))
    if partition is not None and c.is_int(d01_capacity):
        part_value = {k: v for k, v in layout.items() if k != "signed_artifact_size"}
        part_value["boot_slot_capacity"] = d01_capacity
        ev.add(ev.observed("EV-LAYOUT-PARTITION", partition, part_value))
    elif fit is not None and c.is_int(e05_capacity):
        ev.add(ev.observed("EV-LAYOUT-PARTITION", fit, {"boot_slot_capacity": e05_capacity}))

    capacities = {v for v in (d01_capacity, e05_capacity) if c.is_int(v)}
    decisive = (
        fit is not None
        and fit.subject == "candidate_state"
        and c.is_int(signed)
        and len(capacities) == 1
    )
    if decisive:
        ev.cover(c.SURFACE_BOOT_SLOT, fit, subject="S2", scope="E05 layout_fit")  # type: ignore[arg-type]
        return
    if len(capacities) > 1:
        reason = (
            f"Boot slot capacity disagrees between D01 ({d01_capacity}) and E05 ({e05_capacity})"
        )
        ev.gap(
            "GAP-E05-LAYOUT",
            "REQ-LAYOUT",
            reason,
            critical=True,
            requested="Consistent E05 signed size and boot slot capacity",
            gap_type="INCONSISTENT_FACTS",
        )
        return
    ev.missing_gap(
        "GAP-E05-LAYOUT",
        "REQ-LAYOUT",
        "E05",
        "layout_fit",
        critical=True,
        requested="E05 signed candidate image size and boot slot capacity",
    )


def _dual_build(ev: c.EvidenceSet, facts: c.Facts) -> str | None:
    """O05 → evidence value in the engine vocabulary.

    BUILD_FAILED: the dual-signature configuration does not build on the pinned commit →
    ``UNSUPPORTED``. BOOT_OK → ``PASS``. BUILT_NOT_BOOTED → ``FAIL`` only when the test
    result says the boot attempt failed; otherwise the boot was not established (UNKNOWN).
    """
    obs = facts.get("O05", "dual_signature_build")
    if obs is None:
        return None
    result = facts.result("O05")
    mapping = {"BUILD_FAILED": "UNSUPPORTED", "BOOT_OK": "PASS"}
    if result is not None and result.outcome.value == "FAIL":
        mapping["BUILT_NOT_BOOTED"] = "FAIL"
    value = ev.add_enum_fact("EV-O05-DUAL-BUILD", "O05", "dual_signature_build", mapping)
    if value is not None:
        ev.cover(c.SURFACE_HYBRID_BUILD, obs, subject="S1", scope="O05 dual-signature build")
    return value


def _self_update_requirement(scope: str = "IN_SCOPE") -> dict[str, Any]:
    criterion = (
        "STEP-S0-S1 replaces the bootloader over the air (bootloader self-update); E11 must "
        "show the pinned port supports it. Unsupported blocks the transition, not the candidate."
    )
    if scope != "IN_SCOPE":
        criterion = (
            "Not applicable: this plan re-flashes the bootloader through field service, "
            "so no over-the-air bootloader self-update is required."
        )
    return c.requirement(
        "REQ-BOOT-S0S1",
        risk="UPDATE_ROLLBACK_RECOVERY",
        phases=["TRANSITION"],
        subject_types=["TRANSITION_STEP"],
        critical=True,
        criterion=criterion,
        rule="RULE-BOOT-S0S1",
        acquisition=["SOURCE_INSPECTION"],
        surfaces=[c.SURFACE_BL_UPDATE],
        scope=scope,
    )


def _candidate_boot_requirement() -> dict[str, Any]:
    return c.requirement(
        "REQ-CANDIDATE-BOOT",
        risk="AUTHENTICITY_SIGNATURE",
        phases=["TARGET"],
        critical=True,
        criterion="Candidate bootloader verifies and boots the ML-DSA signed image (E02)",
        rule="RULE-CANDIDATE-BOOT",
        acquisition=["EMULATED"],
        surfaces=[c.SURFACE_CANDIDATE_BOOT],
    )


def _hybrid_build_requirement() -> dict[str, Any]:
    return c.requirement(
        "REQ-HYBRID-BUILD",
        risk="AUTHENTICITY_SIGNATURE",
        phases=["TRANSITION"],
        subject_types=["PLAN"],
        critical=True,
        criterion=(
            "The intermediate dual-signature bootloader (SIGN + SIGN_SECONDARY) builds and "
            "boots on the pinned commit (O05)"
        ),
        rule="RULE-HYBRID-BUILD",
        acquisition=["BUILD"],
        surfaces=[c.SURFACE_HYBRID_BUILD],
    )


__all__ = ["ADAPTER_NAME", "build_wolfboot_v1_2_assessment"]
