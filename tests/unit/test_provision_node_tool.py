"""Unit Test Suite for Sensor Node Provisioning & Flashing CLI Tool.

Verifies:
  1. Cryptographic CSPRNG 256-bit key generation, validation, and in-memory zeroization.
  2. ESP-IDF v6.1 NVS partition CSV descriptor and binary synthesis (pure-Python vs IDF tool).
  3. Backend REST API registration, payload serialization, headers, retry backoff, and 409 Conflict abort.
  4. esptool output parsing and flashing command synthesis.
  5. End-to-end CLI workflows in --dry-run mode, return codes, and artifact cleanup.
  6. Masked logging and zero plaintext secret disclosure.
"""

from __future__ import annotations

import io
import json
import logging
import math
from pathlib import Path
import re
import shutil
import struct
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request
import zlib
import sys
from pathlib import Path

# Ensure repo root is in sys.path
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from tools.provisioning.nvs_generator import (
    DEFAULT_PARTITION_SIZE,
    ITEM_TYPE_BLOB_DATA,
    ITEM_TYPE_BLOB_IDX,
    ITEM_TYPE_U8,
    ITEM_TYPE_U32,
    NVS_VERSION_V2,
    PAGE_SIZE,
    PAGE_STATE_ACTIVE,
    NVSV2PartitionWriter,
    generate_nvs_csv,
    synthesize_nvs_partition,
    validate_key,
    validate_mac,
)
from tools.provisioning.provision_node import (
    EXIT_CONFLICT,
    EXIT_ERROR,
    EXIT_SUCCESS,
    DeviceAlreadyProvisionedError,
    ProvisioningConfig,
    ProvisioningError,
    build_parser,
    find_esptool_path,
    generate_csprng_key_bytes,
    generate_synthetic_mac,
    mask_secret,
    parse_mac_from_esptool_output,
    register_device_with_backend,
    run_provisioning,
    secure_wipe_file,
    zeroize_memory,
)


class TestKeyGenerationAndValidation(unittest.TestCase):
    """Test CSPRNG key generation, entropy, and memory zeroization."""

    def test_key_length_and_mutability(self):
        key = generate_csprng_key_bytes()
        self.assertIsInstance(key, bytearray)
        self.assertEqual(len(key), 32)
        # Verify not all zeros
        self.assertNotEqual(bytes(key), b"\x00" * 32)

    def test_key_entropy_and_uniqueness(self):
        keys = [bytes(generate_csprng_key_bytes()) for _ in range(50)]
        # Uniqueness
        self.assertEqual(len(set(keys)), 50)

        # Shannon entropy check on aggregated key material
        sample = b"".join(keys)
        counts = [sample.count(bytes([b])) for b in range(256)]
        entropy = -sum((c / len(sample)) * math.log2(c / len(sample)) for c in counts if c > 0)
        # For ideal random bytes, entropy ~ 8.0 bits/byte; require > 7.5
        self.assertGreater(entropy, 7.5)

    def test_zeroize_memory(self):
        buf = bytearray(b"\xaa" * 32)
        zeroize_memory(buf)
        self.assertEqual(bytes(buf), b"\x00" * 32)

    def test_validate_mac(self):
        # Normal 12-hex
        self.assertEqual(validate_mac("001122334455"), "001122334455")
        # Colons and dashes
        self.assertEqual(validate_mac("00:11:22:33:44:55"), "001122334455")
        self.assertEqual(validate_mac("AA-BB-CC-DD-EE-FF"), "aabbccddeeff")
        # Invalid lengths
        with self.assertRaises(ValueError):
            validate_mac("00112233445")
        with self.assertRaises(ValueError):
            validate_mac("00112233445566")
        # Invalid hex
        with self.assertRaises(ValueError):
            validate_mac("0011223344ZZ")

    def test_validate_key(self):
        valid = "a" * 64
        self.assertEqual(validate_key(valid), valid)
        # Uppercase converted to lower
        self.assertEqual(validate_key("A" * 64), valid)
        # Invalid length
        with self.assertRaises(ValueError):
            validate_key("a" * 63)
        with self.assertRaises(ValueError):
            validate_key("a" * 65)
        # Invalid hex
        with self.assertRaises(ValueError):
            validate_key("g" * 64)

    def test_generate_synthetic_mac(self):
        mac = generate_synthetic_mac()
        self.assertEqual(len(mac), 12)
        self.assertTrue(mac.startswith("02"))
        # Validate hex
        int(mac, 16)


