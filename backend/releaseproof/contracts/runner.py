"""Runner protocol: request sent to a runner and NDJSON events streamed back.

The JSON Schema in ``schemas/runner_event.schema.json`` is generated from these models
(``python -m releaseproof.contracts.export``). Runners must emit events matching it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Stage(StrEnum):
    PREPARING = "PREPARING"
    DISCOVERY = "DISCOVERY"
    AI_PLAN = "AI_PLAN"
    BUILD_SIGN = "BUILD_SIGN"
    EMULATION_TESTS = "EMULATION_TESTS"
    EVALUATION = "EVALUATION"
    NEXT_STEPS = "NEXT_STEPS"


class StageStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"
    SKIPPED = "SKIPPED"


class FailureClass(StrEnum):
    ENVIRONMENT_SETUP = "ENVIRONMENT_SETUP"
    BUILD_FAILED = "BUILD_FAILED"
    TOOL_FAILURE = "TOOL_FAILURE"
    TIMEOUT = "TIMEOUT"
    INCONCLUSIVE = "INCONCLUSIVE"
    INTERNAL = "INTERNAL"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"


class Origin(StrEnum):
    MEASURED_TOOL = "MEASURED_TOOL"
    OBSERVED_EMULATION = "OBSERVED_EMULATION"
    DECLARED = "DECLARED"
    AI_PROPOSAL = "AI_PROPOSAL"


class TestOutcome(StrEnum):
    """Outcome of executing a test template. Not a migration verdict.

    PASS means the test observed what it was designed to check (a negative test that
    observes the expected rejection is PASS). FAIL means the opposite was observed.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_EXECUTED = "NOT_EXECUTED"
    ERROR = "ERROR"


class PlannedTest(_Strict):
    template_id: str
    params: dict[str, Any] = Field(default_factory=dict)


class RunnerRequest(_Strict):
    run_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{6,80}$")
    profile_id: str
    change_id: str
    tests: list[PlannedTest]
    artifact_dir: str = Field(description="Absolute path (shared volume) for this run's artifacts")
    timeout_seconds: int = Field(default=900, ge=30, le=3600)


class _EventBase(_Strict):
    seq: int = Field(ge=0)
    ts: str = Field(description="RFC 3339 UTC timestamp")
    run_id: str


class StageEvent(_EventBase):
    type: Literal["stage"] = "stage"
    stage: Stage
    status: StageStatus
    message: str = ""


class LogEvent(_EventBase):
    type: Literal["log"] = "log"
    stream: Literal["build", "sign", "renode", "uart", "tool", "runner"]
    line: str = Field(max_length=4000)
    test_id: str | None = None


class ArtifactEvent(_EventBase):
    type: Literal["artifact"] = "artifact"
    artifact_id: str
    name: str
    path: str = Field(description="Relative to the run artifact_dir")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    kind: Literal[
        "elf", "bin", "signed_image", "log", "uart", "script", "config", "manifest", "other"
    ]
    test_id: str | None = None


class Observation(_Strict):
    observation_id: str
    test_id: str
    subject: Literal["deployed_state", "candidate_state", "transition", "platform", "toolchain"]
    fact: str
    value: Any
    unit: str | None = None
    origin: Origin
    acquisition_mode: str = Field(
        description="V1.2 acquisition_mode, e.g. EMULATED, STATIC_ARTIFACT, STATIC_CONFIG, "
        "SOURCE_INSPECTION, SIGN_TOOL, BUILD, REPOSITORY"
    )
    source_artifact_ids: list[str] = Field(default_factory=list)
    locator: str | None = Field(default=None, description="e.g. uart.log:L12-L14")
    parser: str = Field(description="parser id@version")


class ObservationEvent(_EventBase):
    type: Literal["observation"] = "observation"
    observation: Observation


class TestResultEvent(_EventBase):
    type: Literal["test_result"] = "test_result"
    test_id: str
    template_id: str
    outcome: TestOutcome
    expected: str
    observed: str
    duration_ms: int = Field(ge=0)
    observation_ids: list[str] = Field(default_factory=list)
    failure_class: FailureClass | None = None


class ErrorEvent(_EventBase):
    type: Literal["error"] = "error"
    failure_class: FailureClass
    message: str
    test_id: str | None = None


class DoneEvent(_EventBase):
    type: Literal["done"] = "done"
    status: Literal["SUCCEEDED", "FAILED"]
    summary: str = ""
    tool_versions: dict[str, str] = Field(default_factory=dict)
    source_pins: dict[str, str] = Field(default_factory=dict)


RunnerEvent = Annotated[
    StageEvent
    | LogEvent
    | ArtifactEvent
    | ObservationEvent
    | TestResultEvent
    | ErrorEvent
    | DoneEvent,
    Field(discriminator="type"),
]


class RunnerEventEnvelope(BaseModel):
    event: RunnerEvent
