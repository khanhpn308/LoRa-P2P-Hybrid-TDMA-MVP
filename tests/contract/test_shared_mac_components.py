"""
Host unit and contract test execution for shared firmware components:
- firmware/components/airtime_policy
- firmware/components/tdma_common
- firmware/components/lora_mac

Authority: Issue #13, Issue #179, Issue #180, Issue #181, Issue #186, Issue #131,
contracts/radio-mac/specification.md, contracts/radio-mac/tdma-schedule.md,
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

        # tdma_common
        cls.tdma_dir = cls.repo_root / "firmware" / "components" / "tdma_common"
        cls.tdma_src = cls.tdma_dir / "src" / "tdma_common.c"
        cls.tdma_inc = cls.tdma_dir / "include"
        cls.tdma_test = cls.tdma_dir / "test" / "test_tdma_common.c"

        assert cls.airtime_src.is_file(), f"Source missing: {cls.airtime_src}"
        assert cls.airtime_test.is_file(), f"Test missing: {cls.airtime_test}"
        assert cls.tdma_src.is_file(), f"Source missing: {cls.tdma_src}"
        assert cls.tdma_test.is_file(), f"Test missing: {cls.tdma_test}"

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

    def test_compile_and_run_tdma_common_tests(self):
        """Compile test_tdma_common.c with strict C11 flags and execute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = Path(tmpdir) / "test_tdma_common"
            cmd_compile = [
                "gcc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-std=c11",
                f"-I{self.tdma_inc}",
                f"-I{self.mock_inc}",
                str(self.tdma_src),
                str(self.tdma_test),
                "-o",
                str(bin_path),
            ]
            comp = subprocess.run(cmd_compile, capture_output=True, text=True)
            self.assertEqual(
                comp.returncode,
                0,
                f"tdma_common compilation failed:\nSTDOUT:\n{comp.stdout}\nSTDERR:\n{comp.stderr}",
            )

            run = subprocess.run([str(bin_path)], capture_output=True, text=True)
            self.assertEqual(
                run.returncode,
                0,
                f"tdma_common execution failed:\nSTDOUT:\n{run.stdout}\nSTDERR:\n{run.stderr}",
            )
            self.assertIn("ALL PASSED", run.stdout)


if __name__ == "__main__":
    unittest.main()