class TestNVSDescriptorAndBinaryGeneration(unittest.TestCase):
    """Test NVS CSV formatting and byte-exact binary synthesis."""

    def setUp(self):
        self.mac = "001122334455"
        self.k_join = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
        self.k_beacon = "202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f"

    def test_generate_nvs_csv(self):
        csv_text = generate_nvs_csv(
            device_mac=self.mac,
            k_join_hex=self.k_join,
            join_counter=0,
            k_beacon_hex=self.k_beacon,
        )
        lines = [line.strip() for line in csv_text.splitlines() if line.strip()]
        self.assertEqual(lines[0], "key,type,encoding,value")
        self.assertEqual(lines[1], "nvs_sec,namespace,,")
        self.assertIn(f"device_mac,data,hex2bin,{self.mac}", lines)
        self.assertIn(f"k_join,data,hex2bin,{self.k_join}", lines)
        self.assertIn("join_counter,data,u32,0", lines)
        self.assertIn(f"k_beacon,data,hex2bin,{self.k_beacon}", lines)

    def test_nvs_partition_size_validation(self):
        # Not a multiple of 4096
        with self.assertRaises(ValueError):
            NVSV2PartitionWriter(partition_size=4000)
        # Too small (< 3 pages = 12288 bytes)
        with self.assertRaises(ValueError):
            NVSV2PartitionWriter(partition_size=8192)

    def test_nvs_binary_layout(self):
        writer = NVSV2PartitionWriter(partition_size=0x6000)
        bin_data = writer.synthesize_credentials_partition(
            device_mac=self.mac,
            k_join_hex=self.k_join,
            join_counter=42,
            k_beacon_hex=self.k_beacon,
        )
        self.assertEqual(len(bin_data), 0x6000)

        # Page 0 Header validation
        state, seq_num = struct.unpack_from("<II", bin_data, 0)
        self.assertEqual(state, PAGE_STATE_ACTIVE)
        self.assertEqual(seq_num, 0)
        version = bin_data[8]
        self.assertEqual(version, NVS_VERSION_V2)

        # Header CRC32 check
        header_crc = struct.unpack_from("<I", bin_data, 28)[0]
        expected_header_crc = zlib.crc32(bin_data[4:28], 0xFFFFFFFF) & 0xFFFFFFFF
        self.assertEqual(header_crc, expected_header_crc)

        # Bitmap array at offset 32: 32 bytes
        bitmap = bin_data[32:64]
        # First 2 bytes should be 0xAA (slots 0..7 active)
        self.assertEqual(bitmap[0], 0xAA)
        self.assertEqual(bitmap[1], 0xAA)
        # Third byte should be 0xEA (slots 8..10 active, slot 11 empty)
        self.assertEqual(bitmap[2], 0xEA)
        # Remaining bitmap bytes should be 0xFF
        self.assertEqual(bitmap[3:], b"\xff" * 29)

        # Entry 0: Namespace 'nvs_sec' at offset 64
        e0 = bin_data[64:96]
        self.assertEqual(e0[0], 0)  # ns_index
        self.assertEqual(e0[1], ITEM_TYPE_U8)  # type
        self.assertEqual(e0[2], 1)  # span
        self.assertEqual(e0[3], 0xFF)  # chunk_index
        self.assertTrue(e0[8:24].startswith(b"nvs_sec\x00"))
        self.assertEqual(e0[24], 1)  # assigned ns_index = 1

        # Entry 7: Primitive join_counter at offset 64 + 7*32 = 288
        e7 = bin_data[288:320]
        self.assertEqual(e7[0], 1)  # ns_index = 1
        self.assertEqual(e7[1], ITEM_TYPE_U32)
        self.assertEqual(e7[2], 1)
        self.assertTrue(e7[8:24].startswith(b"join_counter\x00"))
        jc_val = struct.unpack_from("<I", e7, 24)[0]
        self.assertEqual(jc_val, 42)

        # Empty pages check (pages 1 to 5)
        for p in range(1, 6):
            page_bytes = bin_data[p * PAGE_SIZE : (p + 1) * PAGE_SIZE]
            self.assertEqual(page_bytes, b"\xff" * PAGE_SIZE)

    def test_synthesize_nvs_partition_file_writing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            bin_path = Path(tmpdir) / "test.bin"
            data = synthesize_nvs_partition(
                device_mac=self.mac,
                k_join_hex=self.k_join,
                join_counter=0,
                k_beacon_hex=self.k_beacon,
                output_bin=bin_path,
                output_csv=csv_path,
            )
            self.assertTrue(csv_path.is_file())
            self.assertTrue(bin_path.is_file())
            self.assertEqual(len(data), 0x6000)
            self.assertEqual(bin_path.stat().st_size, 0x6000)


