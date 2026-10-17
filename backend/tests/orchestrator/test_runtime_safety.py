"""Regressions for artifact confinement and concurrent submission boundaries."""

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from rp_fakes import WOLFBOOT, WOLFBOOT_CHANGE, Harness, runner_lines

from releaseproof.contracts.api import RunCreate
from releaseproof.orchestrator.evaluation import (
    EvaluationFailure,
    resolve_artifact_path,
    verify_artifacts,
)
from releaseproof.orchestrator.service import Conflict, _FamilySlot


def _body():
    return RunCreate(configuration_id=WOLFBOOT, change_id=WOLFBOOT_CHANGE)


@pytest.mark.parametrize("owner", ["..", ".", "../outside", "/outside", "C:/outside"])
def test_artifact_owner_cannot_escape_runs_directory(tmp_path, owner):
    assert (
        resolve_artifact_path(
            tmp_path / "runs",
            {
                "owner_run_id": owner,
                "rel_path": "secret.txt",
            },
        )
        is None
    )


def test_artifact_owner_symlink_cannot_escape_runs_directory(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    try:
        (runs / "RP-owner").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks require platform permissions")
    assert (
        resolve_artifact_path(
            runs,
            {
                "owner_run_id": "RP-owner",
                "rel_path": "secret.txt",
            },
        )
        is None
    )


@pytest.mark.parametrize("artifact_id,kind", [("ART-1", "log"), ("MANIFEST", "manifest")])
def test_artifact_integrity_checks_reported_size_and_manifest_hash(tmp_path, artifact_id, kind):
    path = tmp_path / "RP-owner" / "artifact.txt"
    path.parent.mkdir()
    path.write_bytes(b"evidence")
    row = {
        "owner_run_id": "RP-owner",
        "rel_path": "artifact.txt",
        "artifact_id": artifact_id,
        "kind": kind,
        "sha256": hashlib.sha256(b"evidence").hexdigest(),
        "size_bytes": 999,
    }
    with pytest.raises(EvaluationFailure, match="size"):
        verify_artifacts(tmp_path, [row])
    row.update(size_bytes=8, sha256="0" * 64)
    with pytest.raises(EvaluationFailure, match="sha256"):
        verify_artifacts(tmp_path, [row])


@pytest.mark.parametrize("artifact_id", ["MANIFEST", "ART/bad", "ART\x00bad", ".", ".."])
def test_runner_cannot_publish_reserved_or_unroutable_artifact_ids(tmp_path, artifact_id):
    h = Harness(tmp_path)

    def handler(request):
        lines = [json.loads(line) for line in runner_lines(json.loads(request.content))]
        artifact = next(event for event in lines if event["type"] == "artifact")
        artifact["artifact_id"] = artifact_id
        if artifact_id == "MANIFEST":
            artifact["kind"] = "manifest"
        return httpx.Response(200, content="".join(json.dumps(e) + "\n" for e in lines))

    h.deps.runner_transport = httpx.MockTransport(handler)
    orch = h.orchestrator()
    done = orch.wait(orch.create_run(_body())[0].run_id)
    assert done.status == "FAILED"
    assert done.failure.failure_class == "TOOL_FAILURE"
    assert done.verdict is None and h.adapter.calls == []
    assert orch.store.get_result(done.run_id) is None
    orch.shutdown()


def test_stopped_family_slot_never_acquires_even_if_first_in_queue():
    slot = _FamilySlot()
    slot.enqueue("RP-queued")
    stop = threading.Event()
    stop.set()
    assert not slot.acquire("RP-queued", stop)
    assert slot.queued() == []


def test_submission_after_shutdown_does_not_persist_a_run(tmp_path):
    orch = Harness(tmp_path).orchestrator()
    orch.shutdown()
    with pytest.raises(Conflict, match="shutting down"):
        orch.create_run(_body())
    assert orch.store.list_runs() == []


def test_shutdown_timeout_keeps_active_worker_and_store_usable(tmp_path):
    h = Harness(tmp_path)
    gate = threading.Event()
    h.runner.gate = gate
    orch = h.orchestrator()
    active = orch.create_run(_body())[0]
    try:
        assert h.runner.entered.wait(5)
        queued = orch.create_run(_body())[0]
        with pytest.raises(TimeoutError, match="keep the store open"):
            orch.shutdown(timeout=0.05)
        # The queued run is failed without contacting the runner, while the active run drains.
        assert orch.wait(queued.run_id).status == "FAILED"
        assert len(h.runner.calls) == 1
        assert orch.run_view(active.run_id).status == "RUNNING"
        assert orch.store.schema_version == 1
        with pytest.raises(Conflict, match="shutting down"):
            orch.create_run(_body())
    finally:
        gate.set()
        orch.shutdown()
    assert orch.wait(active.run_id).status == "SUCCEEDED"
    assert orch.store.get_result(active.run_id) is not None
    assert orch.store.list_events(active.run_id)[-1].data["status"] == "SUCCEEDED"
    # A successful drain is idempotent and permits the owner to close the connection.
    orch.shutdown(timeout=0)
    orch.store.close()


def test_shutdown_drains_next_steps_ai_and_persists_its_trace(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    orch = h.orchestrator()
    ai = h.deps.ai(orch.trace_sink)
    explain = ai.explain
    entered = threading.Event()
    gate = threading.Event()

    def slow_explain(**kwargs):
        entered.set()
        assert gate.wait(5)
        return explain(**kwargs)

    monkeypatch.setattr(ai, "explain", slow_explain)
    run = orch.create_run(_body())[0]
    try:
        assert entered.wait(5)
        with pytest.raises(TimeoutError, match="keep the store open"):
            orch.shutdown(timeout=0.01)
        assert orch.store.get_result(run.run_id) is not None
        assert orch.run_view(run.run_id).status == "RUNNING"
    finally:
        gate.set()
        orch.shutdown()
    assert orch.wait(run.run_id).status == "SUCCEEDED"
    assert {trace["module"] for trace in orch.store.list_ai_traces(run.run_id)} == {
        "planner",
        "explainer",
        "alternatives",
    }
    orch.store.close()


def test_concurrent_submissions_keep_database_and_runner_fifo_order(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    orch = h.orchestrator()
    slot = orch._slot("wolfboot")
    enqueue = slot.enqueue
    first_paused = threading.Event()
    release_first = threading.Event()
    second_inserted = threading.Event()
    inserted = []
    insert = orch.store.insert_run_with_key

    def record_insert(*args, **kwargs):
        result = insert(*args, **kwargs)
        inserted.append(result[0])
        if len(inserted) == 2:
            second_inserted.set()
        return result

    def pause_first(run_id):
        if run_id == inserted[0]:
            first_paused.set()
            assert release_first.wait(5)
        enqueue(run_id)

    monkeypatch.setattr(orch.store, "insert_run_with_key", record_insert)
    monkeypatch.setattr(slot, "enqueue", pause_first)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(orch.create_run, _body())
        try:
            assert first_paused.wait(5)
            second = pool.submit(orch.create_run, _body())
            # Previously the second insert/enqueue overtook the paused first enqueue.
            second_inserted.wait(0.2)
        finally:
            release_first.set()
        runs = [first.result()[0], second.result()[0]]
    assert all(orch.wait(run.run_id).status == "SUCCEEDED" for run in runs)
    assert inserted == [call["run_id"] for call in h.runner.calls]
    orch.shutdown()
