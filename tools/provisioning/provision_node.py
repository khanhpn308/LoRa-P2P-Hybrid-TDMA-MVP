#!/usr/bin/env python3
"""Factory Flashing & NVS K_JOIN Provisioning CLI Tool for Sensor Nodes.

Automates the provisioning workflow for ESP32 Sensor Nodes:
  1. Generates 256-bit CSPRNG root key K_JOIN and acquires unique device MAC.
  2. Registers device identity and K_JOIN with Backend via POST /api/v1/devices/provision.
  3. Synthesizes an ESP-IDF v6.1 compatible NVS credentials binary partition.
  4. Flashes NVS credentials partition and optional firmware binary via esptool.py.
  5. Enforces security guarantees: memory zeroization, secure disk erasure, masked logs.
  6. Supports full --dry-run mode for offline CI and verification without USB hardware.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Optional
import urllib.error
import urllib.request

try:
    from tools.provisioning.nvs_generator import (
        DEFAULT_PARTITION_SIZE,
        generate_nvs_csv,
        synthesize_nvs_partition,
        validate_key,
        validate_mac,
    )
except ImportError:
    # Handle direct script invocation from outside module root
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from tools.provisioning.nvs_generator import (
        DEFAULT_PARTITION_SIZE,
        generate_nvs_csv,
        synthesize_nvs_partition,
        validate_key,
        validate_mac,
    )


# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("provision_node")


EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_CONFLICT = 2


class ProvisioningError(Exception):
    """Base exception for provisioning failures."""


class DeviceAlreadyProvisionedError(ProvisioningError):
    """Raised when Backend returns 409 Conflict."""


def mask_secret(secret_hex: str) -> str:
    """Mask key material for safe logging without secret leakage."""
    if not secret_hex or len(secret_hex) < 8:
        return "[REDACTED]"
    return f"{secret_hex[:4]}...{secret_hex[-4:]} [REDACTED 256-bit Key]"


def zeroize_memory(buf: bytearray | memoryview) -> None:
    """Securely overwrite in-memory buffer with zeroes."""
    if isinstance(buf, (bytearray, memoryview)):
        for i in range(len(buf)):
            buf[i] = 0


def secure_wipe_file(file_path: Path) -> None:
    """Securely overwrite file data with zeroes before deletion."""
    try:
        if file_path.is_file():
            size = file_path.stat().st_size
            with open(file_path, "wb") as f:
                f.write(b"\x00" * size)
                f.flush()
                os.fsync(f.fileno())
            file_path.unlink()
    except OSError as exc:
        logger.warning("Failed secure wipe of file %s: %s", file_path, exc)


def generate_csprng_key_bytes() -> bytearray:
    """Generate cryptographically secure 256-bit random key in mutable bytearray."""
    return bytearray(secrets.token_bytes(32))


def generate_synthetic_mac() -> str:
    """Generate a locally administered, unicast 6-byte MAC address for testing/dry-run."""
    # Byte 0 has bit 1 set (locally administered) and bit 0 cleared (unicast) => 0x02
    random_tail = secrets.token_bytes(5)
    return "02" + random_tail.hex()


def parse_mac_from_esptool_output(output: str) -> str:
    """Extract 12-hex MAC address from esptool read_mac output."""
    match = re.search(r"MAC:\s*([0-9a-fA-F: -]{12,17})", output)
    if not match:
        raise ProvisioningError(f"Could not parse chip MAC address from esptool output:\n{output}")
    raw_mac = match.group(1).replace(":", "").replace("-", "").replace(" ", "").strip().lower()
    return validate_mac(raw_mac)


def find_esptool_path(custom_path: Optional[str] = None) -> str:
    """Locate esptool.py executable in system or virtualenvs."""
    if custom_path:
        if Path(custom_path).is_file():
            return custom_path
        which = shutil.which(custom_path)
        if which:
            return which
        raise ProvisioningError(f"Specified esptool not found: {custom_path}")

    # Check PATH
    for name in ("esptool.py", "esptool"):
        which = shutil.which(name)
        if which:
            return which

    # Check IDF_PATH
    idf_path = os.environ.get("IDF_PATH")
    if idf_path:
        candidate = Path(idf_path) / "components" / "esptool_py" / "esptool" / "esptool.py"
        if candidate.is_file():
            return str(candidate)

    # Check common ~/.espressif python envs
    home_espressif = Path.home() / ".espressif" / "python_env"
    if home_espressif.is_dir():
        for env_dir in home_espressif.iterdir():
            candidate = env_dir / "bin" / "esptool.py"
            if candidate.is_file():
                return str(candidate)

    raise ProvisioningError("esptool.py not found in PATH or ~/.espressif virtualenvs")


def register_device_with_backend(
    backend_url: str,
    network_id: int,
    device_mac: str,
    k_join_hex: str,
    generation: int = 1,
    initial_join_counter: int = 0,
    token: Optional[str] = None,
    max_retries: int = 3,
    timeout: float = 10.0,
    mock_mode: bool = False,
    mock_status: int = 201,
) -> dict[str, Any]:
    """Register device identity and wrapped root key with Backend.

    Performs HTTP POST /api/v1/devices/provision with exponential backoff retries.
    Fail-closed on 409 Conflict to prevent orphan hardware keys.
    """
    clean_mac = validate_mac(device_mac)
    clean_k_join = validate_key(k_join_hex, "k_join")

    if mock_mode:
        logger.info("[MOCK BACKEND] Simulating registration for MAC=%s with status=%d", clean_mac, mock_status)
        if mock_status == 201:
            return {
                "device_mac": clean_mac,
                "network_id": network_id,
                "generation": generation,
                "status": "ACTIVE",
                "created_at": "2026-11-08T00:00:00Z",
            }
        elif mock_status == 409:
            raise DeviceAlreadyProvisionedError(
                f"Device MAC {clean_mac} is already provisioned in Backend (HTTP 409 Conflict)."
            )
        else:
            raise ProvisioningError(f"Mock Backend error: HTTP {mock_status}")

    endpoint = f"{backend_url.rstrip('/')}/api/v1/devices/provision"
    payload = {
        "network_id": network_id,
        "device_mac": clean_mac,
        "k_join": clean_k_join,
        "generation": generation,
        "initial_join_counter": initial_join_counter,
    }
    payload_bytes = json.dumps(payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"

    logger.info("Registering device MAC=%s with Backend at %s", clean_mac, endpoint)

    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(endpoint, data=payload_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_bytes = resp.read()
                data = json.loads(resp_bytes.decode("utf-8"))
                logger.info(
                    "Backend registered device successfully: MAC=%s network_id=%d generation=%d status=%s",
                    data.get("device_mac", clean_mac),
                    data.get("network_id", network_id),
                    data.get("generation", generation),
                    data.get("status", "ACTIVE"),
                )
                return data

        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 409:
                logger.error(
                    "Backend rejected registration: Device MAC %s already provisioned (HTTP 409 Conflict). Aborting flash.",
                    clean_mac,
                )
                raise DeviceAlreadyProvisionedError(
                    f"Device MAC {clean_mac} is already provisioned in Backend (HTTP 409 Conflict): {err_body}"
                ) from exc

            if exc.code in (400, 401, 403):
                logger.error("Backend rejected registration (HTTP %d): %s", exc.code, err_body)
                raise ProvisioningError(
                    f"Backend rejected registration with status {exc.code}: {err_body}"
                ) from exc

            # 5xx server errors can be retried
            logger.warning(
                "Backend HTTP %d error on attempt %d/%d: %s",
                exc.code,
                attempt,
                max_retries,
                err_body,
            )
            last_error = exc

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning(
                "Network connection failure on attempt %d/%d to %s: %s",
                attempt,
                max_retries,
                endpoint,
                exc,
            )
            last_error = exc

        if attempt < max_retries:
            backoff_sec = 0.5 * (2 ** (attempt - 1))
            logger.info("Retrying registration in %.1f seconds...", backoff_sec)
            time.sleep(backoff_sec)

    raise ProvisioningError(f"Backend registration failed after {max_retries} attempts: {last_error}")


@dataclass
class ProvisioningConfig:
    port: Optional[str]
    baud: int = 460800
    backend_url: str = "http://localhost:8080"
    token: Optional[str] = None
    network_id: int = 1
    mac: Optional[str] = None
    firmware_bin: Optional[Path] = None
    firmware_offset: int = 0x10000
    nvs_partition_offset: int = 0x9000
    nvs_partition_size: int = DEFAULT_PARTITION_SIZE
    k_beacon: Optional[str] = None
    generation: int = 1
    initial_join_counter: int = 0
    dry_run: bool = False
    skip_backend: bool = False
    mock_backend: bool = False
    mock_backend_status: int = 201
    outdir: Optional[Path] = None
    keep_artifacts: bool = False
    nvs_gen_tool: Optional[str] = None
    esptool_path: Optional[str] = None


def read_chip_mac(port: str, baud: int, esptool_path: Optional[str] = None) -> str:
    """Read factory eFuse MAC from ESP32 using esptool.py."""
    tool = find_esptool_path(esptool_path)
    py_bin = Path(tool).parent / "python"
    py_exec = str(py_bin) if py_bin.is_file() else sys.executable
    cmd = [py_exec, tool, "--port", port, "--baud", str(baud), "read_mac"]
    logger.info("Reading ESP32 eFuse MAC from port %s via esptool...", port)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    if proc.returncode != 0:
        raise ProvisioningError(
            f"esptool read_mac failed (exit code {proc.returncode}):\n{proc.stderr}\n{proc.stdout}"
        )
    return parse_mac_from_esptool_output(proc.stdout)


def flash_device(
    port: str,
    baud: int,
    nvs_offset: int,
    nvs_bin: Path,
    firmware_offset: Optional[int] = None,
    firmware_bin: Optional[Path] = None,
    esptool_path: Optional[str] = None,
) -> None:
    """Flash credentials NVS partition and optional firmware binary via esptool.py."""
    tool = find_esptool_path(esptool_path)
    py_bin = Path(tool).parent / "python"
    py_exec = str(py_bin) if py_bin.is_file() else sys.executable
    cmd = [
        py_exec,
        tool,
        "--port",
        port,
        "--baud",
        str(baud),
        "write_flash",
        hex(nvs_offset),
        str(nvs_bin),
    ]

    if firmware_bin:
        if not firmware_bin.is_file():
            raise ProvisioningError(f"Firmware binary not found: {firmware_bin}")
        cmd.extend([hex(firmware_offset or 0x10000), str(firmware_bin)])

    logger.info("Executing esptool flashing command: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    if proc.returncode != 0:
        raise ProvisioningError(
            f"esptool write_flash failed (exit code {proc.returncode}):\n{proc.stderr}\n{proc.stdout}"
        )
    logger.info("Flashing completed successfully.")


def run_provisioning(config: ProvisioningConfig) -> int:
    """Execute complete provisioning and flashing lifecycle."""
    temp_dir_obj: Optional[tempfile.TemporaryDirectory] = None
    created_files: list[Path] = []
    k_join_raw: Optional[bytearray] = None
    k_beacon_raw: Optional[bytearray] = None

    try:
        # 1. Acquire Target MAC Address
        if config.mac:
            target_mac = validate_mac(config.mac)
            logger.info("Using user-specified target MAC: %s", target_mac)
        elif config.dry_run:
            target_mac = generate_synthetic_mac()
            logger.info("[DRY-RUN] Generated simulated test MAC: %s", target_mac)
        else:
            if not config.port:
                raise ProvisioningError("Serial --port is required when --mac is omitted in hardware flashing mode.")
            target_mac = read_chip_mac(config.port, config.baud, config.esptool_path)
            logger.info("Successfully read chip eFuse MAC: %s", target_mac)

        # 2. Generate CSPRNG Cryptographic Keys
        k_join_raw = generate_csprng_key_bytes()
        k_join_hex = bytes(k_join_raw).hex()

        if config.k_beacon:
            k_beacon_hex = validate_key(config.k_beacon, "k_beacon")
        else:
            k_beacon_raw = generate_csprng_key_bytes()
            k_beacon_hex = bytes(k_beacon_raw).hex()

        logger.info(
            "Generated CSPRNG root key K_JOIN: %s",
            mask_secret(k_join_hex),
        )
        logger.info(
            "Configured beacon key K_BEACON: %s",
            mask_secret(k_beacon_hex),
        )

        # 3. Register Identity and K_JOIN with Backend
        if not config.skip_backend:
            register_device_with_backend(
                backend_url=config.backend_url,
                network_id=config.network_id,
                device_mac=target_mac,
                k_join_hex=k_join_hex,
                generation=config.generation,
                initial_join_counter=config.initial_join_counter,
                token=config.token,
                mock_mode=config.mock_backend,
                mock_status=config.mock_backend_status,
            )
        else:
            logger.info("[DRY-RUN] Backend registration skipped (--skip-backend).")

        # 4. Prepare Workspace Directory for NVS Synthesis
        if config.outdir:
            work_dir = Path(config.outdir)
            work_dir.mkdir(parents=True, exist_ok=True)
        else:
            temp_dir_obj = tempfile.TemporaryDirectory(prefix="nvs_prov_")
            work_dir = Path(temp_dir_obj.name)

        nvs_csv_path = work_dir / f"nvs_sec_{target_mac}.csv"
        nvs_bin_path = work_dir / f"nvs_credentials_{target_mac}.bin"
        created_files.extend([nvs_csv_path, nvs_bin_path])

        # 5. Synthesize NVS Partition Binary (ESP-IDF v6.1 Format)
        logger.info(
            "Synthesizing NVS partition (size=0x%x) to %s...",
            config.nvs_partition_size,
            nvs_bin_path,
        )
        synthesize_nvs_partition(
            device_mac=target_mac,
            k_join_hex=k_join_hex,
            join_counter=config.initial_join_counter,
            k_beacon_hex=k_beacon_hex,
            partition_size=config.nvs_partition_size,
            output_bin=nvs_bin_path,
            output_csv=nvs_csv_path,
            use_external_tool=bool(config.nvs_gen_tool),
            nvs_tool_path=config.nvs_gen_tool,
        )
        logger.info("NVS credentials binary partition created (%d bytes).", nvs_bin_path.stat().st_size)

        # 6. Flash Device or Simulate Flash
        if config.dry_run:
            logger.info(
                "[DRY-RUN] Flashing simulated: NVS partition (offset=0x%x, size=0x%x)",
                config.nvs_partition_offset,
                config.nvs_partition_size,
            )
            if config.firmware_bin:
                logger.info(
                    "[DRY-RUN] Flashing simulated: Firmware binary %s at offset 0x%x",
                    config.firmware_bin,
                    config.firmware_offset,
                )
            logger.info("[DRY-RUN] Provisioning cycle completed successfully.")
        else:
            if not config.port:
                raise ProvisioningError("Serial --port is required for hardware flashing.")
            flash_device(
                port=config.port,
                baud=config.baud,
                nvs_offset=config.nvs_partition_offset,
                nvs_bin=nvs_bin_path,
                firmware_offset=config.firmware_offset,
                firmware_bin=config.firmware_bin,
                esptool_path=config.esptool_path,
            )
            logger.info("Hardware provisioning and flashing completed successfully for MAC=%s.", target_mac)

        return EXIT_SUCCESS

    except DeviceAlreadyProvisionedError as exc:
        logger.error("PROVISIONING CONFLICT: %s", exc)
        return EXIT_CONFLICT

    except Exception as exc:
        logger.error("PROVISIONING FAILED: %s", exc)
        return EXIT_ERROR

    finally:
        # 7. Secure Memory Zeroization
        if k_join_raw is not None:
            zeroize_memory(k_join_raw)
        if k_beacon_raw is not None:
            zeroize_memory(k_beacon_raw)

        # 8. Secure Disk Cleanup
        if not config.keep_artifacts:
            for file_path in created_files:
                secure_wipe_file(file_path)
            if temp_dir_obj:
                try:
                    temp_dir_obj.cleanup()
                except OSError:
                    pass
        else:
            logger.info("Retaining generated provisioning artifacts in: %s", created_files)


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Factory Flashing & NVS K_JOIN Provisioning CLI Tool for LoRa TDMA Nodes",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Target Hardware Flashing
    parser.add_argument("--port", type=str, default=None, help="Serial port path (e.g. /dev/ttyUSB0 or COM3)")
    parser.add_argument("--baud", type=int, default=460800, help="Serial flashing baud rate")
    parser.add_argument(
        "--mac",
        type=str,
        default=None,
        help="Target 12-hex MAC address (if omitted, read from chip eFuse via esptool)",
    )
    parser.add_argument(
        "--firmware-bin",
        type=Path,
        default=None,
        help="Optional path to compiled sensor_node.bin to flash alongside credentials",
    )
    parser.add_argument(
        "--firmware-offset",
        type=lambda x: int(x, 0),
        default=0x10000,
        help="Flash offset for firmware binary",
    )
    parser.add_argument(
        "--nvs-partition-offset",
        type=lambda x: int(x, 0),
        default=0x9000,
        help="Flash offset for NVS credentials partition",
    )
    parser.add_argument(
        "--nvs-partition-size",
        type=lambda x: int(x, 0),
        default=DEFAULT_PARTITION_SIZE,
        help="Size of NVS credentials partition in bytes (multiple of 4096)",
    )

    # Backend REST API Parameters
    parser.add_argument("--backend-url", type=str, default="http://localhost:8080", help="Backend base URL")
    parser.add_argument(
        "--token",
        "--api-key",
        dest="token",
        type=str,
        default=None,
        help="Bearer token for Backend POST /api/v1/devices/provision",
    )
    parser.add_argument("--network-id", type=int, default=1, help="Target LoRa network identifier")
    parser.add_argument("--generation", type=int, default=1, help="Initial key generation counter")
    parser.add_argument(
        "--initial-join-counter",
        type=int,
        default=0,
        help="Initial monotonic flash join counter (default 0)",
    )
    parser.add_argument(
        "--k-beacon",
        type=str,
        default=None,
        help="Optional 64-hex K_BEACON key (if omitted, generated via CSPRNG)",
    )

    # Mode & Testing Flags
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate generation, registration, and binary synthesis without opening serial port or flashing",
    )
    parser.add_argument(
        "--skip-backend",
        action="store_true",
        help="Skip Backend registration HTTP request (useful for offline generation)",
    )
    parser.add_argument(
        "--mock-backend",
        action="store_true",
        help="Simulate Backend response locally without network calls",
    )
    parser.add_argument(
        "--mock-backend-status",
        type=int,
        default=201,
        help="Simulated HTTP status code when --mock-backend is enabled (e.g. 201 or 409)",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=None,
        help="Directory to save generated CSV and binary partition files",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Do not wipe temporary CSV and binary partition files after completion",
    )
    parser.add_argument(
        "--nvs-gen-tool",
        type=str,
        default=None,
        help="Optional path or command to external nvs_partition_gen.py",
    )
    parser.add_argument(
        "--esptool-path",
        type=str,
        default=None,
        help="Optional path to custom esptool.py executable",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = ProvisioningConfig(
        port=args.port,
        baud=args.baud,
        backend_url=args.backend_url,
        token=args.token,
        network_id=args.network_id,
        mac=args.mac,
        firmware_bin=args.firmware_bin,
        firmware_offset=args.firmware_offset,
        nvs_partition_offset=args.nvs_partition_offset,
        nvs_partition_size=args.nvs_partition_size,
        k_beacon=args.k_beacon,
        generation=args.generation,
        initial_join_counter=args.initial_join_counter,
        dry_run=args.dry_run,
        skip_backend=args.skip_backend,
        mock_backend=args.mock_backend,
        mock_backend_status=args.mock_backend_status,
        outdir=args.outdir,
        keep_artifacts=args.keep_artifacts,
        nvs_gen_tool=args.nvs_gen_tool,
        esptool_path=args.esptool_path,
    )

    return run_provisioning(config)


if __name__ == "__main__":
    sys.exit(main())
