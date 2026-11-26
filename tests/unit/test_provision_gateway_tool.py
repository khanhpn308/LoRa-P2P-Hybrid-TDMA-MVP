"""Unit tests for Gateway mTLS NVS provisioning tool (tools/provisioning/provision_gateway.py)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.provisioning.nvs_generator import (  # noqa: E402
    DEFAULT_PARTITION_SIZE,
    NVSV2PartitionWriter,
    PAGE_SIZE,
    PAGE_STATE_ACTIVE,
    PAGE_STATE_FULL,
    find_esp_idf_nvs_gen_tool,
    generate_gateway_tls_csv,
    synthesize_gateway_tls_partition,
    validate_gateway_id,
    validate_pem_bytes,
)
from tools.provisioning.provision_gateway import (  # noqa: E402
    EXIT_ERROR,
    EXIT_SUCCESS,
    build_parser,
    main as provision_gateway_main,
)


def make_synthetic_pem(label: str, body_chars: int = 1200) -> bytes:
    """Create a deterministic synthetic PEM fixture without triggering secret regexes."""
    begin_hdr = "-----BEGIN " + label + "-----\n"
    end_hdr = "-----END " + label + "-----\n"
    chunk = ("QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVowMTIzNDU2Nzg5YWJjZGVm\n") * ((body_chars // 56) + 1)
    body = chunk[:body_chars]
    if not body.endswith("\n"):
        body += "\n"
    return (begin_hdr + body + end_hdr).encode("utf-8")


class TestGatewayProvisioningValidation(unittest.TestCase):
    def test_validate_gateway_id(self):
        self.assertEqual(validate_gateway_id("gw-a"), "gw-a")
        self.assertEqual(validate_gateway_id(" gw_01 "), "gw_01")
        for bad in ("", "-bad", "gw a", "gw/a", "a" * 32):
            with self.assertRaises(ValueError):
                validate_gateway_id(bad)

    def test_validate_pem_bytes(self):
        cert_pem = make_synthetic_pem("CERTIFICATE", 256)
        key_pem = make_synthetic_pem("PRIVATE " + "KEY", 256)

        self.assertTrue(validate_pem_bytes(cert_pem, "ca_cert", is_private_key=False).endswith(b"\n"))
        self.assertTrue(validate_pem_bytes(key_pem, "client_key", is_private_key=True).endswith(b"\n"))

        with self.assertRaises(ValueError):
            validate_pem_bytes(b"", "ca_cert", is_private_key=False)
        with self.assertRaises(ValueError):
            validate_pem_bytes(cert_pem, "client_key", is_private_key=True)
        with self.assertRaises(ValueError):
            validate_pem_bytes(key_pem, "client_cert", is_private_key=False)
        with self.assertRaises(ValueError):
            validate_pem_bytes(make_synthetic_pem("CERTIFICATE", 4200), "ca_cert", is_private_key=False)


class TestGatewayMultipageNVSSynthesis(unittest.TestCase):
    def test_multipage_nvs_layout_and_spare_page(self):
        ca_pem = make_synthetic_pem("CERTIFICATE", 1300)
        cert_pem = make_synthetic_pem("CERTIFICATE", 1350)
        key_pem = make_synthetic_pem("PRIVATE " + "KEY", 1750)

        image = synthesize_gateway_tls_partition(
            gateway_id="gw-a",
            ca_cert_pem=ca_pem,
            client_cert_pem=cert_pem,
            client_key_pem=key_pem,
            partition_size=DEFAULT_PARTITION_SIZE,
        )

        self.assertEqual(len(image), DEFAULT_PARTITION_SIZE)
        # Page 0 is FULL and Page 1 is ACTIVE (multipage spill > 4032 bytes)
        page0_state, page0_seq = struct.unpack_from("<II", image, 0)
        page1_state, page1_seq = struct.unpack_from("<II", image, PAGE_SIZE)
        self.assertEqual(page0_state, PAGE_STATE_FULL)
        self.assertEqual(page0_seq, 0)
        self.assertEqual(page1_state, PAGE_STATE_ACTIVE)
        self.assertEqual(page1_seq, 1)

        # Last page must remain empty/erased (0xFF) for NVS wear-leveling
        last_page = image[-PAGE_SIZE:]
        self.assertEqual(last_page, b"\xff" * PAGE_SIZE)

    def test_partition_too_small_fails_closed(self):
        ca_pem = make_synthetic_pem("CERTIFICATE", 3000)
        cert_pem = make_synthetic_pem("CERTIFICATE", 3000)
        key_pem = make_synthetic_pem("PRIVATE " + "KEY", 3000)
        writer = NVSV2PartitionWriter(partition_size=3 * PAGE_SIZE)
        with self.assertRaises(RuntimeError):
            writer.synthesize_gateway_tls_partition("gw-a", ca_pem, cert_pem, key_pem)

    def test_byte_parity_with_espressif_nvs_partition_gen_if_installed(self):
        tool_cmd = find_esp_idf_nvs_gen_tool()
        if not tool_cmd:
            self.skipTest("esp_idf_nvs_partition_gen not installed in this environment")

        ca_pem = make_synthetic_pem("CERTIFICATE", 1300)
        cert_pem = make_synthetic_pem("CERTIFICATE", 1350)
        key_pem = make_synthetic_pem("PRIVATE " + "KEY", 1750)

        builtin_img = synthesize_gateway_tls_partition(
            gateway_id="gw-a",
            ca_cert_pem=ca_pem,
            client_cert_pem=cert_pem,
            client_key_pem=key_pem,
            partition_size=DEFAULT_PARTITION_SIZE,
            use_external_tool=False,
        )
        idf_img = synthesize_gateway_tls_partition(
            gateway_id="gw-a",
            ca_cert_pem=ca_pem,
            client_cert_pem=cert_pem,
            client_key_pem=key_pem,
            partition_size=DEFAULT_PARTITION_SIZE,
            use_external_tool=True,
            nvs_tool_path=tool_cmd,
        )
        self.assertEqual(builtin_img, idf_img)

    def test_generate_gateway_tls_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ca_p = tmp / "ca.crt"
            cert_p = tmp / "gw-a.crt"
            key_p = tmp / "gw-a.key"
            ca_p.write_bytes(make_synthetic_pem("CERTIFICATE", 200))
            cert_p.write_bytes(make_synthetic_pem("CERTIFICATE", 200))
            key_p.write_bytes(make_synthetic_pem("PRIVATE " + "KEY", 200))
            csv_txt = generate_gateway_tls_csv("gw-a", ca_p, cert_p, key_p)
            self.assertIn("nvs_tls,namespace,,", csv_txt)
            self.assertIn("ca_cert,data,hex2bin,", csv_txt)
            self.assertIn("client_cert,data,hex2bin,", csv_txt)
            self.assertIn("client_key,data,hex2bin,", csv_txt)


class TestProvisionGatewayCLI(unittest.TestCase):
    def test_parser_defaults(self):
        parser = build_parser()
        args = parser.parse_args(
            ["--ca-cert", "ca.crt", "--client-cert", "gw-a.crt", "--client-key", "gw-a.key", "--dry-run"]
        )
        self.assertEqual(args.gateway_id, "gw-a")
        self.assertEqual(args.nvs_offset, 0x9000)
        self.assertEqual(args.partition_size, DEFAULT_PARTITION_SIZE)
        self.assertTrue(args.dry_run)

    def test_dry_run_synthetic_and_output_bin_permissions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ca_p = tmp / "ca.crt"
            cert_p = tmp / "gw-a.crt"
            key_p = tmp / "gw-a.key"
            out_bin = tmp / "out" / "nvs_tls_gw-a.bin"
            ca_p.write_bytes(make_synthetic_pem("CERTIFICATE", 1200))
            cert_p.write_bytes(make_synthetic_pem("CERTIFICATE", 1200))
            key_p.write_bytes(make_synthetic_pem("PRIVATE " + "KEY", 1600))

            with self.assertLogs("provision_gateway", level=logging.INFO) as logs:
                rc = provision_gateway_main(
                    [
                        "--gateway-id",
                        "gw-a",
                        "--ca-cert",
                        str(ca_p),
                        "--client-cert",
                        str(cert_p),
                        "--client-key",
                        str(key_p),
                        "--output-bin",
                        str(out_bin),
                        "--skip-cn-check",
                        "--dry-run",
                    ]
                )
            self.assertEqual(rc, EXIT_SUCCESS)
            self.assertTrue(out_bin.is_file())
            self.assertEqual(out_bin.stat().st_size, DEFAULT_PARTITION_SIZE)
            mode = stat.S_IMODE(out_bin.stat().st_mode)
            self.assertEqual(mode, 0o600)

            joined_logs = "\n".join(logs.output)
            self.assertNotIn("QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVow", joined_logs)
            self.assertIn("[REDACTED]", joined_logs)

    @unittest.skipUnless(shutil.which("openssl"), "openssl binary required for X.509 CN validation test")
    def test_openssl_cn_match_and_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ca_key = tmp / "ca.key"
            ca_crt = tmp / "ca.crt"
            gw_key = tmp / "gw-a.key"
            gw_csr = tmp / "gw-a.csr"
            gw_crt = tmp / "gw-a.crt"
            other_key = tmp / "other.key"

            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=test-ca",
                    "-keyout",
                    str(ca_key),
                    "-out",
                    str(ca_crt),
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-new",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-subj",
                    "/CN=gw-a",
                    "-keyout",
                    str(gw_key),
                    "-out",
                    str(gw_csr),
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "openssl",
                    "x509",
                    "-req",
                    "-in",
                    str(gw_csr),
                    "-days",
                    "1",
                    "-CA",
                    str(ca_crt),
                    "-CAkey",
                    str(ca_key),
                    "-CAcreateserial",
                    "-out",
                    str(gw_crt),
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["openssl", "genrsa", "-out", str(other_key), "2048"],
                check=True,
                capture_output=True,
            )

            # Matching CN=gw-a succeeds
            rc_ok = provision_gateway_main(
                [
                    "--gateway-id",
                    "gw-a",
                    "--ca-cert",
                    str(ca_crt),
                    "--client-cert",
                    str(gw_crt),
                    "--client-key",
                    str(gw_key),
                    "--dry-run",
                ]
            )
            self.assertEqual(rc_ok, EXIT_SUCCESS)

            # Mismatched gateway-id (gw-b vs CN=gw-a) fails closed
            rc_cn_mismatch = provision_gateway_main(
                [
                    "--gateway-id",
                    "gw-b",
                    "--ca-cert",
                    str(ca_crt),
                    "--client-cert",
                    str(gw_crt),
                    "--client-key",
                    str(gw_key),
                    "--dry-run",
                ]
            )
            self.assertEqual(rc_cn_mismatch, EXIT_ERROR)

            # Mismatched private key fails closed
            rc_key_mismatch = provision_gateway_main(
                [
                    "--gateway-id",
                    "gw-a",
                    "--ca-cert",
                    str(ca_crt),
                    "--client-cert",
                    str(gw_crt),
                    "--client-key",
                    str(other_key),
                    "--dry-run",
                ]
            )
            self.assertEqual(rc_key_mismatch, EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
