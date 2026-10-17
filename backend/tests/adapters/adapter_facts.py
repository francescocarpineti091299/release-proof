"""Synthetic runner facts for adapter tests, matching the registered fact vocabulary."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from releaseproof.contracts.runner import ArtifactEvent, Observation, TestResultEvent

RUN_ID = "RP-20261017T120000Z-a1b2c3"
CREATED_AT = "2026-10-17T12:30:00Z"
REMOVE = object()

WOLFBOOT_COMMIT = "4c79eee999b7083743811f37928322fe78b9fdb1"
WOLFCRYPT_COMMIT = "4aa1ad7a5b4f7be86d88cc26fe3880a31ff7de9f"

_EMU = "OBSERVED_EMULATION"
_TOOL = "MEASURED_TOOL"

# (test_id, fact) -> (subject, value, origin, acquisition_mode, artifact name)
WOLFBOOT_FACTS: dict[tuple[str, str], tuple[str, Any, str, str, str]] = {
    ("D01", "bootloader_commit"): ("toolchain", WOLFBOOT_COMMIT, _TOOL, "REPOSITORY", "pins.json"),
    ("D01", "crypto_commit"): ("toolchain", WOLFCRYPT_COMMIT, _TOOL, "REPOSITORY", "pins.json"),
    ("D01", "partition_layout"): (
        "platform",
        {
            "boot_partition_address": 0x10000,
            "update_partition_address": 0x50000,
            "swap_address": 0x90000,
            "partition_size_bytes": 262144,
            "sector_size_bytes": 4096,
        },
        _TOOL,
        "STATIC_CONFIG",
        "nrf52840.config",
    ),
    ("E11", "bootloader_field_update"): (
        "platform",
        "UNSUPPORTED",
        _TOOL,
        "SOURCE_INSPECTION",
        "hal_nrf52.c",
    ),
    ("E01", "boot_outcome"): ("deployed_state", "BOOT_OK", _EMU, "EMULATED", "e01-uart.log"),
    ("E01", "observed_version"): ("deployed_state", 1, _EMU, "EMULATED", "e01-uart.log"),
    ("E01", "signed_image_size_bytes"): (
        "deployed_state",
        840,
        _TOOL,
        "STATIC_ARTIFACT",
        "e01-image_v1_signed.bin",
    ),
    ("E01", "bootloader_size_bytes"): (
        "deployed_state",
        23652,
        _TOOL,
        "STATIC_ARTIFACT",
        "e01-wolfboot.bin",
    ),
    ("E01", "public_key_sha256"): (
        "deployed_state",
        "ab" * 32,
        _TOOL,
        "STATIC_ARTIFACT",
        "e01-wolfboot.bin",
    ),
    ("E08", "update_outcome"): ("deployed_state", "APPLIED", _EMU, "EMULATED", "e01-uart.log"),
    ("E02", "boot_outcome"): ("candidate_state", "BOOT_OK", _EMU, "EMULATED", "e02-uart.log"),
    ("E02", "observed_version"): ("candidate_state", 1, _EMU, "EMULATED", "e02-uart.log"),
    ("E02", "signed_image_size_bytes"): (
        "candidate_state",
        12876,
        _TOOL,
        "STATIC_ARTIFACT",
        "e02-image_v1_signed.bin",
    ),
    ("E02", "bootloader_size_bytes"): (
        "candidate_state",
        22840,
        _TOOL,
        "STATIC_ARTIFACT",
        "e02-wolfboot.bin",
    ),
    ("E02", "public_key_sha256"): (
        "candidate_state",
        "cd" * 32,
        _TOOL,
        "STATIC_ARTIFACT",
        "e02-wolfboot.bin",
    ),
    ("E04", "image_header"): (
        "candidate_state",
        {"image_header_size_bytes": 12288, "header_span_bytes": 12288},
        _TOOL,
        "STATIC_ARTIFACT",
        "e02-image_v1_signed.bin",
    ),
    ("E05", "layout_fit"): (
        "candidate_state",
        {"signed_artifact_size": 12876, "boot_slot_capacity": 262144},
        _TOOL,
        "STATIC_ARTIFACT",
        "e02-image_v1_signed.bin",
    ),
    ("E03", "auth_negative"): ("deployed_state", "REJECT", _EMU, "EMULATED", "e03-uart.log"),
    ("X01", "cross_update_outcome"): (
        "transition",
        "REJECTED",
        _EMU,
        "EMULATED",
        "x01-uart.log",
    ),
}

WOLFBOOT_OPTIONAL: dict[tuple[str, str], tuple[str, Any, str, str, str]] = {
    ("P01", "classical_image_on_candidate"): (
        "candidate_state",
        "REJECT",
        _EMU,
        "EMULATED",
        "p01-uart.log",
    ),
    ("O05", "dual_signature_build"): (
        "candidate_state",
        "BUILD_FAILED",
        _TOOL,
        "BUILD",
        "o05-build.log",
    ),
}

MCUBOOT_FACTS: dict[tuple[str, str], tuple[str, Any, str, str, str]] = {
    ("D01", "bootloader_commit"): (
        "toolchain",
        "4eba8087fa606db801455f14d185255bc8c49467",
        _TOOL,
        "REPOSITORY",
        "west.lock",
    ),
    ("D01", "zephyr_commit"): ("toolchain", "2" * 40, _TOOL, "REPOSITORY", "west.lock"),
    ("D01", "partition_layout"): (
        "platform",
        {
            "boot_partition_size": 0xC000,
            "slot0_address": 0xC000,
            "slot0_size": 0x76000,
            "slot1_address": 0x82000,
            "slot1_size": 0x76000,
        },
        _TOOL,
        "STATIC_CONFIG",
        "zephyr.dts",
    ),
    ("D01", "imgtool_key_types"): (
        "toolchain",
        ["rsa-2048", "rsa-3072", "ecdsa-p256", "ecdsa-p384", "ed25519", "x25519"],
        _TOOL,
        "STATIC_ANALYSIS",
        "imgtool-help.txt",
    ),
    ("E11", "bootloader_field_update"): (
        "platform",
        "UNSUPPORTED",
        _TOOL,
        "STATIC_CONFIG",
        "zephyr.dts",
    ),
    ("E01", "boot_outcome"): ("deployed_state", "BOOT_OK", _EMU, "EMULATED", "e01-uart.log"),
    ("E01", "observed_version"): ("deployed_state", 1, _EMU, "EMULATED", "e01-uart.log"),
    ("E01", "signed_image_size_bytes"): (
        "deployed_state",
        41234,
        _TOOL,
        "STATIC_ARTIFACT",
        "app_v1.signed.bin",
    ),
    ("E01", "bootloader_size_bytes"): (
        "deployed_state",
        38000,
        _TOOL,
        "STATIC_ARTIFACT",
        "mcuboot.bin",
    ),
    ("E01", "public_key_sha256"): (
        "deployed_state",
        "ef" * 32,
        _TOOL,
        "STATIC_ARTIFACT",
        "mcuboot.bin",
    ),
    ("E05", "layout_fit"): (
        "deployed_state",
        {"signed_artifact_size": 41234, "boot_slot_capacity": 0x76000},
        _TOOL,
        "STATIC_ARTIFACT",
        "app_v1.signed.bin",
    ),
    ("E08", "update_outcome"): ("deployed_state", "APPLIED", _EMU, "EMULATED", "e08-uart.log"),
    ("E03", "auth_negative"): ("deployed_state", "REJECT", _EMU, "EMULATED", "e03-uart.log"),
    ("E02", "pqc_signing"): (
        "candidate_state",
        {
            "signing_result": "REJECTED",
            "algorithm": "ML-DSA-65",
            "tool": "imgtool 2.2.0",
            "message": "Error: Invalid value for '-t' / '--type': 'ml-dsa-65'",
        },
        _TOOL,
        "SIGN_TOOL",
        "e02-sign.log",
    ),
    ("X01", "cross_update_outcome"): (
        "transition",
        "REJECTED",
        _EMU,
        "EMULATED",
        "x01-uart.log",
    ),
}


@dataclass
class RunFacts:
    """Observations, artifacts and test results of one synthetic LIVE run."""

    observations: list[Observation] = field(default_factory=list)
    artifacts: list[ArtifactEvent] = field(default_factory=list)
    test_results: list[TestResultEvent] = field(default_factory=list)

    def kwargs(self) -> dict[str, Any]:
        return {
            "observations": self.observations,
            "artifacts": self.artifacts,
            "test_results": self.test_results,
        }


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def build_run(
    base: dict[tuple[str, str], tuple[str, Any, str, str, str]],
    overrides: dict[tuple[str, str], Any] | None = None,
    *,
    extra: dict[tuple[str, str], tuple[str, Any, str, str, str]] | None = None,
    outcomes: dict[str, str] | None = None,
    salt: str = "",
    run_id: str = RUN_ID,
) -> RunFacts:
    """``overrides`` maps (test_id, fact) to a new value, or ``REMOVE`` to drop it."""
    facts = dict(base)
    facts.update(extra or {})
    run = RunFacts()
    names: dict[str, str] = {}
    seq = 0
    for (test_id, fact), (subject, value, origin, mode, artifact) in facts.items():
        if overrides and (test_id, fact) in overrides:
            value = overrides[(test_id, fact)]
            if value is REMOVE:
                continue
        artifact_id = names.get(artifact)
        if artifact_id is None:
            artifact_id = f"ART-{len(names) + 1:03d}"
            names[artifact] = artifact_id
            run.artifacts.append(
                ArtifactEvent(
                    seq=seq,
                    ts=CREATED_AT,
                    run_id=run_id,
                    artifact_id=artifact_id,
                    name=artifact,
                    path=f"{test_id}/{artifact}",
                    sha256=_sha(f"{artifact}{salt}"),
                    size_bytes=1024,
                    kind="uart" if artifact.endswith(".log") else "other",
                    test_id=test_id,
                )
            )
            seq += 1
        run.observations.append(
            Observation(
                observation_id=f"OBS-{test_id}-{fact}",
                test_id=test_id,
                subject=subject,  # type: ignore[arg-type]
                fact=fact,
                value=value,
                origin=origin,  # type: ignore[arg-type]
                acquisition_mode=mode,
                source_artifact_ids=[artifact_id],
                locator=f"{artifact}:L1-L4",
                parser="synthetic@1",
            )
        )
    for test_id in sorted({obs.test_id for obs in run.observations}):
        outcome = (outcomes or {}).get(test_id, "PASS")
        run.test_results.append(
            TestResultEvent(
                seq=seq,
                ts=CREATED_AT,
                run_id=run_id,
                test_id=test_id,
                template_id=f"synthetic.{test_id.lower()}",
                outcome=outcome,  # type: ignore[arg-type]
                expected="synthetic",
                observed="synthetic",
                duration_ms=10,
                observation_ids=[
                    o.observation_id for o in run.observations if o.test_id == test_id
                ],
            )
        )
        seq += 1
    return run


def wolfboot_run(
    overrides: dict[tuple[str, str], Any] | None = None,
    *,
    p01: Any = REMOVE,
    o05: Any = REMOVE,
    **kw: Any,
) -> RunFacts:
    """Typical wolfBoot live run; optional P01/O05 facts only when a value is given."""
    extra = {}
    for key, value in (
        (("P01", "classical_image_on_candidate"), p01),
        (("O05", "dual_signature_build"), o05),
    ):
        if value is not REMOVE:
            subject, _, origin, mode, artifact = WOLFBOOT_OPTIONAL[key]
            extra[key] = (subject, value, origin, mode, artifact)
    return build_run(WOLFBOOT_FACTS, overrides, extra=extra, **kw)


def mcuboot_run(
    overrides: dict[tuple[str, str], Any] | None = None,
    *,
    extra: dict[tuple[str, str], tuple[str, Any, str, str, str]] | None = None,
    **kw: Any,
) -> RunFacts:
    """Typical MCUboot live run (PQC signing refused, E11 unsupported)."""
    return build_run(MCUBOOT_FACTS, overrides, extra=extra, **kw)
