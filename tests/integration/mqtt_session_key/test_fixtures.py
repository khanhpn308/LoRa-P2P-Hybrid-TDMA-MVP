"""Test fixtures, ephemeral PKI generator, and test vectors for MQTT Session Key.
Authority: Issue #174, #122 / PR #123, contracts/mqtt/session-key-security.md.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Dict, Any, Tuple


# Baseline #16 ACL from deploy/mosquitto/acl
BASELINE_ACL = """# Local sample identities, certificate CNs, not client-supplied MQTT ClientIDs.
# Issue #14 draft topic mapping. Add a reviewed user block for each Gateway.
user gw-a
topic write iot/v1/gw/gw-a/uplink/telemetry
topic write iot/v1/gw/gw-a/uplink/alert
topic write iot/v1/gw/gw-a/uplink/status
topic write iot/v1/gw/gw-a/uplink/schedule-ack
topic write iot/v1/gw/gw-a/uplink/command-ack
topic read iot/v1/gw/gw-a/downlink/schedule
topic read iot/v1/gw/gw-a/downlink/command

user gw-b
topic write iot/v1/gw/gw-b/uplink/telemetry
topic write iot/v1/gw/gw-b/uplink/alert
topic write iot/v1/gw/gw-b/uplink/status
topic write iot/v1/gw/gw-b/uplink/schedule-ack
topic write iot/v1/gw/gw-b/uplink/command-ack
topic read iot/v1/gw/gw-b/downlink/schedule
topic read iot/v1/gw/gw-b/downlink/command

user backend
topic read iot/v1/gw/+/uplink/telemetry
topic read iot/v1/gw/+/uplink/alert
topic read iot/v1/gw/+/uplink/status
topic read iot/v1/gw/+/uplink/schedule-ack
topic read iot/v1/gw/+/uplink/command-ack
topic write iot/v1/gw/+/downlink/schedule
topic write iot/v1/gw/+/downlink/command
"""

# Reviewed ACL extending #16 with Session Key topics from #122 / PR #123
SESSION_KEY_ACL = """# Reviewed Mosquitto ACL with Session Key topics (PR #123 / Issue #174)
user gw-a
topic write iot/v1/gw/gw-a/uplink/telemetry
topic write iot/v1/gw/gw-a/uplink/alert
topic write iot/v1/gw/gw-a/uplink/status
topic write iot/v1/gw/gw-a/uplink/schedule-ack
topic write iot/v1/gw/gw-a/uplink/command-ack
topic read iot/v1/gw/gw-a/downlink/schedule
topic read iot/v1/gw/gw-a/downlink/command
topic read iot/v1/gw/gw-a/downlink/session-key-install
topic write iot/v1/gw/gw-a/uplink/session-key-ack

user gw-b
topic write iot/v1/gw/gw-b/uplink/telemetry
topic write iot/v1/gw/gw-b/uplink/alert
topic write iot/v1/gw/gw-b/uplink/status
topic write iot/v1/gw/gw-b/uplink/schedule-ack
topic write iot/v1/gw/gw-b/uplink/command-ack
topic read iot/v1/gw/gw-b/downlink/schedule
topic read iot/v1/gw/gw-b/downlink/command
topic read iot/v1/gw/gw-b/downlink/session-key-install
topic write iot/v1/gw/gw-b/uplink/session-key-ack

