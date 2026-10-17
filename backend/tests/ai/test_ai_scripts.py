from __future__ import annotations

import json
import os
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


def test_env_file_preserves_exported_settings_and_literal_key(no_amd_env, monkeypatch, tmp_path):
    from amd_common import load_env_file

    monkeypatch.setenv("AMD_LLM_MODEL", "exported-model")
    monkeypatch.delenv("AMD_LLM_PROVIDER_LABEL", raising=False)
    path = tmp_path / ".env"
    path.write_text(
        'AMD_LLM_MODEL=DeepSeek-V4-Flash\n'
        'AMD_LLM_API_KEY=rc-${LITERAL}\n'
        'AMD_LLM_PROVIDER_LABEL="AMD Token Factory"\n',
        encoding="utf-8-sig",
    )
    load_env_file(str(path))

    from releaseproof.ai import AISettings

    settings = AISettings.from_env()
    assert settings.model == "exported-model"
    assert settings.api_key == "rc-${LITERAL}"
    assert settings.provider_label == "AMD Token Factory"


def test_env_file_is_only_loaded_when_requested(no_amd_env):
    from amd_common import load_env_file

    load_env_file(None)
    assert "AMD_LLM_API_KEY" not in os.environ


def test_smoke_missing_env_file_fails_before_calls(no_amd_env, tmp_path):
    import amd_smoke

    out = tmp_path / "smoke.json"
    with pytest.raises(SystemExit, match="2"):
        amd_smoke.main(["--env-file", str(tmp_path / "missing.env"), "--out", str(out)])
    assert not out.exists()
