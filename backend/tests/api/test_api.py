"""HTTP API: endpoints, SSE replay/live, artifacts, reference, AI endpoints."""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "orchestrator"))

from rp_fakes import (  # noqa: E402
    GOLDEN_BASELINE_HASH,
    MCUBOOT,
    MCUBOOT_CHANGE,
    WOLFBOOT,
    WOLFBOOT_CHANGE,
    Harness,
)

from releaseproof.api.app import create_app  # noqa: E402

CREATE = {"configuration_id": WOLFBOOT, "change_id": WOLFBOOT_CHANGE}


def _client(h: Harness) -> TestClient:
    return TestClient(create_app(h.settings, h.deps))


def _wait(client: TestClient, run_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        view = client.get(f"/api/assessments/{run_id}").json()
        if view["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return view
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if not line or line.startswith(":"):
                continue
            key, _, value = line.partition(": ")
            fields[key] = value
        if "data" in fields:
            events.append(
                {
                    "id": int(fields["id"]),
                    "event": fields["event"],
                    "data": json.loads(fields["data"]),
                }
            )
    return events


def _sse(client: TestClient, run_id: str, **kw) -> list[dict]:
    with client.stream("GET", f"/api/assessments/{run_id}/events", **kw) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        return _parse_sse("".join(resp.iter_text()))


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


def test_health_and_configurations(h):
    with _client(h) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        configs = client.get("/api/configurations").json()
        assert {c["id"] for c in configs} == {WOLFBOOT, MCUBOOT}
        wolf = next(c for c in configs if c["id"] == WOLFBOOT)
        change = wolf["changes"][0]
        templates = {t["template_id"]: t for t in change["templates"]}
        assert templates["wolfboot.tampered_image_rejected"]["negative"] is True
        assert templates["wolfboot.boot_current"]["required"] is True
        assert templates["wolfboot.dual_signature_build"]["required"] is False
        assert all(t["title"] and t["est_seconds"] > 0 for t in change["templates"])
        assert {a["plan_id"] for a in change["alternatives"]} == {
            "field_service_reflash",
            "staged_hybrid_dual_signature",
        }
        assert client.get(f"/api/configurations/{WOLFBOOT}").json()["id"] == WOLFBOOT
        assert client.get("/api/configurations/nope").status_code == 404
        catalog = client.get("/api/catalog/tests").json()
        assert "E03" in catalog["tests"] and catalog["templates"]
        cors = client.options(
            "/api/health",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
        )
        assert cors.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_experimental_profiles_hidden_by_default(tmp_path, monkeypatch):
    _force_experimental(monkeypatch)
    h = Harness(tmp_path, expose=False)
    with _client(h) as client:
        assert client.get("/api/configurations").json() == []
        assert client.get(f"/api/configurations/{WOLFBOOT}").status_code == 404
        assert client.post("/api/assessments", json=CREATE).status_code == 422


def test_create_validation(h):
    with _client(h) as client:
        assert (
            client.post("/api/assessments", json={**CREATE, "configuration_id": "x"}).status_code
            == 422
        )
        assert client.post("/api/assessments", json={**CREATE, "change_id": "x"}).status_code == 422
        assert client.post("/api/assessments", json={**CREATE, "plan_id": "x"}).status_code == 422
        assert (
            client.post("/api/assessments", json={**CREATE, "verdict": "COMPATIBLE"}).status_code
            == 422
        )
        resp = client.post(
            "/api/assessments",
            json={
                "configuration_id": MCUBOOT,
                "change_id": MCUBOOT_CHANGE,
                "plan_id": "switch_to_wolfboot_depot",
            },
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "REQUIRES_EXTERNAL_VALIDATION"
        assert client.get("/api/assessments/RP-nope").status_code == 404
        assert client.get("/api/assessments/RP-nope/result").status_code == 404


def test_happy_path_live_run_and_sse_replay(h):
    with _client(h) as client:
        resp = client.post("/api/assessments", json=CREATE)
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]
        view = _wait(client, run_id)
        assert view["status"] == "SUCCEEDED"
        assert view["mode"] == "LIVE"
        assert view["verdict"]["migration"] == "INCOMPATIBLE"
        assert view["verdict"]["official"] is False

        events = _sse(client, run_id)
        stored = h_store_ids(client, run_id)
        assert [e["id"] for e in events] == stored  # every persisted event, in order
        assert events[0]["event"] == "run" and events[0]["data"]["data"]["status"] == "QUEUED"
        assert events[-1]["event"] == "run" and events[-1]["data"]["data"]["status"] == "SUCCEEDED"
        assert all(e["data"]["id"] == e["id"] and e["data"]["type"] == e["event"] for e in events)
        types = {e["event"] for e in events}
        assert types >= {
            "run",
            "stage",
            "log",
            "artifact",
            "observation",
            "test_result",
            "done",
            "ai",
        }
        stage_order = []
        for e in events:
            if e["event"] == "stage" and e["data"]["data"]["status"] == "RUNNING":
                name = e["data"]["data"]["stage"]
                if name not in stage_order:
                    stage_order.append(name)
        assert stage_order == [
            "PREPARING",
            "AI_PLAN",
            "DISCOVERY",
            "BUILD_SIGN",
            "EMULATION_TESTS",
            "EVALUATION",
            "NEXT_STEPS",
        ]

        middle = events[len(events) // 2]["id"]
        tail = _sse(client, run_id, headers={"Last-Event-ID": str(middle)})
        assert [e["id"] for e in tail] == [i for i in stored if i > middle]
        tail_q = _sse(client, run_id, params={"after": middle})
        assert [e["id"] for e in tail_q] == [i for i in stored if i > middle]

        result = client.get(f"/api/assessments/{run_id}/result").json()
        assert result["result"]["canonical_hash"] == view["verdict"]["canonical_hash"]
        assert result["dossier_markdown"].startswith("# Assessment dossier")
        assert result["evidence"] and result["manifest_sha256"]
        traces = client.get(f"/api/assessments/{run_id}/ai-traces").json()
        assert [t["module"] for t in traces] == ["planner", "explainer", "alternatives"]
        plan = client.get(f"/api/assessments/{run_id}/plan").json()
        assert {p["planned_by"] for p in plan} == {"POLICY_REQUIRED", "AI_PLANNER"}
        listed = client.get("/api/assessments").json()
        assert listed[0]["run_id"] == run_id


def h_store_ids(client: TestClient, run_id: str) -> list[int]:
    return [e.id for e in client.app.state.store.list_events(run_id)]


def test_sse_follows_a_live_run_until_terminal(h):
    gate = threading.Event()
    h.runner.gate = gate
    with _client(h) as client:
        run_id = client.post("/api/assessments", json=CREATE).json()["run_id"]
        assert h.runner.entered.wait(5)
        threading.Timer(0.5, gate.set).start()
        events = _sse(client, run_id)
        assert events[-1]["event"] == "run" and events[-1]["data"]["data"]["status"] == "SUCCEEDED"
        assert [e["id"] for e in events] == h_store_ids(client, run_id)


def test_failed_run_has_no_result(tmp_path):
    h = Harness(tmp_path, behaviour="midstream_error")
    with _client(h) as client:
        run_id = client.post("/api/assessments", json=CREATE).json()["run_id"]
        view = _wait(client, run_id)
        assert view["status"] == "FAILED" and view["verdict"] is None
        assert view["failure"]["failure_class"] == "TOOL_FAILURE"
        resp = client.get(f"/api/assessments/{run_id}/result")
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "RESULT_NOT_AVAILABLE"
        events = _sse(client, run_id)
        assert events[-1]["data"]["data"]["status"] == "FAILED"
        assert not any(
            e["event"] == "stage"
            and e["data"]["data"]["stage"] == "EVALUATION"
            and e["data"]["data"]["status"] == "SUCCEEDED"
            for e in events
        )
        assert client.post(f"/api/assessments/{run_id}/alternatives").status_code == 409


def test_idempotency_header_and_body(h):
    with _client(h) as client:
        first = client.post("/api/assessments", json=CREATE, headers={"Idempotency-Key": "k-1"})
        second = client.post("/api/assessments", json=CREATE, headers={"Idempotency-Key": "k-1"})
        assert first.status_code == 201 and second.status_code == 200
        assert second.headers["Idempotent-Replayed"] == "true"
        assert first.json()["run_id"] == second.json()["run_id"]
        third = client.post("/api/assessments", json={**CREATE, "idempotency_key": "k-1"})
        assert third.json()["run_id"] == first.json()["run_id"]
        clash = client.post(
            "/api/assessments",
            json={**CREATE, "plan_id": "field_service_reflash"},
            headers={"Idempotency-Key": "k-1"},
        )
        assert clash.status_code == 409
        _wait(client, first.json()["run_id"])
        assert len(h.runner.calls) == 1


def test_artifacts_listing_download_and_traversal(h, tmp_path):
    with _client(h) as client:
        run_id = client.post("/api/assessments", json=CREATE).json()["run_id"]
        _wait(client, run_id)
        arts = {
            a["artifact_id"]: a for a in client.get(f"/api/assessments/{run_id}/artifacts").json()
        }
        assert "MANIFEST" in arts
        uart = arts["ART-wolfboot.boot_current-uart"]
        assert uart["url"] == f"/api/assessments/{run_id}/artifacts/{uart['artifact_id']}"

        resp = client.get(uart["url"])
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert resp.headers["content-disposition"].startswith("inline")
        assert hashlib.sha256(resp.content).hexdigest() == uart["sha256"]

        image = arts["ART-wolfboot.boot_current-image"]
        resp = client.get(image["url"])
        assert resp.headers["content-type"] == "application/octet-stream"
        assert resp.headers["content-disposition"].startswith("attachment")

        manifest = client.get(arts["MANIFEST"]["url"])
        result = client.get(f"/api/assessments/{run_id}/result").json()
        assert hashlib.sha256(manifest.content).hexdigest() == result["manifest_sha256"]
        assert manifest.json()["run_id"] == run_id

        secret = h.settings.data_dir / "secret.txt"
        secret.write_text("top secret")
        for bad in ("..%2F..%2Fsecret.txt", "%2E%2E", "...", "MANIFEST%00", "..%5C..%5Csecret.txt"):
            resp = client.get(f"/api/assessments/{run_id}/artifacts/{bad}")
            assert resp.status_code == 404, bad
            assert b"top secret" not in resp.content
        for normalized in ("..", "../../secret.txt", "../../../secret.txt"):
            resp = client.get(f"/api/assessments/{run_id}/artifacts/{normalized}")
            assert b"top secret" not in resp.content
            assert "attachment" not in resp.headers.get("content-disposition", "")
        # even a poisoned row in the database cannot escape the run directory
        client.app.state.store.add_artifact(
            run_id,
            {
                "artifact_id": "ART-evil",
                "name": "secret.txt",
                "rel_path": "../../secret.txt",
                "kind": "log",
                "sha256": "0" * 64,
                "size_bytes": 1,
                "test_id": None,
            },
        )
        resp = client.get(f"/api/assessments/{run_id}/artifacts/ART-evil")
        assert resp.status_code == 404 and b"top secret" not in resp.content


def test_reference_is_the_recorded_freeze_with_golden_hash(h):
    with _client(h) as client:
        ref = client.get("/api/reference").json()
        assert ref["canonical_hash"] == GOLDEN_BASELINE_HASH
        assert ref["result"]["result"]["canonical_hash"] == GOLDEN_BASELINE_HASH
        assert ref["run"]["verdict"]["canonical_hash"] == GOLDEN_BASELINE_HASH
        assert ref["run"]["mode"] == "REFERENCE"
        assert ref["recorded"] is True and ref["recorded_at"] == "2026-10-01"
        assert "not a live execution" in ref["notice"]
        assert ref["run"]["verdict"]["migration"] == "INCOMPATIBLE"
        assert all(
            s["status"] == "SKIPPED" for s in ref["run"]["stages"] if s["stage"] != "EVALUATION"
        )
        assert {e["origin"] for e in ref["result"]["evidence"]} == {"RECORDED_WP0_FREEZE"}
        run_id = ref["run"]["run_id"]
        assert client.get(f"/api/assessments/{run_id}").json()["mode"] == "REFERENCE"
        assert (
            client.get(f"/api/assessments/{run_id}/result").json()["result"]["canonical_hash"]
            == GOLDEN_BASELINE_HASH
        )
        # the reference never shows up as a run
        assert all(r["mode"] != "REFERENCE" for r in client.get("/api/assessments").json())


def test_alternatives_endpoints(h):
    with _client(h) as client:
        parent = client.post("/api/assessments", json=CREATE).json()["run_id"]
        parent_view = _wait(client, parent)
        alts = client.post(f"/api/assessments/{parent}/alternatives")
        assert alts.status_code == 200 and alts.json()["status"] == "OK"

        resp = client.post(
            f"/api/assessments/{parent}/alternatives/field_service_reflash/evaluate",
            headers={"Idempotency-Key": "alt-1"},
        )
        assert resp.status_code == 201
        child = resp.json()
        assert child["mode"] == "REEVALUATION" and child["parent_run_id"] == parent
        again = client.post(
            f"/api/assessments/{parent}/alternatives/field_service_reflash/evaluate",
            headers={"Idempotency-Key": "alt-1"},
        )
        assert again.status_code == 200 and again.json()["run_id"] == child["run_id"]
        child_view = _wait(client, child["run_id"])
        assert child_view["status"] == "SUCCEEDED"
        assert client.get(f"/api/assessments/{child['run_id']}/result").status_code == 200
        child_arts = client.get(f"/api/assessments/{child['run_id']}/artifacts").json()
        uart = next(a for a in child_arts if a["artifact_id"] == "ART-wolfboot.boot_current-uart")
        assert client.get(uart["url"]).status_code == 200  # served from the parent's directory

        after = client.get(f"/api/assessments/{parent}").json()
        assert (
            after["verdict"] == parent_view["verdict"] and after["stages"] == parent_view["stages"]
        )
        assert (
            client.post(f"/api/assessments/{parent}/alternatives/nope/evaluate").status_code == 404
        )


def test_requires_external_validation_alternative_is_422(h):
    with _client(h) as client:
        parent = client.post(
            "/api/assessments", json={"configuration_id": MCUBOOT, "change_id": MCUBOOT_CHANGE}
        ).json()
        _wait(client, parent["run_id"])
        resp = client.post(
            f"/api/assessments/{parent['run_id']}/alternatives/mcuboot_lms_branch/evaluate"
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error"] == "REQUIRES_EXTERNAL_VALIDATION"
        assert detail["plan_id"] == "mcuboot_lms_branch"
        assert "external validation" in detail["explanation"]


def test_assistant_streams_with_context_from_stored_result(h):
    with _client(h) as client:
        run_id = client.post("/api/assessments", json=CREATE).json()["run_id"]
        _wait(client, run_id)
        body = {"run_id": run_id, "messages": [{"role": "user", "content": "Why is it blocked?"}]}
        with client.stream("POST", "/api/assistant", json=body) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/plain")
            text = "".join(resp.iter_text())
        assert text == "The migration verdict is INCOMPATIBLE [cites EV-E01-BOOT]"
        context = h.ai.contexts[-1]
        assert (
            context["run"]["run_id"] == run_id
            and context["result"]["migration_verdict"] == "INCOMPATIBLE"
        )
        assert client.post("/api/assistant", json={**body, "run_id": "RP-nope"}).status_code == 404
        ref = client.post("/api/assistant", json={**body, "run_id": "REF-WP0-FREEZE-20261001"})
        assert ref.status_code == 200 and "INCOMPATIBLE" in ref.text


@pytest.mark.parametrize("ai", ["unavailable", "broken"])
def test_ai_down_run_succeeds_and_ai_endpoints_degrade(tmp_path, ai):
    h = Harness(tmp_path, ai=ai)
    with _client(h) as client:
        run_id = client.post("/api/assessments", json=CREATE).json()["run_id"]
        view = _wait(client, run_id)
        assert view["status"] == "SUCCEEDED" and view["verdict"]["migration"] == "INCOMPATIBLE"
        stages = {s["stage"]: s for s in view["stages"]}
        assert (
            stages["AI_PLAN"]["status"] == "INCONCLUSIVE"
            and stages["AI_PLAN"]["message"] == "AI_UNAVAILABLE"
        )
        assert (
            stages["NEXT_STEPS"]["status"] == "INCONCLUSIVE"
            and stages["NEXT_STEPS"]["message"] == "AI_UNAVAILABLE"
        )
        body = {"run_id": run_id, "messages": [{"role": "user", "content": "hi"}]}
        resp = client.post("/api/assistant", json=body)
        assert resp.status_code == 503 and "AI_UNAVAILABLE" in resp.text
        amd = client.get("/api/amd").json()
        if ai == "unavailable":
            assert amd["provider"]["status"] == "AI_UNAVAILABLE"
        assert (
            client.post(f"/api/assessments/{run_id}/alternatives").json()["status"]
            == "AI_UNAVAILABLE"
        )


def test_amd_panel_aggregates_traces(h):
    with _client(h) as client:
        run_id = client.post("/api/assessments", json=CREATE).json()["run_id"]
        _wait(client, run_id)
        amd = client.get("/api/amd").json()
        assert amd["provider"]["hardware_label"].startswith("AMD")
        assert amd["traces"]["count"] == 3 and amd["traces"]["ok_rate"] == 1.0
        assert amd["traces"]["latency_ms_p50"] == 300 and amd["traces"]["latency_ms_p95"] == 300
        assert amd["traces"]["prompt_tokens"] == 300


def _force_experimental(monkeypatch):
    """Selection rules must not depend on the current status in profiles/*.yaml."""
    from releaseproof.contracts.profile import ProfileStatus
    from releaseproof.profiles import registry

    real = registry.load_profiles()
    forced = {
        k: v.model_copy(update={"status": ProfileStatus.EXPERIMENTAL}) for k, v in real.items()
    }
    monkeypatch.setattr(registry, "load_profiles", lambda: forced)
