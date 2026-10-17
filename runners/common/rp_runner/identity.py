"""Identify the actual baked executor code/assets, not only its image tag."""

import hashlib
import sys
from pathlib import Path


def code_identity(family) -> dict[str, str]:
    module = sys.modules.get(type(family).__module__)
    filename = getattr(module, "__file__", None)
    if not filename:
        return {}
    roots = {"common": Path(__file__).parent, "family": Path(filename).resolve().parent}
    asset_root = roots["family"].parent
    for name in ("app", "renode"):
        if (asset_root / name).is_dir():
            roots[name] = asset_root / name
    digest = hashlib.sha256()
    for label, root in sorted(roots.items()):
        for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            digest.update(f"{label}/{path.relative_to(root).as_posix()}".encode() + b"\0")
            digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return {"releaseproof_runner_code_sha256": digest.hexdigest()}
