"""Paths and constants of the runner image (overridable through env for local debugging)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

HOME = Path(os.environ.get("RP_MCUBOOT_HOME", Path(__file__).resolve().parents[1]))
APP_SRC = HOME / "app"
RENODE_DIR = HOME / "renode"
NVMC_CS = RENODE_DIR / "rp_nrf52840_nvmc.cs"
REPL_TEMPLATE = RENODE_DIR / "nrf52840_rp.repl.in"
RESC_TEMPLATE = RENODE_DIR / "scenario.resc.in"

ZWS = Path(os.environ.get("RP_ZEPHYR_WORKSPACE", "/opt/zws"))
ZEPHYR_BASE = ZWS / "zephyr"
MCUBOOT_DIR = ZWS / "bootloader" / "mcuboot"
IMGTOOL = MCUBOOT_DIR / "scripts" / "imgtool.py"
MANIFEST_FREEZE = ZWS / "manifest.freeze.yml"
WEST_LIST = ZWS / "west-list.txt"
PIP_FREEZE = ZWS / "pip-freeze.txt"

SDK_DIR = Path(os.environ.get("ZEPHYR_SDK_INSTALL_DIR", "/opt/zephyr-sdk-0.17.4"))
ARM_GCC = SDK_DIR / "arm-zephyr-eabi" / "bin" / "arm-zephyr-eabi-gcc"
RENODE = os.environ.get("RP_RENODE", "renode")
SVD_PATH = Path(os.environ.get("RP_NRF52840_SVD", "/opt/rp/renode-assets/NRF52840.svd.gz"))

PYTHON = sys.executable
BOARD = "nrf52840dk/nrf52840"
APP_IMAGE = "app"  # sysbuild names the application image after its source directory
FLASH_SIZE = 0x100000
HEADER_SIZE = 0x200
ALIGN = 4

RENODE_VERSION = "1.16.1"
ZEPHYR_VERSION = "v4.2.0"
SDK_VERSION = "0.17.4"
