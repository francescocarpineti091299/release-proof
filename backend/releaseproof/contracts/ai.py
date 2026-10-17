"""Structured outputs the AMD-hosted LLM must return. Validated before use; never verdicts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------ test planner


class PlannedTemplate(_Strict):
    template_id: str = Field(description="Must be a template_id from the provided catalog")
    priority: int = Field(ge=1, le=10, description="1 = run first")
    rationale: str = Field(max_length=400)


class SkippedTemplate(_Strict):
    template_id: str
    reason: str = Field(max_length=300)


class SuggestedTest(_Strict):
    """A test idea that has no registered implementation. Never executed automatically."""

    title: str = Field(max_length=120)
    purpose: str = Field(max_length=400)


class TestPlanProposal(_Strict):
    selected: list[PlannedTemplate]
    skipped: list[SkippedTemplate] = Field(default_factory=list)
    suggested_new_tests: list[SuggestedTest] = Field(default_factory=list, max_length=3)
    summary: str = Field(max_length=600)


# ------------------------------------------------------------ explainer / reporter


class CitedStatement(_Strict):
    text: str = Field(max_length=500)
    citations: list[str] = Field(
        description="IDs of evidence, requirement, invariant or gap present in the context",
        min_length=1,
    )


class NarrativeReport(_Strict):
    headline: str = Field(max_length=200)
    verdict_echo: dict[Literal["migration", "candidate", "transition"], str | None]
    main_causes: list[CitedStatement] = Field(min_length=1, max_length=3)
    verified: list[CitedStatement] = Field(default_factory=list, max_length=8)
    unknowns: list[CitedStatement] = Field(default_factory=list, max_length=6)
    executive_summary: str = Field(max_length=800)


# ------------------------------------------------------------ alternatives


class ChangeProposal(_Strict):
    plan_id: str = Field(description="Must be one of the allowed alternative plan_ids")
    title: str = Field(max_length=120)
    rationale: str = Field(max_length=600)
    addresses: list[str] = Field(description="Blocking requirement/invariant IDs it addresses")
    preconditions: list[str] = Field(default_factory=list, max_length=6)
    tradeoffs: list[str] = Field(default_factory=list, max_length=4)
    evidence_still_needed: list[str] = Field(default_factory=list, max_length=6)


class AlternativesProposal(_Strict):
    proposals: list[ChangeProposal] = Field(max_length=4)
    not_addressable: list[str] = Field(
        default_factory=list, description="Blockers no allowed plan can address"
    )
