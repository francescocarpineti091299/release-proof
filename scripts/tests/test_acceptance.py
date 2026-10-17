from __future__ import annotations

import hashlib
import json
import urllib.error
from datetime import UTC, datetime, timedelta

import acceptance
import pytest


class RecordedApi:
    def __init__(self, *, missing_required=False, empty_result=False):
        self.missing_required = missing_required
        self.empty_result = empty_result
        self.keys = []
        self.assessment = {"assessment_id": "unit-test"}
        self.result = {
            "official": False,
            "lifecycle": "COMPLETED",
            "migration_verdict": "INCOMPATIBLE",
            "candidate_verdict": "COMPATIBLE",
            "transition_verdict": "INCOMPATIBLE",
        }
        self.result["canonical_hash"] = acceptance.compute_canonical_hash(self.result)
        self.manifest = {
            "run_id": "run",
            "assessment": {"canonical_hash": acceptance.compute_canonical_hash(self.assessment)},
            "implementation": acceptance.implementation_identity(),
            "source_pins": {
                "releaseproof_runner_code_sha256": acceptance.runner_source_digest("wolfboot")
            },
        }
        self.manifest_bytes = json.dumps(self.manifest).encode()

    def post(self, path, body):
        self.keys.append(body["idempotency_key"])
        tests = [
            {"test_id": "E01", "template_id": "boot", "negative": False, "outcome": "PASS"},
            {"test_id": "E03", "template_id": "negative", "negative": True, "outcome": "PASS"},
            {"test_id": "E08", "template_id": "update", "negative": False, "outcome": "PASS"},
        ]
        if not self.missing_required:
            tests.append(
                {"test_id": "D01", "template_id": "discover", "negative": False, "outcome": "PASS"}
            )
        return {
            "run_id": "run",
            "mode": "LIVE",
            "status": "SUCCEEDED",
            "created_at": datetime.now(UTC).isoformat(),
            "tests": tests,
            "stages": [{"stage": "BUILD_SIGN", "status": "SUCCEEDED"}],
            "verdict": {
                "canonical_hash": self.result["canonical_hash"],
                "official": False,
                "lifecycle": self.result["lifecycle"],
                "migration": self.result["migration_verdict"],
                "candidate": self.result["candidate_verdict"],
                "transition": self.result["transition_verdict"],
            },
        }

    def get(self, path):
        if path.endswith("/result"):
            return (
                {}
                if self.empty_result
                else {
                    "assessment": self.assessment,
                    "result": self.result,
                    "manifest_sha256": hashlib.sha256(self.manifest_bytes).hexdigest(),
                    "evidence": [{"run_id": "run"}] * 3,
                }
            )
        if path.endswith("/artifacts"):
            return [
                {
                    "artifact_id": str(i),
                    "url": "/blob",
                    "sha256": hashlib.sha256(b"blob").hexdigest(),
                }
                for i in range(3)
            ] + [
                {
                    "artifact_id": "MANIFEST",
                    "url": "/manifest",
                    "sha256": hashlib.sha256(self.manifest_bytes).hexdigest(),
                }
            ]
        if path.endswith("/ai-traces"):
            return []
        raise AssertionError(path)

    def raw(self, path):
        return self.manifest_bytes if path == "/manifest" else b"blob"


CONFIG = {
    "id": "profile",
    "bootloader": {"family": "wolfboot"},
    "changes": [
        {
            "change_id": "change",
            "templates": [
                {"template_id": "boot", "required": True},
                {"template_id": "discover", "required": True},
            ],
        }
    ],
}


def test_complete_run_passes_without_ai_and_uses_fresh_keys():
    api = RecordedApi()
    for _ in range(2):
        assert acceptance.run_profile(api, CONFIG, require_ai=False, timeout=1)["passed"]
    assert len(set(api.keys)) == 2


class ResumedApi(RecordedApi):
    def __init__(self, *, mode="LIVE", configuration="profile", age_minutes=0):
        super().__init__()
        self.run = super().post("/api/assessments", {"idempotency_key": "fixture-only"})
        self.run.update(mode=mode, configuration_id=configuration, change_id="change")
        self.run["created_at"] = (datetime.now(UTC) - timedelta(minutes=age_minutes)).isoformat()
        self.keys.clear()

    def post(self, path, body):
        raise AssertionError("Resuming must not create an assessment")

    def get(self, path):
        return self.run if path == "/api/assessments/run" else super().get(path)


def test_resume_keeps_all_proof_checks_without_creating_duplicate_run():
    api = ResumedApi()
    report = acceptance.run_profile(
        api,
        CONFIG,
        require_ai=False,
        timeout=1,
        resume_run_id="run",
        deployed_after=datetime.now(UTC) - timedelta(minutes=1),
    )
    assert report["passed"]
    assert not api.keys
    assert any(
        g["gate"] == "resumed LIVE run created after verified deployment" for g in report["gates"]
    )
    assert not any(g["gate"] == "run created now" for g in report["gates"])


@pytest.mark.parametrize("kwargs", [{"mode": "REFERENCE"}, {"configuration": "wrong"}])
def test_resume_refuses_reference_or_mismatched_configuration(kwargs):
    with pytest.raises(ValueError, match="LIVE and match"):
        acceptance.run_profile(
            ResumedApi(**kwargs),
            CONFIG,
            require_ai=False,
            timeout=1,
            resume_run_id="run",
            deployed_after=datetime.now(UTC) - timedelta(minutes=1),
        )


def test_resume_refuses_evidence_from_before_deployment():
    report = acceptance.run_profile(
        ResumedApi(age_minutes=20),
        CONFIG,
        require_ai=False,
        timeout=1,
        resume_run_id="run",
        deployed_after=datetime.now(UTC) - timedelta(minutes=1),
    )
    assert not report["passed"]


