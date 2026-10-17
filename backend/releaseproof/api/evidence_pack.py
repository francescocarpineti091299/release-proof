"""Portable review bundle. Hash the exact bytes archived, never publish a partial ZIP."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Any, BinaryIO
from zipfile import ZIP_DEFLATED, ZipFile

from releaseproof.orchestrator.evaluation import (
    EvaluationFailure,
    canonical_json_bytes,
    resolve_artifact_path,
)

PACK_VERSION = "releaseproof.evidence-pack/1"
MAX_PACK_BYTES = 64 * 1024 * 1024
MAX_PACK_FILES = 512
NOTICE = """# ReleaseProof evidence pack

Non-official engineering assessment (official=false), not certification.
Scope: a pinned configuration and migration plan, not every deployed device.
Renode emulation is not hardware validation. Interrupted-update recovery and
power-loss safety are not demonstrated. AI prose is advisory, not a verdict.
Re-evaluation may reuse parent artifacts; see manifest owner_run_id/evidence_run_id.

pack-index.json records SHA-256 and byte length of the files in this archive.
These hashes detect changes, not authenticity, hardware identity or trusted acquisition.
Keep the original manifest and result hashes; do not rewrite historical assessments.
The pack may contain upstream firmware binaries: review THIRD_PARTY_NOTICES.md and
source/licensing obligations before redistributing it.
"""


def build_evidence_pack(
    *,
    runs_dir: Path,
    run: dict[str, Any],
    result: dict[str, Any],
    artifacts: list[dict[str, Any]],
    traces: list[dict[str, Any]],
) -> BinaryIO:
    """Return a rewound temporary ZIP, owned by the caller. Bound disk and memory use."""
    if len(artifacts) + 5 > MAX_PACK_FILES:
        raise EvaluationFailure("TOOL_FAILURE", "evidence pack has too many files")
    # Ownership transfers to the response, whose iterator/background callback closes it.
    spool = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")  # noqa: SIM115
    entries: list[dict[str, Any]] = []
    names: set[str] = set()
    total = 0

    def record(name: str, digest: str, size: int) -> None:
        entries.append({"path": name, "sha256": digest, "size_bytes": size})

    try:
        with ZipFile(spool, "w", compression=ZIP_DEFLATED) as archive:

            def add(name: str, blob: bytes) -> None:
                nonlocal total
                total += len(blob)
                if total > MAX_PACK_BYTES:
                    raise EvaluationFailure("TOOL_FAILURE", "evidence pack exceeds size limit")
                archive.writestr(name, blob)
                record(name, hashlib.sha256(blob).hexdigest(), len(blob))

            add("run.json", canonical_json_bytes(run))
            add("result.json", canonical_json_bytes(result))
            add("ai-traces.json", canonical_json_bytes(traces))
            add("dossier.md", (result.get("dossier_markdown") or "").encode("utf-8"))
            add("README.md", NOTICE.encode("utf-8"))
            for row in artifacts:
                aid = row["artifact_id"]
                if not isinstance(aid, str) or not re.fullmatch(
                    r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,159}", aid
                ):
                    raise EvaluationFailure("TOOL_FAILURE", "invalid artifact id in pack")
                name = "manifest.json" if aid == "MANIFEST" else f"artifacts/{aid}"
                path = resolve_artifact_path(runs_dir, row)
                if name in names or path is None or not path.is_file():
                    raise EvaluationFailure("TOOL_FAILURE", "invalid or missing pack artifact")
                names.add(name)
                digest = hashlib.sha256()
                size = 0
                with path.open("rb") as source, archive.open(name, "w") as target:
                    for chunk in iter(lambda: source.read(65536), b""):
                        size += len(chunk)
                        total += len(chunk)
                        if total > MAX_PACK_BYTES:
                            raise EvaluationFailure("TOOL_FAILURE", "pack exceeds size limit")
                        digest.update(chunk)
                        target.write(chunk)
                if digest.hexdigest() != row["sha256"] or size != row["size_bytes"]:
                    raise EvaluationFailure("TOOL_FAILURE", "pack artifact integrity check failed")
                record(name, digest.hexdigest(), size)
            if "manifest.json" not in names:
                raise EvaluationFailure("TOOL_FAILURE", "manifest is missing")
            archive.writestr(
                "pack-index.json",
                canonical_json_bytes(
                    {
                        "version": PACK_VERSION,
                        "run_id": run["run_id"],
                        "files": entries,
                    }
                ),
            )
        spool.seek(0)
        return spool
    except BaseException:
        spool.close()
        raise
