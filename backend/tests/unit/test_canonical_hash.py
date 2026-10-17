"""Tests for RFC 8785 canonical hashing vectors."""

from __future__ import annotations

import json
from pathlib import Path

import jcs

from releaseproof.core.canonical.service import compute_canonical_hash

ROOT = Path(__file__).resolve().parents[3] / "contract"
VECTORS = ROOT / "PQC_Engineering_Pack_V1_2" / "examples" / "canonical_hash_vectors_v1_2.json"


def _vectors() -> dict:
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def _canonical_json(obj: dict) -> str:
    payload = {key: value for key, value in obj.items() if key != "canonical_hash"}
    return jcs.canonicalize(payload).decode("utf-8")


def test_hv01_key_order_and_whitespace() -> None:
    vector = _vectors()["vectors"][0]
    objects = vector["objects"]
    assert compute_canonical_hash(objects[0]) == compute_canonical_hash(objects[1])
    assert compute_canonical_hash(objects[0]) == vector["expected_sha256"]
    assert _canonical_json(objects[0]) == vector["expected_canonical_json"]
    compact = json.loads('{"a":1,"b":2}')
    spaced = json.loads('{ "b" : 2, "a" : 1 }')
    assert compute_canonical_hash(compact) == compute_canonical_hash(spaced)


def test_hv02_omits_only_top_level_canonical_hash() -> None:
    vector = _vectors()["vectors"][1]
    assert compute_canonical_hash(vector["object"]) == compute_canonical_hash(
        vector["with_hash_field"]
    )
    assert compute_canonical_hash(vector["object"]) == vector["expected_sha256"]
    assert _canonical_json(vector["object"]) == vector["expected_canonical_json"]


def test_hv03_nested_content_hash_changes_digest() -> None:
    vector = _vectors()["vectors"][2]
    original = vector["object"]
    changed = {
        "id": "y",
        "artifact": {"content_hash": "sha256:other"},
    }
    assert compute_canonical_hash(original) == vector["expected_sha256"]
    assert _canonical_json(original) == vector["expected_canonical_json"]
    assert compute_canonical_hash(original) != compute_canonical_hash(changed)


def test_hv04_unicode_is_stable() -> None:
    vector = _vectors()["vectors"][3]
    obj = vector["object"]
    assert compute_canonical_hash(obj) == compute_canonical_hash({"s": "café", "n": 1.0})
    assert compute_canonical_hash(obj) == vector["expected_sha256"]
    assert _canonical_json(obj) == vector["expected_canonical_json"]
