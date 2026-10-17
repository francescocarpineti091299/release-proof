from __future__ import annotations

from typing import Any

import pytest

from releaseproof.contracts.api import AITraceView
from releaseproof.core.assurance.service import evaluate
from releaseproof.core.projection.wp0 import build_wp0_baseline_assessment
from releaseproof.profiles.registry import get_template, load_profiles


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELEASEPROOF_ENV", "test")


class TraceCollector(list):
    def __call__(self, trace: AITraceView) -> None:
        self.append(trace)

    @property
    def statuses(self) -> list[str]:
        return [str(t.status) for t in self]


@pytest.fixture
def traces() -> TraceCollector:
    return TraceCollector()


def _profile_bundle(profile_id: str) -> dict[str, Any]:
    profile = load_profiles()[profile_id]
    change = profile.changes[0]
    templates = [get_template(t) for t in [*change.required_templates, *change.optional_templates]]
    return {"profile": profile, "change": change, "templates": templates}


@pytest.fixture
def wolfboot() -> dict[str, Any]:
    return _profile_bundle("nrf52840-wolfboot-pqc")


@pytest.fixture
def mcuboot() -> dict[str, Any]:
    return _profile_bundle("nrf52840-mcuboot-pqc")


@pytest.fixture(scope="session")
def freeze() -> dict[str, Any]:
    assessment = build_wp0_baseline_assessment()
    result = evaluate(assessment).model_dump(mode="json")
    tests = [
        {
            "test_id": "E01",
            "template_id": "wolfboot.boot_current",
            "outcome": "PASS",
            "negative": False,
            "expected": "Version 1 boots",
            "observed": "UART: wolfBoot v1 BOOT_OK",
        },
        {
            "test_id": "E03",
            "template_id": "wolfboot.tampered_image_rejected",
            "outcome": "PASS",
            "negative": True,
            "expected": "Tampered image rejected",
            "observed": "UART: panic, image rejected",
        },
    ]
    return {"assessment": assessment, "result": result, "test_results": tests}
