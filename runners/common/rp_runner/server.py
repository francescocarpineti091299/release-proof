"""Minimal HTTP server exposing a runner family (stdlib only).

  GET  /health   -> {"status": "ok", "family": ..., "busy": bool, "tool_versions": {...}}
  POST /execute  -> chunked application/x-ndjson stream of runner events
                    409 if a run is already executing on this runner
"""

from __future__ import annotations

import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from rp_runner.engine import Family, execute

_REQUIRED = ("run_id", "profile_id", "change_id", "tests", "artifact_dir")
_MAX_BODY = 1 << 20


def validate_request(request: Any, family: Family, artifact_root: Path) -> dict[str, Any]:
    """Reject malformed plans and cross-run writes before starting an event stream."""
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    missing = [k for k in _REQUIRED if k not in request]
    if missing:
        raise ValueError(f"missing fields: {missing}")
    run_id = request["run_id"]
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", run_id):
        raise ValueError("invalid run_id")
    for key in ("profile_id", "change_id", "artifact_dir"):
        if not isinstance(request[key], str) or not request[key]:
            raise ValueError(f"{key} must be a nonempty string")
    tests = request["tests"]
    if not isinstance(tests, list) or not tests or len(tests) > 256:
        raise ValueError("tests must be a nonempty list of at most 256 templates")
    seen = set()
    for test in tests:
        if not isinstance(test, dict) or not isinstance(test.get("template_id"), str):
            raise ValueError("each test must specify a template_id")
        tid = test["template_id"]
        if tid not in family.templates or tid in seen:
            raise ValueError(f"unknown or duplicate template_id: {tid}")
        seen.add(tid)
        if "params" in test and not isinstance(test["params"], dict):
            raise ValueError("test params must be an object")
    timeout = request.get("timeout_seconds", 900)
    if type(timeout) is not int or not 1 <= timeout <= 86400:
        raise ValueError("timeout_seconds must be an integer between 1 and 86400")
    root = artifact_root.resolve()
    expected = root / "runs" / run_id / "artifacts"
    artifact_dir = Path(request["artifact_dir"]).resolve()
    if artifact_dir != expected or root not in artifact_dir.parents:
        raise ValueError("artifact_dir must be data/runs/<run_id>/artifacts (without symlink redirects)")
    if artifact_dir.exists() and (not artifact_dir.is_dir() or any(artifact_dir.iterdir())):
        raise ValueError("artifact_dir must be empty; existing evidence cannot be overwritten")
    return {**request, "artifact_dir": str(artifact_dir), "timeout_seconds": timeout}


def create_server(family: Family, host: str = "0.0.0.0", port: int | None = None) -> ThreadingHTTPServer:
    """Construct a server; separated from serve_forever for offline HTTP tests."""
    port = port if port is not None else int(os.environ.get("RUNNER_PORT", "8080"))
    lock = threading.Lock()
    artifact_root = Path(os.environ.get("RELEASEPROOF_DATA_DIR", "/data")).resolve()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:  # quieter access log
            print(f"[{family.name}-runner] " + fmt % args, flush=True)

        def _json(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/health":
                self._json(404, {"error": "not found"})
                return
            self._json(
                200,
                {
                    "status": "ok",
                    "family": family.name,
                    "busy": lock.locked(),
                    "tool_versions": family.tool_versions(),
                    "source_pins": family.source_pins(),
                    "templates": sorted(family.templates),
                },
            )

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/execute":
                self._json(404, {"error": "not found"})
                return
            # Close rejected requests: unread bodies must not be reinterpreted
            # as a second HTTP/1.1 request on this connection.
            self.close_connection = True
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("Transfer-Encoding is not supported")
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or not re.fullmatch(r"[0-9]+", lengths[0]):
                    raise ValueError("one valid Content-Length is required")
                length = int(lengths[0])
                if not 0 < length <= _MAX_BODY:
                    raise ValueError("request body must be between 1 byte and 1 MiB")
                self.connection.settimeout(30)
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError("incomplete request body")
                request = json.loads(body)
                request = validate_request(request, family, artifact_root)
            except (ValueError, OSError, UnicodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            if not lock.acquire(blocking=False):
                self._json(409, {"error": "runner busy"})
                return
            try:
                # Recheck under the execution lock to prevent concurrent replays.
                try:
                    request = validate_request(request, family, artifact_root)
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                broken = threading.Event()

                def write(line: str) -> None:
                    if broken.is_set():
                        return
                    data = line.encode()
                    try:
                        self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
                        self.wfile.flush()
                    except OSError:
                        broken.set()

                execute(family, request, write, cancelled=broken.is_set)
                if not broken.is_set():
                    try:
                        self.wfile.write(b"0\r\n\r\n")
                        self.wfile.flush()
                    except OSError:
                        pass
            finally:
                lock.release()

    return ThreadingHTTPServer((host, port), Handler)


def serve(family: Family, host: str = "0.0.0.0", port: int | None = None) -> None:
    server = create_server(family, host, port)
    print(f"[{family.name}-runner] listening on {host}:{server.server_address[1]}", flush=True)
    server.serve_forever()
