"""Phase 2: trust chain merge, auth-negative requirement, run manifest evidence."""

from __future__ import annotations

from releaseproof.core.assurance.service import evaluate
from releaseproof.core.domain.enums import RequirementResultState
from releaseproof.core.evidence.map import evidence_from_wp0_runs
from releaseproof.core.evidence.trust_chain import (
    trust_chain_explanation_fragment,
    trust_chain_from_evidence,
)
from releaseproof.core.projection.wp0 import build_wp0_baseline_assessment, load_freeze_snapshot


def test_trust_chain_from_evidence_linear_edges() -> None:
    snap = load_freeze_snapshot()
    chain = trust_chain_from_evidence(evidence_from_wp0_runs(snap))
    assert len(chain["nodes"]) == 6
    assert len(chain["edges"]) == 5
    assert chain["edges"][0]["relation"] == "TRUST_CHAIN"
    by_id = {n["node_id"]: n for n in chain["nodes"]}
    assert by_id["signature_verifier"]["detail"]["key_mismatch_observed"] == "REJECT"


def test_trust_chain_explanation_fragment_links_evidence() -> None:
    snap = load_freeze_snapshot()
    nodes, edges = trust_chain_explanation_fragment(evidence_from_wp0_runs(snap))
    assert any(n["id"] == "TC-bootloader" for n in nodes)
    assert any(
        e["from"] == "TC-signature_verifier" and e["to"] == "EV-E03-PANIC"
        for e in edges
    )


def test_merge_trust_chain_appends_to_graph() -> None:
    assessment = build_wp0_baseline_assessment()
    result = evaluate(assessment)
    graph = result.explanation_graph
    node_ids = {n["id"] for n in graph["nodes"]}
    assert "TC-recovery" in node_ids
    assert any(e.get("relation") == "TRUST_CHAIN" for e in graph["edges"])


def test_req_auth_negative_satisfied_on_e03_reject() -> None:
    result = evaluate(build_wp0_baseline_assessment())
    rows = [
        r
        for r in result.requirement_evaluation_results
        if r["requirement_id"] == "REQ-AUTH-NEGATIVE"
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["state"] == RequirementResultState.SATISFIED
    assert row["critical_for_verdict"] is False
    assert row["evidence_refs"] == ["EV-E03-PANIC"]


def test_e03_panic_and_t3_run_manifest() -> None:
    snap = load_freeze_snapshot()
    by_id = {item["id"]: item for item in evidence_from_wp0_runs(snap)}
    panic = by_id["EV-E03-PANIC"]
    assert panic["artifact_refs"] == ["mismatch.resc"]
    t3_run = snap["experiments"]["t3_run_id"]
    manifest_ev = by_id[f"EV-RUN-MANIFEST-{t3_run}"]
    assert manifest_ev["value"] == "CONCLUSIVE"
    assert manifest_ev["content_hash"].startswith("sha256:")
