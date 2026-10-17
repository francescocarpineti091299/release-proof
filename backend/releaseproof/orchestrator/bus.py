"""In-memory pub/sub of persisted run events (worker threads -> asyncio SSE subscribers)."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from dataclasses import dataclass

from releaseproof.store.db import EventRow


@dataclass(eq=False)
class Subscription:
    run_id: str
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[EventRow]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[Subscription]] = {}
        self._lock = threading.Lock()

    def subscribe(self, run_id: str) -> Subscription:
        sub = Subscription(run_id, asyncio.get_running_loop(), asyncio.Queue())
        with self._lock:
            self._subs.setdefault(run_id, set()).add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            subs = self._subs.get(sub.run_id)
            if subs is not None:
                subs.discard(sub)
                if not subs:
                    del self._subs[sub.run_id]

    def publish(self, event: EventRow) -> None:
        with self._lock:
            subs = list(self._subs.get(event.run_id, ()))
        for sub in subs:
            with contextlib.suppress(RuntimeError):  # loop closed: subscriber is gone
                sub.loop.call_soon_threadsafe(sub.queue.put_nowait, event)

    def subscriber_count(self, run_id: str) -> int:
        with self._lock:
            return len(self._subs.get(run_id, ()))
