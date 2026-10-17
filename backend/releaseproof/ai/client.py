"""OpenAI-compatible chat-completions client for AMD-hosted endpoints (httpx, sync).

The client never talks to any host that is not in the AMD allowlist (checked by
:class:`AISettings`) and never logs or returns the API key. Every logical call is described by a
:class:`CallStats` that the caller turns into exactly one ``AITraceView`` via :meth:`emit`.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from releaseproof.ai.config import AISettings
from releaseproof.contracts.api import AIStatus, AITraceView
from releaseproof.contracts.services import TraceSink

log = logging.getLogger("releaseproof.ai")

_REQUEST_ID_HEADERS = (
    "x-request-id",
    "request-id",
    "x-amzn-requestid",
    "x-correlation-id",
    "x-trace-id",
    "cf-ray",
)
_TRANSIENT_STATUS = frozenset({502, 503, 504})
_RF_CHAIN = ("json_schema", "json_object", "none")
_MAX_ERROR_CHARS = 300


class AIUnavailableError(Exception):
    """The AMD endpoint could not produce a response. ``reason`` is safe to show and log."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class CallStats:
    trace_id: str
    started_at: str
    model: str
    latency_ms: int | None = None
    request_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    response_format: str | None = None
    _t0: float = 0.0

    def stop(self) -> None:
        if self._t0:
            self.latency_ms = int((time.perf_counter() - self._t0) * 1000)


@dataclass
class ChatResult:
    content: str
    stats: CallStats


