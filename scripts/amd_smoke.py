#!/usr/bin/env python
"""AMD smoke test: 10 real LLM calls against the configured AMD endpoint.

Usage (from the repo root, with the AMD_LLM_* variables exported):

    backend\\.venv\\Scripts\\python.exe scripts\\amd_smoke.py [--out docs/AMD_SMOKE.json]

No stub, no other provider: if the endpoint is not configured or not reachable every call is
recorded as AI_UNAVAILABLE and the script exits with code 2.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from amd_common import (
    MCUBOOT,
    WOLFBOOT,
    TraceLog,
    assistant_context_for,
    bundle,
    freeze_case,
    load_env_file,
    now_utc,
    run_stamp,
    trace_summary,
    write_json,
)

from releaseproof.ai import AIService
from releaseproof.contracts.api import AssistantMessage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="docs/AMD_SMOKE.json")
    parser.add_argument("--env-file", help="dotenv file, relative to the repository root")
    args = parser.parse_args(argv)
    try:
        load_env_file(args.env_file)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))

    traces = TraceLog()
    svc = AIService.from_env(traces)
    info = svc.provider_info()
    print(f"provider={info['provider']} hardware={info['hardware']} host={info['endpoint_host']}")
    print(f"models={info['models']} configured={info['configured']}")
    if not info["configured"]:
        print(f"WARNING: {info['unavailable_reason']}")

    run_id = f"SMOKE-{run_stamp()}"
    wolf, mcu, freeze = bundle(WOLFBOOT), bundle(MCUBOOT), freeze_case()
    explain_args = {
        "profile": wolf["profile"],
        "change": wolf["change"],
        "plan_id": wolf["change"].default_plan_id,
        "assessment": freeze["assessment"],
        "result": freeze["result"],
    }

    def explain() -> Any:
        return svc.explain(run_id=run_id, test_results=[], **explain_args)

    def alternatives() -> Any:
        return svc.alternatives(run_id=run_id, **explain_args)

    calls: list[tuple[str, str, Any]] = [
        ("planner", WOLFBOOT, lambda: svc.plan_tests(run_id=run_id, **wolf)),
        ("planner", MCUBOOT, lambda: svc.plan_tests(run_id=run_id, **mcu)),
        ("planner", WOLFBOOT, lambda: svc.plan_tests(run_id=run_id, **wolf)),
        ("planner", MCUBOOT, lambda: svc.plan_tests(run_id=run_id, **mcu)),
        ("explainer", "WP0-FREEZE", explain),
        ("explainer", "WP0-FREEZE", explain),
        ("explainer", "WP0-FREEZE", explain),
        ("alternatives", "WP0-FREEZE", alternatives),
        ("alternatives", "WP0-FREEZE", alternatives),
        ("assistant", "WP0-FREEZE", lambda: _assistant(svc, run_id, wolf, freeze)),
    ]
    results = []
    for index, (module, case, fn) in enumerate(calls, start=1):
        print(f"[{index:02d}/{len(calls)}] {module} {case}", flush=True)
        t0 = time.perf_counter()
        view = fn()
        elapsed = int((time.perf_counter() - t0) * 1000)
        data = view if isinstance(view, dict) else view.model_dump(mode="json")
        entry = {"index": index, "module": module, "case": case, "wall_ms": elapsed, **data}
        print(f"  -> status={entry['status']} {entry.get('message', '')[:160]}")
        results.append(entry)

    summary = trace_summary(traces.items)
    ok_calls = sum(1 for r in results if r["status"] == "OK")
    payload = {
        "kind": "AMD_SMOKE",
        "generated_at": now_utc(),
        "run_id": run_id,
        "provider_info": info,
        "fallback_provider": None,
        "calls": results,
        "summary": {**summary, "logical_calls": len(results), "logical_calls_ok": ok_calls},
        "traces": [t.model_dump(mode="json") for t in traces.items],
    }
    path = write_json(args.out, payload)
    print(
        f"\n{ok_calls}/{len(results)} calls OK; {summary['traces']} traces; "
        f"p50={summary['latency_ms']['p50']}ms p95={summary['latency_ms']['p95']}ms"
    )
    print(f"wrote {path}")
    if summary["by_status"].get("AI_UNAVAILABLE") == summary["traces"]:
        return 2
    return 0 if ok_calls == len(results) else 1


def _assistant(svc: AIService, run_id: str, wolf: dict, freeze: dict) -> dict[str, Any]:
    chunks = list(
        svc.assistant_stream(
            run_id=run_id,
            context=assistant_context_for(wolf, freeze),
            messages=[
                AssistantMessage(
                    role="user",
                    content="Why is the migration verdict what it is? Cite the blocking IDs.",
                )
            ],
        )
    )
    text = "".join(chunks)
    failed = text.startswith("AI unavailable")
    return {
        "status": "AI_UNAVAILABLE" if failed else "OK",
        "message": text[:600],
        "chunks": len(chunks),
    }


if __name__ == "__main__":
    sys.exit(main())
