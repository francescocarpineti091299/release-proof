"""Only an explicit unsupported key type is a measured PQC refusal."""

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rp_mcuboot.templates import PqcSignAttempt
from rp_runner.engine import RunContext
from rp_runner.proc import CmdResult


@pytest.mark.parametrize(
    "mode",
    [
        "timeout",
        "crash",
        "missing_key",
        "sign_timeout",
        "sign_crash",
        "missing_image",
        "refusal",
        "success",
    ],
)
def test_pqc_signing_outcomes(tmp_path, mode):
    observations = []
    ctx = RunContext(
        "audit", SimpleNamespace(), tmp_path, tmp_path / "artifacts", time.monotonic() + 1200
    )
    build = SimpleNamespace(
        part=lambda _: SimpleNamespace(size=262144), app_bin=tmp_path / "app.bin"
    )

    def command(argv, **kwargs):
        signing = "sign" in argv
        timed_out = mode == "timeout" or (signing and mode == "sign_timeout")
        rc = (
            None if timed_out else 1 if mode == "crash" or (signing and mode == "sign_crash") else 0
        )
        text = "tool crashed" if rc == 1 else "timeout" if timed_out else "success"
        if mode == "refusal":
            rc = 2
            text = f"Error: Invalid value for '--type': '{argv[-1]}' is not one of 'ecdsa-p256'."
        elif not signing and rc == 0 and mode != "missing_key":
            Path(argv[argv.index("-k") + 1]).write_text("test key")
        elif signing and mode == "success":
            Path(argv[-1]).write_bytes(b"signed test image")
        log = kwargs["log_path"]
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("$ command\n" + text)
        return CmdResult(list(argv), rc, timed_out, 1, log)

    def observation(*args, **kwargs):
        observations.append(args[4])
        return "OBS"

    with (
        patch("rp_mcuboot.templates.ensure_build", return_value=build),
        patch("rp_mcuboot.templates.imgtool_help", return_value=(0, "2.2.0")),
        patch("rp_mcuboot.templates._git_sha", return_value="a" * 40),
        patch("rp_mcuboot.templates.run_cmd", side_effect=command),
        patch("rp_mcuboot.templates.register", return_value="ART"),
        patch("rp_mcuboot.templates._obs", side_effect=observation),
    ):
        result = PqcSignAttempt().run(ctx)
    if mode == "success":
        assert result.outcome == "PASS"
        assert observations[0]["signing_result"] == "OK"
    elif mode == "refusal":
        assert result.outcome == "FAIL"
        assert observations[0]["signing_result"] == "REJECTED"
    else:
        assert result.outcome == "ERROR"
        assert result.failure_class == ("TIMEOUT" if "timeout" in mode else "TOOL_FAILURE")
        assert observations == []


def test_workspace_failure_is_cached_without_retrying_partial_copy(tmp_path):
    from rp_mcuboot.build import ensure_build
    from rp_runner.engine import EnvironmentFailure

    ctx = RunContext("test", SimpleNamespace(), tmp_path, tmp_path, time.monotonic() + 1200)
    with patch("rp_mcuboot.build._build", side_effect=PermissionError("unwritable")) as build:
        for _ in range(2):
            with pytest.raises(EnvironmentFailure, match="unwritable"):
                ensure_build(ctx)
    assert build.call_count == 1
