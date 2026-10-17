import pytest
from fastapi import HTTPException

from releaseproof.api.budget import MutationBudget


def test_global_demo_budget_is_bounded_and_recovers(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("releaseproof.api.budget.time.monotonic", lambda: clock[0])
    budget = MutationBudget(2)
    budget.admit()
    budget.admit()
    with pytest.raises(HTTPException) as exc:
        budget.admit()
    assert exc.value.status_code == 429
    clock[0] = 61.0
    budget.admit()
