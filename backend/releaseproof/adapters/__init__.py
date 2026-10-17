"""Assessment adapters: live runner facts → V1.2 assessment documents (WS-E).

``get_adapter(profile.assessment_adapter)`` returns a pure, deterministic
:class:`~releaseproof.contracts.services.AssessmentAdapter`. ``evidence_index`` turns the
evidence rows of an assessment back into API ``EvidenceView`` rows with artifact links.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from releaseproof.adapters._common import coerce_artifacts, coerce_observations
from releaseproof.adapters.mcuboot import build_mcuboot_v1_2_assessment
from releaseproof.adapters.wolfboot import build_wolfboot_v1_2_assessment
from releaseproof.contracts.api import ArtifactView, EvidenceView
from releaseproof.contracts.runner import ArtifactEvent, Observation, Origin
from releaseproof.contracts.services import AdapterError, AssessmentAdapter

ADAPTERS: dict[str, AssessmentAdapter] = {
    "wolfboot_v1_2": build_wolfboot_v1_2_assessment,
    "mcuboot_v1_2": build_mcuboot_v1_2_assessment,
}


def get_adapter(name: str) -> AssessmentAdapter:
    try:
        return ADAPTERS[name]
    except KeyError as exc:
        raise AdapterError(f"unknown assessment adapter {name!r}") from exc


# evidence id → candidate (test_id, fact) sources; the row's test_id picks the one used.
EVIDENCE_SOURCES: dict[str, tuple[tuple[str, str], ...]] = {
    "EV-PIN-WOLFBOOT": (("D01", "bootloader_commit"),),
    "EV-PIN-WOLFCRYPT": (("D01", "crypto_commit"),),
    "EV-PIN-MCUBOOT": (("D01", "bootloader_commit"),),
    "EV-PIN-ZEPHYR": (("D01", "zephyr_commit"),),
    "EV-LAYOUT-PARTITION": (("D01", "partition_layout"), ("E05", "layout_fit")),
    "EV-D01-IMGTOOL-KEYTYPES": (("D01", "imgtool_key_types"),),
    "EV-E11-SELF-UPDATE": (("E11", "bootloader_field_update"),),
    "EV-E11-BL-FIELD-UPDATE": (("E11", "bootloader_field_update"),),
    "EV-E01-BOOT": (("E01", "boot_outcome"),),
    "EV-E01-VERSION": (("E01", "observed_version"),),
    "EV-E01-SIGNED-SIZE": (("E01", "signed_image_size_bytes"),),
    "EV-E01-PUBKEY": (("E01", "public_key_sha256"),),
    "EV-BOOTLOADER-SIZE-G1": (("E01", "bootloader_size_bytes"),),
    "EV-E02-BOOT": (("E02", "boot_outcome"),),
    "EV-E02-VERSION": (("E02", "observed_version"),),
    "EV-E02-SIGNED-SIZE": (("E02", "signed_image_size_bytes"),),
    "EV-E02-PUBKEY": (("E02", "public_key_sha256"),),
    "EV-BOOTLOADER-SIZE-G2": (("E02", "bootloader_size_bytes"),),
    "EV-E02-PQC-SIGN": (("E02", "pqc_signing"),),
    "EV-E03-PANIC": (("E03", "auth_negative"),),
    "EV-E04-HEADER-SPAN": (("E04", "image_header"),),
    "EV-E05-LAYOUT-G2": (("E05", "layout_fit"),),
    "EV-E05-LAYOUT-CANDIDATE": (("E05", "layout_fit"),),
    "EV-E05-LAYOUT-DEPLOYED": (("E05", "layout_fit"),),
    "EV-E08-UPDATE": (("E08", "update_outcome"),),
    "EV-O05-DUAL-BUILD": (("O05", "dual_signature_build"),),
    "EV-P01-CLASSICAL-REJECT": (("P01", "classical_image_on_candidate"),),
    "EV-X01-CROSS-UPDATE": (("X01", "cross_update_outcome"),),
}


def evidence_index(
    assessment: dict[str, Any],
    observations: Iterable[Observation | dict[str, Any]],
    artifacts: Iterable[ArtifactEvent | dict[str, Any]],
) -> list[dict[str, Any]]:
    """One ``EvidenceView`` dict per assessment evidence row, in assessment order.

    Rows backed by an observation carry its origin, locator and source artifacts (URL
    ``/api/assessments/{artifact run_id}/artifacts/{artifact_id}``). Placeholders for facts
    that were never reported have origin ``NOT_OBSERVED``; plan declarations ``DECLARED``.
    """
    by_key: dict[tuple[str, str], Observation] = {}
    for obs in sorted(coerce_observations(observations), key=lambda o: o.observation_id):
        if obs.origin != Origin.AI_PROPOSAL:
            by_key.setdefault((obs.test_id, obs.fact), obs)
    by_artifact = {a.artifact_id: a for a in coerce_artifacts(artifacts)}

    rows: list[dict[str, Any]] = []
    for item in assessment.get("evidence") or []:
        evidence_id = str(item.get("id") or "")
        test_id = item.get("test_id")
        obs = next(
            (
                by_key[source]
                for source in EVIDENCE_SOURCES.get(evidence_id, ())
                if source[0] == test_id and source in by_key
            ),
            None,
        )
        views: list[ArtifactView] = []
        if obs is not None:
            for artifact_id in obs.source_artifact_ids:
                art = by_artifact.get(artifact_id)
                if art is None:
                    continue
                views.append(
                    ArtifactView(
                        artifact_id=art.artifact_id,
                        name=art.name,
                        kind=art.kind,
                        sha256=art.sha256,
                        size_bytes=art.size_bytes,
                        test_id=art.test_id,
                        url=f"/api/assessments/{art.run_id}/artifacts/{art.artifact_id}",
                    )
                )
        if obs is not None:
            origin = obs.origin.value
        elif item.get("evidence_kind") == "DECLARATION":
            origin = Origin.DECLARED.value
        else:
            origin = "NOT_OBSERVED"
        rows.append(
            EvidenceView(
                id=evidence_id,
                test_id=test_id,
                value=item.get("value"),
                evidence_kind=str(item.get("evidence_kind") or ""),
                acquisition_mode=str(item.get("acquisition_mode") or ""),
                origin=origin,
                run_id=item.get("run_id"),
                artifacts=views,
                locator=obs.locator if obs is not None else None,
            ).model_dump(mode="json")
        )
    return rows


__all__ = ["ADAPTERS", "AdapterError", "EVIDENCE_SOURCES", "evidence_index", "get_adapter"]
