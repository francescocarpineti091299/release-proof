"""AMD LLM gateway settings, read from the environment.

Every LLM call must reach an endpoint that runs on AMD hardware. The base URL host is checked
against an explicit allowlist; there is no fallback provider.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlsplit

Module = Literal["planner", "explainer", "alternatives", "assistant", "smoke"]
MODULES: tuple[str, ...] = ("planner", "explainer", "alternatives", "assistant")
ResponseFormatMode = Literal["auto", "json_schema", "json_object", "none"]

DEFAULT_ALLOWED_HOSTS = ("developer.amd.com.cn",)
DEFAULT_PROVIDER_LABEL = "AMD-hosted endpoint"
DEFAULT_HARDWARE_LABEL = "AMD GPU (not disclosed by provider)"

# Fields of the request body an operator may never override through AMD_LLM_EXTRA_BODY.
_RESERVED_BODY_KEYS = frozenset(
    {"model", "messages", "stream", "response_format", "max_tokens", "temperature"}
)


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class AISettings:
    base_url: str | None = None
    api_key: str | None = field(default=None, repr=False)
    model: str | None = None
    module_models: Mapping[str, str] = field(default_factory=dict)
    provider_label: str = DEFAULT_PROVIDER_LABEL
    hardware_label: str = DEFAULT_HARDWARE_LABEL
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS
    connect_timeout_s: float = 10.0
    read_timeout_s: float = 90.0
    stream_timeout_s: float = 120.0
    temperature: float = 0.1
    max_tokens: Mapping[str, int] = field(default_factory=dict)
    response_format: ResponseFormatMode = "auto"
    extra_body: Mapping[str, Any] = field(default_factory=dict)
    max_context_chars: int = 24000
    env: str = "dev"

    # ------------------------------------------------------------------ construction

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AISettings:
        env = os.environ if env is None else env
        module_models = {
            m: env[f"AMD_LLM_MODEL_{m.upper()}"].strip()
            for m in MODULES
            if env.get(f"AMD_LLM_MODEL_{m.upper()}", "").strip()
        }
        hosts_raw = env.get("AMD_LLM_ALLOWED_HOSTS", "")
        hosts = tuple(h.strip().lower() for h in hosts_raw.split(",") if h.strip())
        rf = env.get("AMD_LLM_RESPONSE_FORMAT", "auto").strip().lower() or "auto"
        if rf not in ("auto", "json_schema", "json_object", "none"):
            rf = "auto"
        extra: dict[str, Any] = {}
        raw_extra = env.get("AMD_LLM_EXTRA_BODY", "").strip()
        if raw_extra:
            try:
                parsed = json.loads(raw_extra)
            except json.JSONDecodeError:
                parsed = {}
            if isinstance(parsed, dict):
                extra = {k: v for k, v in parsed.items() if k not in _RESERVED_BODY_KEYS}
        max_tokens = {
            "planner": _int(env, "AMD_LLM_MAX_TOKENS_PLANNER", 1200),
            "explainer": _int(env, "AMD_LLM_MAX_TOKENS_EXPLAINER", 1800),
            "alternatives": _int(env, "AMD_LLM_MAX_TOKENS_ALTERNATIVES", 1500),
            "assistant": _int(env, "AMD_LLM_MAX_TOKENS_ASSISTANT", 900),
            "smoke": 64,
        }
        return cls(
            base_url=(env.get("AMD_LLM_BASE_URL") or "").strip().rstrip("/") or None,
            api_key=(env.get("AMD_LLM_API_KEY") or "").strip() or None,
            model=(env.get("AMD_LLM_MODEL") or "").strip() or None,
            module_models=module_models,
            provider_label=(env.get("AMD_LLM_PROVIDER_LABEL") or "").strip()
            or DEFAULT_PROVIDER_LABEL,
            hardware_label=(env.get("AMD_LLM_HARDWARE_LABEL") or "").strip()
            or DEFAULT_HARDWARE_LABEL,
            allowed_hosts=hosts or DEFAULT_ALLOWED_HOSTS,
            connect_timeout_s=_float(env, "AMD_LLM_CONNECT_TIMEOUT_S", 10.0),
            read_timeout_s=_float(env, "AMD_LLM_TIMEOUT_S", 90.0),
            stream_timeout_s=_float(env, "AMD_LLM_STREAM_TIMEOUT_S", 120.0),
            temperature=min(_float(env, "AMD_LLM_TEMPERATURE", 0.1), 0.5),
            max_tokens=max_tokens,
            response_format=rf,  # type: ignore[arg-type]
            extra_body=extra,
            max_context_chars=_int(env, "AMD_LLM_MAX_CONTEXT_CHARS", 24000),
            env=(env.get("RELEASEPROOF_ENV") or "dev").strip().lower(),
        )

    # ------------------------------------------------------------------ derived

    @property
    def endpoint_host(self) -> str:
        if not self.base_url:
            return ""
        try:
            return (urlsplit(self.base_url).hostname or "").lower()
        except ValueError:
            return ""

    def model_for(self, module: str) -> str | None:
        return self.module_models.get(module) or self.model

    def max_tokens_for(self, module: str) -> int:
        return int(self.max_tokens.get(module, 1200))

    def unavailable_reason(self, module: str | None = None) -> str | None:
        """Why no call can be made (None when the gateway is usable). Never contains secrets."""
        if not self.base_url:
            return "AMD_LLM_BASE_URL is not set"
        try:
            parts = urlsplit(self.base_url)
        except ValueError:
            return "AMD_LLM_BASE_URL is not a valid URL"
        if parts.scheme not in ("http", "https"):
            return "AMD_LLM_BASE_URL must use http or https"
        host = (parts.hostname or "").lower()
        if not host:
            return "AMD_LLM_BASE_URL has no host"
        if host not in self.allowed_hosts:
            return (
                f"endpoint host '{host}' is not in AMD_LLM_ALLOWED_HOSTS "
                f"({', '.join(self.allowed_hosts)}); only AMD-hosted endpoints may be used"
            )
        if not self.api_key:
            return "AMD_LLM_API_KEY is not set"
        if module is not None and not self.model_for(module):
            return f"no model configured for module '{module}' (AMD_LLM_MODEL)"
        if module is None and not self.model and not self.module_models:
            return "AMD_LLM_MODEL is not set"
        return None

    @property
    def configured(self) -> bool:
        return self.unavailable_reason() is None


__all__ = ["AISettings", "MODULES", "Module", "ResponseFormatMode"]
