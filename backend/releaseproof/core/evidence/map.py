"""Map WP0 run manifests to assessment evidence records."""

from __future__ import annotations

import json
from typing import Any

from releaseproof.core.canonical.service import compute_canonical_hash
from releaseproof.core.paths import REFERENCE_RUNS

WP0_RUNS = REFERENCE_RUNS


def layout_measurement(
    evidence_id: str,
    *,
    signed_artifact_size: int,
    boot_slot_capacity: int,
    run_id: str | None = None,
    acquisition_mode: str = "STATIC_ARTIFACT",
    content_hash: str | None = None,
) -> dict[str, Any]:
    """E05 capacity evidence for REQ-LAYOUT / LEQ."""
    record: dict[str, Any] = {
        "id": evidence_id,
        "evidence_kind": "MEASUREMENT",
        "source_role": "TOOL",
        "authority_context": "OBSERVED",
        "acquisition_mode": acquisition_mode,
        "review_status": "AUTOMATIC",
        "status": "VALID",
        "test_id": "E05",
        "value": {
            "signed_artifact_size": signed_artifact_size,
            "boot_slot_capacity": boot_slot_capacity,
        },
    }
    if run_id:
        record["run_id"] = run_id
    if content_hash:
        record["content_hash"] = content_hash
    return record


def _load_manifest(run_id: str) -> dict[str, Any] | None:
    path = WP0_RUNS / run_id / "manifest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def evidence_from_wp0_runs(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Build typed evidence rows from a freeze snapshot and local run manifests when present."""
    evidence: list[dict[str, Any]] = []
    ecdsa = snapshot["ecdsa"]
    mldsa = snapshot["mldsa87"]
    experiments = snapshot.get("experiments") or {}

    evidence.append(
        {
            "id": "EV-E01-BOOT",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "EMULATED",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "test_id": "E01",
            "run_id": ecdsa.get("run_id"),
            "value": "BOOT_OK",
        }
    )
    evidence.append(
        {
            "id": "EV-E02-BOOT",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "EMULATED",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "test_id": "E02",
            "run_id": mldsa.get("run_id"),
            "value": "BOOT_OK",
        }
    )
    evidence.append(
        {
            "id": "EV-E03-PANIC",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "EMULATED",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "test_id": "E03",
            "run_id": experiments.get("t3_run_id"),
            "artifact_refs": ["mismatch.resc"],
            "value": "REJECT",
        }
    )
    signed = layout_measurement(
        "EV-E05-LAYOUT-G2",
        signed_artifact_size=int(mldsa["signed_image_size_bytes"]),
        boot_slot_capacity=int(snapshot["partition_size_bytes"]),
        run_id=mldsa.get("run_id"),
    )
    signed["artifact_refs"] = ["test-app_image_v1_signed.bin"]
    signed["value"] = {"signed_artifact_size": int(mldsa["signed_image_size_bytes"])}
    evidence.append(signed)
    evidence.append(
        {
            "id": "EV-LAYOUT-PARTITION",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "STATIC_CONFIG",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "test_id": "E05",
            "run_id": mldsa.get("run_id"),
            "artifact_refs": ["config/examples/nrf52840.config"],
            "value": {"boot_slot_capacity": int(snapshot["partition_size_bytes"])},
        }
    )
    evidence.append(
        {
            "id": "EV-E04-HEADER",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "STATIC_CONFIG",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "test_id": "E04",
            "run_id": mldsa.get("run_id"),
            "value": {"image_header_size_declared": mldsa.get("image_header_size_declared")},
        }
    )
    evidence.append(
        {
            "id": "EV-E04-HEADER-SPAN",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "STATIC_ARTIFACT",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "test_id": "E04",
            "run_id": mldsa.get("run_id"),
            "artifact_refs": ["test-app_image_v1_signed.bin"],
            "value": {"header_span_measured_bytes": mldsa.get("header_span_measured_bytes")},
        }
    )
    evidence.append(
        {
            "id": "EV-E11-SELF-UPDATE",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "SOURCE_INSPECTION",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "test_id": "E11",
            "run_id": experiments.get("t1_self_update_run_id"),
            "artifact_refs": ["hal/nrf52.c"],
            "value": "UNSUPPORTED"
            if not experiments.get("t1_bootloader_self_update_supported", False)
            else "PASS",
        }
    )
    evidence.append(
        {
            "id": "EV-PIN-WOLFBOOT",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "REPOSITORY",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "source_identity": snapshot.get("wolfboot_commit"),
            "value": snapshot.get("wolfboot_commit"),
        }
    )
    evidence.append(
        {
            "id": "EV-E12-WINDOW",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "NOT_OBSERVED",
            "acquisition_mode": "UNOBSERVED",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "test_id": "E12",
            "value": "UNKNOWN",
        }
    )
    evidence.append(
        {
            "id": "EV-APP-UPDATE-SCRIPT",
            "evidence_kind": "INFERENCE",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "SOURCE_INSPECTION",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "test_id": "E08",
            "artifact_refs": ["tools/scripts/renode-test-update.sh"],
            "value": "PRESENT",
        }
    )
    evidence.append(
        {
            "id": "EV-BOOTLOADER-SIZE-G1",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "STATIC_ARTIFACT",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "run_id": ecdsa.get("run_id"),
            "artifact_refs": ["wolfboot.bin"],
            "value": {"bootloader_size_bytes": ecdsa.get("bootloader_size_bytes")},
        }
    )
    evidence.append(
        {
            "id": "EV-BOOTLOADER-SIZE-G2",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "STATIC_ARTIFACT",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "run_id": mldsa.get("run_id"),
            "artifact_refs": ["wolfboot.bin"],
            "value": {"bootloader_size_bytes": mldsa.get("bootloader_size_bytes")},
        }
    )
    evidence.append(
        {
            "id": "EV-T3-DUAL-BUILD",
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "BUILD",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "test_id": "E03",
            "run_id": experiments.get("t3_run_id"),
            "source_identity": experiments.get("t3_dual_configuration"),
            "value": experiments.get("t3_dual_build"),
        }
    )

    for run_id in (
        ecdsa.get("run_id"),
        mldsa.get("run_id"),
        experiments.get("t1_self_update_run_id"),
        experiments.get("t3_run_id"),
    ):
        if not run_id:
            continue
        manifest = _load_manifest(run_id)
        if not manifest:
            continue
        record: dict[str, Any] = {
            "id": f"EV-RUN-MANIFEST-{run_id}",
            "evidence_kind": "INFERENCE",
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "acquisition_mode": "RUN_MANIFEST",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "run_id": run_id,
            "content_hash": compute_canonical_hash(manifest),
            "value": manifest.get("status"),
        }
        artifacts = manifest.get("artifacts")
        if isinstance(artifacts, dict) and artifacts:
            record["artifact_refs"] = [next(iter(artifacts))]
        evidence.append(record)

    return enrich_evidence_run_provenance(evidence)


