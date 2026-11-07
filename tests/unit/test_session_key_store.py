"""
Host unit test execution for firmware/components/session_key_store.

Authority: Issue #238, DEC-SEC-05, C Coding Standard v2, contracts/mqtt/session-key-security.md.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest


class TestSessionKeyStoreUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.component_dir = cls.repo_root / "firmware" / "components" / "session_key_store"
        cls.c_inc = cls.component_dir / "include"
        cls.mock_inc = cls.repo_root / "tests" / "unit" / "mock_esp"

        cls.store_c = cls.component_dir / "src" / "session_key_store.c"
        cls.mock_nvs_c = cls.repo_root / "tests" / "unit" / "mock_nvs.c"
        cls.mock_crypto_c = cls.repo_root / "tests" / "unit" / "mock_crypto.c"
        cls.test_store_c = cls.repo_root / "tests" / "unit" / "test_session_key_store.c"

        assert cls.store_c.is_file(), f"Source not found: {cls.store_c}"
        assert cls.mock_nvs_c.is_file(), f"Mock NVS not found: {cls.mock_nvs_c}"
        assert cls.mock_crypto_c.is_file(), f"Mock Crypto not found: {cls.mock_crypto_c}"
        assert cls.test_store_c.is_file(), f"Test not found: {cls.test_store_c}"
        assert (cls.c_inc / "session_key_store.h").is_file(), "session_key_store.h missing"

    def test_compile_and_run_session_key_store_unit_tests(self):
        """Compile test_session_key_store.c with strict flags and execute all state transition tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = Path(tmpdir) / "test_session_key_store"
            cmd_compile = [
                "gcc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-std=c11",
                f"-I{self.c_inc}",
                f"-I{self.mock_inc}",
                str(self.store_c),
                str(self.mock_nvs_c),
                str(self.mock_crypto_c),
                str(self.test_store_c),
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
                f"Execution failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}",
            )
            self.assertIn("ALL Gateway Session Key Store Unit Tests PASSED", res.stdout)


if __name__ == "__main__":
    unittest.main()
