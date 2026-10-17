"""Subprocess execution with streaming, timeouts and process-group kill (POSIX)."""

from __future__ import annotations

import math
import os
import signal
import subprocess
import threading
import time
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

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
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout_s must be finite and positive")
    if echo_every < 1:
        raise ValueError("echo_every must be positive")
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
            timer.join()
            # Also reap descendants when the parent has already exited. They
            # may retain the output pipe or survive a sink/read exception.
            kill_group(proc)
            proc.wait()
            proc.stdout.close()
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
    if os.name == "nt":
        # taskkill /T addresses descendants as well as the immediate child.
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if proc.poll() is None:
            proc.kill()
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    # Waiting only for the leader is insufficient: a descendant can ignore
    # SIGTERM and keep stdout open even after the leader exits.
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.02)
    with suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)


def tool_version(argv: Sequence[str], *, first_line_only: bool = True) -> str:
    try:
        completed = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=30, check=False
        )
        out = completed.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "UNAVAILABLE"
    if completed.returncode != 0 or not out:
        return "UNAVAILABLE"
    return out.splitlines()[0].strip() if first_line_only else out
