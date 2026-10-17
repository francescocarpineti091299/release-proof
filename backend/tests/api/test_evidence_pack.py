from __future__ import annotations

import hashlib
import io
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from test_api import CREATE, Harness, _client, _wait

from releaseproof.release_gate import InvalidPack, release_decision, verify_pack


def _rewrite(blob, mutate):
    with ZipFile(io.BytesIO(blob)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    mutate(files)
    out = io.BytesIO()
    with ZipFile(out, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    out.seek(0)
    return out


def _reindex(files):
    index = json.loads(files["pack-index.json"])
    for entry in index["files"]:
        blob = files[entry["path"]]
        entry.update(sha256=hashlib.sha256(blob).hexdigest(), size_bytes=len(blob))
    files["pack-index.json"] = json.dumps(index).encode()


def test_live_evidence_pack_is_portable_and_migration_blocks(tmp_path):
    h = Harness(tmp_path)
    with _client(h) as client:
        run_id = client.post("/api/assessments", json=CREATE).json()["run_id"]
        run = _wait(client, run_id)
        response = client.get(f"/api/assessments/{run_id}/evidence-pack")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers["content-disposition"]
        pack = verify_pack(io.BytesIO(response.content))
        assert pack["run"]["run_id"] == run_id
        assert pack["manifest"]["result"]["canonical_hash"] == run["verdict"]["canonical_hash"]
        decision = release_decision(
            pack,
            configuration=run["configuration_id"],
            change=run["change_id"],
            plan=run["plan_id"],
        )
        assert decision["decision"] == "BLOCK" and decision["official"] is False
        assert any("migration: INCOMPATIBLE" in r for r in decision["reasons"])
        with ZipFile(io.BytesIO(response.content)) as archive:
            assert b"not certification" in archive.read("README.md")
            assert len(json.loads(archive.read("ai-traces.json"))) == 3


def test_reevaluation_pack_preserves_parent_ownership(tmp_path):
    with _client(Harness(tmp_path)) as client:
        parent = client.post("/api/assessments", json=CREATE).json()["run_id"]
        _wait(client, parent)
        child = client.post(
            f"/api/assessments/{parent}/alternatives/field_service_reflash/evaluate",
        ).json()["run_id"]
        run = _wait(client, child)
        response = client.get(f"/api/assessments/{child}/evidence-pack")
        assert response.status_code == 200
        pack = verify_pack(io.BytesIO(response.content))
        assert pack["manifest"]["evidence_run_id"] == parent
        assert {a["owner_run_id"] for a in pack["manifest"]["artifacts"]} == {parent}
        decision = release_decision(
            pack,
            configuration=run["configuration_id"],
            change=run["change_id"],
            plan=run["plan_id"],
        )
        assert decision["decision"] == "BLOCK"
        assert any("fresh LIVE" in r for r in decision["reasons"])


@pytest.mark.parametrize("behavior", ["midstream_error", "corrupt_file", "no_done"])
def test_failed_run_has_no_evidence_pack(tmp_path, behavior):
    with _client(Harness(tmp_path, behaviour=behavior)) as client:
        run = client.post("/api/assessments", json=CREATE).json()["run_id"]
        _wait(client, run)
        assert client.get(f"/api/assessments/{run}/evidence-pack").status_code == 409


def test_changed_artifact_refuses_entire_pack_before_response(tmp_path):
    h = Harness(tmp_path)
    with _client(h) as client:
        run = client.post("/api/assessments", json=CREATE).json()["run_id"]
        _wait(client, run)
        row = client.app.state.store.get_artifact(run, "ART-wolfboot.boot_current-uart")
        (h.settings.run_dir(run) / row["rel_path"]).write_bytes(b"changed")
        response = client.get(f"/api/assessments/{run}/evidence-pack")
        assert response.status_code == 409 and "attachment" not in response.headers


def test_pack_verifier_rejects_tampering_even_with_recomputed_index(tmp_path):
    with _client(Harness(tmp_path)) as client:
        run = client.post("/api/assessments", json=CREATE).json()["run_id"]
        _wait(client, run)
        blob = client.get(f"/api/assessments/{run}/evidence-pack").content

    def corrupt_artifact(files):
        name = next(n for n in files if n.startswith("artifacts/"))
        files[name] = b"modified"

    with pytest.raises(InvalidPack, match="digest"):
        verify_pack(_rewrite(blob, corrupt_artifact))

    def corrupt_and_reindex(files):
        corrupt_artifact(files)
        _reindex(files)

    with pytest.raises(InvalidPack, match="manifest artifact"):
        verify_pack(_rewrite(blob, corrupt_and_reindex))

    def corrupt_verdict(files):
        doc = json.loads(files["result.json"])
        doc["result"]["migration_verdict"] = "COMPATIBLE"
        files["result.json"] = json.dumps(doc).encode()
        _reindex(files)

    with pytest.raises(InvalidPack, match="canonical"):
        verify_pack(_rewrite(blob, corrupt_verdict))

    def corrupt_tests(files):
        doc = json.loads(files["run.json"])
        doc["tests"][0]["outcome"] = "FAIL"
        files["run.json"] = json.dumps(doc).encode()
        _reindex(files)

    with pytest.raises(InvalidPack, match="test binding"):
        verify_pack(_rewrite(blob, corrupt_tests))

    def malformed_index(files):
        files["pack-index.json"] = b"[]"

    with pytest.raises(InvalidPack, match="malformed"):
        verify_pack(_rewrite(blob, malformed_index))


def test_pack_path_and_size_limits(tmp_path, monkeypatch):
    with _client(Harness(tmp_path)) as client:
        run = client.post("/api/assessments", json=CREATE).json()["run_id"]
        _wait(client, run)
        blob = client.get(f"/api/assessments/{run}/evidence-pack").content
        monkeypatch.setattr("releaseproof.api.evidence_pack.MAX_PACK_BYTES", 1)
        assert client.get(f"/api/assessments/{run}/evidence-pack").status_code == 409

    def escape(files):
        name = next(n for n in files if n.startswith("artifacts/"))
        files["../../secret"] = files.pop(name)
        index = json.loads(files["pack-index.json"])
        next(e for e in index["files"] if e["path"] == name)["path"] = "../../secret"
        files["pack-index.json"] = json.dumps(index).encode()

    with pytest.raises(InvalidPack, match="path"):
        verify_pack(_rewrite(blob, escape))
