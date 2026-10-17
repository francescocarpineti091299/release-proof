"""Malformed upstream responses must degrade explicitly and still produce a trace."""

from __future__ import annotations

import json

import httpx
import pytest
from rp_llm_stub import StubLLM

from releaseproof.ai import AIService, AISettings
from releaseproof.contracts.api import AssistantMessage


@pytest.mark.parametrize(
    "payload",
    [
        [],
        None,
        "answer",
        {},
        {"choices": []},
        {"choices": [{"message": {"content": ["not text"]}}]},
    ],
)
def test_malformed_completion_is_unavailable_with_one_trace(payload, wolfboot, traces):
    stub = StubLLM()
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=json.dumps(payload)))
    with_service = AIService(stub.settings(), traces, transport)
    try:
        view = with_service.plan_tests(run_id="RP-1", **wolfboot)
    finally:
        with_service.close()
    assert view.status == "AI_UNAVAILABLE" and view.proposal is None
    assert traces.statuses == ["AI_UNAVAILABLE"]
    assert view.trace_ids == [traces[0].trace_id]


@pytest.mark.parametrize("tokens", [-1, True, 1.5, "100"])
def test_invalid_upstream_usage_does_not_break_trace(tokens, wolfboot, traces):
    stub = StubLLM()

    def handler(request):
        payload = stub.transport.handle_request(request).json()
        payload["usage"] = {"prompt_tokens": tokens, "completion_tokens": tokens}
        return httpx.Response(200, json=payload)

    service = AIService(stub.settings(), traces, httpx.MockTransport(handler))
    try:
        view = service.plan_tests(run_id="RP-1", **wolfboot)
    finally:
        service.close()
    assert view.status == "OK" and traces.statuses == ["OK"]
    assert traces[0].prompt_tokens is None and traces[0].completion_tokens is None


@pytest.mark.parametrize(
    "tail",
    [
        "",
        "data: broken\n\n",
        "data: []\n\n",
        'data: {"choices": [42]}\n\n',
        'data: {"choices": [{"delta": 42}]}\n\n',
        'data: {"choices": [{"delta": {"content": ["bad"]}}]}\n\n',
    ],
)
def test_truncated_or_malformed_stream_is_not_reported_as_ok(tail, traces):
    stub = StubLLM()
    valid = 'data: {"choices": [{"delta": {"content": "Partial answer"}}]}\n\n'
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=valid + tail))
    service = AIService(stub.settings(), traces, transport)
    try:
        text = "".join(
            service.assistant_stream(
                run_id="RP-1",
                context={},
                messages=[AssistantMessage(role="user", content="why?")],
            )
        )
    finally:
        service.close()
    assert "Partial answer" not in text
    assert text.startswith("AI unavailable")
    assert traces.statuses == ["AI_UNAVAILABLE"]


@pytest.mark.parametrize("value", ["inf", "Infinity", "nan", "-inf"])
def test_non_finite_timeouts_fall_back_to_safe_defaults(value):
    settings = AISettings.from_env({"AMD_LLM_TIMEOUT_S": value})
    assert settings.read_timeout_s == 90.0


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@developer.amd.com.cn/v1",
        "https://developer.amd.com.cn/v1?api_key=secret",
        "https://developer.amd.com.cn/v1#secret",
        "https://developer.amd.com.cn:invalid/v1",
    ],
)
def test_unsafe_endpoint_url_is_rejected_without_exposing_credentials(url):
    settings = AISettings(base_url=url, api_key="key", model="model")
    reason = settings.unavailable_reason()
    assert reason is not None and "secret" not in reason
