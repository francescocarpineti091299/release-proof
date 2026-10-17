"""wolfboot_v1_2 adapter: verdicts derived from contract V1.2 on synthetic live facts."""

from __future__ import annotations

import copy
import random

import pytest
from adapter_facts import CREATED_AT, REMOVE, RUN_ID, WOLFBOOT_FACTS

from releaseproof.adapters import get_adapter
from releaseproof.contracts.services import AdapterError
from releaseproof.core.assurance.service import evaluate
from releaseproof.core.canonical.service import compute_canonical_hash
from releaseproof.core.golden.baseline import verify_baseline_golden, verify_signer_bound_golden
from releaseproof.core.validation.service import validate_assessment

DEFAULT = "bootloader_self_update"
FIELD = "field_service_reflash"
HYBRID = "staged_hybrid_dual_signature"


def _assess(profile, run, plan_id=DEFAULT, *, run_id=RUN_ID, evidence_run_id=RUN_ID):
    adapter = get_adapter(profile.assessment_adapter)
    return adapter(
        profile=profile,
        change=profile.changes[0],
        plan_id=plan_id,
        run_id=run_id,
        evidence_run_id=evidence_run_id,
        created_at=CREATED_AT,
        **run.kwargs(),
    )


def _evaluate(profile, run, plan_id=DEFAULT, **kw):
    assessment = _assess(profile, run, plan_id, **kw)
    validation = validate_assessment(assessment)
    assert validation.ready, validation.errors
    result = evaluate(assessment)
    assert result.lifecycle == "COMPLETED", result.errors
    return assessment, result


def _req(result, req_id, phase=None):
    rows = [
        r
        for r in result.requirement_evaluation_results
        if r["requirement_id"] == req_id and (phase is None or r["phase"] == phase)
    ]
    assert rows, req_id
    return rows


def _inv(result, inv_id, phase="TRANSITION"):
    rows = [
        r
        for r in result.invariant_evaluation_results
        if r["invariant_id"] == inv_id and r["phase"] == phase
    ]
    assert len(rows) == 1, inv_id
    return rows[0]


def _states(rows):
    return {r["state"] for r in rows}


def _policy(assessment):
    return assessment["candidate_state"]["authorization_path_states"]["fw-boot"]["policy"]


FIXTURES = {
    "default": ({}, {}, DEFAULT),
    "default+p01": ({}, {"p01": "REJECT"}, DEFAULT),
    "default-no-e01": ({("E01", "boot_outcome"): REMOVE}, {}, DEFAULT),
    "default-e02-fail": ({("E02", "boot_outcome"): "FAIL"}, {}, DEFAULT),
    "default-e03-accept": ({("E03", "auth_negative"): "ACCEPT"}, {}, DEFAULT),
    "default-no-e05": ({("E05", "layout_fit"): REMOVE}, {"p01": "REJECT"}, DEFAULT),
    "default-e11-unknown": ({("E11", "bootloader_field_update"): "UNKNOWN"}, {}, DEFAULT),
    "field": ({}, {"p01": "REJECT"}, FIELD),
    "hybrid-build-failed": ({}, {"o05": "BUILD_FAILED"}, HYBRID),
    "hybrid-no-o05": ({}, {}, HYBRID),
    "empty-run": ({key: REMOVE for key in WOLFBOOT_FACTS}, {}, DEFAULT),
}


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_fixture_is_ready_and_completed(name, wolfboot_profile, wolfboot_run):
    overrides, optional, plan = FIXTURES[name]
    assessment, result = _evaluate(wolfboot_profile, wolfboot_run(overrides, **optional), plan)
    assert assessment["lifecycle"] == "READY"
    assert assessment["contract_version"] == "1.2"
    assert assessment["assessment_id"] == f"RP-ASSESS-{RUN_ID}"
    assert result.migration_verdict is not None
    assert result.migration_verdict != "COMPATIBLE"  # I4 is never observed by this runner


