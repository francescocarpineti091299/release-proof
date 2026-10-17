"""Golden WP0 baseline: same projection must yield the same canonical_hash."""

from __future__ import annotations

from releaseproof.core.assurance.service import evaluate
from releaseproof.core.golden.baseline import (
    load_golden_hashes,
    verify_baseline_golden,
    verify_signer_bound_golden,
)
from releaseproof.core.projection.wp0 import build_a4_signer_bound_assessment, build_wp0_baseline_assessment


def test_baseline_golden_hash() -> None:
    ok, err = verify_baseline_golden()
    assert ok, err


def test_signer_bound_golden_hash() -> None:
    ok, err = verify_signer_bound_golden()
    assert ok, err


def test_baseline_evaluate_is_deterministic() -> None:
    first = evaluate(build_wp0_baseline_assessment())
    second = evaluate(build_wp0_baseline_assessment())
    assert first.canonical_hash == second.canonical_hash
    expected = load_golden_hashes()["baseline_canonical_hash"]
    assert first.canonical_hash == expected


def test_signer_bound_evaluate_is_deterministic() -> None:
    first = evaluate(build_a4_signer_bound_assessment())
    second = evaluate(build_a4_signer_bound_assessment())
    assert first.canonical_hash == second.canonical_hash
