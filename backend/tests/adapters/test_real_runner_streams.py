"""Real runner streams (recorded 2026-10-17 from the runner containers) through adapters + engine.

These guard the integration between runners, adapters and the V1.2 engine. They are fixtures of
the *test suite*; the product never replays them as live runs.
"""

import json
from pathlib import Path

import pytest

from releaseproof.adapters import evidence_index, get_adapter
from releaseproof.contracts.runner import RunnerEventEnvelope
from releaseproof.core.assurance.service import evaluate
from releaseproof.profiles.registry import get_profile

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "runner_streams"

CASES = [
    (
        "wolfboot_live_20261017.ndjson",
        "nrf52840-wolfboot-pqc",
        "bootloader_self_update",
        ("COMPATIBLE", "INCOMPATIBLE", "INCOMPATIBLE"),
    ),
    (
        "wolfboot_live_20261017.ndjson",
        "nrf52840-wolfboot-pqc",
        "field_service_reflash",
        ("COMPATIBLE", "INDETERMINATE", "INDETERMINATE"),
    ),
    (
        "wolfboot_live_20261017.ndjson",
        "nrf52840-wolfboot-pqc",
        "staged_hybrid_dual_signature",
        ("COMPATIBLE", "INCOMPATIBLE", "INCOMPATIBLE"),
    ),
    (
        "mcuboot_live_20261017.ndjson",
        "nrf52840-mcuboot-pqc",
        "mcuboot_field_update",
        ("INCOMPATIBLE", "INCOMPATIBLE", "INCOMPATIBLE"),
    ),
    (
        "mcuboot_live_20261017.ndjson",
        "nrf52840-mcuboot-pqc",
        "depot_reflash_mcuboot",
        ("INCOMPATIBLE", "INDETERMINATE", "INCOMPATIBLE"),
    ),
]


def _load(name):
    lines = (FIX / name).read_text(encoding="utf-8").splitlines()
    return [RunnerEventEnvelope.model_validate({"event": json.loads(x)}).event for x in lines if x]


@pytest.mark.parametrize(("stream", "profile_id", "plan_id", "expected"), CASES)
def test_real_stream_verdicts(stream, profile_id, plan_id, expected):
    events = _load(stream)
    assert events[-1].type == "done" and events[-1].status == "SUCCEEDED"
    profile = get_profile(profile_id)
    change = profile.changes[0]
    run_id = events[0].run_id
    obs = [e.observation for e in events if e.type == "observation"]
    arts = [e for e in events if e.type == "artifact"]
    results = [e for e in events if e.type == "test_result"]
    assessment = get_adapter(profile.assessment_adapter)(
        profile=profile,
        change=change,
        plan_id=plan_id,
        run_id=run_id,
        evidence_run_id=run_id,
        created_at="2026-10-17T17:00:00Z",
        observations=obs,
        artifacts=arts,
        test_results=results,
    )
    result = evaluate(assessment)
    assert result.lifecycle == "COMPLETED", result.errors
    got = (result.candidate_verdict, result.transition_verdict, result.migration_verdict)
    assert tuple(v.value for v in got) == expected
    rows = evidence_index(assessment, obs, arts)
    assert all(r["run_id"] in (run_id, None) for r in rows)
    assert sum(1 for r in rows if r["artifacts"]) >= 10
