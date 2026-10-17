from __future__ import annotations

import hashlib
import json
import urllib.error
from datetime import UTC, datetime

import acceptance
import pytest


class RecordedApi:
    def __init__(self, *, missing_required=False, empty_result=False):
        self.missing_required = missing_required
        self.empty_result = empty_result
        self.keys = []

    def post(self, path, body):
        self.keys.append(body["idempotency_key"])
        tests = [
            {"test_id": "E01", "template_id": "boot", "negative": False, "outcome": "PASS"},
            {"test_id": "E03", "template_id": "negative", "negative": True, "outcome": "PASS"},
            {"test_id": "E08", "template_id": "update", "negative": False, "outcome": "PASS"},
        ]
        if not self.missing_required:
            tests.append({"test_id": "D01", "template_id": "discover",
                          "negative": False, "outcome": "PASS"})
        return {
            "run_id": "run", "mode": "LIVE", "status": "SUCCEEDED",
            "created_at": datetime.now(UTC).isoformat(), "tests": tests,
            "stages": [{"stage": "BUILD_SIGN", "status": "SUCCEEDED"}],
            "verdict": {"canonical_hash": "sha256:" + "a" * 64, "official": False},
        }

    def get(self, path):
        if path.endswith("/result"):
            return {} if self.empty_result else {
                "result": {"canonical_hash": "sha256:" + "a" * 64},
                "manifest_sha256": hashlib.sha256(b"blob").hexdigest(),
                "evidence": [{"run_id": "run"}] * 3,
            }
        if path.endswith("/artifacts"):
            return [{"artifact_id": str(i) if i < 3 else "MANIFEST", "url": "/blob",
                     "sha256": hashlib.sha256(b"blob").hexdigest()} for i in range(4)]
        if path.endswith("/ai-traces"):
            return []
        raise AssertionError(path)

    def raw(self, path):
        return b"blob"


CONFIG = {
    "id": "profile", "changes": [{"change_id": "change", "templates": [
        {"template_id": "boot", "required": True},
        {"template_id": "discover", "required": True},
    ]}],
}


def test_complete_run_passes_without_ai_and_uses_fresh_keys():
    api = RecordedApi()
    for _ in range(2):
        assert acceptance.run_profile(api, CONFIG, require_ai=False, timeout=1)["passed"]
    assert len(set(api.keys)) == 2


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
            return b"tampered" if path == "/changed-manifest" else b"blob"

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
