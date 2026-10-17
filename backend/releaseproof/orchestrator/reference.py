"""The recorded WP0 freeze (2026-10-01), evaluated by the current engine.

Always presented as ``mode=REFERENCE``: recorded data, never a live execution.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from releaseproof.contracts.api import (
    ResultView,
    RunMode,
    RunStatus,
    RunView,
    StageView,
    VerdictView,
)
from releaseproof.contracts.runner import Stage, StageStatus
from releaseproof.core.assurance.service import evaluate
from releaseproof.core.dossier.service import render_dossier_markdown
from releaseproof.core.planner.service import build_gap_plan
from releaseproof.core.projection.wp0 import (
    SNAPSHOT_PATH,
    build_wp0_baseline_assessment,
    load_freeze_snapshot,
)
from releaseproof.orchestrator.evaluation import build_evidence_views, sha256_file

REFERENCE_RUN_ID = "REF-WP0-FREEZE-20261001"
RECORDED_AT = "2026-10-01"
NOTICE = (
    "Recorded WP0 freeze of 2026-10-01 (nRF52840 + wolfBoot, ECDSA P-256 -> ML-DSA-87). "
    "These facts were measured on 2026-10-01 and are re-evaluated here by the current engine; "
    "this is not a live execution."
)
_STAGES = (
    Stage.PREPARING,
    Stage.AI_PLAN,
    Stage.DISCOVERY,
    Stage.BUILD_SIGN,
    Stage.EMULATION_TESTS,
    Stage.EVALUATION,
    Stage.NEXT_STEPS,
)


@lru_cache(maxsize=1)
def reference_bundle() -> tuple[RunView, ResultView]:
    snapshot = load_freeze_snapshot()
    assessment = build_wp0_baseline_assessment(snapshot)
    result: dict[str, Any] = evaluate(assessment).model_dump(mode="json")
    gap_plan = build_gap_plan(assessment, result)
    dossier = render_dossier_markdown(
        assessment,
        result,
        gap_plan=gap_plan,
        meta={
            "board": snapshot.get("board"),
            "freeze_at": snapshot.get("freeze_at"),
            "wolfboot_commit": snapshot.get("wolfboot_commit"),
        },
    )
    evidence = build_evidence_views(
        run_id=REFERENCE_RUN_ID, assessment=assessment, observations=[], artifact_rows=[]
    )
    evidence = [e.model_copy(update={"origin": "RECORDED_WP0_FREEZE"}) for e in evidence]
    stages = [
        StageView(
            stage=s,
            status=StageStatus.SUCCEEDED if s == Stage.EVALUATION else StageStatus.SKIPPED,
            message=(
                "recorded freeze evaluated by the current engine"
                if s == Stage.EVALUATION
                else f"recorded {RECORDED_AT}: not executed in this view"
            ),
        )
        for s in _STAGES
    ]
    plan_id = (assessment.get("transition_plan") or {}).get("plan_id", "bootloader_self_update")
    run = RunView(
        run_id=REFERENCE_RUN_ID,
        mode=RunMode.REFERENCE,
        status=RunStatus.SUCCEEDED,
        configuration_id="nrf52840-wolfboot-pqc",
        configuration_version="WP0-freeze",
        change_id="ecdsa_p256_to_mldsa87",
        plan_id=str(plan_id),
        created_at=str(snapshot.get("freeze_at") or f"{RECORDED_AT}T00:00:00Z"),
        stages=stages,
        verdict=VerdictView(
            lifecycle=str(result.get("lifecycle")),
            migration=result.get("migration_verdict"),
            candidate=result.get("candidate_verdict"),
            transition=result.get("transition_verdict"),
            canonical_hash=result.get("canonical_hash"),
        ),
        source_pins={
            "wolfboot": str(snapshot.get("wolfboot_commit")),
            "wolfcrypt": str(snapshot.get("wolfcrypt_commit")),
        },
    )
    view = ResultView(
        run_id=REFERENCE_RUN_ID,
        assessment=assessment,
        result=result,
        gap_plan=gap_plan,
        dossier_markdown=dossier,
        evidence=evidence,
        manifest_sha256=sha256_file(SNAPSHOT_PATH),
    )
    return run, view
