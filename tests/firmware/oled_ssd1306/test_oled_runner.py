"""
Host unit test runner for SSD1306 OLED driver component.
Authority: Issue #271, C Coding Standard v2, Quality Gates.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest


class TestOledSSD1306HostUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.oled_dir = cls.repo_root / "firmware" / "components" / "oled_ssd1306"
        cls.test_dir = cls.repo_root / "tests" / "firmware" / "oled_ssd1306"

    def test_oled_ssd1306_c_unit_suite(self):
        """Compile and execute SSD1306 C unit tests with -Wall -Wextra -Werror."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = Path(tmpdir) / "test_oled_bin"
            cmd = [
                "gcc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I", str(self.test_dir / "mock"),
                "-I", str(self.oled_dir / "include"),
                "-I", str(self.oled_dir / "src"),
                str(self.oled_dir / "src" / "oled_ssd1306.c"),
                str(self.test_dir / "test_oled_ssd1306.c"),
                "-o", str(bin_path),
            ]
            compile_res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(compile_res.returncode, 0, f"Compilation failed: {compile_res.stderr}")

            run_res = subprocess.run([str(bin_path)], capture_output=True, text=True)
            self.assertEqual(run_res.returncode, 0, f"Execution failed: {run_res.stderr}")
            self.assertIn("ALL SSD1306 UNIT TESTS PASSED SUCCESSFULLY!", run_res.stdout)


if __name__ == "__main__":
    unittest.main()
