"""Run state machine, FIFO queue per runner family, ingestion of runner events, evaluation.

Stages (user order): PREPARING → AI_PLAN → DISCOVERY → BUILD_SIGN → EMULATION_TESTS →
EVALUATION → NEXT_STEPS. Invariants:

* A run whose runner failed (done FAILED, transport error, timeout, invalid event) is FAILED and is
  never evaluated: no assessment, no verdict, no fallback to recorded data.
* The verdict only comes from ``core.assurance.service.evaluate``; AI output never changes it and
  AI failures never fail a run (stage INCONCLUSIVE, ``AI_UNAVAILABLE``).
* Re-evaluations are new runs; the parent run is only read.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from releaseproof.contracts.api import (
    AIAlternativesView,
    AIPlanView,
    AIReportView,
    AIStatus,
    AITraceView,
    AssistantMessage,
    EvidenceView,
    FailureView,
    RunCreate,
    RunMode,
    RunStatus,
    RunView,
    StageView,
    TestResultView,
    VerdictView,
)
from releaseproof.contracts.profile import (
    AlternativePlan,
    ChangeScenario,
    Profile,
    ProfileStatus,
    TestTemplate,
)
from releaseproof.contracts.runner import (
    ArtifactEvent,
    DoneEvent,
    ErrorEvent,
    FailureClass,
    LogEvent,
    Observation,
    ObservationEvent,
    PlannedTest,
    RunnerEvent,
    RunnerRequest,
    Stage,
    StageEvent,
    StageStatus,
    TestResultEvent,
)
from releaseproof.contracts.services import AdapterError
from releaseproof.core.assurance.service import evaluate
from releaseproof.core.canonical.service import compute_canonical_hash
from releaseproof.core.dossier.service import render_dossier_markdown
from releaseproof.core.planner.service import build_gap_plan
from releaseproof.orchestrator import evaluation as ev
from releaseproof.orchestrator.bus import EventBus
from releaseproof.orchestrator.deps import Deps
from releaseproof.orchestrator.plan import blocked_templates, merge_plan
from releaseproof.orchestrator.runner_client import InvalidRunnerEvent, RunnerClient, RunnerFailure
from releaseproof.orchestrator.settings import Settings
from releaseproof.profiles import registry
from releaseproof.store.db import EventRow, Store, StoreError

log = logging.getLogger(__name__)

STAGE_ORDER: tuple[Stage, ...] = (
    Stage.PREPARING,
    Stage.AI_PLAN,
    Stage.DISCOVERY,
    Stage.BUILD_SIGN,
    Stage.EMULATION_TESTS,
    Stage.EVALUATION,
    Stage.NEXT_STEPS,
)
RUNNER_STAGES = (Stage.DISCOVERY, Stage.BUILD_SIGN, Stage.EMULATION_TESTS)
TERMINAL_RUN = {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
TERMINAL_STAGE = {
    StageStatus.SUCCEEDED,
    StageStatus.FAILED,
    StageStatus.INCONCLUSIVE,
    StageStatus.SKIPPED,
}
MANIFEST_ARTIFACT_ID = "MANIFEST"
AI_UNAVAILABLE = AIStatus.AI_UNAVAILABLE.value


# ---------------------------------------------------------------------------- errors


class OrchestratorError(Exception):
    status_code = 400

    def __init__(self, detail: Any) -> None:
        super().__init__(str(detail))
        self.detail = detail


class NotFound(OrchestratorError):
    status_code = 404


class Conflict(OrchestratorError):
    status_code = 409


class Unprocessable(OrchestratorError):
    status_code = 422


class AIUnavailable(OrchestratorError):
    status_code = 503


# ---------------------------------------------------------------------------- helpers


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def new_run_id() -> str:
    return f"RP-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@lru_cache(maxsize=1)
def catalog_templates() -> dict[str, TestTemplate]:
    return {t.template_id: t for t in registry.load_catalog().templates}


def find_change(profile: Profile, change_id: str) -> ChangeScenario | None:
    return next((c for c in profile.changes if c.change_id == change_id), None)


def find_alternative(change: ChangeScenario, plan_id: str) -> AlternativePlan | None:
    return next((a for a in change.alternatives if a.plan_id == plan_id), None)


def external_validation_detail(alt: AlternativePlan) -> dict[str, Any]:
    return {
        "error": "REQUIRES_EXTERNAL_VALIDATION",
        "plan_id": alt.plan_id,
        "title": alt.title,
        "explanation": (
            f"{alt.description.strip()} This alternative cannot be proven from the evidence "
            "ReleaseProof can produce for this configuration, so it is not executed or "
            "evaluated automatically; it requires external validation."
        ),
    }


class _FamilySlot:
    """One concurrent run per runner family, strict FIFO."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._queue: deque[str] = deque()
        self._busy: str | None = None

    def enqueue(self, run_id: str) -> None:
        with self._cond:
            self._queue.append(run_id)

    def acquire(self, run_id: str, stop: threading.Event) -> bool:
        with self._cond:
            while True:
                if stop.is_set():
                    if run_id in self._queue:
                        self._queue.remove(run_id)
                    self._cond.notify_all()
                    return False
                if self._busy is None and self._queue and self._queue[0] == run_id:
                    break
                self._cond.wait(timeout=0.5)
            self._queue.popleft()
            self._busy = run_id
            return True

    def release(self, run_id: str) -> bool:
        with self._cond:
            if self._busy != run_id:
                return False
            self._busy = None
            self._cond.notify_all()
            return True

    def discard(self, run_id: str) -> None:
        """Drop ``run_id`` from the slot whatever its state (used on unexpected exits)."""
        with self._cond:
            if run_id in self._queue:
                self._queue.remove(run_id)
            if self._busy == run_id:
                self._busy = None
            self._cond.notify_all()

    def position(self, run_id: str) -> int | None:
        with self._cond:
            try:
                return list(self._queue).index(run_id) + 1
            except ValueError:
                return None

    def queued(self) -> list[str]:
        with self._cond:
            return list(self._queue)

    def wake(self) -> None:
        with self._cond:
            self._cond.notify_all()


@dataclass
class _RunCtx:
    run_id: str
    mode: RunMode
    profile: Profile
    change: ChangeScenario
    plan_id: str
    parent_run_id: str | None
    evidence_run_id: str
    created_at: str
    include_all_optional: bool
    stages: dict[Stage, dict[str, Any]]
    planned: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    assessment: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


# ---------------------------------------------------------------------------- orchestrator


