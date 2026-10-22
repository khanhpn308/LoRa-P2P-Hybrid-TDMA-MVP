"""Keep firmware CI and AI Harness on the approved project-wide ESP-IDF v6.1 baseline."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "agent_harness"))
from toolchains.resolver import load_project_version


class ApprovedIDFBaselineTests(unittest.TestCase):
    def test_project_pin_is_approved_v61(self):
        self.assertEqual(load_project_version(ROOT), "6.1")
        self.assertEqual(
            (ROOT / "firmware/esp-idf-version.txt").read_text(encoding="utf-8"),
            "v6.1\n",
        )

    def test_both_firmware_ci_jobs_read_same_approved_pin(self):
        ci = (ROOT / ".github/workflows/ci-firmware.yml").read_text(encoding="utf-8")
        self.assertEqual(ci.count("esp_idf_version: ${{ steps.idf.outputs.version }}"), 2)
        self.assertEqual(ci.count("firmware/esp-idf-version.txt"), 2)
        self.assertIn("gateway-esp32-build", ci)
        self.assertIn("node-esp32-build", ci)
        self.assertNotIn('esp_idf_version: "release-v5.4"', ci)
        self.assertNotIn("esp_idf_version: latest", ci)

    def test_accepted_adr_documents_technical_scope(self):
        adr = (ROOT / "docs/adr/0003-esp-idf-v6-1.md").read_text(encoding="utf-8")
        self.assertIn("APPROVED BY OWNER", adr)
        self.assertIn("NOT_VERIFIED", adr)
        self.assertIn("firmware/esp-idf-version.txt", adr)


if __name__ == "__main__":
    unittest.main()