def test_default_plan_e11_unsupported_blocks_transition(wolfboot_profile, wolfboot_run):
    _, result = _evaluate(wolfboot_profile, wolfboot_run())
    rows = _req(result, "REQ-BOOT-S0S1")
    assert _states(rows) == {"VIOLATED"}
    assert all(r["evidence_refs"] == ["EV-E11-SELF-UPDATE"] for r in rows)
    assert result.transition_verdict == "INCOMPATIBLE"
    assert result.migration_verdict == "INCOMPATIBLE"
    # T1 blocks the transition, not the candidate.
    assert result.candidate_verdict == "INDETERMINATE"
    assert _states(_req(result, "REQ-LAYOUT")) == {"SATISFIED"}
    assert _states(_req(result, "REQ-AUTH-NEGATIVE")) == {"SATISFIED"}
    assert _inv(result, "INV-I1")["state"] == "SATISFIED"
    assert _inv(result, "INV-I4")["state"] == "UNKNOWN"


def test_p01_reject_vs_missing_changes_candidate(wolfboot_profile, wolfboot_run):
    without, r_without = _evaluate(wolfboot_profile, wolfboot_run())
    with_p01, r_with = _evaluate(wolfboot_profile, wolfboot_run(p01="REJECT"))

    assert without["candidate_state"]["authorization_path_states"]["fw-boot"] == {
        "policy": "UNKNOWN",
        "accepted_schemes": ["ML_DSA_87"],
    }
    assert with_p01["candidate_state"]["authorization_path_states"]["fw-boot"] == {
        "policy": "PQC_ONLY",
        "accepted_schemes": ["ML_DSA_87"],
    }
    assert _inv(r_without, "INV-I3", "TARGET")["state"] == "UNKNOWN"
    assert _inv(r_without, "INV-I3", "TARGET")["gap_refs"] == ["GAP-P01-AUTH-POLICY"]
    assert _inv(r_with, "INV-I3", "TARGET")["state"] == "SATISFIED"
    assert r_without.candidate_verdict == "INDETERMINATE"
    assert r_with.candidate_verdict == "COMPATIBLE"
    assert r_with.transition_verdict == "INCOMPATIBLE"


def test_p01_accept_does_not_derive_a_policy(wolfboot_profile, wolfboot_run):
    assessment, result = _evaluate(wolfboot_profile, wolfboot_run(p01="ACCEPT"))
    assert _policy(assessment) == "UNKNOWN"
    assert _inv(result, "INV-I3", "TARGET")["state"] == "UNKNOWN"
    assert result.candidate_verdict == "INDETERMINATE"


def test_p01_unknown_value_is_not_a_reject(wolfboot_profile, wolfboot_run):
    assessment, result = _evaluate(wolfboot_profile, wolfboot_run(p01="UNKNOWN"))
    row = next(e for e in assessment["evidence"] if e["id"] == "EV-P01-CLASSICAL-REJECT")
    assert row["authority_context"] == "NOT_OBSERVED"
    assert _policy(assessment) == "UNKNOWN"
    assert result.candidate_verdict == "INDETERMINATE"


def test_missing_e01_never_compatible(wolfboot_profile, wolfboot_run):
    # Best case otherwise: self-update supported, candidate policy measured.
    run = wolfboot_run(
        {("E01", "boot_outcome"): REMOVE, ("E11", "bootloader_field_update"): "SUPPORTED"},
        p01="REJECT",
    )
    assessment, result = _evaluate(wolfboot_profile, run)
    i1 = _inv(result, "INV-I1")
    assert i1["state"] == "UNKNOWN"
    assert "GAP-E01-BOOT" in i1["gap_refs"]
    placeholder = next(e for e in assessment["evidence"] if e["id"] == "EV-E01-BOOT")
    assert placeholder["value"] == "UNKNOWN" and "run_id" not in placeholder
    assert result.transition_verdict != "COMPATIBLE"
    assert result.migration_verdict != "COMPATIBLE"
    assert _states(_req(result, "REQ-BOOT-S0S1")) == {"SATISFIED"}


def test_e01_failure_violates_i1_without_contaminating_candidate(wolfboot_profile, wolfboot_run):
    _, result = _evaluate(
        wolfboot_profile, wolfboot_run({("E01", "boot_outcome"): "FAIL"}, p01="REJECT")
    )
    assert _inv(result, "INV-I1")["state"] == "VIOLATED"
    assert result.transition_verdict == "INCOMPATIBLE"
    assert _states(_req(result, "REQ-CANDIDATE-BOOT")) == {"SATISFIED"}
    assert result.candidate_verdict == "COMPATIBLE"


