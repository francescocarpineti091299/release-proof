"""Pins, paths and build parameters of the wolfBoot runner (single source of truth)."""

from __future__ import annotations

import os
from pathlib import Path

PARSER_VERSION = "0.1.0"

BAKED_TREE = Path(os.environ.get("WOLFBOOT_BAKED_TREE", "/opt/wolfboot"))
PINNED_WOLFBOOT_COMMIT = "4c79eee999b7083743811f37928322fe78b9fdb1"
PINNED_WOLFSSL_COMMIT = "4aa1ad7a5b4f7be86d88cc26fe3880a31ff7de9f"
WOLFBOOT_REPO = "https://github.com/wolfSSL/wolfBoot"

BOARD_CONFIG = Path("config/examples/nrf52840.config")
RENODE_PLATFORM = "platforms/cpus/nrf52840.repl"
RENODE_MIPS = 100

# Build variants. ECC256 = deployed state (G1 of the WP0 reference run), ML-DSA-87 = candidate (G2).
ECC_MAKE_ARGS = ["SIGN=ECC256"]
MLDSA_MAKE_ARGS = [
    "SIGN=ML_DSA",
    "ML_DSA_LEVEL=5",
    "WOLFBOOT_SMALL_STACK=0",
    "IMAGE_SIGNATURE_SIZE=4627",
    "IMAGE_HEADER_SIZE=12288",
    "WOLFBOOT_SECTOR_SIZE=0x3000",
]
DUAL_MAKE_ARGS = [
    "SIGN=ECC256",
    "SIGN_SECONDARY=ML_DSA",
    "ML_DSA_LEVEL=5",
    "WOLFBOOT_SMALL_STACK=0",
    "IMAGE_HEADER_SIZE=12288",
    "WOLFBOOT_SECTOR_SIZE=0x3000",
]
# IMAGE_HEADER_SIZE default of options.mk for SIGN=ECC256 on this commit.
ECC_DEFAULT_HEADER_SIZE = 256

TEST_UPDATE_VERSION = 2

# Per-step wall-clock limits (seconds).
COPY_TIMEOUT_S = 120
MAKE_TIMEOUT_S = 600
EMULATION_WALL_TIMEOUT_S = 120

# Deterministic virtual time per emulation phase (Renode `emulation RunFor`).
BOOT_PHASE_VIRTUAL_S = 2.0
UPDATE_PHASE_VIRTUAL_S = 4.0

# Paths never copied into a per-run tree.
COPY_IGNORE = {".git"}
