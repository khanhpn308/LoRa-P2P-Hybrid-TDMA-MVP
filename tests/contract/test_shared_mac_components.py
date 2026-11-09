"""
Host unit and contract test execution for shared firmware components:
- firmware/components/airtime_policy
- firmware/components/lora_mac

Authority: Issue #13, Issue #179, Issue #180, Issue #181, Issue #186, Issue #131,
Issue #275 (removal of tdma_common),
contracts/radio-mac/specification.md,
C Coding Standard v2.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest


class TestSharedMacComponentsContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.mock_inc = cls.repo_root / "tests" / "unit" / "mock_esp"

        # airtime_policy
        cls.airtime_dir = cls.repo_root / "firmware" / "components" / "airtime_policy"
        cls.airtime_src = cls.airtime_dir / "src" / "airtime_policy.c"
        cls.airtime_inc = cls.airtime_dir / "include"
        cls.airtime_test = cls.airtime_dir / "test" / "test_airtime_policy.c"

        assert cls.airtime_src.is_file(), f"Source missing: {cls.airtime_src}"
        assert cls.airtime_test.is_file(), f"Test missing: {cls.airtime_test}"

    def test_compile_and_run_airtime_policy_tests(self):
        """Compile test_airtime_policy.c with strict C11 flags and execute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = Path(tmpdir) / "test_airtime_policy"
            cmd_compile = [
                "gcc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-std=c11",
                f"-I{self.airtime_inc}",
                f"-I{self.mock_inc}",
                str(self.airtime_src),
                str(self.airtime_test),
                "-o",
                str(bin_path),
            ]
            comp = subprocess.run(cmd_compile, capture_output=True, text=True)
            self.assertEqual(
                comp.returncode,
                0,
                f"airtime_policy compilation failed:\nSTDOUT:\n{comp.stdout}\nSTDERR:\n{comp.stderr}",
            )

            run = subprocess.run([str(bin_path)], capture_output=True, text=True)
            self.assertEqual(
                run.returncode,
                0,
                f"airtime_policy execution failed:\nSTDOUT:\n{run.stdout}\nSTDERR:\n{run.stderr}",
            )
            self.assertIn("ALL PASSED", run.stdout)


if __name__ == "__main__":
    unittest.main()
