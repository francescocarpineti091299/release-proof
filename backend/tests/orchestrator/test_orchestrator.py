"""Orchestrator state machine: live runs, failures, AI degradation, queue, re-evaluation."""

from __future__ import annotations

import threading

import pytest
from rp_fakes import (
    MCUBOOT,
    MCUBOOT_CHANGE,
    WOLFBOOT,
    WOLFBOOT_CHANGE,
    Harness,
    wait_until,
)

from releaseproof.contracts.api import RunCreate
from releaseproof.orchestrator.service import (
    Conflict,
    NotFound,
    Orchestrator,
    Unprocessable,
)
from releaseproof.profiles import registry
from releaseproof.store.db import Store

STAGES = [
    "PREPARING",
    "AI_PLAN",
    "DISCOVERY",
    "BUILD_SIGN",
    "EMULATION_TESTS",
    "EVALUATION",
    "NEXT_STEPS",
]


def _create(orch: Orchestrator, key: str | None = None, **kw):
    body = RunCreate(
        configuration_id=kw.pop("cfg", WOLFBOOT), change_id=kw.pop("change", WOLFBOOT_CHANGE), **kw
    )
    return orch.create_run(body, key)


def _stage(view, name):
    return next(s for s in view.stages if s.stage == name)


@pytest.fixture
def harness(tmp_path):
    return Harness(tmp_path)


def test_happy_path_live_run_stores_verdict_manifest_and_events(harness):
    orch = harness.orchestrator()
    view, created = _create(orch)
    assert created and view.status in {"QUEUED", "RUNNING"}
    assert view.run_id.startswith("RP-") and len(view.run_id.split("-")[-1]) == 6
    done = orch.wait(view.run_id)

    assert done.status == "SUCCEEDED", done.failure
    assert [s.stage for s in done.stages] == STAGES
    assert all(s.status == "SUCCEEDED" for s in done.stages), [
        (s.stage, s.status, s.message) for s in done.stages
    ]
    assert done.verdict is not None and done.verdict.migration == "INCOMPATIBLE"
    assert done.verdict.canonical_hash and done.verdict.canonical_hash.startswith("sha256:")
    assert done.tool_versions["renode"] == "1.16.1"
    assert done.source_pins["wolfboot"].startswith("4c79eee")

    # plan: all required + the optional the AI selected; unregistered proposal blocked
    planned = {p["template_id"]: p["planned_by"] for p in orch.planned_tests(view.run_id)}
    # P01 is now required by policy to close candidate invariant I3, even if AI skips it.
    assert planned["wolfboot.candidate_rejects_classical"] == "POLICY_REQUIRED"
    assert planned["wolfboot.dual_signature_build"] == "AI_PLANNER"
    assert "wolfboot.flash_everything" not in planned
    assert done.ai_plan.blocked_templates == ["wolfboot.flash_everything"]
    assert {t.template_id for t in done.tests} == set(planned)
    negative = next(t for t in done.tests if t.template_id == "wolfboot.tampered_image_rejected")
    assert negative.negative is True and negative.title

    # runner got exactly the merged plan, with the shared-volume artifact dir
    call = harness.runner.calls[0]
    assert [t["template_id"] for t in call["tests"]] == list(planned)
    assert call["artifact_dir"].endswith(f"/runs/{view.run_id}/artifacts")

    # adapter saw the live facts of this run
    kwargs = harness.adapter.calls[0]
    assert kwargs["run_id"] == kwargs["evidence_run_id"] == view.run_id
    assert len(kwargs["observations"]) == len(planned)
    assert len(kwargs["test_results"]) == len(planned)

    result = orch.store.get_result(view.run_id)
    assert result["result"]["canonical_hash"] == done.verdict.canonical_hash
    manifest_path = harness.settings.run_dir(view.run_id) / "manifest.json"
    import hashlib
    import json

    raw = manifest_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == result["manifest_sha256"]
    manifest = json.loads(raw)
    assert manifest["profile"]["id"] == WOLFBOOT and len(manifest["profile"]["sha256"]) == 64
    assert manifest["result"]["canonical_hash"] == done.verdict.canonical_hash
    assert manifest["assessment"]["canonical_hash"].startswith("sha256:")
    assert {a["artifact_id"] for a in manifest["artifacts"]} >= {"ART-wolfboot.boot_current-uart"}
    assert all(len(a["sha256"]) == 64 for a in manifest["artifacts"])
    assert "## 13. ReleaseProof run provenance" in result["dossier_markdown"]
    assert result["manifest_sha256"] in result["dossier_markdown"]

    # every runner event persisted, in order
    events = orch.store.list_events(view.run_id)
    ids = [e.id for e in events]
    assert ids == sorted(ids)
    runner_seqs = [
        e.data["seq"]
        for e in events
        if e.type in {"log", "artifact", "observation", "test_result", "done"}
    ]
    assert runner_seqs == sorted(runner_seqs)
    assert events[-1].type == "run" and events[-1].data["status"] == "SUCCEEDED"
    assert harness.ai.calls == ["plan_tests", "explain", "alternatives"]
    assert len(orch.store.list_ai_traces(view.run_id)) == 3


