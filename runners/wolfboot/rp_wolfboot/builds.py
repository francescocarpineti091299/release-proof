"""Per-run wolfBoot trees and memoised builds (deployed ECC256, candidate ML-DSA-87, hybrid)."""

from __future__ import annotations

import os
import re
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path

from rp_runner.engine import BuildFailed, EnvironmentFailure, RunContext
from rp_runner.proc import CmdResult, run_cmd

from rp_wolfboot import settings
from rp_wolfboot.parsers import apply_make_args, parse_config, parse_target_h, to_int

# Collected after a successful build: key -> (path relative to the tree, artifact kind)
_OUTPUTS = {
    "wolfboot_elf": ("wolfboot.elf", "elf"),
    "wolfboot_bin": ("wolfboot.bin", "bin"),
    "app_bin": ("test-app/image.bin", "bin"),
    "image_v1": ("test-app/image_v1_signed.bin", "signed_image"),
    "image_v2": (f"test-app/image_v{settings.TEST_UPDATE_VERSION}_signed.bin", "signed_image"),
    "keystore": ("keystore.der", "other"),
    "config": (".config", "config"),
    "target_h": ("include/target.h", "config"),
}


@dataclass
class Build:
    name: str
    make_args: list[str]
    tree: Path
    files: dict[str, Path] = field(default_factory=dict)  # copies under artifact_dir
    artifact_ids: dict[str, str] = field(default_factory=dict)
    target: dict[str, int] = field(default_factory=dict)
    effective: dict[str, tuple[str, int]] = field(default_factory=dict)
    update_image: Path | None = None

    @property
    def header_size(self) -> int:
        value = to_int(self.effective.get("IMAGE_HEADER_SIZE", ("", 0))[0])
        return value if value is not None else settings.ECC_DEFAULT_HEADER_SIZE

    def size(self, key: str) -> int:
        return self.files[key].stat().st_size

    def layout(self) -> dict[str, int | None]:
        return {
            "boot_partition_address": self.target.get("WOLFBOOT_PARTITION_BOOT_ADDRESS"),
            "update_partition_address": self.target.get("WOLFBOOT_PARTITION_UPDATE_ADDRESS"),
            "swap_address": self.target.get("WOLFBOOT_PARTITION_SWAP_ADDRESS"),
            "partition_size_bytes": self.target.get("WOLFBOOT_PARTITION_SIZE"),
            "sector_size_bytes": self.target.get("WOLFBOOT_SECTOR_SIZE"),
        }


def _copy_writable(src: str, dst: str) -> str:
    shutil.copy2(src, dst, follow_symlinks=False)
    if not os.path.islink(dst):
        os.chmod(dst, os.stat(dst).st_mode | stat.S_IWUSR)
    return dst


def prepare_tree(ctx: RunContext, name: str) -> Path:
    """Fresh copy of the baked (read-only) pinned tree; the baked tree is never mutated."""
    if not (settings.BAKED_TREE / "Makefile").is_file():
        raise EnvironmentFailure(f"pinned wolfBoot tree missing at {settings.BAKED_TREE}")
    dest = ctx.workdir / name / "wolfBoot"
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(
            settings.BAKED_TREE,
            dest,
            symlinks=True,
            ignore=shutil.ignore_patterns(*settings.COPY_IGNORE),
            copy_function=_copy_writable,
        )
    except OSError as exc:
        raise EnvironmentFailure(f"cannot copy pinned tree: {exc}") from exc
    for d, _dirs, _files in os.walk(dest):
        os.chmod(d, os.stat(d).st_mode | stat.S_IWUSR)
    return dest


def make_env(tree: Path) -> dict[str, str]:
    return {"WOLFBOOT_ROOT": str(tree), "PWD": str(tree), "LC_ALL": "C"}


def make_steps(tree: Path, out_dir: Path, args: list[str], *, update_image: bool) -> list[tuple[str, list[str]]]:
    """Steps of tools/scripts/renode-test-update.sh, with per-run paths instead of /tmp.

    Serial make, as in the reference script: ``-j`` races on key generation for the hybrid build.
    """
    steps = [
        ("keysclean", ["make", "keysclean"]),
        ("keytools", ["make", "keytools"]),
        ("clean", ["make", "clean"]),
        ("build", ["make", *args]),
    ]
    if update_image:
        target = out_dir / "renode-test-update.bin"
        steps.append(("update_image", ["make", str(target), f"TMP={out_dir}", *args]))
    return steps


def find_lines(path: Path, pattern: str) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    rx = re.compile(pattern)
    return [(n, line.strip()) for n, line in enumerate(text, start=1) if rx.search(line)]


def error_lines(log_path: Path, limit: int = 6) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return hits
    numbered = list(enumerate(text, start=1))
    compiler = [(n, s.strip()[:300]) for n, s in numbered if re.search(r"\berror:", s)]
    make_err = [(n, s.strip()[:300]) for n, s in numbered if "***" in s]
    return (compiler + make_err)[:limit]


