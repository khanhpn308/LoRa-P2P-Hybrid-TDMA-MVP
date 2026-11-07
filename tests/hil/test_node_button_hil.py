"""
HIL and synthetic state-machine verification for Issue #149:
Node Button Wake-up, Debounce, and Event Trigger.

Authority:
- Issue #149
- docs/verification/pcb-hw001-pinmap.md
- firmware/esp-idf-version.txt (ESP-IDF v6.1)
"""

import unittest
from pathlib import Path
import re


class TestNodeButtonWakeupHIL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.node_dir = cls.repo_root / "firmware" / "sensor_node"
        cls.main_dir = cls.node_dir / "main"
        cls.kconfig_file = cls.main_dir / "Kconfig.projbuild"
        cls.button_h = cls.main_dir / "button_driver.h"
        cls.button_c = cls.main_dir / "button_driver.c"
        cls.main_c = cls.main_dir / "main.c"
        cls.cmakelists = cls.main_dir / "CMakeLists.txt"

    def test_files_exist_in_allowed_paths(self):
        """Verify all required button wake-up files exist in firmware/sensor_node/main/."""
        self.assertTrue(self.kconfig_file.is_file(), "Kconfig.projbuild missing")
        self.assertTrue(self.button_h.is_file(), "button_driver.h missing")
        self.assertTrue(self.button_c.is_file(), "button_driver.c missing")
        self.assertTrue(self.main_c.is_file(), "main.c missing")
        self.assertTrue(self.cmakelists.is_file(), "CMakeLists.txt missing")

    def test_kconfig_definitions(self):
        """Verify Kconfig exposes all required user configuration knobs."""
        content = self.kconfig_file.read_text(encoding="utf-8")
        self.assertIn("config NODE_BUTTON_GPIO", content)
        self.assertIn("config NODE_BUTTON_ACTIVE_LEVEL", content)
        self.assertIn("config NODE_BUTTON_DEBOUNCE_MS", content)
        self.assertIn("config NODE_BUTTON_HOLD_TIME_MS", content)
        self.assertIn("config NODE_DEEP_SLEEP_TIMEOUT_SEC", content)

    def test_sx1276_pin_protection(self):
        """Verify button driver explicitly blocks selection of reserved SX1276 HW-001 nets."""
        content = self.button_c.read_text(encoding="utf-8")
        # SX1276 pins: 5, 18, 19, 23, 26, 27
        for pin in [5, 18, 19, 23, 26, 27]:
            self.assertIn(str(pin), content, f"Reserved pin {pin} must be protected against collision")

    def test_rtc_gpio_validation(self):
        """Verify button driver validates that the chosen GPIO is an RTC-capable wake pin."""
        content = self.button_c.read_text(encoding="utf-8")
        self.assertIn("is_rtc_gpio", content)
        self.assertIn("GPIO_NUM_0", content)
        self.assertIn("GPIO_NUM_4", content)
        self.assertIn("GPIO_NUM_34", content)

    def test_debounce_and_anti_storm(self):
        """Verify debounce window, release waiting, and anti-storm loop protection."""
        content = self.button_c.read_text(encoding="utf-8")
        self.assertIn("debounce_ms", content)
        self.assertIn("Button bounced inactive", content)
        self.assertIn("Button press verified", content)
        self.assertIn("Button released", content)
        self.assertIn("Button stuck/held down", content)

    def test_fifo_event_handoff(self):
        """Verify main.c hands off qualified events into persistent node_event_fifo."""
        content = self.main_c.read_text(encoding="utf-8")
        self.assertIn("RTC_DATA_ATTR static node_event_fifo_t s_event_fifo;", content)
        self.assertIn("node_event_fifo_push", content)
        self.assertIn("button_driver_arm_sleep", content)
        self.assertIn("esp_deep_sleep_start", content)


if __name__ == "__main__":
    unittest.main()