def new_trace_id() -> str:
    return f"AIT-{uuid.uuid4().hex[:16]}"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class AMDChatClient:
    def __init__(
        self,
        settings: AISettings,
        trace_sink: TraceSink | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._sink = trace_sink
        self._transport = transport
        self._http: httpx.Client | None = None
        self._lock = threading.Lock()
        self._rf_mode: dict[str, str] = {}

    # ------------------------------------------------------------------ plumbing

    def _client(self) -> httpx.Client:
        with self._lock:
            if self._http is None:
                timeout = httpx.Timeout(
                    self.settings.read_timeout_s, connect=self.settings.connect_timeout_s
                )
                self._http = httpx.Client(
                    base_url=self.settings.base_url or "",
                    timeout=timeout,
                    transport=self._transport,
                    follow_redirects=False,
                    trust_env=False,
                )
            return self._http

    def close(self) -> None:
        with self._lock:
            if self._http is not None:
                self._http.close()
                self._http = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.api_key or ''}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def scrub(self, text: str) -> str:
        """Remove anything that might be a secret and bound the length."""
        out = text or ""
        if self.settings.api_key:
            out = out.replace(self.settings.api_key, "***")
        out = re.sub(r"(?i)bearer\s+\S+", "Bearer ***", out)
        out = re.sub(r"(?i)(api[_-]?key[\"'=:\s]+)\S+", r"\1***", out)
        out = " ".join(out.split())
        return out[:_MAX_ERROR_CHARS]

    def new_stats(self, module: str) -> CallStats:
        return CallStats(
            trace_id=new_trace_id(),
            started_at=_now(),
            model=self.settings.model_for(module) or "",
            _t0=time.perf_counter(),
        )

    def emit(
        self,
        stats: CallStats,
        *,
        module: str,
        prompt_template: str,
        run_id: str | None,
        status: AIStatus,
        error: str | None = None,
    ) -> AITraceView:
        if stats.latency_ms is None:
            stats.stop()
        trace = AITraceView(
            trace_id=stats.trace_id,
            run_id=run_id,
            module=module,  # type: ignore[arg-type]
            provider=self.settings.provider_label,
            model=stats.model,
            endpoint_host=self.settings.endpoint_host,
            hardware_label=self.settings.hardware_label,
            request_id=stats.request_id,
            prompt_template=prompt_template,
            started_at=stats.started_at,
            latency_ms=stats.latency_ms,
            prompt_tokens=stats.prompt_tokens,
            completion_tokens=stats.completion_tokens,
            status=status,
            error=self.scrub(error) if error else None,
        )
        log.info(
            "ai_call module=%s status=%s model=%s host=%s latency_ms=%s request_id=%s",
            module,
            status,
            stats.model,
            trace.endpoint_host,
            trace.latency_ms,
            trace.request_id,
        )
        if self._sink is not None:
            try:
                self._sink(trace)
            except Exception:  # a broken sink must never break the run
                log.exception("trace sink failed")
        return trace

    @staticmethod
    def _request_id(response: httpx.Response, body: dict[str, Any] | None) -> str | None:
        for name in _REQUEST_ID_HEADERS:
            value = response.headers.get(name)
            if value:
                return value[:120]
        if body and isinstance(body.get("id"), str):
            return body["id"][:120]
        return None

    @staticmethod
    def _apply_usage(stats: CallStats, usage: Any) -> None:
        if isinstance(usage, dict):
            pt, ct = usage.get("prompt_tokens"), usage.get("completion_tokens")
            stats.prompt_tokens = pt if type(pt) is int and pt >= 0 else stats.prompt_tokens
            stats.completion_tokens = ct if type(ct) is int and ct >= 0 else stats.completion_tokens

    def _http_error(self, response: httpx.Response) -> AIUnavailableError:
        code = response.status_code
        try:
            snippet = response.text
        except Exception:
            snippet = ""
        if code in (401, 403):
            hint = "authentication rejected by the AMD endpoint"
            if (
                code == 401
                and self.settings.endpoint_host == "developer.amd.com.cn"
                and (self.settings.api_key or "").startswith("Rc-")
            ):
                hint += "; check AMD_LLM_API_KEY prefix: Token Factory documents 'rc-', not 'Rc-'"
        elif code == 404:
            hint = "endpoint or model not found"
        elif code == 429:
            hint = "rate limit or quota exhausted on the AMD endpoint"
        elif code >= 500:
            hint = "AMD endpoint server error"
        else:
            hint = "request rejected by the AMD endpoint"
        return AIUnavailableError(self.scrub(f"{hint} (HTTP {code}): {snippet}"))

    def _post(self, body: dict[str, Any]) -> httpx.Response:
        """POST with one retry on connection errors and transient upstream failures."""
        client = self._client()
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                response = client.post("/chat/completions", json=body, headers=self._headers())
            except httpx.TimeoutException as exc:
                raise AIUnavailableError(f"AMD endpoint timed out ({type(exc).__name__})") from exc
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                raise AIUnavailableError(
                    self.scrub(f"cannot reach AMD endpoint: {type(exc).__name__}: {exc}")
                ) from exc
            if self._retryable(response) and attempt == 0:
                time.sleep(0.5)
                continue
            return response
        raise AIUnavailableError(self.scrub(f"cannot reach AMD endpoint: {last_exc}"))

    @staticmethod
    def _retryable(response: httpx.Response) -> bool:
        if response.status_code in _TRANSIENT_STATUS:
            return True
        if response.status_code != 500:
            return False
        # Token Factory wraps the serving backend's transient 504 in HTTP 500.
        # Do not retry arbitrary 500s, authentication failures or quota errors.
        try:
            payload = response.json()
        except ValueError:
            return False
        error = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(error, dict):
            return False
        message = error.get("message")
        return error.get("code") == "call_upstream_timeout" or (
            isinstance(message, str) and "call_upstream_timeout" in message
        )

    def _rf_start(self, model: str) -> str:
        configured = self.settings.response_format
        if configured != "auto":
            return configured
        with self._lock:
            return self._rf_mode.get(model, "json_schema")

    def _rf_remember(self, model: str, mode: str) -> None:
        if self.settings.response_format == "auto":
            with self._lock:
                self._rf_mode[model] = mode

    # ------------------------------------------------------------------ public calls

    def complete(
        self,
        *,
        module: str,
        messages: list[dict[str, str]],
        stats: CallStats,
        schema_name: str | None = None,
        schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """One non-streaming chat completion. Raises :class:`AIUnavailableError`.

        With a schema, ``response_format`` json_schema (strict) is tried first; a 400/422 makes the
        client fall back to ``json_object`` and then to no response_format (the schema is always
        also written in the prompt). The working mode is remembered per model.
        """
        reason = self.settings.unavailable_reason(module)
        if reason:
            raise AIUnavailableError(reason)
        model = self.settings.model_for(module) or ""
        stats.model = model
        base: dict[str, Any] = {
            **self.settings.extra_body,
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens or self.settings.max_tokens_for(module),
            "temperature": self.settings.temperature,
        }
        modes: list[str] = ["none"]
        if schema is not None:
            start = self._rf_start(model)
            modes = list(_RF_CHAIN[_RF_CHAIN.index(start) :])
        for index, mode in enumerate(modes):
            body = dict(base)
            if mode == "json_schema" and schema is not None:
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name or "output",
                        "schema": schema,
                        "strict": True,
                    },
                }
            elif mode == "json_object":
                body["response_format"] = {"type": "json_object"}
            response = self._post(body)
            if response.status_code in (400, 422) and index < len(modes) - 1:
                log.warning(
                    "response_format=%s rejected (HTTP %s); falling back to %s",
                    mode,
                    response.status_code,
                    modes[index + 1],
                )
                continue
            if response.status_code != 200:
                stats.request_id = self._request_id(response, None)
                raise self._http_error(response)
            try:
                payload = response.json()
            except ValueError as exc:
                stats.request_id = self._request_id(response, None)
                raise AIUnavailableError("AMD endpoint returned a non-JSON body") from exc
            if not isinstance(payload, dict):
                stats.request_id = self._request_id(response, None)
                raise AIUnavailableError("AMD endpoint response is not a JSON object")
            stats.request_id = self._request_id(response, payload)
            if isinstance(payload.get("model"), str) and payload["model"]:
                stats.model = payload["model"]
            self._apply_usage(stats, payload.get("usage"))
            stats.response_format = mode
            if schema is not None:
                self._rf_remember(model, mode)
            stats.stop()
            try:
                content = payload["choices"][0]["message"].get("content")
            except (KeyError, IndexError, TypeError, AttributeError) as exc:
                raise AIUnavailableError("AMD endpoint response has no choices[0].message") from exc
            if content is not None and not isinstance(content, str):
                raise AIUnavailableError("AMD endpoint message content is not text")
            return ChatResult(content=content or "", stats=stats)
        raise AIUnavailableError("no response_format accepted by the AMD endpoint")

    def stream(
        self,
        *,
        module: str,
        messages: list[dict[str, str]],
        stats: CallStats,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Stream content deltas (SSE ``data:`` lines). Raises :class:`AIUnavailableError`."""
        reason = self.settings.unavailable_reason(module)
        if reason:
            raise AIUnavailableError(reason)
        model = self.settings.model_for(module) or ""
        stats.model = model
        body: dict[str, Any] = {
            **self.settings.extra_body,
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens or self.settings.max_tokens_for(module),
            "temperature": self.settings.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        client = self._client()
        timeout = httpx.Timeout(
            self.settings.stream_timeout_s, connect=self.settings.connect_timeout_s
        )
        for attempt in range(2):
            try:
                with client.stream(
                    "POST", "/chat/completions", json=body, headers=self._headers(), timeout=timeout
                ) as response:
                    if response.status_code in (400, 422) and attempt == 0:
                        response.read()
                        body.pop("stream_options", None)
                        continue
                    if response.status_code != 200:
                        response.read()
                        stats.request_id = self._request_id(response, None)
                        raise self._http_error(response)
                    stats.request_id = self._request_id(response, None)
                    yield from self._iter_sse(response, stats)
                    stats.stop()
                    return
            except httpx.TimeoutException as exc:
                raise AIUnavailableError(f"AMD endpoint timed out ({type(exc).__name__})") from exc
            except httpx.HTTPError as exc:
                raise AIUnavailableError(
                    self.scrub(f"AMD stream failed: {type(exc).__name__}: {exc}")
                ) from exc
        raise AIUnavailableError("AMD endpoint rejected the streaming request")

    def _iter_sse(self, response: httpx.Response, stats: CallStats) -> Iterator[str]:
        for line in response.iter_lines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError as exc:
                raise AIUnavailableError("AMD stream returned invalid JSON") from exc
            if not isinstance(chunk, dict):
                raise AIUnavailableError("AMD stream chunk is not a JSON object")
            if stats.request_id is None and isinstance(chunk.get("id"), str):
                stats.request_id = chunk["id"][:120]
            if isinstance(chunk.get("model"), str) and chunk["model"]:
                stats.model = chunk["model"]
            self._apply_usage(stats, chunk.get("usage"))
            if "error" in chunk:
                raise AIUnavailableError(self.scrub(f"AMD stream error: {chunk['error']}"))
            choices = chunk.get("choices") or []
            if not isinstance(choices, list):
                raise AIUnavailableError("AMD stream choices is not a list")
            for choice in choices:
                if not isinstance(choice, dict):
                    raise AIUnavailableError("AMD stream choice is not a JSON object")
                delta = choice.get("delta") or {}
                if not isinstance(delta, dict):
                    raise AIUnavailableError("AMD stream delta is not a JSON object")
                text = delta.get("content")
                if text is not None and not isinstance(text, str):
                    raise AIUnavailableError("AMD stream content is not text")
                if isinstance(text, str) and text:
                    yield text
        raise AIUnavailableError("AMD stream ended without a [DONE] marker")


__all__ = ["AIUnavailableError", "AMDChatClient", "CallStats", "ChatResult", "new_trace_id"]