def test_e02_failure_makes_candidate_incompatible(wolfboot_profile, wolfboot_run):
    _, result = _evaluate(
        wolfboot_profile, wolfboot_run({("E02", "boot_outcome"): "FAIL"}, p01="REJECT")
    )
    rows = _req(result, "REQ-CANDIDATE-BOOT")
    assert _states(rows) == {"VIOLATED"}
    assert rows[0]["evidence_refs"] == ["EV-E02-BOOT"]
    assert result.candidate_verdict == "INCOMPATIBLE"
    assert _inv(result, "INV-I1")["state"] == "VIOLATED"


def test_missing_e02_keeps_candidate_open(wolfboot_profile, wolfboot_run):
    _, result = _evaluate(
        wolfboot_profile, wolfboot_run({("E02", "boot_outcome"): REMOVE}, p01="REJECT")
    )
    rows = _req(result, "REQ-CANDIDATE-BOOT")
    assert _states(rows) == {"UNKNOWN"}
    assert rows[0]["gap_refs"] == ["GAP-E02-CANDIDATE-BOOT"]
    assert result.candidate_verdict == "INDETERMINATE"
    assert _inv(result, "INV-I1")["state"] == "UNKNOWN"


@pytest.mark.parametrize("value", [REMOVE, "UNKNOWN"])
def test_missing_e11_is_unknown_not_satisfied(value, wolfboot_profile, wolfboot_run):
    _, result = _evaluate(
        wolfboot_profile, wolfboot_run({("E11", "bootloader_field_update"): value})
    )
    rows = _req(result, "REQ-BOOT-S0S1")
    assert _states(rows) == {"UNKNOWN"}
    assert all(r["gap_refs"] == ["GAP-E11-SELF-UPDATE"] for r in rows)
    assert result.transition_verdict == "INDETERMINATE"


def test_e11_supported_satisfies_self_update(wolfboot_profile, wolfboot_run):
    assessment, result = _evaluate(
        wolfboot_profile, wolfboot_run({("E11", "bootloader_field_update"): "SUPPORTED"})
    )
    assert _states(_req(result, "REQ-BOOT-S0S1")) == {"SATISFIED"}
    assert assessment["platform_model"]["components"][0]["mutability"] == "UPDATABLE"
    # Still not COMPATIBLE: I2 and I4 are not observed.
    assert result.transition_verdict == "INDETERMINATE"


def test_missing_layout_is_unknown_not_satisfied(wolfboot_profile, wolfboot_run):
    _, result = _evaluate(
        wolfboot_profile, wolfboot_run({("E05", "layout_fit"): REMOVE}, p01="REJECT")
    )
    rows = _req(result, "REQ-LAYOUT")
    assert _states(rows) == {"UNKNOWN"}
    assert rows[0]["gap_refs"] == ["GAP-E05-LAYOUT"]
    assert result.candidate_verdict == "INDETERMINATE"


def test_oversized_layout_violates(wolfboot_profile, wolfboot_run):
    run = wolfboot_run(
        {("E05", "layout_fit"): {"signed_artifact_size": 300000, "boot_slot_capacity": 262144}},
        p01="REJECT",
    )
    _, result = _evaluate(wolfboot_profile, run)
    assert _states(_req(result, "REQ-LAYOUT", "TARGET")) == {"VIOLATED"}
    assert result.candidate_verdict == "INCOMPATIBLE"


def test_inconsistent_capacity_is_not_covered(wolfboot_profile, wolfboot_run):
    run = wolfboot_run(
        {("E05", "layout_fit"): {"signed_artifact_size": 12876, "boot_slot_capacity": 131072}},
        p01="REJECT",
    )
    assessment, result = _evaluate(wolfboot_profile, run)
    gap = next(g for g in assessment["evidence_gaps"] if g["gap_id"] == "GAP-E05-LAYOUT")
    assert gap["gap_type"] == "INCONSISTENT_FACTS"
    assert _states(_req(result, "REQ-LAYOUT")) == {"UNKNOWN"}


