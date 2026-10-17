"""Public HTTP API view models consumed by the web UI."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from releaseproof.contracts.ai import AlternativesProposal, NarrativeReport, TestPlanProposal
from releaseproof.contracts.runner import FailureClass, Stage, StageStatus, TestOutcome


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"  # pipeline completed; says nothing about the migration verdict
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunMode(StrEnum):
    LIVE = "LIVE"  # fresh build/sign/emulation in this run
    REEVALUATION = "REEVALUATION"  # alternative plan evaluated on evidence of a parent LIVE run
    REFERENCE = "REFERENCE"  # recorded WP0 freeze (2026-10-01); never presented as live


class AIStatus(StrEnum):
    OK = "OK"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    REJECTED_BY_GUARDRAIL = "REJECTED_BY_GUARDRAIL"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    NOT_REQUESTED = "NOT_REQUESTED"


class RunCreate(_Model):
    configuration_id: str
    change_id: str
    plan_id: str | None = Field(default=None, description="Defaults to the change's default plan")
    idempotency_key: str | None = Field(default=None, max_length=80)


class StageView(_Model):
    stage: Stage
    status: StageStatus
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    message: str = ""


class TestResultView(_Model):
    test_id: str
    template_id: str
    title: str
    negative: bool
    outcome: TestOutcome
    expected: str
    observed: str
    duration_ms: int
    observation_ids: list[str] = Field(default_factory=list)
    failure_class: FailureClass | None = None
    planned_by: Literal["POLICY_REQUIRED", "AI_PLANNER", "PROFILE_OPTIONAL"]


class VerdictView(_Model):
    lifecycle: str
    migration: str | None
    candidate: str | None
    transition: str | None
    canonical_hash: str | None
    official: Literal[False] = False


class FailureView(_Model):
    failure_class: FailureClass
    message: str


class AIArtifact(_Model):
    status: AIStatus
    trace_ids: list[str] = Field(default_factory=list)
    message: str = ""


class AIPlanView(AIArtifact):
    proposal: TestPlanProposal | None = None
    blocked_templates: list[str] = Field(
        default_factory=list, description="Templates the model proposed that are not registered"
    )


class AIReportView(AIArtifact):
    report: NarrativeReport | None = None


class AIAlternativesView(AIArtifact):
    alternatives: AlternativesProposal | None = None


class RunView(_Model):
    run_id: str
    mode: RunMode
    status: RunStatus
    configuration_id: str
    configuration_version: str
    change_id: str
    plan_id: str
    parent_run_id: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    queue_position: int | None = None
    stages: list[StageView]
    tests: list[TestResultView] = Field(default_factory=list)
    verdict: VerdictView | None = None
    failure: FailureView | None = None
    ai_plan: AIPlanView | None = None
    ai_report: AIReportView | None = None
    ai_alternatives: AIAlternativesView | None = None
    source_pins: dict[str, str] = Field(default_factory=dict)
    tool_versions: dict[str, str] = Field(default_factory=dict)


class ArtifactView(_Model):
    artifact_id: str
    name: str
    kind: str
    sha256: str
    size_bytes: int
    test_id: str | None = None
    url: str


class EvidenceView(_Model):
    """One V1.2 evidence row plus where it came from in this run."""

    id: str
    test_id: str | None
    value: Any
    evidence_kind: str
    acquisition_mode: str
    origin: str
    run_id: str | None
    artifacts: list[ArtifactView] = Field(default_factory=list)
    locator: str | None = None


class ResultView(_Model):
    run_id: str
    assessment: dict[str, Any] = Field(description="V1.2 assessment document evaluated")
    result: dict[str, Any] = Field(description="SemanticAssessmentResult (contract V1.2)")
    gap_plan: dict[str, Any] | list[Any] | None = None
    dossier_markdown: str | None = None
    evidence: list[EvidenceView]
    manifest_sha256: str


class AITraceView(_Model):
    trace_id: str
    run_id: str | None
    module: Literal["planner", "explainer", "alternatives", "assistant", "smoke"]
    provider: str
    model: str
    endpoint_host: str
    hardware_label: str
    request_id: str | None
    prompt_template: str
    started_at: str
    latency_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    status: AIStatus
    error: str | None = None


class AssistantMessage(_Model):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=12000)


class AssistantRequest(_Model):
    run_id: str
    messages: list[AssistantMessage] = Field(min_length=1, max_length=24)


class SSEEvent(_Model):
    """Server-sent event payload. `event:` line carries `type`."""

    id: int
    type: Literal[
        "stage", "log", "artifact", "observation", "test_result", "error", "done", "run", "ai"
    ]
    data: dict[str, Any]
