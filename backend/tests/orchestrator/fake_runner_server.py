"""Dev helper: serve the fake runner family over real HTTP (UI/API plumbing only).

    cd backend
    .venv\\Scripts\\python.exe tests\\orchestrator\\fake_runner_server.py --port 28080
        --data-dir ..\\data

Then run the API with RUNNER_URL_WOLFBOOT / RUNNER_URL_MCUBOOT = http://127.0.0.1:28080 and the
same RELEASEPROOF_DATA_DIR. Facts are synthetic: never use this for a demo or a recorded run.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from rp_fakes import FakeFamily
from rp_runner.server import serve


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=28080)
    parser.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[3] / "data"))
    parser.add_argument("--fail", action="store_true", help="fail in PREPARING (ENVIRONMENT_SETUP)")
    args = parser.parse_args()
    os.environ["RELEASEPROOF_DATA_DIR"] = str(Path(args.data_dir).resolve())
    serve(FakeFamily(fail_prepare=args.fail), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