def run_steps(
    ctx: RunContext,
    tree: Path,
    steps: list[tuple[str, list[str]]],
    log_dir: Path,
    test_id: str,
) -> tuple[list[tuple[str, CmdResult]], tuple[str, CmdResult] | None]:
    """Run steps in order; returns (results, first_failed_step_or_None)."""
    results: list[tuple[str, CmdResult]] = []
    env = make_env(tree)
    for idx, (label, argv) in enumerate(steps, start=1):
        log_path = log_dir / f"{idx:02d}_{label}.log"
        res = run_cmd(
            argv,
            cwd=tree,
            log_path=log_path,
            sink=ctx.sink,
            stream="build",
            test_id=test_id,
            env=env,
            timeout_s=min(settings.MAKE_TIMEOUT_S, ctx.remaining()),
            echo_every=25,
        )
        results.append((label, res))
        if not res.ok:
            return results, (label, res)
    return results, None


def register_logs(ctx: RunContext, results: list[tuple[str, CmdResult]], test_id: str) -> dict[str, str]:
    return {
        label: ctx.sink.artifact(res.log_path, kind="log", test_id=test_id) for label, res in results
    }


def get_build(ctx: RunContext, name: str, test_id: str) -> Build:
    """Memoised per run. A failed build is remembered and re-raised for every dependent test."""
    key = f"build:{name}"
    cached = ctx.cache.get(key)
    if isinstance(cached, Build):
        return cached
    if isinstance(cached, BuildFailed):
        raise cached
    try:
        build = _do_build(ctx, name, test_id)
    except BuildFailed as exc:
        ctx.cache[key] = exc
        raise
    ctx.cache[key] = build
    return build


_VARIANTS = {"ecc": settings.ECC_MAKE_ARGS, "mldsa": settings.MLDSA_MAKE_ARGS}


def _do_build(ctx: RunContext, name: str, test_id: str) -> Build:
    args = list(_VARIANTS[name])
    sink = ctx.sink
    sink.log("runner", f"[{name}] preparing isolated tree; make args: {' '.join(args)}", test_id=test_id)
    tree = prepare_tree(ctx, name)
    out_dir = ctx.workdir / name / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    art_dir = ctx.artifact_dir / f"build_{name}"
    art_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tree / settings.BOARD_CONFIG, tree / ".config")

    results, failed = run_steps(
        ctx, tree, make_steps(tree, out_dir, args, update_image=True), art_dir / "logs", test_id
    )
    log_ids = register_logs(ctx, results, test_id)
    build = Build(name=name, make_args=args, tree=tree)
    build.artifact_ids.update({f"log_{k}": v for k, v in log_ids.items()})
    if failed:
        label, res = failed
        detail = "; ".join(f"L{n}: {line}" for n, line in error_lines(res.log_path)[:3])
        reason = "timeout" if res.timed_out else f"exit {res.returncode}"
        raise BuildFailed(f"[{name}] step '{label}' failed ({reason}) {detail}".strip(), res.log_path)

    for key, (rel, kind) in _OUTPUTS.items():
        src = tree / rel
        if not src.is_file():
            raise BuildFailed(f"[{name}] expected build output missing: {rel}", res_log(results))
        dst = art_dir / ("dot_config" if rel == ".config" else rel.replace("/", "_"))
        shutil.copyfile(src, dst)
        build.files[key] = dst
        build.artifact_ids[key] = sink.artifact(dst, kind=kind, test_id=test_id)
    upd = out_dir / "renode-test-update.bin"
    if not upd.is_file():
        raise BuildFailed(f"[{name}] update image not produced", res_log(results))
    dst = art_dir / "renode-test-update.bin"
    shutil.copyfile(upd, dst)
    build.files["update_image"] = dst
    build.artifact_ids["update_image"] = sink.artifact(dst, kind="signed_image", test_id=test_id)

    build.target = parse_target_h(build.files["target_h"].read_text(encoding="utf-8", errors="replace"))
    cfg = parse_config(build.files["config"].read_text(encoding="utf-8", errors="replace"))
    build.effective = apply_make_args(cfg, args)
    sink.log(
        "runner",
        f"[{name}] built: wolfboot.bin={build.size('wolfboot_bin')} B, "
        f"image_v1_signed.bin={build.size('image_v1')} B, image.bin={build.size('app_bin')} B",
        test_id=test_id,
    )
    return build


def res_log(results: list[tuple[str, CmdResult]]) -> Path | None:
    return results[-1][1].log_path if results else None


def build_update_image(signed: bytes, partition_size: int) -> bytes:
    """Layout of tools/test-renode.mk $(RENODE_UPDATE_FILE): 0xFF fill to POFF, image at 0, "pBOOT".

    POFF = partition size - 5: the last 5 bytes are the partition trailer (state 'p' =
    IMG_STATE_UPDATING, magic "BOOT").
    """
    poff = partition_size - 5
    if len(signed) > poff:
        raise ValueError(f"signed image ({len(signed)} B) larger than the update partition payload ({poff} B)")
    buf = bytearray(b"\xff" * poff)
    buf[: len(signed)] = signed
    return bytes(buf) + b"pBOOT"
