"""MCUboot templates (family ``mcuboot``) — facts per docs/WORKSTREAMS.md (MCUboot table)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from rp_runner.engine import RunContext, Template, TemplateResult
from rp_runner.proc import run_cmd

from rp_mcuboot import config as C
from rp_mcuboot.build import (
    Build,
    Signed,
    compose_flash,
    ensure_build,
    ensure_key,
    imgtool_help,
    parse_kconfig,
    parse_key_types,
    register,
    rel_artifact,
    sign,
    tampered_copy,
)
from rp_mcuboot.renode import INVALID_RE, JUMP, NO_BOOTABLE, SWAP_START, Phase, ScenarioResult, run_scenario

P_UART = "rp-mcuboot.uart@1"
P_DTS = "rp-mcuboot.zephyr-dts@1"
P_KCONFIG = "rp-mcuboot.kconfig@1"
P_WEST = "rp-mcuboot.west-list@1"
P_HELP = "rp-mcuboot.imgtool-help@1"
P_SIZE = "rp-mcuboot.file-size@1"
P_KEY = "rp-mcuboot.pubkey-sha256@1"
P_SIGN = "rp-mcuboot.imgtool-sign@1"


def _obs(
    ctx: RunContext,
    test_id: str,
    fact: str,
    subject: str,
    value: Any,
    *,
    origin: str,
    mode: str,
    parser: str,
    sources: list[str],
    locator: str | None = None,
    unit: str | None = None,
) -> str:
    return ctx.sink.observation(
        observation_id=f"OBS-{test_id}-{fact}",
        test_id=test_id,
        subject=subject,
        fact=fact,
        value=value,
        origin=origin,
        acquisition_mode=mode,
        parser=parser,
        source_artifact_ids=sorted(set(a for a in sources if a)),
        locator=locator,
        unit=unit,
    )


def _git_sha(repo: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out if re.fullmatch(r"[0-9a-f]{40}", out) else None


def _phase_ok(phase: Phase, major: int, key_prefix: str) -> tuple[bool, str]:
    jump = phase.find(JUMP)
    marks = [m for m in phase.markers() if m.major == major and m.key == key_prefix]
    if jump and marks:
        return True, f"{phase.loc(jump)}, {phase.loc(marks[0].line)}"
    return False, ""


# ====================================================================== D01


class Discover(Template):
    template_id = "mcuboot.discover"
    test_id = "D01"
    phase = "DISCOVERY"
    expected = "Pins, partitions and algorithms recorded"

    def run(self, ctx: RunContext) -> TemplateResult:
        tid = self.test_id
        ids: list[str] = []
        problems: list[str] = []
        # ---- pins (west list baked at image build + git HEAD of the checkouts)
        west_list = ctx.artifact_path("toolchain", "west-list.txt")
        west_list.write_bytes(C.WEST_LIST.read_bytes())
        wl_aid = register(ctx, west_list, "manifest", tid)
        freeze_aid = register(ctx, ctx.cache["manifest_path"], "manifest", tid) if "manifest_path" in ctx.cache else ""
        rows = {}
        for n, line in enumerate(west_list.read_text().splitlines(), 1):
            parts = line.split()
            if len(parts) >= 3:
                rows[parts[0]] = (parts[2], n)
        mcuboot_sha = _git_sha(C.MCUBOOT_DIR)
        zephyr_sha = _git_sha(C.ZEPHYR_BASE)
        pins = ctx.artifact_path("toolchain", "git-heads.txt")
        pins.write_text(f"zephyr {zephyr_sha}\nmcuboot {mcuboot_sha}\n", encoding="utf-8")
        pins_aid = register(ctx, pins, "manifest", tid)
        if mcuboot_sha and rows.get("mcuboot", ("",))[0] == mcuboot_sha:
            ids.append(_obs(ctx, tid, "bootloader_commit", "toolchain", mcuboot_sha, origin="MEASURED_TOOL",
                            mode="REPOSITORY", parser=P_WEST, sources=[wl_aid, freeze_aid, pins_aid],
                            locator=f"toolchain/west-list.txt:L{rows['mcuboot'][1]}"))
        else:
            problems.append(f"mcuboot pin mismatch git={mcuboot_sha} west={rows.get('mcuboot')}")
        if zephyr_sha:
            ids.append(_obs(ctx, tid, "zephyr_commit", "toolchain", zephyr_sha, origin="MEASURED_TOOL",
                            mode="REPOSITORY", parser=P_WEST, sources=[pins_aid, freeze_aid],
                            locator="toolchain/git-heads.txt:L1"))
        else:
            problems.append("zephyr HEAD not resolvable")
        # ---- partitions from the built devicetree
        b = ensure_build(ctx, tid)
        boot, s0, s1 = b.part("boot_partition"), b.part("slot0_partition"), b.part("slot1_partition")
        layout = {
            "boot_partition_size": boot.size,
            "slot0_address": s0.address,
            "slot0_size": s0.size,
            "slot1_address": s1.address,
            "slot1_size": s1.size,
        }
        ids.append(_obs(ctx, tid, "partition_layout", "platform", layout, origin="MEASURED_TOOL",
                        mode="STATIC_CONFIG", parser=P_DTS, sources=[b.artifacts["mcuboot_dts"]],
                        locator=f"build/mcuboot.zephyr.dts:L{boot.line},L{s0.line},L{s1.line}"))
        # ---- signature algorithms offered by the pinned imgtool
        rc, text = imgtool_help(["keygen", "--help"])
        help_path = ctx.artifact_path("toolchain", "imgtool-keygen-help.txt")
        help_path.write_text(text, encoding="utf-8")
        help_aid = register(ctx, help_path, "log", tid)
        types = parse_key_types(text) if rc == 0 else []
        if types:
            ids.append(_obs(ctx, tid, "imgtool_key_types", "toolchain", types, origin="MEASURED_TOOL",
                            mode="STATIC_ANALYSIS", parser=P_HELP, sources=[help_aid],
                            locator="toolchain/imgtool-keygen-help.txt (--type)"))
        else:
            problems.append(f"imgtool keygen --help not parseable (rc={rc})")
        observed = (
            f"zephyr={zephyr_sha and zephyr_sha[:12]} mcuboot={mcuboot_sha and mcuboot_sha[:12]}; "
            f"boot=0x{boot.size:x} slot0=0x{s0.address:x}+0x{s0.size:x} slot1=0x{s1.address:x}+0x{s1.size:x}; "
            f"imgtool key types={types}"
        )
        if problems:
            return TemplateResult("INCONCLUSIVE", observed + "; " + "; ".join(problems), ids, "INCONCLUSIVE")
        return TemplateResult("PASS", observed, ids)


# ====================================================================== E11

_BL_UPDATE_PART = re.compile(r"^(s0|s1|b0|mcuboot_(primary|secondary)(_\d+)?|bootloader_update|.*mcuboot.*secondary.*)$")


class BootloaderUpdateCapability(Template):
    template_id = "mcuboot.bootloader_update_capability"
    test_id = "E11"
    phase = "DISCOVERY"
    expected = "Capability recorded as SUPPORTED or UNSUPPORTED"

    def run(self, ctx: RunContext) -> TemplateResult:
        tid = self.test_id
        b = ensure_build(ctx, tid)
        boot = b.part("boot_partition")
        mcfg = parse_kconfig(b.mcuboot_config)
        sbcfg = parse_kconfig(b.sysbuild_config)
        img_num = mcfg.get("CONFIG_UPDATEABLE_IMAGE_NUMBER", ("", 0))
        candidates = [p for p in b.partitions.values()
                      if _BL_UPDATE_PART.match(p.node_label) or _BL_UPDATE_PART.match(p.label)]
        first_stage = {k: v for k, v in sbcfg.items()
                       if re.match(r"SB_CONFIG_(SECURE_BOOT|.*NSIB.*|.*_B0_.*)", k) and v[0] == "y"}
        mode = next((k for k, v in mcfg.items() if k.startswith("CONFIG_BOOT_SWAP_USING_") and v[0] == "y"), None)
        facts = [
            f"boot_partition '{boot.label}' @0x{boot.address:x}+0x{boot.size:x} (mcuboot.zephyr.dts:L{boot.line})",
            f"CONFIG_UPDATEABLE_IMAGE_NUMBER={img_num[0]} (mcuboot.config:L{img_num[1]})",
            f"mode={mode}",
            f"partitions={sorted(b.partitions)}",
        ]
        if (not candidates and not first_stage and boot.address == 0 and img_num[0] == "1"):
            value = "UNSUPPORTED"
            why = ("single-stage MCUboot at the reset address; no second bootloader slot, no immutable "
                   "first stage and only one updateable image (the application)")
        elif candidates and first_stage:
            value = "SUPPORTED"
            why = f"bootloader update partitions {[p.node_label for p in candidates]} with first stage {sorted(first_stage)}"
        else:
            value = "UNKNOWN"
            why = f"ambiguous configuration: candidates={[p.node_label for p in candidates]} first_stage={sorted(first_stage)}"
        oid = _obs(ctx, tid, "bootloader_field_update", "platform", value, origin="MEASURED_TOOL",
                   mode="STATIC_CONFIG", parser=P_KCONFIG,
                   sources=[b.artifacts["mcuboot_dts"], b.artifacts["mcuboot_config"], b.artifacts["sysbuild_config"]],
                   locator=f"build/mcuboot.zephyr.dts:L{boot.line}; build/mcuboot.config:L{img_num[1]}")
        observed = f"{value}: {why}. " + "; ".join(facts)
        if value == "UNKNOWN":
            return TemplateResult("INCONCLUSIVE", observed, [oid], "INCONCLUSIVE")
        return TemplateResult("PASS", observed, [oid])


# ====================================================================== shared signing plan


def _v1(ctx: RunContext, b: Build, tid: str) -> Signed:
    return sign(ctx, b, "app-v1.0.0-deployed", key=b.key, version="1.0.0", slot="slot0_partition",
                pad=False, test_id=tid)


def _v2(ctx: RunContext, b: Build, tid: str) -> Signed:
    return sign(ctx, b, "app-v2.0.0-deployed-slot1", key=b.key, version="2.0.0",
                slot="slot1_partition", pad=True, test_id=tid)


class _Staged(Template):
    """Phase 1: power-on with v1 in slot 0. Phase 2: stage an image in slot 1, reset."""

    scenario = ""

    def staged_image(self, ctx: RunContext, b: Build) -> Signed:
        raise NotImplementedError

    def build(self, ctx: RunContext) -> None:
        b = ensure_build(ctx, self.test_id)
        compose_flash(ctx, b, _v1(ctx, b, self.test_id), "v1", self.test_id)
        self.staged_image(ctx, b)

    def observe(self, ctx: RunContext) -> tuple[str, str, ScenarioResult, list[str]]:
        """Returns (classification APPLIED|REJECTED|UNKNOWN, explanation, scenario, locators)."""
        tid = self.test_id
        b = ensure_build(ctx, tid)
        v1 = _v1(ctx, b, tid)
        staged = self.staged_image(ctx, b)
        flash, _ = compose_flash(ctx, b, v1, "v1", tid)
        r = run_scenario(ctx, f"{tid}-{self.scenario}", test_id=tid, flash_image=flash,
                         staged_slot1=staged.path, slot1_address=b.part("slot1_partition").address)
        p1, p2 = r.phases
        dep = b.key.public_sha256[:16]
        ok1, loc1 = _phase_ok(p1, 1, dep)
        locs = [f"{rel_artifact(ctx, p1.path)}:{loc1}"] if ok1 else []
        if not ok1:
            return "UNKNOWN", (f"precondition not observed: v1 did not boot at power-on "
                               f"(renode rc={r.returncode}, timeout={r.timed_out}, {len(p1.lines)} UART lines)"), r, locs
        marks = p2.markers()
        v2 = [m for m in marks if m.major == 2]
        v1m = [m for m in marks if m.major == 1]
        inv_line, inv = p2.find_re(INVALID_RE)
        inv_secondary = inv_line if inv is not None and inv["slot"] == "secondary" else None
        swap_line = p2.find(SWAP_START)
        rel2 = rel_artifact(ctx, p2.path)
        if v2 and not v1m:
            locs.append(f"{rel2}:L{v2[0].line}" + (f",L{swap_line}" if swap_line else ""))
            return "APPLIED", f"after reset the device runs {v2[0].text!r}" + (
                " (MCUboot: swap using move)" if swap_line else ""), r, locs
        if (v1m and not v2) or (inv_secondary and not v2):
            parts = []
            if inv_secondary:
                parts.append(f"MCUboot logged {p2.lines[inv_secondary - 1].strip()!r}")
                locs.append(f"{rel2}:L{inv_secondary}")
            if v1m:
                parts.append(f"v1 kept running after reset: {v1m[0].text!r}")
                locs.append(f"{rel2}:L{v1m[0].line}")
            return "REJECTED", "; ".join(parts), r, locs
        return "UNKNOWN", (f"no decisive marker after reset (renode rc={r.returncode}, timeout={r.timed_out}, "
                           f"{len(p2.lines)} UART lines, markers={[m.text for m in marks]})"), r, locs


# ====================================================================== E01


class BootCurrent(Template):
    template_id = "mcuboot.boot_current"
    test_id = "E01"
    expected = "MCUboot validates slot 0 and the application reports version 1"

    def build(self, ctx: RunContext) -> None:
        b = ensure_build(ctx, self.test_id)
        compose_flash(ctx, b, _v1(ctx, b, self.test_id), "v1", self.test_id)

    def run(self, ctx: RunContext) -> TemplateResult:
        tid = self.test_id
        b = ensure_build(ctx, tid)
        v1 = _v1(ctx, b, tid)
        flash, flash_aid = compose_flash(ctx, b, v1, "v1", tid)
        r = run_scenario(ctx, f"{tid}-boot-current", test_id=tid, flash_image=flash)
        p = r.phases[0]
        dep = b.key.public_sha256[:16]
        jump = p.find(JUMP)
        marks = p.markers()
        inv_line, inv = p.find_re(INVALID_RE)
        nob = p.find(NO_BOOTABLE)
        rel = rel_artifact(ctx, p.path)
        mine = [m for m in marks if m.key == dep]
        if jump and mine and mine[0].major == 1:
            outcome, loc = "BOOT_OK", f"{rel}:L{jump},L{mine[0].line}"
        elif nob or (inv is not None and inv["slot"] == "primary"):
            outcome, loc = "FAIL", f"{rel}:L{nob or inv_line}"
        else:
            outcome, loc = "UNKNOWN", rel
        emu_src = [p.artifact_id, r.resc_artifact, v1.artifact_id, flash_aid]
        ids = [
            _obs(ctx, tid, "boot_outcome", "deployed_state", outcome, origin="OBSERVED_EMULATION",
                 mode="EMULATED", parser=P_UART, sources=emu_src, locator=loc),
            _obs(ctx, tid, "observed_version", "deployed_state", mine[0].major if mine else "UNKNOWN",
                 origin="OBSERVED_EMULATION", mode="EMULATED", parser=P_UART, sources=emu_src,
                 locator=f"{rel}:L{mine[0].line}" if mine else rel),
            _obs(ctx, tid, "signed_image_size_bytes", "deployed_state", v1.path.stat().st_size,
                 origin="MEASURED_TOOL", mode="STATIC_ARTIFACT", parser=P_SIZE, sources=[v1.artifact_id],
                 locator=rel_artifact(ctx, v1.path), unit="bytes"),
            _obs(ctx, tid, "bootloader_size_bytes", "deployed_state", b.mcuboot_bin.stat().st_size,
                 origin="MEASURED_TOOL", mode="STATIC_ARTIFACT", parser=P_SIZE,
                 sources=[b.artifacts["mcuboot_bin"]], locator=rel_artifact(ctx, b.mcuboot_bin), unit="bytes"),
            _obs(ctx, tid, "public_key_sha256", "deployed_state", b.key.public_sha256,
                 origin="MEASURED_TOOL", mode="STATIC_ARTIFACT", parser=P_KEY, sources=[b.key.artifact_id],
                 locator=rel_artifact(ctx, b.key.public_pem)),
        ]
        s0 = b.part("slot0_partition")
        ids.append(_obs(ctx, "E05", "layout_fit", "deployed_state",
                        {"signed_artifact_size": v1.path.stat().st_size, "boot_slot_capacity": s0.size},
                        origin="MEASURED_TOOL", mode="STATIC_ARTIFACT", parser=P_DTS,
                        sources=[v1.artifact_id, b.artifacts["mcuboot_dts"]],
                        locator=f"build/mcuboot.zephyr.dts:L{s0.line}", unit="bytes"))
        text = (f"boot_outcome={outcome}; " + (f"{mine[0].text!r}" if mine else f"markers={[m.text for m in marks]}")
                + f"; signed v1={v1.path.stat().st_size} B, MCUboot={b.mcuboot_bin.stat().st_size} B; "
                f"renode {r.duration_ms} ms")
        if outcome == "BOOT_OK":
            return TemplateResult("PASS", text, ids)
        if outcome == "FAIL":
            return TemplateResult("FAIL", text, ids)
        return _undecided(text, ids, r)


# ====================================================================== E08 / E03 / X01


class SignedUpdate(_Staged):
    template_id = "mcuboot.signed_update"
    test_id = "E08"
    expected = "MCUboot swaps and the application reports version 2"
    scenario = "signed-update"

    def staged_image(self, ctx: RunContext, b: Build) -> Signed:
        return _v2(ctx, b, self.test_id)

    def run(self, ctx: RunContext) -> TemplateResult:
        cls, why, r, locs = self.observe(ctx)
        b = ensure_build(ctx, self.test_id)
        # the v2 marker must also carry the deployed key hash
        value = {"APPLIED": "APPLIED", "REJECTED": "NOT_APPLIED"}.get(cls, "UNKNOWN")
        if value == "APPLIED" and b.key.public_sha256[:16] not in why:
            value, why = "UNKNOWN", why + " (key hash in marker does not match the deployed key)"
        oid = _obs(ctx, self.test_id, "update_outcome", "deployed_state", value, origin="OBSERVED_EMULATION",
                   mode="EMULATED", parser=P_UART,
                   sources=[ph.artifact_id for ph in r.phases] + [r.resc_artifact, self.staged_image(ctx, b).artifact_id],
                   locator="; ".join(locs) or None)
        text = f"update_outcome={value}: {why}; renode {r.duration_ms} ms"
        return _result(value, {"APPLIED": "PASS", "NOT_APPLIED": "FAIL"}, text, [oid], r)


class TamperedImageRejected(_Staged):
    template_id = "mcuboot.tampered_image_rejected"
    test_id = "E03"
    expected = "MCUboot rejects slot 1; version 1 keeps running"
    scenario = "tampered-update"

    def staged_image(self, ctx: RunContext, b: Build) -> Signed:
        return tampered_copy(ctx, _v2(ctx, b, self.test_id), "app-v2.0.0-deployed-slot1-tampered", self.test_id)[0]

    def run(self, ctx: RunContext) -> TemplateResult:
        cls, why, r, locs = self.observe(ctx)
        b = ensure_build(ctx, self.test_id)
        value = {"APPLIED": "ACCEPT", "REJECTED": "REJECT"}.get(cls, "UNKNOWN")
        oid = _obs(ctx, self.test_id, "auth_negative", "deployed_state", value, origin="OBSERVED_EMULATION",
                   mode="EMULATED", parser=P_UART,
                   sources=[ph.artifact_id for ph in r.phases] + [r.resc_artifact, self.staged_image(ctx, b).artifact_id],
                   locator="; ".join(locs) or None)
        text = f"auth_negative={value}: {why}; renode {r.duration_ms} ms"
        return _result(value, {"REJECT": "PASS", "ACCEPT": "FAIL"}, text, [oid], r)


class CrossKeyUpdate(_Staged):
    template_id = "mcuboot.cross_key_update"
    test_id = "X01"
    expected = "MCUboot rejects the update; version 1 keeps running"
    scenario = "cross-key-update"

    def staged_image(self, ctx: RunContext, b: Build) -> Signed:
        other = ensure_key(ctx, "rotated", self.test_id)
        return sign(ctx, b, "app-v2.0.0-rotated-key-slot1", key=other, version="2.0.0",
                    slot="slot1_partition", pad=True, test_id=self.test_id)

    def run(self, ctx: RunContext) -> TemplateResult:
        cls, why, r, locs = self.observe(ctx)
        b = ensure_build(ctx, self.test_id)
        value = {"APPLIED": "APPLIED", "REJECTED": "REJECTED"}.get(cls, "UNKNOWN")
        other = ensure_key(ctx, "rotated", self.test_id)
        oid = _obs(ctx, self.test_id, "cross_update_outcome", "transition", value, origin="OBSERVED_EMULATION",
                   mode="EMULATED", parser=P_UART,
                   sources=[ph.artifact_id for ph in r.phases]
                   + [r.resc_artifact, self.staged_image(ctx, b).artifact_id, other.artifact_id],
                   locator="; ".join(locs) or None)
        text = (f"cross_update_outcome={value}: {why}; staged key sha256={other.public_sha256[:16]}..., "
                f"deployed key sha256={b.key.public_sha256[:16]}...; renode {r.duration_ms} ms")
        return _result(value, {"REJECTED": "PASS", "APPLIED": "FAIL"}, text, [oid], r)


def _result(value: str, mapping: dict[str, str], text: str, ids: list[str], r: ScenarioResult) -> TemplateResult:
    if value in mapping:
        return TemplateResult(mapping[value], text, ids)
    return _undecided(text, ids, r)


def _undecided(text: str, ids: list[str], r: ScenarioResult) -> TemplateResult:
    """No decisive observation. A UART/emulation timeout is INCONCLUSIVE, never a rejection."""
    if r.timed_out:
        return TemplateResult("INCONCLUSIVE", text + "; emulation wall-clock timeout", ids, "TIMEOUT")
    if r.returncode not in (0, None):
        return TemplateResult("ERROR", text + f"; renode exited with rc={r.returncode}", ids, "TOOL_FAILURE")
    return TemplateResult("INCONCLUSIVE", text, ids, "INCONCLUSIVE")


# ====================================================================== E02

PQC_VARIANTS = ("ml-dsa-44", "ml-dsa-65", "ml-dsa-87")


class PqcSignAttempt(Template):
    template_id = "mcuboot.pqc_sign_attempt"
    test_id = "E02"
    expected = "Signed image produced, or refusal recorded with the tool output"

    def build(self, ctx: RunContext) -> None:
        ensure_build(ctx, self.test_id)

    def run(self, ctx: RunContext) -> TemplateResult:
        tid = self.test_id
        b = ensure_build(ctx, tid)
        _, ver = imgtool_help(["version"])
        ver = ver.strip().splitlines()[-1] if ver.strip() else "unknown"
        mcuboot_sha = _git_sha(C.MCUBOOT_DIR) or "unknown"
        tool = f"imgtool {ver} (mcuboot {mcuboot_sha[:12]})"
        pdir = ctx.workdir / "pqc"
        pdir.mkdir(parents=True, exist_ok=True)
        aids: list[str] = []
        attempts: list[str] = []
        produced: tuple[str, Path] | None = None
        for variant in PQC_VARIANTS:
            key = pdir / f"{variant}.pem"
            res = run_cmd([C.PYTHON, str(C.IMGTOOL), "keygen", "-k", str(key), "-t", variant],
                          cwd=pdir, log_path=ctx.artifact_path("pqc", f"keygen-{variant}.log"),
                          sink=ctx.sink, stream="sign", test_id=tid, timeout_s=60)
            aids.append(register(ctx, res.log_path, "log", tid))
            if res.ok and key.exists():
                out = ctx.artifact_path("pqc", f"app-v2.0.0-{variant}.signed.bin")
                sres = run_cmd([C.PYTHON, str(C.IMGTOOL), "sign", "--key", str(key), "--header-size",
                                hex(C.HEADER_SIZE), "--align", str(C.ALIGN), "--version", "2.0.0",
                                "--slot-size", hex(b.part("slot1_partition").size), str(b.app_bin), str(out)],
                               cwd=pdir, log_path=ctx.artifact_path("pqc", f"sign-{variant}.log"),
                               sink=ctx.sink, stream="sign", test_id=tid, timeout_s=120)
                aids.append(register(ctx, sres.log_path, "log", tid))
                if sres.ok and out.exists():
                    aids.append(register(ctx, out, "signed_image", tid))
                    produced = (variant, out)
                    attempts.append(f"{variant}: keygen OK, sign OK ({out.stat().st_size} B)")
                    break
                attempts.append(f"{variant}: keygen OK, sign failed: {_last_error(sres.log_path)}")
            else:
                attempts.append(f"{variant}: keygen refused (rc={res.returncode}): {_last_error(res.log_path)}")
        if produced:
            value = {"signing_result": "OK", "algorithm": produced[0].upper(), "tool": tool,
                     "message": "; ".join(attempts)}
        else:
            value = {"signing_result": "REJECTED", "algorithm": "ML-DSA", "tool": tool,
                     "message": "; ".join(attempts)}
        oid = _obs(ctx, tid, "pqc_signing", "candidate_state", value, origin="MEASURED_TOOL", mode="SIGN_TOOL",
                   parser=P_SIGN, sources=aids, locator="pqc/keygen-*.log")
        text = f"pqc_signing={value['signing_result']} with {tool}: {value['message']}"
        if produced:
            return TemplateResult("PASS", text, [oid])
        return TemplateResult("FAIL", text, [oid])


def _last_error(log: Path) -> str:
    lines = [ln.strip() for ln in log.read_text(encoding="utf-8", errors="replace").splitlines()[1:] if ln.strip()]
    errs = [ln for ln in lines if "Error" in ln or "error" in ln or "Invalid" in ln]
    return (errs[-1] if errs else (lines[-1] if lines else "no output"))[:400]


TEMPLATES: dict[str, Template] = {
    t.template_id: t
    for t in (
        Discover(),
        BootloaderUpdateCapability(),
        BootCurrent(),
        SignedUpdate(),
        TamperedImageRejected(),
        PqcSignAttempt(),
        CrossKeyUpdate(),
    )
}
