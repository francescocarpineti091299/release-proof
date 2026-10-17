"""Server-sent events: replay persisted events after Last-Event-ID, then follow live."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from starlette.concurrency import run_in_threadpool

from releaseproof.contracts.api import RunStatus, SSEEvent
from releaseproof.orchestrator.service import Orchestrator
from releaseproof.store.db import EventRow

_TERMINAL = {RunStatus.SUCCEEDED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value}
_BATCH = 500
MAX_EVENT_ID = (1 << 63) - 1  # SQLite INTEGER range


def format_event(row: EventRow) -> str:
    payload = SSEEvent(id=row.id, type=row.type, data=row.data).model_dump_json()
    return f"id: {row.id}\nevent: {row.type}\ndata: {payload}\n\n"


def _is_terminal_event(row: EventRow) -> bool:
    return row.type == "run" and row.data.get("status") in _TERMINAL


async def event_stream(
    orchestrator: Orchestrator, run_id: str, *, after: int, heartbeat: float
) -> AsyncIterator[str]:
    store = orchestrator.store
    sub = orchestrator.bus.subscribe(run_id)  # subscribe before replay: no gap
    last = after
    try:
        yield "retry: 3000\n\n"
        while True:
            rows = await run_in_threadpool(store.list_events, run_id, after=last, limit=_BATCH)
            for row in rows:
                last = row.id
                yield format_event(row)
                if _is_terminal_event(row):
                    return
            if len(rows) < _BATCH:
                break
        while True:
            try:
                row = await asyncio.wait_for(sub.queue.get(), timeout=heartbeat)
            except TimeoutError:
                yield ": heartbeat\n\n"
                # Safety net: catch up from the store and stop once the run is over.
                rows = await run_in_threadpool(store.list_events, run_id, after=last, limit=_BATCH)
                for missed in rows:
                    last = missed.id
                    yield format_event(missed)
                    if _is_terminal_event(missed):
                        return
                run = await run_in_threadpool(store.get_run, run_id)
                if not rows and (run is None or run["status"] in _TERMINAL):
                    return
                continue
            if row.id <= last:
                continue
            last = row.id
            yield format_event(row)
            if _is_terminal_event(row):
                return
    finally:
        orchestrator.bus.unsubscribe(sub)


def parse_last_event_id(header: str | None, after: int | None) -> int:
    for candidate in (header, after):
        if candidate is None or candidate == "":
            continue
        try:
            return min(MAX_EVENT_ID, max(0, int(candidate)))
        except (TypeError, ValueError):
            continue
    return 0


__all__ = ["event_stream", "format_event", "parse_last_event_id"]
