"""Deterministic plan merge: required ∪ (AI-selected ∩ optional), AI-ordered."""

from __future__ import annotations

from releaseproof.contracts.ai import PlannedTemplate
from releaseproof.contracts.ai import TestPlanProposal as PlanProposal
from releaseproof.contracts.api import AIPlanView, AIStatus
from releaseproof.contracts.profile import ChangeScenario
from releaseproof.orchestrator.plan import blocked_templates, merge_plan

CHANGE = ChangeScenario(
    change_id="c",
    title="t",
    summary="s",
    from_scheme="A",
    to_scheme="B",
    default_plan_id="p",
    default_plan_title="P",
    required_templates=["r.discover", "r.boot", "r.negative"],
    optional_templates=["o.one", "o.two", "o.three"],
)


def _view(*selected: tuple[str, int], status: AIStatus = AIStatus.OK) -> AIPlanView:
    return AIPlanView(
        status=status,
        proposal=PlanProposal(
            selected=[
                PlannedTemplate(template_id=t, priority=p, rationale="r") for t, p in selected
            ],
            summary="s",
        ),
    )


def test_ai_unavailable_runs_required_plus_all_optional_in_profile_order():
    expected = [
        ("r.discover", "POLICY_REQUIRED"),
        ("r.boot", "POLICY_REQUIRED"),
        ("r.negative", "POLICY_REQUIRED"),
        ("o.one", "PROFILE_OPTIONAL"),
        ("o.two", "PROFILE_OPTIONAL"),
        ("o.three", "PROFILE_OPTIONAL"),
    ]
    assert merge_plan(CHANGE, None) == expected
    assert merge_plan(CHANGE, AIPlanView(status=AIStatus.AI_UNAVAILABLE)) == expected
    # A proposal attached to a non-OK status is never trusted.
    assert merge_plan(CHANGE, _view(("o.two", 1), status=AIStatus.SCHEMA_INVALID)) == expected


def test_ai_selection_intersects_optional_and_keeps_all_required():
    plan = merge_plan(CHANGE, _view(("o.three", 2), ("r.boot", 1), ("evil.rm_rf", 1)))
    assert plan == [
        ("r.boot", "POLICY_REQUIRED"),
        ("o.three", "AI_PLANNER"),
        ("r.discover", "POLICY_REQUIRED"),
        ("r.negative", "POLICY_REQUIRED"),
    ]
    assert "evil.rm_rf" not in dict(plan)
    assert "o.one" not in dict(plan)


def test_ai_cannot_drop_required_templates():
    plan = merge_plan(CHANGE, _view())
    assert [t for t, _ in plan] == ["r.discover", "r.boot", "r.negative"]


def test_order_ties_follow_profile_order_and_duplicates_take_best_priority():
    plan = merge_plan(CHANGE, _view(("o.two", 5), ("o.one", 5), ("o.two", 1)))
    assert [t for t, _ in plan] == ["o.two", "o.one", "r.discover", "r.boot", "r.negative"]


def test_merge_is_deterministic():
    view = _view(("o.two", 3), ("o.one", 3), ("r.negative", 2))
    assert merge_plan(CHANGE, view) == merge_plan(CHANGE, view.model_copy(deep=True))


def test_include_all_optional_keeps_unselected_as_profile_optional():
    plan = merge_plan(CHANGE, _view(("o.two", 1)), include_all_optional=True)
    assert dict(plan)["o.two"] == "AI_PLANNER"
    assert dict(plan)["o.one"] == "PROFILE_OPTIONAL"
    assert dict(plan)["o.three"] == "PROFILE_OPTIONAL"
    assert plan[0] == ("o.two", "AI_PLANNER")


def test_blocked_templates_lists_unregistered_proposals():
    view = _view(("o.one", 1), ("evil.rm_rf", 2), ("other.family", 3))
    assert blocked_templates(CHANGE, view) == ["evil.rm_rf", "other.family"]
    assert blocked_templates(CHANGE, None) == []
