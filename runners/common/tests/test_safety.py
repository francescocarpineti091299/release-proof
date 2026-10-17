"""Offline runner regressions: python -m unittest discover -s runners/common/tests."""

import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from rp_runner.engine import Family, Template, TemplateResult, execute
from rp_runner.proc import run_cmd, tool_version
from rp_runner.server import create_server, validate_request


class FakeTemplate(Template):
    template_id = "offline.test"
    test_id = "E01"

    def __init__(self, outcome):
        self.outcome = outcome

    def run(self, ctx):
        return TemplateResult(self.outcome, "offline regression")


class FakeFamily(Family):
    name = "offline"

    def __init__(self, outcome="PASS"):
        self.templates = {"offline.test": FakeTemplate(outcome)}

    def prepare(self, ctx):
        pass


class RunnerSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.request = {
            "run_id": "run-1",
            "profile_id": "profile",
            "change_id": "change",
            "tests": [{"template_id": "offline.test"}],
            "artifact_dir": str(self.root / "runs" / "run-1" / "artifacts"),
        }

    def test_valid_request(self):
        self.assertEqual(
            validate_request(self.request, FakeFamily(), self.root)["timeout_seconds"], 900
        )

    def test_invalid_requests(self):
        cases = [
            [],
            None,
            {**self.request, "run_id": "../escape"},
            {**self.request, "tests": []},
            {**self.request, "tests": [None]},
            {**self.request, "tests": [{"template_id": "unknown"}]},
            {**self.request, "tests": self.request["tests"] * 2},
            {**self.request, "tests": [{"template_id": "offline.test", "params": []}]},
            {**self.request, "timeout_seconds": True},
            {**self.request, "timeout_seconds": -1},
            {**self.request, "artifact_dir": str(self.root / "runs" / "other" / "artifacts")},
        ]
        for request in cases:
            with self.subTest(request=request), self.assertRaises(ValueError):
                validate_request(request, FakeFamily(), self.root)

    def test_existing_evidence_rejected(self):
        directory = Path(self.request["artifact_dir"])
        directory.mkdir(parents=True)
        evidence = directory / "uart.log"
        evidence.write_text("previous evidence")
        with self.assertRaises(ValueError):
            validate_request(self.request, FakeFamily(), self.root)
        self.assertEqual(evidence.read_text(), "previous evidence")

    def test_run_status_distinguishes_results_from_execution_errors(self):
        for outcome, expected in [
            ("PASS", "SUCCEEDED"),
            ("FAIL", "SUCCEEDED"),
            ("INCONCLUSIVE", "SUCCEEDED"),
            ("ERROR", "FAILED"),
        ]:
            with self.subTest(outcome=outcome):
                events = []
                status = execute(FakeFamily(outcome), self.request, events.append)
                self.assertEqual(status, expected)
                self.assertEqual(json.loads(events[-1])["status"], expected)

    def test_cancelled_execution_is_not_success(self):
        events = []
        self.assertEqual(
            execute(FakeFamily(), self.request, events.append, cancelled=lambda: True), "FAILED"
        )
        results = [json.loads(e) for e in events if json.loads(e)["type"] == "test_result"]
        self.assertEqual(results[0]["outcome"], "NOT_EXECUTED")
        work_root = self.root / "workspaces"
        work_root.mkdir()

        def broken_on_done(line):
            if json.loads(line)["type"] == "done":
                raise RuntimeError("connection lost")

        with self.assertRaises(RuntimeError):
            execute(FakeFamily(), self.request, broken_on_done, work_root=work_root)
        self.assertEqual(list(work_root.iterdir()), [])

    def test_command_success_and_failure(self):
        for code in (0, 3):
            result = run_cmd(
                [sys.executable, "-c", f"print('output'); raise SystemExit({code})"],
                cwd=self.root,
                log_path=self.root / "cmd.log",
                timeout_s=5,
            )
            self.assertEqual(result.ok, code == 0)
            self.assertIn("output", result.log_path.read_text())

        class BrokenSink:
            def log(self, *args, **kwargs):
                raise RuntimeError("sink failed")

        started = time.monotonic()
        with self.assertRaises(RuntimeError):
            run_cmd(
                [sys.executable, "-c", "import time; print('line', flush=True); time.sleep(30)"],
                cwd=self.root,
                log_path=self.root / "sink-error.log",
                timeout_s=10,
                sink=BrokenSink(),
            )
        self.assertLess(time.monotonic() - started, 5)

    def test_command_timeout(self):
        started = time.monotonic()
        result = run_cmd(
            [sys.executable, "-c", "import time; print('partial', flush=True); time.sleep(30)"],
            cwd=self.root,
            log_path=self.root / "timeout.log",
            timeout_s=0.2,
        )
        self.assertTrue(result.timed_out)
        self.assertFalse(result.ok)
        self.assertLess(time.monotonic() - started, 10)

    def test_invalid_process_options(self):
        for kwargs in ({"timeout_s": 0}, {"timeout_s": float("nan")}, {"echo_every": 0}):
            with self.assertRaises(ValueError):
                run_cmd([sys.executable], cwd=self.root, log_path=self.root / "bad.log", **kwargs)

    def test_failed_version_probe_is_unavailable(self):
        with patch(
            "rp_runner.proc.subprocess.run",
            return_value=subprocess.CompletedProcess([], 2, "fake version"),
        ):
            self.assertEqual(tool_version(["tool"]), "UNAVAILABLE")

    @unittest.skipIf(os.name == "nt", "POSIX process-group semantics")
    def test_term_resistant_descendant_is_killed_after_leader_exits(self):
        code = (
            "import subprocess,sys; subprocess.Popen([sys.executable,'-c',"
            "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)'])"
        )
        started = time.monotonic()
        result = run_cmd(
            [sys.executable, "-c", code],
            cwd=self.root,
            log_path=self.root / "descendant.log",
            timeout_s=0.5,
        )
        self.assertTrue(result.timed_out)
        self.assertLess(time.monotonic() - started, 5)

    @unittest.skipIf(os.name == "nt", "symlinks require extra Windows privileges")
    def test_symlink_redirect_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "runs").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            validate_request(self.request, FakeFamily(), self.root)


class HttpSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with patch.dict(os.environ, {"RELEASEPROOF_DATA_DIR": str(self.root)}):
            self.server = create_server(FakeFamily(), "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def post(self, body, headers=None):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        self.addCleanup(conn.close)
        conn.request("POST", "/execute", body=body, headers=headers or {})
        response = conn.getresponse()
        return response.status, response.read()

    def test_invalid_json_shapes_are_400_not_handler_crashes(self):
        for body in (b"[]", b"null", b"{broken"):
            with self.subTest(body=body):
                status, _ = self.post(body)
                self.assertEqual(status, 400)

    def test_body_size_limit(self):
        status, _ = self.post(b"{}", {"Content-Length": str((1 << 20) + 1)})
        self.assertEqual(status, 400)

    def test_valid_request_streams_chunked_events(self):
        request = {
            "run_id": "http-run",
            "profile_id": "profile",
            "change_id": "change",
            "artifact_dir": str(self.root / "runs" / "http-run" / "artifacts"),
            "tests": [{"template_id": "offline.test"}],
        }
        status, body = self.post(json.dumps(request).encode())
        self.assertEqual(status, 200)
        events = [json.loads(line) for line in body.splitlines()]
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["status"], "SUCCEEDED")
        self.assertEqual([e["seq"] for e in events], list(range(len(events))))


if __name__ == "__main__":
    unittest.main()
