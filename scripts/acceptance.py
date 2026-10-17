"""End-to-end acceptance gate for ReleaseProof profiles (brief §3.3 / §10.1).

Starts one fresh LIVE run per profile through the public API, waits for completion and checks
the objective gates. A profile may be promoted to SUPPORTED only if every gate passes.

Usage:
  python scripts/acceptance.py --base http://localhost:8080 [--profile ID ...] [--require-ai]
Writes a JSON report to docs/acceptance/<timestamp>.json. Exit code 0 only if all gates pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def _req(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
        return json.loads(raw) if "json" in ctype else raw

    def get(self, path: str) -> Any:
        return self._req("GET", path)

    def raw(self, path: str) -> bytes:
        with urllib.request.urlopen(self.base + path, timeout=60) as resp:
            return resp.read()

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self._req("POST", path, body)


def gate(report: list[dict[str, Any]], name: str, ok: bool, detail: str = "") -> bool:
    report.append({"gate": name, "ok": bool(ok), "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{' — ' + detail if detail else ''}")
    return bool(ok)


def run_profile(api: Api, config: dict[str, Any], *, require_ai: bool, timeout: int) -> dict:
    gates: list[dict[str, Any]] = []
    change = config["changes"][0]
    print(f"\n== {config['id']} / {change['change_id']}")
    started = datetime.now(UTC)
    run = api.post(
        "/api/assessments",
        {
            "configuration_id": config["id"],
            "change_id": change["change_id"],
            "idempotency_key": f"acceptance-{config['id']}-{int(time.time())}",
        },
    )
    run_id = run["run_id"]
    print(f"  run_id={run_id}")
    deadline = time.monotonic() + timeout
    while run["status"] not in TERMINAL and time.monotonic() < deadline:
        time.sleep(5)
        run = api.get(f"/api/assessments/{run_id}")
    gate(gates, "run reached a terminal state", run["status"] in TERMINAL, run["status"])
    gate(gates, "run is LIVE (not replay)", run["mode"] == "LIVE", run["mode"])
    created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
    gate(
        gates, "run created now", abs((created - started).total_seconds()) < 120, run["created_at"]
    )
    gate(gates, "pipeline succeeded", run["status"] == "SUCCEEDED", str(run.get("failure")))

    tests = run.get("tests") or []
    executed = [t for t in tests if t["outcome"] in {"PASS", "FAIL"}]
    gate(gates, "tests executed", len(executed) >= 3, f"{len(executed)}/{len(tests)}")
    negatives = [t for t in tests if t["negative"] and t["outcome"] == "PASS"]
    gate(
        gates,
        "at least one negative test observed",
        bool(negatives),
        ", ".join(t["template_id"] for t in negatives),
    )
    boots = [t for t in tests if t["test_id"] == "E01" and t["outcome"] == "PASS"]
    gate(gates, "positive boot observed (E01)", bool(boots))
    gate(
        gates,
        "build/sign stage succeeded",
        any(s["stage"] == "BUILD_SIGN" and s["status"] == "SUCCEEDED" for s in run["stages"]),
    )

    verdict = run.get("verdict") or {}
    gate(
        gates,
        "deterministic verdict issued",
        bool(verdict.get("canonical_hash")),
        f"{verdict.get('migration')} "
        f"(cand {verdict.get('candidate')}, trans {verdict.get('transition')})",
    )
    gate(gates, "official flag is false", verdict.get("official") is False)

    result: dict[str, Any] = {}
    try:
        result = api.get(f"/api/assessments/{run_id}/result")
    except urllib.error.HTTPError as exc:
        gate(gates, "result available", False, str(exc))
    if result:
        gate(
            gates,
            "result hash matches run verdict",
            result["result"].get("canonical_hash") == verdict.get("canonical_hash"),
        )
        ev = result.get("evidence") or []
        live = [e for e in ev if e.get("run_id") == run_id]
        gate(gates, "evidence belongs to this run", len(live) >= 3, f"{len(live)}/{len(ev)}")
        gate(gates, "manifest hash recorded", bool(result.get("manifest_sha256")))

    artifacts = api.get(f"/api/assessments/{run_id}/artifacts")
    gate(gates, "artifacts recorded", len(artifacts) >= 3, str(len(artifacts)))
    mismatches = []
    for art in artifacts[:5]:
        blob = api.raw(art["url"])
        if hashlib.sha256(blob).hexdigest() != art["sha256"]:
            mismatches.append(art["artifact_id"])
    gate(gates, "artifact sha256 verified (sample)", not mismatches, ",".join(mismatches))

    traces = api.get(f"/api/assessments/{run_id}/ai-traces")
    ok_traces = [t for t in traces if t["status"] == "OK"]
    ai_ok = bool(ok_traces)
    if require_ai:
        gate(
            gates,
            "AMD LLM called for this run",
            ai_ok,
            ", ".join(f"{t['module']}:{t['model']}@{t['endpoint_host']}" for t in ok_traces),
        )
    else:
        gates.append(
            {"gate": "AMD LLM called for this run", "ok": ai_ok, "detail": "informational"}
        )
    return {
        "profile": config["id"],
        "change": change["change_id"],
        "run_id": run_id,
        "verdict": verdict,
        "gates": gates,
        "passed": all(g["ok"] for g in gates if g.get("detail") != "informational"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--profile", action="append")
    parser.add_argument("--require-ai", action="store_true")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    api = Api(args.base)
    configs = api.get("/api/configurations")
    if args.profile:
        configs = [c for c in configs if c["id"] in args.profile]
    if not configs:
        print("no configurations selected/exposed")
        return 2
    results = [
        run_profile(api, c, require_ai=args.require_ai, timeout=args.timeout) for c in configs
    ]
    out = ROOT / "docs" / "acceptance"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (out / f"{stamp}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    ok = all(r["passed"] for r in results)
    print(f"\nACCEPTANCE {'PASSED' if ok else 'FAILED'} — report docs/acceptance/{stamp}.json")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
