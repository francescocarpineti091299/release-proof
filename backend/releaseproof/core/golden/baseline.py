"""Golden hash checks for WP0 baseline and signer-bound assessments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from releaseproof.core.assurance.service import evaluate
from releaseproof.core.projection.wp0 import build_a4_signer_bound_assessment, build_wp0_baseline_assessment
from releaseproof.core.paths import CONTRACT_PACK

_PACK = CONTRACT_PACK
GOLDEN_HASH_PATH = _PACK / "examples" / "golden" / "wp0_result_hashes_v1_2.json"


def load_golden_hashes(path: Path | None = None) -> dict[str, Any]:
    target = path or GOLDEN_HASH_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def verify_baseline_golden() -> tuple[bool, str | None]:
    """Return (ok, error_message). Assessment input comes from projection only."""
    expected = load_golden_hashes()
    result = evaluate(build_wp0_baseline_assessment())
    if result.assessment_id != expected["baseline_assessment_id"]:
        return False, f"assessment_id atteso {expected['baseline_assessment_id']!r}"
    if result.canonical_hash != expected["baseline_canonical_hash"]:
        return (
            False,
            f"canonical_hash baseline: atteso {expected['baseline_canonical_hash']}, "
            f"ottenuto {result.canonical_hash}",
        )
    return True, None


def verify_signer_bound_golden() -> tuple[bool, str | None]:
    expected = load_golden_hashes()
    result = evaluate(build_a4_signer_bound_assessment())
    if result.assessment_id != expected["signer_bound_assessment_id"]:
        return False, f"assessment_id atteso {expected['signer_bound_assessment_id']!r}"
    if result.canonical_hash != expected["signer_bound_canonical_hash"]:
        return (
            False,
            f"canonical_hash signer-bound: atteso {expected['signer_bound_canonical_hash']}, "
            f"ottenuto {result.canonical_hash}",
        )
    return True, None


__all__ = [
    "GOLDEN_HASH_PATH",
    "load_golden_hashes",
    "verify_baseline_golden",
    "verify_signer_bound_golden",
]
