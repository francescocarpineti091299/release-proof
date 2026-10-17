"""Pure parsers: Makefile-style configs, generated target.h, keystore, image header, UART."""

from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

# ------------------------------------------------------------------ configs


def parse_config(text: str) -> dict[str, tuple[str, int]]:
    """Parse ``KEY?=VALUE`` / ``KEY=VALUE`` lines -> {key: (value, 1-based line)}. Later lines win."""
    values: dict[str, tuple[str, int]] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(\?|:|\+)?=\s*(.*)$", line)
        if not m:
            continue
        values[m.group(1)] = (m.group(3).strip(), lineno)
    return values


def apply_make_args(base: dict[str, tuple[str, int]], args: list[str]) -> dict[str, tuple[str, int]]:
    merged = dict(base)
    for arg in args:
        key, sep, value = arg.partition("=")
        if sep:
            merged[key.strip()] = (value.strip(), 0)
    return merged


def to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip(), 0)
    except ValueError:
        return None


LAYOUT_KEYS = {
    "boot_partition_address": "WOLFBOOT_PARTITION_BOOT_ADDRESS",
    "update_partition_address": "WOLFBOOT_PARTITION_UPDATE_ADDRESS",
    "swap_address": "WOLFBOOT_PARTITION_SWAP_ADDRESS",
    "partition_size_bytes": "WOLFBOOT_PARTITION_SIZE",
    "sector_size_bytes": "WOLFBOOT_SECTOR_SIZE",
}


def layout_from_config(cfg: dict[str, tuple[str, int]]) -> tuple[dict[str, int | None], list[int]]:
    layout: dict[str, int | None] = {}
    lines: list[int] = []
    for name, key in LAYOUT_KEYS.items():
        entry = cfg.get(key)
        layout[name] = to_int(entry[0]) if entry else None
        if entry and entry[1]:
            lines.append(entry[1])
    return layout, sorted(lines)


def parse_target_h(text: str) -> dict[str, int]:
    """Numeric ``#define WOLFBOOT_*`` values of the generated include/target.h."""
    out: dict[str, int] = {}
    pattern = r"^\s*#\s*define\s+(WOLFBOOT_[A-Z0-9_]+)\s+(0x[0-9A-Fa-f]+|\d+)\s*$"
    for m in re.finditer(pattern, text, re.M):
        out.setdefault(m.group(1), int(m.group(2), 0))
    return out


# ------------------------------------------------------------------ keystore / image


def keystore_pubkey(path: Path) -> tuple[int, int, bytes]:
    """keystore.der slot 0 -> (key_type, pubkey_size, pubkey). Slot = 4 LE u32 + pubkey."""
    data = path.read_bytes()
    if len(data) < 16:
        raise ValueError(f"keystore too short ({len(data)} bytes)")
    _slot, key_type, _mask, size = struct.unpack_from("<IIII", data, 0)
    if size <= 0 or 16 + size > len(data):
        raise ValueError(f"keystore pubkey_size {size} inconsistent with file length {len(data)}")
    return key_type, size, data[16 : 16 + size]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


WOLFBOOT_MAGIC = 0x464C4F57  # "WOLF" little-endian


@dataclass
class ImageHeader:
    magic_ok: bool
    fw_size: int
    version: int | None
    image_type: int | None


def parse_image_header(data: bytes) -> ImageHeader:
    """wolfBoot manifest: u32 magic, u32 fw_size, then TLVs (u16 type, u16 len, value; 0xFF pad)."""
    magic, fw_size = struct.unpack_from("<II", data, 0)
    version = image_type = None
    off = 8
    limit = min(len(data), 0x10000)
    while off + 4 <= limit:
        if data[off] == 0xFF:
            off += 1
            continue
        tlv_type, tlv_len = struct.unpack_from("<HH", data, off)
        if tlv_type == 0 or tlv_type == 0xFFFF:
            break
        value = data[off + 4 : off + 4 + tlv_len]
        if tlv_type == 0x0001 and tlv_len == 4:
            version = struct.unpack("<I", value)[0]
        elif tlv_type == 0x0004 and tlv_len == 2:
            image_type = struct.unpack("<H", value)[0]
        if version is not None and image_type is not None:
            break
        off += 4 + tlv_len
    return ImageHeader(magic == WOLFBOOT_MAGIC, fw_size, version, image_type)


# ------------------------------------------------------------------ UART

FRAME_START = 0x2A  # test-app: '*' followed by the 4-byte big-endian firmware version
_MAX_PLAUSIBLE_VERSION = 0xFFFF

# Explicit refusal markers printed by src/update_flash.c / include/loader.h (DEBUG_UART=1).
# "Partition 1 header magic ... invalid" is NOT a refusal: it is printed on every boot with an
# empty update partition.
BOOT_REFUSAL_MARKERS = (
    "wolfBoot: PANIC!",
    "Boot failed",
    "No boot option available",
)
UPDATE_REFUSAL_MARKERS = (
    "Update verify failed",
    "Update type invalid",
    "Update version not allowed",
    "Invalid update size",
)
FAILURE_MARKERS = BOOT_REFUSAL_MARKERS + UPDATE_REFUSAL_MARKERS


@dataclass
class Frame:
    offset: int
    version: int
    raw_hex: str


@dataclass
class UartCapture:
    raw: bytes
    frames: list[Frame] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def versions(self) -> list[int]:
        return [f.version for f in self.frames]

    def find_lines(self, needle: str) -> list[int]:
        return [i + 1 for i, line in enumerate(self.lines) if needle in line]

    def markers(self, which: tuple[str, ...] = FAILURE_MARKERS) -> dict[str, list[int]]:
        found: dict[str, list[int]] = {}
        for marker in which:
            hits = self.find_lines(marker)
            if hits:
                found[marker] = hits
        return found

    def booting_versions(self) -> list[int]:
        out: list[int] = []
        for line in self.lines:
            m = re.search(r"Booting version: 0x([0-9a-fA-F]+)", line)
            if m:
                out.append(int(m.group(1), 16))
        return out


def parse_uart(raw: bytes) -> UartCapture:
    """Extract version frames from the raw UART bytes; text lines exclude the frame bytes."""
    frames: list[Frame] = []
    text = bytearray()
    i = 0
    while i < len(raw):
        b = raw[i]
        if b == FRAME_START and i + 4 < len(raw):
            value = int.from_bytes(raw[i + 1 : i + 5], "big")
            if value <= _MAX_PLAUSIBLE_VERSION:
                frames.append(Frame(i, value, raw[i : i + 5].hex(" ")))
                text.extend(b"\n")
                i += 5
                continue
        text.append(b)
        i += 1
    lines = text.decode("latin-1").replace("\r", "").split("\n")
    return UartCapture(raw=raw, frames=frames, lines=lines)


def frame_locator(name: str, capture: UartCapture) -> str:
    if not capture.frames:
        return f"{name}:no-version-frame"
    return ", ".join(f"{name}@0x{f.offset:x}[{f.raw_hex}]" for f in capture.frames)