class Orchestrator:
    def __init__(
        self,
        *,
        store: Store,
        settings: Settings,
        deps: Deps | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.deps = deps or Deps()
        self.deps.check_environment(settings.env)
        self.bus = bus or EventBus()
        self._slots: dict[str, _FamilySlot] = {}
        self._slots_lock = threading.Lock()
        self._done: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._submission_lock = threading.Lock()
        self._stop = threading.Event()

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        self.settings.runs_dir.mkdir(parents=True, exist_ok=True)
        self.recover()

    def shutdown(self, timeout: float | None = None) -> None:
        """Stop submissions/queued runs and drain active workers before returning.

        Active runner/AI calls finish normally so their final events reach the store. By default
        the drain waits for every worker; a caller-supplied timeout is one total budget, not a
        budget per thread. If it expires, raise rather than imply the store is safe to close.
        The caller must keep the store open and may retry shutdown after the workers finish.
        """
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        with self._submission_lock:
            self._stop.set()
            threads = list(self._threads.values())
        with self._slots_lock:
            slots = list(self._slots.values())
        for slot in slots:
            slot.wake()
        for thread in threads:
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            thread.join(timeout=remaining)
        active = [thread.name for thread in threads if thread.is_alive()]
        if active:
            raise TimeoutError(
                f"orchestrator shutdown incomplete; keep the store open: {', '.join(active)}"
            )

    def recover(self) -> list[str]:
        """Runs left QUEUED/RUNNING by a previous process cannot be resumed: fail them."""
        failed = []
        for row in self.store.list_runs(statuses=[RunStatus.RUNNING, RunStatus.QUEUED]):
            stages = row["stages"] or []
            for st in stages:
                if st["status"] == StageStatus.RUNNING:
                    st.update(status=StageStatus.FAILED, message="interrupted by restart")
                elif st["status"] == StageStatus.QUEUED:
                    st.update(status=StageStatus.SKIPPED, message="not executed: run interrupted")
            self.store.update_run(
                row["run_id"],
                status=RunStatus.FAILED.value,
                finished_at=utc_now(),
                stages=stages,
                verdict=None,
                failure={
                    "failure_class": FailureClass.INTERNAL.value,
                    "message": "interrupted by restart",
                },
            )
            self._emit_run(row["run_id"])
            failed.append(row["run_id"])
        return failed

    def _slot(self, family: str) -> _FamilySlot:
        with self._slots_lock:
            return self._slots.setdefault(family, _FamilySlot())

    def wait(self, run_id: str, timeout: float = 30.0) -> RunView:
        event = self._done.get(run_id)
        if event is not None and not event.wait(timeout):
            raise TimeoutError(f"run {run_id} did not finish within {timeout}s")
        return self.run_view(run_id)

    # ------------------------------------------------------------------ events

    def _emit(self, run_id: str, type_: str, data: dict[str, Any]) -> EventRow:
        return self.store.append_event(
            run_id, type_, data, created_at=utc_now(), on_commit=self.bus.publish
        )

    def _emit_run(self, run_id: str) -> None:
        self._emit(run_id, "run", self.run_view(run_id).model_dump(mode="json"))

    def _publish_queue(self, family: str) -> None:
        for run_id in self._slot(family).queued():
            self._emit_run(run_id)

    def trace_sink(self, trace: AITraceView | dict[str, Any]) -> None:
        """Receives every AI call trace from the AI gateway. Never raises."""
        try:
            view = trace if isinstance(trace, AITraceView) else AITraceView.model_validate(trace)
            data = view.model_dump(mode="json")
            self.store.add_ai_trace(data)
            if view.run_id and self.store.get_run(view.run_id) is not None:
                self._emit(
                    view.run_id, "ai", {"kind": "trace", "module": view.module, "trace": data}
                )
        except Exception:  # noqa: BLE001
            log.exception("failed to record AI trace")

    # ------------------------------------------------------------------ resolution

    def resolve(self, configuration_id: str, change_id: str) -> tuple[Profile, ChangeScenario]:
        try:
            profile = registry.get_profile(configuration_id)
        except registry.RegistryError as exc:
            raise Unprocessable(f"unknown configuration {configuration_id!r}") from exc
        change = find_change(profile, change_id)
        if change is None:
            raise Unprocessable(f"unknown change {change_id!r} for {configuration_id}")
        return profile, change

    def is_selectable(self, profile: Profile) -> bool:
        if profile.status == ProfileStatus.SUPPORTED:
            return True
        return profile.status == ProfileStatus.EXPERIMENTAL and self.settings.expose_experimental

    # ------------------------------------------------------------------ submission

    def create_run(
        self, body: RunCreate, idempotency_key: str | None = None
    ) -> tuple[RunView, bool]:
        key = self._idempotency_key(idempotency_key, body.idempotency_key)
        profile, change = self.resolve(body.configuration_id, body.change_id)
        if not self.is_selectable(profile):
            raise Unprocessable(
                f"configuration {profile.id} is {profile.status.value}; not selectable"
            )
        plan_id = body.plan_id or change.default_plan_id
        include_all_optional = False
        if plan_id != change.default_plan_id:
            alt = find_alternative(change, plan_id)
            if alt is None:
                raise Unprocessable(f"unknown plan {plan_id!r} for change {change.change_id}")
            if alt.status == "REQUIRES_EXTERNAL_VALIDATION":
                raise Unprocessable(external_validation_detail(alt))
            include_all_optional = alt.requires_rerun_tests
        request_hash = _request_hash(
            {"kind": "create", "cfg": profile.id, "change": change.change_id, "plan": plan_id}
        )
        return self._insert_and_start(
            mode=RunMode.LIVE,
            profile=profile,
            change=change,
            plan_id=plan_id,
            parent=None,
            include_all_optional=include_all_optional,
            key=key,
            request_hash=request_hash,
        )

    def evaluate_alternative(
        self, parent_run_id: str, plan_id: str, idempotency_key: str | None = None
    ) -> tuple[RunView, bool]:
        key = self._idempotency_key(idempotency_key, None)
        parent = self.store.get_run(parent_run_id)
        if parent is None:
            raise NotFound(f"unknown run {parent_run_id}")
        if parent["status"] != RunStatus.SUCCEEDED or self.store.get_result(parent_run_id) is None:
            raise Conflict(f"run {parent_run_id} has no evaluated result to branch from")
        profile, change = self.resolve(parent["configuration_id"], parent["change_id"])
        alt = find_alternative(change, plan_id)
        if alt is None:
            raise NotFound(f"plan {plan_id!r} is not an alternative of change {change.change_id}")
        if alt.status == "REQUIRES_EXTERNAL_VALIDATION":
            raise Unprocessable(external_validation_detail(alt))
        request_hash = _request_hash(
            {"kind": "alternative", "parent": parent_run_id, "plan": plan_id}
        )
        return self._insert_and_start(
            mode=RunMode.LIVE if alt.requires_rerun_tests else RunMode.REEVALUATION,
            profile=profile,
            change=change,
            plan_id=plan_id,
            parent=parent,
            include_all_optional=alt.requires_rerun_tests,
            key=key,
            request_hash=request_hash,
        )

    @staticmethod
    def _idempotency_key(header: str | None, body: str | None) -> str | None:
        header = (header or "").strip() or None
        body = (body or "").strip() or None
        if header and body and header != body:
            raise Unprocessable("Idempotency-Key header and body idempotency_key differ")
        key = header or body
        if key is not None and len(key) > 80:
            raise Unprocessable("idempotency key longer than 80 characters")
        return key

    def _insert_and_start(
        self,
        *,
        mode: RunMode,
        profile: Profile,
        change: ChangeScenario,
        plan_id: str,
        parent: dict[str, Any] | None,
        include_all_optional: bool,
        key: str | None,
        request_hash: str,
    ) -> tuple[RunView, bool]:
        now = utc_now()
        run_id = new_run_id()
        if mode == RunMode.REEVALUATION:
            assert parent is not None
            evidence_run_id = parent["evidence_run_id"] or parent["run_id"]
        else:
            evidence_run_id = run_id
        row = {
            "run_id": run_id,
            "mode": mode.value,
            "status": RunStatus.QUEUED.value,
            "configuration_id": profile.id,
            "configuration_version": profile.version,
            "change_id": change.change_id,
            "plan_id": plan_id,
            "parent_run_id": parent["run_id"] if parent else None,
            "evidence_run_id": evidence_run_id,
            "runner_family": profile.bootloader.family if mode == RunMode.LIVE else None,
            "created_at": now,
            "stages": [
                StageView(stage=s, status=StageStatus.QUEUED).model_dump(mode="json")
                for s in STAGE_ORDER
            ],
            "plan": [],
            "source_pins": {},
            "tool_versions": {},
            "extra": {"include_all_optional": include_all_optional, "idempotency_key": key},
        }
        # Keep database insertion, FIFO enqueue and worker registration in the same order,
        # even when concurrent API requests submit runs for the same runner family.
        with self._submission_lock:
            if self._stop.is_set():
                raise Conflict("orchestrator shutting down")
            try:
                existing_id, created = self.store.insert_run_with_key(
                    row, key=key, request_hash=request_hash, created_at=now
                )
            except StoreError as exc:
                raise Conflict(str(exc)) from exc
            if not created:
                return self.run_view(existing_id), False
            if mode == RunMode.LIVE:
                self._slot(profile.bootloader.family).enqueue(run_id)
            self._done[run_id] = threading.Event()
            self._emit_run(run_id)
            thread = threading.Thread(
                target=self._execute, args=(run_id,), name=f"run-{run_id}", daemon=True
            )
            self._threads[run_id] = thread
            thread.start()
        return self.run_view(run_id), True

    # ------------------------------------------------------------------ worker

    def _load_ctx(self, run_id: str) -> _RunCtx:
        row = self.store.get_run(run_id)
        assert row is not None
        profile = registry.get_profile(row["configuration_id"])
        change = find_change(profile, row["change_id"])
        assert change is not None
        return _RunCtx(
            run_id=run_id,
            mode=RunMode(row["mode"]),
            profile=profile,
            change=change,
            plan_id=row["plan_id"],
            parent_run_id=row["parent_run_id"],
            evidence_run_id=row["evidence_run_id"] or run_id,
            created_at=row["created_at"],
            include_all_optional=bool((row["extra"] or {}).get("include_all_optional")),
            stages={Stage(s["stage"]): s for s in row["stages"]},
            planned=list(row["plan"] or []),
            extra=dict(row["extra"] or {}),
        )

    def _execute(self, run_id: str) -> None:
        ctx: _RunCtx | None = None
        row = self.store.get_run(run_id) or {}
        family: str | None = row.get("runner_family")
        try:
            ctx = self._load_ctx(run_id)
            if ctx.mode == RunMode.LIVE:
                assert family is not None
                slot = self._slot(family)
                if not slot.acquire(run_id, self._stop):
                    raise RunnerFailure(FailureClass.INTERNAL, "orchestrator shutting down")
                try:
                    self._mark_running(ctx)
                    self._publish_queue(family)
                    self._prepare(ctx)
                    self._ai_plan(ctx)
                    self._run_runner(ctx)
                finally:
                    if slot.release(run_id):
                        self._publish_queue(family)
            else:
                self._mark_running(ctx)
                self._prepare_reevaluation(ctx)
            self._evaluate(ctx)
            self._next_steps(ctx)
            self._finish(ctx)
        except (RunnerFailure, ev.EvaluationFailure) as exc:
            self._fail(run_id, ctx, str(exc.failure_class), exc.message)
        except Exception as exc:  # noqa: BLE001 - every unexpected error fails the run, visibly
            log.exception("run %s crashed", run_id)
            self._fail(run_id, ctx, FailureClass.INTERNAL.value, f"{type(exc).__name__}: {exc}")
        finally:
            if family is not None:
                self._slot(family).discard(run_id)
            done = self._done.get(run_id)
            if done is not None:
                done.set()
            with self._submission_lock:
                self._threads.pop(run_id, None)

    def _mark_running(self, ctx: _RunCtx) -> None:
        self.store.update_run(ctx.run_id, status=RunStatus.RUNNING.value, started_at=utc_now())
        self._emit_run(ctx.run_id)

    def _set_stage(
        self,
        ctx: _RunCtx,
        stage: Stage,
        status: StageStatus,
        message: str | None = None,
        *,
        source: str = "orchestrator",
        runner_seq: int | None = None,
    ) -> None:
        st = ctx.stages[stage]
        now = utc_now()
        unchanged = st["status"] == status.value
        if status == StageStatus.RUNNING and not st.get("started_at"):
            st["started_at"] = now
        if status in TERMINAL_STAGE and status != StageStatus.SKIPPED and not unchanged:
            st["started_at"] = st.get("started_at") or now
            st["finished_at"] = now
            st["duration_ms"] = max(
                0, int((_parse_ts(now) - _parse_ts(st["started_at"])).total_seconds() * 1000)
            )
        st["status"] = status.value
        if message is not None:
            st["message"] = message[:2000]
        self.store.update_run(ctx.run_id, stages=[ctx.stages[s] for s in STAGE_ORDER])
        data = {**st, "source": source}
        if runner_seq is not None:
            data["runner_seq"] = runner_seq
        self._emit(ctx.run_id, "stage", data)

    # ------------------------------------------------------------------ PREPARING

    def _prepare(self, ctx: _RunCtx) -> None:
        self._set_stage(ctx, Stage.PREPARING, StageStatus.RUNNING, "resolving configuration")
        file_name, file_sha = ev.profile_source(ctx.profile.id)
        ctx.extra.update(
            profile_file=file_name,
            profile_sha256=file_sha,
            runner_service=ctx.profile.runner.service,
            runner_image=ctx.profile.runner.image,
        )
        self.store.update_run(ctx.run_id, extra=ctx.extra)
        (self.settings.run_dir(ctx.run_id) / "artifacts").mkdir(parents=True, exist_ok=True)
        self._set_stage(
            ctx,
            Stage.PREPARING,
            StageStatus.SUCCEEDED,
            f"{ctx.profile.title} v{ctx.profile.version}; plan {ctx.plan_id}; "
            f"runner {ctx.profile.runner.image}",
        )

    def _prepare_reevaluation(self, ctx: _RunCtx) -> None:
        self._set_stage(ctx, Stage.PREPARING, StageStatus.RUNNING, "loading parent evidence")
        source = self.store.get_run(ctx.evidence_run_id)
        if (
            source is None
            or source["status"] != RunStatus.SUCCEEDED
            or source["mode"] != RunMode.LIVE
        ):
            raise ev.EvaluationFailure(
                FailureClass.INTERNAL.value,
                f"evidence run {ctx.evidence_run_id} is not a succeeded LIVE run",
            )
        file_name, file_sha = ev.profile_source(ctx.profile.id)
        for obs in self.store.list_observations(ctx.evidence_run_id):
            self.store.add_observation(ctx.run_id, obs, source_run_id=ctx.evidence_run_id)
        for art in self.store.list_artifacts(ctx.evidence_run_id):
            if art["artifact_id"] == MANIFEST_ARTIFACT_ID:
                continue
            self.store.add_artifact(ctx.run_id, {**art, "owner_run_id": art["owner_run_id"]})
        for result in self.store.list_test_results(ctx.evidence_run_id):
            self.store.add_test_result(ctx.run_id, result)
        ctx.planned = list(source["plan"] or [])
        ctx.extra.update(
            profile_file=file_name,
            profile_sha256=file_sha,
            evidence_source=ctx.evidence_run_id,
            runner_service=(source["extra"] or {}).get("runner_service"),
            runner_image=(source["extra"] or {}).get("runner_image"),
        )
        self.store.update_run(
            ctx.run_id,
            plan=ctx.planned,
            extra=ctx.extra,
            source_pins=source["source_pins"] or {},
            tool_versions=source["tool_versions"] or {},
        )
        reused = f"evidence reused from LIVE run {ctx.evidence_run_id}"
        self._set_stage(
            ctx, Stage.PREPARING, StageStatus.SUCCEEDED, f"alternative plan {ctx.plan_id}; {reused}"
        )
        self._set_stage(ctx, Stage.AI_PLAN, StageStatus.SKIPPED, f"no new tests: {reused}")
        for stage in RUNNER_STAGES:
            self._set_stage(ctx, stage, StageStatus.SKIPPED, reused)

    # ------------------------------------------------------------------ AI_PLAN

    def _ai_plan(self, ctx: _RunCtx) -> None:
        self._set_stage(ctx, Stage.AI_PLAN, StageStatus.RUNNING, "AI test planner")
        catalog = catalog_templates()
        allowed_ids = list(
            dict.fromkeys([*ctx.change.required_templates, *ctx.change.optional_templates])
        )
        templates = [catalog[t] for t in allowed_ids]
        ai = self.deps.ai(self.trace_sink)
        if ai is None:
            view = AIPlanView(
                status=AIStatus.AI_UNAVAILABLE,
                message=self.deps.ai_error or "AI service unavailable",
            )
        else:
            view = self._safe_ai(
                AIPlanView,
                lambda: ai.plan_tests(
                    run_id=ctx.run_id, profile=ctx.profile, change=ctx.change, templates=templates
                ),
            )
        view = view.model_copy(update={"blocked_templates": blocked_templates(ctx.change, view)})
        merged = merge_plan(ctx.change, view, include_all_optional=ctx.include_all_optional)
        ctx.planned = [
            {
                "template_id": tid,
                "test_id": catalog[tid].test_id,
                "planned_by": by,
                "title": catalog[tid].title,
                "negative": catalog[tid].negative,
                "est_seconds": catalog[tid].est_seconds,
                "params": {},
            }
            for tid, by in merged
        ]
        self.store.update_run(ctx.run_id, ai_plan=view.model_dump(mode="json"), plan=ctx.planned)
        self._emit(
            ctx.run_id,
            "ai",
            {
                "kind": "result",
                "module": "planner",
                "status": view.status.value,
                "view": view.model_dump(mode="json"),
            },
        )
        if view.status == AIStatus.OK:
            by_ai = sum(1 for p in ctx.planned if p["planned_by"] == "AI_PLANNER")
            message = f"{len(ctx.planned)} tests planned ({by_ai} optional selected by AI)"
            if view.blocked_templates:
                message += f"; blocked unregistered: {', '.join(view.blocked_templates)}"
            self._set_stage(ctx, Stage.AI_PLAN, StageStatus.SUCCEEDED, message)
        else:
            self._set_stage(ctx, Stage.AI_PLAN, StageStatus.INCONCLUSIVE, view.status.value)

    @staticmethod
    def _safe_ai(view_cls: type, call: Callable[[], Any]) -> Any:
        try:
            out = call()
        except Exception as exc:  # noqa: BLE001 - AI failure is reported, never raised
            return view_cls(
                status=AIStatus.AI_UNAVAILABLE, message=f"{type(exc).__name__}: {exc}"[:500]
            )
        if isinstance(out, view_cls):
            return out
        try:
            payload = out if isinstance(out, dict) else out.model_dump(mode="json")
            return view_cls.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            return view_cls(status=AIStatus.SCHEMA_INVALID, message=f"invalid AI view: {exc}"[:500])

    # ------------------------------------------------------------------ runner stages

    def _run_runner(self, ctx: _RunCtx) -> None:
        family = ctx.profile.bootloader.family
        request = RunnerRequest(
            run_id=ctx.run_id,
            profile_id=ctx.profile.id,
            change_id=ctx.change.change_id,
            tests=[
                PlannedTest(template_id=p["template_id"], params=p.get("params") or {})
                for p in ctx.planned
            ],
            artifact_dir=self.settings.runner_artifact_dir(ctx.run_id),
            timeout_seconds=ctx.profile.runner.timeout_seconds,
        )
        client = RunnerClient(
            self.settings.runner_url(family, ctx.profile.runner.service),
            transport=self.deps.runner_transport,
            connect_timeout=self.settings.runner_connect_timeout,
            grace_seconds=self.settings.runner_grace_seconds,
        )
        state: dict[str, Any] = {"first_error": None, "done": None}
        events: Iterator[RunnerEvent] = client.execute(request)
        try:
            for event in events:
                self._ingest(ctx, event, state)
        finally:
            close = getattr(events, "close", None)
            if close is not None:
                close()
        done: DoneEvent = state["done"]
        if done.status == "FAILED":
            first: ErrorEvent | None = state["first_error"]
            failure = first.failure_class if first else FailureClass.TOOL_FAILURE
            message = first.message if first else (done.summary or "runner reported FAILED")
            raise RunnerFailure(failure, f"runner FAILED: {message}")
        for stage in RUNNER_STAGES:
            status = ctx.stages[stage]["status"]
            if status == StageStatus.QUEUED:
                self._set_stage(ctx, stage, StageStatus.SKIPPED, "no planned test in this stage")
            elif status == StageStatus.RUNNING:
                self._set_stage(
                    ctx, stage, StageStatus.INCONCLUSIVE, "runner did not close this stage"
                )

    def _ingest(self, ctx: _RunCtx, event: RunnerEvent, state: dict[str, Any]) -> None:
        data = event.model_dump(mode="json", exclude_none=True)
        run_id = ctx.run_id
        if isinstance(event, StageEvent):
            if event.stage not in (Stage.PREPARING, *RUNNER_STAGES):
                raise InvalidRunnerEvent(f"runner cannot drive stage {event.stage.value}")
            if event.stage == Stage.PREPARING and event.status != StageStatus.FAILED:
                message = f"runner: {event.message or event.status.value.lower()}"
                self._set_stage(
                    ctx,
                    Stage.PREPARING,
                    StageStatus(ctx.stages[Stage.PREPARING]["status"]),
                    message,
                    source="runner",
                    runner_seq=event.seq,
                )
            else:
                self._set_stage(
                    ctx,
                    event.stage,
                    event.status,
                    event.message or None,
                    source="runner",
                    runner_seq=event.seq,
                )
        elif isinstance(event, LogEvent):
            self._emit(run_id, "log", data)
        elif isinstance(event, ArtifactEvent):
            try:
                self.store.add_artifact(
                    run_id,
                    {
                        "artifact_id": event.artifact_id,
                        "owner_run_id": run_id,
                        "name": event.name,
                        "rel_path": f"artifacts/{event.path}",
                        "kind": event.kind,
                        "sha256": event.sha256,
                        "size_bytes": event.size_bytes,
                        "test_id": event.test_id,
                        "event": data,
                    },
                )
            except StoreError as exc:
                raise InvalidRunnerEvent(str(exc)) from exc
            self._emit(
                run_id,
                "artifact",
                {**data, "url": f"/api/assessments/{run_id}/artifacts/{event.artifact_id}"},
            )
        elif isinstance(event, ObservationEvent):
            try:
                self.store.add_observation(
                    run_id, event.observation.model_dump(mode="json"), source_run_id=run_id
                )
            except StoreError as exc:
                raise InvalidRunnerEvent(str(exc)) from exc
            self._emit(run_id, "observation", data)
        elif isinstance(event, TestResultEvent):
            planned = {p["template_id"]: p for p in ctx.planned}
            plan = planned.get(event.template_id)
            if plan is None:
                raise InvalidRunnerEvent(f"result for unplanned template {event.template_id}")
            if plan["test_id"] != event.test_id:
                raise InvalidRunnerEvent(
                    f"{event.template_id} reported test_id {event.test_id}, "
                    f"catalog says {plan['test_id']}"
                )
            try:
                self.store.add_test_result(run_id, event.model_dump(mode="json"))
            except StoreError as exc:
                raise InvalidRunnerEvent(str(exc)) from exc
            self._emit(
                run_id,
                "test_result",
                {
                    **data,
                    "title": plan["title"],
                    "negative": plan["negative"],
                    "planned_by": plan["planned_by"],
                },
            )
        elif isinstance(event, ErrorEvent):
            if state["first_error"] is None:
                state["first_error"] = event
            self._emit(run_id, "error", {**data, "source": "runner"})
        elif isinstance(event, DoneEvent):
            state["done"] = event
            self.store.update_run(
                run_id, tool_versions=event.tool_versions, source_pins=event.source_pins
            )
            self._emit(run_id, "done", data)

    # ------------------------------------------------------------------ EVALUATION

    def _evaluate(self, ctx: _RunCtx) -> None:
        self._set_stage(ctx, Stage.EVALUATION, StageStatus.RUNNING, "projecting evidence into V1.2")
        run_id = ctx.run_id
        observation_rows = self.store.list_observations(run_id)
        artifact_rows = [
            a for a in self.store.list_artifacts(run_id) if a["artifact_id"] != MANIFEST_ARTIFACT_ID
        ]
        result_rows = self.store.list_test_results(run_id)
        ev.verify_artifacts(self.settings.runs_dir, artifact_rows)
        observations = [Observation.model_validate(o) for o in observation_rows]
        artifacts = [ArtifactEvent.model_validate(a["event"]) for a in artifact_rows]
        test_results = [TestResultEvent.model_validate(t) for t in result_rows]

        try:
            adapter = self.deps.get_adapter(ctx.profile.assessment_adapter)
        except Exception as exc:  # noqa: BLE001
            raise ev.EvaluationFailure(
                FailureClass.INTERNAL.value,
                f"assessment adapter {ctx.profile.assessment_adapter} unavailable: {exc}",
            ) from exc
        try:
            assessment = adapter(
                profile=ctx.profile,
                change=ctx.change,
                plan_id=ctx.plan_id,
                run_id=run_id,
                evidence_run_id=ctx.evidence_run_id,
                created_at=ctx.created_at,
                observations=observations,
                artifacts=artifacts,
                test_results=test_results,
            )
        except AdapterError as exc:
            raise ev.EvaluationFailure(
                FailureClass.INTERNAL.value, f"adapter could not project facts: {exc}"
            ) from exc
        if not isinstance(assessment, dict):
            raise ev.EvaluationFailure(
                FailureClass.INTERNAL.value, "adapter did not return an assessment document"
            )

        result = evaluate(assessment).model_dump(mode="json")
        gap_plan = build_gap_plan(assessment, result)
        evidence = self._evidence_views(
            run_id, assessment, observations, artifacts, observation_rows, artifact_rows
        )
        run_row = self.store.get_run(run_id) or {}
        manifest = self._manifest(
            ctx, run_row, assessment, result, observation_rows, artifact_rows, result_rows
        )
        manifest_path = self.settings.run_dir(run_id) / "manifest.json"
        manifest_sha = ev.write_manifest(manifest_path, manifest)
        self.store.add_artifact(
            run_id,
            {
                "artifact_id": MANIFEST_ARTIFACT_ID,
                "owner_run_id": run_id,
                "name": "manifest.json",
                "rel_path": "manifest.json",
                "kind": "manifest",
                "sha256": manifest_sha,
                "size_bytes": manifest_path.stat().st_size,
                "test_id": None,
            },
        )
        dossier = self._dossier(ctx, run_row, assessment, result, gap_plan, manifest_sha)
        self.store.save_result(
            run_id,
            assessment=assessment,
            result=result,
            gap_plan=gap_plan,
            dossier_md=dossier,
            evidence=[e.model_dump(mode="json") for e in evidence],
            manifest_sha256=manifest_sha,
            canonical_hash=result.get("canonical_hash"),
            created_at=utc_now(),
        )
        verdict = VerdictView(
            lifecycle=str(result.get("lifecycle")),
            migration=result.get("migration_verdict"),
            candidate=result.get("candidate_verdict"),
            transition=result.get("transition_verdict"),
            canonical_hash=result.get("canonical_hash"),
        )
        self.store.update_run(run_id, verdict=verdict.model_dump(mode="json"))
        ctx.assessment, ctx.result = assessment, result
        message = f"lifecycle {verdict.lifecycle}; migration {verdict.migration or '—'}"
        status = (
            StageStatus.SUCCEEDED if verdict.lifecycle == "COMPLETED" else StageStatus.INCONCLUSIVE
        )
        self._set_stage(ctx, Stage.EVALUATION, status, message)

    def _evidence_views(
        self,
        run_id: str,
        assessment: dict[str, Any],
        observations: list[Observation],
        artifacts: list[ArtifactEvent],
        observation_rows: list[dict[str, Any]],
        artifact_rows: list[dict[str, Any]],
    ) -> list[EvidenceView]:
        """Adapter-provided evidence index (WS-E) when available, else a generic join.

        The index is presentation only: it never feeds evaluate()."""
        index: Any = None
        indexer = self.deps.evidence_indexer()
        if indexer is not None:
            try:
                index = indexer(
                    assessment=assessment, observations=observations, artifacts=artifacts
                )
                if isinstance(index, list):
                    return [EvidenceView.model_validate(row) for row in index]
            except Exception:  # noqa: BLE001
                log.warning("evidence_index failed for %s", run_id, exc_info=True)
                index = None
        return ev.build_evidence_views(
            run_id=run_id,
            assessment=assessment,
            observations=observation_rows,
            artifact_rows=artifact_rows,
            index=index if isinstance(index, dict) else None,
        )

    def _manifest(
        self,
        ctx: _RunCtx,
        run_row: dict[str, Any],
        assessment: dict[str, Any],
        result: dict[str, Any],
        observations: list[dict[str, Any]],
        artifacts: list[dict[str, Any]],
        test_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        catalog_file, catalog_sha = ev.catalog_source()
        alt = find_alternative(ctx.change, ctx.plan_id)
        ai_plan = run_row.get("ai_plan") or {}
        return {
            "manifest_version": "releaseproof.run-manifest/1",
            "run_id": ctx.run_id,
            "mode": ctx.mode.value,
            "parent_run_id": ctx.parent_run_id,
            "evidence_run_id": ctx.evidence_run_id,
            "created_at": ctx.created_at,
            "profile": {
                "id": ctx.profile.id,
                "version": ctx.profile.version,
                "status": ctx.profile.status.value,
                "file": ctx.extra.get("profile_file"),
                "sha256": ctx.extra.get("profile_sha256"),
                "assessment_adapter": ctx.profile.assessment_adapter,
                "ruleset_version": ctx.profile.ruleset_version,
            },
            "test_catalog": {
                "version": registry.load_catalog().version,
                "file": catalog_file,
                "sha256": catalog_sha,
            },
            "change": ctx.change.model_dump(mode="json"),
            "plan": {
                "plan_id": ctx.plan_id,
                "kind": "ALTERNATIVE" if alt else "DEFAULT",
                "title": alt.title if alt else ctx.change.default_plan_title,
                "alternative": alt.model_dump(mode="json") if alt else None,
            },
            "planned_tests": ctx.planned,
            "runner": {
                "family": ctx.profile.bootloader.family,
                "service": ctx.extra.get("runner_service"),
                "image": ctx.extra.get("runner_image"),
                "timeout_seconds": ctx.profile.runner.timeout_seconds,
                "executed_in_run": ctx.evidence_run_id,
            },
            "bootloader": ctx.profile.bootloader.model_dump(mode="json"),
            "tool_versions": run_row.get("tool_versions") or {},
            "source_pins": run_row.get("source_pins") or {},
            "artifacts": [
                {
                    "artifact_id": a["artifact_id"],
                    "name": a["name"],
                    "owner_run_id": a["owner_run_id"],
                    "path": a["rel_path"],
                    "kind": a["kind"],
                    "sha256": a["sha256"],
                    "size_bytes": a["size_bytes"],
                    "test_id": a["test_id"],
                }
                for a in artifacts
            ],
            "observations": {
                "count": len(observations),
                "canonical_hash": compute_canonical_hash({"observations": observations}),
            },
            "test_results": [
                {"template_id": t["template_id"], "test_id": t["test_id"], "outcome": t["outcome"]}
                for t in test_results
            ],
            "ai_plan": {
                "status": ai_plan.get("status", AIStatus.NOT_REQUESTED.value),
                "trace_ids": ai_plan.get("trace_ids", []),
            },
            "assessment": {
                "assessment_id": assessment.get("assessment_id"),
                "contract_version": assessment.get("contract_version"),
                "canonical_hash": compute_canonical_hash(assessment),
            },
            "result": {
                "lifecycle": result.get("lifecycle"),
                "migration_verdict": result.get("migration_verdict"),
                "candidate_verdict": result.get("candidate_verdict"),
                "transition_verdict": result.get("transition_verdict"),
                "canonical_hash": result.get("canonical_hash"),
                "official": False,
            },
        }

    def _dossier(
        self,
        ctx: _RunCtx,
        run_row: dict[str, Any],
        assessment: dict[str, Any],
        result: dict[str, Any],
        gap_plan: list[dict[str, Any]],
        manifest_sha: str,
    ) -> str:
        pins = run_row.get("source_pins") or {}
        bootloader = ctx.profile.bootloader
        family_pin = next(
            (v for k, v in pins.items() if bootloader.family in k.lower()), bootloader.commit
        )
        evidence_label = (
            f"live run {ctx.run_id} ({ctx.created_at})"
            if ctx.mode == RunMode.LIVE
            else f"re-evaluation of LIVE run {ctx.evidence_run_id}"
        )
        md = render_dossier_markdown(
            assessment,
            result,
            gap_plan=gap_plan,
            meta={
                "board": ctx.profile.board.name,
                "bootloader": f"{bootloader.name} {family_pin}",
                "evidence": evidence_label,
            },
        )
        lines = [
            "",
            "## 13. ReleaseProof run provenance",
            "",
            f"- **run_id**: `{ctx.run_id}` ({ctx.mode.value})",
            f"- **parent_run_id**: `{ctx.parent_run_id or '—'}`",
            f"- **evidence_run_id**: `{ctx.evidence_run_id}`",
            f"- **configuration**: `{ctx.profile.id}` v{ctx.profile.version} "
            f"(sha256 `{ctx.extra.get('profile_sha256')}`)",
            f"- **bootloader**: {bootloader.name} `{bootloader.commit}`",
            f"- **change / plan**: `{ctx.change.change_id}` / `{ctx.plan_id}`",
            f"- **planned tests**: {', '.join(p['template_id'] for p in ctx.planned) or '—'}",
            f"- **runner image**: `{ctx.extra.get('runner_image') or '—'}`",
            f"- **manifest.json sha256**: `{manifest_sha}`",
            "",
        ]
        for title, values in (
            ("Source pins", pins),
            ("Tool versions", run_row.get("tool_versions") or {}),
        ):
            lines.append(f"**{title}**")
            lines.append("")
            lines.extend(f"- `{k}`: `{v}`" for k, v in sorted(values.items()))
            if not values:
                lines.append("- —")
            lines.append("")
        return md + "\n".join(lines)

    # ------------------------------------------------------------------ NEXT_STEPS

    def _next_steps(self, ctx: _RunCtx) -> None:
        self._set_stage(
            ctx, Stage.NEXT_STEPS, StageStatus.RUNNING, "AI explanation and alternatives"
        )
        try:
            assert ctx.assessment is not None and ctx.result is not None
            tests = [t.model_dump(mode="json") for t in self.run_view(ctx.run_id).tests]
            ai = self.deps.ai(self.trace_sink)
            reason = self.deps.ai_error or "AI service unavailable"

            def _explain() -> AIReportView:
                if ai is None:
                    return AIReportView(status=AIStatus.AI_UNAVAILABLE, message=reason)
                return self._safe_ai(
                    AIReportView,
                    lambda: ai.explain(
                        run_id=ctx.run_id,
                        profile=ctx.profile,
                        change=ctx.change,
                        plan_id=ctx.plan_id,
                        assessment=ctx.assessment,
                        result=ctx.result,
                        test_results=tests,
                    ),
                )

            def _alternatives() -> AIAlternativesView:
                return self._alternatives_view(
                    ctx.run_id, ctx.profile, ctx.change, ctx.plan_id, ctx.assessment, ctx.result
                )

            # Both calls are independent: run them concurrently (each takes tens of seconds on
            # the hosted endpoint); results are persisted on this thread, in a fixed order.
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="rp-ai") as pool:
                report_future = pool.submit(_explain)
                alternatives_future = pool.submit(_alternatives)
                report = report_future.result()
                alternatives = alternatives_future.result()
            self.store.update_run(ctx.run_id, ai_report=report.model_dump(mode="json"))
            self._emit(
                ctx.run_id,
                "ai",
                {
                    "kind": "result",
                    "module": "explainer",
                    "status": report.status.value,
                    "view": report.model_dump(mode="json"),
                },
            )
            self.store.update_run(ctx.run_id, ai_alternatives=alternatives.model_dump(mode="json"))
            self._emit(
                ctx.run_id,
                "ai",
                {
                    "kind": "result",
                    "module": "alternatives",
                    "status": alternatives.status.value,
                    "view": alternatives.model_dump(mode="json"),
                },
            )
        except Exception as exc:  # noqa: BLE001 - AI never fails the run
            log.exception("NEXT_STEPS failed for %s", ctx.run_id)
            self._set_stage(
                ctx,
                Stage.NEXT_STEPS,
                StageStatus.INCONCLUSIVE,
                f"{AI_UNAVAILABLE}: {type(exc).__name__}",
            )
            return
        statuses = {report.status, alternatives.status}
        if statuses <= {AIStatus.OK, AIStatus.NOT_REQUESTED}:
            self._set_stage(
                ctx, Stage.NEXT_STEPS, StageStatus.SUCCEEDED, "explanation and alternatives drafted"
            )
        elif AIStatus.AI_UNAVAILABLE in statuses:
            self._set_stage(ctx, Stage.NEXT_STEPS, StageStatus.INCONCLUSIVE, AI_UNAVAILABLE)
        else:
            bad = sorted(
                s.value for s in statuses if s not in {AIStatus.OK, AIStatus.NOT_REQUESTED}
            )
            self._set_stage(ctx, Stage.NEXT_STEPS, StageStatus.INCONCLUSIVE, ", ".join(bad))

    def _alternatives_view(
        self,
        run_id: str,
        profile: Profile,
        change: ChangeScenario,
        plan_id: str,
        assessment: dict[str, Any],
        result: dict[str, Any],
    ) -> AIAlternativesView:
        if result.get("migration_verdict") == "COMPATIBLE":
            return AIAlternativesView(
                status=AIStatus.NOT_REQUESTED, message="migration COMPATIBLE: no alternative needed"
            )
        ai = self.deps.ai(self.trace_sink)
        if ai is None:
            return AIAlternativesView(
                status=AIStatus.AI_UNAVAILABLE,
                message=self.deps.ai_error or "AI service unavailable",
            )
        return self._safe_ai(
            AIAlternativesView,
            lambda: ai.alternatives(
                run_id=run_id,
                profile=profile,
                change=change,
                plan_id=plan_id,
                assessment=assessment,
                result=result,
            ),
        )

    def request_alternatives(self, run_id: str) -> AIAlternativesView:
        row = self.store.get_run(run_id)
        if row is None:
            raise NotFound(f"unknown run {run_id}")
        stored = self.store.get_result(run_id)
        if row["status"] != RunStatus.SUCCEEDED or stored is None:
            raise Conflict(f"run {run_id} has no evaluated result")
        profile, change = self.resolve(row["configuration_id"], row["change_id"])
        view = self._alternatives_view(
            run_id, profile, change, row["plan_id"], stored["assessment"], stored["result"]
        )
        self.store.update_run(run_id, ai_alternatives=view.model_dump(mode="json"))
        self._emit(
            run_id,
            "ai",
            {
                "kind": "result",
                "module": "alternatives",
                "status": view.status.value,
                "view": view.model_dump(mode="json"),
            },
        )
        return view

    # ------------------------------------------------------------------ terminal

    def _finish(self, ctx: _RunCtx) -> None:
        self.store.update_run(ctx.run_id, status=RunStatus.SUCCEEDED.value, finished_at=utc_now())
        self._emit_run(ctx.run_id)

    def _fail(self, run_id: str, ctx: _RunCtx | None, failure_class: str, message: str) -> None:
        try:
            if ctx is not None:
                for stage in STAGE_ORDER:
                    status = ctx.stages[stage]["status"]
                    if status == StageStatus.RUNNING:
                        self._set_stage(ctx, stage, StageStatus.FAILED, message)
                    elif status == StageStatus.QUEUED:
                        reason = (
                            "no evaluation: run failed"
                            if stage in (Stage.EVALUATION, Stage.NEXT_STEPS)
                            else "not executed: run failed"
                        )
                        self._set_stage(ctx, stage, StageStatus.SKIPPED, reason)
            self.store.update_run(
                run_id,
                status=RunStatus.FAILED.value,
                finished_at=utc_now(),
                verdict=None,
                failure=FailureView(
                    failure_class=FailureClass(failure_class), message=message[:2000]
                ).model_dump(mode="json"),
            )
            self._emit(
                run_id,
                "error",
                {
                    "source": "orchestrator",
                    "failure_class": failure_class,
                    "message": message[:2000],
                },
            )
            self._emit_run(run_id)
        except Exception:  # noqa: BLE001
            log.exception("could not record failure of %s", run_id)

    # ------------------------------------------------------------------ views

    def run_view(self, run_id: str) -> RunView:
        row = self.store.get_run(run_id)
        if row is None:
            raise NotFound(f"unknown run {run_id}")
        return self._row_view(row)

    def list_runs(self, limit: int = 50) -> list[RunView]:
        return [self._row_view(r) for r in self.store.list_runs(limit=limit)]

    def _row_view(self, row: dict[str, Any]) -> RunView:
        plan = {p["template_id"]: p for p in row["plan"] or []}
        catalog = catalog_templates()
        tests = []
        for t in self.store.list_test_results(row["run_id"]):
            template = catalog.get(t["template_id"])
            planned = plan.get(t["template_id"], {})
            tests.append(
                TestResultView(
                    test_id=t["test_id"],
                    template_id=t["template_id"],
                    title=template.title if template else t["template_id"],
                    negative=template.negative if template else False,
                    outcome=t["outcome"],
                    expected=t["expected"],
                    observed=t["observed"],
                    duration_ms=t["duration_ms"],
                    observation_ids=t.get("observation_ids") or [],
                    failure_class=t.get("failure_class"),
                    planned_by=planned.get("planned_by", "POLICY_REQUIRED"),
                )
            )
        queue_position = None
        if row["status"] == RunStatus.QUEUED and row["runner_family"]:
            queue_position = self._slot(row["runner_family"]).position(row["run_id"])
        return RunView(
            run_id=row["run_id"],
            mode=row["mode"],
            status=row["status"],
            configuration_id=row["configuration_id"],
            configuration_version=row["configuration_version"],
            change_id=row["change_id"],
            plan_id=row["plan_id"],
            parent_run_id=row["parent_run_id"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            queue_position=queue_position,
            stages=[StageView.model_validate(s) for s in row["stages"]],
            tests=tests,
            verdict=row["verdict"],
            failure=row["failure"],
            ai_plan=row["ai_plan"],
            ai_report=row["ai_report"],
            ai_alternatives=row["ai_alternatives"],
            source_pins=row["source_pins"] or {},
            tool_versions=row["tool_versions"] or {},
        )

    def planned_tests(self, run_id: str) -> list[dict[str, Any]]:
        row = self.store.get_run(run_id)
        if row is None:
            raise NotFound(f"unknown run {run_id}")
        return list(row["plan"] or [])

    # ------------------------------------------------------------------ assistant / AMD

    def assistant_context(self, run_id: str) -> dict[str, Any]:
        from releaseproof.orchestrator.reference import REFERENCE_RUN_ID, reference_bundle

        if run_id == REFERENCE_RUN_ID:
            run, result = reference_bundle()
            return {
                "run": run.model_dump(mode="json"),
                **result.model_dump(mode="json"),
                "recorded_reference": True,
            }
        run = self.run_view(run_id)
        context: dict[str, Any] = {"run": run.model_dump(mode="json")}
        stored = self.store.get_result(run_id) if run.status == RunStatus.SUCCEEDED else None
        if stored is not None:
            context.update(
                assessment=stored["assessment"],
                result=stored["result"],
                gap_plan=stored["gap_plan"],
                evidence=stored["evidence"],
                manifest_sha256=stored["manifest_sha256"],
            )
        try:
            profile, change = self.resolve(run.configuration_id, run.change_id)
            context["configuration"] = {
                "id": profile.id,
                "title": profile.title,
                "known_limitations": profile.known_limitations,
                "change": change.model_dump(mode="json"),
            }
        except OrchestratorError:
            pass
        return context

    def assistant_stream(self, run_id: str, messages: list[AssistantMessage]) -> Iterator[str]:
        context = self.assistant_context(run_id)
        ai = self.deps.ai(self.trace_sink)
        if ai is None:
            raise AIUnavailable(
                f"{AI_UNAVAILABLE}: {self.deps.ai_error or 'AI service unavailable'}"
            )
        try:
            return iter(ai.assistant_stream(run_id=run_id, context=context, messages=messages))
        except Exception as exc:  # noqa: BLE001
            raise AIUnavailable(f"{AI_UNAVAILABLE}: {type(exc).__name__}: {exc}") from exc

    def amd_info(self) -> dict[str, Any]:
        ai = self.deps.ai(self.trace_sink)
        provider: dict[str, Any]
        if ai is None:
            provider = {"status": AI_UNAVAILABLE, "error": self.deps.ai_error}
        else:
            try:
                provider = dict(ai.provider_info())
            except Exception as exc:  # noqa: BLE001
                provider = {"status": AI_UNAVAILABLE, "error": f"{type(exc).__name__}: {exc}"}
        return {"provider": provider, "traces": trace_stats(self.store.ai_trace_rows())}


def _percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, int(-(-pct * len(ordered) // 100)))  # nearest-rank
    return ordered[min(rank, len(ordered)) - 1]


def trace_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    ok = sum(1 for r in rows if r["status"] == AIStatus.OK)
    latencies = [int(r["latency_ms"]) for r in rows if r.get("latency_ms") is not None]
    by_module: dict[str, int] = {}
    for r in rows:
        by_module[r["module"]] = by_module.get(r["module"], 0) + 1
    return {
        "count": count,
        "ok": ok,
        "ok_rate": (ok / count) if count else None,
        "latency_ms_p50": _percentile(latencies, 50),
        "latency_ms_p95": _percentile(latencies, 95),
        "prompt_tokens": sum(int(r["prompt_tokens"] or 0) for r in rows),
        "completion_tokens": sum(int(r["completion_tokens"] or 0) for r in rows),
        "by_module": by_module,
    }
