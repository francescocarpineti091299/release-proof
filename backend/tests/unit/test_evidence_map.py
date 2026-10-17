"""Evidence mapping from WP0 snapshot."""

from __future__ import annotations

from releaseproof.core.evidence.map import evidence_from_wp0_runs
from releaseproof.core.projection.wp0 import load_freeze_snapshot


def test_wp0_evidence_typed_acquisition_modes() -> None:
    snap = load_freeze_snapshot()
    rows = {item["id"]: item for item in evidence_from_wp0_runs(snap)}
    assert rows["EV-E02-BOOT"]["acquisition_mode"] == "EMULATED"
    assert rows["EV-E05-LAYOUT-G2"]["acquisition_mode"] == "STATIC_ARTIFACT"
    assert rows["EV-E11-SELF-UPDATE"]["acquisition_mode"] == "SOURCE_INSPECTION"
    assert rows["EV-PIN-WOLFBOOT"]["acquisition_mode"] == "REPOSITORY"
    assert rows["EV-LAYOUT-PARTITION"]["acquisition_mode"] == "STATIC_CONFIG"
    assert rows["EV-E04-HEADER-SPAN"]["acquisition_mode"] == "STATIC_ARTIFACT"
    assert rows["EV-E12-WINDOW"]["value"] == "UNKNOWN"
    assert rows["EV-T3-DUAL-BUILD"]["value"] == "BUILD_FAILED"
    assert (
        rows["EV-T3-DUAL-BUILD"]["source_identity"]
        == "UNSUPPORTED_CONFIGURATION_ON_FROZEN_COMMIT"
    )
    assert rows["EV-E12-WINDOW"]["acquisition_mode"] != "EMULATED"


def test_wp0_evidence_links_catalog_tests() -> None:
    snap = load_freeze_snapshot()
    test_ids = {item.get("test_id") for item in evidence_from_wp0_runs(snap)}
    assert {"E01", "E02", "E03", "E04", "E05", "E11"} <= test_ids