def test_e03_accept_violates_auth_negative(wolfboot_profile, wolfboot_run):
    _, result = _evaluate(wolfboot_profile, wolfboot_run({("E03", "auth_negative"): "ACCEPT"}))
    rows = _req(result, "REQ-AUTH-NEGATIVE")
    assert _states(rows) == {"VIOLATED"}
    assert rows[0]["evidence_refs"] == ["EV-E03-PANIC"]
    assert result.transition_verdict == "INCOMPATIBLE"


def test_missing_e03_is_gap_not_incomplete(wolfboot_profile, wolfboot_run):
    _, result = _evaluate(wolfboot_profile, wolfboot_run({("E03", "auth_negative"): REMOVE}))
    rows = _req(result, "REQ-AUTH-NEGATIVE")
    assert _states(rows) == {"UNKNOWN"}
    assert rows[0]["gap_refs"] == ["GAP-E03-AUTH-NEGATIVE"]


def test_trust_chain_is_merged_with_live_ids(wolfboot_profile, wolfboot_run):
    _, result = _evaluate(wolfboot_profile, wolfboot_run())
    node_ids = {n["id"] for n in result.explanation_graph["nodes"]}
    assert {"TC-bootloader", "TC-signed_image", "TC-update_path", "TC-recovery"} <= node_ids
    edge = {
        "from": "TC-update_path",
        "to": "EV-E11-SELF-UPDATE",
        "relation": "SUPPORTED_BY_EVIDENCE",
    }
    assert edge in result.explanation_graph["edges"]


def test_evidence_is_live_not_freeze(wolfboot_profile, wolfboot_run):
    assessment = _assess(wolfboot_profile, wolfboot_run())
    by_id = {e["id"]: e for e in assessment["evidence"]}
    for row in assessment["evidence"]:
        if row["authority_context"] == "OBSERVED":
            assert row["run_id"] == RUN_ID
            assert row["content_hash"].startswith("sha256:") and len(row["content_hash"]) == 71
            assert row["artifact_refs"]
    assert by_id["EV-E05-LAYOUT-G2"]["value"] == {
        "signed_artifact_size": 12876,
        "boot_slot_capacity": 262144,
    }
    assert by_id["EV-LAYOUT-PARTITION"]["test_id"] == "D01"
    assert by_id["EV-PIN-WOLFBOOT"]["value"] == "4c79eee999b7083743811f37928322fe78b9fdb1"
    assert by_id["EV-E12-WINDOW"]["acquisition_mode"] == "UNOBSERVED"
    assert by_id["EV-X01-CROSS-UPDATE"]["value"] == "REJECTED"
    assert "EV-T3-DUAL-BUILD" not in by_id and "EV-APP-UPDATE-SCRIPT" not in by_id


def test_empty_run_has_no_boot_ok(wolfboot_profile, wolfboot_run):
    assessment, result = _evaluate(
        wolfboot_profile, wolfboot_run({k: REMOVE for k in WOLFBOOT_FACTS})
    )
    assert not any(e.get("value") == "BOOT_OK" for e in assessment["evidence"])
    assert result.candidate_verdict == "INDETERMINATE"
    assert result.transition_verdict == "INDETERMINATE"
    satisfied = [
        r["requirement_id"]
        for r in result.requirement_evaluation_results
        if r["state"] == "SATISFIED"
    ]
    assert satisfied == []


