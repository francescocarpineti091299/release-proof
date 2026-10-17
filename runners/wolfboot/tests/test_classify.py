"""Offline unit tests of the UART / classification logic (stdlib unittest, no Docker needed).

    set PYTHONPATH=runners\\common;runners\\wolfboot
    backend\\.venv\\Scripts\\python.exe -m unittest discover -s runners\\wolfboot\\tests -v
"""

from __future__ import annotations

import unittest
from pathlib import Path

from rp_wolfboot.builds import build_update_image
from rp_wolfboot.emulation import Phase
from rp_wolfboot.family import classify_boot, classify_staged_update
from rp_wolfboot.parsers import BOOT_REFUSAL_MARKERS, parse_config, parse_target_h, parse_uart

BOOT_V1 = (
    b"Boot partition: 0x20000 (sz 584, ver 0x1, type 0x201)\r\n"
    b"Partition 1 header magic 0x00000000 invalid at 0x60000\r\n"
    b"Booting version: 0x1\r\nChecking integrity...done\r\r\nVerifying signature...done\r\r\n*\x00\x00\x00\x01"
)
PANIC = (
    b"Booting version: 0x1\r\nChecking integrity...Boot failed: Hdr 1, Hash 0, Sig 0\r\n"
    b"Trying emergency update\r\nBoot failed! No boot option available!\r\nwolfBoot: PANIC!\r\n"
)
UPDATE_REJECTED = b"Update type invalid 0xB01!=0x200\r\nBooting version: 0x1\r\n*\x00\x00\x00\x01"
UPDATE_APPLIED = b"Copy sector 0 (part 1->2)\r\nBooting version: 0x2\r\n*\x00\x00\x00\x02"


def phase(name: str, raw: bytes) -> Phase:
    return Phase(name, Path(f"{name}.bin"), parse_uart(raw), f"ART-{name}")


class UartTests(unittest.TestCase):
    def test_frame_and_text(self) -> None:
        cap = parse_uart(BOOT_V1)
        self.assertEqual(cap.versions(), [1])
        self.assertEqual(cap.booting_versions(), [1])
        self.assertEqual(cap.markers(BOOT_REFUSAL_MARKERS), {})  # empty-update-partition line is not a refusal

    def test_truncated_frame_is_not_a_version(self) -> None:
        self.assertEqual(parse_uart(b"*\x00\x00").versions(), [])

    def test_boot_classification(self) -> None:
        self.assertEqual(classify_boot(phase("boot", BOOT_V1))[:2], ("BOOT_OK", 1))
        self.assertEqual(classify_boot(phase("boot", PANIC))[0], "FAIL")
        # Silence / timeout is never a refusal.
        self.assertEqual(classify_boot(phase("boot", b""))[0], "UNKNOWN")
        self.assertEqual(classify_boot(phase("boot", b"Booting version: 0x1\r\n"))[0], "UNKNOWN")

    def test_staged_update(self) -> None:
        boot = phase("boot", BOOT_V1)
        self.assertEqual(classify_staged_update(boot, phase("update", UPDATE_APPLIED), 2)[0], "APPLIED")
        self.assertEqual(classify_staged_update(boot, phase("update", UPDATE_REJECTED), 2)[0], "NOT_APPLIED")
        self.assertEqual(classify_staged_update(boot, phase("update", b""), 2)[0], "UNKNOWN")
        self.assertEqual(
            classify_staged_update(boot, phase("update", b"Update verify failed: Hdr 0\r\n"), 2)[0], "UNKNOWN"
        )
        self.assertEqual(classify_staged_update(phase("boot", b""), phase("update", UPDATE_REJECTED), 2)[0],
                         "UNKNOWN")


class ConfigTests(unittest.TestCase):
    def test_config_and_target_h(self) -> None:
        cfg = parse_config("SIGN?=ECC256\nWOLFBOOT_PARTITION_SIZE?=0x40000 # c\n")
        self.assertEqual(cfg["WOLFBOOT_PARTITION_SIZE"], ("0x40000", 2))
        th = parse_target_h(
            "#define WOLFBOOT_SECTOR_SIZE                 0x3000\n"
            "        #define WOLFBOOT_PARTITION_BOOT_ADDRESS   (ARCH_FLASH_OFFSET + 0x20000)\n"
            "    #define WOLFBOOT_PARTITION_BOOT_ADDRESS   0x20000\n"
        )
        self.assertEqual(th, {"WOLFBOOT_SECTOR_SIZE": 0x3000, "WOLFBOOT_PARTITION_BOOT_ADDRESS": 0x20000})

    def test_update_image_layout(self) -> None:
        img = build_update_image(b"WOLF" + b"\x00" * 10, 0x40000)
        self.assertEqual(len(img), 0x40000)
        self.assertEqual(img[-5:], b"pBOOT")
        self.assertEqual(img[14:20], b"\xff" * 6)


if __name__ == "__main__":
    unittest.main()
