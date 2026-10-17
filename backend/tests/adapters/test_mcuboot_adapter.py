"""mcuboot_v1_2 adapter: verdicts derived from contract V1.2 on synthetic live facts."""

from __future__ import annotations

import pytest
from adapter_facts import CREATED_AT, MCUBOOT_FACTS, REMOVE, RUN_ID

from releaseproof.adapters import get_adapter
from releaseproof.contracts.services import AdapterError
from releaseproof.core.assurance.service import evaluate
from releaseproof.core.canonical.service import compute_canonical_hash
from releaseproof.core.validation.service import validate_assessment

DEFAULT = "mcuboot_field_update"
DEPOT = "depot_reflash_mcuboot"

SIGN_OK = {"signing_result": "OK", "algorithm": "ML-DSA-65", "tool": "imgtool", "message": ""}
CANDIDATE_BOOT = {
    ("E02", "boot_outcome"): (
        "candidate_state", "BOOT_OK", "OBSERVED_EMULATION", "EMULATED", "e02-uart.log",
    ),
}


def _assess(profile, run, plan_id=DEFAULT):
    return get_adapter(profile.assessment_adapter)(
        profile=profile,
        change=profile.changes[0],
        plan_id=plan_id,
        run_id=RUN_ID,
        evidence_run_id=RUN_ID,
        created_at=CREATED_AT,
        **run.kwargs(),
    )


def _evaluate(profile, run, plan_id=DEFAULT):
    assessment = _assess(profile, run, plan_id)
    validation = validate_assessment(assessment)
    assert validation.ready, validation.errors
    result = evaluate(assessment)
    assert result.lifecycle == "COMPLETED", result.errors
    return assessment, result


def _states(result, req_id):
    rows = [r for r in result.requirement_evaluation_results if r["requirement_id"] == req_id]
    assert rows, req_id
    return {r["state"] for r in rows}, rows


FIXTURES = {
    "default": ({}, None, DEFAULT),
    "depot": ({}, None, DEPOT),
    "e03-accept": ({("E03", "auth_negative"): "ACCEPT"}, None, DEFAULT),
    "sign-ok-no-boot": ({("E02", "pqc_signing"): SIGN_OK}, None, DEFAULT),
    "sign-ok-boot": ({("E02", "pqc_signing"): SIGN_OK}, CANDIDATE_BOOT, DEFAULT),
    "no-e11": ({("E11", "bootloader_field_update"): REMOVE}, None, DEFAULT),
    "empty-run": ({key: REMOVE for key in MCUBOOT_FACTS}, None, DEFAULT),
}


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_fixture_is_ready_and_completed(name, mcuboot_profile, mcuboot_run):
    overrides, extra, plan = FIXTURES[name]
    assessment, result = _evaluate(mcuboot_profile, mcuboot_run(overrides, extra=extra), plan)
    assert assessment["lifecycle"] == "READY"
    assert result.migration_verdict not in (None, "COMPATIBLE")


def test_pqc_signing_refused_makes_candidate_incompatible(mcuboot_profile, mcuboot_run):
    assessment, result = _evaluate(mcuboot_profile, mcuboot_run())
    states, rows = _states(result, "REQ-PQC-VERIFIER")
    assert states == {"VIOLATED"}
    assert rows[0]["evidence_refs"] == ["EV-E02-PQC-SIGN"]
    assert result.candidate_verdict == "INCOMPATIBLE"
    row = next(e for e in assessment["evidence"] if e["id"] == "EV-E02-PQC-SIGN")
    assert row["value"] == "UNSUPPORTED" and row["acquisition_mode"] == "SIGN_TOOL"
    assert row["source_identity"] == "imgtool 2.2.0:ML-DSA-65"
    # E11 UNSUPPORTED blocks the field replacement of MCUboot.
    states, _ = _states(result, "REQ-BL-FIELD-UPDATE")
    assert states == {"VIOLATED"}
    assert result.transition_verdict == "INCOMPATIBLE"
    assert assessment["platform_model"]["components"][0]["mutability"] == "NOT_FIELD_UPDATABLE"
    path = assessment["candidate_state"]["authorization_path_states"]["fw-boot"]
    assert path["policy"] == "UNKNOWN"


def test_e03_accept_violates_auth_negative(mcuboot_profile, mcuboot_run):
    _, result = _evaluate(mcuboot_profile, mcuboot_run({("E03", "auth_negative"): "ACCEPT"}))
    states, rows = _states(result, "REQ-AUTH-NEGATIVE")
    assert states == {"VIOLATED"}
    assert rows[0]["evidence_refs"] == ["EV-E03-PANIC"]


