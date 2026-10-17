"""Shared fakes for orchestrator/API tests: runner (real rp_runner engine behind
httpx.MockTransport), adapter and AI service."""

from __future__ import annotations

import copy
import json
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx

from releaseproof.contracts.ai import (
    AlternativesProposal,
    ChangeProposal,
    PlannedTemplate,
    TestPlanProposal,
)
from releaseproof.contracts.api import (
    AIAlternativesView,
    AIPlanView,
    AIReportView,
    AIStatus,
    AITraceView,
)
from releaseproof.core.projection.wp0 import build_wp0_baseline_assessment
from releaseproof.orchestrator.deps import Deps
from releaseproof.orchestrator.service import Orchestrator
from releaseproof.orchestrator.settings import Settings
from releaseproof.profiles import registry
from releaseproof.store.db import Store

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "runners" / "common"))

from rp_runner.engine import (  # noqa: E402
    EnvironmentFailure,
    Family,
    Template,
    TemplateResult,
    execute,
)

GOLDEN_BASELINE_HASH = "sha256:0a4a6ecbfe034f4965fd7b0f01085226083f0574c2db18813e1eaa1039e73d31"
WOLFBOOT = "nrf52840-wolfboot-pqc"
WOLFBOOT_CHANGE = "ecdsa_p256_to_mldsa87"
MCUBOOT = "nrf52840-mcuboot-pqc"
MCUBOOT_CHANGE = "ecdsa_p256_to_mldsa"
_DISCOVERY_TESTS = {"D01", "E11"}


class _GenericTemplate(Template):
    def __init__(self, template_id: str, test_id: str, expected: str) -> None:
        self.template_id = template_id
        self.test_id = test_id
        self.expected = expected
        self.phase = "DISCOVERY" if test_id in _DISCOVERY_TESTS else "TEST"

    def build(self, ctx: Any) -> None:
        if self.phase == "TEST":
            image = ctx.artifact_path(self.test_id, "image_signed.bin")
            image.write_bytes(b"\x7fSIGNED" + self.template_id.encode())
            ctx.cache.setdefault("images", {})[self.template_id] = ctx.sink.artifact(
                image,
                kind="signed_image",
                test_id=self.test_id,
                artifact_id=f"ART-{self.template_id}-image",
            )

    def run(self, ctx: Any) -> TemplateResult:
        log = ctx.artifact_path(self.test_id, f"{self.template_id}.uart.log")
        log.write_text(f"[{self.template_id}] wolfBoot v1 boot ok\nversion=1\n", encoding="utf-8")
        aid = ctx.sink.artifact(
            log, kind="uart", test_id=self.test_id, artifact_id=f"ART-{self.template_id}-uart"
        )
        ctx.sink.log("uart", f"[{self.template_id}] version=1", test_id=self.test_id)
        oid = ctx.sink.observation(
            observation_id=f"OBS-{self.template_id}-outcome",
            test_id=self.test_id,
            subject="deployed_state",
            fact="boot_outcome",
            value="BOOT_OK",
            origin="OBSERVED_EMULATION",
            acquisition_mode="EMULATED",
            parser="fake-uart@1",
            source_artifact_ids=[aid],
            locator=f"{log.name}:L1-L2",
        )
        return TemplateResult("PASS", "version=1", [oid])


class FakeFamily(Family):
    name = "fake"

    def __init__(self, *, fail_prepare: bool = False) -> None:
        self.fail_prepare = fail_prepare
        self.templates = {
            t.template_id: _GenericTemplate(t.template_id, t.test_id, t.expected)
            for t in registry.load_catalog().templates
        }

    def prepare(self, ctx: Any) -> None:
        if self.fail_prepare:
            raise EnvironmentFailure("renode binary not found")

    def tool_versions(self) -> dict[str, str]:
        return {"renode": "1.16.1", "arm-none-eabi-gcc": "14.2.rel1"}

    def source_pins(self) -> dict[str, str]:
        return {"wolfboot": "4c79eee999b7083743811f37928322fe78b9fdb1"}


def runner_lines(request_json: dict[str, Any], *, fail_prepare: bool = False) -> list[str]:
    lines: list[str] = []
    execute(FakeFamily(fail_prepare=fail_prepare), request_json, lines.append)
    return lines


