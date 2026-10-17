"""Strict preflight policy over an independently verified portable evidence pack.

This gate authorizes no OTA action and is not proof of fleet-wide/hardware safety.
It deliberately has no override for CONDITIONAL, UNKNOWN or candidate-only success.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, BinaryIO
from zipfile import BadZipFile, ZipFile

from releaseproof.api.evidence_pack import MAX_PACK_BYTES, MAX_PACK_FILES, PACK_VERSION
from releaseproof.contracts.api import ResultView, RunView
from releaseproof.core.assurance.service import evaluate
from releaseproof.core.canonical.service import compute_canonical_hash


class InvalidPack(ValueError):
    """Incomplete, corrupted, incoherent or unsupported evidence bundle."""


def verify_pack(source: Path | BinaryIO) -> dict[str, Any]:
    """Verify bytes, manifest bindings and engine replay; never extract archive paths."""
    try:
        return _verify_pack(source)
    except InvalidPack:
        raise
    except (BadZipFile, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as exc:
        raise InvalidPack(f"malformed evidence pack ({type(exc).__name__})") from exc


def _verify_pack(source: Path | BinaryIO) -> dict[str, Any]:
    with ZipFile(source) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        if (
            len(names) != len(set(names))
            or len(names) > MAX_PACK_FILES + 1
            or sum(i.file_size for i in infos) > MAX_PACK_BYTES + 1024 * 1024
        ):
            raise InvalidPack("duplicate files or evidence pack limit exceeded")
        required = {"pack-index.json", "run.json", "result.json", "manifest.json"}
        if not required <= set(names):
            raise InvalidPack("required evidence pack documents missing")
        index = json.loads(archive.read("pack-index.json"))
        if index.get("version") != PACK_VERSION:
            raise InvalidPack("unsupported evidence pack version")
        entries = index["files"]
        indexed = [e["path"] for e in entries]
        if len(indexed) != len(set(indexed)) or set(indexed) != set(names) - {"pack-index.json"}:
            raise InvalidPack("pack index does not cover exactly the archive")
        blobs = {}
        for entry in entries:
            name = entry["path"]
            if not (
                name
                in {
                    "run.json",
                    "result.json",
                    "manifest.json",
                    "ai-traces.json",
                    "dossier.md",
                    "README.md",
                }
                or re.fullmatch(r"artifacts/[A-Za-z0-9_][A-Za-z0-9_.-]{0,159}", name)
            ):
                raise InvalidPack("unexpected pack path")
            blob = archive.read(name)
            if (
                hashlib.sha256(blob).hexdigest() != entry["sha256"]
                or len(blob) != entry["size_bytes"]
            ):
                raise InvalidPack("pack file digest or size mismatch")
            blobs[name] = blob
    run = RunView.model_validate_json(blobs["run.json"]).model_dump(mode="json")
    result = ResultView.model_validate_json(blobs["result.json"]).model_dump(mode="json")
    manifest = json.loads(blobs["manifest.json"])
    if not (run["run_id"] == result["run_id"] == manifest.get("run_id") == index.get("run_id")):
        raise InvalidPack("run identity mismatch")
    if hashlib.sha256(blobs["manifest.json"]).hexdigest() != result["manifest_sha256"]:
        raise InvalidPack("manifest digest mismatch")
    assessment_hash = compute_canonical_hash(result["assessment"])
    semantic = result["result"]
    result_hash = compute_canonical_hash(semantic)
    if (
        (manifest.get("assessment") or {}).get("canonical_hash") != assessment_hash
        or semantic.get("canonical_hash") != result_hash
        or (manifest.get("result") or {}).get("canonical_hash") != result_hash
        or (run.get("verdict") or {}).get("canonical_hash") != result_hash
    ):
        raise InvalidPack("canonical document hash mismatch")
    replay = evaluate(result["assessment"]).model_dump(mode="json")
    if replay.get("canonical_hash") != result_hash:
        raise InvalidPack("current engine replay differs; preserve pack and review its release")
    for key in ("migration", "candidate", "transition"):
        if run["verdict"].get(key) != semantic.get(f"{key}_verdict") or manifest["result"].get(
            f"{key}_verdict"
        ) != semantic.get(f"{key}_verdict"):
            raise InvalidPack("verdict phase mismatch")
    if (
        manifest["result"].get("official") is not False
        or semantic.get("official") is not False
        or manifest["result"].get("lifecycle") != semantic.get("lifecycle")
        or run["verdict"].get("lifecycle") != semantic.get("lifecycle")
    ):
        raise InvalidPack("result lifecycle or official flag mismatch")
    if (
        manifest.get("mode") != run["mode"]
        or (manifest.get("profile") or {}).get("id") != run["configuration_id"]
        or manifest["profile"].get("version") != run["configuration_version"]
        or (manifest.get("change") or {}).get("change_id") != run["change_id"]
        or (manifest.get("plan") or {}).get("plan_id") != run["plan_id"]
    ):
        raise InvalidPack("profile, change, plan or mode binding mismatch")
    if run["mode"] == "LIVE":

        def test_binding(test: dict[str, Any]) -> tuple[str, str, str]:
            return test["template_id"], test["test_id"], test["outcome"]

        recorded = [test_binding(test) for test in manifest["test_results"]]
        exposed = [test_binding(test) for test in run["tests"]]
        planned = [test["template_id"] for test in manifest["planned_tests"]]
        if (
            len(recorded) != len(set(recorded))
            or sorted(recorded) != sorted(exposed)
            or len(planned) != len(set(planned))
            or set(planned) != {test["template_id"] for test in run["tests"]}
        ):
            raise InvalidPack("planned/executed test binding mismatch")
    artifact_names = []
    for artifact in manifest["artifacts"]:
        name = f"artifacts/{artifact['artifact_id']}"
        artifact_names.append(name)
        blob = blobs.get(name)
        if (
            blob is None
            or hashlib.sha256(blob).hexdigest() != artifact["sha256"]
            or len(blob) != artifact["size_bytes"]
        ):
            raise InvalidPack("manifest artifact missing or changed")
    if len(artifact_names) != len(set(artifact_names)) or set(artifact_names) != {
        n for n in blobs if n.startswith("artifacts/")
    }:
        raise InvalidPack("manifest artifact inventory mismatch")
    return {"run": run, "result": result, "manifest": manifest}


def release_decision(
    pack: dict[str, Any],
    *,
    configuration: str,
    change: str,
    plan: str,
) -> dict[str, Any]:
    """Call only with verify_pack output. SUCCEEDED means completed, not deployable."""
    run, result, manifest = pack["run"], pack["result"]["result"], pack["manifest"]
    reasons = []
    if (run["configuration_id"], run["change_id"], run["plan_id"]) != (configuration, change, plan):
        reasons.append("Run does not match the configuration/change/plan pinned by CI.")
    if run["status"] != "SUCCEEDED" or run["mode"] != "LIVE" or run.get("failure"):
        reasons.append("A successful fresh LIVE execution is required, not replay/re-evaluation.")
    if manifest["profile"].get("status") != "SUPPORTED":
        reasons.append("Profile was not SUPPORTED at execution time.")
    if result.get("official") is not False or result.get("lifecycle") != "COMPLETED":
        reasons.append("Completed non-official engineering result required.")
    for phase in ("migration", "candidate", "transition"):
        value = result.get(f"{phase}_verdict")
        if value != "COMPATIBLE":
            reasons.append(f"{phase}: {value or 'missing'}; only COMPATIBLE passes.")
    if result.get("errors") or result.get("conditions"):
        reasons.append("Engine errors or unresolved conditions block the release.")
    rows = [
        *result.get("requirement_evaluation_results", []),
        *result.get("invariant_evaluation_results", []),
    ]
    if not rows or any(
        r.get("critical_for_verdict") and r.get("state") != "SATISFIED" for r in rows
    ):
        reasons.append("Critical checks are absent, violated, unknown or conditional.")
    required = set(manifest["change"].get("required_templates") or [])
    executed = {t["template_id"] for t in run["tests"] if t["outcome"] in {"PASS", "FAIL"}}
    if not required or not required <= executed:
        reasons.append("Required test coverage is incomplete.")
    if any(t["outcome"] in {"ERROR", "INCONCLUSIVE", "NOT_EXECUTED"} for t in run["tests"]):
        reasons.append("A tool/test did not complete conclusively.")
    if not any(t["negative"] and t["outcome"] == "PASS" for t in run["tests"]):
        reasons.append("No passing authentication-negative test was observed.")
    return {
        "policy": "releaseproof.preflight/1",
        "run_id": run["run_id"],
        "decision": "BLOCK" if reasons else "PASS",
        "reasons": reasons,
        "canonical_hash": result["canonical_hash"],
        "official": False,
        "scope": "Supported emulated configuration only; not OTA authorization or certification.",
    }
