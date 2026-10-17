"""Generate a reproducible application dependency/license inventory (not a full OS SBOM).

Python packages come from the actual API image, npm packages from the committed production
lockfile. Missing license metadata is REVIEW_REQUIRED, never presumed MIT.
"""

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="releaseproof-api-1")
    parser.add_argument("--out", default="docs/DEPENDENCY_INVENTORY.json")
    args = parser.parse_args()
    inspected = json.loads(
        subprocess.check_output(
            ["docker", "exec", args.container, "python", "-m", "pip", "inspect", "--local"],
            text=True,
            encoding="utf-8",
        )
    )
    components = []
    for package in inspected["installed"]:
        meta = package["metadata"]
        license_name = meta.get("license_expression") or meta.get("license") or ""
        if not license_name:
            license_name = "; ".join(
                c for c in meta.get("classifier", []) if c.startswith("License ::")
            )
        components.append(
            {
                "ecosystem": "pypi",
                "name": meta["name"],
                "version": meta["version"],
                "license_metadata": license_name[:1000] or "REVIEW_REQUIRED",
                "requires_dist": meta.get("requires_dist", []),
            }
        )
    lock_path = ROOT / "web/package-lock.json"
    raw_lock = lock_path.read_bytes()
    lock = json.loads(raw_lock)
    for location, package in lock["packages"].items():
        if not location or package.get("dev") or not package.get("version"):
            continue
        components.append(
            {
                "ecosystem": "npm",
                "name": location.rsplit("node_modules/", 1)[-1],
                "version": package["version"],
                "integrity": package.get("integrity"),
                "license_metadata": package.get("license") or "REVIEW_REQUIRED",
                "optional": package.get("optional", False),
            }
        )
    image = json.loads(
        subprocess.check_output(
            ["docker", "inspect", "--format", "{{json .Image}}", args.container],
            text=True,
        )
    )
    report = {
        "format": "releaseproof.dependency-inventory/1",
        "generated_at": datetime.now(UTC).isoformat(),
        "api_image_id": image,
        "web_lock_sha256": hashlib.sha256(raw_lock).hexdigest(),
        "scope": (
            "API installed Python packages; "
            "npm production lockfile including optional platform variants"
        ),
        "limitations": [
            "Not an OS/toolchain/container-complete SBOM",
            "Metadata is not a legal compatibility opinion",
            "Runner tools and copyleft distribution obligations are in THIRD_PARTY_NOTICES.md",
        ],
        "components": sorted(components, key=lambda c: (c["ecosystem"], c["name"], c["version"])),
    }
    target = ROOT / args.out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded {len(components)} dependencies in {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
