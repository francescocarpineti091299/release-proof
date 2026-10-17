"""Per-run keys, Zephyr/MCUboot sysbuild, imgtool signing and flash image composition."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rp_runner.engine import BuildFailed, EnvironmentFailure, RunContext
from rp_runner.proc import run_cmd

from rp_mcuboot import config as C


def register(ctx: RunContext, path: Path, kind: str, test_id: str | None = None) -> str:
    """Register a file under artifact_dir once per run; returns its artifact id."""
    reg: dict[str, str] = ctx.cache.setdefault("artifacts", {})
    key = str(path.resolve())
    if key not in reg:
        reg[key] = ctx.sink.artifact(path, kind=kind, test_id=test_id)
    return reg[key]


def publish(
    ctx: RunContext, src: Path, rel: str, kind: str, test_id: str | None = None
) -> tuple[Path, str]:
    dst = ctx.artifact_path(*rel.split("/"))
    shutil.copyfile(src, dst)
    return dst, register(ctx, dst, kind, test_id)


def rel_artifact(ctx: RunContext, path: Path) -> str:
    return path.resolve().relative_to(ctx.artifact_dir.resolve()).as_posix()


@dataclass
class Key:
    label: str
    private_pem: Path
    public_pem: Path  # artifact
    public_sha256: str  # sha256(DER SubjectPublicKeyInfo) == MCUboot KEYHASH TLV
    artifact_id: str


def _imgtool(*args: Any) -> list[str]:
    return [C.PYTHON, str(C.IMGTOOL), *[str(a) for a in args]]


def _public_der(private_pem: Path) -> bytes:
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(private_pem.read_bytes(), password=None)
    return key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def ensure_key(ctx: RunContext, label: str, test_id: str | None = None) -> Key:
    keys: dict[str, Key] = ctx.cache.setdefault("keys", {})
    if label in keys:
        return keys[label]
    kdir = ctx.workdir / "keys"
    kdir.mkdir(parents=True, exist_ok=True)
    priv = kdir / f"{label}-ecdsa-p256.pem"
    res = run_cmd(
        _imgtool("keygen", "-k", priv, "-t", "ecdsa-p256"),
        cwd=ctx.workdir,
        log_path=ctx.artifact_path("keys", f"keygen-{label}.log"),
        sink=ctx.sink,
        stream="sign",
        test_id=test_id,
        timeout_s=60,
    )
    if not res.ok or not priv.exists():
        raise BuildFailed(f"imgtool keygen ({label}) failed", res.log_path)
    from cryptography.hazmat.primitives import serialization

    der = _public_der(priv)
    pub = ctx.artifact_path("keys", f"{label}-ecdsa-p256.pub.pem")
    pub.write_bytes(
        serialization.load_der_public_key(der).public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    aid = register(ctx, pub, "other", test_id)
    key = Key(label, priv, pub, hashlib.sha256(der).hexdigest(), aid)
    keys[label] = key
    ctx.sink.log(
        "sign", f"ephemeral {label} key ecdsa-p256 public sha256={key.public_sha256}", test_id
    )
    return key


_PART_RE = re.compile(
    r"(?P<label>[A-Za-z0-9_]+)\s*:\s*partition@(?P<unit>[0-9a-fA-F]+)\s*\{(?P<body>[^{}]*)\}",
    re.S,
)
_REG_RE = re.compile(r"reg\s*=\s*<\s*(0x[0-9a-fA-F]+|\d+)\s+(0x[0-9a-fA-F]+|\d+)\s*>")
_LABEL_RE = re.compile(r'label\s*=\s*"([^"]*)"')
_ERASE_RE = re.compile(r"erase-block-size\s*=\s*<\s*(0x[0-9a-fA-F]+|\d+)\s*>")


@dataclass
class Partition:
    node_label: str
    label: str
    address: int
    size: int
    line: int


def parse_partitions(dts: Path) -> dict[str, Partition]:
    text = dts.read_text(encoding="utf-8", errors="replace")
    parts: dict[str, Partition] = {}
    for m in _PART_RE.finditer(text):
        reg = _REG_RE.search(m.group("body"))
        if not reg:
            continue
        lab = _LABEL_RE.search(m.group("body"))
        parts[m.group("label")] = Partition(
            node_label=m.group("label"),
            label=lab.group(1) if lab else "",
            address=int(reg.group(1), 0),
            size=int(reg.group(2), 0),
            line=text.count("\n", 0, m.start()) + 1,
        )
    return parts


def parse_erase_block(dts: Path) -> int | None:
    m = _ERASE_RE.search(dts.read_text(encoding="utf-8", errors="replace"))
    return int(m.group(1), 0) if m else None


def parse_kconfig(path: Path) -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if line.startswith("CONFIG_") or line.startswith("SB_CONFIG_"):
            k, _, v = line.partition("=")
            out[k] = (v.strip().strip('"'), n)
        elif line.startswith("# ") and line.endswith(" is not set"):
            out[line[2:-11]] = ("n", n)
    return out


@dataclass
class Build:
    build_dir: Path
    log: Path
    log_artifact: str
    key: Key
    mcuboot_elf: Path
    mcuboot_bin: Path
    app_bin: Path
    mcuboot_dts: Path
    app_dts: Path
    mcuboot_config: Path
    app_config: Path
    sysbuild_config: Path
    partitions: dict[str, Partition]
    sector_size: int | None
    artifacts: dict[str, str] = field(default_factory=dict)  # logical name -> artifact id
    duration_ms: int = 0

    def part(self, name: str) -> Partition:
        if name not in self.partitions:
            raise BuildFailed(f"partition {name} not found in {self.mcuboot_dts.name}")
        return self.partitions[name]


def ensure_build(ctx: RunContext, test_id: str | None = None) -> Build:
    """One sysbuild (MCUboot embedding this run's deployed key + demo app) per run."""
    cached = ctx.cache.get("build")
    if isinstance(cached, BuildFailed | EnvironmentFailure):
        raise cached
    if cached is not None:
        return cached
    try:
        build = _build(ctx, test_id)
    except (BuildFailed, EnvironmentFailure) as exc:
        ctx.cache["build"] = exc
        raise
    except OSError as exc:
        failure = EnvironmentFailure(f"build workspace unavailable: {exc}")
        ctx.cache["build"] = failure
        raise failure from exc
    ctx.cache["build"] = build
    return build


def _build(ctx: RunContext, test_id: str | None) -> Build:
    if not C.ZEPHYR_BASE.is_dir() or not C.ARM_GCC.exists():
        raise EnvironmentFailure(
            "Zephyr workspace or arm-zephyr-eabi toolchain missing in the image"
        )
    key = ensure_key(ctx, "deployed", test_id)
    src = ctx.workdir / "src" / C.APP_IMAGE
    shutil.copytree(C.APP_SRC, src)
    # Keep private keys inside the disposable run workspace, including during image warmup.
    # A fixed /tmp key path leaked warmup state into the image and broke non-root execution.
    staged = key.private_pem
    with (src / "sysbuild.conf").open("a", encoding="utf-8") as fh:
        fh.write(f'SB_CONFIG_BOOT_SIGNATURE_KEY_FILE="{staged}"\n')
    bdir = ctx.workdir / "build"
    argv = [
        "west",
        "build",
        "-p",
        "always",
        "-b",
        C.BOARD,
        "--sysbuild",
        "-d",
        str(bdir),
        str(src),
        "--",
        f"-Dmcuboot_EXTRA_CONF_FILE={src / 'mcuboot_extra' / 'mcuboot.conf'}",
        f"-Dmcuboot_EXTRA_DTC_OVERLAY_FILE={src / 'mcuboot_extra' / 'mcuboot.overlay'}",
    ]
    log = ctx.artifact_path("build", "sysbuild.log")
    ctx.sink.log(
        "build",
        f"west build --sysbuild {C.BOARD} (MCUboot ECDSA-P256 swap-using-move + demo app)",
        test_id,
    )
    res = run_cmd(
        argv,
        cwd=C.ZWS,
        log_path=log,
        sink=ctx.sink,
        stream="build",
        test_id=test_id,
        timeout_s=min(900, ctx.remaining()),
        echo_every=10,
    )
    log_aid = register(ctx, log, "log", test_id)
    if not res.ok:
        tail = _tail(log, 15)
        raise BuildFailed(
            f"west build failed (rc={res.returncode}, timeout={res.timed_out}): {tail}", log
        )
    mz = bdir / "mcuboot" / "zephyr"
    az = bdir / C.APP_IMAGE / "zephyr"
    need = {
        "mcuboot_elf": mz / "zephyr.elf",
        "mcuboot_bin": mz / "zephyr.bin",
        "mcuboot_dts": mz / "zephyr.dts",
        "mcuboot_config": mz / ".config",
        "app_elf": az / "zephyr.elf",
        "app_bin": az / "zephyr.bin",
        "app_dts": az / "zephyr.dts",
        "app_config": az / ".config",
        "sysbuild_config": bdir / "zephyr" / ".config",
    }
    missing = [str(p) for p in need.values() if not p.exists()]
    if missing:
        raise BuildFailed(f"build outputs missing: {missing}", log)
    kinds = {"elf": "elf", "bin": "bin", "dts": "config", "config": "config"}
    published: dict[str, Path] = {}
    aids: dict[str, str] = {"build_log": log_aid}
    names = {
        "mcuboot_elf": "mcuboot.elf",
        "mcuboot_bin": "mcuboot.bin",
        "mcuboot_dts": "mcuboot.zephyr.dts",
        "mcuboot_config": "mcuboot.config",
        "app_elf": "app.elf",
        "app_bin": "app.unsigned.bin",
        "app_dts": "app.zephyr.dts",
        "app_config": "app.config",
        "sysbuild_config": "sysbuild.config",
    }
    for logical, path in need.items():
        kind = kinds[logical.rsplit("_", 1)[1]]
        dst, aid = publish(ctx, path, f"build/{names[logical]}", kind, test_id)
        published[logical] = dst
        aids[logical] = aid
    parts = parse_partitions(published["mcuboot_dts"])
    build = Build(
        build_dir=bdir,
        log=log,
        log_artifact=log_aid,
        key=key,
        mcuboot_elf=published["mcuboot_elf"],
        mcuboot_bin=published["mcuboot_bin"],
        app_bin=published["app_bin"],
        mcuboot_dts=published["mcuboot_dts"],
        app_dts=published["app_dts"],
        mcuboot_config=published["mcuboot_config"],
        app_config=published["app_config"],
        sysbuild_config=published["sysbuild_config"],
        partitions=parts,
        sector_size=parse_erase_block(published["mcuboot_dts"]),
        artifacts=aids,
        duration_ms=res.duration_ms,
    )
    for name in ("boot_partition", "slot0_partition", "slot1_partition"):
        build.part(name)
    ctx.sink.log("build", f"sysbuild done in {res.duration_ms} ms", test_id)
    return build


def _tail(path: Path, n: int) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return " | ".join(line.strip() for line in lines[-n:] if line.strip())[-1500:]


@dataclass
class Signed:
    name: str
    path: Path
    artifact_id: str
    version: str
    key: Key
    padded: bool


def sign(
    ctx: RunContext,
    build: Build,
    name: str,
    *,
    key: Key,
    version: str,
    slot: str,
    pad: bool,
    test_id: str | None = None,
) -> Signed:
    images: dict[str, Signed] = ctx.cache.setdefault("signed", {})
    if name in images:
        return images[name]
    out = ctx.artifact_path("images", f"{name}.signed.bin")
    argv = _imgtool(
        "sign",
        "--key",
        key.private_pem,
        "--header-size",
        hex(C.HEADER_SIZE),
        "--align",
        C.ALIGN,
        "--version",
        version,
        "--slot-size",
        hex(build.part(slot).size),
    )
    if pad:
        argv.append("--pad")
    argv += [build.app_bin, out]
    res = run_cmd(
        argv,
        cwd=ctx.workdir,
        log_path=ctx.artifact_path("images", f"{name}.sign.log"),
        sink=ctx.sink,
        stream="sign",
        test_id=test_id,
        timeout_s=120,
    )
    register(ctx, res.log_path, "log", test_id)
    if not res.ok or not out.exists():
        raise BuildFailed(f"imgtool sign {name} failed: {_tail(res.log_path, 6)}", res.log_path)
    signed = Signed(name, out, register(ctx, out, "signed_image", test_id), version, key, pad)
    images[name] = signed
    return signed


def tampered_copy(
    ctx: RunContext, src: Signed, name: str, test_id: str | None = None
) -> tuple[Signed, int]:
    """Flip one byte inside the signed payload (after the 0x200 header)."""
    images: dict[str, Signed] = ctx.cache.setdefault("signed", {})
    offset = C.HEADER_SIZE + 0x100
    if name in images:
        return images[name], offset
    data = bytearray(src.path.read_bytes())
    data[offset] ^= 0x01
    out = ctx.artifact_path("images", f"{name}.signed.bin")
    out.write_bytes(bytes(data))
    signed = Signed(
        name, out, register(ctx, out, "signed_image", test_id), src.version, src.key, src.padded
    )
    images[name] = signed
    ctx.sink.log("sign", f"{name}: flipped bit 0 of byte 0x{offset:x} of {src.name}", test_id)
    return signed, offset


def compose_flash(
    ctx: RunContext, build: Build, slot0: Signed, name: str, test_id: str | None = None
) -> tuple[Path, str]:
    """Power-on flash content: erased (0xFF) 1 MiB, MCUboot at 0x0, the slot-0 image."""
    cache: dict[str, tuple[Path, str]] = ctx.cache.setdefault("flash", {})
    if name in cache:
        return cache[name]
    buf = bytearray(b"\xff" * C.FLASH_SIZE)
    boot = build.part("boot_partition")
    mcu = build.mcuboot_bin.read_bytes()
    if len(mcu) > boot.size:
        raise BuildFailed(f"MCUboot ({len(mcu)} B) larger than boot_partition ({boot.size} B)")
    buf[boot.address : boot.address + len(mcu)] = mcu
    s0 = build.part("slot0_partition")
    img = slot0.path.read_bytes()
    if len(img) > s0.size:
        raise BuildFailed(f"{slot0.name} ({len(img)} B) larger than slot0 ({s0.size} B)")
    buf[s0.address : s0.address + len(img)] = img
    out = ctx.artifact_path("renode", f"{name}.flash.bin")
    out.write_bytes(bytes(buf))
    res = (out, register(ctx, out, "bin", test_id))
    cache[name] = res
    return res


def imgtool_help(args: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(_imgtool(*args), capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


_TYPES_RE = re.compile(r"-t,\s*--type\s+\S+\s+One of:\s*(?P<list>.*?)\s*\[required\]", re.S)
_TYPES_BRACKET_RE = re.compile(r"--type\s*\[(?P<list>[^\]]+)\]")


def parse_key_types(help_text: str) -> list[str]:
    m = _TYPES_RE.search(help_text)
    if m:
        return [t.strip() for t in re.split(r"[,\s]+", m.group("list")) if t.strip()]
    m = _TYPES_BRACKET_RE.search(help_text)
    if m:
        return [t.strip() for t in m.group("list").split("|") if t.strip()]
    return []