@pytest.mark.parametrize(
    "behaviour", ["fail", "connect_error", "midstream_error", "timeout", "no_done"]
)
def test_runner_failure_fails_run_and_never_yields_a_verdict(tmp_path, behaviour):
    h = Harness(tmp_path, behaviour=behaviour)
    orch = h.orchestrator()
    view, _ = _create(orch)
    done = orch.wait(view.run_id)

    assert done.status == "FAILED"
    assert done.verdict is None
    assert done.failure is not None
    expected = {
        "fail": "ENVIRONMENT_SETUP",
        "connect_error": "ENVIRONMENT_SETUP",
        "midstream_error": "TOOL_FAILURE",
        "timeout": "TIMEOUT",
        "no_done": "TOOL_FAILURE",
    }[behaviour]
    assert done.failure.failure_class == expected
    # no evaluation of any kind, and no fallback to the recorded freeze
    assert h.adapter.calls == []
    assert orch.store.get_result(view.run_id) is None
    assert not (h.settings.run_dir(view.run_id) / "manifest.json").exists()
    assert _stage(done, "EVALUATION").status == "SKIPPED"
    assert _stage(done, "NEXT_STEPS").status == "SKIPPED"
    assert all(
        e.type != "ai" or e.data.get("module") == "planner" or e.data.get("kind") == "trace"
        for e in orch.store.list_events(view.run_id)
    )
    assert "explain" not in h.ai.calls
    last = orch.store.list_events(view.run_id)[-1]
    assert last.type == "run" and last.data["status"] == "FAILED" and last.data["verdict"] is None


@pytest.mark.parametrize("behaviour", ["invalid_json", "traversal", "unplanned", "wrong_run"])
def test_invalid_runner_event_fails_run_with_tool_failure(tmp_path, behaviour):
    h = Harness(tmp_path, behaviour=behaviour)
    orch = h.orchestrator()
    view, _ = _create(orch)
    done = orch.wait(view.run_id)
    assert done.status == "FAILED"
    assert done.failure.failure_class == "TOOL_FAILURE"
    assert "invalid runner event" in done.failure.message
    assert done.verdict is None
    assert orch.store.get_result(view.run_id) is None
    assert h.adapter.calls == []


def test_artifact_tampered_on_volume_fails_run(tmp_path):
    h = Harness(tmp_path, behaviour="corrupt_file")
    orch = h.orchestrator()
    done = orch.wait(_create(orch)[0].run_id)
    assert done.status == "FAILED"
    assert done.failure.failure_class == "TOOL_FAILURE"
    assert "sha256" in done.failure.message
    assert done.verdict is None
    assert orch.store.get_result(done.run_id) is None


@pytest.mark.parametrize("ai", ["unavailable", "broken"])
def test_ai_unavailable_never_changes_verdict_nor_fails_run(tmp_path, ai):
    reference = Harness(tmp_path / "ok")
    orch_ok = reference.orchestrator()
    ok_view = orch_ok.wait(_create(orch_ok)[0].run_id)

    h = Harness(tmp_path / "noai", ai=ai)
    orch = h.orchestrator()
    view = orch.wait(_create(orch)[0].run_id)

    assert view.status == "SUCCEEDED"
    assert view.verdict == ok_view.verdict  # identical verdict and canonical hash
    ai_plan, next_steps = _stage(view, "AI_PLAN"), _stage(view, "NEXT_STEPS")
    assert ai_plan.status == "INCONCLUSIVE" and ai_plan.message == "AI_UNAVAILABLE"
    assert next_steps.status == "INCONCLUSIVE" and next_steps.message == "AI_UNAVAILABLE"
    assert view.ai_plan.status == "AI_UNAVAILABLE"
    assert view.ai_report.status == "AI_UNAVAILABLE"
    assert view.ai_alternatives.status == "AI_UNAVAILABLE"
    planned = orch.planned_tests(view.run_id)
    change = registry.get_profile(WOLFBOOT).changes[0]
    assert [p["template_id"] for p in planned] == [
        *change.required_templates,
        *change.optional_templates,
    ]
    assert {p["planned_by"] for p in planned if p["template_id"] in change.optional_templates} == {
        "PROFILE_OPTIONAL"
    }