def test_field_service_removes_self_update_blocker(wolfboot_profile, wolfboot_run):
    assessment, result = _evaluate(wolfboot_profile, wolfboot_run(p01="REJECT"), FIELD)
    assert not [
        r for r in result.requirement_evaluation_results if r["requirement_id"] == "REQ-BOOT-S0S1"
    ]
    req = next(r for r in assessment["profile"]["requirements"] if r["id"] == "REQ-BOOT-S0S1")
    assert req["scope_status"] == "NOT_APPLICABLE"
    step = assessment["transition_plan"]["steps"][0]
    assert step["actions"][0]["parameters"]["mechanism"] == "field_service_reflash"
    assert step["preconditions"][0]["condition_id"] == "COND-MAINTENANCE-WINDOW"
    assert assessment["observed_recovery_mode"] == "FIELD_SERVICE"
    declaration = next(e for e in assessment["evidence"] if e["id"] == "EV-SCENARIO-RECOVERY")
    assert declaration["evidence_kind"] == "DECLARATION"

    assert _states(_req(result, "REQ-MAINTENANCE-WINDOW")) == {"OPEN_CONDITION"}
    assert _inv(result, "INV-I2")["state"] == "SATISFIED"
    assert _inv(result, "INV-I4")["state"] == "UNKNOWN"
    assert result.conditions == [
        {
            "condition_id": "COND-MAINTENANCE-WINDOW",
            "step_id": "STEP-S0-S1",
            "requirement_id": "REQ-MAINTENANCE-WINDOW",
            "allowed_by_profile": True,
        }
    ]
    # Unknown critical (I4) outranks the open condition: INDETERMINATE, not CONDITIONAL.
    assert result.transition_verdict == "INDETERMINATE"
    assert result.candidate_verdict == "COMPATIBLE"


def test_hybrid_build_failed_is_incompatible(wolfboot_profile, wolfboot_run):
    assessment, result = _evaluate(wolfboot_profile, wolfboot_run(o05="BUILD_FAILED"), HYBRID)
    rows = _req(result, "REQ-HYBRID-BUILD")
    assert _states(rows) == {"VIOLATED"}
    assert rows[0]["evidence_refs"] == ["EV-O05-DUAL-BUILD"]
    assert result.transition_verdict == "INCOMPATIBLE"
    s1 = assessment["transition_plan"]["states"][1]
    assert s1["authorization_path_states"]["fw-boot"] == {
        "policy": "UNKNOWN",
        "accepted_schemes": ["ECDSA_P256", "ML_DSA_87"],
    }
    assert s1["components"][0]["configuration"]["sign_secondary"] == "ML_DSA"


def test_hybrid_without_o05_is_unknown(wolfboot_profile, wolfboot_run):
    _, result = _evaluate(
        wolfboot_profile,
        wolfboot_run({("E11", "bootloader_field_update"): "SUPPORTED"}),
        HYBRID,
    )
    rows = _req(result, "REQ-HYBRID-BUILD")
    assert _states(rows) == {"UNKNOWN"}
    assert rows[0]["gap_refs"] == ["GAP-O05-DUAL-BUILD"]
    assert result.transition_verdict == "INDETERMINATE"


@pytest.mark.parametrize(
    ("outcome", "expected"), [("FAIL", "VIOLATED"), ("INCONCLUSIVE", "UNKNOWN")]
)
def test_hybrid_built_not_booted_needs_a_failed_boot(
    outcome, expected, wolfboot_profile, wolfboot_run
):
    run = wolfboot_run(o05="BUILT_NOT_BOOTED", outcomes={"O05": outcome})
    _, result = _evaluate(wolfboot_profile, run, HYBRID)
    assert _states(_req(result, "REQ-HYBRID-BUILD")) == {expected}


def test_unknown_plan_is_refused(wolfboot_profile, wolfboot_run):
    with pytest.raises(AdapterError, match="unknown plan"):
        _assess(wolfboot_profile, wolfboot_run(), "firmware_only_yolo")


def test_wrong_family_is_refused(mcuboot_profile, wolfboot_run):
    adapter = get_adapter("wolfboot_v1_2")
    with pytest.raises(AdapterError, match="mcuboot profile"):
        adapter(
            profile=mcuboot_profile,
            change=mcuboot_profile.changes[0],
            plan_id="mcuboot_field_update",
            run_id=RUN_ID,
            evidence_run_id=RUN_ID,
            created_at=CREATED_AT,
            **wolfboot_run().kwargs(),
        )


def test_unknown_adapter_name():
    with pytest.raises(AdapterError):
        get_adapter("evolus_v9")


def test_pin_mismatch_is_refused(wolfboot_profile, wolfboot_run):
    run = wolfboot_run({("D01", "bootloader_commit"): "0" * 40})
    with pytest.raises(AdapterError, match="profile pin"):
        _assess(wolfboot_profile, run)


