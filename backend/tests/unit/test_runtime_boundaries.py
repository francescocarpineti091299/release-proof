"""Regression checks: synthetic fixtures must stay outside the shipped application."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import httpx
import pytest

import releaseproof
from releaseproof.core import projection
from releaseproof.orchestrator.deps import Deps, InjectedDependencyRefused
from releaseproof.orchestrator.service import Orchestrator
from releaseproof.orchestrator.settings import Settings
from releaseproof.store.db import Store


@pytest.mark.parametrize(
    "module", ["releaseproof.ai.stub", "releaseproof.core.projection.scenarios"]
)
def test_synthetic_modules_are_not_in_runtime_package(module):
    assert importlib.util.find_spec(module) is None


def test_projection_does_not_export_demo_catalog():
    assert not hasattr(projection, "build_assessment_by_id")
    assert not hasattr(projection, "list_scenario_descriptors")
    assert callable(projection.build_wp0_baseline_assessment)


def test_runtime_does_not_import_test_fixtures():
    root = Path(releaseproof.__file__).parent
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            for module in modules:
                assert module.split(".")[0] not in {
                    "tests",
                    "rp_llm_stub",
                    "rp_scenarios",
                    "rp_fakes",
                    "adapter_facts",
                }, f"{path} imports test fixture {module}"


@pytest.mark.parametrize("env", ["dev", "demo", "production", ""])
@pytest.mark.parametrize("kind", ["adapter", "ai", "runner", "indexer"])
def test_orchestrator_refuses_injected_dependencies_outside_tests(tmp_path, env, kind):
    kwargs = {
        "adapter": {"adapter_factory": lambda name: None},
        "ai": {"ai_factory": lambda sink: None},
        "runner": {"runner_transport": httpx.MockTransport(lambda request: httpx.Response(200))},
        "indexer": {"evidence_indexer": lambda **kw: {}},
    }[kind]
    store = Store(tmp_path / "test.sqlite")
    try:
        with pytest.raises(InjectedDependencyRefused, match="RELEASEPROOF_ENV=test"):
            Orchestrator(store=store, settings=Settings(env=env), deps=Deps(**kwargs))
    finally:
        store.close()


def test_test_environment_still_allows_fakes():
    deps = Deps(ai_factory=lambda sink: None)
    deps.check_environment("test")


@pytest.mark.parametrize("env", ["dev", "demo", "production", "test"])
def test_default_dependencies_are_allowed_and_have_no_mock_transport(env):
    deps = Deps()
    deps.check_environment(env)
    assert deps.runner_transport is None
