"""Pydantic result models for validation and evaluation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from releaseproof.core.domain.enums import AssessmentLifecycle, Verdict


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lifecycle: AssessmentLifecycle
    errors: list[str] = Field(default_factory=list)
    ready: bool


class SemanticAssessmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: str
    lifecycle: AssessmentLifecycle
    official: bool = False
    migration_verdict: Verdict | None = None
    candidate_verdict: Verdict | None = None
    transition_verdict: Verdict | None = None
    candidate_state_assurance: dict[str, Verdict] | None = None
    transition_plan_assurance: dict[str, Verdict] | None = None
    requirement_evaluation_results: list[dict[str, Any]] = Field(default_factory=list)
    invariant_evaluation_results: list[dict[str, Any]] = Field(default_factory=list)
    explanation_graph: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    canonical_hash: str | None = None


__all__ = ["SemanticAssessmentResult", "ValidationResult"]
