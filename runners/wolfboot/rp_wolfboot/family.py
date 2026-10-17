"""wolfBoot runner family: templates of profiles/test_catalog.yaml (family ``wolfboot``)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from rp_runner.engine import EnvironmentFailure, Family, RunContext, Template, TemplateResult
from rp_runner.proc import run_cmd, tool_version

from rp_wolfboot import settings
from rp_wolfboot.builds import (
    Build,
    build_update_image,
    error_lines,
    find_lines,
    get_build,
    make_steps,
    prepare_tree,
    register_logs,
    run_steps,
)
from rp_wolfboot.emulation import Emulation, Phase, emulate
from rp_wolfboot.parsers import (
    BOOT_REFUSAL_MARKERS,
    UPDATE_REFUSAL_MARKERS,
    keystore_pubkey,
    layout_from_config,
    parse_config,
    parse_image_header,
    sha256_hex,
)

V = settings.PARSER_VERSION
P_UART = f"wolfboot.uart_version_frame@{V}"
P_STAT = f"wolfboot.file_stat@{V}"
P_KEYSTORE = f"wolfboot.keystore_der@{V}"
P_HEADER = f"wolfboot.image_header@{V}"
P_CONFIG = f"wolfboot.make_config@{V}"
P_GIT = f"git.rev-parse@{V}"
P_SCAN = f"wolfboot.self_update_scan@{V}"
P_MAKE = f"wolfboot.make_exit@{V}"
MO = "MEASURED_TOOL"
OE = "OBSERVED_EMULATION"
UNKNOWN = "UNKNOWN"


# ------------------------------------------------------------------ helpers


class Obs:
    """Collects observation ids emitted by one template run."""

    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx
        self.ids: list[str] = []

    def add(
        self,
        test_id: str,
        subject: str,
        fact: str,
        value: Any,
        *,
        origin: str,
        mode: str,
        parser: str,
        sources: list[str],
        locator: str | None = None,
        unit: str | None = None,
    ) -> str:
        oid = self.ctx.sink.observation(
            observation_id=f"OBS-{test_id}-{fact}",
            test_id=test_id,
            subject=subject,
            fact=fact,
            value=value,
            origin=origin,
            acquisition_mode=mode,
            parser=parser,
            source_artifact_ids=[s for s in sources if s],
            locator=locator,
            unit=unit,
        )
        self.ids.append(oid)
        return oid


def _rel(ctx: RunContext, path: Path) -> str:
    return path.resolve().relative_to(ctx.artifact_dir.resolve()).as_posix()


def _marker_locator(ctx: RunContext, phase: Phase, markers: dict[str, list[int]]) -> str:
    rel = _rel(ctx, phase.uart_path)
    return "; ".join(f"{rel}:L{','.join(map(str, lines))} '{m}'" for m, lines in markers.items())


def _frames_locator(ctx: RunContext, phase: Phase) -> str:
    rel = _rel(ctx, phase.uart_path)
    if not phase.capture.frames:
        return f"{rel}: no version frame (0x2A + 4-byte BE version)"
    return "; ".join(f"{rel}@0x{f.offset:x} [{f.raw_hex}] -> {f.version}" for f in phase.capture.frames)


def _emu_problem(emu: Emulation) -> str:
    if emu.timed_out:
        return f"Renode wall-clock timeout ({settings.EMULATION_WALL_TIMEOUT_S}s)"
    if emu.returncode not in (0, None):
        return f"Renode exited {emu.returncode}"
    return ""


def classify_boot(phase: Phase) -> tuple[str, Any, dict[str, list[int]]]:
    """BOOT_OK only with a version frame; FAIL only with an explicit refusal marker; else UNKNOWN."""
    cap = phase.capture
    refusals = cap.markers(BOOT_REFUSAL_MARKERS)
    if cap.frames:
        return "BOOT_OK", cap.frames[0].version, refusals
    if refusals:
        return "FAIL", UNKNOWN, refusals
    return UNKNOWN, UNKNOWN, refusals


def classify_staged_update(boot: Phase, update: Phase, new_version: int) -> tuple[str, str]:
    """APPLIED / NOT_APPLIED / UNKNOWN for a staged update, with positive identification only.

    APPLIED: the new version's frame (or wolfBoot's "Booting version" line) after the reset.
    NOT_APPLIED: the previously running version's frame is observed after the reset and no
    trace of the new version. Anything else (timeout, silence) stays UNKNOWN.
    """
    before = boot.capture.versions()
    after = update.capture.versions()
    booting_after = update.capture.booting_versions()
    if new_version in after or new_version in booting_after:
        return "APPLIED", f"after reset: frames {after}, 'Booting version' {booting_after}"
    if before and after and all(v == before[0] for v in after) and before[0] != new_version:
        return "NOT_APPLIED", f"version {before[0]} before and after reset (frames {before} -> {after})"
    return UNKNOWN, f"no decisive frame (before {before}, after {after})"


def _static_facts(obs: Obs, test_id: str, subject: str, build: Build) -> None:
    aid = build.artifact_ids
    obs.add(
        test_id, subject, "signed_image_size_bytes", build.size("image_v1"),
        origin=MO, mode="STATIC_ARTIFACT", parser=P_STAT, sources=[aid["image_v1"]],
        locator=f"build_{build.name}/test-app_image_v1_signed.bin", unit="bytes",
    )
    obs.add(
        test_id, subject, "bootloader_size_bytes", build.size("wolfboot_bin"),
        origin=MO, mode="STATIC_ARTIFACT", parser=P_STAT, sources=[aid["wolfboot_bin"]],
        locator=f"build_{build.name}/wolfboot.bin", unit="bytes",
    )
    try:
        key_type, size, pub = keystore_pubkey(build.files["keystore"])
        value: Any = sha256_hex(pub)
        loc = f"build_{build.name}/keystore.der slot 0 (key_type 0x{key_type:02x}, pubkey {size} B @16)"
    except (OSError, ValueError) as exc:
        value, loc = UNKNOWN, f"keystore.der unparsable: {exc}"
    obs.add(
        test_id, subject, "public_key_sha256", value,
        origin=MO, mode="STATIC_ARTIFACT", parser=P_KEYSTORE, sources=[aid["keystore"]], locator=loc,
    )


def _result(outcome: str, observed: str, obs: Obs, emu: Emulation | None = None) -> TemplateResult:
    failure = None
    if outcome == "INCONCLUSIVE":
        failure = "TIMEOUT" if emu is not None and emu.timed_out else "INCONCLUSIVE"
    return TemplateResult(outcome, observed, observation_ids=obs.ids, failure_class=failure)


def _tool_failure(emu: Emulation, what: str) -> TemplateResult | None:
    """Renode could not produce any UART byte and did not exit cleanly: the tool failed."""
    if any(p.capture.raw for p in emu.phases):
        return None
    if emu.timed_out:
        return TemplateResult("ERROR", f"{what}: {_emu_problem(emu)}, no UART output", failure_class="TIMEOUT")
    if emu.returncode != 0:
        return TemplateResult("ERROR", f"{what}: {_emu_problem(emu)}, no UART output", failure_class="TOOL_FAILURE")
    return None


# ------------------------------------------------------------------ templates


class Discover(Template):
    template_id = "wolfboot.discover"
    test_id = "D01"
    phase = "DISCOVERY"
    expected = "Pins and layout recorded"

    def run(self, ctx: RunContext) -> TemplateResult:
        obs = Obs(ctx)
        out = ctx.artifact_dir / "discovery"
        out.mkdir(parents=True, exist_ok=True)
        pins = git_pins()
        pins_path = out / "pins.json"
        pins_path.write_text(json.dumps(pins, indent=2), encoding="utf-8")
        pins_id = ctx.sink.artifact(pins_path, kind="manifest", test_id=self.test_id)
        cfg_copy = out / "nrf52840.config"
        shutil.copyfile(settings.BAKED_TREE / settings.BOARD_CONFIG, cfg_copy)
        cfg_id = ctx.sink.artifact(cfg_copy, kind="config", test_id=self.test_id)

        obs.add(self.test_id, "toolchain", "bootloader_commit", pins.get("wolfboot_commit") or UNKNOWN,
                origin=MO, mode="REPOSITORY", parser=P_GIT, sources=[pins_id],
                locator=f"git -C {settings.BAKED_TREE} rev-parse HEAD")
        obs.add(self.test_id, "toolchain", "crypto_commit", pins.get("wolfssl_commit") or UNKNOWN,
                origin=MO, mode="REPOSITORY", parser=P_GIT, sources=[pins_id],
                locator=f"git -C {settings.BAKED_TREE}/lib/wolfssl rev-parse HEAD")
        layout, lines = layout_from_config(parse_config(cfg_copy.read_text(encoding="utf-8")))
        complete = all(isinstance(v, int) for v in layout.values())
        obs.add(self.test_id, "platform", "partition_layout", layout if complete else UNKNOWN,
                origin=MO, mode="STATIC_CONFIG", parser=P_CONFIG, sources=[cfg_id],
                locator=f"{settings.BOARD_CONFIG.as_posix()}:L{','.join(map(str, lines))}")

        wb_ok = pins.get("wolfboot_commit") == settings.PINNED_WOLFBOOT_COMMIT
        ssl_ok = pins.get("wolfssl_commit") == settings.PINNED_WOLFSSL_COMMIT
        observed = (
            f"wolfBoot {pins.get('wolfboot_commit')}, wolfSSL {pins.get('wolfssl_commit')}, "
            f"layout {json.dumps(layout)}"
        )
        if not complete:
            return _result("INCONCLUSIVE", observed + " (layout incomplete)", obs)
        if not (wb_ok and ssl_ok):
            return _result("FAIL", observed + " (does not match the profile pins)", obs)
        return _result("PASS", observed, obs)


class SelfUpdateCapability(Template):
    template_id = "wolfboot.self_update_capability"
    test_id = "E11"
    phase = "DISCOVERY"
    expected = "Capability recorded as SUPPORTED or UNSUPPORTED"

    def run(self, ctx: RunContext) -> TemplateResult:
        obs = Obs(ctx)
        tree = settings.BAKED_TREE
        report: dict[str, Any] = {"tree": str(tree), "commit": git_pins().get("wolfboot_commit")}
        examples = sorted((tree / "config" / "examples").glob("*self-update*"))
        report["self_update_example_configs"] = [p.name for p in examples]
        nrf_examples = []
        for p in examples:
            hits = find_lines(p, r"(?i)nrf52")
            if hits:
                nrf_examples.append(f"config/examples/{p.name}:L{hits[0][0]}")
        report["nrf52_self_update_configs"] = nrf_examples
        hal = tree / "hal" / "nrf52.c"
        hal_hits = find_lines(hal, r"(?i)self_update|bootloader_update|HDR_IMG_TYPE_WOLFBOOT")
        report["hal_nrf52_self_update_lines"] = [f"hal/nrf52.c:L{n}" for n, _ in hal_hits]
        cfg = tree / settings.BOARD_CONFIG
        ram_code = find_lines(cfg, r"^\s*RAM_CODE\s*\??=")
        ram_value = ram_code[-1][1].split("=", 1)[1].strip() if ram_code else None
        report["board_config_RAM_CODE"] = ram_value
        upd = tree / "src" / "update_flash.c"
        gate = find_lines(upd, r"^#ifdef RAM_CODE|wolfBoot_check_self_update\(|HDR_IMG_TYPE_WOLFBOOT")
        report["update_flash_self_update_gate"] = [f"src/update_flash.c:L{n} {s}" for n, s in gate]

        if nrf_examples or hal_hits:
            value = "SUPPORTED"
        elif ram_value is not None and ram_value != "1":
            value = "UNSUPPORTED"
        else:
            value = UNKNOWN
        report["value"] = value
        report["rule"] = (
            "SUPPORTED if an nRF52 self-update example config or an nRF52 HAL self-update path exists; "
            "UNSUPPORTED if neither exists and the board config does not enable RAM_CODE (the "
            "self-update path in src/update_flash.c is compiled only under RAM_CODE); else UNKNOWN."
        )
        out = ctx.artifact_dir / "discovery"
        out.mkdir(parents=True, exist_ok=True)
        rpath = out / "e11_self_update_scan.json"
        rpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
        rid = ctx.sink.artifact(rpath, kind="manifest", test_id=self.test_id)
        locator_parts = (
            [f"config/examples/*self-update* ({len(examples)} files, nRF52: {nrf_examples or 'none'})"]
            + [f"hal/nrf52.c self-update refs: {report['hal_nrf52_self_update_lines'] or 'none'}"]
            + [f"{settings.BOARD_CONFIG.as_posix()}:L{ram_code[-1][0]} RAM_CODE={ram_value}" if ram_code else "RAM_CODE not set"]
            + [", ".join(f"src/update_flash.c:L{n}" for n, _ in gate)]
        )
        obs.add(self.test_id, "platform", "bootloader_field_update", value,
                origin=MO, mode="SOURCE_INSPECTION", parser=P_SCAN, sources=[rid],
                locator="; ".join(locator_parts))
        observed = f"bootloader_field_update={value}; " + "; ".join(locator_parts)
        return _result("PASS" if value != UNKNOWN else "INCONCLUSIVE", observed, obs)


class BootCurrent(Template):
    template_id = "wolfboot.boot_current"
    test_id = "E01"
    expected = "Version 1 boots; version 2 update applied"

    def build(self, ctx: RunContext) -> None:
        get_build(ctx, "ecc", self.test_id)

    def run(self, ctx: RunContext) -> TemplateResult:
        b = get_build(ctx, "ecc", self.test_id)
        emu = emulate(ctx, test_id=self.test_id, label="E01_boot_current",
                      elf=b.files["wolfboot_elf"], boot_image=b.files["image_v1"],
                      update_image=b.files["update_image"])
        failed = _tool_failure(emu, "E01 emulation")
        if failed:
            return failed
        obs = Obs(ctx)
        boot, update = emu.phase("boot"), emu.phase("update")
        assert boot is not None and update is not None
        srcs = emu.artifact_ids + [b.artifact_ids["wolfboot_elf"], b.artifact_ids["image_v1"]]
        outcome, version, refusals = classify_boot(boot)
        obs.add(self.test_id, "deployed_state", "boot_outcome", outcome, origin=OE, mode="EMULATED",
                parser=P_UART, sources=srcs,
                locator=_frames_locator(ctx, boot) + ("; " + _marker_locator(ctx, boot, refusals) if refusals else ""))
        obs.add(self.test_id, "deployed_state", "observed_version", version, origin=OE, mode="EMULATED",
                parser=P_UART, sources=srcs, locator=_frames_locator(ctx, boot))
        upd, why = classify_staged_update(boot, update, settings.TEST_UPDATE_VERSION)
        obs.add("E08", "deployed_state", "update_outcome", upd, origin=OE, mode="EMULATED", parser=P_UART,
                sources=srcs + [b.artifact_ids["update_image"], b.artifact_ids["image_v2"]],
                locator=_frames_locator(ctx, update))
        _static_facts(obs, self.test_id, "deployed_state", b)
        observed = (
            f"boot={outcome} version={version}; update v1->v2 (ECC256) {upd}: {why}; "
            f"signed v1 {b.size('image_v1')} B, wolfboot.bin {b.size('wolfboot_bin')} B; "
            f"emulation {emu.duration_ms} ms {_emu_problem(emu)}".strip()
        )
        if outcome == "BOOT_OK" and version == 1 and upd == "APPLIED":
            return _result("PASS", observed, obs, emu)
        if outcome == "FAIL" or (outcome == "BOOT_OK" and version != 1) or upd == "NOT_APPLIED":
            return _result("FAIL", observed, obs, emu)
        return _result("INCONCLUSIVE", observed, obs, emu)


class BootCandidate(Template):
    template_id = "wolfboot.boot_candidate"
    test_id = "E02"
    expected = "Version 1 boots; signed image fits the slot"

    def build(self, ctx: RunContext) -> None:
        get_build(ctx, "mldsa", self.test_id)

    def run(self, ctx: RunContext) -> TemplateResult:
        b = get_build(ctx, "mldsa", self.test_id)
        emu = emulate(ctx, test_id=self.test_id, label="E02_boot_candidate",
                      elf=b.files["wolfboot_elf"], boot_image=b.files["image_v1"])
        failed = _tool_failure(emu, "E02 emulation")
        if failed:
            return failed
        obs = Obs(ctx)
        boot = emu.phase("boot")
        assert boot is not None
        srcs = emu.artifact_ids + [b.artifact_ids["wolfboot_elf"], b.artifact_ids["image_v1"]]
        outcome, version, refusals = classify_boot(boot)
        obs.add(self.test_id, "candidate_state", "boot_outcome", outcome, origin=OE, mode="EMULATED",
                parser=P_UART, sources=srcs,
                locator=_frames_locator(ctx, boot) + ("; " + _marker_locator(ctx, boot, refusals) if refusals else ""))
        obs.add(self.test_id, "candidate_state", "observed_version", version, origin=OE, mode="EMULATED",
                parser=P_UART, sources=srcs, locator=_frames_locator(ctx, boot))
        _static_facts(obs, self.test_id, "candidate_state", b)

        signed = b.files["image_v1"].read_bytes()
        unsigned_len = b.size("app_bin")
        hdr = parse_image_header(signed)
        span = len(signed) - hdr.fw_size if hdr.magic_ok and hdr.fw_size == unsigned_len else len(signed) - unsigned_len
        header_value = {"image_header_size_bytes": b.header_size, "header_span_bytes": span}
        obs.add("E04", "candidate_state", "image_header", header_value, origin=MO, mode="STATIC_ARTIFACT",
                parser=P_HEADER, sources=[b.artifact_ids["image_v1"], b.artifact_ids["app_bin"]],
                locator=(f"IMAGE_HEADER_SIZE={b.header_size} (make args); header span = signed {len(signed)} B - "
                         f"payload {unsigned_len} B; manifest magic_ok={hdr.magic_ok} fw_size={hdr.fw_size} "
                         f"version={hdr.version} type=0x{(hdr.image_type or 0):04x}"))
        capacity = b.target.get("WOLFBOOT_PARTITION_SIZE")
        fit = {"signed_artifact_size": len(signed), "boot_slot_capacity": capacity if capacity else UNKNOWN}
        obs.add("E05", "candidate_state", "layout_fit", fit, origin=MO, mode="STATIC_ARTIFACT", parser=P_STAT,
                sources=[b.artifact_ids["image_v1"], b.artifact_ids["target_h"]],
                locator=f"build_{b.name}/include_target.h WOLFBOOT_PARTITION_SIZE; test-app_image_v1_signed.bin size")
        fits = bool(capacity) and len(signed) <= capacity
        observed = (
            f"boot={outcome} version={version}; ML-DSA-87 signed v1 {len(signed)} B "
            f"(header span {span} B) vs boot slot {capacity} B -> {'fits' if fits else 'does not fit'}; "
            f"wolfboot.bin {b.size('wolfboot_bin')} B; emulation {emu.duration_ms} ms {_emu_problem(emu)}".strip()
        )
        if outcome == "BOOT_OK" and version == 1 and fits:
            return _result("PASS", observed, obs, emu)
        if outcome == "FAIL" or (outcome == "BOOT_OK" and version != 1) or (capacity and not fits):
            return _result("FAIL", observed, obs, emu)
        return _result("INCONCLUSIVE", observed, obs, emu)


def _refusal_test(
    ctx: RunContext, test_id: str, label: str, elf: Path, image: Path, extra_sources: list[str]
) -> tuple[str, str, list[str], Emulation, str]:
    """Boot ``image`` with ``elf``: REJECT needs an explicit refusal marker and no version frame."""
    emu = emulate(ctx, test_id=test_id, label=label, elf=elf, boot_image=image)
    boot = emu.phase("boot")
    assert boot is not None
    cap = boot.capture
    refusals = cap.markers(BOOT_REFUSAL_MARKERS)
    if cap.frames:
        value = "ACCEPT"
        why = f"application ran: version frame(s) {cap.versions()}"
        locator = _frames_locator(ctx, boot)
    elif refusals:
        value = "REJECT"
        why = "explicit refusal: " + "; ".join(
            f"'{cap.lines[lines[0] - 1].strip()}'" for lines in refusals.values()
        ) + "; no version frame"
        locator = _marker_locator(ctx, boot, refusals) + "; " + _frames_locator(ctx, boot)
    else:
        value = UNKNOWN
        why = f"no version frame and no refusal marker ({len(cap.raw)} UART bytes) {_emu_problem(emu)}".strip()
        locator = _frames_locator(ctx, boot)
    return value, why, emu.artifact_ids + extra_sources, emu, locator


class TamperedImageRejected(Template):
    template_id = "wolfboot.tampered_image_rejected"
    test_id = "E03"
    expected = "Boot refused (no application version frame)"

    def build(self, ctx: RunContext) -> None:
        get_build(ctx, "ecc", self.test_id)

    def run(self, ctx: RunContext) -> TemplateResult:
        b = get_build(ctx, "ecc", self.test_id)
        data = bytearray(b.files["image_v1"].read_bytes())
        hdr = parse_image_header(bytes(data))
        offset = b.header_size + max(0, hdr.fw_size // 2)
        if offset >= len(data):
            offset = len(data) - 1
        original = data[offset]
        data[offset] ^= 0xFF
        tampered = ctx.artifact_dir / "E03_tampered_image_rejected" / "image_v1_signed_tampered.bin"
        tampered.parent.mkdir(parents=True, exist_ok=True)
        tampered.write_bytes(bytes(data))
        tid = ctx.sink.artifact(tampered, kind="signed_image", test_id=self.test_id)
        ctx.sink.log("runner", f"E03: flipped payload byte at offset {offset} (0x{original:02x} -> "
                     f"0x{data[offset]:02x}) of {len(data)}-byte ECC256 image", test_id=self.test_id)
        value, why, srcs, emu, locator = _refusal_test(
            ctx, self.test_id, "E03_tampered_image_rejected", b.files["wolfboot_elf"], tampered,
            [tid, b.artifact_ids["wolfboot_elf"], b.artifact_ids["image_v1"]],
        )
        failed = _tool_failure(emu, "E03 emulation")
        if failed:
            return failed
        obs = Obs(ctx)
        obs.add(self.test_id, "deployed_state", "auth_negative", value, origin=OE, mode="EMULATED",
                parser=P_UART, sources=srcs, locator=locator)
        observed = f"auth_negative={value} (payload byte {offset} flipped): {why}"
        outcome = {"REJECT": "PASS", "ACCEPT": "FAIL"}.get(value, "INCONCLUSIVE")
        return _result(outcome, observed, obs, emu)


class CrossGenerationUpdate(Template):
    template_id = "wolfboot.cross_generation_update"
    test_id = "X01"
    expected = "Update not applied (device stays on version 1)"

    def build(self, ctx: RunContext) -> None:
        get_build(ctx, "ecc", self.test_id)
        get_build(ctx, "mldsa", self.test_id)

    def run(self, ctx: RunContext) -> TemplateResult:
        dep = get_build(ctx, "ecc", self.test_id)
        cand = get_build(ctx, "mldsa", self.test_id)
        out = ctx.artifact_dir / "X01_cross_generation_update"
        out.mkdir(parents=True, exist_ok=True)
        dep_layout, cand_layout = dep.layout(), cand.layout()
        part = dep_layout["partition_size_bytes"]
        if not isinstance(part, int):
            return TemplateResult("ERROR", "deployed partition size not found in include/target.h",
                                  failure_class="TOOL_FAILURE")
        # Self-check: the Python layout must reproduce the make-built same-scheme update image.
        selfcheck = build_update_image(dep.files["image_v2"].read_bytes(), part) == dep.files["update_image"].read_bytes()
        image = out / "renode-test-update-mldsa.bin"
        image.write_bytes(build_update_image(cand.files["image_v2"].read_bytes(), part))
        img_id = ctx.sink.artifact(image, kind="signed_image", test_id=self.test_id)
        note = {
            "deployed_layout_target_h": dep_layout,
            "candidate_layout_target_h": cand_layout,
            "addresses_equal": {k: dep_layout[k] == cand_layout[k] for k in dep_layout},
            "deployed_image_header_size": dep.header_size,
            "candidate_image_header_size": cand.header_size,
            "update_image": {
                "payload": "candidate test-app/image_v2_signed.bin (ML-DSA-87)",
                "placed_at": f"0x{dep_layout['update_partition_address']:x}" if dep_layout["update_partition_address"] else None,
                "trailer": f"'pBOOT' at partition offset {part - 5} (IMG_STATE_UPDATING + magic), 0xFF fill",
                "trailer_note": "NVM_FLASH_WRITEONCE=0 -> trailer at partition end, independent of the sector size",
                "python_layout_matches_make_layout_for_ecc_v2": selfcheck,
            },
        }
        npath = out / "layout_comparison.json"
        npath.write_text(json.dumps(note, indent=2), encoding="utf-8")
        nid = ctx.sink.artifact(npath, kind="manifest", test_id=self.test_id)
        if not selfcheck:
            return TemplateResult("ERROR", "update image layout self-check failed (Python vs make)",
                                  failure_class="INTERNAL")
        emu = emulate(ctx, test_id=self.test_id, label="X01_cross_generation_update",
                      elf=dep.files["wolfboot_elf"], boot_image=dep.files["image_v1"], update_image=image)
        failed = _tool_failure(emu, "X01 emulation")
        if failed:
            return failed
        obs = Obs(ctx)
        boot, update = emu.phase("boot"), emu.phase("update")
        assert boot is not None and update is not None
        upd, why = classify_staged_update(boot, update, settings.TEST_UPDATE_VERSION)
        value = {"APPLIED": "APPLIED", "NOT_APPLIED": "REJECTED"}.get(upd, UNKNOWN)
        refusals = update.capture.markers(UPDATE_REFUSAL_MARKERS)
        locator = _frames_locator(ctx, boot) + " | " + _frames_locator(ctx, update)
        if refusals:
            locator += "; " + _marker_locator(ctx, update, refusals)
        srcs = emu.artifact_ids + [img_id, nid, dep.artifact_ids["wolfboot_elf"], dep.artifact_ids["image_v1"],
                                   cand.artifact_ids["image_v2"]]
        obs.add(self.test_id, "transition", "cross_update_outcome", value, origin=OE, mode="EMULATED",
                parser=P_UART, sources=srcs, locator=locator)
        marker_text = "; ".join(
            f"'{update.capture.lines[l[0] - 1].strip()}'" for l in refusals.values()
        ) or "no explicit update refusal line"
        same = all(v for k, v in note["addresses_equal"].items() if k != "sector_size_bytes")
        observed = (
            f"cross_update_outcome={value}: {why}; bootloader said: {marker_text}; "
            f"partition addresses/size {'identical' if same else 'DIFFER'} in both builds; "
            f"sector {dep_layout['sector_size_bytes']} vs {cand_layout['sector_size_bytes']} B, "
            f"header {dep.header_size} vs {cand.header_size} B"
        )
        outcome = {"REJECTED": "PASS", "APPLIED": "FAIL"}.get(value, "INCONCLUSIVE")
        return _result(outcome, observed, obs, emu)


class CandidateRejectsClassical(Template):
    template_id = "wolfboot.candidate_rejects_classical"
    test_id = "P01"
    expected = "Boot refused (PQC-only policy observed)"

    def build(self, ctx: RunContext) -> None:
        get_build(ctx, "ecc", self.test_id)
        get_build(ctx, "mldsa", self.test_id)

    def run(self, ctx: RunContext) -> TemplateResult:
        dep = get_build(ctx, "ecc", self.test_id)
        cand = get_build(ctx, "mldsa", self.test_id)
        # Cell A: the deployed ECC256 v1 artifact exactly as shipped (256-byte header).
        value_a, why_a, srcs_a, emu_a, loc_a = _refusal_test(
            ctx, self.test_id, "P01_candidate_rejects_classical", cand.files["wolfboot_elf"], dep.files["image_v1"],
            [cand.artifact_ids["wolfboot_elf"], dep.artifact_ids["image_v1"]],
        )
        failed = _tool_failure(emu_a, "P01 emulation")
        if failed:
            return failed
        # Cell B: candidate payload ECC256-signed with the deployed key but the candidate header size,
        # so that only the signature algorithm differs from what the candidate expects.
        value_b, why_b, srcs_b, loc_b = self._header_matched_cell(ctx, dep, cand)
        if value_a == "ACCEPT" or value_b == "ACCEPT":
            value = "ACCEPT"
        elif value_a == "REJECT" and value_b in ("REJECT", "NOT_EXECUTED", UNKNOWN):
            value = "REJECT"
        else:
            value = UNKNOWN
        obs = Obs(ctx)
        obs.add(self.test_id, "candidate_state", "classical_image_on_candidate", value, origin=OE,
                mode="EMULATED", parser=P_UART, sources=srcs_a + srcs_b,
                locator=f"A: {loc_a} | B: {loc_b}")
        observed = (
            f"classical_image_on_candidate={value}. A (deployed ECC256 v1 image, {dep.header_size}-byte header) "
            f"{value_a}: {why_a}. B (ECC256 signature, {cand.header_size}-byte header) {value_b}: {why_b}"
        )
        outcome = {"REJECT": "PASS", "ACCEPT": "FAIL"}.get(value, "INCONCLUSIVE")
        return _result(outcome, observed, obs, emu_a)

    def _header_matched_cell(self, ctx: RunContext, dep: Build, cand: Build) -> tuple[str, str, list[str], str]:
        label = "P01_candidate_rejects_classical_hdr_matched"
        work = ctx.workdir / "p01_sign"
        work.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cand.files["app_bin"], work / "image.bin")
        key = dep.tree / "wolfboot_signing_private_key.der"
        eff = cand.effective
        env = {
            "IMAGE_HEADER_SIZE": str(cand.header_size),
            "WOLFBOOT_PARTITION_SIZE": eff.get("WOLFBOOT_PARTITION_SIZE", ("", 0))[0],
            "WOLFBOOT_SECTOR_SIZE": eff.get("WOLFBOOT_SECTOR_SIZE", ("", 0))[0],
        }
        out = ctx.artifact_dir / label
        out.mkdir(parents=True, exist_ok=True)
        res = run_cmd(
            [str(dep.tree / "tools" / "keytools" / "sign"), "--ecc256", "--sha256", str(work / "image.bin"),
             str(key), "1"],
            cwd=work, log_path=out / "sign.log", sink=ctx.sink, stream="sign", test_id=self.test_id,
            env=env, timeout_s=min(120, ctx.remaining()),
        )
        log_id = ctx.sink.artifact(res.log_path, kind="log", test_id=self.test_id)
        signed = work / "image_v1_signed.bin"
        if not res.ok or not signed.is_file():
            return "NOT_EXECUTED", f"sign tool failed (exit {res.returncode})", [log_id], _rel(ctx, res.log_path)
        image = out / "image_v1_signed_ecc256_hdr_matched.bin"
        shutil.copyfile(signed, image)
        img_id = ctx.sink.artifact(image, kind="signed_image", test_id=self.test_id)
        value, why, srcs, _emu, loc = _refusal_test(
            ctx, self.test_id, label, cand.files["wolfboot_elf"], image, [img_id, log_id],
        )
        return value, why, srcs, loc


class DualSignatureBuild(Template):
    template_id = "wolfboot.dual_signature_build"
    test_id = "O05"
    expected = "Build outcome recorded"

    def run(self, ctx: RunContext) -> TemplateResult:
        # Built inside run(): a failing hybrid build is a measured result, not a runner error.
        args = list(settings.DUAL_MAKE_ARGS)
        tree = prepare_tree(ctx, "dual")
        shutil.copyfile(tree / settings.BOARD_CONFIG, tree / ".config")
        log_dir = ctx.artifact_dir / "build_dual" / "logs"
        steps = make_steps(tree, ctx.workdir / "dual" / "out", args, update_image=False)
        results, failed = run_steps(ctx, tree, steps, log_dir, self.test_id)
        log_ids = register_logs(ctx, results, self.test_id)
        obs = Obs(ctx)
        if failed and failed[0] != "build":
            label, res = failed
            return TemplateResult("ERROR", f"hybrid build preparation step '{label}' failed "
                                  f"(exit {res.returncode}, timeout={res.timed_out})", failure_class="TOOL_FAILURE")
        if failed and failed[1].timed_out:
            return TemplateResult("ERROR", "hybrid build timed out", failure_class="TIMEOUT")
        build_log = results[-1][1].log_path
        rel = _rel(ctx, build_log)
        if failed:
            errs = error_lines(build_log)
            value = "BUILD_FAILED"
            locator = "; ".join(f"{rel}:L{n}" for n, _ in errs) or rel
            detail = " | ".join(s for _, s in errs[:3]) or f"make exit {failed[1].returncode}"
            observed = f"dual_signature_build=BUILD_FAILED (make {' '.join(args)} exit {failed[1].returncode}): {detail}"
            outcome = "FAIL"
        else:
            bin_path = tree / "wolfboot.bin"
            value = "BUILT_NOT_BOOTED" if bin_path.is_file() else "BUILD_FAILED"
            locator = rel
            observed = f"dual_signature_build={value} (make {' '.join(args)} exit 0); hybrid image not booted"
            outcome = "INCONCLUSIVE" if value == "BUILT_NOT_BOOTED" else "FAIL"
        obs.add(self.test_id, "candidate_state", "dual_signature_build", value, origin=MO, mode="BUILD",
                parser=P_MAKE, sources=list(log_ids.values()), locator=locator)
        return _result(outcome, observed, obs)


# ------------------------------------------------------------------ family


def _git(path: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(path), *args],
                             capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


_PINS: dict[str, str] = {}


def git_pins() -> dict[str, str]:
    if not _PINS:
        wb = _git(settings.BAKED_TREE, "rev-parse", "HEAD")
        ssl = _git(settings.BAKED_TREE / "lib" / "wolfssl", "rev-parse", "HEAD")
        gitlink = _git(settings.BAKED_TREE, "ls-tree", "HEAD", "lib/wolfssl")
        if wb:
            _PINS["wolfboot_commit"] = wb
        if ssl:
            _PINS["wolfssl_commit"] = ssl
        if gitlink:
            _PINS["wolfssl_gitlink_in_wolfboot"] = gitlink.split()[2]
        _PINS["wolfboot_repo"] = settings.WOLFBOOT_REPO
    return dict(_PINS)


class WolfbootFamily(Family):
    name = "wolfboot"
    templates = {
        t.template_id: t
        for t in (
            Discover(),
            SelfUpdateCapability(),
            BootCurrent(),
            BootCandidate(),
            TamperedImageRejected(),
            CrossGenerationUpdate(),
            CandidateRejectsClassical(),
            DualSignatureBuild(),
        )
    }

    def __init__(self) -> None:
        self._versions: dict[str, str] = {}

    def prepare(self, ctx: RunContext) -> None:
        missing = [t for t in ("renode", "make", "git", "gcc", "arm-none-eabi-gcc") if shutil.which(t) is None]
        if missing:
            raise EnvironmentFailure(f"tools missing from the runner image: {missing}")
        if not (settings.BAKED_TREE / "Makefile").is_file():
            raise EnvironmentFailure(f"pinned wolfBoot tree missing at {settings.BAKED_TREE}")
        if not (settings.BAKED_TREE / "tools" / "keytools" / "sign").is_file():
            raise EnvironmentFailure("pre-built wolfBoot keytools missing from the image")
        pins = git_pins()
        ctx.sink.log("runner", f"pinned tree {settings.BAKED_TREE}: {json.dumps(pins)}; workdir {ctx.workdir}")

    def tool_versions(self) -> dict[str, str]:
        if not self._versions:
            self._versions = {
                "renode": tool_version(["renode", "--version"]),
                "arm-none-eabi-gcc": tool_version(["arm-none-eabi-gcc", "--version"]),
                "arm_gnu_toolchain_release": "14.2.rel1",
                "make": tool_version(["make", "--version"]),
                "git": tool_version(["git", "--version"]),
                "gcc_host": tool_version(["gcc", "--version"]),
                "python": tool_version(["python3", "--version"]),
            }
        return dict(self._versions)

    def source_pins(self) -> dict[str, str]:
        return git_pins()
