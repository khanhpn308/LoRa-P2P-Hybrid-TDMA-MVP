"""
Host unit test execution for firmware/components/lora_mac framing parser and encoder.

Authority: Issue #186, C Coding Standard v2, contracts/radio-mac/specification.md.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest


class TestLoraMacFramingUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.component_dir = cls.repo_root / "firmware" / "components" / "lora_mac"
        cls.c_src = cls.component_dir / "src" / "lora_mac.c"
        cls.c_inc = cls.component_dir / "include"
        cls.test_c = cls.repo_root / "tests" / "unit" / "test_lora_mac.c"
        cls.mock_inc = cls.repo_root / "tests" / "unit" / "mock_esp"

        assert cls.c_src.is_file(), f"Source not found: {cls.c_src}"
        assert cls.test_c.is_file(), f"Test not found: {cls.test_c}"
        assert (cls.c_inc / "lora_mac.h").is_file(), "lora_mac.h missing"

    def test_compile_and_run_lora_mac_framing_unit_tests(self):
        """Compile test_lora_mac.c with strict flags and execute all framing tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = Path(tmpdir) / "test_lora_mac"
            cmd_compile = [
                "gcc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-std=c11",
                f"-I{self.c_inc}",
                f"-I{self.mock_inc}",
                str(self.c_src),
                str(self.test_c),
                "-o",
                str(bin_path),
            ]
            comp = subprocess.run(cmd_compile, capture_output=True, text=True)
            self.assertEqual(
                comp.returncode,
                0,
                f"Compilation failed:\nSTDOUT:\n{comp.stdout}\nSTDERR:\n{comp.stderr}",
            )

            res = subprocess.run([str(bin_path)], capture_output=True, text=True)
            self.assertEqual(
                res.returncode,
                0,
                f"Test execution failed with code {res.returncode}:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}",
            )
            self.assertIn("All LoRa MAC framing tests PASSED successfully!", res.stdout)
            self.assertIn("Running test_lora_mac_roundtrip_all_fields ... PASSED", res.stdout)
            self.assertIn("Running test_lora_mac_roundtrip_all_message_types ... PASSED", res.stdout)
            self.assertIn("Running test_lora_mac_boundary_payload_lengths ... PASSED", res.stdout)
            self.assertIn("Running test_lora_mac_header_parse_negative ... PASSED", res.stdout)
            self.assertIn("Running test_lora_mac_header_encode_negative ... PASSED", res.stdout)


if __name__ == "__main__":
    unittest.main()
