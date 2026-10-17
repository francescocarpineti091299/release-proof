"""Smoke test for the running wolfBoot runner container.

    docker run --rm -d --name rp-wolfboot -v <hostdir>:/data -p 18081:8080 releaseproof/runner-wolfboot:0.1.0
    backend\\.venv\\Scripts\\python.exe runners\\wolfboot\\smoke.py --data-dir <hostdir>

POSTs /execute with every wolfBoot template, validates each NDJSON event against
schemas/runner_event.schema.json, checks protocol invariants, verifies artifact hashes on the host
side of the /data volume (when --data-dir is given) and prints a per-test summary.
Exit code 0 only if every check passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "schemas" / "runner_event.schema.json"
TEMPLATES = [
    "wolfboot.discover",
    "wolfboot.self_update_capability",
    "wolfboot.boot_current",
    "wolfboot.boot_candidate",
    "wolfboot.tampered_image_rejected",
    "wolfboot.cross_generation_update",
    "wolfboot.candidate_rejects_classical",
    "wolfboot.dual_signature_build",
]
# Facts each template must emit (WORKSTREAMS.md, wolfBoot table).
EXPECTED_FACTS = {
    "D01": {"bootloader_commit", "crypto_commit", "partition_layout"},
    "E11": {"bootloader_field_update"},
    "E01": {"boot_outcome", "observed_version", "signed_image_size_bytes", "bootloader_size_bytes",
            "public_key_sha256"},
    "E08": {"update_outcome"},
    "E02": {"boot_outcome", "observed_version", "signed_image_size_bytes", "bootloader_size_bytes",
            "public_key_sha256"},
    "E04": {"image_header"},
    "E05": {"layout_fit"},
    "E03": {"auth_negative"},
    "X01": {"cross_update_outcome"},
    "P01": {"classical_image_on_candidate"},
    "O05": {"dual_signature_build"},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:18081")
    ap.add_argument("--data-dir", help="host directory mounted at /data (enables artifact hash checks)")
    ap.add_argument("--templates", nargs="*", default=TEMPLATES)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--save", help="write the raw NDJSON stream to this file")
    args = ap.parse_args()

    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    run_id = "RP-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    request = {
        "run_id": run_id,
        "profile_id": "nrf52840-wolfboot-pqc",
        "change_id": "ecdsa_p256_to_mldsa87",
        "tests": [{"template_id": t, "params": {}} for t in args.templates],
        "artifact_dir": f"/data/runs/{run_id}/artifacts",
        "timeout_seconds": args.timeout,
    }
    with urllib.request.urlopen(args.url + "/health", timeout=30) as resp:
        health = json.loads(resp.read())
    print(f"health: {health.get('status')} templates={len(health.get('templates', []))}")

    req = urllib.request.Request(
        args.url + "/execute", data=json.dumps(request).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    errors: list[str] = []
    events: list[dict] = []
    started = time.monotonic()
    raw_lines: list[str] = []
    with urllib.request.urlopen(req, timeout=args.timeout + 60) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            raw_lines.append(line)
            ev = json.loads(line)
            events.append(ev)
            for err in validator.iter_errors({"event": ev}):
                errors.append(f"seq {ev.get('seq')} ({ev.get('type')}): schema: {err.message[:200]}")
            if ev["type"] == "stage":
                print(f"[{time.monotonic() - started:6.1f}s] stage {ev['stage']} {ev['status']} {ev.get('message', '')}")
            elif ev["type"] == "test_result":
                print(f"[{time.monotonic() - started:6.1f}s] {ev['test_id']} {ev['outcome']} ({ev['duration_ms']} ms)")
            elif ev["type"] == "error":
                print(f"[{time.monotonic() - started:6.1f}s] ERROR {ev['failure_class']}: {ev['message'][:300]}")
    total_s = time.monotonic() - started
    if args.save:
        Path(args.save).write_text("\n".join(raw_lines) + "\n", encoding="utf-8")

    # ---- invariants
    seqs = [e["seq"] for e in events]
    if seqs != list(range(len(events))):
        errors.append("seq is not contiguous from 0")
    if any(e["run_id"] != run_id for e in events):
        errors.append("run_id mismatch")
    done = [e for e in events if e["type"] == "done"]
    if len(done) != 1 or events[-1]["type"] != "done":
        errors.append("exactly one final done event expected")
    elif done[0]["status"] != "SUCCEEDED":
        errors.append(f"done.status={done[0]['status']}")
    results = {e["template_id"]: e for e in events if e["type"] == "test_result"}
    for t in args.templates:
        if t not in results:
            errors.append(f"no test_result for {t}")
    observations = {e["observation"]["observation_id"]: e["observation"] for e in events if e["type"] == "observation"}
    artifacts = {e["artifact_id"]: e for e in events if e["type"] == "artifact"}
    for r in results.values():
        for oid in r.get("observation_ids", []):
            if oid not in observations:
                errors.append(f"{r['test_id']}: references unknown observation {oid}")
    for o in observations.values():
        for aid in o["source_artifact_ids"]:
            if aid not in artifacts:
                errors.append(f"{o['observation_id']}: unknown source artifact {aid}")
    facts_by_test: dict[str, set[str]] = {}
    for o in observations.values():
        facts_by_test.setdefault(o["test_id"], set()).add(o["fact"])
    requested_tests = {results[t]["test_id"] for t in args.templates if t in results}
    for test_id, facts in EXPECTED_FACTS.items():
        owner = {"E08": "E01", "E04": "E02", "E05": "E02"}.get(test_id, test_id)
        if owner in requested_tests and results.get(_tid(owner), {}).get("outcome") not in (None, "ERROR"):
            missing = facts - facts_by_test.get(test_id, set())
            if missing:
                errors.append(f"{test_id}: missing facts {sorted(missing)}")
    if args.data_dir:
        root = Path(args.data_dir) / "runs" / run_id / "artifacts"
        for a in artifacts.values():
            p = root / a["path"]
            if not p.is_file():
                errors.append(f"artifact file missing on host: {p}")
                continue
            if hashlib.sha256(p.read_bytes()).hexdigest() != a["sha256"]:
                errors.append(f"artifact hash mismatch: {p}")

    # ---- report
    print(f"\nrun {run_id}: {len(events)} events, {len(observations)} observations, "
          f"{len(artifacts)} artifacts, {total_s:.1f}s wall")
    for t in args.templates:
        r = results.get(t)
        if not r:
            continue
        print(f"\n== {r['test_id']} {t}: {r['outcome']}"
              f"{' [' + r['failure_class'] + ']' if r.get('failure_class') else ''} ({r['duration_ms']} ms)")
        print(f"   observed: {r['observed']}")
        for oid in r.get("observation_ids", []):
            o = observations.get(oid)
            if o:
                print(f"   - {oid} [{o['subject']}/{o['acquisition_mode']}] = {json.dumps(o['value'])}")
                if o.get("locator"):
                    print(f"       @ {o['locator'][:400]}")
    if done:
        print(f"\ntool_versions: {json.dumps(done[0].get('tool_versions'), indent=1)}")
        print(f"source_pins: {json.dumps(done[0].get('source_pins'), indent=1)}")
    if errors:
        print(f"\nSMOKE FAILED ({len(errors)} problems):")
        for e in errors[:50]:
            print("  - " + e)
        return 1
    print("\nSMOKE OK")
    return 0


def _tid(test_id: str) -> str:
    return {
        "D01": "wolfboot.discover", "E11": "wolfboot.self_update_capability", "E01": "wolfboot.boot_current",
        "E02": "wolfboot.boot_candidate", "E03": "wolfboot.tampered_image_rejected",
        "X01": "wolfboot.cross_generation_update", "P01": "wolfboot.candidate_rejects_classical",
        "O05": "wolfboot.dual_signature_build",
    }[test_id]


if __name__ == "__main__":
    sys.exit(main())
