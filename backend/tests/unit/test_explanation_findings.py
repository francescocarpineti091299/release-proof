"""Findings appear in explanation graph between rule and evidence."""

from __future__ import annotations

from releaseproof.core.explanation.service import build_explanation_graph, provenance_errors


def test_finding_node_between_rule_and_evidence() -> None:
    graph = build_explanation_graph(
        migration_verdict="INCOMPATIBLE",
        requirement_results=[
            {
                "requirement_id": "REQ-BOOT-S0S1",
                "phase": "TRANSITION",
                "subject_type": "TRANSITION_STEP",
                "subject_ref": "STEP-S0-S1",
                "rule_refs": ["RULE-BOOT-S0S1"],
                "evidence_refs": ["EV-E11-SELF-UPDATE"],
                "gap_refs": [],
                "provenance": "EVIDENCE",
                "findings": [
                    {
                        "requirement_id": "REQ-BOOT-S0S1",
                        "observation": "Self-update unsupported",
                    }
                ],
            }
        ],
        invariant_results=[],
        evidence_by_id={
            "EV-E11-SELF-UPDATE": {
                "id": "EV-E11-SELF-UPDATE",
                "evidence_kind": "MEASUREMENT",
                "test_id": "E11",
                "run_id": "run-1",
                "acquisition_mode": "SOURCE_INSPECTION",
                "authority_context": "OBSERVED",
            }
        },
        gaps=[],
    )
    finding_nodes = [n for n in graph["nodes"] if n["type"] == "FINDING"]
    assert len(finding_nodes) == 1
    fid = finding_nodes[0]["id"]
    assert any(e["from"] == "RULE-BOOT-S0S1" and e["to"] == fid for e in graph["edges"])
    assert any(e["from"] == fid and e["to"] == "EV-E11-SELF-UPDATE" for e in graph["edges"])
    errors = provenance_errors(
        graph,
        requirement_results=[
            {
                "requirement_id": "REQ-BOOT-S0S1",
                "phase": "TRANSITION",
                "subject_type": "TRANSITION_STEP",
                "subject_ref": "STEP-S0-S1",
                "critical_for_verdict": True,
                "rule_refs": ["RULE-BOOT-S0S1"],
                "evidence_refs": ["EV-E11-SELF-UPDATE"],
                "gap_refs": [],
                "provenance": "EVIDENCE",
            }
        ],
        invariant_results=[],
        evidence_by_id={
            "EV-E11-SELF-UPDATE": {
                "evidence_kind": "MEASUREMENT",
                "test_id": "E11",
                "run_id": "run-1",
                "acquisition_mode": "SOURCE_INSPECTION",
            }
        },
    )
    assert errors == []
