"""
Host unit test execution for V2 MAC framing, codecs, Node Event FIFO,
and OTA V2 Join Handshake.

Authority: Issue #131, Issue #241, Issue #275 (TDMA cleanup), C Coding Standard v2,
           contracts/radio-mac/specification.md.
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
        cls.lora_mac_join_crypto_c = cls.component_dir / "src" / "lora_mac_join_crypto.c"
        cls.node_event_fifo_c = cls.component_dir / "src" / "node_event_fifo.c"

        cls.test_lora_mac_v2_c = cls.repo_root / "tests" / "unit" / "test_lora_mac_v2.c"
        cls.test_node_event_fifo_c = cls.repo_root / "tests" / "unit" / "test_node_event_fifo.c"
        cls.test_firmware_v2_join_c = cls.repo_root / "tests" / "unit" / "test_firmware_v2_join.c"

        cls.airtime_policy_inc = cls.repo_root / "firmware" / "components" / "airtime_policy" / "include"
        cls.session_key_store_inc = cls.repo_root / "firmware" / "components" / "session_key_store" / "include"
        cls.gateway_transport_inc = cls.repo_root / "firmware" / "components" / "gateway_transport" / "include"

        cls.node_v2_join_dir = cls.repo_root / "firmware" / "components" / "node_v2_join"
        cls.node_v2_join_inc = cls.node_v2_join_dir / "include"
        cls.node_v2_join_c = cls.node_v2_join_dir / "src" / "node_v2_join.c"

        cls.gw_v2_join_dir = cls.repo_root / "firmware" / "components" / "gateway_v2_join"
        cls.gw_v2_join_inc = cls.gw_v2_join_dir / "include"
        cls.gateway_v2_join_c = cls.gw_v2_join_dir / "src" / "gateway_v2_join.c"

        cls.airtime_policy_c = cls.repo_root / "firmware" / "components" / "airtime_policy" / "src" / "airtime_policy.c"
        cls.mock_nvs_c = cls.repo_root / "tests" / "unit" / "mock_nvs.c"

        assert cls.lora_mac_c.is_file(), f"Source not found: {cls.lora_mac_c}"
        assert cls.lora_mac_join_crypto_c.is_file(), f"Source not found: {cls.lora_mac_join_crypto_c}"
        assert cls.node_event_fifo_c.is_file(), f"Source not found: {cls.node_event_fifo_c}"
        assert cls.test_lora_mac_v2_c.is_file(), f"Test not found: {cls.test_lora_mac_v2_c}"
        assert cls.test_node_event_fifo_c.is_file(), f"Test not found: {cls.test_node_event_fifo_c}"
        assert cls.test_firmware_v2_join_c.is_file(), f"Test not found: {cls.test_firmware_v2_join_c}"
        assert cls.airtime_policy_c.is_file(), f"Source not found: {cls.airtime_policy_c}"
        assert cls.node_v2_join_c.is_file(), f"Source not found: {cls.node_v2_join_c}"
        assert cls.gateway_v2_join_c.is_file(), f"Source not found: {cls.gateway_v2_join_c}"
        assert cls.mock_nvs_c.is_file(), f"Source not found: {cls.mock_nvs_c}"

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

    def test_compile_and_run_v2_join_handshake_unit_tests(self):
        """Compile test_firmware_v2_join.c with strict flags and execute V2 Join handshake tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = Path(tmpdir) / "test_firmware_v2_join"
            cmd_compile = [
                "gcc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-std=c11",
                f"-I{self.c_inc}",
                f"-I{self.mock_inc}",
                f"-I{self.node_v2_join_inc}",
                f"-I{self.gw_v2_join_inc}",
                f"-I{self.session_key_store_inc}",
                f"-I{self.gateway_transport_inc}",
                str(self.lora_mac_c),
                str(self.lora_mac_join_crypto_c),
                str(self.node_v2_join_c),
                str(self.gateway_v2_join_c),
                str(self.mock_nvs_c),
                str(self.test_firmware_v2_join_c),
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
            self.assertIn("ALL TESTS PASSED", res.stdout)
            self.assertIn("Running test_join_frame_codecs_roundtrip ... PASSED", res.stdout)
            self.assertIn("Running test_join_crypto_derivations_and_proofs ... PASSED", res.stdout)
            self.assertIn("Running test_rfc7748_all_zeros_shared_secret_abort ... PASSED", res.stdout)
            self.assertIn("Running test_monotonic_nvs_counter_commit_and_rollback_lockout ... PASSED", res.stdout)
            self.assertIn("Running test_cad_retry_exhaustion ... PASSED", res.stdout)
            self.assertIn("Running test_node_complete_handshake_end_to_end ... PASSED", res.stdout)
            self.assertIn("Running test_gateway_relay_engine_and_mqtt_schema ... PASSED", res.stdout)


if __name__ == "__main__":
    unittest.main()