def test_idempotency_key_returns_same_run(harness):
    orch = harness.orchestrator()
    first, created1 = _create(orch, key="click-1")
    second, created2 = _create(orch, key="click-1")
    assert created1 and not created2
    assert first.run_id == second.run_id
    body_key, created3 = _create(orch, idempotency_key="click-1")
    assert not created3 and body_key.run_id == first.run_id
    with pytest.raises(Conflict):
        _create(orch, key="click-1", plan_id="field_service_reflash")
    orch.wait(first.run_id)
    assert len(harness.runner.calls) == 1
    with pytest.raises(Unprocessable):
        _create(orch, key="a", idempotency_key="b")


def test_queue_positions_fifo_one_run_per_family(harness):
    gate = threading.Event()
    harness.runner.gate = gate
    orch = harness.orchestrator()
    a, _ = _create(orch)
    harness.runner.entered.wait(5)
    b, _ = _create(orch)
    c, _ = _create(orch)
    wait_until(lambda: orch.run_view(a.run_id).status == "RUNNING")
    assert orch.run_view(a.run_id).queue_position is None
    vb, vc = orch.run_view(b.run_id), orch.run_view(c.run_id)
    assert (vb.status, vb.queue_position) == ("QUEUED", 1)
    assert (vc.status, vc.queue_position) == ("QUEUED", 2)
    assert len(harness.runner.calls) == 1
    gate.set()
    views = [orch.wait(r.run_id) for r in (a, b, c)]
    assert all(v.status == "SUCCEEDED" for v in views)
    assert [call["run_id"] for call in harness.runner.calls] == [a.run_id, b.run_id, c.run_id]
    assert views[0].started_at < views[1].started_at < views[2].started_at
    assert all(v.queue_position is None for v in views)


def test_different_families_run_concurrently(harness):
    gate = threading.Event()
    harness.runner.gate = gate
    orch = harness.orchestrator()
    a, _ = _create(orch)
    b, _ = _create(orch, cfg=MCUBOOT, change=MCUBOOT_CHANGE)
    wait_until(lambda: len(harness.runner.calls) == 2)
    assert orch.run_view(b.run_id).queue_position is None
    gate.set()
    assert orch.wait(a.run_id).status == orch.wait(b.run_id).status == "SUCCEEDED"


def _snapshot(orch, run_id):
    return (
        orch.run_view(run_id).model_dump(),
        orch.store.get_result(run_id),
        [e.id for e in orch.store.list_events(run_id)],
        orch.store.list_observations(run_id),
        orch.store.list_artifacts(run_id),
    )


def test_reevaluation_creates_new_run_and_never_mutates_parent(harness):
    orch = harness.orchestrator()
    parent = orch.wait(_create(orch)[0].run_id)
    before = _snapshot(orch, parent.run_id)
    calls_before = len(harness.runner.calls)

    child, created = orch.evaluate_alternative(parent.run_id, "field_service_reflash")
    assert created
    child = orch.wait(child.run_id)

    assert child.run_id != parent.run_id
    assert child.mode == "REEVALUATION" and child.parent_run_id == parent.run_id
    assert child.plan_id == "field_service_reflash"
    assert child.status == "SUCCEEDED" and child.verdict is not None
    assert len(harness.runner.calls) == calls_before  # no runner call
    for name in ("AI_PLAN", "DISCOVERY", "BUILD_SIGN", "EMULATION_TESTS"):
        assert _stage(child, name).status == "SKIPPED"
        assert parent.run_id in _stage(child, name).message
    kwargs = harness.adapter.calls[-1]
    assert kwargs["run_id"] == child.run_id and kwargs["evidence_run_id"] == parent.run_id
    assert kwargs["plan_id"] == "field_service_reflash"
    assert len(kwargs["observations"]) == len(before[3])
    # evidence references point at the parent's files
    child_arts = {a["artifact_id"]: a for a in orch.store.list_artifacts(child.run_id)}
    assert child_arts["ART-wolfboot.boot_current-uart"]["owner_run_id"] == parent.run_id
    assert child_arts["MANIFEST"]["owner_run_id"] == child.run_id
    assert [t.template_id for t in child.tests] == [t.template_id for t in parent.tests]

    assert _snapshot(orch, parent.run_id) == before


def test_alternative_requiring_rerun_starts_live_run(harness):
    orch = harness.orchestrator()
    parent = orch.wait(_create(orch)[0].run_id)
    child, _ = orch.evaluate_alternative(parent.run_id, "staged_hybrid_dual_signature")
    child = orch.wait(child.run_id)
    assert child.mode == "LIVE" and child.parent_run_id == parent.run_id
    assert child.status == "SUCCEEDED"
    assert harness.runner.calls[-1]["run_id"] == child.run_id
    planned = {p["template_id"] for p in orch.planned_tests(child.run_id)}
    assert "wolfboot.dual_signature_build" in planned  # all optional tests run for the alternative
    assert harness.adapter.calls[-1]["evidence_run_id"] == child.run_id


