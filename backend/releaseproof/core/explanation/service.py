"""Explanation graph construction."""

from __future__ import annotations

from typing import Any

from releaseproof.core.domain.enums import EvidenceKind


def build_explanation_graph(
    *,
    migration_verdict: str,
    requirement_results: list[dict[str, Any]],
    invariant_results: list[dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    gaps: list[dict[str, Any]],
    global_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build provenance paths for requirement and invariant results."""
    nodes: list[dict[str, Any]] = [
        {"id": "V-MIG", "type": "VERDICT", "verdict": migration_verdict},
    ]
    edges: list[dict[str, Any]] = []
    gap_by_id = {g.get("gap_id"): g for g in gaps}

    findings_by_req: dict[str, list[dict[str, Any]]] = {}
    for item in global_findings or []:
        rid = str(item.get("requirement_id") or "")
        findings_by_req.setdefault(rid, []).append(item)

    for req in requirement_results:
        node_id = _result_node_id(req, "requirement_id")
        req_id = str(req.get("requirement_id") or "")
        row_findings = list(req.get("findings") or [])
        if not row_findings and req_id in findings_by_req:
            row_findings = findings_by_req.get(req_id, [])
        _link_subject(
            nodes,
            edges,
            node_id=node_id,
            node_type="REQUIREMENT",
            rule_refs=req.get("rule_refs") or [],
            evidence_refs=req.get("evidence_refs") or [],
            gap_refs=req.get("gap_refs") or [],
            evidence_by_id=evidence_by_id,
            gap_by_id=gap_by_id,
            provenance=req.get("provenance"),
            findings=row_findings,
            subject_node_id=node_id,
        )
    for inv in invariant_results:
        node_id = _result_node_id(inv, "invariant_id")
        _link_subject(
            nodes,
            edges,
            node_id=node_id,
            node_type="INVARIANT",
            rule_refs=inv.get("rule_refs") or [],
            evidence_refs=inv.get("evidence_refs") or [],
            gap_refs=inv.get("gap_refs") or [],
            evidence_by_id=evidence_by_id,
            gap_by_id=gap_by_id,
            provenance=inv.get("provenance"),
            findings=[],
            subject_node_id=node_id,
        )
    return {"nodes": nodes, "edges": edges}


_GRAPH_NODE_KEYS = frozenset({"id", "type", "verdict", "kind"})
_GRAPH_EDGE_KEYS = frozenset({"from", "to", "relation"})


def sanitize_explanation_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Strip node/edge fields not allowed by semantic_result_v1_2 explanationGraph."""
    return {
        "nodes": [
            {key: node[key] for key in _GRAPH_NODE_KEYS if key in node}
            for node in graph.get("nodes") or []
        ],
        "edges": [
            {key: edge[key] for key in _GRAPH_EDGE_KEYS if key in edge}
            for edge in graph.get("edges") or []
        ],
    }


def merge_trust_chain(
    graph: dict[str, Any],
    *,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Append linear trust-chain nodes without replacing the verdict explanation graph."""
    from releaseproof.core.evidence.trust_chain import trust_chain_explanation_fragment

    if not any(item.get("id") == "EV-E05-LAYOUT-G2" for item in evidence):
        return graph
    tc_nodes, tc_edges = trust_chain_explanation_fragment(evidence)
    existing_node_ids = {node["id"] for node in graph.get("nodes") or []}
    for node in tc_nodes:
        if node["id"] not in existing_node_ids:
            graph.setdefault("nodes", []).append(node)
    graph.setdefault("edges", []).extend(tc_edges)
    return graph


def provenance_errors(
    graph: dict[str, Any],
    *,
    requirement_results: list[dict[str, Any]],
    invariant_results: list[dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Return errors when a critical conclusion lacks its provenance path."""
    errors: list[str] = []
    for req in requirement_results:
        if not req.get("critical_for_verdict"):
            continue
        errors.extend(
            _path_errors(
                graph,
                node_id=_result_node_id(req, "requirement_id"),
                rule_refs=req.get("rule_refs") or [],
                evidence_refs=req.get("evidence_refs") or [],
                gap_refs=req.get("gap_refs") or [],
                evidence_by_id=evidence_by_id,
                provenance=req.get("provenance"),
            )
        )
    for inv in invariant_results:
        if not inv.get("critical_for_verdict"):
            continue
        errors.extend(
            _path_errors(
                graph,
                node_id=_result_node_id(inv, "invariant_id"),
                rule_refs=inv.get("rule_refs") or [],
                evidence_refs=inv.get("evidence_refs") or [],
                gap_refs=inv.get("gap_refs") or [],
                evidence_by_id=evidence_by_id,
                provenance=inv.get("provenance"),
            )
        )
    return errors


def _finding_node_id(subject_node_id: str, finding: dict[str, Any], index: int) -> str:
    req = finding.get("requirement_id") or "FINDING"
    return f"FINDING|{subject_node_id}|{req}|{index}"


def _result_node_id(result: dict[str, Any], key: str) -> str:
    return "|".join(
        [
            str(result.get(key) or ""),
            str(result.get("phase") or ""),
            str(result.get("subject_type") or ""),
            str(result.get("subject_ref") or ""),
        ]
    )


def _link_subject(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    node_id: str,
    node_type: str,
    rule_refs: list[str],
    evidence_refs: list[str],
    gap_refs: list[str],
    evidence_by_id: dict[str, dict[str, Any]],
    gap_by_id: dict[str, Any],
    provenance: str | None,
    findings: list[dict[str, Any]] | None = None,
    subject_node_id: str | None = None,
) -> None:
    nodes.append({"id": node_id, "type": node_type})
    edges.append({"from": "V-MIG", "to": node_id, "relation": "SUPPORTED_BY"})
    rule_id = rule_refs[0] if rule_refs else None
    if rule_id:
        nodes.append({"id": rule_id, "type": "RULE"})
        edges.append({"from": node_id, "to": rule_id, "relation": "RULE"})
    parent = rule_id or node_id
    finding_parent = parent
    subject = subject_node_id or node_id
    for index, finding in enumerate(findings or []):
        fid = _finding_node_id(subject, finding, index)
        nodes.append({"id": fid, "type": "FINDING"})
        edges.append({"from": parent, "to": fid, "relation": "FINDING"})
        finding_parent = fid
    if provenance == "CONSTRAINT" and not evidence_refs and not gap_refs:
        return
    link_from = finding_parent if (findings or []) else parent
    for eid in evidence_refs:
        ev = evidence_by_id.get(eid, {})
        nodes.append(
            {
                "id": eid,
                "type": "EVIDENCE",
                "kind": ev.get("evidence_kind"),
                "run_id": ev.get("run_id"),
                "acquisition_mode": ev.get("acquisition_mode"),
                "authority_context": ev.get("authority_context"),
                "test_id": ev.get("test_id"),
            }
        )
        edges.append({"from": link_from, "to": eid, "relation": "EVIDENCE_FOR"})
        family = _provenance_family(ev)
        if family == "measurement":
            _link_measurement(nodes, edges, eid, ev)
        elif family == "declaration":
            source = ev.get("source_identity") or (ev.get("artifact_refs") or [None])[0]
            if source:
                nodes.append({"id": str(source), "type": "SOURCE"})
                edges.append({"from": eid, "to": str(source), "relation": "FROM_SOURCE"})
    for gid in gap_refs:
        nodes.append({"id": gid, "type": "EVIDENCE_GAP"})
        edges.append({"from": link_from, "to": gid, "relation": "GAP"})
        gap = gap_by_id.get(gid) or {}
        requirement = gap.get("requested_evidence") or f"{gid}-REQUIREMENT"
        nodes.append({"id": requirement, "type": "EVIDENCE_REQUIREMENT"})
        edges.append({"from": gid, "to": requirement, "relation": "REQUIRES"})


def _link_measurement(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    evidence_id: str,
    evidence: dict[str, Any],
) -> None:
    if evidence.get("acquisition_mode") == "CATALOG_FACT":
        return
    test_id = evidence.get("test_id")
    run_id = evidence.get("run_id")
    artifacts = evidence.get("artifact_refs") or []
    if not test_id or not run_id:
        return
    nodes.append({"id": test_id, "type": "TEST"})
    edges.append({"from": evidence_id, "to": test_id, "relation": "FROM_TEST"})
    nodes.append(
        {
            "id": run_id,
            "type": "RUN",
            "acquisition_mode": evidence.get("acquisition_mode"),
            "authority_context": evidence.get("authority_context"),
        }
    )
    edges.append({"from": test_id, "to": run_id, "relation": "RUN"})
    if not artifacts:
        return
    artifact = artifacts[0]
    nodes.append({"id": artifact, "type": "ARTIFACT"})
    edges.append({"from": run_id, "to": artifact, "relation": "ARTIFACT"})


def _provenance_family(evidence: dict[str, Any]) -> str:
    kind = evidence.get("evidence_kind")
    if kind == EvidenceKind.MEASUREMENT:
        return "measurement"
    if kind in (EvidenceKind.DECLARATION, EvidenceKind.INFERENCE):
        return "declaration"
    return "gap"


def _path_errors(
    graph: dict[str, Any],
    *,
    node_id: str,
    rule_refs: list[str],
    evidence_refs: list[str],
    gap_refs: list[str],
    evidence_by_id: dict[str, dict[str, Any]],
    provenance: str | None,
) -> list[str]:
    edges = graph.get("edges") or []
    linked = {e.get("to") for e in edges if e.get("from") == "V-MIG"}
    if node_id not in linked:
        return [f"Percorso explanation assente per {node_id}"]
    if not rule_refs:
        return [f"Regola assente nel percorso di {node_id}"]
    rule_id = rule_refs[0]
    if not any(e.get("from") == node_id and e.get("to") == rule_id for e in edges):
        return [f"Regola non collegata per {node_id}"]
    if provenance == "CONSTRAINT" and not evidence_refs and not gap_refs:
        return []
    errors: list[str] = []
    sources = _rule_and_findings(edges, rule_id)
    if evidence_refs:
        for eid in evidence_refs:
            ev = evidence_by_id.get(eid, {})
            if not any(e.get("from") in sources and e.get("to") == eid for e in edges):
                errors.append(f"Evidence non collegata per {node_id}")
                continue
            family = _provenance_family(ev)
            if family == "measurement" and not _measurement_complete(edges, ev):
                errors.append(f"Misura senza Test/Run/Artifact per {eid}")
            if family == "declaration" and not _declaration_complete(edges, eid, ev):
                errors.append(f"Dichiarazione senza Source per {eid}")
    elif gap_refs:
        for gid in gap_refs:
            if not any(e.get("from") in sources and e.get("to") == gid for e in edges):
                errors.append(f"Gap non collegato per {node_id}")
            elif not any(e.get("from") == gid and e.get("relation") == "REQUIRES" for e in edges):
                errors.append(f"EvidenceRequirement assente per {gid}")
    else:
        errors.append(f"Provenance assente per {node_id}")
    return errors


def _rule_and_findings(edges: list[dict[str, Any]], rule_id: str) -> set[str]:
    """Rule plus FINDING nodes chained after it. Evidence may hang off either."""
    sources = {rule_id}
    changed = True
    while changed:
        changed = False
        for edge in edges:
            if edge.get("relation") != "FINDING" or edge.get("from") not in sources:
                continue
            target = edge.get("to")
            if target and target not in sources:
                sources.add(target)
                changed = True
    return sources


def _measurement_complete(edges: list[dict[str, Any]], evidence: dict[str, Any]) -> bool:
    if evidence.get("acquisition_mode") == "CATALOG_FACT":
        return True
    test_id = evidence.get("test_id")
    run_id = evidence.get("run_id")
    artifacts = evidence.get("artifact_refs") or []
    if not test_id or not run_id:
        return False
    if not artifacts:
        return any(e.get("from") == test_id and e.get("to") == run_id for e in edges)
    return any(e.get("from") == run_id and e.get("to") == artifacts[0] for e in edges)


def _declaration_complete(
    edges: list[dict[str, Any]],
    evidence_id: str,
    evidence: dict[str, Any],
) -> bool:
    source = evidence.get("source_identity") or (evidence.get("artifact_refs") or [None])[0]
    if not source:
        return False
    return any(e.get("from") == evidence_id and e.get("to") == str(source) for e in edges)


__all__ = [
    "build_explanation_graph",
    "merge_trust_chain",
    "provenance_errors",
    "sanitize_explanation_graph",
]
