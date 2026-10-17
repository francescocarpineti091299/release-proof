from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture
def no_amd_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "AMD_LLM_BASE_URL",
        "AMD_LLM_API_KEY",
        "AMD_LLM_MODEL",
        "AMD_LLM_ALLOWED_HOSTS",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.syspath_prepend(str(SCRIPTS))


def test_smoke_without_endpoint_records_ai_unavailable(no_amd_env, tmp_path) -> None:
    import amd_smoke

    out = tmp_path / "smoke.json"
    assert amd_smoke.main(["--out", str(out)]) == 2
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["calls"]) == 10
    assert data["fallback_provider"] is None
    assert {t["status"] for t in data["traces"]} == {"AI_UNAVAILABLE"}
    sys.modules.pop("amd_smoke", None)


def test_benchmark_without_endpoint(no_amd_env, tmp_path) -> None:
    import amd_benchmark

    out = tmp_path / "bench.json"
    assert amd_benchmark.main(["-n", "1", "--out", str(out)]) == 2
    data = json.loads(out.read_text(encoding="utf-8"))
    (result,) = data["results"].values()
    assert result["metrics"]["adversarial"]["injection_leaked"] == 0
    sys.modules.pop("amd_benchmark", None)
