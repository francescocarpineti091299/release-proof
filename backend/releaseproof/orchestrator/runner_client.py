"""HTTP/NDJSON client of a runner family (``POST {RUNNER_URL}/execute``).

Every line is validated against ``RunnerEventEnvelope`` plus protocol invariants (run id, strictly
increasing seq, safe artifact paths, nothing after ``done``, stream must end with ``done``).
Any violation, transport error or timeout raises :class:`RunnerFailure`; the caller fails the run
and never evaluates it.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import PurePosixPath

import httpx
from pydantic import ValidationError

from releaseproof.contracts.runner import (
    ArtifactEvent,
    DoneEvent,
    FailureClass,
    RunnerEvent,
    RunnerEventEnvelope,
    RunnerRequest,
)


class RunnerFailure(Exception):
    def __init__(self, failure_class: FailureClass, message: str) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.message = message


class InvalidRunnerEvent(RunnerFailure):
    def __init__(self, message: str) -> None:
        super().__init__(FailureClass.TOOL_FAILURE, f"invalid runner event: {message}")


def safe_relative_path(path: str) -> bool:
    if not path or "\\" in path or "\x00" in path:
        return False
    pure = PurePosixPath(path)
    return not pure.is_absolute() and ".." not in pure.parts and ":" not in pure.parts[0]


def parse_event_line(line: str) -> RunnerEvent:
    try:
        payload = json.loads(line)
        return RunnerEventEnvelope.model_validate({"event": payload}).event
    except (ValueError, ValidationError) as exc:
        raise InvalidRunnerEvent(str(exc)[:600]) from exc


class _ProtocolChecker:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.last_seq = -1
        self.done: DoneEvent | None = None

    def check(self, event: RunnerEvent) -> None:
        if self.done is not None:
            raise InvalidRunnerEvent(f"event seq={event.seq} after done")
        if event.run_id != self.run_id:
            raise InvalidRunnerEvent(f"run_id {event.run_id!r} != {self.run_id!r}")
        if event.seq <= self.last_seq:
            raise InvalidRunnerEvent(f"seq {event.seq} not increasing (last {self.last_seq})")
        self.last_seq = event.seq
        if isinstance(event, ArtifactEvent) and not safe_relative_path(event.path):
            raise InvalidRunnerEvent(f"artifact path {event.path!r} escapes the artifact dir")
        if isinstance(event, DoneEvent):
            self.done = event


class RunnerClient:
    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        connect_timeout: float = 10.0,
        grace_seconds: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.connect_timeout = connect_timeout
        self.grace_seconds = grace_seconds

    def execute(self, request: RunnerRequest) -> Iterator[RunnerEvent]:
        budget = request.timeout_seconds + self.grace_seconds
        deadline = time.monotonic() + budget
        timeout = httpx.Timeout(connect=self.connect_timeout, read=budget, write=30.0, pool=30.0)
        checker = _ProtocolChecker(request.run_id)
        try:
            with (
                httpx.Client(
                    base_url=self.base_url,
                    transport=self.transport,
                    timeout=timeout,
                    trust_env=False,  # internal network: never route runner traffic via a proxy
                ) as client,
                client.stream("POST", "/execute", json=request.model_dump(mode="json")) as response,
            ):
                if response.status_code != 200:
                    body = response.read()[:500].decode("utf-8", "replace")
                    failure = (
                        FailureClass.ENVIRONMENT_SETUP
                        if response.status_code == 409
                        else FailureClass.TOOL_FAILURE
                    )
                    raise RunnerFailure(failure, f"runner HTTP {response.status_code}: {body}")
                for line in response.iter_lines():
                    if time.monotonic() > deadline:
                        raise RunnerFailure(FailureClass.TIMEOUT, f"runner exceeded {budget}s")
                    if not line.strip():
                        continue
                    event = parse_event_line(line)
                    checker.check(event)
                    yield event
        except httpx.TimeoutException as exc:
            raise RunnerFailure(FailureClass.TIMEOUT, f"runner timeout: {exc}") from exc
        except httpx.ConnectError as exc:
            raise RunnerFailure(
                FailureClass.ENVIRONMENT_SETUP, f"runner unreachable at {self.base_url}: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RunnerFailure(
                FailureClass.TOOL_FAILURE, f"runner transport error: {type(exc).__name__}: {exc}"
            ) from exc
        if checker.done is None:
            raise RunnerFailure(FailureClass.TOOL_FAILURE, "runner stream ended without done event")
