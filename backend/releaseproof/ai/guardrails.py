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
_VERDICT_RE = re.compile(r"\b(" + "|".join(VERDICT_WORDS) + r")\b", re.I)
_DEPLOYMENT_CLAIM_RE = re.compile(
    r"\b(?:safe to deploy|guaranteed safe|certified safe|fully secure)\b",
    re.I,
)


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
        found.update(word.upper() for word in _VERDICT_RE.findall(text or ""))
    return found


def _check_verdict_phases(text: str, verdicts: dict[str, Any]) -> list[str]:
    """Check explicit labels against their phase, not against any verdict in the run.

    This is a conservative lexical check, not proof that free-form prose is entailed.
    Markdown formatting must not hide or separate a phase/verdict assertion.
    """
    token = re.compile(
        r"\b(migration|candidate|transition|COMPATIBLE|CONDITIONAL|INDETERMINATE|INCOMPATIBLE)\b",
        re.I,
    )
    for clause in re.split(r"[.;\n]", text):
        phase = None
        for match in token.finditer(clause):
            word = match.group().lower()
            if word in VERDICT_KEYS:
                phase = word
            elif phase is None or word.upper() != verdicts.get(phase):
                return ["verdict claim does not match its engine phase"]
    return []


def check_assistant(text: str, context: dict[str, Any]) -> list[str]:
    """Validate buffered chat before *any* generated text reaches the browser.

    This enforces ID existence and phase-specific verdicts, not semantic entailment of prose.
    The model has no authority to certify a deployment.
    """
    verdicts = context.get("verdicts") or context.get("engine_verdicts") or {}
    result = context.get("result") or {}
    if result:
        verdicts = {key: result.get(f"{key}_verdict") for key in VERDICT_KEYS}
    elif not verdicts:
        verdicts = (context.get("run") or {}).get("verdict") or {}
    allowed = set(context.get("evidence_ids") or [])

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"id", "gap_id", "requirement_id", "invariant_id"} and isinstance(
                    child, str
                ):
                    allowed.add(child)
                elif isinstance(child, dict | list):
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for key in ("assessment", "result", "evidence", "requirements", "invariants", "gaps"):
        collect(context.get(key))
    # Validate every ID-shaped citation, not only known prefixes: an invented
    # [FAKE-PROOF] must not evade checks by using a different namespace.
    cited = set(re.findall(r"\[([A-Z][A-Za-z0-9_.-]*)\]", text))
    problems = []
    if cited - allowed:
        problems.append("unknown citations: " + ", ".join(sorted(cited - allowed)))
    if allowed and not cited:
        problems.append("answer has no verifiable citation")
    if _DEPLOYMENT_CLAIM_RE.search(text):
        problems.append("unsupported deployment certification")
    problems.extend(_check_verdict_phases(text, verdicts))
    return problems


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
    for text in texts:
        problems.extend(_check_verdict_phases(text, verdicts))
        if _DEPLOYMENT_CLAIM_RE.search(text):
            problems.append("unsupported deployment certification")
    return problems


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
        # A capability description such as "PQC-compatible bootloader" is not an
        # assessment verdict. Reject enum labels and explicit verdict assertions,
        # without rejecting ordinary lower-case technical adjectives.
        words = set()
        for text in texts:
            words.update(re.findall(r"\b(" + "|".join(VERDICT_WORDS) + r")\b", text))
            claims = re.findall(
                r"\b(?:migration|candidate|transition|plan|assessment|verdict)\b\s*"
                r"(?:(?:verdict|result)\s*)?"
                r"(?:is|will be|would be|should be|becomes|must be|[:=\-])\s*"
                r"(compatible|conditional|indeterminate|incompatible)\b",
                text,
                re.I,
            )
            words.update(word.upper() for word in claims)
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
