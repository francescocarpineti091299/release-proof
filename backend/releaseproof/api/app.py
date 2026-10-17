"""FastAPI application. Run with ``uvicorn releaseproof.api.app:app``."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from releaseproof.api.models import (
    AmdView,
    ConfigurationView,
    HealthView,
    PlannedTestView,
    ReferenceView,
    configuration_view,
)
from releaseproof.api.sse import MAX_EVENT_ID, event_stream, parse_last_event_id
from releaseproof.contracts.api import (
    AIAlternativesView,
    AITraceView,
    ArtifactView,
    AssistantRequest,
    EvidenceView,
    ResultView,
    RunCreate,
    RunStatus,
    RunView,
)
from releaseproof.contracts.profile import TestCatalog
from releaseproof.orchestrator.deps import Deps
from releaseproof.orchestrator.evaluation import (
    EvaluationFailure,
    artifact_view,
    resolve_artifact_path,
    verify_artifacts,
)
from releaseproof.orchestrator.reference import (
    NOTICE,
    RECORDED_AT,
    REFERENCE_RUN_ID,
    reference_bundle,
)
from releaseproof.orchestrator.service import (
    AI_UNAVAILABLE,
    AIUnavailable,
    Orchestrator,
    OrchestratorError,
    catalog_templates,
)
from releaseproof.orchestrator.settings import Settings
from releaseproof.profiles import registry
from releaseproof.store.db import Store

_ID = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")
_TEXT_KINDS = {"log", "uart", "script", "config"}


def _check_id(value: str, what: str) -> str:
    if not _ID.fullmatch(value):
        raise HTTPException(status_code=404, detail=f"unknown {what}")
    return value


def _orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


Orch = Annotated[Orchestrator, Depends(_orchestrator)]


def create_app(settings: Settings | None = None, deps: Deps | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(settings.db_path)
        orchestrator: Orchestrator | None = None
        try:
            orchestrator = Orchestrator(store=store, settings=settings, deps=deps)
            orchestrator.start()
            app.state.settings = settings
            app.state.store = store
            app.state.orchestrator = orchestrator
            yield
        finally:
            if orchestrator is not None:
                # Shutdown returns only once all run workers (including their AI calls) exit.
                # Keep the event loop responsive while draining, and never close SQLite if
                # the drain raises or is interrupted.
                await run_in_threadpool(orchestrator.shutdown)
            store.close()

    app = FastAPI(
        title="ReleaseProof API",
        version="0.1.0",
        description="Evidence-backed firmware migration assessments (official=false).",
        lifespan=lifespan,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["Idempotent-Replayed"],
        )

    @app.exception_handler(OrchestratorError)
    async def _orchestrator_error(_: Request, exc: OrchestratorError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    # -------------------------------------------------------------- registry

    @app.get("/api/health", response_model=HealthView)
    def health(o: Orch) -> HealthView:
        return HealthView(
            env=o.settings.env,
            schema_version=o.store.schema_version,
            expose_experimental=o.settings.expose_experimental,
        )

    @app.get("/api/configurations", response_model=list[ConfigurationView])
    def configurations(o: Orch) -> list[ConfigurationView]:
        profiles = registry.selectable_profiles(include_experimental=o.settings.expose_experimental)
        return [configuration_view(p, catalog_templates()) for p in profiles]

    @app.get("/api/configurations/{configuration_id}", response_model=ConfigurationView)
    def configuration(configuration_id: str, o: Orch) -> ConfigurationView:
        try:
            profile = registry.get_profile(configuration_id)
        except registry.RegistryError as exc:
            raise HTTPException(404, f"unknown configuration {configuration_id}") from exc
        if not o.is_selectable(profile):
            raise HTTPException(404, f"configuration {configuration_id} is not available")
        return configuration_view(profile, catalog_templates())

    @app.get("/api/catalog/tests", response_model=TestCatalog)
    def catalog() -> TestCatalog:
        return registry.load_catalog()

    # -------------------------------------------------------------- runs

    @app.post("/api/assessments", response_model=RunView, status_code=201)
    def create_assessment(
        body: RunCreate,
        response: Response,
        o: Orch,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> RunView:
        view, created = o.create_run(body, idempotency_key)
        if not created:
            response.status_code = 200
            response.headers["Idempotent-Replayed"] = "true"
        return view

    @app.get("/api/assessments", response_model=list[RunView])
    def list_assessments(o: Orch, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[RunView]:
        return o.list_runs(limit)

    @app.get("/api/assessments/{run_id}", response_model=RunView)
    def get_assessment(run_id: str, o: Orch) -> RunView:
        if run_id == REFERENCE_RUN_ID:
            return reference_bundle()[0]
        return o.run_view(_check_id(run_id, "run"))

    @app.get("/api/assessments/{run_id}/plan", response_model=list[PlannedTestView])
    def get_plan(run_id: str, o: Orch) -> list[PlannedTestView]:
        return [
            PlannedTestView.model_validate(p) for p in o.planned_tests(_check_id(run_id, "run"))
        ]

    @app.get("/api/assessments/{run_id}/events")
    async def events(
        run_id: str,
        request: Request,
        after: Annotated[int | None, Query(ge=0, le=MAX_EVENT_ID)] = None,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        o: Orchestrator = request.app.state.orchestrator
        _check_id(run_id, "run")
        if o.store.get_run(run_id) is None:
            raise HTTPException(404, f"unknown run {run_id}")
        stream = event_stream(
            o,
            run_id,
            after=parse_last_event_id(last_event_id, after),
            heartbeat=o.settings.sse_heartbeat_seconds,
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/assessments/{run_id}/result", response_model=ResultView)
    def get_result(run_id: str, o: Orch) -> ResultView:
        if run_id == REFERENCE_RUN_ID:
            return reference_bundle()[1]
        run = o.run_view(_check_id(run_id, "run"))
        stored = o.store.get_result(run_id) if run.status == RunStatus.SUCCEEDED else None
        if stored is None:
            detail = {"error": "RESULT_NOT_AVAILABLE", "status": run.status.value}
            if run.failure is not None:
                detail["failure"] = run.failure.model_dump(mode="json")
            raise HTTPException(409, detail)
        return ResultView(
            run_id=run_id,
            assessment=stored["assessment"],
            result=stored["result"],
            gap_plan=stored["gap_plan"],
            dossier_markdown=stored["dossier_markdown"],
            evidence=[EvidenceView.model_validate(e) for e in stored["evidence"]],
            manifest_sha256=stored["manifest_sha256"],
        )

    @app.get("/api/assessments/{run_id}/artifacts", response_model=list[ArtifactView])
    def list_artifacts(run_id: str, o: Orch) -> list[ArtifactView]:
        o.run_view(_check_id(run_id, "run"))
        return [artifact_view(run_id, a) for a in o.store.list_artifacts(run_id)]

    @app.get("/api/assessments/{run_id}/artifacts/{artifact_id}")
    def download_artifact(run_id: str, artifact_id: str, o: Orch) -> FileResponse:
        _check_id(run_id, "run")
        _check_id(artifact_id, "artifact")
        row = o.store.get_artifact(run_id, artifact_id)
        if row is None:
            raise HTTPException(404, "unknown artifact")
        path = resolve_artifact_path(o.settings.runs_dir, row)
        if path is None or not path.is_file():
            raise HTTPException(404, "artifact not available")
        try:
            verify_artifacts(o.settings.runs_dir, [row])
        except (EvaluationFailure, OSError) as exc:
            raise HTTPException(409, "artifact integrity check failed") from exc
        headers = {"X-Content-Type-Options": "nosniff", "X-Artifact-Sha256": row["sha256"]}
        if row["kind"] in _TEXT_KINDS:
            return FileResponse(
                path,
                media_type="text/plain; charset=utf-8",
                filename=row["name"],
                content_disposition_type="inline",
                headers=headers,
            )
        if row["kind"] == "manifest":
            return FileResponse(
                path,
                media_type="application/json",
                filename=row["name"],
                content_disposition_type="inline",
                headers=headers,
            )
        return FileResponse(
            path, media_type="application/octet-stream", filename=row["name"], headers=headers
        )

    @app.get("/api/assessments/{run_id}/ai-traces", response_model=list[AITraceView])
    def ai_traces(run_id: str, o: Orch) -> list[AITraceView]:
        o.run_view(_check_id(run_id, "run"))
        return [AITraceView.model_validate(t) for t in o.store.list_ai_traces(run_id)]

    @app.post("/api/assessments/{run_id}/alternatives", response_model=AIAlternativesView)
    def request_alternatives(run_id: str, o: Orch) -> AIAlternativesView:
        return o.request_alternatives(_check_id(run_id, "run"))

    @app.post(
        "/api/assessments/{run_id}/alternatives/{plan_id}/evaluate",
        response_model=RunView,
        status_code=201,
    )
    def evaluate_alternative(
        run_id: str,
        plan_id: str,
        response: Response,
        o: Orch,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> RunView:
        view, created = o.evaluate_alternative(
            _check_id(run_id, "run"), _check_id(plan_id, "plan"), idempotency_key
        )
        if not created:
            response.status_code = 200
            response.headers["Idempotent-Replayed"] = "true"
        return view

    # -------------------------------------------------------------- AI

    @app.post("/api/assistant")
    def assistant(body: AssistantRequest, o: Orch) -> StreamingResponse:
        if body.run_id != REFERENCE_RUN_ID:
            o.run_view(_check_id(body.run_id, "run"))
        chunks = o.assistant_stream(body.run_id, body.messages)
        try:
            first = next(chunks, "")
        except Exception as exc:  # noqa: BLE001
            raise AIUnavailable(f"{AI_UNAVAILABLE}: {type(exc).__name__}: {exc}") from exc

        def body_iter():
            yield first
            try:
                yield from chunks
            except Exception:  # noqa: BLE001 - stream already started; say so in-band
                yield f"\n\n[{AI_UNAVAILABLE}: the assistant stream was interrupted]"

        return StreamingResponse(
            body_iter(),
            media_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/reference", response_model=ReferenceView)
    def reference() -> ReferenceView:
        run, result = reference_bundle()
        return ReferenceView(
            recorded_at=RECORDED_AT,
            notice=NOTICE,
            canonical_hash=result.result.get("canonical_hash"),
            run=run,
            result=result,
        )

    @app.get("/api/amd", response_model=AmdView)
    def amd(o: Orch) -> AmdView:
        return AmdView.model_validate(o.amd_info())

    return app


app = create_app()

__all__ = ["app", "create_app"]
