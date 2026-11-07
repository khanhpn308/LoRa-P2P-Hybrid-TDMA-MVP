"""
Host unit test execution for firmware/components/gateway_transport.

Authority: Issue #244, ADR-0002, ADR-0003, C Coding Standard v2, contracts/mqtt/topics.md.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest


class TestGatewayTransportUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.component_dir = cls.repo_root / "firmware" / "components" / "gateway_transport"
        cls.c_inc = cls.component_dir / "include"
        cls.mock_inc = cls.repo_root / "tests" / "unit" / "mock_esp"

        cls.transport_c = cls.component_dir / "src" / "gateway_transport.c"
        cls.wifi_c = cls.component_dir / "src" / "gateway_wifi.c"
        cls.mqtt_c = cls.component_dir / "src" / "gateway_mqtt.c"
        cls.test_c = cls.repo_root / "tests" / "unit" / "test_gateway_transport.c"

        assert cls.transport_c.is_file(), f"Source not found: {cls.transport_c}"
        assert cls.wifi_c.is_file(), f"Source not found: {cls.wifi_c}"
        assert cls.mqtt_c.is_file(), f"Source not found: {cls.mqtt_c}"
        assert cls.test_c.is_file(), f"Test not found: {cls.test_c}"
        assert (cls.c_inc / "gateway_transport.h").is_file(), "gateway_transport.h missing"

    def test_compile_and_run_gateway_transport_unit_tests(self):
        """Compile test_gateway_transport.c with strict C11 flags and execute all tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = Path(tmpdir) / "test_gateway_transport"
            cmd_compile = [
                "gcc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-std=c11",
                f"-I{self.c_inc}",
                f"-I{self.mock_inc}",
                str(self.transport_c),
                str(self.wifi_c),
                str(self.mqtt_c),
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
                f"Execution failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}",
            )
            self.assertIn("ALL Gateway Transport Unit Tests PASSED", res.stdout)


if __name__ == "__main__":
    unittest.main()
