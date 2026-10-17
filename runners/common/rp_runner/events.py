"""Event emission for the ReleaseProof runner protocol (stdlib only, Python >= 3.10).

Mirrors backend/releaseproof/contracts/runner.py. Keep both in sync; the backend validates
every event it receives against the pydantic models.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

STAGES = (
    "PREPARING",
    "DISCOVERY",
    "BUILD_SIGN",
    "EMULATION_TESTS",
)
FAILURE_CLASSES = (
    "ENVIRONMENT_SETUP",
    "BUILD_FAILED",
    "TOOL_FAILURE",
    "TIMEOUT",
    "INCONCLUSIVE",
    "INTERNAL",
)
ORIGINS = ("MEASURED_TOOL", "OBSERVED_EMULATION", "DECLARED")
OUTCOMES = ("PASS", "FAIL", "INCONCLUSIVE", "NOT_EXECUTED", "ERROR")
_MAX_LINE = 3900


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


class EventSink:
    """Serialises events as NDJSON lines through ``write`` (thread-safe)."""

    def __init__(self, run_id: str, artifact_dir: Path, write: Callable[[str], None]) -> None:
        self.run_id = run_id
        self.artifact_dir = artifact_dir
        self._write = write
        self._seq = 0
        self._lock = threading.Lock()
        self._artifact_ids: set[str] = set()
        self._observation_ids: set[str] = set()

    # -------------------------------------------------------------- primitives

    def emit(self, payload: dict[str, Any]) -> None:
        with self._lock:
            event = {"seq": self._seq, "ts": utc_now(), "run_id": self.run_id, **payload}
            self._seq += 1
            self._write(json.dumps(event, separators=(",", ":"), default=str) + "\n")

    def stage(self, stage: str, status: str, message: str = "") -> None:
        assert stage in STAGES, stage
        self.emit({"type": "stage", "stage": stage, "status": status, "message": message})

    def log(self, stream: str, line: str, test_id: str | None = None) -> None:
        payload: dict[str, Any] = {"type": "log", "stream": stream, "line": line[:_MAX_LINE]}
        if test_id:
            payload["test_id"] = test_id
        self.emit(payload)

    def artifact(
        self,
        path: Path,
        *,
        kind: str,
        test_id: str | None = None,
        artifact_id: str | None = None,
    ) -> str:
        """Register a file that already lives under ``artifact_dir``; returns its artifact_id."""
        path = path.resolve()
        rel = path.relative_to(self.artifact_dir.resolve()).as_posix()
        aid = artifact_id or "ART-" + rel.replace("/", "-").replace(".", "_")
        if aid in self._artifact_ids:
            raise ValueError(f"duplicate artifact id {aid}")
        self._artifact_ids.add(aid)
        payload: dict[str, Any] = {
            "type": "artifact",
            "artifact_id": aid,
            "name": path.name,
            "path": rel,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "kind": kind,
        }
        if test_id:
            payload["test_id"] = test_id
        self.emit(payload)
        return aid

    def observation(
        self,
        *,
        observation_id: str,
        test_id: str,
        subject: str,
        fact: str,
        value: Any,
        origin: str,
        acquisition_mode: str,
        parser: str,
        source_artifact_ids: list[str] | None = None,
        locator: str | None = None,
        unit: str | None = None,
    ) -> str:
        assert origin in ORIGINS, origin
        if observation_id in self._observation_ids:
            raise ValueError(f"duplicate observation id {observation_id}")
        self._observation_ids.add(observation_id)
        obs: dict[str, Any] = {
            "observation_id": observation_id,
            "test_id": test_id,
            "subject": subject,
            "fact": fact,
            "value": value,
            "origin": origin,
            "acquisition_mode": acquisition_mode,
            "parser": parser,
            "source_artifact_ids": list(source_artifact_ids or []),
        }
        if locator:
            obs["locator"] = locator
        if unit:
            obs["unit"] = unit
        self.emit({"type": "observation", "observation": obs})
        return observation_id

    def test_result(
        self,
        *,
        test_id: str,
        template_id: str,
        outcome: str,
        expected: str,
        observed: str,
        duration_ms: int,
        observation_ids: list[str] | None = None,
        failure_class: str | None = None,
    ) -> None:
        assert outcome in OUTCOMES, outcome
        payload: dict[str, Any] = {
            "type": "test_result",
            "test_id": test_id,
            "template_id": template_id,
            "outcome": outcome,
            "expected": expected,
            "observed": observed,
            "duration_ms": max(0, int(duration_ms)),
            "observation_ids": list(observation_ids or []),
        }
        if failure_class:
            assert failure_class in FAILURE_CLASSES, failure_class
            payload["failure_class"] = failure_class
        self.emit(payload)

    def error(self, failure_class: str, message: str, test_id: str | None = None) -> None:
        assert failure_class in FAILURE_CLASSES, failure_class
        payload: dict[str, Any] = {
            "type": "error",
            "failure_class": failure_class,
            "message": message[:_MAX_LINE],
        }
        if test_id:
            payload["test_id"] = test_id
        self.emit(payload)

    def done(
        self,
        status: str,
        summary: str = "",
        tool_versions: dict[str, str] | None = None,
        source_pins: dict[str, str] | None = None,
    ) -> None:
        self.emit(
            {
                "type": "done",
                "status": status,
                "summary": summary,
                "tool_versions": dict(tool_versions or {}),
                "source_pins": dict(source_pins or {}),
            }
        )
