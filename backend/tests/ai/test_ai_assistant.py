from __future__ import annotations

from rp_llm_stub import StubLLM, StubMode

from releaseproof.ai import AI_UNAVAILABLE_TEXT, AIService
from releaseproof.ai.service import _ThinkFilter
from releaseproof.contracts.api import AssistantMessage

CONTEXT = {
    "run_id": "RP-1",
    "verdicts": {"migration": "INCOMPATIBLE", "candidate": "INDETERMINATE"},
    "causes": ["REQ-BOOT-S0S1 VIOLATED"],
    "evidence_ids": ["EV-E11-SELF-UPDATE"],
}
MSGS = [AssistantMessage(role="user", content="Why is the migration blocked?")]


def _stream(modes, traces, **kw):
    stub = StubLLM(modes)
    svc = AIService(stub.settings(**kw), traces, transport=stub.transport)
    chunks = list(svc.assistant_stream(run_id="RP-1", context=CONTEXT, messages=MSGS))
    return stub, chunks


def test_stream_ok(traces) -> None:
    stub, chunks = _stream(StubMode.VALID, traces)
    assert len(chunks) > 1
    assert "INCOMPATIBLE" in "".join(chunks)
    assert traces.statuses == ["OK"]
    t = traces[0]
    assert t.module == "assistant" and t.prompt_template == "assistant@1"
    assert t.request_id == "stub-req-1" and t.completion_tokens == 12
    body = stub.requests[0]
    assert body["stream"] is True
    assert body["messages"][-1] == {"role": "user", "content": "Why is the migration blocked?"}
    assert "<untrusted_data>" in body["messages"][0]["content"]


def test_stream_think_block_removed(traces) -> None:
    _, chunks = _stream(StubMode.THINK_AND_FENCE, traces)
    text = "".join(chunks)
    assert "<think>" not in text and "check the context" not in text
    assert text.startswith("Based on this run")


def test_stream_unavailable_single_message(traces) -> None:
    stub, chunks = _stream(StubMode.VALID, traces, api_key=None)
    assert len(chunks) == 1 and chunks[0].startswith(AI_UNAVAILABLE_TEXT)
    assert "No other AI provider" in chunks[0]
    assert stub.requests == []
    assert traces.statuses == ["AI_UNAVAILABLE"]


def test_stream_http_error_single_message(traces) -> None:
    _, chunks = _stream(StubMode.HTTP_500, traces)
    assert len(chunks) == 1 and chunks[0].startswith(AI_UNAVAILABLE_TEXT)
    assert "stub-secret" not in chunks[0]
    assert traces.statuses == ["AI_UNAVAILABLE"]


def test_think_filter_split_tags() -> None:
    f = _ThinkFilter()
    out = "".join(f.feed(c) for c in ["<thi", "nk>abc</th", "ink>Hello", " world"]) + f.flush()
    assert out == "Hello world"
    g = _ThinkFilter()
    assert "".join(g.feed(c) for c in ["<", "b>x"]) + g.flush() == "<b>x"
