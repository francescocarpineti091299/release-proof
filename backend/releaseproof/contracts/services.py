"""Interfaces between backend modules (implemented by adapters/ and ai/, used by orchestrator/).

These are the seams that let the workstreams be built in parallel. Do not change signatures
without updating all implementers.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, Protocol

from releaseproof.contracts.api import (
    AIAlternativesView,
    AIPlanView,
    AIReportView,
    AITraceView,
    AssistantMessage,
)
from releaseproof.contracts.profile import ChangeScenario, Profile, TestTemplate
from releaseproof.contracts.runner import ArtifactEvent, Observation, TestResultEvent


class AdapterError(ValueError):
    """The run's facts cannot be projected into a valid V1.2 assessment."""


class AssessmentAdapter(Protocol):
    """Project live runner facts into a V1.2 assessment document (pure, deterministic)."""

    def __call__(
        self,
        *,
        profile: Profile,
        change: ChangeScenario,
        plan_id: str,
        run_id: str,
        evidence_run_id: str,
        created_at: str,
        observations: list[Observation],
        artifacts: list[ArtifactEvent],
        test_results: list[TestResultEvent],
    ) -> dict[str, Any]:
        """Return a V1.2 assessment dict.

        ``run_id`` is the run being evaluated; ``evidence_run_id`` is the LIVE run whose
        observations are used (equal to run_id for LIVE runs, the parent for REEVALUATION).
        Facts that were not observed must appear as UNKNOWN / gaps, never as defaults.
        """
        ...


TraceSink = Callable[[AITraceView], None]


class AIServiceProtocol(Protocol):
    def plan_tests(
        self,
        *,
        run_id: str,
        profile: Profile,
        change: ChangeScenario,
        templates: list[TestTemplate],
    ) -> AIPlanView: ...

    def explain(
        self,
        *,
        run_id: str,
        profile: Profile,
        change: ChangeScenario,
        plan_id: str,
        assessment: dict[str, Any],
        result: dict[str, Any],
        test_results: list[dict[str, Any]],
    ) -> AIReportView: ...

    def alternatives(
        self,
        *,
        run_id: str,
        profile: Profile,
        change: ChangeScenario,
        plan_id: str,
        assessment: dict[str, Any],
        result: dict[str, Any],
    ) -> AIAlternativesView: ...

    def assistant_stream(
        self,
        *,
        run_id: str,
        context: dict[str, Any],
        messages: list[AssistantMessage],
    ) -> Iterator[str]: ...

    def provider_info(self) -> dict[str, Any]: ...
