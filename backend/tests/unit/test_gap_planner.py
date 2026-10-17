"""Gap planner reads mapping only."""

from __future__ import annotations

from rp_scenarios import (
    build_scenario_compatible,
    build_scenario_conditional,
)

from releaseproof.core.assurance.service import evaluate
from releaseproof.core.planner.service import build_gap_plan, load_planner_mapping
from releaseproof.core.projection.wp0 import build_wp0_baseline_assessment


def test_mapping_loads() -> None:
    spec = load_planner_mapping()
    assert spec["version"] == "1.0"
    assert len(spec["entries"]) >= 4


def test_freeze_has_o05_gap_plan() -> None:
    assessment = build_wp0_baseline_assessment()
    result = evaluate(assessment).model_dump(mode="json")
    plan = build_gap_plan(assessment, result)
    o05 = [p for p in plan if p.get("source_id") == "GAP-O05-DUAL-POLICY"]
    assert o05
    assert o05[0]["suggested_test_id"] == "O05"
    assert o05[0]["status"] == "NOT_EXECUTABLE"


def test_closed_invariant_drops_catalog_gap_from_plan() -> None:
    assessment = build_scenario_compatible()
    result = evaluate(assessment).model_dump(mode="json")
    plan = build_gap_plan(assessment, result)
    assert not any(p.get("source_id") == "GAP-O05-DUAL-POLICY" for p in plan)


def test_conditional_plan_lists_open_maintenance() -> None:
    assessment = build_scenario_conditional()
    result = evaluate(assessment).model_dump(mode="json")
    plan = build_gap_plan(assessment, result)
    maintenance = [p for p in plan if p.get("requirement_id") == "REQ-MAINTENANCE-WINDOW"]
    assert maintenance
    assert maintenance[0]["status"] == "MISSING"