class FakeRunner:
    """httpx transport emulating ``POST /execute`` of a runner container.

    behaviour: ok | fail | invalid_json | traversal | unplanned | wrong_run | connect_error |
    midstream_error | timeout | no_done
    """

    def __init__(self, behaviour: str = "ok") -> None:
        self.behaviour = behaviour
        self.calls: list[dict[str, Any]] = []
        self.gate: threading.Event | None = None
        self.entered = threading.Event()
        self._lock = threading.Lock()

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/execute"
        body = json.loads(request.content)
        with self._lock:
            self.calls.append(body)
        self.entered.set()
        if self.gate is not None:
            assert self.gate.wait(20), "test gate never opened"
        b = self.behaviour
        if b == "connect_error":
            raise httpx.ConnectError("connection refused", request=request)
        if b == "timeout":
            raise httpx.ReadTimeout("read timed out", request=request)
        lines = runner_lines(body, fail_prepare=(b == "fail"))
        if b == "corrupt_file":
            victim = next(Path(body["artifact_dir"]).rglob("*.uart.log"))
            victim.write_text("rewritten after the runner hashed it\n", encoding="utf-8")
        if b == "invalid_json":
            lines.insert(3, "this is not json\n")
        elif b == "traversal":
            evil = {
                "seq": 10_000,
                "ts": "2026-10-17T00:00:00Z",
                "run_id": body["run_id"],
                "type": "artifact",
                "artifact_id": "ART-evil",
                "name": "passwd",
                "path": "../../../etc/passwd",
                "sha256": "0" * 64,
                "size_bytes": 1,
                "kind": "other",
            }
            lines = _renumber([*lines[:3], json.dumps(evil) + "\n", *lines[3:]])
        elif b == "unplanned":
            extra = {
                "seq": 0,
                "ts": "2026-10-17T00:00:00Z",
                "run_id": body["run_id"],
                "type": "test_result",
                "test_id": "O05",
                "template_id": "wolfboot.not_in_plan",
                "outcome": "PASS",
                "expected": "x",
                "observed": "y",
                "duration_ms": 1,
                "observation_ids": [],
            }
            lines = _renumber([*lines[:3], json.dumps(extra) + "\n", *lines[3:]])
        elif b == "wrong_run":
            first = json.loads(lines[1])
            first["run_id"] = "RP-someone-else"
            lines[1] = json.dumps(first) + "\n"
        elif b == "no_done":
            lines = lines[:-1]
        elif b == "midstream_error":
            head = lines[:5]

            def broken() -> Iterator[bytes]:
                for line in head:
                    yield line.encode()
                raise httpx.ReadError("connection reset by peer")

            return httpx.Response(
                200, headers={"content-type": "application/x-ndjson"}, content=broken()
            )
        return httpx.Response(
            200,
            headers={"content-type": "application/x-ndjson"},
            content="".join(lines).encode(),
        )


def _renumber(lines: list[str]) -> list[str]:
    out = []
    for i, line in enumerate(lines):
        event = json.loads(line)
        event["seq"] = i
        out.append(json.dumps(event) + "\n")
    return out


