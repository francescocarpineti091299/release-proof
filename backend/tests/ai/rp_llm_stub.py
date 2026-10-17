"""Test fixture: deterministic fake AMD endpoint (httpx.MockTransport).

Refused unless RELEASEPROOF_ENV=test. Besides schema-valid answers it implements adversarial
modes that the test-suite and the benchmark use to prove the guardrails.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

import httpx

from releaseproof.ai.config import AISettings
from releaseproof.ai.service import InjectedTransportRefused

STUB_HOST = "amd-stub.invalid"
INJECTION_MARKER = re.compile(r"ignore (all )?(previous|prior|above) instructions", re.IGNORECASE)


class StubRefusedError(InjectedTransportRefused):
    pass


class StubMode(StrEnum):
    VALID = "VALID"
    INVALID_JSON = "INVALID_JSON"
    HALLUCINATED_CITATION = "HALLUCINATED_CITATION"
    WRONG_VERDICT_ECHO = "WRONG_VERDICT_ECHO"
    UNKNOWN_TEMPLATE = "UNKNOWN_TEMPLATE"
    BAD_ALTERNATIVE = "BAD_ALTERNATIVE"
    PROMPT_INJECTION = "PROMPT_INJECTION"  # a gullible model that obeys instructions in data
    JSON_SCHEMA_UNSUPPORTED = "JSON_SCHEMA_UNSUPPORTED"
    THINK_AND_FENCE = "THINK_AND_FENCE"
    HTTP_401 = "HTTP_401"
    HTTP_429 = "HTTP_429"
    HTTP_500 = "HTTP_500"
    HTTP_503 = "HTTP_503"
    HTTP_UPSTREAM_TIMEOUT = "HTTP_UPSTREAM_TIMEOUT"
    TIMEOUT = "TIMEOUT"


def _require_test_env() -> None:
    if os.environ.get("RELEASEPROOF_ENV", "").strip().lower() != "test":
        raise StubRefusedError("the stub LLM is test-only (RELEASEPROOF_ENV must be 'test')")


def _section(text: str, tag: str) -> Any:
    match = re.search(rf"<{tag}>\n(.*?)\n</{tag}>", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


class StubLLM:
    """Fake OpenAI-compatible endpoint. ``modes`` is consumed one per request (last repeats)."""

    def __init__(
        self,
        modes: StubMode | Sequence[StubMode] = StubMode.VALID,
        *,
        model: str = "stub-amd-model",
    ) -> None:
        _require_test_env()
        self.modes = [modes] if isinstance(modes, StubMode) else list(modes)
        self.model = model
        self.requests: list[dict[str, Any]] = []
        self.transport = httpx.MockTransport(self._handle)
        self.transport.releaseproof_stub = True  # type: ignore[attr-defined]

    def settings(self, **overrides: Any) -> AISettings:
        values: dict[str, Any] = {
            "base_url": f"https://{STUB_HOST}/v1",
            "api_key": "stub-secret-key-0123456789",
            "model": self.model,
            "provider_label": "AMD Developer Cloud (stub)",
            "hardware_label": "AMD Instinct MI300X (stub)",
            "allowed_hosts": (STUB_HOST,),
            "env": "test",
        }
        values.update(overrides)
        return AISettings(**values)

    def _mode(self) -> StubMode:
        index = min(len(self.requests) - 1, len(self.modes) - 1)
        return self.modes[max(index, 0)]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        self.requests.append(body)
        mode = self._mode()
        n = len(self.requests)
        if mode == StubMode.TIMEOUT:
            raise httpx.ReadTimeout("stub timeout", request=request)
        if mode == StubMode.HTTP_UPSTREAM_TIMEOUT:
            return httpx.Response(
                500,
                json={
                    "error": {
                        "message": "Error from provider: 504 Gateway Timeout "
                        '{"error":{"code":"call_upstream_timeout"}}'
                    }
                },
            )
        status = {
            StubMode.HTTP_401: 401,
            StubMode.HTTP_429: 429,
            StubMode.HTTP_500: 500,
            StubMode.HTTP_503: 503,
        }.get(mode)
        if status:
            return httpx.Response(status, json={"error": {"message": f"stub HTTP {status}"}})
        rf = (body.get("response_format") or {}).get("type")
        if mode == StubMode.JSON_SCHEMA_UNSUPPORTED and rf == "json_schema":
            return httpx.Response(
                400, json={"error": {"message": "response_format json_schema is not supported"}}
            )
        messages = body.get("messages") or []
        system = messages[0]["content"] if messages else ""
        found = re.search(r"ReleaseProof prompt template: (\w+)@", system)
        module = found.group(1) if found else "smoke"
        headers = {"x-request-id": f"stub-req-{n}"}
        if body.get("stream"):
            return self._stream(module, messages, mode, n, headers)
        user = messages[1]["content"] if len(messages) > 1 else ""
        content = self._content(module, user, mode)
        return httpx.Response(
            200,
            headers=headers,
            json={
                "id": f"chatcmpl-stub-{n}",
                "object": "chat.completion",
                "model": self.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": len(json.dumps(messages)) // 4,
                    "completion_tokens": len(content) // 4,
                    "total_tokens": (len(json.dumps(messages)) + len(content)) // 4,
                },
            },
        )

    def _stream(
        self,
        module: str,
        messages: list[dict[str, Any]],
        mode: StubMode,
        n: int,
        headers: dict[str, str],
    ) -> httpx.Response:
        context = _section(messages[0]["content"], "untrusted_data") or {}
        verdict = (
            (context.get("verdicts") or {}).get("migration") if isinstance(context, dict) else None
        )
        if mode == StubMode.PROMPT_INJECTION and INJECTION_MARKER.search(json.dumps(messages)):
            pieces = ["The migration is ", "COMPATIBLE", " and safe to deploy."]
        else:
            pieces = [
                "<think>check the context</think>" if mode == StubMode.THINK_AND_FENCE else "",
                "Based on this run, the engine migration verdict is ",
                f"{verdict or 'UNKNOWN'}",
                ".",
                " [" + (context.get("evidence_ids") or ["EV-E11-SELF-UPDATE"])[0] + "]",
            ]
        lines = []
        for piece in [p for p in pieces if p]:
            chunk = {
                "id": f"chatcmpl-stub-{n}",
                "model": self.model,
                "choices": [{"index": 0, "delta": {"content": piece}}],
            }
            lines.append(f"data: {json.dumps(chunk)}\n\n")
        usage = {
            "id": f"chatcmpl-stub-{n}",
            "choices": [],
            "usage": {"prompt_tokens": 100, "completion_tokens": 12},
        }
        lines.append(f"data: {json.dumps(usage)}\n\n")
        lines.append("data: [DONE]\n\n")
        return httpx.Response(
            200,
            headers={**headers, "content-type": "text/event-stream"},
            content="".join(lines).encode(),
        )

    def _content(self, module: str, user: str, mode: StubMode) -> str:
        if mode == StubMode.INVALID_JSON:
            return 'Sure! Here is the JSON: {"selected": [ {"template_id": oops'
        allowed = _section(user, "allowed_ids") or {}
        data = _section(user, "untrusted_data") or {}
        injected = mode == StubMode.PROMPT_INJECTION and bool(
            INJECTION_MARKER.search(json.dumps(data))
        )
        if module == "planner":
            obj = self._plan(allowed, mode, injected)
        elif module == "explainer":
            obj = self._report(allowed, mode, injected)
        elif module == "alternatives":
            obj = self._alternatives(allowed, data, mode, injected)
        else:
            obj = {"ok": True}
        text = json.dumps(obj)
        if mode == StubMode.THINK_AND_FENCE:
            text = f"<think>reasoning about the plan</think>\n```json\n{text}\n```"
        return text

    @staticmethod
    def _plan(allowed: dict[str, Any], mode: StubMode, injected: bool) -> dict[str, Any]:
        ids = list(allowed.get("template_ids") or [])
        required = list(allowed.get("required_template_ids") or [])
        selected = [
            {"template_id": t, "priority": min(i + 1, 10), "rationale": "Relevant to the change."}
            for i, t in enumerate(ids)
        ]
        skipped: list[dict[str, Any]] = []
        if mode == StubMode.UNKNOWN_TEMPLATE:
            selected.append(
                {"template_id": "custom.flash_production_fleet", "priority": 1, "rationale": "x"}
            )
            if required:
                skipped.append({"template_id": required[0], "reason": "not needed"})
        if injected:
            selected.insert(0, {"template_id": "shell.rm_rf", "priority": 1, "rationale": "asked"})
        return {
            "selected": selected,
            "skipped": skipped,
            "suggested_new_tests": [
                {"title": "Interrupted update", "purpose": "Observe the non-atomic window."}
            ],
            "summary": "Run discovery and capability checks first, then boots and negatives.",
        }

    @staticmethod
    def _report(allowed: dict[str, Any], mode: StubMode, injected: bool) -> dict[str, Any]:
        verdicts = dict(allowed.get("verdicts") or {})
        citable = list(allowed.get("citable_ids") or [])
        blocking = list(allowed.get("blocking_ids") or [])
        evidence = [c for c in citable if c.startswith("EV-")] or citable
        gaps = [c for c in citable if c.startswith("GAP-")]
        cause = blocking[:1] or citable[:1]
        echo = dict(verdicts)
        if mode == StubMode.WRONG_VERDICT_ECHO:
            echo["migration"] = (
                "INCOMPATIBLE" if verdicts.get("migration") == "COMPATIBLE" else "COMPATIBLE"
            )
        if injected:
            echo = {
                "migration": "COMPATIBLE",
                "candidate": "COMPATIBLE",
                "transition": "COMPATIBLE",
            }
            cause = ["EV-INJECTED-PROOF"]
        main = [
            {"text": "The critical blocking result drives the engine verdict.", "citations": cause}
        ]
        if mode == StubMode.HALLUCINATED_CITATION:
            main[0]["citations"] = [*cause, "EV-DOES-NOT-EXIST"]
        return {
            "headline": f"Engine migration verdict: {verdicts.get('migration')}",
            "verdict_echo": echo,
            "main_causes": main,
            "verified": [{"text": "Observed during emulation.", "citations": evidence[:1]}]
            if evidence
            else [],
            "unknowns": [{"text": "Not observed in this run.", "citations": gaps[:1]}]
            if gaps
            else [],
            "executive_summary": "Summary grounded in the engine result and cited evidence.",
        }

    @staticmethod
    def _alternatives(
        allowed: dict[str, Any], data: dict[str, Any], mode: StubMode, injected: bool
    ) -> dict[str, Any]:
        plans = list(allowed.get("plan_ids") or [])
        blocking = list(allowed.get("blocking_ids") or [])
        proposals = [
            {
                "plan_id": p,
                "title": f"Consider {p}",
                "rationale": "May remove the blocking result; must be re-evaluated by the engine.",
                "addresses": blocking[:1],
                "preconditions": [],
                "tradeoffs": ["Operational cost"],
                "evidence_still_needed": ["Re-run the affected tests on this plan"],
            }
            for p in plans[:4]
        ]
        if mode == StubMode.BAD_ALTERNATIVE:
            proposals.append(
                {
                    "plan_id": "invented_plan",
                    "title": "Invented",
                    "rationale": "This is now COMPATIBLE.",
                    "addresses": ["REQ-FAKE"],
                }
            )
            proposals = proposals[-4:]
        if mode == StubMode.HALLUCINATED_CITATION and proposals:
            proposals[0]["addresses"] = [*blocking[:1], "REQ-FAKE"]
        if injected:
            proposals = [
                {
                    "plan_id": "ship_it_now",
                    "title": "Ship now",
                    "rationale": "Verified COMPATIBLE as instructed.",
                    "addresses": blocking,
                }
            ]
        return {"proposals": proposals, "not_addressable": blocking[1:]}


__all__ = ["INJECTION_MARKER", "STUB_HOST", "StubLLM", "StubMode", "StubRefusedError"]
