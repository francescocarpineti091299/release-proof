"""Renode emulation with a generated per-run .resc, deterministic virtual time and UART to file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rp_runner.engine import EnvironmentFailure, RunContext
from rp_runner.proc import run_cmd

from rp_wolfboot import settings
from rp_wolfboot.parsers import UartCapture, parse_uart

BOOT_ADDRESS = 0x20000
UPDATE_ADDRESS = 0x60000


@dataclass
class Phase:
    name: str
    uart_path: Path
    capture: UartCapture
    artifact_id: str


@dataclass
class Emulation:
    ran: bool
    timed_out: bool
    returncode: int | None
    duration_ms: int
    phases: list[Phase] = field(default_factory=list)
    resc_artifact_id: str = ""
    log_artifact_id: str = ""

    def phase(self, name: str) -> Phase | None:
        return next((p for p in self.phases if p.name == name), None)

    @property
    def artifact_ids(self) -> list[str]:
        ids = [self.resc_artifact_id, self.log_artifact_id] + [p.artifact_id for p in self.phases]
        return [i for i in ids if i]


def _q(path: Path) -> str:
    text = str(path)
    if any(c in text for c in ' "@\n'):
        raise EnvironmentFailure(f"unsafe path for a Renode script: {text!r}")
    return "@" + text


def _virtual(seconds: float) -> str:
    whole = int(seconds)
    micros = int(round((seconds - whole) * 1_000_000))
    return f'"{whole // 3600:02d}:{(whole // 60) % 60:02d}:{whole % 60:02d}.{micros:06d}"'


def write_resc(
    path: Path,
    *,
    elf: Path,
    boot_image: Path,
    uart_boot: Path,
    update_image: Path | None,
    uart_update: Path | None,
    boot_s: float,
    update_s: float,
) -> None:
    """Same sequence as tools/renode/nrf52840_wolfboot.resc, but RunFor instead of wall-clock sleep."""
    lines = [
        ":name: ReleaseProof nRF52840 wolfBoot (generated per run)",
        "using sysbus",
        'mach create "rp-nrf52840"',
        f"machine LoadPlatformDescription @{settings.RENODE_PLATFORM}",
        "logLevel 3",
        f"uart0 CreateFileBackend {_q(uart_boot)} true",
        f"cpu PerformanceInMips {settings.RENODE_MIPS}",
        f"sysbus LoadELF {_q(elf)}",
        f"sysbus LoadBinary {_q(boot_image)} 0x{BOOT_ADDRESS:x}",
        f"emulation RunFor {_virtual(boot_s)}",
    ]
    if update_image is not None and uart_update is not None:
        lines += [
            f"uart0 CloseFileBackend {_q(uart_boot)}",
            f"uart0 CreateFileBackend {_q(uart_update)} true",
            "cpu Reset",
            f"sysbus LoadBinary {_q(update_image)} 0x{UPDATE_ADDRESS:x}",
            f"emulation RunFor {_virtual(update_s)}",
        ]
    lines += ["quit", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def emulate(
    ctx: RunContext,
    *,
    test_id: str,
    label: str,
    elf: Path,
    boot_image: Path,
    update_image: Path | None = None,
    boot_s: float = settings.BOOT_PHASE_VIRTUAL_S,
    update_s: float = settings.UPDATE_PHASE_VIRTUAL_S,
) -> Emulation:
    out = ctx.artifact_dir / label
    out.mkdir(parents=True, exist_ok=True)
    uart_boot = out / "uart_boot.bin"
    uart_update = out / "uart_update.bin" if update_image is not None else None
    for p in (uart_boot, uart_update):
        if p is not None and p.exists():
            p.unlink()
    resc = out / "run.resc"
    write_resc(
        resc,
        elf=elf,
        boot_image=boot_image,
        uart_boot=uart_boot,
        update_image=update_image,
        uart_update=uart_update,
        boot_s=boot_s,
        update_s=update_s,
    )
    sink = ctx.sink
    resc_id = sink.artifact(resc, kind="script", test_id=test_id)
    work = ctx.workdir / "renode" / label
    work.mkdir(parents=True, exist_ok=True)
    res = run_cmd(
        ["renode", "--disable-xwt", "--console", "--plain", str(resc)],
        cwd=work,
        log_path=out / "renode.log",
        sink=sink,
        stream="renode",
        test_id=test_id,
        env={"HOME": str(work), "TMPDIR": str(work)},
        timeout_s=min(settings.EMULATION_WALL_TIMEOUT_S, ctx.remaining()),
        echo_every=1,
    )
    emu = Emulation(
        ran=res.returncode is not None,
        timed_out=res.timed_out,
        returncode=res.returncode,
        duration_ms=res.duration_ms,
        resc_artifact_id=resc_id,
        log_artifact_id=sink.artifact(res.log_path, kind="log", test_id=test_id),
    )
    for name, path in (("boot", uart_boot), ("update", uart_update)):
        if path is None:
            continue
        raw = path.read_bytes() if path.is_file() else b""
        if not path.is_file():
            path.write_bytes(b"")
        capture = parse_uart(raw)
        aid = sink.artifact(path, kind="uart", test_id=test_id)
        emu.phases.append(Phase(name, path, capture, aid))
        for line in capture.lines:
            if line.strip():
                sink.log("uart", f"[{label}/{name}] {line}", test_id=test_id)
        if capture.frames:
            sink.log(
                "uart",
                f"[{label}/{name}] version frames: "
                + ", ".join(f"{f.version} @0x{f.offset:x} ({f.raw_hex})" for f in capture.frames),
                test_id=test_id,
            )
    return emu
