"""Filesystem locations of the normative contract and reference records.

Defaults resolve relative to the repository; containers override them via environment.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

CONTRACT_PACK = Path(
    os.environ.get(
        "RELEASEPROOF_CONTRACT_DIR",
        _REPO_ROOT / "contract" / "PQC_Engineering_Pack_V1_2",
    )
)

REFERENCE_DIR = Path(
    os.environ.get(
        "RELEASEPROOF_REFERENCE_DIR",
        _REPO_ROOT / "reference" / "wp0-freeze-20261001",
    )
)

REFERENCE_RUNS = REFERENCE_DIR / "runs"
