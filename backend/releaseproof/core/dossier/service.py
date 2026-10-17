"""Deterministic Markdown view of an assessment result."""

from __future__ import annotations

from typing import Any


def render_dossier_markdown(
    assessment: dict[str, Any],
    result: dict[str, Any],
    *,
    gap_plan: list[dict[str, Any]] | None = None,
    meta: dict[str, Any] | None = None,
) -> str:
    meta = meta or {}
    lines: list[str] = [
        "# Assessment dossier",
        "",
        "> **official=false** — vista del risultato automatico, non un dossier ufficiale.",
        "",
        "## 1. Assessment identity",
        "",
        f"- **assessment_id**: `{result.get('assessment_id')}`",
        f"- **contract_version**: {assessment.get('contract_version', '—')}",
        f"- **created_at**: {assessment.get('created_at', '—')}",
        f"- **lifecycle**: {result.get('lifecycle')}",
        f"- **canonical_hash**: `{result.get('canonical_hash') or '—'}`",
        "",
        "## 2. Target and versions",
        "",
        f"- **board**: {meta.get('board', '—')}",
        f"- **freeze_at**: {meta.get('freeze_at', '—')}",
        f"- **wolfboot_commit**: `{meta.get('wolfboot_commit', '—')}`",
        "",
        "## 3. Declared change",
        "",
        f"- **plan_id**: {(assessment.get('transition_plan') or {}).get('plan_id', '—')}",
    ]
    allowed = assessment.get("allowed_change_set") or {}
    lines.append(f"- **modifiable_components**: {allowed.get('modifiable_components', [])}")
    lines.extend(["", "## 4. Scope and limitations", "", "- Valutazione automatica V1.2.", ""])
    lines.extend(
        [
            "## 5. Executive verdict",
            "",
            f"- **migration**: {result.get('migration_verdict')}",
            f"- **transition**: {result.get('transition_verdict')}",
            f"- **candidate**: {result.get('candidate_verdict')}",
            "",
            "## 6. Decision basis",
            "",
        ]
    )
    for finding in result.get("findings") or []:
        lines.append(f"- **{finding.get('requirement_id')}**: {finding.get('observation')}")
    if not result.get("findings"):
        lines.append("- (nessun finding strutturato)")
    lines.extend(["", "## 7. Requirements and invariants", ""])
    for row in result.get("requirement_evaluation_results") or []:
        if not row.get("critical_for_verdict"):
            continue
        lines.append(
            f"- `{row.get('requirement_id')}` ({row.get('phase')}) → **{row.get('state')}**"
        )
    for row in result.get("invariant_evaluation_results") or []:
        if not row.get("critical_for_verdict"):
            continue
        lines.append(
            f"- `{row.get('invariant_id')}` ({row.get('phase')}) → **{row.get('state')}**"
        )
    lines.extend(["", "## 8. Evidence", ""])
    for item in assessment.get("evidence") or []:
        eid = item.get("id")
        lines.append(
            f"- `{eid}` — {item.get('evidence_kind')} / {item.get('acquisition_mode')} "
            f"/ run `{item.get('run_id') or '—'}`"
        )
    lines.extend(["", "## 9. Open gaps", ""])
    for gap in assessment.get("evidence_gaps") or []:
        lines.append(f"- `{gap.get('gap_id')}` → {gap.get('requirement_id')}: {gap.get('reason')}")
    lines.extend(["", "## 10. Contrary evidence", ""])
    contrary = [
        item
        for item in assessment.get("evidence") or []
        if item.get("supports_conclusion") is False
    ]
    if contrary:
        for item in contrary:
            lines.append(f"- `{item.get('id')}`")
    else:
        lines.append("- Nessuna prova contraria nel risultato.")
    if gap_plan:
        lines.extend(["", "## 11. Gap planner", ""])
        for plan in gap_plan:
            lines.append(
                f"- **{plan.get('label')}** — status `{plan.get('status')}`; "
                f"test `{plan.get('suggested_test_id')}`; {plan.get('reason')}"
            )
    lines.extend(
        [
            "",
            "## 12. Reproduction metadata",
            "",
            "```text",
            "python -m src.demo.verify",
            "python -m src.demo.export_catalog",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = ["render_dossier_markdown"]
