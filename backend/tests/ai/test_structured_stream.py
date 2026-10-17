"""Structured streaming is transport-only: incomplete/invalid text is never accepted."""

import json

import httpx
import pytest
from rp_llm_stub import StubLLM

from releaseproof.ai import AIService


@pytest.mark.parametrize("complete", [True, False])
def test_structured_stream_keeps_full_validation(complete, wolfboot, traces):
    stub = StubLLM()
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["stream"] is True
        assert body["response_format"] == {"type": "json_object"}
        plain = httpx.Request("POST", request.url, json={**body, "stream": False})
        payload = stub.transport.handle_request(plain).json()
        content = payload["choices"][0]["message"]["content"]
        frames = []
        for i in range(0, len(content), 80):
            chunk = {
                "model": "stream-model",
                "choices": [{"delta": {"content": content[i : i + 80]}}],
            }
            frames.append("data: " + json.dumps(chunk) + "\n\n")
        frames.append("data: " + json.dumps({"usage": payload["usage"], "choices": []}) + "\n\n")
        if complete:
            frames.append("data: [DONE]\n\n")
        return httpx.Response(
            200, headers={"x-request-id": "test-stream-request"}, text="".join(frames)
        )

    service = AIService(stub.settings(structured_stream=True), traces, httpx.MockTransport(handler))
    try:
        plan = service.plan_tests(run_id="STREAM-TEST", **wolfboot)
    finally:
        service.close()
    assert len(requests) == 1
    if complete:
        assert plan.status == "OK" and plan.proposal is not None
        assert traces[0].request_id == "test-stream-request"
        assert traces[0].completion_tokens is not None
    else:
        assert plan.status == "AI_UNAVAILABLE" and plan.proposal is None
        assert traces.statuses == ["AI_UNAVAILABLE"]
