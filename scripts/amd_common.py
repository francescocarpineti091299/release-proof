"""Shared helpers for the AMD smoke test and benchmark scripts (real AMD endpoint only)."""

from __future__ import annotations

import json
import os
import statistics
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from releaseproof.ai.context import explain_context  # noqa: E402
from releaseproof.contracts.api import AITraceView  # noqa: E402
from releaseproof.core.assurance.service import evaluate  # noqa: E402
from releaseproof.core.projection.wp0 import build_wp0_baseline_assessment  # noqa: E402
from releaseproof.profiles.registry import get_template, load_profiles  # noqa: E402

WOLFBOOT = "nrf52840-wolfboot-pqc"
MCUBOOT = "nrf52840-mcuboot-pqc"


def load_env_file(path: str | None) -> None:
    """Load an explicitly selected dotenv file without replacing exported settings.

    No automatic discovery: tests and CI must not accidentally consume local credentials.
    Interpolation is disabled so API keys are kept exactly as supplied.
    """
    if path is None:
        return
    target = Path(path)
    if not target.is_absolute():
        target = REPO_ROOT / target
    if not target.is_file():
        raise ValueError(f"Environment file not found: {target}")
    for key, value in dotenv_values(target, interpolate=False, encoding="utf-8-sig").items():
        if value is not None:
            os.environ.setdefault(key, value)


class TraceLog:
    def __init__(self, echo: bool = True) -> None:
        self.items: list[AITraceView] = []
        self._lock = threading.Lock()
        self._echo = echo

    def __call__(self, trace: AITraceView) -> None:
        with self._lock:
            self.items.append(trace)
        if self._echo:
            print(
                f"  trace {trace.trace_id} {trace.module:<12} {trace.status:<22} "
                f"model={trace.model} latency_ms={trace.latency_ms} "
                f"tokens={trace.prompt_tokens}/{trace.completion_tokens} "
                f"request_id={trace.request_id}"
                + (f"\n    error: {trace.error}" if trace.error else ""),
                flush=True,
            )


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def bundle(profile_id: str) -> dict[str, Any]:
    profile = load_profiles()[profile_id]
    change = profile.changes[0]
    templates = [get_template(t) for t in [*change.required_templates, *change.optional_templates]]
    return {"profile": profile, "change": change, "templates": templates}


def freeze_case() -> dict[str, Any]:
    assessment = build_wp0_baseline_assessment()
    result = evaluate(assessment).model_dump(mode="json")
    return {"assessment": assessment, "result": result}


def assistant_context_for(b: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    ctx = explain_context(
        profile=b["profile"],
        change=b["change"],
        plan_id=b["change"].default_plan_id,
        assessment=case["assessment"],
        result=case["result"],
        test_results=[],
        budget_chars=12000,
    )
    return {"mode": "REFERENCE", "assessment_id": case["result"]["assessment_id"], **ctx.data}


def assistant_unavailable(text: str) -> bool:
    """Recognize service failure markers, including failures after partial streamed text."""
    return (
        not text.strip()
        or text.startswith("AI unavailable")
        or text.rstrip().endswith("[AI unavailable: the AMD stream was interrupted]")
    )


def percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1))))
    return ordered[k]


def trace_summary(traces: list[AITraceView]) -> dict[str, Any]:
    lat = [
        t.latency_ms for t in traces if t.latency_ms is not None and t.status != "AI_UNAVAILABLE"
    ]
    by_status: dict[str, int] = {}
    for t in traces:
        by_status[str(t.status)] = by_status.get(str(t.status), 0) + 1
    pt = [t.prompt_tokens for t in traces if t.prompt_tokens is not None]
    ct = [t.completion_tokens for t in traces if t.completion_tokens is not None]
    return {
        "traces": len(traces),
        "by_status": by_status,
        "latency_ms": {
            "p50": percentile(lat, 50),
            "p95": percentile(lat, 95),
            "mean": int(statistics.mean(lat)) if lat else None,
        },
        "prompt_tokens_total": sum(pt),
        "completion_tokens_total": sum(ct),
        "models": sorted({t.model for t in traces if t.model}),
        "request_ids_present": sum(1 for t in traces if t.request_id),
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    if not target.is_absolute():
        target = REPO_ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target
