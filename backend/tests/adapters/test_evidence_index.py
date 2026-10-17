"""evidence_index: assessment evidence rows → API EvidenceView rows with artifact links."""

from __future__ import annotations

from adapter_facts import CREATED_AT, REMOVE, RUN_ID, mcuboot_run, wolfboot_run

from releaseproof.adapters import evidence_index, get_adapter
from releaseproof.contracts.api import EvidenceView
from releaseproof.profiles.registry import get_profile


def _assessment(profile_id, plan_id, run):
    profile = get_profile(profile_id)
    return get_adapter(profile.assessment_adapter)(
        profile=profile,
        change=profile.changes[0],
        plan_id=plan_id,
        run_id=RUN_ID,
        evidence_run_id=RUN_ID,
        created_at=CREATED_AT,
        **run.kwargs(),
    )


def test_rows_match_evidence_view_and_link_artifacts():
    run = wolfboot_run({("E01", "boot_outcome"): REMOVE}, p01="REJECT")
    assessment = _assessment("nrf52840-wolfboot-pqc", "field_service_reflash", run)
    rows = evidence_index(assessment, run.observations, run.artifacts)

    assert [r["id"] for r in rows] == [e["id"] for e in assessment["evidence"]]
    for row in rows:
        EvidenceView.model_validate(row)
    by_id = {r["id"]: r for r in rows}

    layout = by_id["EV-E05-LAYOUT-G2"]
    assert layout["origin"] == "MEASURED_TOOL"
    assert layout["locator"] == "e02-image_v1_signed.bin:L1-L4"
    [art] = layout["artifacts"]
    assert art["name"] == "e02-image_v1_signed.bin"
    assert art["url"] == f"/api/assessments/{RUN_ID}/artifacts/{art['artifact_id']}"
    sha = next(e for e in assessment["evidence"] if e["id"] == "EV-E05-LAYOUT-G2")["content_hash"]
    assert sha == f"sha256:{art['sha256']}"

    partition = by_id["EV-LAYOUT-PARTITION"]
    assert partition["test_id"] == "D01" and partition["artifacts"][0]["name"] == "nrf52840.config"

    assert by_id["EV-E03-PANIC"]["origin"] == "OBSERVED_EMULATION"
    assert by_id["EV-E01-BOOT"]["origin"] == "NOT_OBSERVED"
    assert by_id["EV-E01-BOOT"]["artifacts"] == [] and by_id["EV-E01-BOOT"]["run_id"] is None
    assert by_id["EV-E12-WINDOW"]["origin"] == "NOT_OBSERVED"
    assert by_id["EV-SCENARIO-RECOVERY"]["origin"] == "DECLARED"


def test_mcuboot_rows_and_dict_inputs():
    run = mcuboot_run()
    assessment = _assessment("nrf52840-mcuboot-pqc", "mcuboot_field_update", run)
    rows = evidence_index(
        assessment,
        [o.model_dump(mode="json") for o in run.observations],
        [a.model_dump(mode="json") for a in run.artifacts],
    )
    by_id = {r["id"]: r for r in rows}
    sign = by_id["EV-E02-PQC-SIGN"]
    assert sign["value"] == "UNSUPPORTED"
    assert sign["acquisition_mode"] == "SIGN_TOOL"
    assert sign["artifacts"][0]["name"] == "e02-sign.log"
    assert by_id["EV-E02-BOOT"]["origin"] == "NOT_OBSERVED"
