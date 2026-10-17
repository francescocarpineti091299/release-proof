"""Verify the public demo with normal TLS validation, optionally including a live run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def check(base: str, *, live: bool, timeout: int) -> dict:
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use an HTTPS viewer URL without embedded credentials")
    base = base.rstrip("/")
    report = {"base": base, "checked_at": datetime.now(UTC).isoformat(), "checks": []}

    def record(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"check": name, "ok": ok, "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
        if not ok:
            raise AssertionError(name)

    def request(path: str, body: dict | None = None, headers: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            base + path,
            data=data,
            headers={
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if data else {}),
                **(headers or {}),
            },
        )
        # Default urllib/SSL context validates both certificate chain and hostname.
        return urllib.request.urlopen(req, timeout=75)

    def get_json(path: str):
        with request(path) as response:
            record(f"HTTP {path}", response.status == 200, str(response.status))
            return json.load(response)

    with request("/") as response:
        html = response.read().decode()
        record(
            "UI and trusted HTTPS",
            response.status == 200 and "ReleaseProof" in html,
            f"HTTP {response.status}; {response.headers.get('X-Cache', '')}",
        )
        record("no redirect to origin hostname", response.url.startswith(base + "/"), response.url)

    assets = list(dict.fromkeys(re.findall(r'(?:src|href)="(/_next/static/[^"<>]+)"', html)))
    record("UI has built assets", bool(assets), str(len(assets)))
    for asset in assets[:5]:
        with request(asset) as response:
            record("static asset", response.status == 200 and bool(response.read()), asset)

    health = get_json("/api/health")
    record(
        "demo health",
        health.get("status") == "ok" and health.get("env") == "demo",
        json.dumps(health),
    )
    configurations = get_json("/api/configurations")
    record(
        "two supported profiles",
        len(configurations) == 2 and all(c.get("status") == "SUPPORTED" for c in configurations),
    )
    runs = get_json("/api/assessments?limit=1")
    record("query parameters forwarded", len(runs) <= 1)

    if live:
        config = next(c for c in configurations if c["id"] == "nrf52840-mcuboot-pqc")
        key = f"cloudfront-smoke-{uuid4().hex}"
        body = {
            "configuration_id": config["id"],
            "change_id": config["changes"][0]["change_id"],
            "idempotency_key": key,
        }
        with request("/api/assessments", body, {"Idempotency-Key": key}) as response:
            run = json.load(response)
            record(
                "POST creates live run",
                response.status == 201 and run.get("mode") == "LIVE",
                run["run_id"],
            )
        with request("/api/assessments", body, {"Idempotency-Key": key}) as response:
            duplicate = json.load(response)
            record("POST retry is idempotent", duplicate["run_id"] == run["run_id"])
        run_id = run["run_id"]
        deadline = time.monotonic() + timeout
        event_count = 0
        with request(f"/api/assessments/{run_id}/events") as response:
            record(
                "SSE content type", "text/event-stream" in response.headers.get("Content-Type", "")
            )
            for line in response:
                if time.monotonic() > deadline:
                    raise TimeoutError("Live run exceeded smoke timeout")
                if line.startswith(b"data:"):
                    event_count += 1
        record("SSE delivered events", event_count > 0, str(event_count))
        run = get_json(f"/api/assessments/{run_id}")
        record("live pipeline succeeded", run["status"] == "SUCCEEDED", run["status"])
        record("live tests executed", len(run.get("tests", [])) >= 3)
    elif runs:
        # An operator may be using the demo during a read-only infra check. A
        # RUNNING/QUEUED run has no result yet; inspect a completed run instead.
        completed = next((r for r in runs if r["status"] == "SUCCEEDED"), None)
        if completed is None:
            history = get_json("/api/assessments?limit=20")
            completed = next((r for r in history if r["status"] == "SUCCEEDED"), None)
        run_id = completed["run_id"] if completed else None
    else:
        run_id = None

    if run_id:
        report["run_id"] = run_id
        result = get_json(f"/api/assessments/{run_id}/result")
        record("verdict available", bool(result["result"].get("canonical_hash")))
        artifacts = get_json(f"/api/assessments/{run_id}/artifacts")
        manifest = next(a for a in artifacts if a["artifact_id"] == "MANIFEST")
        with request(manifest["url"]) as response:
            digest = hashlib.sha256(response.read()).hexdigest()
        record("manifest downloaded and hash verified", digest == manifest["sha256"])
    report["passed"] = True
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument(
        "--live", action="store_true", help="Create one new MCUboot run and verify live SSE"
    )
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check(args.base, live=args.live, timeout=args.timeout)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"passed": report["passed"], "base": report["base"], "run_id": report.get("run_id")}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