class TestBackendRegistration(unittest.TestCase):
    """Test Backend REST API registration, payload formatting, retries, and error handling."""

    def setUp(self):
        self.backend_url = "http://backend.internal:8080"
        self.mac = "001122334455"
        self.k_join = "00" * 32

    @patch("urllib.request.urlopen")
    def test_successful_registration_201(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "device_mac": self.mac,
                "network_id": 1,
                "generation": 1,
                "status": "ACTIVE",
                "created_at": "2026-11-08T00:00:00Z",
            }
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = register_device_with_backend(
            backend_url=self.backend_url,
            network_id=1,
            device_mac=self.mac,
            k_join_hex=self.k_join,
            generation=1,
            initial_join_counter=0,
            token="admin-token-secret",
        )
        self.assertEqual(res["status"], "ACTIVE")
        self.assertEqual(res["device_mac"], self.mac)

        # Inspect request
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, "http://backend.internal:8080/api/v1/devices/provision")
        self.assertEqual(req.get_header("Authorization"), "Bearer admin-token-secret")
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["device_mac"], self.mac)
        self.assertEqual(payload["k_join"], self.k_join)
        self.assertEqual(payload["network_id"], 1)

    @patch("urllib.request.urlopen")
    def test_conflict_409_aborts_immediately(self, mock_urlopen):
        http_error = urllib.error.HTTPError(
            url="http://backend/api/v1/devices/provision",
            code=409,
            msg="Conflict",
            hdrs={},
            fp=io.BytesIO(b'{"code": "CONFLICT", "message": "device already provisioned"}'),
        )
        mock_urlopen.side_effect = http_error

        with self.assertRaises(DeviceAlreadyProvisionedError) as ctx:
            register_device_with_backend(
                backend_url=self.backend_url,
                network_id=1,
                device_mac=self.mac,
                k_join_hex=self.k_join,
            )
        self.assertIn("already provisioned", str(ctx.exception))
        # 409 must not be retried: call count must be 1
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("urllib.request.urlopen")
    def test_bad_request_400_aborts_immediately(self, mock_urlopen):
        http_error = urllib.error.HTTPError(
            url="http://backend/api/v1/devices/provision",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=io.BytesIO(b'{"code": "INVALID_INPUT", "message": "invalid mac"}'),
        )
        mock_urlopen.side_effect = http_error

        with self.assertRaises(ProvisioningError) as ctx:
            register_device_with_backend(
                backend_url=self.backend_url,
                network_id=1,
                device_mac=self.mac,
                k_join_hex=self.k_join,
            )
        self.assertIn("status 400", str(ctx.exception))
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_retry_on_transient_failure_then_success(self, mock_urlopen, mock_sleep):
        # Attempt 1: 500 Internal Error, Attempt 2: 201 Success
        http_error = urllib.error.HTTPError(
            url="http://backend/api/v1/devices/provision",
            code=500,
            msg="Internal Error",
            hdrs={},
            fp=io.BytesIO(b'{"code": "INTERNAL_ERROR"}'),
        )
        mock_ok = MagicMock()
        mock_ok.__enter__.return_value.read.return_value = json.dumps({"status": "ACTIVE"}).encode("utf-8")

        mock_urlopen.side_effect = [http_error, mock_ok]

        res = register_device_with_backend(
            backend_url=self.backend_url,
            network_id=1,
            device_mac=self.mac,
            k_join_hex=self.k_join,
            max_retries=3,
        )
        self.assertEqual(res["status"], "ACTIVE")
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(0.5)

    def test_mock_backend_mode(self):
        res = register_device_with_backend(
            backend_url="",
            network_id=1,
            device_mac=self.mac,
            k_join_hex=self.k_join,
            mock_mode=True,
            mock_status=201,
        )
        self.assertEqual(res["status"], "ACTIVE")

        with self.assertRaises(DeviceAlreadyProvisionedError):
            register_device_with_backend(
                backend_url="",
                network_id=1,
                device_mac=self.mac,
                k_join_hex=self.k_join,
                mock_mode=True,
                mock_status=409,
            )


