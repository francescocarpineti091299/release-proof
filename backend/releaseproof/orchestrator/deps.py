"""Dependency injection for modules owned by other workstreams (adapters, AI gateway).

They are imported lazily so the orchestrator works (and fails honestly) while they are absent,
and tests can inject fakes. Expected seams:

* ``releaseproof.adapters.get_adapter(name) -> AssessmentAdapter`` (contracts/services.py)
* ``releaseproof.adapters.evidence_index(*, assessment, observations, artifacts)`` (optional)
  ``-> list[EvidenceView dict]`` in assessment order (a ``{evidence_id: hints}`` mapping is
  also accepted); presentation only, never an input of ``evaluate()``.
* ``releaseproof.ai.service.AIService`` implementing ``AIServiceProtocol``, built with
  ``AIService.from_env(trace_sink)`` or ``AIService(settings, trace_sink)`` where settings come
  from ``releaseproof.ai.config``.
"""

from __future__ import annotations

import importlib
import logging
import threading
from collections.abc import Callable
from typing import Any

import httpx

from releaseproof.contracts.services import AIServiceProtocol, AssessmentAdapter, TraceSink

log = logging.getLogger(__name__)

AdapterFactory = Callable[[str], AssessmentAdapter]
EvidenceIndexer = Callable[..., dict[str, dict[str, Any]]]
AIFactory = Callable[[TraceSink], AIServiceProtocol]


class DependencyUnavailable(RuntimeError):
    pass


def _default_adapter_factory(name: str) -> AssessmentAdapter:
    try:
        module = importlib.import_module("releaseproof.adapters")
    except ImportError as exc:
        raise DependencyUnavailable(f"assessment adapters not installed: {exc}") from exc
    return module.get_adapter(name)


def _default_evidence_indexer() -> EvidenceIndexer | None:
    try:
        module = importlib.import_module("releaseproof.adapters")
    except ImportError:
        return None
    return getattr(module, "evidence_index", None)


def _load_ai_settings() -> Any:
    config = importlib.import_module("releaseproof.ai.config")
    for name in ("load_settings", "get_settings", "load_ai_settings"):
        fn = getattr(config, name, None)
        if callable(fn):
            return fn()
    for name in ("AISettings", "Settings"):
        cls = getattr(config, name, None)
        if cls is not None and callable(getattr(cls, "from_env", None)):
            return cls.from_env()
    raise DependencyUnavailable("releaseproof.ai.config exposes no settings loader")


def _default_ai_factory(trace_sink: TraceSink) -> AIServiceProtocol:
    try:
        service = importlib.import_module("releaseproof.ai.service")
    except ImportError as exc:
        raise DependencyUnavailable(f"AI gateway not installed: {exc}") from exc
    from_env = getattr(service.AIService, "from_env", None)
    if callable(from_env):
        return from_env(trace_sink)
    return service.AIService(_load_ai_settings(), trace_sink)


class Deps:
    def __init__(
        self,
        *,
        adapter_factory: AdapterFactory | None = None,
        evidence_indexer: EvidenceIndexer | None | bool = True,
        ai_factory: AIFactory | None = None,
        runner_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._evidence_indexer = evidence_indexer
        self._ai_factory = ai_factory or _default_ai_factory
        self.runner_transport = runner_transport
        self._ai: AIServiceProtocol | None = None
        self._ai_error: str | None = None
        self._lock = threading.Lock()

    def get_adapter(self, name: str) -> AssessmentAdapter:
        return self._adapter_factory(name)

    def evidence_indexer(self) -> EvidenceIndexer | None:
        if self._evidence_indexer is True:
            return _default_evidence_indexer()
        return self._evidence_indexer or None

    def ai(self, trace_sink: TraceSink) -> AIServiceProtocol | None:
        """The AI service, or None (caller reports AI_UNAVAILABLE). Construction is retried."""
        with self._lock:
            if self._ai is None:
                try:
                    self._ai = self._ai_factory(trace_sink)
                    self._ai_error = None
                except Exception as exc:  # noqa: BLE001 - AI must never break the pipeline
                    self._ai_error = f"{type(exc).__name__}: {exc}"
                    log.warning("AI service unavailable: %s", self._ai_error)
                    return None
            return self._ai

    @property
    def ai_error(self) -> str | None:
        return self._ai_error
