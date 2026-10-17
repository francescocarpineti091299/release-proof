"""Template execution engine shared by all runner families.

Execution order for one request (one run):
  PREPARING        family.prepare(ctx): isolated workdir, copy pinned sources
  DISCOVERY        templates with phase == "DISCOVERY" -> run()
  BUILD_SIGN       build() of every TEST template (builds are memoised in ctx.cache)
  EMULATION_TESTS  run() of every TEST template, in the requested order

A template's run() returns a TemplateResult; the engine emits the test_result event.
A test that observes a failure is a *result*, not a runner error: the run still SUCCEEDS.
The run FAILS only when the environment/infrastructure prevents producing results.
"""

from __future__ import annotations

import shutil
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from rp_runner.events import EventSink


class BuildFailed(Exception):
    """A build/sign step failed. Carries the log path for evidence."""

    def __init__(self, message: str, log_path: Path | None = None) -> None:
        super().__init__(message)
        self.log_path = log_path


class EnvironmentFailure(Exception):
    """Tooling or setup missing: the run cannot produce trustworthy results."""


@dataclass
class TemplateResult:
    outcome: str  # PASS | FAIL | INCONCLUSIVE | NOT_EXECUTED | ERROR
    observed: str
    observation_ids: list[str] = field(default_factory=list)
    failure_class: str | None = None


@dataclass
class RunContext:
    run_id: str
    sink: EventSink
    workdir: Path
    artifact_dir: Path
    deadline: float
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=dict)
    cancelled: Callable[[], bool] = lambda: False
    _next_port: int = 0

    def remaining(self, cap: float | None = None) -> float:
        left = max(1.0, self.deadline - time.monotonic())
        return min(left, cap) if cap else left

    def expired(self) -> bool:
        return time.monotonic() >= self.deadline

    def artifact_path(self, *parts: str) -> Path:
        path = self.artifact_dir.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def alloc_port(self, base: int = 40000) -> int:
        """Ports unique within this runner process (one run at a time per runner)."""
        self._next_port += 1
        return base + self._next_port


class Template:
    template_id: str = ""
    test_id: str = ""
    phase: str = "TEST"  # "DISCOVERY" | "TEST"
    expected: str = ""

    def build(self, ctx: RunContext) -> None:  # pragma: no cover - optional hook
        return None

    def run(self, ctx: RunContext) -> TemplateResult:
        raise NotImplementedError


class Family:
    """A bootloader family runner (wolfboot, mcuboot)."""

    name: str = ""
    templates: dict[str, Template] = {}

    def prepare(self, ctx: RunContext) -> None:
        raise NotImplementedError

    def tool_versions(self) -> dict[str, str]:
        return {}

    def source_pins(self) -> dict[str, str]:
        return {}


