"""Deterministic merge of the profile policy with the AI test-plan proposal.

final = required ∪ (AI-selected ∩ optional), ordered by AI priority (ties and templates the AI
did not rank keep profile order, after the ranked ones). Without a usable AI proposal the plan is
required + all optional (``PROFILE_OPTIONAL``). The AI can never add a template that is not in
the profile, nor remove a required one.
"""

from __future__ import annotations

from typing import Literal

from releaseproof.contracts.api import AIPlanView, AIStatus
from releaseproof.contracts.profile import ChangeScenario

PlannedBy = Literal["POLICY_REQUIRED", "AI_PLANNER", "PROFILE_OPTIONAL"]

_UNRANKED = 1_000


def _usable(view: AIPlanView | None) -> bool:
    return view is not None and view.status == AIStatus.OK and view.proposal is not None


def _ai_priorities(view: AIPlanView) -> dict[str, int]:
    assert view.proposal is not None
    priorities: dict[str, int] = {}
    for item in view.proposal.selected:
        current = priorities.get(item.template_id)
        priorities[item.template_id] = (
            item.priority if current is None else min(current, item.priority)
        )
    return priorities


def merge_plan(
    change: ChangeScenario,
    ai_plan_view: AIPlanView | None,
    *,
    include_all_optional: bool = False,
) -> list[tuple[str, PlannedBy]]:
    required = list(dict.fromkeys(change.required_templates))
    optional = [t for t in dict.fromkeys(change.optional_templates) if t not in required]
    profile_order = {tid: i for i, tid in enumerate([*required, *optional])}

    if not _usable(ai_plan_view):
        return [(t, "POLICY_REQUIRED") for t in required] + [
            (t, "PROFILE_OPTIONAL") for t in optional
        ]

    assert ai_plan_view is not None
    priorities = _ai_priorities(ai_plan_view)
    chosen: list[tuple[str, PlannedBy]] = [(t, "POLICY_REQUIRED") for t in required]
    for tid in optional:
        if tid in priorities:
            chosen.append((tid, "AI_PLANNER"))
        elif include_all_optional:
            chosen.append((tid, "PROFILE_OPTIONAL"))
    chosen.sort(key=lambda item: (priorities.get(item[0], _UNRANKED), profile_order[item[0]]))
    return chosen


def blocked_templates(change: ChangeScenario, ai_plan_view: AIPlanView | None) -> list[str]:
    """Templates the AI proposed that are not part of this change's registered plan."""
    if ai_plan_view is None or ai_plan_view.proposal is None:
        return list(ai_plan_view.blocked_templates) if ai_plan_view else []
    allowed = {*change.required_templates, *change.optional_templates}
    blocked = list(ai_plan_view.blocked_templates)
    for item in ai_plan_view.proposal.selected:
        if item.template_id not in allowed and item.template_id not in blocked:
            blocked.append(item.template_id)
    return blocked