class FakeAdapter:
    """Projects nothing live: returns the WP0 baseline document under a constant id, so the
    verdict/canonical hash of every fake run is identical (lets tests prove AI cannot move it)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        assessment = copy.deepcopy(build_wp0_baseline_assessment())
        assessment["assessment_id"] = "FAKE-LIVE-ASSESSMENT"
        return assessment


def _trace(
    sink: Callable[[AITraceView], None],
    run_id: str | None,
    module: str,
    status: AIStatus = AIStatus.OK,
) -> str:
    trace_id = f"TR-{module}-{time.monotonic_ns()}"
    sink(
        AITraceView(
            trace_id=trace_id,
            run_id=run_id,
            module=module,  # type: ignore[arg-type]
            provider="fake-amd",
            model="fake-model",
            endpoint_host="amd.invalid",
            hardware_label="AMD Instinct MI300X (fake)",
            request_id=None,
            prompt_template=f"{module}@1",
            started_at="2026-10-17T00:00:00.000Z",
            latency_ms=120 if module == "planner" else 300,
            prompt_tokens=100,
            completion_tokens=20,
            status=status,
        )
    )
    return trace_id


class FakeAI:
    def __init__(self, trace_sink: Callable[[AITraceView], None]) -> None:
        self.sink = trace_sink
        self.calls: list[str] = []
        self.contexts: list[dict[str, Any]] = []

    def plan_tests(self, *, run_id, profile, change, templates):
        self.calls.append("plan_tests")
        tid = _trace(self.sink, run_id, "planner")
        optional = change.optional_templates[:1]
        selected = [
            PlannedTemplate(template_id=t, priority=1, rationale="observe PQC-only policy")
            for t in optional
        ]
        selected.append(
            PlannedTemplate(
                template_id="wolfboot.flash_everything", priority=2, rationale="injected"
            )
        )
        selected.append(
            PlannedTemplate(template_id=change.required_templates[-1], priority=3, rationale="key")
        )
        return AIPlanView(
            status=AIStatus.OK,
            trace_ids=[tid],
            proposal=TestPlanProposal(selected=selected, summary="fake plan"),
        )

    def explain(self, *, run_id, profile, change, plan_id, assessment, result, test_results):
        self.calls.append("explain")
        tid = _trace(self.sink, run_id, "explainer")
        return AIReportView(status=AIStatus.OK, trace_ids=[tid])

    def alternatives(self, *, run_id, profile, change, plan_id, assessment, result):
        self.calls.append("alternatives")
        tid = _trace(self.sink, run_id, "alternatives")
        alt = change.alternatives[0]
        return AIAlternativesView(
            status=AIStatus.OK,
            trace_ids=[tid],
            alternatives=AlternativesProposal(
                proposals=[
                    ChangeProposal(
                        plan_id=alt.plan_id,
                        title=alt.title,
                        rationale="fake",
                        addresses=["REQ-BOOT-S0S1"],
                    )
                ]
            ),
        )

    def assistant_stream(self, *, run_id, context, messages):
        self.calls.append("assistant")
        self.contexts.append(context)
        _trace(self.sink, run_id, "assistant")
        verdict = (context.get("result") or {}).get("migration_verdict")
        yield "The migration verdict is "
        yield f"{verdict} "
        yield "[cites EV-E01-BOOT]"

    def provider_info(self) -> dict[str, Any]:
        return {
            "provider": "fake-amd",
            "hardware_label": "AMD Instinct MI300X (fake)",
            "models": {"planner": "fake-model"},
        }


class BrokenAI(FakeAI):
    """Constructed fine, every call fails (endpoint down)."""

    def plan_tests(self, **kwargs):
        raise ConnectionError("AMD endpoint unreachable")

    def explain(self, **kwargs):
        raise ConnectionError("AMD endpoint unreachable")

    def alternatives(self, **kwargs):
        raise ConnectionError("AMD endpoint unreachable")

    def assistant_stream(self, **kwargs):
        raise ConnectionError("AMD endpoint unreachable")


def unavailable_ai_factory(_sink: Any) -> Any:
    raise RuntimeError("AMD_LLM_BASE_URL not configured")


class Harness:
    def __init__(
        self, tmp_path: Path, *, behaviour: str = "ok", ai: str = "ok", expose: bool = True
    ) -> None:
        self.runner = FakeRunner(behaviour)
        self.adapter = FakeAdapter()
        self.ai_instances: list[FakeAI] = []
        self.settings = Settings(
            env="test",
            data_dir=tmp_path / "data",
            runner_data_dir=(tmp_path / "data").as_posix(),
            expose_experimental=expose,
            runner_urls={
                "wolfboot": "http://runner-wolfboot:8080",
                "mcuboot": "http://runner-mcuboot:8080",
            },
            cors_origins=("http://localhost:3000",),
            sse_heartbeat_seconds=0.2,
        )

        def ai_factory(sink: Any) -> Any:
            if ai == "unavailable":
                return unavailable_ai_factory(sink)
            instance = (BrokenAI if ai == "broken" else FakeAI)(sink)
            self.ai_instances.append(instance)
            return instance

        self.deps = Deps(
            adapter_factory=lambda name: self.adapter,
            evidence_indexer=None,
            ai_factory=ai_factory,
            runner_transport=self.runner.transport(),
        )

    @property
    def ai(self) -> FakeAI:
        return self.ai_instances[0]

    def orchestrator(self) -> Orchestrator:
        store = Store(self.settings.db_path)
        orch = Orchestrator(store=store, settings=self.settings, deps=self.deps)
        orch.start()
        return orch


def wait_until(predicate: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met in time")