def test_conflicting_duplicate_observations_are_refused(wolfboot_profile, wolfboot_run):
    run = wolfboot_run()
    dup = run.observations[0].model_copy(
        update={"observation_id": "OBS-ZZ-dup", "value": "deadbeef" * 5}
    )
    run.observations.append(dup)
    with pytest.raises(AdapterError, match="conflicting"):
        _assess(wolfboot_profile, run)


def test_ai_proposal_observations_are_not_facts(wolfboot_profile, wolfboot_run):
    run = wolfboot_run({("E11", "bootloader_field_update"): REMOVE})
    template = next(o for o in run.observations if o.test_id == "E03")
    run.observations.append(
        template.model_copy(
            update={
                "observation_id": "OBS-E11-ai",
                "test_id": "E11",
                "fact": "bootloader_field_update",
                "value": "SUPPORTED",
                "origin": "AI_PROPOSAL",
                "acquisition_mode": "SOURCE_INSPECTION",
            }
        )
    )
    _, result = _evaluate(wolfboot_profile, run)
    assert _states(_req(result, "REQ-BOOT-S0S1")) == {"UNKNOWN"}


def test_same_inputs_same_canonical_hash(wolfboot_profile, wolfboot_run):
    run = wolfboot_run(p01="REJECT")
    first = evaluate(_assess(wolfboot_profile, run))
    shuffled = copy.deepcopy(run)
    rng = random.Random(7)
    rng.shuffle(shuffled.observations)
    rng.shuffle(shuffled.artifacts)
    rng.shuffle(shuffled.test_results)
    second = evaluate(_assess(wolfboot_profile, shuffled))
    assert first.canonical_hash == second.canonical_hash
    assert _assess(wolfboot_profile, run) == _assess(wolfboot_profile, shuffled)


def test_snapshot_hashes_follow_artifacts(wolfboot_profile, wolfboot_run):
    a = _assess(wolfboot_profile, wolfboot_run())
    b = _assess(wolfboot_profile, wolfboot_run(salt="-rebuild"))
    for assessment in (a, b):
        final = assessment["transition_plan"]["states"][-1]
        assert final["snapshot_hash"] == assessment["candidate_state"]["snapshot_hash"]
        assert assessment["deployed_state"] == assessment["transition_plan"]["states"][0]
        hashes = [s["snapshot_hash"] for s in assessment["transition_plan"]["states"]]
        assert len(set(hashes)) == 3
    assert a["candidate_state"]["snapshot_hash"] != b["candidate_state"]["snapshot_hash"]
    # The result hash covers verdicts and graph only; artifact digests live in the assessment.
    assert compute_canonical_hash(a) != compute_canonical_hash(b)
    assert evaluate(a).canonical_hash == evaluate(b).canonical_hash


def test_reevaluation_uses_parent_evidence_run(wolfboot_profile, wolfboot_run):
    parent = RUN_ID
    child = "RP-20261017T130000Z-0f0f0f"
    assessment, _ = _evaluate(
        wolfboot_profile, wolfboot_run(), FIELD, run_id=child, evidence_run_id=parent
    )
    assert assessment["assessment_id"] == f"RP-ASSESS-{child}"
    observed = [e for e in assessment["evidence"] if e["authority_context"] == "OBSERVED"]
    assert observed and {e["run_id"] for e in observed} == {parent}


def test_measurement_without_run_linkage_is_incomplete(wolfboot_profile, wolfboot_run):
    assessment = _assess(wolfboot_profile, wolfboot_run(p01="REJECT"))
    row = next(e for e in assessment["evidence"] if e["id"] == "EV-E05-LAYOUT-G2")
    del row["run_id"]
    result = evaluate(assessment)
    assert result.lifecycle == "INCOMPLETE"
    assert result.migration_verdict is None
    assert any("EV-E05-LAYOUT-G2" in err for err in result.errors)


def test_reference_freeze_golden_still_passes():
    assert verify_baseline_golden() == (True, None)
    assert verify_signer_bound_golden() == (True, None)
