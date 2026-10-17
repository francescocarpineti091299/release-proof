"""Offline regressions for emulator completion and application UART markers."""

import unittest
from pathlib import Path

from rp_mcuboot.renode import Phase, ScenarioResult
from rp_mcuboot.templates import _result


class EvidenceTests(unittest.TestCase):
    def test_partial_uart_never_overrides_process_failure(self):
        for code, timeout, expected in [
            (1, False, "ERROR"),
            (None, False, "ERROR"),
            (None, True, "INCONCLUSIVE"),
            (0, False, "PASS"),
        ]:
            result = ScenarioResult("test", [], "script", "log", code, timeout, 1)
            self.assertEqual(
                _result("APPLIED", {"APPLIED": "PASS"}, "partial UART", [], result).outcome,
                expected,
            )

    def test_application_marker_and_locator(self):
        phase = Phase(
            Path("uart.log"),
            "ART-uart",
            ["boot noise", "RP-APP version=1.2.3 build=4 key=0123456789abcdef slot=0x10000"],
        )
        marker = phase.markers()[0]
        self.assertEqual(marker.version, "1.2.3")
        self.assertEqual(marker.line, 2)
        self.assertEqual(phase.loc(marker.line), "uart.log:L2")


if __name__ == "__main__":
    unittest.main()
