"""Compact, token-bounded contexts for the LLM modules, plus the ID sets the guardrails enforce."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from releaseproof.contracts.profile import ChangeScenario, Profile, TestTemplate

VERDICT_KEYS = ("migration", "candidate", "transition")
VERDICT_WORDS = ("COMPATIBLE", "CONDITIONAL", "INDETERMINATE", "INCOMPATIBLE")
BLOCKING_STATES = ("VIOLATED", "UNKNOWN")


def _clip(value: Any, limit: int) -> Any:
    """Scalars are kept; long strings and structures are clipped to a JSON string of ``limit``."""
    if value is None or isinstance(value, bool | int | float):
        return value
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return value
    return text[: max(limit - 1, 0)] + "…"


def _size(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str))


def engine_verdicts(result: dict[str, Any]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for key in VERDICT_KEYS:
        value = result.get(f"{key}_verdict")
        out[key] = None if value is None else str(value)
    return out


@dataclass
class PlannerContext:
    data: dict[str, Any]
    allowed: list[str]
    required: list[str]
    optional: list[str]


def planner_context(
    profile: Profile, change: ChangeScenario, templates: list[TestTemplate]
) -> PlannerContext:
    by_id = {t.template_id: t for t in templates}
    required = [t for t in change.required_templates if t in by_id]
    optional = [t for t in change.optional_templates if t in by_id and t not in required]
    allowed = [*required, *optional]
    data = {
        "profile": {
            "id": profile.id,
            "title": profile.title,
            "board": {"name": profile.board.name, "soc": profile.board.soc},
            "bootloader": {
                "family": profile.bootloader.family,
                "name": profile.bootloader.name,
                "version_label": profile.bootloader.version_label,
            },
            "known_limitations": [_clip(x, 200) for x in profile.known_limitations[:6]],
        },
        "change": {
            "change_id": change.change_id,
            "title": change.title,
            "summary": _clip(change.summary, 500),
            "from_scheme": change.from_scheme,
            "to_scheme": change.to_scheme,
            "default_plan_title": change.default_plan_title,
        },
        "templates": [
            {
                "template_id": tid,
                "test_id": by_id[tid].test_id,
                "title": by_id[tid].title,
                "description": _clip(by_id[tid].description, 300),
                "negative": by_id[tid].negative,
                "expected": _clip(by_id[tid].expected, 160),
                "est_seconds": by_id[tid].est_seconds,
                "required": tid in required,
            }
            for tid in allowed
        ],
    }
    return PlannerContext(data=data, allowed=allowed, required=required, optional=optional)


def _group_results(
    rows: list[dict[str, Any]], id_key: str, criteria: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        rid = row.get(id_key)
        if not isinstance(rid, str):
            continue
        entry = grouped.setdefault(
            rid,
            {
                "id": rid,
                "critical": bool(row.get("critical_for_verdict")),
                "results": [],
                "evidence_refs": [],
                "gap_refs": [],
            },
        )
        if criteria and rid in criteria and "criterion" not in entry:
            entry["criterion"] = _clip(criteria[rid], 240)
        entry["critical"] = entry["critical"] or bool(row.get("critical_for_verdict"))
        entry["results"].append(
            f"{row.get('phase')}/{row.get('subject_type')}/{row.get('subject_ref')}="
            f"{row.get('state')}"
        )
        for key in ("evidence_refs", "gap_refs"):
            for ref in row.get(key) or []:
                if isinstance(ref, str) and ref not in entry[key]:
                    entry[key].append(ref)
        findings = row.get("findings") or []
        if findings:
            entry.setdefault("findings", [])
            entry["findings"].extend(_clip(f, 200) for f in findings[:3])
    for entry in grouped.values():
        states = {r.rsplit("=", 1)[-1] for r in entry["results"]}
        entry["worst_state"] = next(
            (s for s in ("VIOLATED", "UNKNOWN", "OPEN_CONDITION", "SATISFIED") if s in states),
            sorted(states)[0] if states else "UNKNOWN",
        )
    return list(grouped.values())


def _criteria(assessment: dict[str, Any]) -> dict[str, str]:
    reqs = ((assessment.get("profile") or {}).get("requirements")) or []
    return {
        r["id"]: str(r.get("criterion", ""))
        for r in reqs
        if isinstance(r, dict) and isinstance(r.get("id"), str)
    }


def _gaps(assessment: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for gap in assessment.get("evidence_gaps") or []:
        if isinstance(gap, dict) and isinstance(gap.get("gap_id"), str):
            out.append(
                {
                    "gap_id": gap["gap_id"],
                    "requirement_id": gap.get("requirement_id"),
                    "critical": gap.get("critical"),
                    "reason": _clip(gap.get("reason"), 200),
                    "requested_evidence": _clip(gap.get("requested_evidence"), 160),
                }
            )
    return out


def _evidence(assessment: dict[str, Any], value_limit: int) -> list[dict[str, Any]]:
    out = []
    for ev in assessment.get("evidence") or []:
        if isinstance(ev, dict) and isinstance(ev.get("id"), str):
            out.append(
                {
                    "id": ev["id"],
                    "test_id": ev.get("test_id"),
                    "kind": ev.get("evidence_kind"),
                    "acquisition_mode": ev.get("acquisition_mode"),
                    "status": ev.get("status"),
                    "value": _clip(ev.get("value"), value_limit),
                }
            )
    return out


def _tests(test_results: list[dict[str, Any]], observed_limit: int) -> list[dict[str, Any]]:
    out = []
    for t in test_results:
        if not isinstance(t, dict):
            continue
        out.append(
            {
                "test_id": t.get("test_id"),
                "template_id": t.get("template_id"),
                "outcome": t.get("outcome"),
                "negative": t.get("negative"),
                "expected": _clip(t.get("expected"), 120),
                "observed": _clip(t.get("observed"), observed_limit),
                "failure_class": t.get("failure_class"),
            }
        )
    return out


@dataclass
class ExplainContext:
    data: dict[str, Any]
    verdicts: dict[str, str | None]
    citable: list[str]
    blocking: list[str] = field(default_factory=list)


def explain_context(
    *,
    profile: Profile,
    change: ChangeScenario,
    plan_id: str,
    assessment: dict[str, Any],
    result: dict[str, Any],
    test_results: list[dict[str, Any]],
    budget_chars: int,
) -> ExplainContext:
    verdicts = engine_verdicts(result)
    requirements = _group_results(
        result.get("requirement_evaluation_results") or [], "requirement_id", _criteria(assessment)
    )
    invariants = _group_results(result.get("invariant_evaluation_results") or [], "invariant_id")
    data: dict[str, Any] = {
        "engine_verdicts": verdicts,
        "lifecycle": result.get("lifecycle"),
        "official": False,
        "configuration": {"id": profile.id, "bootloader": profile.bootloader.name},
        "change": {
            "title": change.title,
            "from_scheme": change.from_scheme,
            "to_scheme": change.to_scheme,
            "plan_id": plan_id,
        },
        "requirements": requirements,
        "invariants": invariants,
        "findings": [_clip(f, 300) for f in (result.get("findings") or [])[:8]],
        "conditions": [_clip(c, 200) for c in (result.get("conditions") or [])[:6]],
        "errors": [_clip(e, 200) for e in (result.get("errors") or [])[:6]],
        "gaps": _gaps(assessment),
        "evidence": _evidence(assessment, 200),
        "tests": _tests(test_results, 240),
    }
    referenced = {
        ref for group in (requirements, invariants) for e in group for ref in e["evidence_refs"]
    }
    # Shrink step by step until the context fits the budget.
    steps = [
        lambda d: d.update(evidence=_evidence(assessment, 80), tests=_tests(test_results, 100)),
        lambda d: d.update(evidence=[e for e in d["evidence"] if e["id"] in referenced]),
        lambda d: d.update(findings=d["findings"][:3], conditions=d["conditions"][:3]),
        lambda d: [e.pop("findings", None) for e in (*d["requirements"], *d["invariants"])],
        lambda d: d.update(
            evidence=_evidence_ids_only(d["evidence"]), tests=_tests(test_results, 40)
        ),
    ]
    for step in steps:
        if _size(data) <= budget_chars:
            break
        step(data)

    citable: list[str] = []
    for e in data["evidence"]:
        citable.append(e["id"])
    for group in (requirements, invariants):
        for e in group:
            citable.append(e["id"])
            citable.extend(e["evidence_refs"])
            citable.extend(e["gap_refs"])
    citable.extend(g["gap_id"] for g in data["gaps"])
    blocking = [
        e["id"]
        for e in (*requirements, *invariants)
        if e["critical"] and e["worst_state"] in BLOCKING_STATES
    ]
    return ExplainContext(
        data=data, verdicts=verdicts, citable=list(dict.fromkeys(citable)), blocking=blocking
    )


def _evidence_ids_only(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": e["id"], "test_id": e.get("test_id"), "value": _clip(e.get("value"), 30)}
        for e in evidence
    ]


@dataclass
class AlternativesContext:
    data: dict[str, Any]
    plan_ids: list[str]
    blocking: list[str]
    external_validation: set[str]


def alternatives_context(
    *,
    profile: Profile,
    change: ChangeScenario,
    plan_id: str,
    assessment: dict[str, Any],
    result: dict[str, Any],
) -> AlternativesContext:
    criteria = _criteria(assessment)
    rows = [
        *(
            {**g, "kind": "requirement"}
            for g in _group_results(
                result.get("requirement_evaluation_results") or [], "requirement_id", criteria
            )
        ),
        *(
            {**g, "kind": "invariant"}
            for g in _group_results(
                result.get("invariant_evaluation_results") or [], "invariant_id"
            )
        ),
    ]
    blocking_rows = [r for r in rows if r["critical"] and r["worst_state"] in BLOCKING_STATES]
    for r in blocking_rows:
        r.pop("findings", None)
        r.pop("critical", None)
    gap_ids = {g for r in blocking_rows for g in r["gap_refs"]}
    alternatives = [a for a in change.alternatives if a.plan_id != plan_id]
    data = {
        "engine_verdicts": engine_verdicts(result),
        "configuration": {"id": profile.id, "bootloader": profile.bootloader.name},
        "change": {
            "title": change.title,
            "from_scheme": change.from_scheme,
            "to_scheme": change.to_scheme,
            "evaluated_plan_id": plan_id,
        },
        "blocking": blocking_rows,
        "gaps": [g for g in _gaps(assessment) if g["gap_id"] in gap_ids],
        "known_limitations": [_clip(x, 200) for x in profile.known_limitations[:6]],
        "alternatives": [
            {
                "plan_id": a.plan_id,
                "title": a.title,
                "description": _clip(a.description, 400),
                "mechanism": a.mechanism,
                "status": a.status,
                "requires_rerun_tests": a.requires_rerun_tests,
            }
            for a in alternatives
        ],
    }
    return AlternativesContext(
        data=data,
        plan_ids=[a.plan_id for a in alternatives],
        blocking=[r["id"] for r in blocking_rows],
        external_validation={
            a.plan_id for a in alternatives if a.status == "REQUIRES_EXTERNAL_VALIDATION"
        },
    )


def assistant_context(context: dict[str, Any], budget_chars: int) -> Any:
    if _size(context) <= budget_chars:
        return context
    text = json.dumps(context, ensure_ascii=False, separators=(",", ":"), default=str)
    return {"truncated": True, "context_json_prefix": text[:budget_chars]}


__all__ = [
    "AlternativesContext",
    "BLOCKING_STATES",
    "ExplainContext",
    "PlannerContext",
    "VERDICT_KEYS",
    "VERDICT_WORDS",
    "alternatives_context",
    "assistant_context",
    "engine_verdicts",
    "explain_context",
    "planner_context",
]
