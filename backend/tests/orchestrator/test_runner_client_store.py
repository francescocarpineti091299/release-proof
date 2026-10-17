"""Runner client protocol checks and store basics."""

from __future__ import annotations

import json

import httpx
import pytest
from rp_fakes import runner_lines

from releaseproof.contracts.runner import RunnerRequest
from releaseproof.orchestrator.runner_client import (
    InvalidRunnerEvent,
    RunnerClient,
    RunnerFailure,
    parse_event_line,
    safe_relative_path,
)
from releaseproof.orchestrator.service import trace_stats
from releaseproof.store.db import Store, StoreError

RUN_ID = "RP-20261017T120000Z-abcdef"


def _request(tmp_path) -> RunnerRequest:
    return RunnerRequest(
        run_id=RUN_ID,
        profile_id="nrf52840-wolfboot-pqc",
        change_id="ecdsa_p256_to_mldsa87",
        tests=[{"template_id": "wolfboot.discover"}, {"template_id": "wolfboot.boot_current"}],
        artifact_dir=(tmp_path / "runs" / RUN_ID / "artifacts").as_posix(),
        timeout_seconds=60,
    )


def _client(handler) -> RunnerClient:
    return RunnerClient("http://runner-wolfboot:8080", transport=httpx.MockTransport(handler))


def test_streams_validated_events_from_real_engine_output(tmp_path):
    req = _request(tmp_path)
    lines = runner_lines(req.model_dump())
    events = list(
        _client(lambda r: httpx.Response(200, content="".join(lines).encode())).execute(req)
    )
    assert len(events) == len(lines)
    assert events[-1].type == "done" and events[-1].status == "SUCCEEDED"
    assert {e.type for e in events} >= {"stage", "artifact", "observation", "test_result", "log"}


def test_non_200_is_a_failure(tmp_path):
    client = _client(lambda r: httpx.Response(409, json={"error": "runner busy"}))
    with pytest.raises(RunnerFailure) as exc:
        list(client.execute(_request(tmp_path)))
    assert exc.value.failure_class == "ENVIRONMENT_SETUP"
    client = _client(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(RunnerFailure) as exc:
        list(client.execute(_request(tmp_path)))
    assert exc.value.failure_class == "TOOL_FAILURE"


def test_seq_must_increase(tmp_path):
    req = _request(tmp_path)
    lines = runner_lines(req.model_dump())
    lines = [lines[0], lines[0], *lines[1:]]
    with pytest.raises(InvalidRunnerEvent):
        list(_client(lambda r: httpx.Response(200, content="".join(lines).encode())).execute(req))


def test_events_after_done_are_invalid(tmp_path):
    req = _request(tmp_path)
    lines = runner_lines(req.model_dump())
    extra = json.loads(lines[-1])
    extra["seq"] += 1
    lines.append(json.dumps(extra) + "\n")
    with pytest.raises(InvalidRunnerEvent):
        list(_client(lambda r: httpx.Response(200, content="".join(lines).encode())).execute(req))


def test_unknown_fields_and_types_are_rejected():
    base = {"seq": 0, "ts": "2026-10-17T00:00:00Z", "run_id": RUN_ID}
    with pytest.raises(InvalidRunnerEvent):
        parse_event_line(json.dumps({**base, "type": "verdict", "migration": "COMPATIBLE"}))
    with pytest.raises(InvalidRunnerEvent):
        parse_event_line(
            json.dumps({**base, "type": "log", "stream": "uart", "line": "x", "extra": 1})
        )
    with pytest.raises(InvalidRunnerEvent):
        parse_event_line("[1, 2]")


@pytest.mark.parametrize(
    "path,ok",
    [
        ("E01/uart.log", True),
        ("a.bin", True),
        ("../x", False),
        ("a/../../x", False),
        ("/etc/passwd", False),
        ("C:/Windows/x", False),
        ("a\\..\\b", False),
        ("", False),
        (".", False),
        ("./", False),
        ("a/file:stream", False),
    ],
)
def test_safe_relative_path(path, ok):
    assert safe_relative_path(path) is ok


def test_store_migrates_and_uses_wal(tmp_path):
    store = Store(tmp_path / "x.sqlite")
    assert store.schema_version == 1
    assert store._query("PRAGMA journal_mode")[0][0] == "wal"
    store.close()
    again = Store(tmp_path / "x.sqlite")  # idempotent migration
    assert again.schema_version == 1


def test_store_rejects_duplicate_observations(tmp_path):
    store = Store(tmp_path / "x.sqlite")
    obs = {"observation_id": "OBS-1", "test_id": "E01"}
    store.add_observation("R1", obs, source_run_id="R1")
    with pytest.raises(StoreError):
        store.add_observation("R1", obs, source_run_id="R1")
    store.add_observation("R2", obs, source_run_id="R1")  # same id in another run is fine


def test_trace_stats():
    rows = [
        {
            "module": "planner",
            "status": "OK",
            "latency_ms": 100,
            "prompt_tokens": 10,
            "completion_tokens": 5,
        },
        {
            "module": "planner",
            "status": "OK",
            "latency_ms": 300,
            "prompt_tokens": 10,
            "completion_tokens": 5,
        },
        {
            "module": "explainer",
            "status": "AI_UNAVAILABLE",
            "latency_ms": None,
            "prompt_tokens": None,
            "completion_tokens": None,
        },
        {
            "module": "explainer",
            "status": "OK",
            "latency_ms": 200,
            "prompt_tokens": 1,
            "completion_tokens": 1,
        },
    ]
    stats = trace_stats(rows)
    assert stats["count"] == 4 and stats["ok_rate"] == 0.75
    assert stats["latency_ms_p50"] == 200 and stats["latency_ms_p95"] == 300
    assert stats["prompt_tokens"] == 21 and stats["completion_tokens"] == 11
    assert stats["by_module"] == {"planner": 2, "explainer": 2}
    assert trace_stats([])["ok_rate"] is None
