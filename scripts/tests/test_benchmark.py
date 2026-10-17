from __future__ import annotations

import pytest

import amd_benchmark


def test_zero_iterations_is_rejected_before_inference():
    with pytest.raises(SystemExit, match="2"):
        amd_benchmark.main(["-n", "0"])


@pytest.mark.parametrize("text,failed", [
    ("AI unavailable: unconfigured", True),
    ("Partial answer\n\n[AI unavailable: the AMD stream was interrupted]", True),
    ("", True),
    ("The pipeline works even when AI unavailable is displayed.", False),
])
def test_partial_assistant_outage_is_not_counted_as_a_success(text, failed):
    from amd_common import assistant_unavailable

    assert assistant_unavailable(text) is failed


@pytest.mark.parametrize("status,falsified,expected", [
    ("OK", False, 0), ("OK", True, 1), ("SCHEMA_INVALID", False, 1),
])
def test_benchmark_exit_code_matches_logical_failures(monkeypatch, tmp_path,
                                                    status, falsified, expected):
    from types import SimpleNamespace

    trace = SimpleNamespace(status="OK", module="assistant", latency_ms=1,
                            prompt_tokens=1, completion_tokens=1, model="test",
                            request_id="id", model_dump=lambda **kwargs: {})
    calls = [{"case": "adversarial.falsify_verdict", "module": "assistant",
              "status": status, "verdict_falsified": falsified}]
    monkeypatch.setattr(amd_benchmark, "_run_model", lambda *args: {
        "calls": calls, "traces": [trace], "provider_info": {},
    })
    assert amd_benchmark.main(["-n", "1", "--out", str(tmp_path / "report.json")]) == expected
