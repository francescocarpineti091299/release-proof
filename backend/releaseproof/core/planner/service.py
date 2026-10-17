"""Interpret gap_planner_mapping_v1.json; no assessment-id branches."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from releaseproof.core.paths import CONTRACT_PACK

_MAPPING_PATH = CONTRACT_PACK / "examples" / "gap_planner_mapping_v1.json"


def load_planner_mapping(path: Path | None = None) -> dict[str, Any]:
    target = path or _MAPPING_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def _entry_matches(
    match: dict[str, Any],
    *,
    gap: dict[str, Any] | None,
    row: dict[str, Any] | None,
) -> bool:
    if not match:
        return False
    if "gap_id" in match:
        return gap is not None and gap.get("gap_id") == match["gap_id"]
    if row is None:
        return False
    for key, value in match.items():
        if key == "requirement_id":
            rid = row.get("requirement_id") or row.get("invariant_id")
            if rid != value:
                return False
        elif row.get(key) != value:
            return False
    return True


def _plan_item(
    *,
    source_id: str,
    source_kind: str,
    requirement_id: str | None,
    entry: dict[str, Any],
    gap: dict[str, Any] | None,
) -> dict[str, Any]:
    reason = (gap or {}).get("reason") or entry.get("default_reason") or ""
    status = entry.get("default_status") or "MISSING"
    if gap and gap.get("gap_type") == "NOT_EXECUTABLE":
        status = "NOT_EXECUTABLE"
    return {
        "source_id": source_id,
        "source_kind": source_kind,
        "requirement_id": requirement_id or (gap or {}).get("requirement_id"),
        "evidence_requirement_id": entry.get("evidence_requirement_id"),
        "label": entry.get("label"),
        "suggested_test_id": entry.get("suggested_test_id"),
        "suggested_open_question": entry.get("suggested_open_question"),
        "status": status,
        "reason": reason,
        "why_needed": entry.get("label"),
    }


def _gap_still_drives_result(result: dict[str, Any], requirement_id: str | None) -> bool:
    """Keep a catalog gap only while some row for that id is still open or violated."""
    if not requirement_id:
        return True
    rows = [
        row
        for row in (result.get("requirement_evaluation_results") or [])
        + (result.get("invariant_evaluation_results") or [])
        if (row.get("requirement_id") or row.get("invariant_id")) == requirement_id
    ]
    if not rows:
        return True
    return any(
        row.get("state") in {"UNKNOWN", "OPEN_CONDITION", "VIOLATED", "NOT_EXECUTED"}
        for row in rows
    )


def build_gap_plan(
    assessment: dict[str, Any],
    result: dict[str, Any],
    *,
    mapping: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return planner rows for catalog gaps and critical UNKNOWN rows."""
    spec = mapping or load_planner_mapping()
    entries = spec.get("entries") or []
    plans: list[dict[str, Any]] = []
    seen: set[str] = set()

    for gap in assessment.get("evidence_gaps") or []:
        gid = str(gap.get("gap_id") or "")
        if not _gap_still_drives_result(result, gap.get("requirement_id")):
            continue
        for entry in entries:
            match = entry.get("match") or {}
            if not _entry_matches(match, gap=gap, row=None):
                continue
            key = f"gap:{gid}"
            if key in seen:
                break
            seen.add(key)
            plans.append(
                _plan_item(
                    source_id=gid,
                    source_kind="EVIDENCE_GAP",
                    requirement_id=gap.get("requirement_id"),
                    entry=entry,
                    gap=gap,
                )
            )
            break

    for row in (result.get("requirement_evaluation_results") or []) + (
        result.get("invariant_evaluation_results") or []
    ):
        if not row.get("critical_for_verdict"):
            continue
        if row.get("state") not in {"UNKNOWN", "OPEN_CONDITION"}:
            continue
        rid = row.get("requirement_id") or row.get("invariant_id")
        for entry in entries:
            match = entry.get("match") or {}
            if "gap_id" in match:
                continue
            if not _entry_matches(match, gap=None, row=row):
                continue
            key = f"row:{rid}:{row.get('phase')}:{row.get('subject_ref')}"
            if key in seen:
                break
            seen.add(key)
            kind = "INVARIANT" if row.get("invariant_id") else "REQUIREMENT"
            plans.append(
                _plan_item(
                    source_id=key,
                    source_kind=kind,
                    requirement_id=str(rid) if rid else None,
                    entry=entry,
                    gap=None,
                )
            )
            break

    return plans


__all__ = ["build_gap_plan", "load_planner_mapping"]
