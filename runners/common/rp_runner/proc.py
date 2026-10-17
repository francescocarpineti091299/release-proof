"""Subprocess execution with streaming, timeouts and process-group kill (POSIX)."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from rp_runner.events import EventSink


@dataclass
class CmdResult:
    argv: list[str]
    returncode: int | None
    timed_out: bool
    duration_ms: int
    log_path: Path

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def run_cmd(
    argv: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    sink: EventSink | None = None,
    stream: str = "build",
    test_id: str | None = None,
    env: dict[str, str] | None = None,
    timeout_s: float = 600,
    echo_every: int = 1,
) -> CmdResult:
    """Run ``argv`` (never through a shell), tee merged output to ``log_path`` and the sink.

    ``echo_every`` > 1 forwards only every n-th line to the sink (the log file keeps all).
    """
    argv = [str(a) for a in argv]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    full_env = {**os.environ, **(env or {})}
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("$ " + " ".join(argv) + "\n")
        log.flush()
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=full_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            text=True,
            errors="replace",
            bufsize=1,
        )
        timed_out = threading.Event()

        def _kill() -> None:
            timed_out.set()
            kill_group(proc)

        timer = threading.Timer(timeout_s, _kill)
        timer.start()
        try:
            assert proc.stdout is not None
            for n, line in enumerate(proc.stdout):
                log.write(line)
                if sink is not None and n % echo_every == 0:
                    sink.log(stream, line.rstrip("\n"), test_id=test_id)
            proc.wait()
        finally:
            timer.cancel()
            if proc.poll() is None:
                kill_group(proc)
        if timed_out.is_set():
            log.write(f"\n[releaseproof] TIMEOUT after {timeout_s}s; process group killed\n")
    return CmdResult(
        argv=argv,
        returncode=None if timed_out.is_set() else proc.returncode,
        timed_out=timed_out.is_set(),
        duration_ms=int((time.monotonic() - started) * 1000),
        log_path=log_path,
    )


def kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def tool_version(argv: Sequence[str], *, first_line_only: bool = True) -> str:
    try:
        out = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=30, check=False
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "UNAVAILABLE"
    if not out:
        return "UNAVAILABLE"
    return out.splitlines()[0].strip() if first_line_only else out
