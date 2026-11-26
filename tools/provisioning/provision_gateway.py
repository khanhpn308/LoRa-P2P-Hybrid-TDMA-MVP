#!/usr/bin/env python3
"""Factory Flashing & NVS mTLS Certificate Provisioning CLI Tool for ESP32 Gateway.

Automates the provisioning workflow for ESP32-WROOM-32E Gateway Master:
  1. Validates ca.crt, client cert (<gw-id>.crt), and client private key (<gw-id>.key).
  2. Verifies client certificate Subject CN matches --gateway-id (matching Mosquitto ACL
     use_identity_as_username true) and verifies cert/key public-key pair consistency.
  3. Synthesizes an ESP-IDF v6.1 compatible NVS binary partition containing namespace
     'nvs_tls' (gateway_id, ca_cert, client_cert, client_key as null-terminated blobs).
  4. Flashes NVS credentials partition (default 0x9000) and optional gateway_master.bin
     (default 0x10000) via esptool.py.
  5. Enforces security guarantees: memory zeroization, secure temp-file wiping, masked logs,
     0600 file permissions on optional retained NVS binary, and --dry-run CI support.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

try:
    from tools.provisioning.nvs_generator import (
        DEFAULT_PARTITION_SIZE,
        synthesize_gateway_tls_partition,
        validate_gateway_id,
        validate_pem_bytes,
    )
    from tools.provisioning.provision_node import (
        EXIT_ERROR,
        EXIT_SUCCESS,
        ProvisioningError,
        find_esptool_path,
        secure_wipe_file,
        zeroize_memory,
    )
except ImportError:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from tools.provisioning.nvs_generator import (
        DEFAULT_PARTITION_SIZE,
        synthesize_gateway_tls_partition,
        validate_gateway_id,
        validate_pem_bytes,
    )
    from tools.provisioning.provision_node import (
        EXIT_ERROR,
        EXIT_SUCCESS,
        ProvisioningError,
        find_esptool_path,
        secure_wipe_file,
        zeroize_memory,
    )


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("provision_gateway")

CN_EXTRACT_PATTERN = re.compile(r"(?:^|,\s*|\s+)CN\s*=\s*([^\r\n,/]+)")


def parse_hex_int(value: str) -> int:
    """Parse integer from decimal or 0x-prefixed hex string."""
    return int(value, 0)


def extract_cert_common_name(cert_path: Path) -> Optional[str]:
    """Extract X.509 Subject CN using openssl CLI if available."""
    openssl_bin = shutil.which("openssl")
    if not openssl_bin:
        return None

    proc = subprocess.run(
        [openssl_bin, "x509", "-in", str(cert_path), "-noout", "-subject", "-nameopt", "RFC2253"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        raise ProvisioningError(
            f"openssl failed to inspect certificate '{cert_path}': {proc.stderr.strip()}"
        )

    subject_line = proc.stdout.strip()
    if subject_line.startswith("subject="):
        subject_line = subject_line[len("subject=") :].strip()

    match = CN_EXTRACT_PATTERN.search(subject_line)
    if not match:
        raise ProvisioningError(f"Certificate '{cert_path}' has no Subject CN field: {subject_line}")
    return match.group(1).strip()


def verify_cert_and_key_pair(cert_path: Path, key_path: Path) -> None:
    """Verify public key of client certificate matches client private key via openssl."""
    openssl_bin = shutil.which("openssl")
    if not openssl_bin:
        return

    cert_pub = subprocess.run(
        [openssl_bin, "x509", "-in", str(cert_path), "-pubkey", "-noout"],
        capture_output=True,
        timeout=10,
        check=False,
    )
    key_pub = subprocess.run(
        [openssl_bin, "pkey", "-in", str(key_path), "-pubout"],
        capture_output=True,
        timeout=10,
        check=False,
    )
    if cert_pub.returncode != 0 or key_pub.returncode != 0:
        raise ProvisioningError("Failed to extract public key from client certificate or private key")
    if cert_pub.stdout.strip() != key_pub.stdout.strip():
        raise ProvisioningError(
            f"Client private key '{key_path.name}' does not match public key in '{cert_path.name}'"
        )


def verify_cert_signed_by_ca(ca_path: Path, cert_path: Path) -> None:
    """Verify client certificate chains to ca_cert via openssl verify."""
    openssl_bin = shutil.which("openssl")
    if not openssl_bin:
        return

    proc = subprocess.run(
        [openssl_bin, "verify", "-CAfile", str(ca_path), str(cert_path)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        raise ProvisioningError(
            f"Client certificate '{cert_path.name}' failed CA verification against '{ca_path.name}': "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )


def flash_gateway_nvs_esptool(
    esptool_path: str,
    port: str,
    baud: int,
    nvs_offset: int,
    nvs_bin_path: Path,
    firmware_bin_path: Optional[Path] = None,
    firmware_offset: int = 0x10000,
) -> None:
    """Flash NVS mTLS partition (and optional gateway_master.bin) via esptool.py."""
    if not nvs_bin_path.is_file():
        raise ProvisioningError(f"NVS binary not found: {nvs_bin_path}")

    cmd = [
        sys.executable if esptool_path.endswith(".py") else esptool_path,
    ]
    if esptool_path.endswith(".py"):
        cmd.append(esptool_path)
    cmd.extend(
        [
            "--chip",
            "esp32",
            "--port",
            port,
            "--baud",
            str(baud),
            "write_flash",
            hex(nvs_offset),
            str(nvs_bin_path),
        ]
    )

    if firmware_bin_path is not None:
        if not firmware_bin_path.is_file():
            raise ProvisioningError(f"Firmware binary not found: {firmware_bin_path}")
        cmd.extend([hex(firmware_offset), str(firmware_bin_path)])

    logger.info("Executing esptool flash to port %s (NVS offset=0x%x)...", port, nvs_offset)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    if proc.returncode != 0:
        raise ProvisioningError(
            f"esptool write_flash failed (exit {proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )
    logger.info("ESP32 Gateway NVS flash completed and verified.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision ESP32 Gateway Master mTLS credentials into ESP-IDF v6.1 NVS flash.",
    )
    parser.add_argument(
        "--gateway-id",
        default="gw-a",
        help="Canonical Gateway ID matching CONFIG_GATEWAY_ID and client cert CN (default: gw-a).",
    )
    parser.add_argument("--ca-cert", required=True, type=Path, help="Path to Broker CA certificate PEM (ca.crt).")
    parser.add_argument(
        "--client-cert",
        required=True,
        type=Path,
        help="Path to Gateway client certificate PEM (e.g. gw-a.crt).",
    )
    parser.add_argument(
        "--client-key",
        required=True,
        type=Path,
        help="Path to Gateway client private key PEM (e.g. gw-a.key).",
    )
    parser.add_argument("--port", default=None, help="ESP32 serial port (e.g. /dev/ttyUSB0).")
    parser.add_argument("--baud", type=int, default=460800, help="Serial baud rate (default: 460800).")
    parser.add_argument(
        "--nvs-offset",
        type=parse_hex_int,
        default=0x9000,
        help="Flash offset of NVS partition (default: 0x9000).",
    )
    parser.add_argument(
        "--partition-size",
        type=parse_hex_int,
        default=DEFAULT_PARTITION_SIZE,
        help="NVS partition size in bytes (default: 0x6000).",
    )
    parser.add_argument(
        "--firmware-bin",
        type=Path,
        default=None,
        help="Optional path to gateway_master.bin to flash alongside NVS.",
    )
    parser.add_argument(
        "--firmware-offset",
        type=parse_hex_int,
        default=0x10000,
        help="Flash offset of gateway_master.bin (default: 0x10000).",
    )
    parser.add_argument(
        "--output-bin",
        type=Path,
        default=None,
        help="Optional output path to retain synthesized NVS .bin (chmod 0600; NEVER commit to Git).",
    )
    parser.add_argument(
        "--use-idf-tool",
        action="store_true",
        help="Prefer ESP-IDF nvs_partition_gen.py when available instead of built-in writer.",
    )
    parser.add_argument(
        "--skip-cn-check",
        action="store_true",
        help="Skip OpenSSL CN and CA chain checks (not recommended outside synthetic unit tests).",
    )
    parser.add_argument("--esptool-path", default=None, help="Custom path to esptool.py.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate certificates and synthesize NVS partition without flashing hardware.",
    )
    return parser


def run_provisioning(args: argparse.Namespace) -> int:
    gateway_id = validate_gateway_id(args.gateway_id)

    for label, path in (
        ("CA cert", args.ca_cert),
        ("Client cert", args.client_cert),
        ("Client key", args.client_key),
    ):
        if not path.is_file():
            raise ProvisioningError(f"{label} file not found: {path}")

    if not args.dry_run and not args.output_bin and not args.port:
        raise ProvisioningError("Either --port, --output-bin, or --dry-run must be specified")

    ca_bytes = validate_pem_bytes(args.ca_cert.read_bytes(), "ca_cert", is_private_key=False)
    cert_bytes = validate_pem_bytes(args.client_cert.read_bytes(), "client_cert", is_private_key=False)
    key_buf = bytearray(validate_pem_bytes(args.client_key.read_bytes(), "client_key", is_private_key=True))

    tmp_dir_obj: Optional[tempfile.TemporaryDirectory[str]] = None
    temp_bin_path: Optional[Path] = None

    try:
        if not args.skip_cn_check:
            cn = extract_cert_common_name(args.client_cert)
            if cn is not None and cn != gateway_id:
                raise ProvisioningError(
                    f"Certificate CN '{cn}' does not match --gateway-id '{gateway_id}' "
                    f"(required by deploy/mosquitto/tls.conf use_identity_as_username)"
                )
            verify_cert_and_key_pair(args.client_cert, args.client_key)
            verify_cert_signed_by_ca(args.ca_cert, args.client_cert)

        ca_sha = hashlib.sha256(ca_bytes).hexdigest()[:16]
        cert_sha = hashlib.sha256(cert_bytes).hexdigest()[:16]
        logger.info(
            "Validated mTLS bundle for gateway_id='%s' (ca_sha256=%s..., client_cert_sha256=%s..., key_len=%dB [REDACTED])",
            gateway_id,
            ca_sha,
            cert_sha,
            len(key_buf),
        )

        if args.output_bin is not None:
            target_bin = args.output_bin
        else:
            tmp_dir_obj = tempfile.TemporaryDirectory(prefix="gw_nvs_tls_")
            temp_bin_path = Path(tmp_dir_obj.name) / f"nvs_tls_{gateway_id}.bin"
            target_bin = temp_bin_path

        bin_data = synthesize_gateway_tls_partition(
            gateway_id=gateway_id,
            ca_cert_pem=ca_bytes,
            client_cert_pem=cert_bytes,
            client_key_pem=key_buf,
            partition_size=args.partition_size,
            output_bin=target_bin,
            use_external_tool=args.use_idf_tool,
        )
        logger.info(
            "Synthesized NVS partition 'nvs_tls' (%d bytes, offset=0x%x)",
            len(bin_data),
            args.nvs_offset,
        )

        if args.dry_run:
            logger.info(
                "[DRY-RUN] Skipping esptool flash (would flash %d bytes to offset 0x%x%s)",
                len(bin_data),
                args.nvs_offset,
                f" and {args.firmware_bin} to 0x{args.firmware_offset:x}" if args.firmware_bin else "",
            )
            return EXIT_SUCCESS

        if args.port:
            esptool_bin = find_esptool_path(args.esptool_path)
            flash_gateway_nvs_esptool(
                esptool_path=esptool_bin,
                port=args.port,
                baud=args.baud,
                nvs_offset=args.nvs_offset,
                nvs_bin_path=target_bin,
                firmware_bin_path=args.firmware_bin,
                firmware_offset=args.firmware_offset,
            )

        if args.output_bin is not None:
            os.chmod(args.output_bin, 0o600)
            logger.warning(
                "Retained NVS binary at %s (chmod 0600, contains private key — NEVER commit to Git)",
                args.output_bin,
            )

        return EXIT_SUCCESS

    finally:
        zeroize_memory(key_buf)
        if temp_bin_path is not None and temp_bin_path.exists():
            secure_wipe_file(temp_bin_path)
        if tmp_dir_obj is not None:
            tmp_dir_obj.cleanup()


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_provisioning(args)
    except (ProvisioningError, ValueError, OSError) as exc:
        logger.error("Gateway mTLS provisioning failed: %s", exc)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
