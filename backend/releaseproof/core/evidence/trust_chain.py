"""Deterministic trust chain from WP0 evidence (linear, not force-directed)."""

from __future__ import annotations

from typing import Any

_CHAIN_ORDER = (
    "bootloader",
    "signature_verifier",
    "signed_image",
    "application",
    "update_path",
    "recovery",
)


def _evidence_index(evidence: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in evidence if item.get("id")}


def _provenance_for_ids(
    evidence_ids: list[str],
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for eid in evidence_ids:
        ev = evidence_by_id.get(eid)
        if not ev:
            continue
        rows.append(
            {
                "evidence_id": eid,
                "run_id": ev.get("run_id"),
                "acquisition_mode": ev.get("acquisition_mode"),
                "authority_context": ev.get("authority_context"),
                "test_id": ev.get("test_id"),
            }
        )
    return rows


def trust_chain_from_evidence(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Build nodes and edges from assessment evidence rows (no parallel domain model)."""
    by_id = _evidence_index(evidence)
    layout = by_id.get("EV-E05-LAYOUT-G2", {})
    partition = by_id.get("EV-LAYOUT-PARTITION", {})
    signed_size = None
    capacity = None
    layout_value = layout.get("value")
    if isinstance(layout_value, dict):
        signed_size = layout_value.get("signed_artifact_size")
    partition_value = partition.get("value")
    if isinstance(partition_value, dict):
        capacity = partition_value.get("boot_slot_capacity")
    if signed_size is None or capacity is None:
        signed_size = signed_size or 0
        capacity = capacity or 0

    self_update = by_id.get("EV-E11-SELF-UPDATE", {}).get("value") == "PASS"
    key_mismatch = by_id.get("EV-E03-PANIC", {}).get("value")

    node_specs: list[dict[str, Any]] = [
        {
            "node_id": "bootloader",
            "role": "Component",
            "status": "OBSERVED",
            "evidence_ids": ["EV-BOOTLOADER-SIZE-G1", "EV-BOOTLOADER-SIZE-G2"],
        },
        {
            "node_id": "signature_verifier",
            "role": "CryptoAsset",
            "status": "OBSERVED",
            "evidence_ids": ["EV-E02-BOOT", "EV-E03-PANIC"],
            "detail": {"key_mismatch_observed": key_mismatch},
        },
        {
            "node_id": "signed_image",
            "role": "Artifact",
            "status": "SATISFIED" if int(signed_size) <= int(capacity) else "VIOLATED",
            "evidence_ids": ["EV-E05-LAYOUT-G2", "EV-LAYOUT-PARTITION"],
            "detail": {
                "signed_image_size_bytes": signed_size,
                "boot_slot_capacity": capacity,
            },
        },
        {
            "node_id": "application",
            "role": "Component",
            "status": "OBSERVED",
            "evidence_ids": ["EV-E02-BOOT"],
        },
        {
            "node_id": "update_path",
            "role": "AuthorizationSurface",
            "status": "PARTIAL" if not self_update else "OBSERVED",
            "evidence_ids": ["EV-APP-UPDATE-SCRIPT", "EV-E11-SELF-UPDATE"],
            "detail": {"bootloader_self_update_supported": self_update},
        },
        {
            "node_id": "recovery",
            "role": "AuthorizationSurface",
            "status": "GAP",
            "evidence_ids": ["EV-E12-WINDOW"],
            "gap_ids": ["GAP-E10-INTERRUPT", "GAP-E12-NON-ATOMIC"],
            "detail": {"observed_recovery_mode": "UNKNOWN"},
        },
    ]
    if "EV-SCENARIO-RECOVERY" in by_id:
        for spec in node_specs:
            if spec["node_id"] != "recovery":
                continue
            spec["status"] = "DECLARED"
            spec["evidence_ids"] = ["EV-SCENARIO-RECOVERY"]
            spec["gap_ids"] = []
            spec["detail"] = {"observed_recovery_mode": "DECLARED_IN_SCENARIO"}

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for spec in node_specs:
        eids = list(spec.get("evidence_ids") or [])
        prov = _provenance_for_ids(eids, by_id)
        run_ids = [row["run_id"] for row in prov if row.get("run_id")]
        nodes.append(
            {
                "node_id": spec["node_id"],
                "role": spec["role"],
                "status": spec["status"],
                "run_id": run_ids[0] if run_ids else None,
                "evidence_ids": eids,
                "gap_ids": list(spec.get("gap_ids") or []),
                "provenance": prov,
                "detail": spec.get("detail") or {},
            }
        )

    for index, node_id in enumerate(_CHAIN_ORDER):
        if index == 0:
            continue
        edges.append(
            {
                "from": _CHAIN_ORDER[index - 1],
                "to": node_id,
                "relation": "TRUST_CHAIN",
            }
        )

    return {"nodes": nodes, "edges": edges}


def trust_chain_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Backward-compatible list of nodes for CLI output."""
    from releaseproof.core.evidence.map import evidence_from_wp0_runs

    fragment = trust_chain_from_evidence(evidence_from_wp0_runs(snapshot))
    return fragment["nodes"]


def trust_chain_explanation_fragment(
    evidence: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map trust chain into explanation-graph node/edge shape."""
    chain = trust_chain_from_evidence(evidence)
    graph_nodes: list[dict[str, Any]] = []
    graph_edges: list[dict[str, Any]] = []
    for node in chain["nodes"]:
        graph_id = f"TC-{node['node_id']}"
        graph_nodes.append(
            {
                "id": graph_id,
                "type": "COMPONENT",
                "role": node["role"],
                "status": node["status"],
                "run_id": node.get("run_id"),
                "provenance": node.get("provenance"),
            }
        )
        for eid in node.get("evidence_ids") or []:
            graph_edges.append(
                {"from": graph_id, "to": eid, "relation": "SUPPORTED_BY_EVIDENCE"}
            )
        for gid in node.get("gap_ids") or []:
            graph_edges.append({"from": graph_id, "to": gid, "relation": "OPEN_GAP"})
    for edge in chain["edges"]:
        graph_edges.append(
            {
                "from": f"TC-{edge['from']}",
                "to": f"TC-{edge['to']}",
                "relation": edge["relation"],
            }
        )
    return graph_nodes, graph_edges


__all__ = [
    "trust_chain_explanation_fragment",
    "trust_chain_from_evidence",
    "trust_chain_from_snapshot",
]
