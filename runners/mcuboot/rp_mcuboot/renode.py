"""Renode scenarios: generate a per-run .resc, run headless with virtual time, parse the UART."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from rp_runner.engine import EnvironmentFailure, RunContext
from rp_runner.proc import run_cmd

from rp_mcuboot import config as C
from rp_mcuboot.build import register

MARKER_RE = re.compile(
    r"RP-APP version=(?P<major>\d+)\.(?P<minor>\d+)\.(?P<rev>\d+) build=(?P<build>\d+) "
    r"key=(?P<key>[0-9a-f]{16}|none) slot=(?P<slot>0x[0-9a-f]+)"
)
MCUBOOT_BANNER = "*** Booting MCUboot"
JUMP = "Jumping to the first image slot"
INVALID_RE = re.compile(r"Image in the (?P<slot>primary|secondary) slot is not valid")
NO_BOOTABLE = "Unable to find bootable image"
SWAP_START = "Starting swap using move algorithm"
SWAP_TYPE_RE = re.compile(r"Swap type: (?P<type>\w+)")


@dataclass
class Marker:
    major: int
    minor: int
    rev: int
    key: str
    line: int
    text: str

    @property
    def version(self) -> str:
        return f"{self.major}.{self.minor}.{self.rev}"


@dataclass
class Phase:
    """UART capture of one power-on/reset phase."""

    path: Path
    artifact_id: str
    lines: list[str]

    def find(self, needle: str) -> int | None:
        for n, line in enumerate(self.lines, 1):
            if needle in line:
                return n
        return None

    def find_re(self, rx: re.Pattern[str]) -> tuple[int, re.Match[str]] | tuple[None, None]:
        for n, line in enumerate(self.lines, 1):
            m = rx.search(line)
            if m:
                return n, m
        return None, None

    def markers(self) -> list[Marker]:
        out = []
        for n, line in enumerate(self.lines, 1):
            m = MARKER_RE.search(line)
            if m:
                out.append(
                    Marker(int(m["major"]), int(m["minor"]), int(m["rev"]), m["key"], n, line.strip())
                )
        return out

    def loc(self, line: int | None) -> str:
        return f"{self.path.name}:L{line}" if line else self.path.name


@dataclass
class ScenarioResult:
    name: str
    phases: list[Phase]
    resc_artifact: str
    renode_log_artifact: str
    returncode: int | None
    timed_out: bool
    duration_ms: int
    artifact_ids: list[str] = field(default_factory=list)

    @property
    def completed(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def _repl(ctx: RunContext) -> tuple[Path, list[str]]:
    cached = ctx.cache.get("repl")
    if cached:
        return cached
    if not C.SVD_PATH.exists():
        raise EnvironmentFailure(f"nRF52840 SVD missing at {C.SVD_PATH}")
    text = C.REPL_TEMPLATE.read_text(encoding="utf-8").replace("{SVD_PATH}", str(C.SVD_PATH))
    repl = ctx.artifact_path("renode", "nrf52840_rp.repl")
    repl.write_text(text, encoding="utf-8")
    cs = ctx.artifact_path("renode", C.NVMC_CS.name)
    cs.write_bytes(C.NVMC_CS.read_bytes())
    aids = [register(ctx, repl, "script"), register(ctx, cs, "script")]
    ctx.cache["repl"] = (repl, aids)
    return repl, aids


def run_scenario(
    ctx: RunContext,
    name: str,
    *,
    test_id: str,
    flash_image: Path,
    staged_slot1: Path | None = None,
    slot1_address: int = 0,
    phase1: str = "00:00:03",
    phase2: str = "00:00:05",
    wall_timeout_s: float = 180,
) -> ScenarioResult:
    repl, repl_aids = _repl(ctx)
    sdir = ctx.artifact_path("renode", name, "x").parent
    uart1 = sdir / "uart-phase1-power-on.log"
    uart2 = sdir / "uart-phase2-after-reset.log"
    rlog = sdir / "renode.log"
    # Renode failing before opening its backends must not expose an old capture.
    for previous in (uart1, uart2, rlog):
        if previous.exists():
            previous.unlink()
    phase2_block = ""
    if staged_slot1 is not None:
        phase2_block = "\n".join(
            [
                f"sysbus.uart0 CloseFileBackend @{uart1}",
                f"sysbus.uart0 CreateFileBackend @{uart2} true",
                "# Staged update written to slot 1 (as the running application would), then reset.",
                f"sysbus LoadBinary @{staged_slot1} 0x{slot1_address:x}",
                "machine Reset",
                f'emulation RunFor "{phase2}"',
            ]
        )
    resc_text = (
        C.RESC_TEMPLATE.read_text(encoding="utf-8")
        .replace("{RENODE_LOG}", str(rlog))
        .replace("{NVMC_CS}", str(C.NVMC_CS))
        .replace("{REPL}", str(repl))
        .replace("{UART_LOG}", str(uart1))
        .replace("{FLASH_IMAGE}", str(flash_image))
        .replace("{PHASE1_TIME}", phase1)
        .replace("{PHASE2}", phase2_block)
    )
    resc = sdir / f"{name}.resc"
    resc.write_text(resc_text, encoding="utf-8")
    resc_aid = register(ctx, resc, "script", test_id)
    ctx.sink.log("renode", f"renode {name}: phase1={phase1}" + (f" reset phase2={phase2}" if staged_slot1 else ""), test_id)
    res = run_cmd(
        [C.RENODE, "--disable-xwt", "--console", "--plain", "--hide-log", str(resc)],
        cwd=sdir,
        log_path=sdir / "renode.stdout.log",
        sink=ctx.sink,
        stream="renode",
        test_id=test_id,
        timeout_s=min(wall_timeout_s, ctx.remaining()),
    )
    aids = list(repl_aids) + [resc_aid, register(ctx, res.log_path, "log", test_id)]
    rlog_aid = ""
    if rlog.exists():
        rlog_aid = register(ctx, rlog, "log", test_id)
        aids.append(rlog_aid)
    phases: list[Phase] = []
    for path in (uart1, uart2) if staged_slot1 is not None else (uart1,):
        if not path.exists():
            path.write_text("", encoding="utf-8")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        aid = register(ctx, path, "uart", test_id)
        aids.append(aid)
        phases.append(Phase(path, aid, lines))
        for line in lines:
            ctx.sink.log("uart", f"[{name}/{path.stem}] {line}", test_id)
    return ScenarioResult(
        name=name, phases=phases, resc_artifact=resc_aid, renode_log_artifact=rlog_aid,
        returncode=res.returncode, timed_out=res.timed_out, duration_ms=res.duration_ms,
        artifact_ids=aids,
    )
