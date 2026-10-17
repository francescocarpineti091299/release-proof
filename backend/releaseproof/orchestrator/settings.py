"""Runtime settings of the API/orchestrator process (environment driven)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    env: str = "dev"
    data_dir: Path = _REPO_ROOT / "data"
    # Path of data_dir as seen by the runner containers (same volume, maybe different mount).
    runner_data_dir: str = "/data"
    expose_experimental: bool = False
    runner_urls: dict[str, str] = field(default_factory=dict)
    cors_origins: tuple[str, ...] = ()
    sse_heartbeat_seconds: float = 15.0
    runner_connect_timeout: float = 10.0
    runner_grace_seconds: int = 120

    @property
    def db_path(self) -> Path:
        return self.data_dir / "releaseproof.sqlite"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def runner_artifact_dir(self, run_id: str) -> str:
        return f"{self.runner_data_dir.rstrip('/')}/runs/{run_id}/artifacts"

    def runner_url(self, family: str, service: str) -> str:
        return self.runner_urls.get(family) or f"http://{service}:8080"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        mode = env.get("RELEASEPROOF_ENV", "dev")
        data_dir = Path(env.get("RELEASEPROOF_DATA_DIR") or (_REPO_ROOT / "data"))
        runner_urls = {
            key[len("RUNNER_URL_") :].lower(): value.rstrip("/")
            for key, value in env.items()
            if key.startswith("RUNNER_URL_") and value
        }
        origins = [
            o.strip() for o in env.get("RELEASEPROOF_CORS_ORIGINS", "").split(",") if o.strip()
        ]
        if mode in {"dev", "test"} and "http://localhost:3000" not in origins:
            origins.append("http://localhost:3000")
        return cls(
            env=mode,
            data_dir=data_dir,
            runner_data_dir=env.get("RELEASEPROOF_RUNNER_DATA_DIR") or data_dir.as_posix(),
            expose_experimental=_flag(env.get("RELEASEPROOF_EXPOSE_EXPERIMENTAL")),
            runner_urls=runner_urls,
            cors_origins=tuple(origins),
            sse_heartbeat_seconds=float(env.get("RELEASEPROOF_SSE_HEARTBEAT_SECONDS", "15")),
        )