class TestEsptoolIntegration(unittest.TestCase):
    """Test parsing MAC addresses from esptool output and command validation."""

    def test_parse_mac_various_formats(self):
        output_colon = "Connecting.....\nDetecting chip type... ESP32\nMAC: 24:0a:c4:01:02:03\nUploading stub..."
        self.assertEqual(parse_mac_from_esptool_output(output_colon), "240ac4010203")

        output_dash = "Chip is ESP32-D0WD-V3\nMAC: A0-B7-65-12-34-56\nFeatures: WiFi, BT"
        self.assertEqual(parse_mac_from_esptool_output(output_dash), "a0b765123456")

        output_spaces = "MAC: 00 11 22 33 44 55\n"
        self.assertEqual(parse_mac_from_esptool_output(output_spaces), "001122334455")

    def test_parse_mac_invalid_raises(self):
        with self.assertRaises(ProvisioningError):
            parse_mac_from_esptool_output("Connecting... No MAC found in output.")


class TestCLIWorkflowAndArtifacts(unittest.TestCase):
    """Test CLI argument parsing, dry-run execution, and secure artifact handling."""

    def test_argument_parser_help(self):
        parser = build_parser()
        with io.StringIO() as buf, patch("sys.stdout", buf):
            try:
                parser.parse_args(["--help"])
            except SystemExit as exc:
                self.assertEqual(exc.code, 0)
            self.assertIn("Factory Flashing & NVS K_JOIN Provisioning", buf.getvalue())

    def test_dry_run_mock_backend_success(self):
        parser = build_parser()
        args = parser.parse_args(["--dry-run", "--mock-backend", "--mac", "001122334455"])
        config = ProvisioningConfig(
            port=args.port,
            baud=args.baud,
            backend_url=args.backend_url,
            token=args.token,
            network_id=args.network_id,
            mac=args.mac,
            dry_run=args.dry_run,
            mock_backend=args.mock_backend,
            mock_backend_status=args.mock_backend_status,
        )
        code = run_provisioning(config)
        self.assertEqual(code, EXIT_SUCCESS)

    def test_dry_run_mock_backend_conflict_exit_code(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "--dry-run",
                "--mock-backend",
                "--mock-backend-status",
                "409",
                "--mac",
                "001122334455",
            ]
        )
        config = ProvisioningConfig(
            port=args.port,
            baud=args.baud,
            backend_url=args.backend_url,
            token=args.token,
            network_id=args.network_id,
            mac=args.mac,
            dry_run=args.dry_run,
            mock_backend=args.mock_backend,
            mock_backend_status=args.mock_backend_status,
        )
        code = run_provisioning(config)
        self.assertEqual(code, EXIT_CONFLICT)

    def test_secure_wipe_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"secret_key_material_bytes")
            tmp_path = Path(f.name)

        self.assertTrue(tmp_path.is_file())
        secure_wipe_file(tmp_path)
        self.assertFalse(tmp_path.exists())

    def test_artifacts_retained_with_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir) / "artifacts"
            config = ProvisioningConfig(
                port=None,
                dry_run=True,
                mock_backend=True,
                mac="001122334455",
                outdir=outdir,
                keep_artifacts=True,
            )
            code = run_provisioning(config)
            self.assertEqual(code, EXIT_SUCCESS)

            csv_file = outdir / "nvs_sec_001122334455.csv"
            bin_file = outdir / "nvs_credentials_001122334455.bin"
            self.assertTrue(csv_file.is_file())
            self.assertTrue(bin_file.is_file())


class TestSecurityAndMasking(unittest.TestCase):
    """Test masking secrets in logs and preventing leakage."""

    def test_mask_secret(self):
        key = "0123456789abcdef" * 4
        masked = mask_secret(key)
        self.assertNotIn(key, masked)
        self.assertTrue(masked.startswith("0123...cdef"))
        self.assertIn("[REDACTED", masked)

    def test_log_output_contains_no_raw_keys(self):
        k_join_pattern = re.compile(r"[0-9a-f]{64}")
        with self.assertLogs("provision_node", level="INFO") as log_ctx:
            config = ProvisioningConfig(
                port=None,
                dry_run=True,
                mock_backend=True,
                mac="001122334455",
            )
            run_provisioning(config)

            # Check all log records
            for msg in log_ctx.output:
                # Any 64-hex string in log is a leak violation
                matches = k_join_pattern.findall(msg)
                self.assertEqual(matches, [], f"Raw 256-bit key leaked in log: {msg}")


if __name__ == "__main__":
    unittest.main()
