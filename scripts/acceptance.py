"""End-to-end acceptance gate for ReleaseProof profiles.

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
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from releaseproof.ai.config import AISettings  # noqa: E402
from releaseproof.core.canonical.service import compute_canonical_hash  # noqa: E402
from releaseproof.orchestrator.identity import implementation_identity  # noqa: E402

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


def runner_source_digest(family: str) -> str:
    """Same sorted content identity emitted by the baked rp_runner executor."""
    if family not in {"wolfboot", "mcuboot"}:
        raise ValueError("unsupported runner family")
    roots = {
        "common": ROOT / "runners/common/rp_runner",
        "family": ROOT / f"runners/{family}/rp_{family}",
    }
    for name in ("app", "renode"):
        path = ROOT / f"runners/{family}/{name}"
        if path.is_dir():
            roots[name] = path
    digest = hashlib.sha256()
    for label, root in sorted(roots.items()):
        for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            digest.update(f"{label}/{path.relative_to(root).as_posix()}".encode() + b"\0")
            digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


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
            "idempotency_key": f"acceptance-{config['id']}-{uuid4().hex}",
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
    required = {t["template_id"] for t in change["templates"] if t["required"]}
    observed_templates = {t["template_id"] for t in executed}
    missing = sorted(required - observed_templates)
    gate(gates, "required templates executed", not missing, ", ".join(missing))
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
        bool(re.fullmatch(r"sha256:[0-9a-f]{64}", verdict.get("canonical_hash") or ""))
        and verdict.get("lifecycle") == "COMPLETED"
        and all(
            verdict.get(phase) in {"COMPATIBLE", "INCOMPATIBLE", "INDETERMINATE", "CONDITIONAL"}
            for phase in ("migration", "candidate", "transition")
        ),
        f"{verdict.get('migration')} "
        f"(cand {verdict.get('candidate')}, trans {verdict.get('transition')})",
    )
    gate(gates, "official flag is false", verdict.get("official") is False)

    result: dict[str, Any] = {}
    try:
        result = api.get(f"/api/assessments/{run_id}/result")
    except urllib.error.HTTPError as exc:
        gate(gates, "result available", False, str(exc))
    else:
        gate(gates, "result available", bool(result))
    if result:
        gate(
            gates,
            "canonical result hash recomputed",
            compute_canonical_hash(result["result"]) == verdict.get("canonical_hash"),
        )
        gate(
            gates,
            "result hash matches run verdict",
            result["result"].get("canonical_hash") == verdict.get("canonical_hash"),
        )
        ev = result.get("evidence") or []
        live = [e for e in ev if e.get("run_id") == run_id]
        gate(gates, "evidence belongs to this run", len(live) >= 3, f"{len(live)}/{len(ev)}")
        gate(
            gates,
            "manifest hash recorded",
            bool(re.fullmatch(r"[0-9a-f]{64}", result.get("manifest_sha256") or "")),
        )

    artifacts = api.get(f"/api/assessments/{run_id}/artifacts")
    gate(gates, "artifacts recorded", len(artifacts) >= 3, str(len(artifacts)))
    manifests = [a for a in artifacts if a["artifact_id"] == "MANIFEST"]
    gate(
        gates,
        "manifest artifact matches result digest",
        len(manifests) == 1 and manifests[0]["sha256"] == result.get("manifest_sha256"),
    )
    mismatches = []
    manifest = {}
    for art in artifacts:
        blob = api.raw(art["url"])
        if hashlib.sha256(blob).hexdigest() != art["sha256"]:
            mismatches.append(art["artifact_id"])
        if art["artifact_id"] == "MANIFEST":
            manifest = json.loads(blob)
    gate(gates, "artifact sha256 verified (all)", not mismatches, ",".join(mismatches))
    gate(
        gates,
        "manifest identifies this run and assessment",
        manifest.get("run_id") == run_id
        and (manifest.get("assessment") or {}).get("canonical_hash")
        == (compute_canonical_hash(result["assessment"]) if result.get("assessment") else None),
    )
    local_identity = implementation_identity()
    gate(
        gates,
        "deployed backend matches current source",
        (manifest.get("implementation") or {}).get("backend_sha256")
        == local_identity["backend_sha256"],
    )
    gate(
        gates,
        "runner code identity recorded",
        bool(
            re.fullmatch(
                r"[0-9a-f]{64}",
                (manifest.get("source_pins") or {}).get("releaseproof_runner_code_sha256", ""),
            )
        ),
    )
    gate(
        gates,
        "deployed runner matches current source",
        (manifest.get("source_pins") or {}).get("releaseproof_runner_code_sha256")
        == runner_source_digest(config["bootloader"]["family"]),
    )

    traces = api.get(f"/api/assessments/{run_id}/ai-traces")
    ok_traces = [t for t in traces if t["status"] == "OK"]
    ai_ok = bool(ok_traces)
    if require_ai:
        provider = api.get("/api/amd")["provider"]
        host = provider.get("endpoint_host")
        valid_traces = [
            t
            for t in ok_traces
            if t.get("run_id") == run_id
            and t.get("endpoint_host") == host
            and host in AISettings.from_env().allowed_hosts
            and t.get("request_id")
            and t.get("model")
        ]
        plan = run.get("ai_plan") or {}
        planner_traces = {t["trace_id"] for t in valid_traces if t["module"] == "planner"}
        ai_ok = (
            plan.get("status") == "OK"
            and bool(planner_traces & set(plan.get("trace_ids") or []))
            and provider.get("fallback_provider") is None
        )
        gate(
            gates,
            "AMD LLM called for this run",
            ai_ok,
            ", ".join(f"{t['module']}:{t['model']}@{t['endpoint_host']}" for t in ok_traces),
        )
        selected = {t["template_id"] for t in (plan.get("proposal") or {}).get("selected", [])}
        allowed = {t["template_id"] for t in change["templates"]}
        expected = required | (selected & (allowed - required))
        gate(
            gates,
            "accepted AMD plan was executed",
            ai_ok
            and bool(selected & observed_templates)
            and selected <= allowed
            and expected == observed_templates
            and not any(t.get("planned_by") == "PROFILE_OPTIONAL" for t in tests),
        )
        for module, field in (("explainer", "ai_report"), ("alternatives", "ai_alternatives")):
            view = run.get(field) or {}
            ids = {t["trace_id"] for t in valid_traces if t["module"] == module}
            gate(
                gates,
                f"AMD {module} validated for this run",
                view.get("status") == "OK"
                and bool(ids & set(view.get("trace_ids") or []))
                or module == "alternatives"
                and verdict.get("migration") == "COMPATIBLE"
                and view.get("status") == "NOT_REQUESTED",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--profile", action="append")
    parser.add_argument("--require-ai", action="store_true")
    parser.add_argument("--env-file", help="explicit dotenv file (never loaded implicitly)")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.env_file:
        from amd_common import load_env_file

        load_env_file(args.env_file)
    api = Api(args.base)
    configs = api.get("/api/configurations")
    if args.profile:
        unknown = sorted(set(args.profile) - {c["id"] for c in configs})
        if unknown:
            print(f"unknown or unexposed profiles: {', '.join(unknown)}")
            return 2
        configs = [c for c in configs if c["id"] in args.profile]
    if not configs:
        print("no configurations selected/exposed")
        return 2
    results = []
    for config in configs:
        try:
            result = run_profile(api, config, require_ai=args.require_ai, timeout=args.timeout)
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            # Preserve a failed report and continue checking the other profiles, even when
            # a failed/timed-out pipeline has no result or artifact endpoint yet.
            result = {
                "profile": config["id"],
                "passed": False,
                "gates": [
                    {"gate": "API response available and valid", "ok": False, "detail": str(exc)}
                ],
            }
            print(f"  [FAIL] {config['id']}: {exc}")
        results.append(result)
    out = ROOT / "docs" / "acceptance"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (out / f"{stamp}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    ok = all(r["passed"] for r in results)
    print(f"\nACCEPTANCE {'PASSED' if ok else 'FAILED'} — report docs/acceptance/{stamp}.json")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
