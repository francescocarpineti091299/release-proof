from dataclasses import replace

import pytest
from rp_fakes import WOLFBOOT, WOLFBOOT_CHANGE, Harness

from releaseproof.contracts.api import RunCreate
from releaseproof.orchestrator.service import CapacityExceeded


def test_capacity_rejects_before_creating_a_run_and_keeps_idempotency(tmp_path, monkeypatch):
    harness = Harness(tmp_path)
    harness.settings = replace(harness.settings, max_active_runs=1)
    orch = harness.orchestrator()
    # Hold the existing worker at the runner boundary without executing firmware.
    import threading

    entered = threading.Event()
    release = threading.Event()
    original = orch._execute

    def held(run_id):
        entered.set()
        release.wait(10)
        original(run_id)

    monkeypatch.setattr(orch, "_execute", held)
    body = RunCreate(configuration_id=WOLFBOOT, change_id=WOLFBOOT_CHANGE)
    try:
        first, _ = orch.create_run(body, "first")
        assert entered.wait(2)
        replay, created = orch.create_run(body, "first")
        assert replay.run_id == first.run_id and not created
        with pytest.raises(CapacityExceeded):
            orch.create_run(body, "second")
        assert len(orch.list_runs()) == 1
    finally:
        release.set()
        orch.shutdown()
        orch.store.close()
