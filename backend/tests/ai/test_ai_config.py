from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values

from releaseproof.ai import AIService, AISettings, InjectedTransportRefused
from releaseproof.ai.client import AMDChatClient
from releaseproof.ai.stub import STUB_HOST, StubLLM, StubMode, StubRefusedError
from releaseproof.contracts.api import AIStatus


def test_from_env_parses_all_variables() -> None:
    s = AISettings.from_env(
        {
            "AMD_LLM_BASE_URL": "https://developer.amd.com.cn/radeon/api/v1/",
            "AMD_LLM_API_KEY": "rc-secret",
            "AMD_LLM_MODEL": "Qwen3.8-Flash-Next",
            "AMD_LLM_MODEL_EXPLAINER": "DeepSeek-V4-Flash-0731",
            "AMD_LLM_PROVIDER_LABEL": "AMD Token Factory",
            "AMD_LLM_HARDWARE_LABEL": "AMD Instinct MI300X",
            "AMD_LLM_ALLOWED_HOSTS": " developer.amd.com.cn , 10.0.0.5 ",
            "AMD_LLM_TIMEOUT_S": "30",
            "AMD_LLM_EXTRA_BODY": '{"chat_template_kwargs": {"enable_thinking": false}, '
            '"model": "evil"}',
            "RELEASEPROOF_ENV": "demo",
        }
    )
    assert s.base_url == "https://developer.amd.com.cn/radeon/api/v1"
    assert s.endpoint_host == "developer.amd.com.cn"
    assert s.allowed_hosts == ("developer.amd.com.cn", "10.0.0.5")
    assert s.model_for("planner") == "Qwen3.8-Flash-Next"
    assert s.model_for("explainer") == "DeepSeek-V4-Flash-0731"
    assert s.read_timeout_s == 30
    assert s.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert s.env == "demo"
    assert s.configured
    assert "rc-secret" not in repr(s)


def test_host_not_in_allowlist_is_ai_unavailable(wolfboot, traces) -> None:
    stub = StubLLM()
    settings = stub.settings(base_url="https://api.openai.com/v1")
    svc = AIService(settings, traces, transport=stub.transport)
    view = svc.plan_tests(run_id="RP-1", **wolfboot)
    assert view.status == AIStatus.AI_UNAVAILABLE
    assert "api.openai.com" in view.message and "AMD_LLM_ALLOWED_HOSTS" in view.message
    assert stub.requests == []  # nothing was sent anywhere
    assert traces.statuses == ["AI_UNAVAILABLE"]
    assert traces[0].endpoint_host == "api.openai.com"


def test_default_allowlist_rejects_unknown_hosts() -> None:
    s = AISettings.from_env(
        {"AMD_LLM_BASE_URL": "https://example.com/v1", "AMD_LLM_API_KEY": "k", "AMD_LLM_MODEL": "m"}
    )
    assert not s.configured
    assert "example.com" in (s.unavailable_reason() or "")


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"api_key": None}, "AMD_LLM_API_KEY"),
        ({"base_url": None}, "AMD_LLM_BASE_URL"),
        ({"model": None}, "no model configured"),
        ({"base_url": "ftp://amd-stub.invalid/v1"}, "http or https"),
    ],
)
def test_missing_configuration_is_ai_unavailable(wolfboot, traces, override, fragment) -> None:
    stub = StubLLM()
    svc = AIService(stub.settings(**override), traces, transport=stub.transport)
    view = svc.plan_tests(run_id="RP-1", **wolfboot)
    assert view.status == AIStatus.AI_UNAVAILABLE
    assert fragment in view.message
    assert view.proposal is None
    assert stub.requests == []
    assert traces.statuses == ["AI_UNAVAILABLE"]
    assert view.trace_ids == [traces[0].trace_id]


def test_no_key_from_env_is_ai_unavailable(wolfboot, traces) -> None:
    svc = AIService(AISettings.from_env({}), traces)
    view = svc.plan_tests(run_id="RP-1", **wolfboot)
    assert view.status == AIStatus.AI_UNAVAILABLE
    assert traces.statuses == ["AI_UNAVAILABLE"]
    info = svc.provider_info()
    assert info["configured"] is False and info["fallback_provider"] is None


def test_stub_refused_outside_test_env(monkeypatch) -> None:
    for env in ("demo", "dev", ""):
        monkeypatch.setenv("RELEASEPROOF_ENV", env)
        with pytest.raises(StubRefusedError):
            StubLLM()


def test_injected_transport_refused_outside_test_env(monkeypatch) -> None:
    stub = StubLLM()
    monkeypatch.setenv("RELEASEPROOF_ENV", "demo")
    with pytest.raises(InjectedTransportRefused):
        AIService(stub.settings(), transport=stub.transport)
    monkeypatch.setenv("RELEASEPROOF_ENV", "test")
    with pytest.raises(InjectedTransportRefused):
        AIService(stub.settings(env="demo"), transport=stub.transport)


def test_provider_info(traces) -> None:
    stub = StubLLM(StubMode.VALID)
    svc = AIService(
        stub.settings(module_models={"assistant": "small-model"}), traces, stub.transport
    )
    info = svc.provider_info()
    assert info["endpoint_host"] == STUB_HOST
    assert info["configured"] is True
    assert info["models"]["assistant"] == "small-model"
    assert info["models"]["planner"] == "stub-amd-model"
    assert info["prompt_templates"]["explainer"] == "explainer@1"
    assert "api_key" not in info and "stub-secret" not in str(info)


@pytest.mark.parametrize(
    ("host", "key", "prefix_hint"),
    [
        ("developer.amd.com.cn", "Rc-test-secret", True),
        ("developer.amd.com.cn", "rc-test-secret", False),
        ("dedicated.example.com", "Rc-test-secret", False),
    ],
)
def test_token_factory_auth_error_explains_prefix_without_changing_key(host, key, prefix_hint):
    client = AMDChatClient(AISettings(base_url=f"https://{host}/v1", api_key=key))
    error = client._http_error(httpx.Response(401, text=f"Rejected credential {key}"))
    assert ("Token Factory documents 'rc-'" in error.reason) is prefix_hint
    assert key not in error.reason
    assert client._headers()["Authorization"] == f"Bearer {key}"


def test_token_factory_example_has_safe_usable_defaults():
    example = Path(__file__).resolve().parents[3] / ".env.example"
    env = {key: value for key, value in dotenv_values(example).items() if value is not None}
    assert env["AMD_LLM_API_KEY"] == ""
    settings = AISettings.from_env(env)
    assert not settings.configured
    assert settings.unavailable_reason() == "AMD_LLM_API_KEY is not set"
    assert settings.endpoint_host == "developer.amd.com.cn"
    assert settings.response_format == "json_object"
    assert settings.provider_label == "AMD Token Factory"
    assert "MI300X" not in settings.hardware_label
    env["AMD_LLM_API_KEY"] = "rc-test-secret"
    assert AISettings.from_env(env).configured