def execute(
    family: Family,
    request: dict[str, Any],
    write: Callable[[str], None],
    *,
    cancelled: Callable[[], bool] = lambda: False,
    work_root: Path | None = None,
) -> str:
    run_id = str(request["run_id"])
    artifact_dir = Path(request["artifact_dir"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    sink = EventSink(run_id, artifact_dir, write)
    planned = list(request.get("tests") or [])
    deadline = time.monotonic() + int(request.get("timeout_seconds") or 900)
    workdir = Path(tempfile.mkdtemp(prefix=f"rp-{run_id}-", dir=str(work_root) if work_root else None))
    ctx = RunContext(
        run_id=run_id,
        sink=sink,
        workdir=workdir,
        artifact_dir=artifact_dir,
        deadline=deadline,
        params={t["template_id"]: dict(t.get("params") or {}) for t in planned},
        cancelled=cancelled,
    )
    status = "FAILED"
    try:
        status = _execute(family, ctx, [t["template_id"] for t in planned])
    except Exception as exc:  # noqa: BLE001 - last-resort guard, reported as INTERNAL
        sink.error("INTERNAL", f"{type(exc).__name__}: {exc}")
        sink.log("runner", traceback.format_exc()[-3000:])
        status = "FAILED"
    finally:
        sink.done(
            status,
            summary=f"{family.name} runner finished with {status}",
            tool_versions=_safe(family.tool_versions),
            source_pins=_safe(family.source_pins),
        )
        shutil.rmtree(workdir, ignore_errors=True)
    return status


def _safe(fn: Callable[[], dict[str, str]]) -> dict[str, str]:
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return {}


def _execute(family: Family, ctx: RunContext, template_ids: list[str]) -> str:
    sink = ctx.sink
    sink.stage("PREPARING", "RUNNING", f"{family.name}: isolated workspace for {ctx.run_id}")
    unknown = [tid for tid in template_ids if tid not in family.templates]
    if unknown:
        sink.error("INTERNAL", f"templates not registered in this runner: {unknown}")
        sink.stage("PREPARING", "FAILED", "unregistered templates requested")
        return "FAILED"
    try:
        family.prepare(ctx)
    except EnvironmentFailure as exc:
        sink.error("ENVIRONMENT_SETUP", str(exc))
        sink.stage("PREPARING", "FAILED", str(exc))
        return "FAILED"
    sink.stage("PREPARING", "SUCCEEDED")

    templates = [family.templates[tid] for tid in template_ids]
    discovery = [t for t in templates if t.phase == "DISCOVERY"]
    tests = [t for t in templates if t.phase != "DISCOVERY"]

    if discovery:
        sink.stage("DISCOVERY", "RUNNING")
        statuses = [_run_one(ctx, t) for t in discovery]
        sink.stage("DISCOVERY", _phase_status(statuses))

    build_errors: dict[str, BuildFailed] = {}
    if tests:
        sink.stage("BUILD_SIGN", "RUNNING")
        build_failed = False
        for t in tests:
            if ctx.expired() or ctx.cancelled():
                break
            try:
                t.build(ctx)
            except BuildFailed as exc:
                build_errors[t.template_id] = exc
                build_failed = True
                sink.error("BUILD_FAILED", str(exc), test_id=t.test_id)
        sink.stage("BUILD_SIGN", "FAILED" if build_failed else "SUCCEEDED")

        sink.stage("EMULATION_TESTS", "RUNNING")
        statuses = []
        for t in tests:
            if t.template_id in build_errors:
                sink.test_result(
                    test_id=t.test_id,
                    template_id=t.template_id,
                    outcome="ERROR",
                    expected=t.expected,
                    observed=f"build failed: {build_errors[t.template_id]}",
                    duration_ms=0,
                    failure_class="BUILD_FAILED",
                )
                statuses.append("ERROR")
                continue
            statuses.append(_run_one(ctx, t))
        sink.stage("EMULATION_TESTS", _phase_status(statuses))
    return "SUCCEEDED"


def _run_one(ctx: RunContext, template: Template) -> str:
    sink = ctx.sink
    if ctx.expired() or ctx.cancelled():
        reason = "cancelled" if ctx.cancelled() else "run deadline exceeded"
        sink.test_result(
            test_id=template.test_id,
            template_id=template.template_id,
            outcome="NOT_EXECUTED",
            expected=template.expected,
            observed=reason,
            duration_ms=0,
            failure_class="TIMEOUT",
        )
        return "NOT_EXECUTED"
    started = time.monotonic()
    try:
        result = template.run(ctx)
    except BuildFailed as exc:
        result = TemplateResult("ERROR", f"build failed: {exc}", failure_class="BUILD_FAILED")
    except EnvironmentFailure as exc:
        result = TemplateResult("ERROR", str(exc), failure_class="ENVIRONMENT_SETUP")
    except Exception as exc:  # noqa: BLE001
        sink.log("runner", traceback.format_exc()[-3000:], test_id=template.test_id)
        result = TemplateResult("ERROR", f"{type(exc).__name__}: {exc}", failure_class="INTERNAL")
    sink.test_result(
        test_id=template.test_id,
        template_id=template.template_id,
        outcome=result.outcome,
        expected=template.expected,
        observed=result.observed,
        duration_ms=int((time.monotonic() - started) * 1000),
        observation_ids=result.observation_ids,
        failure_class=result.failure_class,
    )
    return result.outcome


def _phase_status(outcomes: list[str]) -> str:
    if any(o == "ERROR" for o in outcomes):
        return "FAILED"
    if any(o in {"INCONCLUSIVE", "NOT_EXECUTED"} for o in outcomes):
        return "INCONCLUSIVE"
    return "SUCCEEDED"