user backend
topic read iot/v1/gw/+/uplink/telemetry
topic read iot/v1/gw/+/uplink/alert
topic read iot/v1/gw/+/uplink/status
topic read iot/v1/gw/+/uplink/schedule-ack
topic read iot/v1/gw/+/uplink/command-ack
topic write iot/v1/gw/+/downlink/schedule
topic write iot/v1/gw/+/downlink/command
topic write iot/v1/gw/+/downlink/session-key-install
topic read iot/v1/gw/+/uplink/session-key-ack
"""


def generate_ephemeral_pki(cert_dir: Path, broker_dir: Path) -> None:
    """Generate isolated ephemeral CA and client/server certificates."""
    cert_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    broker_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
    ca_dir = cert_dir / "ca"
    ca_dir.mkdir(exist_ok=True, mode=0o700)

    def run_openssl(*args: str) -> None:
        subprocess.run(["openssl", *args], check=True, capture_output=True, timeout=30)

    # 1. Ephemeral CA
    run_openssl(
        "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-subj", "/CN=issue174-test-ca",
        "-keyout", str(ca_dir / "ca.key"),
        "-out", str(cert_dir / "ca.crt"),
    )

    # 2. Server and Client certificates
    identities = ["server", "gw-a", "gw-b", "backend", "unknown"]
    for name in identities:
        run_openssl(
            "req", "-new", "-newkey", "rsa:2048", "-nodes",
            "-subj", f"/CN={name}",
            "-keyout", str(cert_dir / f"{name}.key"),
            "-out", str(ca_dir / f"{name}.csr"),
        )
        ext_file = ca_dir / f"{name}.cnf"
        if name == "server":
            ext_content = (
                "basicConstraints=CA:FALSE\n"
                "extendedKeyUsage=serverAuth\n"
                "subjectAltName=DNS:mqtt-tls,DNS:localhost,IP:127.0.0.1\n"
            )
        else:
            ext_content = "basicConstraints=CA:FALSE\nextendedKeyUsage=clientAuth\n"
        ext_file.write_text(ext_content, encoding="utf-8")

        run_openssl(
            "x509", "-req",
            "-in", str(ca_dir / f"{name}.csr"),
            "-CA", str(cert_dir / "ca.crt"),
            "-CAkey", str(ca_dir / "ca.key"),
            "-CAcreateserial", "-days", "1",
            "-extfile", str(ext_file),
            "-out", str(cert_dir / f"{name}.crt"),
        )

    # 3. Untrusted self-signed certificate (CN=wrong)
    run_openssl(
        "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-subj", "/CN=gw-a",
        "-keyout", str(cert_dir / "wrong.key"),
        "-out", str(cert_dir / "wrong.crt"),
    )

    # Set strict permissions
    for p in cert_dir.iterdir():
        if p.is_file():
            p.chmod(0o600)

    # Copy broker files
    for name in ("ca.crt", "server.crt", "server.key"):
        shutil.copyfile(cert_dir / name, broker_dir / name)
        (broker_dir / name).chmod(0o640)

    # Chgrp broker directory to 1883 (Mosquitto user in container)
    subprocess.run(
        [
            "docker", "run", "--rm", "--user", "0:0", "--entrypoint", "chgrp",
            "--mount", f"type=bind,src={broker_dir},dst=/broker",
            "eclipse-mosquitto:2.0", "-R", "1883", "/broker"
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )


def create_sample_session_key_install_payload(
    gateway_id: str = "gw-a",
    target_gw_id: int = 1,
    session_revision: str = "7",
    deadline_offset_sec: int = 300,
) -> Dict[str, Any]:
    """Create a syntactically valid session-key-install JSON payload."""
    now = datetime.now(timezone.utc)
    not_before = (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    expires_at = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    deadline = (now + timedelta(seconds=deadline_offset_sec)).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "schema_version": "1.1-draft",
        "install_protocol_version": 1,
        "aad_version": 1,
        "gateway_id": gateway_id,
        "target_gw_id": target_gw_id,
        "device_mac": "246f28123456",
        "node_id": 14,
        "key_id": 1,
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
        "install_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "session_revision": session_revision,
        "assignment_revision": "3",
        "session_context_hash": "a" * 64,
        "not_before": not_before,
        "expires_at": expires_at,
        "install_deadline": deadline,
        "wrap_key_id": 1,
        "crypto_suite": "AES-256-GCM",
        "nonce": base64.b64encode(b"\x01" * 12).decode("ascii"),
        "ciphertext": base64.b64encode(b"\x02" * 64).decode("ascii"),
        "tag": base64.b64encode(b"\x03" * 16).decode("ascii"),
    }


def create_sample_session_key_ack_payload(
    gateway_id: str = "gw-a",
    status: str = "INSTALLED",
    reason_code: str = "NONE",
    session_revision: str = "7",
    wrap_key_id: int = 1,
) -> Dict[str, Any]:
    """Create a syntactically valid session-key-ack JSON payload."""
    return {
        "schema_version": "1.1-draft",
        "ack_protocol_version": 1,
        "gateway_id": gateway_id,
        "install_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
        "session_revision": session_revision,
        "wrap_key_id": wrap_key_id,
        "status": status,
        "reason_code": reason_code,
        "ack_tag": base64.b64encode(b"\x04" * 16).decode("ascii"),
    }
