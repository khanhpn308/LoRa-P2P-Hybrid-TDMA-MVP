"""
Host unit test execution for V2 MAC framing, codecs, and Node Event FIFO.

Authority: Issue #131, C Coding Standard v2, contracts/radio-mac/specification.md.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest


class TestFirmwareV2Unit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.component_dir = cls.repo_root / "firmware" / "components" / "lora_mac"
        cls.c_inc = cls.component_dir / "include"
        cls.mock_inc = cls.repo_root / "tests" / "unit" / "mock_esp"

        cls.lora_mac_c = cls.component_dir / "src" / "lora_mac.c"
        cls.node_event_fifo_c = cls.component_dir / "src" / "node_event_fifo.c"

        cls.test_lora_mac_v2_c = cls.repo_root / "tests" / "unit" / "test_lora_mac_v2.c"
        cls.test_node_event_fifo_c = cls.repo_root / "tests" / "unit" / "test_node_event_fifo.c"
        cls.test_node_tdma_client_c = cls.repo_root / "tests" / "unit" / "test_node_tdma_client.c"

        cls.tdma_common_inc = cls.repo_root / "firmware" / "components" / "tdma_common" / "include"
        cls.airtime_policy_inc = cls.repo_root / "firmware" / "components" / "airtime_policy" / "include"
        cls.sensor_node_main_dir = cls.repo_root / "firmware" / "sensor_node" / "main"

        cls.tdma_common_c = cls.repo_root / "firmware" / "components" / "tdma_common" / "src" / "tdma_common.c"
        cls.airtime_policy_c = cls.repo_root / "firmware" / "components" / "airtime_policy" / "src" / "airtime_policy.c"
        cls.node_crypto_c = cls.sensor_node_main_dir / "node_crypto.c"
        cls.node_tdma_client_c = cls.sensor_node_main_dir / "node_tdma_client.c"

        assert cls.lora_mac_c.is_file(), f"Source not found: {cls.lora_mac_c}"
        assert cls.node_event_fifo_c.is_file(), f"Source not found: {cls.node_event_fifo_c}"
        assert cls.test_lora_mac_v2_c.is_file(), f"Test not found: {cls.test_lora_mac_v2_c}"
        assert cls.test_node_event_fifo_c.is_file(), f"Test not found: {cls.test_node_event_fifo_c}"
        assert cls.test_node_tdma_client_c.is_file(), f"Test not found: {cls.test_node_tdma_client_c}"
        assert cls.tdma_common_c.is_file(), f"Source not found: {cls.tdma_common_c}"
        assert cls.airtime_policy_c.is_file(), f"Source not found: {cls.airtime_policy_c}"
        assert cls.node_crypto_c.is_file(), f"Source not found: {cls.node_crypto_c}"
        assert cls.node_tdma_client_c.is_file(), f"Source not found: {cls.node_tdma_client_c}"

    def test_compile_and_run_lora_mac_v2_unit_tests(self):
        """Compile test_lora_mac_v2.c with strict flags and execute all V2 framing/codec tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = Path(tmpdir) / "test_lora_mac_v2"
            cmd_compile = [
                "gcc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-std=c11",
                f"-I{self.c_inc}",
                f"-I{self.mock_inc}",
                str(self.lora_mac_c),
                str(self.test_lora_mac_v2_c),
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
            self.assertIn("All LoRa MAC V2 unit tests PASSED successfully!", res.stdout)
            self.assertIn("Running test_lora_mac_v2_header_roundtrip ... PASSED", res.stdout)
            self.assertIn("Running test_lora_mac_v2_build_nonce ... PASSED", res.stdout)
            self.assertIn("Running test_lora_mac_v2_up_event_roundtrip ... PASSED", res.stdout)
            self.assertIn("Running test_lora_mac_v2_down_event_ack_roundtrip ... PASSED", res.stdout)
            self.assertIn("Running test_lora_mac_v2_up_health_reply_roundtrip ... PASSED", res.stdout)
            self.assertIn("Running test_lora_mac_v2_up_diag_metrics_roundtrip ... PASSED", res.stdout)
            self.assertIn("Running test_lora_mac_v2_beacon_roundtrip ... PASSED", res.stdout)

    def test_compile_and_run_node_event_fifo_unit_tests(self):
        """Compile test_node_event_fifo.c with strict flags and execute FIFO tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = Path(tmpdir) / "test_node_event_fifo"
            cmd_compile = [
                "gcc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-std=c11",
                f"-I{self.c_inc}",
                f"-I{self.mock_inc}",
                str(self.node_event_fifo_c),
                str(self.test_node_event_fifo_c),
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
            self.assertIn("All Node Event FIFO unit tests PASSED successfully!", res.stdout)
            self.assertIn("Running test_fifo_init ... PASSED", res.stdout)
            self.assertIn("Running test_fifo_push_and_peek ... PASSED", res.stdout)
            self.assertIn("Running test_fifo_ack_in_order ... PASSED", res.stdout)
            self.assertIn("Running test_fifo_ack_out_of_order ... PASSED", res.stdout)
            self.assertIn("Running test_fifo_overflow_drop_oldest ... PASSED", res.stdout)
            self.assertIn("Running test_fifo_retry_count ... PASSED", res.stdout)
            self.assertIn("Running test_fifo_negative_and_bounds ... PASSED", res.stdout)

    def test_compile_and_run_node_tdma_client_unit_tests(self):
        """Compile test_node_tdma_client.c with strict flags and execute TDMA slot client state tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = Path(tmpdir) / "test_node_tdma_client"
            cmd_compile = [
                "gcc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-std=c11",
                f"-I{self.c_inc}",
                f"-I{self.mock_inc}",
                f"-I{self.tdma_common_inc}",
                f"-I{self.airtime_policy_inc}",
                f"-I{self.sensor_node_main_dir}",
                str(self.lora_mac_c),
                str(self.node_event_fifo_c),
                str(self.tdma_common_c),
                str(self.airtime_policy_c),
                str(self.node_crypto_c),
                str(self.node_tdma_client_c),
                str(self.test_node_tdma_client_c),
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
            self.assertIn("All Node TDMA Slot Client unit tests PASSED successfully!", res.stdout)
            self.assertIn("Running test_node_tdma_client_init_and_config ... PASSED", res.stdout)
            self.assertIn("Running test_node_tdma_slot_boundary_calculation ... PASSED", res.stdout)
            self.assertIn("Running test_crypto_operations_roundtrip ... PASSED", res.stdout)
            self.assertIn("Running test_state_transition_success_pop ... PASSED", res.stdout)
            self.assertIn("Running test_state_transition_missed_and_corrupted_ack_retry ... PASSED", res.stdout)
            self.assertIn("Running test_state_transition_airtime_exhaustion_suppression ... PASSED", res.stdout)
            self.assertIn("Running test_state_transition_beacon_loss_lock ... PASSED", res.stdout)
            self.assertIn("Running test_zero_out_of_slot_rf_transmission ... PASSED", res.stdout)


if __name__ == "__main__":
    unittest.main()

