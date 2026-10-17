"""Minimal HTTP server exposing a runner family (stdlib only).

  GET  /health   -> {"status": "ok", "family": ..., "busy": bool, "tool_versions": {...}}
  POST /execute  -> chunked application/x-ndjson stream of runner events
                    409 if a run is already executing on this runner
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from rp_runner.engine import Family, execute

_REQUIRED = ("run_id", "profile_id", "change_id", "tests", "artifact_dir")


def serve(family: Family, host: str = "0.0.0.0", port: int | None = None) -> None:
    port = port or int(os.environ.get("RUNNER_PORT", "8080"))
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
            length = int(self.headers.get("Content-Length") or 0)
            try:
                request = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._json(400, {"error": "invalid JSON"})
                return
            missing = [k for k in _REQUIRED if k not in request]
            if missing:
                self._json(400, {"error": f"missing fields: {missing}"})
                return
            artifact_dir = Path(request["artifact_dir"]).resolve()
            if artifact_root not in artifact_dir.parents:
                self._json(400, {"error": "artifact_dir outside data volume"})
                return
            if not lock.acquire(blocking=False):
                self._json(409, {"error": "runner busy"})
                return
            try:
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
                    except (BrokenPipeError, ConnectionResetError):
                        broken.set()

                execute(family, request, write, cancelled=broken.is_set)
                if not broken.is_set():
                    try:
                        self.wfile.write(b"0\r\n\r\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
            finally:
                lock.release()

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"[{family.name}-runner] listening on {host}:{port}", flush=True)
    server.serve_forever()
