"""Policy unit tests use synthetic verified metadata, not emulation claims."""

import copy

import pytest

from releaseproof.release_gate import release_decision


def _pack():
    return {
        "run": {
            "run_id": "unit",
            "configuration_id": "profile",
            "change_id": "change",
            "plan_id": "plan",
            "status": "SUCCEEDED",
            "mode": "LIVE",
            "tests": [{"template_id": "negative", "negative": True, "outcome": "PASS"}],
        },
        "result": {
            "result": {
                "lifecycle": "COMPLETED",
                "official": False,
                "migration_verdict": "COMPATIBLE",
                "candidate_verdict": "COMPATIBLE",
                "transition_verdict": "COMPATIBLE",
                "canonical_hash": "sha256:" + "a" * 64,
                "requirement_evaluation_results": [
                    {"critical_for_verdict": True, "state": "SATISFIED"},
                ],
                "invariant_evaluation_results": [],
                "errors": [],
                "conditions": [],
            }
        },
        "manifest": {
            "profile": {"status": "SUPPORTED"},
            "change": {"required_templates": ["negative"]},
        },
    }


def _decision(pack):
    return release_decision(pack, configuration="profile", change="change", plan="plan")


def test_only_complete_compatible_live_supported_run_passes():
    assert _decision(_pack())["decision"] == "PASS"


@pytest.mark.parametrize("phase", ["migration", "candidate", "transition"])
@pytest.mark.parametrize("verdict", ["INCOMPATIBLE", "INDETERMINATE", "CONDITIONAL", None])
def test_no_candidate_only_or_unknown_or_conditional_green(phase, verdict):
    pack = _pack()
    pack["result"]["result"][f"{phase}_verdict"] = verdict
    assert _decision(pack)["decision"] == "BLOCK"


@pytest.mark.parametrize(
    "key,value",
    [
        ("mode", "REFERENCE"),
        ("mode", "REEVALUATION"),
        ("status", "FAILED"),
        ("status", "RUNNING"),
        ("configuration_id", "other"),
        ("change_id", "other"),
        ("plan_id", "other"),
    ],
)
def test_ci_identity_and_fresh_execution_required(key, value):
    pack = _pack()
    pack["run"][key] = value
    assert _decision(pack)["decision"] == "BLOCK"


def test_unknown_invariant_and_incomplete_templates_block_without_mutating_evidence():
    pack = _pack()
    pack["result"]["result"]["invariant_evaluation_results"] = [
        {"critical_for_verdict": True, "state": "UNKNOWN"},
    ]
    pack["manifest"]["change"]["required_templates"].append("missing")
    before = copy.deepcopy(pack)
    assert len(_decision(pack)["reasons"]) == 2
    assert pack == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("errors", ["tool failure"]),
        ("conditions", [{"condition_id": "COND-1"}]),
        ("official", True),
        ("lifecycle", "INCOMPLETE"),
    ],
)
def test_errors_conditions_and_invalid_lifecycle_block(field, value):
    pack = _pack()
    pack["result"]["result"][field] = value
    assert _decision(pack)["decision"] == "BLOCK"