def test_alternative_validation(harness):
    orch = harness.orchestrator()
    parent = orch.wait(_create(orch, cfg=MCUBOOT, change=MCUBOOT_CHANGE)[0].run_id)
    with pytest.raises(Unprocessable) as exc:
        orch.evaluate_alternative(parent.run_id, "switch_to_wolfboot_depot")
    assert exc.value.detail["error"] == "REQUIRES_EXTERNAL_VALIDATION"
    assert "external validation" in exc.value.detail["explanation"]
    with pytest.raises(NotFound):
        orch.evaluate_alternative(parent.run_id, "not_a_plan")
    with pytest.raises(NotFound):
        orch.evaluate_alternative("RP-missing", "depot_reflash_mcuboot")
    with pytest.raises(Unprocessable):
        _create(orch, cfg=MCUBOOT, change=MCUBOOT_CHANGE, plan_id="mcuboot_lms_branch")


def test_cannot_branch_from_failed_run(tmp_path):
    h = Harness(tmp_path, behaviour="fail")
    orch = h.orchestrator()
    failed = orch.wait(_create(orch)[0].run_id)
    with pytest.raises(Conflict):
        orch.evaluate_alternative(failed.run_id, "field_service_reflash")
    with pytest.raises(Conflict):
        orch.request_alternatives(failed.run_id)


def test_request_alternatives_updates_ai_view_only(harness):
    orch = harness.orchestrator()
    run = orch.wait(_create(orch)[0].run_id)
    view = orch.request_alternatives(run.run_id)
    assert view.status == "OK"
    after = orch.run_view(run.run_id)
    assert after.verdict == run.verdict
    assert after.ai_alternatives == view


def test_selection_rules(tmp_path, monkeypatch):
    _force_experimental(monkeypatch)
    h = Harness(tmp_path, expose=False)
    orch = h.orchestrator()
    with pytest.raises(Unprocessable):
        _create(orch)  # both profiles are EXPERIMENTAL until the acceptance gate
    with pytest.raises(Unprocessable):
        _create(orch, cfg="nope")
    with pytest.raises(Unprocessable):
        _create(orch, change="nope")


def test_real_adapters_plug_into_the_pipeline(tmp_path):
    adapters = pytest.importorskip("releaseproof.adapters")
    from rp_fakes import FakeAI

    from releaseproof.orchestrator.deps import Deps

    h = Harness(tmp_path)
    h.deps = Deps(ai_factory=FakeAI, runner_transport=h.runner.transport())
    orch = h.orchestrator()
    for cfg, change in ((WOLFBOOT, WOLFBOOT_CHANGE), (MCUBOOT, MCUBOOT_CHANGE)):
        view = orch.wait(_create(orch, cfg=cfg, change=change)[0].run_id)
        assert view.status == "SUCCEEDED", view.failure
        assert view.verdict is not None and view.verdict.canonical_hash
        stored = orch.store.get_result(view.run_id)
        assert stored["evidence"] and all("origin" in e for e in stored["evidence"])
        assert callable(adapters.evidence_index)


def test_startup_recovery_fails_interrupted_runs(harness):
    gate = threading.Event()
    harness.runner.gate = gate
    orch = harness.orchestrator()
    run, _ = _create(orch)
    wait_until(lambda: orch.run_view(run.run_id).status == "RUNNING")
    # simulate a crash: a new process opens the same database
    store2 = Store(harness.settings.db_path)
    orch2 = Orchestrator(store=store2, settings=harness.settings, deps=harness.deps)
    orch2.start()
    view = orch2.run_view(run.run_id)
    assert view.status == "FAILED"
    assert view.failure.failure_class == "INTERNAL"
    assert view.failure.message == "interrupted by restart"
    assert view.verdict is None
    assert not any(s.status == "RUNNING" for s in view.stages)
    gate.set()
    orch.wait(run.run_id)


def _force_experimental(monkeypatch):
    """Selection rules must not depend on the current status in profiles/*.yaml."""
    from releaseproof.contracts.profile import ProfileStatus
    from releaseproof.profiles import registry

    real = registry.load_profiles()
    forced = {
        k: v.model_copy(update={"status": ProfileStatus.EXPERIMENTAL}) for k, v in real.items()
    }
    monkeypatch.setattr(registry, "load_profiles", lambda: forced)
