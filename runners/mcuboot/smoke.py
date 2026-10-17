"""Smoke test for a running MCUboot runner container.

    docker run -d --name rp-mcuboot -p 18080:8080 -v <tmp>:/data releaseproof/runner-mcuboot:0.1.0
    python runners/mcuboot/smoke.py --url http://localhost:18080 --data-dir <tmp>

POSTs /execute with every mcuboot template, validates every NDJSON event against
schemas/runner_event.schema.json (jsonschema if installed, else a built-in subset validator),
checks the fact vocabulary of docs/WORKSTREAMS.md and artifact hashes, and prints a summary.
Exit code 0 only if the run SUCCEEDED and every event is valid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "runner_event.schema.json"
TEMPLATES = [
    "mcuboot.discover",
    "mcuboot.bootloader_update_capability",
    "mcuboot.boot_current",
    "mcuboot.signed_update",
    "mcuboot.tampered_image_rejected",
    "mcuboot.pqc_sign_attempt",
    "mcuboot.cross_key_update",
]
# (test_id, fact) -> (subject, allowed values or a predicate)
_ENUM = lambda *vals: (lambda v: v in vals)  # noqa: E731
_INT = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
FACTS: dict[tuple[str, str], tuple[str, Any]] = {
    ("D01", "bootloader_commit"): ("toolchain", lambda v: bool(re.fullmatch(r"[0-9a-f]{40}", str(v)))),
    ("D01", "zephyr_commit"): ("toolchain", lambda v: bool(re.fullmatch(r"[0-9a-f]{40}", str(v)))),
    ("D01", "partition_layout"): ("platform", lambda v: isinstance(v, dict) and set(v) == {
        "boot_partition_size", "slot0_address", "slot0_size", "slot1_address", "slot1_size"}
        and all(_INT(x) for x in v.values())),
    ("D01", "imgtool_key_types"): ("toolchain", lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v)),
    ("E11", "bootloader_field_update"): ("platform", _ENUM("SUPPORTED", "UNSUPPORTED", "UNKNOWN")),
    ("E01", "boot_outcome"): ("deployed_state", _ENUM("BOOT_OK", "FAIL", "UNKNOWN")),
    ("E01", "observed_version"): ("deployed_state", lambda v: _INT(v) or v == "UNKNOWN"),
    ("E01", "signed_image_size_bytes"): ("deployed_state", _INT),
    ("E01", "bootloader_size_bytes"): ("deployed_state", _INT),
    ("E01", "public_key_sha256"): ("deployed_state", lambda v: bool(re.fullmatch(r"[0-9a-f]{64}", str(v)))),
    ("E05", "layout_fit"): ("deployed_state", lambda v: isinstance(v, dict)
                            and set(v) == {"signed_artifact_size", "boot_slot_capacity"}),
    ("E08", "update_outcome"): ("deployed_state", _ENUM("APPLIED", "NOT_APPLIED", "UNKNOWN")),
    ("E03", "auth_negative"): ("deployed_state", _ENUM("REJECT", "ACCEPT", "UNKNOWN")),
    ("E02", "pqc_signing"): ("candidate_state", lambda v: isinstance(v, dict)
                             and set(v) == {"signing_result", "algorithm", "tool", "message"}
                             and v["signing_result"] in ("OK", "REJECTED")),
    ("X01", "cross_update_outcome"): ("transition", _ENUM("REJECTED", "APPLIED", "UNKNOWN")),
}


# ------------------------------------------------------------------ minimal JSON-schema subset


class MiniValidator:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.root = schema

    def _resolve(self, ref: str) -> dict[str, Any]:
        node: Any = self.root
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
        return node

    def errors(self, inst: Any, sch: dict[str, Any], path: str = "$") -> list[str]:
        if "$ref" in sch:
            return self.errors(inst, self._resolve(sch["$ref"]), path)
        errs: list[str] = []
        if "discriminator" in sch and isinstance(inst, dict):
            target = sch["discriminator"]["mapping"].get(inst.get(sch["discriminator"]["propertyName"]))
            if not target:
                return [f"{path}: unknown discriminator {inst.get('type')!r}"]
            return self.errors(inst, self._resolve(target), path)
        if "oneOf" in sch:
            ok = sum(1 for s in sch["oneOf"] if not self.errors(inst, s, path))
            if ok != 1:
                errs.append(f"{path}: matches {ok} of oneOf")
        if "anyOf" in sch and not any(not self.errors(inst, s, path) for s in sch["anyOf"]):
            errs.append(f"{path}: matches none of anyOf")
        t = sch.get("type")
        types = {"string": str, "integer": int, "object": dict, "array": list, "null": type(None),
                 "boolean": bool, "number": (int, float)}
        if t and not (isinstance(inst, types[t]) and not (t in ("integer", "number") and isinstance(inst, bool))):
            return errs + [f"{path}: expected {t}, got {type(inst).__name__}"]
        if "const" in sch and inst != sch["const"]:
            errs.append(f"{path}: expected const {sch['const']!r}")
        if "enum" in sch and inst not in sch["enum"]:
            errs.append(f"{path}: {inst!r} not in enum")
        if isinstance(inst, str):
            if "pattern" in sch and not re.search(sch["pattern"], inst):
                errs.append(f"{path}: pattern mismatch")
            if "maxLength" in sch and len(inst) > sch["maxLength"]:
                errs.append(f"{path}: longer than {sch['maxLength']}")
        if isinstance(inst, int) and "minimum" in sch and inst < sch["minimum"]:
            errs.append(f"{path}: below minimum")
        if isinstance(inst, list) and "items" in sch:
            for i, item in enumerate(inst):
                errs += self.errors(item, sch["items"], f"{path}[{i}]")
        if isinstance(inst, dict):
            props = sch.get("properties", {})
            for req in sch.get("required", []):
                if req not in inst:
                    errs.append(f"{path}: missing {req}")
            for k, v in inst.items():
                if k in props:
                    errs += self.errors(v, props[k], f"{path}.{k}")
                elif sch.get("additionalProperties") is False:
                    errs.append(f"{path}: unexpected property {k}")
                elif isinstance(sch.get("additionalProperties"), dict):
                    errs += self.errors(v, sch["additionalProperties"], f"{path}.{k}")
        return errs


def make_validator() -> Any:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    try:
        import jsonschema  # type: ignore

        v = jsonschema.Draft202012Validator(schema)
        return "jsonschema", lambda ev: [e.message for e in v.iter_errors({"event": ev})]
    except ImportError:
        mv = MiniValidator(schema)
        return "builtin", lambda ev: mv.errors({"event": ev}, schema)


# ------------------------------------------------------------------ main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:18080")
    ap.add_argument("--data-dir", help="host path mounted as /data (enables artifact hash checks)")
    ap.add_argument("--templates", nargs="*", default=TEMPLATES)
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument("--save", help="write the raw NDJSON stream to this file")
    args = ap.parse_args()

    run_id = datetime.now(timezone.utc).strftime("RP-%Y%m%dT%H%M%SZ-") + secrets.token_hex(3)
    request = {
        "run_id": run_id,
        "profile_id": "nrf52840-mcuboot-pqc",
        "change_id": "ecdsa_p256_to_mldsa",
        "tests": [{"template_id": t} for t in args.templates],
        "artifact_dir": f"/data/runs/{run_id}/artifacts",
        "timeout_seconds": args.timeout,
    }
    vname, validate = make_validator()
    with urllib.request.urlopen(args.url.rstrip("/") + "/health", timeout=30) as resp:
        health = json.load(resp)
    print(f"health: {health.get('status')} family={health.get('family')} templates={len(health.get('templates', []))}")
    req = urllib.request.Request(
        args.url.rstrip("/") + "/execute", data=json.dumps(request).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    started = time.monotonic()
    events: list[dict[str, Any]] = []
    invalid: list[str] = []
    raw = open(args.save, "w", encoding="utf-8") if args.save else None
    with urllib.request.urlopen(req, timeout=args.timeout + 60) as resp:
        for line in resp:
            if not line.strip():
                continue
            if raw:
                raw.write(line.decode())
            ev = json.loads(line)
            errs = validate(ev)
            if errs:
                invalid.append(f"seq={ev.get('seq')} type={ev.get('type')}: {errs[:3]}")
            events.append(ev)
            if ev["type"] == "stage":
                print(f"[{time.monotonic() - started:6.1f}s] stage {ev['stage']} {ev['status']} {ev.get('message', '')}")
            elif ev["type"] == "test_result":
                print(f"[{time.monotonic() - started:6.1f}s] {ev['test_id']} {ev['template_id']}: {ev['outcome']} "
                      f"({ev['duration_ms']} ms) {ev['observed'][:220]}")
            elif ev["type"] == "error":
                print(f"[{time.monotonic() - started:6.1f}s] ERROR {ev['failure_class']}: {ev['message'][:300]}")
    if raw:
        raw.close()
    elapsed = time.monotonic() - started

    problems: list[str] = list(invalid)
    seqs = [e["seq"] for e in events]
    if seqs != list(range(len(seqs))):
        problems.append("seq is not 0..n-1 contiguous")
    obs = [e["observation"] for e in events if e["type"] == "observation"]
    ids = [o["observation_id"] for o in obs]
    if len(ids) != len(set(ids)):
        problems.append("duplicate observation ids")
    artifacts = {e["artifact_id"]: e for e in events if e["type"] == "artifact"}
    for o in obs:
        key = (o["test_id"], o["fact"])
        if o["observation_id"] != f"OBS-{o['test_id']}-{o['fact']}":
            problems.append(f"bad observation id {o['observation_id']}")
        if key not in FACTS:
            problems.append(f"fact not in WORKSTREAMS vocabulary: {key}")
            continue
        subject, check = FACTS[key]
        if o["subject"] != subject:
            problems.append(f"{key}: subject {o['subject']} != {subject}")
        if not check(o["value"]):
            problems.append(f"{key}: value not allowed: {o['value']!r}")
        for aid in o["source_artifact_ids"]:
            if aid not in artifacts:
                problems.append(f"{key}: unknown source artifact {aid}")
    for tr in (e for e in events if e["type"] == "test_result"):
        for oid in tr["observation_ids"]:
            if oid not in ids:
                problems.append(f"{tr['test_id']}: test_result references unknown {oid}")
    if args.data_dir:
        base = Path(args.data_dir) / "runs" / run_id / "artifacts"
        for a in artifacts.values():
            p = base / a["path"]
            if not p.exists():
                problems.append(f"artifact missing on host: {a['path']}")
            elif hashlib.sha256(p.read_bytes()).hexdigest() != a["sha256"]:
                problems.append(f"artifact hash mismatch: {a['path']}")
    done = [e for e in events if e["type"] == "done"]
    status = done[-1]["status"] if done else "NO_DONE_EVENT"

    print("\n=== summary ===")
    print(f"run_id={run_id} status={status} elapsed={elapsed:.1f}s events={len(events)} "
          f"observations={len(obs)} artifacts={len(artifacts)} validator={vname}")
    for tr in (e for e in events if e["type"] == "test_result"):
        print(f"  {tr['test_id']:4} {tr['outcome']:13} {tr['template_id']}")
    for o in obs:
        print(f"  {o['observation_id']:36} = {json.dumps(o['value'])[:160]}")
    if done:
        print(f"source_pins={json.dumps(done[-1].get('source_pins'))}")
        print(f"tool_versions={json.dumps(done[-1].get('tool_versions'))}")
    if problems:
        print(f"\n{len(problems)} PROBLEM(S):")
        for p in problems[:50]:
            print("  - " + p)
    return 0 if status == "SUCCEEDED" and not problems else 1


if __name__ == "__main__":
    sys.exit(main())
