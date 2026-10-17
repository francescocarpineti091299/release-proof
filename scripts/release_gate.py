"""Download an evidence pack and apply the strict CI preflight gate (no new AI calls)."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlsplit
from zipfile import BadZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from releaseproof.api.evidence_pack import MAX_PACK_BYTES  # noqa: E402
from releaseproof.release_gate import release_decision, verify_pack  # noqa: E402


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward judge credentials to another host/path.


def download_pack(base: str, run_id: str, out: Path) -> None:
    parsed = urlsplit(base)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("base must be an HTTP(S) origin without credentials or path")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("HTTPS is required outside localhost")
    if (
        not run_id
        or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for c in run_id
        )
        or len(run_id) > 160
    ):
        raise ValueError("invalid run id")
    headers = {"Accept": "application/zip"}
    user, password = os.getenv("RELEASEPROOF_DEMO_USER"), os.getenv("RELEASEPROOF_DEMO_PASSWORD")
    if bool(user) != bool(password):
        raise ValueError("both demo credential environment variables are required")
    if user and password:
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/assessments/{quote(run_id, safe='')}/evidence-pack",
        headers=headers,
    )
    # Exclusive creation avoids overwriting an earlier evidence pack or user data.
    with (
        urllib.request.build_opener(NoRedirect).open(req, timeout=120) as response,
        out.open("xb") as target,
    ):
        size = 0
        while chunk := response.read(65536):
            size += len(chunk)
            if size > MAX_PACK_BYTES + 1024 * 1024:
                raise ValueError("download exceeds evidence pack limit")
            target.write(chunk)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-id", help="download a completed run from the API")
    source.add_argument("--pack", type=Path, help="verify an existing local ZIP (offline)")
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--change", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--out", type=Path, default=Path("releaseproof-gate"))
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    report_path = args.out / "gate.json"
    if report_path.exists():
        parser.error("output already contains gate.json; choose a fresh directory")
    report = {"decision": "ERROR", "official": False}
    code = 2
    try:
        pack_path = args.pack
        if args.run_id:
            pack_path = args.out / "evidence.zip"
            download_pack(args.base, args.run_id, pack_path)
        pack = verify_pack(pack_path)
        if args.run_id and pack["run"]["run_id"] != args.run_id:
            raise ValueError("downloaded pack does not belong to the requested run")
        report = release_decision(
            pack,
            configuration=args.configuration,
            change=args.change,
            plan=args.plan,
        )
        code = 0 if report["decision"] == "PASS" else 1
    except (OSError, ValueError, TypeError, KeyError, BadZipFile, RuntimeError) as exc:
        # No endpoint URLs/headers/credentials in logs. Retain downloaded bytes for review.
        report["reasons"] = [f"Evidence verification failed ({type(exc).__name__})."]
    with report_path.open("x", encoding="utf-8") as target:
        json.dump(report, target, indent=2)
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
