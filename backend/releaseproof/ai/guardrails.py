"""Output parsing and guardrails. The LLM proposes; these checks decide what is accepted."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from releaseproof.ai.context import VERDICT_KEYS, VERDICT_WORDS
from releaseproof.contracts.ai import AlternativesProposal, NarrativeReport, TestPlanProposal

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
_VERDICT_RE = re.compile(r"\b(" + "|".join(VERDICT_WORDS) + r")\b")


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract one JSON object from a model reply (tolerates <think> blocks and code fences)."""
    cleaned = _THINK_RE.sub("", text or "").strip()
    if cleaned.lower().startswith("<think>"):  # unterminated reasoning block
        raise ValueError("reply contains only an unterminated <think> block")
    match = _FENCE_RE.match(cleaned)
    if match:
        cleaned = match.group(1).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("reply is not JSON") from None
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"reply is not valid JSON: {exc.msg} at char {exc.pos}") from None
    if not isinstance(value, dict):
        raise ValueError("reply JSON is not an object")
    return value


def format_validation_error(exc: ValidationError | ValueError) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for err in exc.errors()[:8]:
            loc = ".".join(str(p) for p in err.get("loc", ()))
            parts.append(f"{loc or '<root>'}: {err.get('msg')}")
        return "schema validation failed: " + "; ".join(parts)
    return str(exc)


def _verdict_words(texts: Iterable[str]) -> set[str]:
    found: set[str] = set()
    for text in texts:
        found.update(_VERDICT_RE.findall(text or ""))
    return found


# ------------------------------------------------------------------ planner


def sanitize_plan(
    proposal: TestPlanProposal, *, allowed: list[str], required: list[str]
) -> tuple[TestPlanProposal, list[str], list[str]]:
    """Drop templates outside the allowlist; required templates cannot be skipped.

    Returns (sanitized proposal, blocked template ids, notes).
    """
    allowed_set, required_set = set(allowed), set(required)
    blocked: list[str] = []
    notes: list[str] = []
    selected, seen = [], set()
    for item in proposal.selected:
        if item.template_id not in allowed_set:
            if item.template_id not in blocked:
                blocked.append(item.template_id)
            continue
        if item.template_id in seen:
            continue
        seen.add(item.template_id)
        selected.append(item)
    skipped = []
    for item in proposal.skipped:
        if item.template_id not in allowed_set:
            if item.template_id not in blocked:
                blocked.append(item.template_id)
        elif item.template_id in required_set:
            notes.append(f"required template {item.template_id} cannot be skipped")
        elif item.template_id not in seen:
            seen.add(item.template_id)
            skipped.append(item)
    if blocked:
        notes.insert(
            0, f"guardrail dropped template(s) not registered for this change: {', '.join(blocked)}"
        )
    clean = TestPlanProposal(
        selected=selected,
        skipped=skipped,
        suggested_new_tests=proposal.suggested_new_tests,
        summary=proposal.summary,
    )
    return clean, blocked, notes


# ------------------------------------------------------------------ explainer


def check_report(
    report: NarrativeReport, *, verdicts: dict[str, str | None], citable: Iterable[str]
) -> list[str]:
    problems: list[str] = []
    echo = {k: report.verdict_echo.get(k, "<missing>") for k in VERDICT_KEYS}  # type: ignore[call-overload]
    if set(report.verdict_echo) != set(VERDICT_KEYS) or echo != verdicts:
        problems.append(
            f"verdict_echo {json.dumps(dict(report.verdict_echo))} does not equal the engine "
            f"verdicts {json.dumps(verdicts)}"
        )
    allowed = set(citable)
    statements = [*report.main_causes, *report.verified, *report.unknowns]
    bad = sorted({c for s in statements for c in s.citations if c not in allowed})
    if bad:
        problems.append(f"citations not present in the context: {', '.join(bad[:10])}")
    actual = {v for v in verdicts.values() if v}
    texts = [report.headline, report.executive_summary, *(s.text for s in statements)]
    stray = sorted(_verdict_words(texts) - actual)
    if stray:
        problems.append(f"text states verdict(s) the engine did not produce: {', '.join(stray)}")
    return problems


# ------------------------------------------------------------------ alternatives


def check_alternatives(
    proposal: AlternativesProposal,
    *,
    plan_ids: list[str],
    blocking: list[str],
    external_validation: set[str],
) -> list[str]:
    problems: list[str] = []
    allowed_plans, blocking_set = set(plan_ids), set(blocking)
    seen: set[str] = set()
    for p in proposal.proposals:
        if p.plan_id not in allowed_plans:
            problems.append(f"plan_id {p.plan_id!r} is not an allowed alternative")
            continue
        if p.plan_id in seen:
            problems.append(f"plan_id {p.plan_id!r} proposed twice")
        seen.add(p.plan_id)
        if not p.addresses:
            problems.append(f"{p.plan_id}: 'addresses' is empty")
        extra = sorted(set(p.addresses) - blocking_set)
        if extra:
            problems.append(f"{p.plan_id}: addresses non-blocking IDs {', '.join(extra)}")
        texts = [p.title, p.rationale, *p.preconditions, *p.tradeoffs, *p.evidence_still_needed]
        words = _verdict_words(texts)
        if words:
            problems.append(f"{p.plan_id}: claims a verdict ({', '.join(sorted(words))})")
        if p.plan_id in external_validation and not p.evidence_still_needed:
            problems.append(
                f"{p.plan_id}: requires external validation but evidence_still_needed is empty"
            )
    extra_na = sorted(set(proposal.not_addressable) - blocking_set)
    if extra_na:
        problems.append(f"not_addressable contains non-blocking IDs {', '.join(extra_na)}")
    return problems


__all__ = [
    "check_alternatives",
    "check_report",
    "format_validation_error",
    "parse_json_object",
    "sanitize_plan",
]
