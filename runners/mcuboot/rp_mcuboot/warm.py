"""Image-build self-test: one full run of every template (also warms ccache).

Fails the docker build only if the run cannot produce results (done.status == FAILED).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from rp_runner.engine import execute

from rp_mcuboot.family import McubootFamily
from rp_mcuboot.templates import TEMPLATES


def main() -> int:
    data = Path(tempfile.mkdtemp(prefix="rp-warm-data-"))
    events: list[dict] = []

    def write(line: str) -> None:
        ev = json.loads(line)
        events.append(ev)
        if ev["type"] in ("stage", "test_result", "error", "done"):
            print(
                json.dumps(
                    {k: v for k, v in ev.items() if k not in ("tool_versions", "source_pins")}
                )[:600],
                flush=True,
            )

    request = {
        "run_id": "RP-00000000T000000Z-000000",
        "profile_id": "nrf52840-mcuboot-pqc",
        "change_id": "ecdsa_p256_to_mldsa",
        "tests": [{"template_id": t} for t in TEMPLATES],
        "artifact_dir": str(data / "artifacts"),
        "timeout_seconds": 1200,
    }
    status = execute(McubootFamily(), request, write)
    shutil.rmtree(data, ignore_errors=True)
    return 0 if status == "SUCCEEDED" else 1


if __name__ == "__main__":
    sys.exit(main())
