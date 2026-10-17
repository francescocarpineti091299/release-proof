"""Record the actual local images/security settings and verify executable source identities.

No container environment or credentials are exported. This is deployment evidence, not AMD
GPU attestation, a signature, or a substitute for fresh acceptance.
"""

import argparse
import json
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from acceptance import implementation_identity, runner_source_digest

ROOT = Path(__file__).resolve().parents[1]
SSH_HOST: str | None = None
SSH_KEY: str | None = None


def docker(*args):
    command = ["docker", *args]
    if SSH_HOST:
        command = [
            "ssh",
            "-i",
            SSH_KEY,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=15",
            SSH_HOST,
            shlex.join(command),
        ]
    return subprocess.check_output(command, text=True, encoding="utf-8")


def main():
    global SSH_HOST, SSH_KEY
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-host", help="Inspect a remote Docker host, e.g. ubuntu@<VM-IP>")
    parser.add_argument("--ssh-key", help="Existing key path; not included in the report")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/RELEASE_EVIDENCE.json")
    args = parser.parse_args()
    if bool(args.ssh_host) != bool(args.ssh_key):
        parser.error("--ssh-host and --ssh-key must be supplied together")
    SSH_HOST, SSH_KEY = args.ssh_host, args.ssh_key
    names = [
        "releaseproof-" + name + "-1"
        for name in ("api", "web", "runner-wolfboot", "runner-mcuboot", "caddy")
    ]
    inspected = json.loads(docker("inspect", *names))
    containers = []
    for item in inspected:
        subpaths = {
            m["Target"]: (m.get("VolumeOptions") or {}).get("Subpath")
            for m in item["HostConfig"].get("Mounts") or []
        }
        containers.append(
            {
                "name": item["Name"],
                "image_id": item["Image"],
                "image_reference": item["Config"]["Image"],
                "user": item["Config"].get("User"),
                "privileged": item["HostConfig"]["Privileged"],
                "cap_drop": item["HostConfig"].get("CapDrop"),
                "mounts": [
                    {
                        "target": m["Destination"],
                        "type": m["Type"],
                        "volume": m.get("Name"),
                        "writable": m["RW"],
                        "subpath": subpaths.get(m["Destination"]),
                    }
                    for m in item["Mounts"]
                ],
                "networks": sorted(item["NetworkSettings"]["Networks"]),
            }
        )
    remote_backend = json.loads(
        docker(
            "exec",
            "releaseproof-api-1",
            "python",
            "-c",
            "import json; "
            "from releaseproof.orchestrator.identity import implementation_identity; "
            "print(json.dumps(implementation_identity()))",
        )
    )
    matches = {"backend": remote_backend == implementation_identity()}
    for family, cls, py in (
        ("wolfboot", "WolfbootFamily", "python3"),
        ("mcuboot", "McubootFamily", "python"),
    ):
        remote = json.loads(
            docker(
                "exec",
                f"releaseproof-runner-{family}-1",
                py,
                "-c",
                "import json; from rp_runner.identity import code_identity; "
                f"from rp_{family}.family import {cls}; "
                f"print(json.dumps(code_identity({cls}())))",
            )
        )
        matches[family] = remote["releaseproof_runner_code_sha256"] == runner_source_digest(family)
    report = {
        "format": "releaseproof.deployment-evidence/1",
        "generated_at": datetime.now(UTC).isoformat(),
        "containers": containers,
        "implementation": remote_backend,
        "source_matches_worktree": matches,
        "runner_network_internal": json.loads(docker("network", "inspect", "releaseproof_runners"))[
            0
        ]["Internal"],
        "scope": (
            "remote Compose over SSH; source checked against this worktree; no GPU attestation"
            if SSH_HOST
            else "local Compose deployment, not public-cloud/hardware attestation"
        ),
    }
    target = args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(matches))
    return 0 if all(matches.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
