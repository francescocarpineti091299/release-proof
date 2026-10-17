"""Single-instance demo request budget. Global, not a spoofable per-IP quota."""

import threading
import time
from collections import deque

from fastapi import HTTPException, Request


class MutationBudget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._lock = threading.Lock()
        self._requests: deque[float] = deque()

    def admit(self) -> None:
        now = time.monotonic()
        with self._lock:
            while self._requests and self._requests[0] <= now - 60:
                self._requests.popleft()
            if len(self._requests) >= self.limit:
                raise HTTPException(
                    429,
                    "demo request budget exhausted; retry later",
                    headers={"Retry-After": "60"},
                )
            self._requests.append(now)


def mutation_budget(request: Request) -> None:
    if request.method == "POST":
        request.app.state.mutation_budget.admit()
