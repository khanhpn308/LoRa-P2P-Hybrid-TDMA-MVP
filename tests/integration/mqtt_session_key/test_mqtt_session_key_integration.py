"""Real Mosquitto mTLS integration test for MQTT Session Key Install/ACK and two-layer identity binding.
Authority: Issue #174, #122 / PR #123, contracts/mqtt/session-key-security.md.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import ssl
import subprocess
import time
import unittest
from typing import Dict, Any, Optional

try:
    from .mqtt5_client import Mqtt5Client
    from .test_fixtures import (
        generate_ephemeral_pki,
        BASELINE_ACL,
        SESSION_KEY_ACL,
        create_sample_session_key_install_payload,
        create_sample_session_key_ack_payload,
    )
    from .semantic_validator import SessionKeySemanticValidator
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from mqtt5_client import Mqtt5Client
    from test_fixtures import (
        generate_ephemeral_pki,
        BASELINE_ACL,
        SESSION_KEY_ACL,
        create_sample_session_key_install_payload,
        create_sample_session_key_ack_payload,
    )
    from semantic_validator import SessionKeySemanticValidator


ROOT = Path(__file__).resolve().parents[3]
IMAGE = "eclipse-mosquitto:2.0"


def run_cmd(*args: str, check: bool = True, env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    res = subprocess.run(args, capture_output=True, text=True, timeout=90, env=env)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {' '.join(args)}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
    return res


class TestMqttSessionKeyIntegration(unittest.TestCase):
    """End-to-end integration test against real Mosquitto broker over mTLS."""

    @classmethod
    def setUpClass(cls):
        # 1. Ephemeral directories under ignored tests/integration/secrets/
        cls.secrets_parent = ROOT / "tests/integration/secrets"
        cls.secrets_parent.mkdir(exist_ok=True, mode=0o700)
        # Verify secrets parent is ignored by git
        git_check = run_cmd("git", "-C", str(ROOT), "check-ignore", str(cls.secrets_parent), check=False)
        assert git_check.returncode == 0, "tests/integration/secrets must be gitignored"

        cls.run_id = secrets.token_hex(4)
        cls.work_dir = cls.secrets_parent / f"session-key-{cls.run_id}"
        cls.work_dir.mkdir(mode=0o700)

        cls.cert_dir = cls.work_dir / "certs"
        cls.broker_dir = cls.work_dir / "broker"
        generate_ephemeral_pki(cls.cert_dir, cls.broker_dir)

        # 2. Write test ACL file extending #16 with session key topics
        cls.acl_path = cls.work_dir / "session_key.acl"
        cls.acl_path.write_text(SESSION_KEY_ACL, encoding="utf-8")
        cls.acl_path.chmod(0o600)
        run_cmd(
            "docker", "run", "--rm", "--user", "0:0", "--entrypoint", "chown",
            "--mount", f"type=bind,src={cls.acl_path},dst=/acl",
            IMAGE, "1883:1883", "/acl"
        )

        # 3. Build Compose config reusing deploy/compose.yaml
        cls.project = f"issue174-{cls.run_id}"
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("POSTGRES_", "COMPOSE_", "MQTT_CERT_DIR"))
        }
        env.update({
            "POSTGRES_USER": "testuser",
            "POSTGRES_DB": "testdb",
            "POSTGRES_PASSWORD": secrets.token_hex(16),
            "MQTT_CERT_DIR": str(cls.broker_dir),
        })
        cls.env = env

        base_compose = [
            "docker", "compose", "--env-file", "/dev/null", "-p", cls.project,
            "-f", str(ROOT / "deploy/compose.yaml"), "--profile", "tls"
        ]
        config = json.loads(run_cmd(*base_compose, "config", "--format", "json", env=env).stdout)

        # Ensure random published loopback port and mount our test ACL
        for port in config["services"]["mqtt-tls"].get("ports", []):
            port["host_ip"] = "127.0.0.1"
            port["published"] = "0"

        # Mount test ACL over /mosquitto/config/acl
        config["services"]["mqtt-tls"]["volumes"].append({
            "type": "bind",
            "source": str(cls.acl_path),
            "target": "/mosquitto/config/acl",
            "read_only": True,
        })

        # Remove postgres service from test compose since this issue is broker mTLS/ACL scoped
        config["services"] = {"mqtt-tls": config["services"]["mqtt-tls"]}

        cls.compose_file = cls.work_dir / "compose.json"
        cls.compose_file.write_text(json.dumps(config), encoding="utf-8")
        cls.compose_file.chmod(0o600)

        cls.compose_cmd = ["docker", "compose", "-p", cls.project, "-f", str(cls.compose_file), "--profile", "tls"]

        # Start broker container
        run_cmd(*cls.compose_cmd, "up", "-d", "--build", "--wait", "--wait-timeout", "60", env=env)

        # Resolve published port
        port_out = run_cmd(*cls.compose_cmd, "port", "mqtt-tls", "8883", env=env).stdout.strip()
        cls.broker_port = int(port_out.rsplit(":", 1)[1])
        cls.ca_path = str(cls.cert_dir / "ca.crt")

    @classmethod
    def tearDownClass(cls):
        # Capture logs
        logs = run_cmd(*cls.compose_cmd, "logs", "--no-color", "mqtt-tls", check=False, env=cls.env)
        cls.broker_logs = logs.stdout + logs.stderr

        # Teardown containers and volumes
        run_cmd(*cls.compose_cmd, "down", "-v", "--rmi", "local", "--remove-orphans", check=False, env=cls.env)

        # Remove temporary secrets directory
        if cls.work_dir.exists():
            shutil.rmtree(cls.work_dir, ignore_errors=True)

    def _client(self, identity: Optional[str] = None) -> Mqtt5Client:
        """Create a client with the given test certificate identity."""
        client_cert = str(self.cert_dir / f"{identity}.crt") if identity else None
        client_key = str(self.cert_dir / f"{identity}.key") if identity else None
        return Mqtt5Client(
            host="127.0.0.1",
            port=self.broker_port,
            ca_cert_path=self.ca_path,
            client_cert_path=client_cert,
            client_key_path=client_key,
            server_hostname="localhost",
        )

    # -------------------------------------------------------------------------
    # TEST 1: TLS Mutual Authentication & Handshake Verification
    # -------------------------------------------------------------------------
    def test_01_tls_mutual_authentication_and_rejection(self):
        """Test mTLS handshakes: authorized identities connect, anonymous and untrusted certs are rejected."""
        # Positive connections
        for identity in ("backend", "gw-a", "gw-b"):
            client = self._client(identity)
            client.connect_tls()
            rc = client.connect_mqtt5(client_id=f"test-{identity}-{secrets.token_hex(4)}")
            self.assertEqual(rc, 0, f"Expected CONNACK 0 for {identity}")
            client.disconnect()

        # Negative: anonymous connection (no client cert) rejected by broker
        anon_client = self._client(None)
        with self.assertRaises((ssl.SSLError, ConnectionResetError, BrokenPipeError)):
            try:
                anon_client.connect_tls()
                anon_client.connect_mqtt5(client_id="test-anon")
            finally:
                anon_client.disconnect()

        # Negative: untrusted self-signed certificate (CN=wrong) rejected by broker
        wrong_client = self._client("wrong")
        with self.assertRaises((ssl.SSLError, ConnectionResetError, BrokenPipeError)):
            try:
                wrong_client.connect_tls()
                wrong_client.connect_mqtt5(client_id="test-wrong")
            finally:
                wrong_client.disconnect()

        # Unknown principal (valid CA signature, but CN=unknown not listed in ACL)
        unknown_client = self._client("unknown")
        unknown_client.connect_tls()
        rc = unknown_client.connect_mqtt5(client_id="test-unknown")
        self.assertEqual(rc, 0, "Unknown client can complete TLS connect, but has no ACL grants")
        # Publish to session key topic denied with Reason Code 135 (0x87)
        pub_rc = unknown_client.publish(
            topic="iot/v1/gw/gw-a/downlink/session-key-install",
            payload=b'{"test":1}',
            qos=1,
        )
        self.assertEqual(pub_rc, 135, "Unknown principal must receive PUBACK 135 (Not authorized)")
        unknown_client.disconnect()

    # -------------------------------------------------------------------------
    # TEST 2: Positive Session Key Install and ACK Flow (Real Broker QoS 1)
    # -------------------------------------------------------------------------
    def test_02_positive_session_key_install_and_ack_flow(self):
        """Privileged Backend publishes session-key-install; matching Gateway receives it and replies with ACK."""
        backend = self._client("backend")
        backend.connect_tls()
        self.assertEqual(backend.connect_mqtt5("test-backend"), 0)

        gw_a = self._client("gw-a")
        gw_a.connect_tls()
        self.assertEqual(gw_a.connect_mqtt5("test-gw-a"), 0)

        # 1. Gateway A subscribes to its own downlink install topic
        sub_rc = gw_a.subscribe("iot/v1/gw/gw-a/downlink/session-key-install", qos=1)
        self.assertEqual(sub_rc, 1, "Gateway A granted QoS 1 for its install topic")

        # 2. Backend subscribes to all Gateway uplink ACK topics
        sub_backend_rc = backend.subscribe("iot/v1/gw/+/uplink/session-key-ack", qos=1)
        self.assertEqual(sub_backend_rc, 1, "Backend granted QoS 1 for wildcard uplink ACK topic")

        # 3. Backend publishes valid session-key-install payload
        install_payload = create_sample_session_key_install_payload(gateway_id="gw-a", target_gw_id=1)
        payload_bytes = json.dumps(install_payload).encode("utf-8")

        puback_rc = backend.publish(
            topic="iot/v1/gw/gw-a/downlink/session-key-install",
            payload=payload_bytes,
            qos=1,
            retain=False,
            message_expiry_sec=300,
        )
        self.assertEqual(puback_rc, 0, "Backend received PUBACK 0 for session-key-install")

        # 4. Gateway A receives message
        recv_msg = gw_a.receive_message(timeout=5.0)
        self.assertIsNotNone(recv_msg, "Gateway A should receive the downlink install message")
        self.assertEqual(recv_msg["topic"], "iot/v1/gw/gw-a/downlink/session-key-install")
        self.assertFalse(recv_msg["retain"])
        self.assertEqual(recv_msg["qos"], 1)

        # 5. Gateway A validates payload at application semantic validator (Layer 2)
        gw_validator = SessionKeySemanticValidator(expected_principal="gw-a")
        valid, reason, parsed = gw_validator.validate_install(
            topic=recv_msg["topic"],
            payload_bytes=recv_msg["payload"],
            retained=recv_msg["retain"],
        )
        self.assertTrue(valid, f"Gateway semantic validation failed: {reason}")
        self.assertEqual(reason, "ACCEPT_SESSION_KEY_INSTALL")

        # 6. Gateway A publishes valid session-key-ack
        ack_payload = create_sample_session_key_ack_payload(gateway_id="gw-a", status="INSTALLED", reason_code="NONE")
        ack_bytes = json.dumps(ack_payload).encode("utf-8")

        ack_pub_rc = gw_a.publish(
            topic="iot/v1/gw/gw-a/uplink/session-key-ack",
            payload=ack_bytes,
            qos=1,
            retain=False,
        )
        self.assertEqual(ack_pub_rc, 0, "Gateway A received PUBACK 0 for session-key-ack")

        # 7. Backend receives session-key-ack
        recv_ack = backend.receive_message(timeout=5.0)
        self.assertIsNotNone(recv_ack, "Backend should receive uplink session-key-ack")
        self.assertEqual(recv_ack["topic"], "iot/v1/gw/gw-a/uplink/session-key-ack")

        # 8. Backend validates ACK payload
        backend_validator = SessionKeySemanticValidator()
        ack_valid, ack_reason, _ = backend_validator.validate_ack(
            topic=recv_ack["topic"],
            payload_bytes=recv_ack["payload"],
            retained=recv_ack["retain"],
        )
        self.assertTrue(ack_valid, f"Backend ACK validation failed: {ack_reason}")
        self.assertEqual(ack_reason, "ACCEPT_SESSION_KEY_ACK")

        gw_a.disconnect()
        backend.disconnect()

    # -------------------------------------------------------------------------
    # TEST 3: Negative ACL Denials & Isolation (Cross-Gateway, Wildcards, Roles)
    # -------------------------------------------------------------------------
    def test_03_negative_broker_acl_cross_gateway_denials(self):
        """Test broker ACL enforcement: cross-gateway writes, role reversals, spoofing denied with PUBACK 135."""
        gw_a = self._client("gw-a")
        gw_a.connect_tls()
        gw_a.connect_mqtt5("test-gw-a-neg")

        backend = self._client("backend")
        backend.connect_tls()
        backend.connect_mqtt5("test-backend-neg")

        # Gateway A attempting to write Gateway B's uplink ACK -> PUBACK 135
        rc = gw_a.publish("iot/v1/gw/gw-b/uplink/session-key-ack", b'{"test":1}', qos=1)
        self.assertEqual(rc, 135, "Cross-gateway publish to gw-b must be denied with PUBACK 135")

        # Gateway A attempting to publish to downlink install (role reversal) -> PUBACK 135
        rc = gw_a.publish("iot/v1/gw/gw-a/downlink/session-key-install", b'{"test":1}', qos=1)
        self.assertEqual(rc, 135, "Gateway publishing to downlink must be denied with PUBACK 135")

        # Backend attempting to publish to uplink ACK (role reversal) -> PUBACK 135
        rc = backend.publish("iot/v1/gw/gw-a/uplink/session-key-ack", b'{"test":1}', qos=1)
        self.assertEqual(rc, 135, "Backend publishing to uplink ACK must be denied with PUBACK 135")

        # Gateway A publishing to unlisted topic -> PUBACK 135
        rc = gw_a.publish("iot/v1/gw/gw-a/uplink/unlisted", b'{"test":1}', qos=1)
        self.assertEqual(rc, 135, "Publishing to unlisted topic must be denied with PUBACK 135")

        # ClientID spoofing: connect with gw-a cert, but set client_id="gw-b"
        spoof_client = self._client("gw-a")
        spoof_client.connect_tls()
        spoof_client.connect_mqtt5(client_id="gw-b")
        # Broker uses certificate CN (use_identity_as_username true), so username is gw-a, not gw-b
        rc_spoof = spoof_client.publish("iot/v1/gw/gw-b/uplink/session-key-ack", b'{"test":1}', qos=1)
        self.assertEqual(rc_spoof, 135, "ClientID spoofing cannot bypass certificate CN ACL binding")
        spoof_client.disconnect()

        # Gateway A subscribing to Gateway B downlink: should receive NO messages
        gw_b_sub = self._client("gw-a")
        gw_b_sub.connect_tls()
        gw_b_sub.connect_mqtt5("gw-a-eavesdrop")
        gw_b_sub.subscribe("iot/v1/gw/gw-b/downlink/session-key-install", qos=1)

        # Backend publishes message for Gateway B
        payload_b = json.dumps(create_sample_session_key_install_payload(gateway_id="gw-b", target_gw_id=2)).encode()
        backend.publish("iot/v1/gw/gw-b/downlink/session-key-install", payload_b, qos=1)

        # Gateway A must NOT receive Gateway B's downlink message
        leaked_msg = gw_b_sub.receive_message(timeout=1.5)
        self.assertIsNone(leaked_msg, "Gateway A must not receive Gateway B's session key install message")

        gw_b_sub.disconnect()
        gw_a.disconnect()
        backend.disconnect()

    # -------------------------------------------------------------------------
    # TEST 4: Cross-Layer Identity Binding & Payload Gateway ID Spoofing (Layer 2)
    # -------------------------------------------------------------------------
    def test_04_cross_layer_identity_binding_and_spoofing(self):
        """Identity binding must be enforced at two independent layers: TLS principal/ACL + payload validator."""
        backend = self._client("backend")
        backend.connect_tls()
        backend.connect_mqtt5("test-backend-layer2")

        gw_a = self._client("gw-a")
        gw_a.connect_tls()
        gw_a.connect_mqtt5("test-gw-a-layer2")
        gw_a.subscribe("iot/v1/gw/gw-a/downlink/session-key-install", qos=1)

        # Case 1: Backend publishes to topic 'gw-a', but payload has forged 'gateway_id: gw-b'
        spoofed_payload = create_sample_session_key_install_payload(gateway_id="gw-b", target_gw_id=2)
        spoofed_bytes = json.dumps(spoofed_payload).encode("utf-8")

        # Broker ACL allows this publish because Backend is authorized to publish to iot/v1/gw/+/downlink/session-key-install
        # and Gateway A is authorized to read iot/v1/gw/gw-a/downlink/session-key-install
        rc = backend.publish("iot/v1/gw/gw-a/downlink/session-key-install", spoofed_bytes, qos=1)
        self.assertEqual(rc, 0, "Broker transports the message based on topic ACL alone")

        recv = gw_a.receive_message(timeout=5.0)
        self.assertIsNotNone(recv, "Gateway A receives the message from broker transport")

        # Layer 2 Validator at Gateway A MUST detect and REJECT the payload gateway_id mismatch!
        gw_validator = SessionKeySemanticValidator(expected_principal="gw-a")
        valid, reason, _ = gw_validator.validate_install(recv["topic"], recv["payload"])
        self.assertFalse(valid, "Gateway validator must reject payload gateway_id mismatch")
        self.assertIn("REJECT_WRONG_GATEWAY", reason)

        # Case 2: Gateway ID in payload matches topic ('gw-a'), but target_gw_id (RF code) is mismatched (e.g. 2 instead of 1)
        rf_mismatch_payload = create_sample_session_key_install_payload(gateway_id="gw-a", target_gw_id=2)
        rf_mismatch_bytes = json.dumps(rf_mismatch_payload).encode("utf-8")
        backend.publish("iot/v1/gw/gw-a/downlink/session-key-install", rf_mismatch_bytes, qos=1)

        recv_rf = gw_a.receive_message(timeout=5.0)
        valid_rf, reason_rf, _ = gw_validator.validate_install(recv_rf["topic"], recv_rf["payload"])
        self.assertFalse(valid_rf, "Gateway validator must reject RF target_gw_id mismatch")
        self.assertIn("REQUIRES_GATEWAY_REGISTRY_CHECK", reason_rf)

        # Case 3: Gateway A sends ACK to topic gw-a, but payload gateway_id is 'gw-b'
        backend.subscribe("iot/v1/gw/+/uplink/session-key-ack", qos=1)
        spoofed_ack = create_sample_session_key_ack_payload(gateway_id="gw-b", status="INSTALLED", reason_code="NONE")
        spoofed_ack_bytes = json.dumps(spoofed_ack).encode("utf-8")

        gw_a.publish("iot/v1/gw/gw-a/uplink/session-key-ack", spoofed_ack_bytes, qos=1)
        recv_ack = backend.receive_message(timeout=5.0)
        self.assertIsNotNone(recv_ack)

        backend_validator = SessionKeySemanticValidator()
        ack_valid, ack_reason, _ = backend_validator.validate_ack(recv_ack["topic"], recv_ack["payload"])
        self.assertFalse(ack_valid, "Backend validator must reject ACK gateway_id mismatch")
        self.assertIn("REJECT_WRONG_GATEWAY", ack_reason)

        gw_a.disconnect()
        backend.disconnect()

    # -------------------------------------------------------------------------
    # TEST 5: Resilience, QoS 1 Duplicate Delivery, Reconnect, Stale & Expired Cases
    # -------------------------------------------------------------------------
    def test_05_resilience_and_qos1_delivery(self):
        """Test QoS 1 duplicate delivery idempotency, reconnect with Clean Start, stale revisions, and expired deadlines."""
        backend = self._client("backend")
        backend.connect_tls()
        backend.connect_mqtt5("test-backend-resilience")

        gw_a = self._client("gw-a")
        gw_a.connect_tls()
        gw_a.connect_mqtt5("test-gw-a-resilience", clean_start=True)
        gw_a.subscribe("iot/v1/gw/gw-a/downlink/session-key-install", qos=1)

        validator = SessionKeySemanticValidator(expected_principal="gw-a")

        # 1. First delivery of session-key-install
        payload_1 = create_sample_session_key_install_payload(gateway_id="gw-a", target_gw_id=1, session_revision="5")
        bytes_1 = json.dumps(payload_1).encode("utf-8")
        backend.publish("iot/v1/gw/gw-a/downlink/session-key-install", bytes_1, qos=1)

        recv_1 = gw_a.receive_message(timeout=5.0)
        valid_1, reason_1, _ = validator.validate_install(recv_1["topic"], recv_1["payload"])
        self.assertTrue(valid_1)
        self.assertEqual(reason_1, "ACCEPT_SESSION_KEY_INSTALL")

        # 2. Duplicate QoS 1 delivery with identical install_id & payload
        backend.publish("iot/v1/gw/gw-a/downlink/session-key-install", bytes_1, qos=1, dup=True)
        recv_dup = gw_a.receive_message(timeout=5.0)
        valid_dup, reason_dup, _ = validator.validate_install(recv_dup["topic"], recv_dup["payload"])
        self.assertTrue(valid_dup, "Duplicate delivery of identical payload must be accepted idempotently")
        self.assertEqual(reason_dup, "DUPLICATE_IDEMPOTENT_ACCEPT")

        # 3. Stale session revision (e.g. revision 3 after revision 5)
        stale_payload = create_sample_session_key_install_payload(
            gateway_id="gw-a", target_gw_id=1, session_revision="3"
        )
        stale_payload["install_id"] = "a1111111-1111-1111-1111-111111111111"
        stale_bytes = json.dumps(stale_payload).encode("utf-8")
        backend.publish("iot/v1/gw/gw-a/downlink/session-key-install", stale_bytes, qos=1)

        recv_stale = gw_a.receive_message(timeout=5.0)
        valid_stale, reason_stale, _ = validator.validate_install(recv_stale["topic"], recv_stale["payload"])
        self.assertFalse(valid_stale, "Stale session revision must be rejected")
        self.assertIn("REJECT_STALE_SESSION_REVISION", reason_stale)

        # 4. Expired install deadline (deadline in the past)
        expired_payload = create_sample_session_key_install_payload(
            gateway_id="gw-a", target_gw_id=1, session_revision="10", deadline_offset_sec=-100
        )
        expired_payload["install_id"] = "b2222222-2222-2222-2222-222222222222"
        expired_bytes = json.dumps(expired_payload).encode("utf-8")
        backend.publish("iot/v1/gw/gw-a/downlink/session-key-install", expired_bytes, qos=1)

        recv_exp = gw_a.receive_message(timeout=5.0)
        valid_exp, reason_exp, _ = validator.validate_install(recv_exp["topic"], recv_exp["payload"])
        self.assertFalse(valid_exp, "Expired install deadline must be rejected")
        self.assertEqual(reason_exp, "REJECT_EXPIRED_INSTALL_DEADLINE")

        # 5. Retained message rejection
        valid_retain_test, reason_retain, _ = validator.validate_install(
            recv_1["topic"], recv_1["payload"], retained=True
        )
        self.assertFalse(valid_retain_test, "Retained message must be rejected")
        self.assertEqual(reason_retain, "REJECT_UNAUTHORIZED_RETAINED_MESSAGE")

        # 6. Reconnect with Clean Start=True: disconnect and reconnect cleanly
        gw_a.disconnect()
        gw_reconnect = self._client("gw-a")
        gw_reconnect.connect_tls()
        rc_reconn = gw_reconnect.connect_mqtt5("test-gw-a-reconnect", clean_start=True)
        self.assertEqual(rc_reconn, 0, "Gateway successfully reconnects with Clean Start=True")
        gw_reconnect.subscribe("iot/v1/gw/gw-a/downlink/session-key-install", qos=1)

        # Fresh valid install after reconnect
        payload_fresh = create_sample_session_key_install_payload(
            gateway_id="gw-a", target_gw_id=1, session_revision="11"
        )
        payload_fresh["install_id"] = "c3333333-3333-3333-3333-333333333333"
        fresh_bytes = json.dumps(payload_fresh).encode("utf-8")
        backend.publish("iot/v1/gw/gw-a/downlink/session-key-install", fresh_bytes, qos=1)

        recv_fresh = gw_reconnect.receive_message(timeout=5.0)
        valid_fresh, reason_fresh, _ = validator.validate_install(recv_fresh["topic"], recv_fresh["payload"])
        self.assertTrue(valid_fresh)
        self.assertEqual(reason_fresh, "ACCEPT_SESSION_KEY_INSTALL")

        gw_reconnect.disconnect()
        backend.disconnect()

    # -------------------------------------------------------------------------
    # TEST 6: Provenance, Image IDs and Log Secret Cleanliness
    # -------------------------------------------------------------------------
    def test_06_provenance_and_clean_audit(self):
        """Assert Mosquitto image ID, broker logs cleanliness, and absence of private keys."""
        inspect_res = run_cmd("docker", "inspect", IMAGE)
        image_data = json.loads(inspect_res.stdout)
        self.assertTrue(image_data, "eclipse-mosquitto:2.0 image inspection must succeed")
        image_id = image_data[0]["Id"]
        self.assertTrue(image_id.startswith("sha256:"), f"Expected sha256 image ID, got {image_id}")

        logs = run_cmd(*self.compose_cmd, "logs", "--no-color", "mqtt-tls", env=self.env).stdout
        # Broker logs must contain evidence of TLS connection and auth decisions
        self.assertIn("mosquitto version 2.0", logs)
        self.assertIn("Opening ipv4 listen socket on port 8883", logs)
        self.assertIn("peer did not return a certificate", logs)
        self.assertIn("certificate verify failed", logs)

        # Assert no private key material appears in logs
        for forbidden in ("BEGIN RSA PRIVATE KEY", "BEGIN PRIVATE KEY", "BEGIN EC PRIVATE KEY"):
            self.assertNotIn(forbidden, logs, f"Forbidden secret header found in broker logs: {forbidden}")


if __name__ == "__main__":
    unittest.main()