def test_signing_ok_without_verification_is_not_satisfied(mcuboot_profile, mcuboot_run):
    _, result = _evaluate(mcuboot_profile, mcuboot_run({("E02", "pqc_signing"): SIGN_OK}))
    states, rows = _states(result, "REQ-PQC-VERIFIER")
    assert states == {"UNKNOWN"}
    assert rows[0]["gap_refs"] == ["GAP-E02-PQC-VERIFIER"]
    assert result.candidate_verdict == "INDETERMINATE"


def test_signing_ok_and_candidate_boot_satisfies_verifier(mcuboot_profile, mcuboot_run):
    run = mcuboot_run({("E02", "pqc_signing"): SIGN_OK}, extra=CANDIDATE_BOOT)
    _, result = _evaluate(mcuboot_profile, run)
    states, _ = _states(result, "REQ-PQC-VERIFIER")
    assert states == {"SATISFIED"}
    # Candidate layout and policy are still unmeasured: never COMPATIBLE.
    assert result.candidate_verdict == "INDETERMINATE"


def test_deployed_layout_does_not_cover_candidate(mcuboot_profile, mcuboot_run):
    assessment, result = _evaluate(mcuboot_profile, mcuboot_run())
    states, rows = _states(result, "REQ-LAYOUT")
    assert states == {"UNKNOWN"}
    assert rows[0]["gap_refs"] == ["GAP-E05-CANDIDATE-LAYOUT"]
    ids = {e["id"] for e in assessment["evidence"]}
    assert "EV-E05-LAYOUT-DEPLOYED" in ids and "EV-E05-LAYOUT-G2" not in ids


def test_missing_e11_is_not_satisfied_by_partition_rows(mcuboot_profile, mcuboot_run):
    _, result = _evaluate(
        mcuboot_profile, mcuboot_run({("E11", "bootloader_field_update"): REMOVE})
    )
    states, rows = _states(result, "REQ-BL-FIELD-UPDATE")
    assert states == {"UNKNOWN"}
    assert rows[0]["gap_refs"] == ["GAP-E11-BL-FIELD-UPDATE"]


def test_depot_reflash_removes_field_update_not_pqc_blocker(mcuboot_profile, mcuboot_run):
    assessment, result = _evaluate(mcuboot_profile, mcuboot_run(), DEPOT)
    assert not [
        r
        for r in result.requirement_evaluation_results
        if r["requirement_id"] == "REQ-BL-FIELD-UPDATE"
    ]
    assert assessment["observed_recovery_mode"] == "DEPOT_PHYSICAL_REFLASH"
    step = assessment["transition_plan"]["steps"][0]
    assert step["actions"][0]["parameters"]["mechanism"] == "depot_physical_reflash"
    states, _ = _states(result, "REQ-MAINTENANCE-WINDOW")
    assert states == {"OPEN_CONDITION"}
    i2 = next(r for r in result.invariant_evaluation_results if r["invariant_id"] == "INV-I2")
    assert i2["state"] == "SATISFIED"
    assert result.transition_verdict == "INDETERMINATE"
    assert result.candidate_verdict == "INCOMPATIBLE"
    assert result.migration_verdict == "INCOMPATIBLE"


@pytest.mark.parametrize("plan_id", ["switch_to_wolfboot_depot", "mcuboot_lms_branch"])
def test_external_validation_plans_are_not_evaluable(plan_id, mcuboot_profile, mcuboot_run):
    with pytest.raises(AdapterError, match="REQUIRES_EXTERNAL_VALIDATION"):
        _assess(mcuboot_profile, mcuboot_run(), plan_id)


def test_unknown_plan_is_refused(mcuboot_profile, mcuboot_run):
    with pytest.raises(AdapterError, match="unknown plan"):
        _assess(mcuboot_profile, mcuboot_run(), "bootloader_self_update")


def test_deterministic(mcuboot_profile, mcuboot_run):
    first = _assess(mcuboot_profile, mcuboot_run())
    second = _assess(mcuboot_profile, mcuboot_run())
    assert first == second
    assert evaluate(first).canonical_hash == evaluate(second).canonical_hash
    rebuilt = _assess(mcuboot_profile, mcuboot_run(salt="x"))
    assert compute_canonical_hash(rebuilt) != compute_canonical_hash(first)