@pytest.mark.parametrize("kwargs", [{"missing_required": True}, {"empty_result": True}])
def test_incomplete_proof_cannot_pass(kwargs):
    result = acceptance.run_profile(RecordedApi(**kwargs), CONFIG, require_ai=False, timeout=1)
    assert not result["passed"]


def test_malformed_hash_cannot_count_as_a_deterministic_verdict():
    class Api(RecordedApi):
        def post(self, path, body):
            run = super().post(path, body)
            run["verdict"]["canonical_hash"] = "not-a-hash"
            return run

    assert not acceptance.run_profile(Api(), CONFIG, require_ai=False, timeout=1)["passed"]


def test_manifest_digest_is_checked_even_outside_the_artifact_sample():
    class Api(RecordedApi):
        def get(self, path):
            data = super().get(path)
            if path.endswith("/artifacts"):
                manifest = data.pop()
                data.extend([{**data[0], "artifact_id": f"extra-{i}"} for i in range(3)])
                data.append({**manifest, "url": "/changed-manifest"})
            return data

        def raw(self, path):
            return b"{}" if path == "/changed-manifest" else super().raw(path)

    assert not acceptance.run_profile(Api(), CONFIG, require_ai=False, timeout=1)["passed"]


def test_explainer_only_cannot_pass_the_required_ai_gate():
    class Api(RecordedApi):
        def get(self, path):
            if path == "/api/amd":
                return {
                    "provider": {"endpoint_host": "developer.amd.com.cn", "fallback_provider": None}
                }
            if path.endswith("/ai-traces"):
                return [
                    {
                        "status": "OK",
                        "module": "alternatives",
                        "run_id": "run",
                        "trace_id": "T",
                        "model": "model",
                        "endpoint_host": "developer.amd.com.cn",
                        "request_id": "request",
                    }
                ]
            return super().get(path)

    result = acceptance.run_profile(Api(), CONFIG, require_ai=True, timeout=1)
    assert not result["passed"]
    assert not next(g for g in result["gates"] if g["gate"] == "AMD LLM called for this run")["ok"]


def test_tampering_with_serialized_result_cannot_pass():
    api = RecordedApi()
    api.result["official"] = True
    assert not acceptance.run_profile(api, CONFIG, require_ai=False, timeout=1)["passed"]


@pytest.mark.parametrize("empty_plan", [False, True])
def test_required_ai_needs_an_executed_selection(empty_plan):
    templates = [
        {"template_id": name, "required": True}
        for name in ("boot", "negative", "update", "discover")
    ]
    config = {**CONFIG, "changes": [{"change_id": "change", "templates": templates}]}

    class Api(RecordedApi):
        def post(self, path, body):
            run = super().post(path, body)
            run["ai_plan"] = {
                "status": "OK",
                "trace_ids": ["planner"],
                "proposal": {"selected": [] if empty_plan else templates},
            }
            run["ai_report"] = {"status": "OK", "trace_ids": ["explainer"]}
            run["ai_alternatives"] = {"status": "OK", "trace_ids": ["alternatives"]}
            return run

        def get(self, path):
            if path == "/api/amd":
                return {
                    "provider": {"endpoint_host": "developer.amd.com.cn", "fallback_provider": None}
                }
            if path.endswith("/ai-traces"):
                return [
                    {
                        "module": module,
                        "trace_id": module,
                        "status": "OK",
                        "run_id": "run",
                        "model": "unit-model",
                        "request_id": "unit-request",
                        "endpoint_host": "developer.amd.com.cn",
                    }
                    for module in ("planner", "explainer", "alternatives")
                ]
            return super().get(path)

    result = acceptance.run_profile(Api(), config, require_ai=True, timeout=1)
    assert result["passed"] is not empty_plan


def test_artifact_outside_previous_sample_is_verified():
    class Api(RecordedApi):
        def get(self, path):
            data = super().get(path)
            if path.endswith("/artifacts"):
                data.extend([{**data[0], "artifact_id": f"extra-{i}"} for i in range(5)])
                data[-1]["url"] = "/changed"
            return data

        def raw(self, path):
            return b"tampered" if path == "/changed" else super().raw(path)

    assert not acceptance.run_profile(Api(), CONFIG, require_ai=False, timeout=1)["passed"]


def test_profile_failure_writes_report_and_checks_other_profiles(monkeypatch, tmp_path):
    class Api:
        def __init__(self, base):
            pass

        def get(self, path):
            return [{"id": "one"}, {"id": "two"}]

    checked = []

    def run_profile(api, config, **kwargs):
        checked.append(config["id"])
        if config["id"] == "one":
            raise urllib.error.HTTPError("url", 409, "no result", None, None)
        return {"profile": "two", "passed": True}

    monkeypatch.setattr(acceptance, "Api", Api)
    monkeypatch.setattr(acceptance, "run_profile", run_profile)
    monkeypatch.setattr(acceptance, "ROOT", tmp_path)
    assert acceptance.main([]) == 1
    assert checked == ["one", "two"]
    report = next((tmp_path / "docs/acceptance").glob("*.json"))
    assert json.loads(report.read_text())[0]["passed"] is False


def test_unknown_profile_does_not_silently_check_a_subset(monkeypatch):
    class Api:
        def __init__(self, base):
            pass

        def get(self, path):
            return [{"id": "one"}]

    monkeypatch.setattr(acceptance, "Api", Api)
    assert acceptance.main(["--profile", "one", "--profile", "typo"]) == 2
