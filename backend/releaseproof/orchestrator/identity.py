"""Content identities for reproducibility, independent of mutable image tags or Git dirtiness."""

import hashlib
from functools import lru_cache
from pathlib import Path


def source_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


@lru_cache(maxsize=1)
def implementation_identity() -> dict[str, str]:
    package = Path(__file__).resolve().parents[1]
    return {
        "backend_sha256": source_digest(package),
        "engine_sha256": source_digest(package / "core"),
        "adapters_sha256": source_digest(package / "adapters"),
        "contract_version": "1.2",
        "identity_algorithm": "sorted-python-path-lf-sha256/1",
    }
