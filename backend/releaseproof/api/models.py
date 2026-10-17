"""API-local response models (not part of the shared contract)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from releaseproof.contracts.api import ResultView, RunView
from releaseproof.contracts.profile import (
    AlternativePlan,
    Board,
    Bootloader,
    ChangeScenario,
    Profile,
    TestTemplate,
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthView(_Model):
    status: Literal["ok"] = "ok"
    env: str
    schema_version: int
    expose_experimental: bool


class TemplateView(_Model):
    template_id: str
    test_id: str
    title: str
    description: str
    negative: bool
    expected: str
    est_seconds: int
    required: bool


class ChangeView(_Model):
    change_id: str
    title: str
    summary: str
    from_scheme: str
    to_scheme: str
    default_plan_id: str
    default_plan_title: str
    templates: list[TemplateView]
    alternatives: list[AlternativePlan]
    est_seconds_total: int


class ConfigurationView(_Model):
    id: str
    version: str
    status: str
    title: str
    description: str
    board: Board
    bootloader: Bootloader
    toolchain: dict[str, str]
    runner_image: str
    timeout_seconds: int
    ruleset_version: str
    known_limitations: list[str]
    changes: list[ChangeView]


class PlannedTestView(_Model):
    template_id: str
    test_id: str
    planned_by: Literal["POLICY_REQUIRED", "AI_PLANNER", "PROFILE_OPTIONAL"]
    title: str
    negative: bool
    est_seconds: int
    params: dict[str, Any] = Field(default_factory=dict)


class ReferenceView(_Model):
    recorded: Literal[True] = True
    recorded_at: str
    notice: str
    canonical_hash: str | None
    run: RunView
    result: ResultView


class AmdView(_Model):
    provider: dict[str, Any]
    traces: dict[str, Any]


def _change_view(change: ChangeScenario, catalog: dict[str, TestTemplate]) -> ChangeView:
    ids = list(dict.fromkeys([*change.required_templates, *change.optional_templates]))
    templates = [
        TemplateView(
            template_id=tid,
            test_id=catalog[tid].test_id,
            title=catalog[tid].title,
            description=catalog[tid].description,
            negative=catalog[tid].negative,
            expected=catalog[tid].expected,
            est_seconds=catalog[tid].est_seconds,
            required=tid in change.required_templates,
        )
        for tid in ids
    ]
    return ChangeView(
        change_id=change.change_id,
        title=change.title,
        summary=change.summary.strip(),
        from_scheme=change.from_scheme,
        to_scheme=change.to_scheme,
        default_plan_id=change.default_plan_id,
        default_plan_title=change.default_plan_title,
        templates=templates,
        alternatives=change.alternatives,
        est_seconds_total=sum(t.est_seconds for t in templates),
    )


def configuration_view(profile: Profile, catalog: dict[str, TestTemplate]) -> ConfigurationView:
    return ConfigurationView(
        id=profile.id,
        version=profile.version,
        status=profile.status.value,
        title=profile.title,
        description=profile.description.strip(),
        board=profile.board,
        bootloader=profile.bootloader,
        toolchain=profile.toolchain,
        runner_image=profile.runner.image,
        timeout_seconds=profile.runner.timeout_seconds,
        ruleset_version=profile.ruleset_version,
        known_limitations=profile.known_limitations,
        changes=[_change_view(c, catalog) for c in profile.changes],
    )
