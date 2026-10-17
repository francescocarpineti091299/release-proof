"""Evaluation helpers: artifact integrity, evidence views, reproduction manifest."""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from releaseproof.contracts.api import ArtifactView, EvidenceView
from releaseproof.orchestrator.runner_client import safe_relative_path
from releaseproof.profiles import registry


class EvaluationFailure(Exception):
    def __init__(self, failure_class: str, message: str) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.message = message


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=16)
def profile_source(profile_id: str) -> tuple[str, str]:
    """(file name, sha256) of the registry YAML that defines ``profile_id``."""
    for path in sorted(Path(registry.PROFILES_DIR).glob("*.yaml")):
        if path.name == "test_catalog.yaml":
            continue
        raw = path.read_bytes()
        if (yaml.safe_load(raw) or {}).get("id") == profile_id:
            return path.name, sha256_bytes(raw)
    raise EvaluationFailure("INTERNAL", f"profile file for {profile_id} not found")


@lru_cache(maxsize=1)
def catalog_source() -> tuple[str, str]:
    path = Path(registry.PROFILES_DIR) / "test_catalog.yaml"
    return path.name, sha256_bytes(path.read_bytes())


def resolve_artifact_path(runs_dir: Path, row: dict[str, Any]) -> Path | None:
    """Absolute path of an artifact row, or None if it would leave its owner run directory."""
    owner = str(row["owner_run_id"])
    relative = str(row["rel_path"])
    if owner in (".", "..") or not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", owner):
        return None
    if not safe_relative_path(relative):
        return None
    try:
        root = runs_dir.resolve()
        base = (root / owner).resolve()
        target = (base / relative).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    if base.parent != root or target == base or base not in target.parents:
        return None
    return target


def verify_artifacts(runs_dir: Path, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        path = resolve_artifact_path(runs_dir, row)
        if path is None or not path.is_file():
            raise EvaluationFailure(
                "TOOL_FAILURE", f"artifact {row['artifact_id']} missing on the shared volume"
            )
        if sha256_file(path) != row["sha256"]:
            raise EvaluationFailure(
                "TOOL_FAILURE",
                f"artifact {row['artifact_id']} sha256 does not match the runner report",
            )
        if path.stat().st_size != row["size_bytes"]:
            raise EvaluationFailure(
                "TOOL_FAILURE",
                f"artifact {row['artifact_id']} size does not match the runner report",
            )


def artifact_view(run_id: str, row: dict[str, Any]) -> ArtifactView:
    return ArtifactView(
        artifact_id=row["artifact_id"],
        name=row["name"],
        kind=row["kind"],
        sha256=row["sha256"],
        size_bytes=int(row["size_bytes"]),
        test_id=row.get("test_id"),
        url=f"/api/assessments/{run_id}/artifacts/{row['artifact_id']}",
    )


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def _derived_origin(row: dict[str, Any]) -> str:
    if row.get("authority_context") == "DECLARED" or row.get("evidence_kind") == "DECLARATION":
        return "DECLARED"
    if row.get("acquisition_mode") == "EMULATED":
        return "OBSERVED_EMULATION"
    return "MEASURED_TOOL"


def build_evidence_views(
    *,
    run_id: str,
    assessment: dict[str, Any],
    observations: list[dict[str, Any]],
    artifact_rows: list[dict[str, Any]],
    index: dict[str, dict[str, Any]] | None = None,
) -> list[EvidenceView]:
    """Join V1.2 evidence rows with the observations/artifacts they came from."""
    obs_by_id = {o["observation_id"]: o for o in observations}
    art_by_id = {a["artifact_id"]: a for a in artifact_rows}
    art_by_name: dict[str, dict[str, Any]] = {}
    for a in artifact_rows:
        art_by_name.setdefault(a["name"], a)
    index = index or {}
    views: list[EvidenceView] = []
    for row in assessment.get("evidence") or []:
        eid = str(row.get("id"))
        hint = index.get(eid) or {}
        obs_ids = _as_list(hint.get("observation_ids")) or _as_list(
            row.get("observation_ids") or row.get("observation_id")
        )
        linked = [obs_by_id[o] for o in obs_ids if o in obs_by_id]
        refs = _as_list(hint.get("artifact_ids")) or [
            *_as_list(row.get("artifact_ids")),
            *_as_list(row.get("source_artifact_ids")),
            *_as_list(row.get("artifact_refs")),
        ]
        for obs in linked:
            refs.extend(_as_list(obs.get("source_artifact_ids")))
        artifacts: list[ArtifactView] = []
        seen: set[str] = set()
        for ref in refs:
            art = art_by_id.get(ref) or art_by_name.get(ref)
            if art is None or art["artifact_id"] in seen:
                continue
            seen.add(art["artifact_id"])
            artifacts.append(artifact_view(run_id, art))
        origin = hint.get("origin") or (linked[0]["origin"] if linked else _derived_origin(row))
        locator = hint.get("locator") or row.get("locator")
        if locator is None:
            locator = next((o.get("locator") for o in linked if o.get("locator")), None)
        views.append(
            EvidenceView(
                id=eid,
                test_id=row.get("test_id"),
                value=row.get("value"),
                evidence_kind=str(row.get("evidence_kind", "")),
                acquisition_mode=str(row.get("acquisition_mode", "")),
                origin=str(origin),
                run_id=row.get("run_id"),
                artifacts=artifacts,
                locator=locator,
            )
        )
    return views


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def write_manifest(path: Path, manifest: dict[str, Any]) -> str:
    data = canonical_json_bytes(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha256_bytes(data)
