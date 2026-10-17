"""D05: requirement evaluators select live evidence by test_id; legacy IDs keep precedence."""

import copy

from releaseproof.core.assurance.service import evaluate
from releaseproof.core.domain.enums import RequirementResultState
from releaseproof.core.golden.baseline import verify_baseline_golden, verify_signer_bound_golden
from releaseproof.core.projection.wp0 import (
    build_a4_signer_bound_assessment,
    build_wp0_baseline_assessment,
)


def _state(result, requirement_id):
    rows = [r for r in result.requirement_evaluation_results if r["requirement_id"] == requirement_id]
    assert rows, requirement_id
    return rows[0]["state"], rows[0]["evidence_refs"]


def test_golden_hashes_unchanged_by_d05() -> None:
    assert verify_baseline_golden() == (True, None)
    assert verify_signer_bound_golden() == (True, None)


def test_e03_selected_by_test_id_when_legacy_id_absent() -> None:
    assessment = copy.deepcopy(build_wp0_baseline_assessment())
    legacy = next(e for e in assessment["evidence"] if e["id"] == "EV-E03-PANIC")
    legacy["id"] = "EV-RUN-X-E03"
    legacy["test_id"] = "E03"
    result = evaluate(assessment)
    state, refs = _state(result, "REQ-AUTH-NEGATIVE")
    assert state == RequirementResultState.SATISFIED
    assert refs == ["EV-RUN-X-E03"]


def test_e03_accept_by_test_id_is_violation() -> None:
    assessment = copy.deepcopy(build_wp0_baseline_assessment())
    legacy = next(e for e in assessment["evidence"] if e["id"] == "EV-E03-PANIC")
    legacy.update({"id": "EV-RUN-X-E03", "test_id": "E03", "value": "ACCEPT"})
    result = evaluate(assessment)
    state, _ = _state(result, "REQ-AUTH-NEGATIVE")
    assert state == RequirementResultState.VIOLATED


def test_a4_selected_by_test_id_when_legacy_id_absent() -> None:
    assessment = copy.deepcopy(build_a4_signer_bound_assessment())
    legacy = next(e for e in assessment["evidence"] if e["id"] == "EV-A4-SIGNER-BOUND")
    legacy.update({"id": "EV-RUN-X-A4", "test_id": "A4"})
    result = evaluate(assessment)
    state, refs = _state(result, "REQ-SIGN-BOUND")
    assert state == RequirementResultState.VIOLATED
    assert refs == ["EV-RUN-X-A4"]
