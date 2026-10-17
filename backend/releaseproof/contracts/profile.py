"""Configuration registry: versioned device/bootloader profiles and the test template catalog."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    EXPERIMENTAL = "EXPERIMENTAL"
    UNAVAILABLE = "UNAVAILABLE"


class Board(_Strict):
    id: str
    name: str
    soc: str
    emulator: Literal["renode"]
    platform_script: str


class Bootloader(_Strict):
    family: Literal["wolfboot", "mcuboot"]
    name: str
    repo: str
    commit: str
    version_label: str
    license: str


class AlternativePlan(_Strict):
    plan_id: str
    title: str
    description: str
    mechanism: str
    requires_rerun_tests: bool = False
    status: Literal["EXECUTABLE", "REQUIRES_EXTERNAL_VALIDATION"] = "EXECUTABLE"


class ChangeScenario(_Strict):
    change_id: str
    title: str
    summary: str
    from_scheme: str
    to_scheme: str
    default_plan_id: str
    default_plan_title: str
    required_templates: list[str]
    optional_templates: list[str] = Field(default_factory=list)
    alternatives: list[AlternativePlan] = Field(default_factory=list)


class Runner(_Strict):
    service: str = Field(description="Compose service name / base URL key")
    image: str
    timeout_seconds: int = Field(ge=60, le=3600)


class Profile(_Strict):
    id: str
    version: str
    status: ProfileStatus
    title: str
    description: str
    board: Board
    bootloader: Bootloader
    toolchain: dict[str, str]
    runner: Runner
    changes: list[ChangeScenario]
    assessment_adapter: str
    ruleset_version: Literal["1.2"]
    known_limitations: list[str] = Field(default_factory=list)


class TestTemplate(_Strict):
    template_id: str
    test_id: str = Field(description="Bootloader-agnostic catalog test (E01, E02, E03, X01, ...)")
    family: Literal["wolfboot", "mcuboot"]
    title: str
    description: str
    negative: bool = False
    expected: str
    params_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    est_seconds: int = Field(ge=1)


class TestCatalog(_Strict):
    version: str
    tests: dict[str, str] = Field(description="test_id -> generic meaning")
    templates: list[TestTemplate]
