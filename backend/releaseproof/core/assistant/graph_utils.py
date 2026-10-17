"""Join explanation graph edges with evaluation rows (mirrors web/domain/graph-trace.ts)."""

from __future__ import annotations

from typing import Any


def parse_subject_node(node_id: str) -> dict[str, str]:
    parts = node_id.split("|")
    return {
        "label": parts[0] if parts else node_id,
        "phase": parts[1] if len(parts) > 1 else "",
        "subject_type": parts[2] if len(parts) > 2 else "",
        "subject_ref": parts[3] if len(parts) > 3 else "",
    }


def _result_row(result: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    parsed = parse_subject_node(node_id)
    for row in result.get("requirement_evaluation_results") or []:
        if (
            row.get("requirement_id") == parsed["label"]
            and row.get("phase") == parsed["phase"]
            and row.get("subject_ref") == parsed["subject_ref"]
        ):
            return row
    for row in result.get("invariant_evaluation_results") or []:
        if (
            row.get("invariant_id") == parsed["label"]
            and row.get("phase") == parsed["phase"]
            and row.get("subject_ref") == parsed["subject_ref"]
        ):
            return row
    return None


def trace_requirement(
    result: dict[str, Any],
    requirement_id: str,
    *,
    phase: str | None = "TRANSITION",
    subject_ref: str | None = None,
) -> dict[str, Any] | None:
    graph = result.get("explanation_graph") or {}
    nodes = {n["id"]: n for n in graph.get("nodes") or []}
    out: dict[str, list[str]] = {}
    for edge in graph.get("edges") or []:
        out.setdefault(edge["from"], []).append(edge["to"])

    subject_nodes = [
        n
        for n in graph.get("nodes") or []
        if n.get("type") in ("REQUIREMENT", "INVARIANT")
        and parse_subject_node(n["id"])["label"] == requirement_id
        and (phase is None or parse_subject_node(n["id"])["phase"] == phase)
        and (
            subject_ref is None
            or parse_subject_node(n["id"])["subject_ref"] == subject_ref
        )
    ]
    if not subject_nodes:
        return None
    node = subject_nodes[0]
    node_id = node["id"]
    rules = [tid for tid in out.get(node_id, []) if nodes.get(tid, {}).get("type") == "RULE"]
    rule_id = rules[0] if rules else None
    from_rule = out.get(rule_id, []) if rule_id else out.get(node_id, [])
    finding_ids = [tid for tid in from_rule if nodes.get(tid, {}).get("type") == "FINDING"]
    link_root = finding_ids[-1] if finding_ids else (rule_id or node_id)
    downstream = out.get(link_root, [])
    if not downstream and rule_id:
        downstream = out.get(rule_id, [])
    evidence_ids = list(
        dict.fromkeys(tid for tid in downstream if nodes.get(tid, {}).get("type") == "EVIDENCE")
    )
    gap_ids = list(
        dict.fromkeys(tid for tid in downstream if nodes.get(tid, {}).get("type") == "EVIDENCE_GAP")
    )
    row = _result_row(result, node_id)
    return {
        "node_id": node_id,
        "requirement_id": requirement_id,
        "phase": parse_subject_node(node_id)["phase"],
        "state": (row or {}).get("state", "UNKNOWN"),
        "critical": (row or {}).get("critical_for_verdict", False),
        "rule_ids": rules,
        "evidence_ids": evidence_ids,
        "gap_ids": gap_ids,
        "row": row,
    }


def critical_violated_traces(result: dict[str, Any]) -> list[dict[str, Any]]:
    """One trace per distinct critical VIOLATED requirement, in evaluation order."""
    traces: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in result.get("requirement_evaluation_results") or []:
        if not (row.get("critical_for_verdict") and row.get("state") == "VIOLATED"):
            continue
        requirement_id = str(row.get("requirement_id") or "")
        if not requirement_id or requirement_id in seen:
            continue
        trace = trace_requirement(
            result,
            requirement_id,
            phase=str(row.get("phase") or ""),
            subject_ref=str(row.get("subject_ref") or ""),
        )
        if not trace:
            continue
        seen.add(requirement_id)
        traces.append(trace)
    return traces


def build_causal_steps(result: dict[str, Any], trace: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    mig = result.get("migration_verdict")
    if mig:
        steps.append(
            {
                "step_kind": "VERDICT",
                "id": "V-MIG",
                "label": f"Migrazione: {mig}",
                "state": None,
                "phase": None,
            }
        )
    steps.append(
        {
            "step_kind": "REQUIREMENT",
            "id": trace["node_id"],
            "label": trace["requirement_id"],
            "state": trace["state"],
            "phase": trace["phase"],
        }
    )
    for rid in trace.get("rule_ids") or []:
        steps.append({"step_kind": "RULE", "id": rid, "label": rid, "state": None, "phase": None})
    for eid in trace.get("evidence_ids") or []:
        steps.append(
            {"step_kind": "EVIDENCE", "id": eid, "label": eid, "state": None, "phase": None}
        )
    for gid in trace.get("gap_ids") or []:
        steps.append({"step_kind": "GAP", "id": gid, "label": gid, "state": None, "phase": None})
    return steps
