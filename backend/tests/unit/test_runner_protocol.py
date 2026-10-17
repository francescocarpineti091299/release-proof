"""The shared runner engine emits only events that the backend contract accepts."""

import json
import sys
from pathlib import Path

from releaseproof.contracts.runner import RunnerEventEnvelope

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "runners" / "common"))

from rp_runner.engine import (  # noqa: E402
    BuildFailed,
    Family,
    Template,
    TemplateResult,
    execute,
)


class _Discover(Template):
    template_id = "fake.discover"
    test_id = "D01"
    phase = "DISCOVERY"
    expected = "pins"

    def run(self, ctx):
        path = ctx.artifact_path("discovery", "pins.json")
        path.write_text("{}")
        aid = ctx.sink.artifact(path, kind="config", test_id="D01")
        oid = ctx.sink.observation(
            observation_id="OBS-D01-PIN",
            test_id="D01",
            subject="toolchain",
            fact="bootloader_commit",
            value="abc",
            origin="MEASURED_TOOL",
            acquisition_mode="REPOSITORY",
            parser="fake@1",
            source_artifact_ids=[aid],
        )
        return TemplateResult("PASS", "recorded", [oid])


class _Boot(Template):
    template_id = "fake.boot"
    test_id = "E01"
    expected = "boots"

    def build(self, ctx):
        ctx.cache["built"] = True

    def run(self, ctx):
        assert ctx.cache["built"]
        return TemplateResult("PASS", "version=1")


class _BrokenBuild(Template):
    template_id = "fake.broken"
    test_id = "O05"
    expected = "build outcome"

    def build(self, ctx):
        raise BuildFailed("macro redefinition")

    def run(self, ctx):  # pragma: no cover - never reached
        raise AssertionError


class _Fam(Family):
    name = "fake"
    templates = {t.template_id: t for t in (_Discover(), _Boot(), _BrokenBuild())}

    def prepare(self, ctx):
        return None


def _run(tmp_path, template_ids):
    lines: list[str] = []
    request = {
        "run_id": "RP-test-0001",
        "profile_id": "p",
        "change_id": "c",
        "tests": [{"template_id": t} for t in template_ids],
        "artifact_dir": str(tmp_path / "art"),
    }
    status = execute(_Fam(), request, lines.append, work_root=tmp_path)
    events = [RunnerEventEnvelope.model_validate({"event": json.loads(x)}).event for x in lines]
    return status, events


def test_all_events_match_backend_contract(tmp_path):
    status, events = _run(tmp_path, ["fake.discover", "fake.boot", "fake.broken"])
    assert status == "FAILED"
    assert [e.seq for e in events] == list(range(len(events)))
    results = {e.template_id: e for e in events if e.type == "test_result"}
    assert results["fake.boot"].outcome == "PASS"
    assert results["fake.broken"].outcome == "ERROR"
    assert results["fake.broken"].failure_class == "BUILD_FAILED"
    assert events[-1].type == "done"


def test_successful_templates_succeed_the_run(tmp_path):
    status, events = _run(tmp_path, ["fake.discover", "fake.boot"])
    assert status == "SUCCEEDED"
    assert events[-1].type == "done"
    assert all(event.outcome == "PASS" for event in events if event.type == "test_result")


def test_unregistered_template_fails_run(tmp_path):
    status, events = _run(tmp_path, ["fake.boot", "rm -rf /"])
    assert status == "FAILED"
    assert any(e.type == "error" and e.failure_class == "INTERNAL" for e in events)
    assert not any(e.type == "test_result" for e in events)
