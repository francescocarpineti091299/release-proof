"""RFC 8785 canonical hashing."""

from __future__ import annotations

import hashlib
from typing import Any

import jcs

__all__ = ["compute_canonical_hash"]


def compute_canonical_hash(obj: dict[str, Any]) -> str:
    """Return sha256 hex digest of JCS-canonicalized object without top-level canonical_hash."""
    payload = {k: v for k, v in obj.items() if k != "canonical_hash"}
    canonical_bytes = jcs.canonicalize(payload)
    digest = hashlib.sha256(canonical_bytes).hexdigest()
    return f"sha256:{digest}"
