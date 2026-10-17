"""MCUboot family: environment checks, tool versions and source pins."""

from __future__ import annotations

import shutil
import subprocess
import threading

from rp_runner.engine import EnvironmentFailure, Family, RunContext
from rp_runner.proc import tool_version

from rp_mcuboot import config as C
from rp_mcuboot.build import register
from rp_mcuboot.templates import TEMPLATES

_lock = threading.Lock()
_versions: dict[str, str] | None = None


class McubootFamily(Family):
    name = "mcuboot"
    templates = TEMPLATES

    def prepare(self, ctx: RunContext) -> None:
        missing = []
        for label, path in (
            ("zephyr workspace", C.ZEPHYR_BASE),
            ("mcuboot", C.MCUBOOT_DIR),
            ("imgtool", C.IMGTOOL),
            ("arm-zephyr-eabi-gcc", C.ARM_GCC),
            ("nRF52840 SVD", C.SVD_PATH),
            ("NVMC model", C.NVMC_CS),
            ("west manifest freeze", C.MANIFEST_FREEZE),
        ):
            if not path.exists():
                missing.append(f"{label} ({path})")
        for exe in (C.RENODE, "west", "cmake", "ninja"):
            if shutil.which(exe) is None:
                missing.append(exe)
        if missing:
            raise EnvironmentFailure("runner image incomplete: " + ", ".join(missing))
        for src, name in (
            (C.MANIFEST_FREEZE, "west-manifest.freeze.yml"),
            (C.PIP_FREEZE, "pip-freeze.txt"),
        ):
            if src.exists():
                dst = ctx.artifact_path("toolchain", name)
                dst.write_bytes(src.read_bytes())
                aid = register(ctx, dst, "manifest")
                if name.startswith("west"):
                    ctx.cache["manifest_path"] = dst
                    ctx.cache["manifest_aid"] = aid
        ctx.sink.log(
            "runner", f"workdir {ctx.workdir}; Zephyr {C.ZEPHYR_VERSION}, Renode {C.RENODE_VERSION}"
        )

    def tool_versions(self) -> dict[str, str]:
        global _versions
        with _lock:
            if _versions is None:
                _versions = {
                    "renode": tool_version([C.RENODE, "--version"]),
                    "arm-zephyr-eabi-gcc": tool_version([str(C.ARM_GCC), "--version"]),
                    "zephyr-sdk": C.SDK_VERSION,
                    "imgtool": tool_version([C.PYTHON, str(C.IMGTOOL), "version"]),
                    "west": tool_version(["west", "--version"]),
                    "cmake": tool_version(["cmake", "--version"]),
                    "python": tool_version([C.PYTHON, "--version"]),
                }
            return dict(_versions)

    def source_pins(self) -> dict[str, str]:
        pins: dict[str, str] = {"zephyr_version": C.ZEPHYR_VERSION}
        try:
            head = subprocess.run(
                ["git", "-C", str(C.ZEPHYR_BASE), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=20,
            ).stdout.strip()
            if head:
                pins["zephyr"] = head
        except (OSError, subprocess.TimeoutExpired):
            pass
        if C.WEST_LIST.exists():
            for line in C.WEST_LIST.read_text().splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[0] != "manifest":
                    pins[parts[0]] = parts[2]
        if C.SVD_PATH.with_suffix(".gz.sha256").exists():
            pins["nrf52840_svd_sha256"] = (
                C.SVD_PATH.with_suffix(".gz.sha256").read_text().split()[0]
            )
        return pins