def enrich_evidence_run_provenance(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach artifact content_hash from run manifests when artifact_refs are known."""
    for item in evidence:
        run_id = item.get("run_id")
        if not run_id or item.get("content_hash"):
            continue
        manifest = _load_manifest(run_id)
        if not manifest:
            continue
        artifacts = manifest.get("artifacts") or {}
        refs = item.get("artifact_refs") or []
        if not refs:
            continue
        art = artifacts.get(refs[0])
        if isinstance(art, dict) and art.get("content_hash"):
            item["content_hash"] = art["content_hash"]
    return evidence


def evidence_gaps_for_wp0() -> list[dict[str, Any]]:
    """Open catalog gaps for the WP0 baseline assessment."""
    return [
        {
            "gap_id": "GAP-E07-RAM",
            "requirement_id": "REQ-RAM",
            "gap_type": "NOT_EXECUTABLE",
            "reason": "Stack painting not run; linker region only",
            "critical": False,
            "requested_evidence": "E07 RAM/stack method beyond static linker region",
        },
        {
            "gap_id": "GAP-E10-INTERRUPT",
            "requirement_id": "INV-I4",
            "gap_type": "UNKNOWN_FACT",
            "reason": "T2 firmware update interruption not repeatable on frozen point",
            "critical": True,
            "requested_evidence": "E10 event-based interruption with stable UART",
        },
        {
            "gap_id": "GAP-E12-NON-ATOMIC",
            "requirement_id": "INV-I4",
            "gap_type": "UNKNOWN_FACT",
            "reason": "Non-atomic update window not observed; I4 remains UNKNOWN",
            "critical": True,
            "requested_evidence": "E12 interrupted update with observed recovery",
        },
        {
            "gap_id": "GAP-O05-DUAL-POLICY",
            "requirement_id": "INV-I3",
            "gap_type": "UNKNOWN_FACT",
            "reason": "Dual signature build failed; AND/OR not observed on frozen commit",
            "critical": True,
            "requested_evidence": "O05 behavioral dual signature matrix",
        },
    ]


__all__ = [
    "enrich_evidence_run_provenance",
    "evidence_from_wp0_runs",
    "evidence_gaps_for_wp0",
    "layout_measurement",
]
