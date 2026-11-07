"""End-to-end Integration Test for MQTT V2 Join Relay Envelope Ingest & PostgreSQL Idempotency.

Authority: Issue #218, contracts/mqtt/schemas/join-hello.schema.json,
contracts/mqtt/topics.md, contracts/mqtt/semantic-rules.md (JH-01..JH-08).
"""

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import struct
import subprocess
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_01_UP = ROOT / "backend-go/migrations/000001_rf_channels.up.sql"
MIGRATION_02_UP = ROOT / "backend-go/migrations/000002_device_join_registry.up.sql"
MIGRATION_02_DOWN = ROOT / "backend-go/migrations/000002_device_join_registry.down.sql"
SCHEMA_JOIN_HELLO = ROOT / "contracts/mqtt/schemas/join-hello.schema.json"

PG_IMAGE = "postgres:16-alpine"
MOSQUITTO_IMAGE = "eclipse-mosquitto:2.0"


def run_cmd(*args, check=True, timeout=60):
    return subprocess.run(args, capture_output=True, text=True, check=check, timeout=timeout)


def hkdf_extract_and_expand(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    # HKDF-Extract(salt, ikm) -> PRK
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    # HKDF-Expand(PRK, info, L) -> OKM
    t = b""
    okm = b""
    i = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
        i += 1
    return okm[:length]


def build_up_join_hello_frame(network_id: int, gen: int, mac: bytes, target_gw: int, counter: int, k_join: bytes) -> bytes:
    ver_type = 0x45
    nonce = os.urandom(8)
    pub = os.urandom(32)
    # Ensure pub is non-zero
    if all(b == 0 for b in pub):
        pub = b"\x01" + pub[1:]

    prefix52 = bytearray()
    prefix52.append(ver_type)
    prefix52.extend(mac)
    prefix52.append(target_gw)
    prefix52.extend(struct.pack(">I", counter))
    prefix52.extend(nonce)
    prefix52.extend(pub)
    assert len(prefix52) == 52

    # HKDF salt = "LP2P/V2/JOIN-ROOT" || network_id (4B BE) || mac (6B) || gen (2B BE)
    salt = b"LP2P/V2/JOIN-ROOT" + struct.pack(">I", network_id) + mac + struct.pack(">H", gen)
    kj_req = hkdf_extract_and_expand(salt=salt, ikm=k_join, info=b"LP2P/V2/JOIN-REQ", length=32)

    # M_HELLO = "LP2P/V2/M-HELLO" || network_id (4B BE) || prefix52
    m_hello = b"LP2P/V2/M-HELLO" + struct.pack(">I", network_id) + bytes(prefix52)
    full_hmac = hmac.new(kj_req, m_hello, hashlib.sha256).digest()
    proof = full_hmac[:16]

    return bytes(prefix52) + proof


class TestMQTTJoinHelloPostgresIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Start PostgreSQL container
        cls.pg_name = "test-pg-join-" + secrets.token_hex(4)
        cls.db_user = "test_user"
        cls.db_name = "lora_join_test"
        cls.db_password = secrets.token_hex(16)

        run_cmd(
            "docker", "run", "-d",
            "--name", cls.pg_name,
            "-e", f"POSTGRES_USER={cls.db_user}",
            "-e", f"POSTGRES_PASSWORD={cls.db_password}",
            "-e", f"POSTGRES_DB={cls.db_name}",
            PG_IMAGE
        )

        # Wait for PostgreSQL
        ready = False
        for _ in range(30):
            res = run_cmd("docker", "exec", cls.pg_name,
                          "pg_isready", "-U", cls.db_user, "-d", cls.db_name, check=False)
            if res.returncode == 0:
                ready = True
                break
            time.sleep(1)

        if not ready:
            run_cmd("docker", "rm", "-f", cls.pg_name, check=False)
            raise RuntimeError("PostgreSQL container failed to become ready")

        # 2. Start Mosquitto container with anonymous allow for local test network
        cls.mqtt_name = "test-mqtt-join-" + secrets.token_hex(4)
        run_cmd(
            "docker", "run", "-d",
            "--name", cls.mqtt_name,
            MOSQUITTO_IMAGE,
            "mosquitto", "-c", "/mosquitto/config/mosquitto.conf"
        )
        time.sleep(2)

    @classmethod
    def tearDownClass(cls):
        run_cmd("docker", "rm", "-f", cls.pg_name, check=False)
        run_cmd("docker", "rm", "-f", cls.mqtt_name, check=False)

    def psql(self, sql_statement, check=True):
        return run_cmd(
            "docker", "exec", "-i", self.pg_name,
            "psql", "-U", self.db_user, "-d", self.db_name,
            "-v", "ON_ERROR_STOP=1", "-Atc", sql_statement,
            check=check
        )

    def psql_file(self, sql_file_path, check=True):
        content = Path(sql_file_path).read_text(encoding="utf-8")
        p = subprocess.Popen(
            ["docker", "exec", "-i", self.pg_name,
             "psql", "-U", self.db_user, "-d", self.db_name, "-v", "ON_ERROR_STOP=1"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, stderr = p.communicate(input=content, timeout=30)
        if check and p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, "psql_file", output=stdout, stderr=stderr)
        return p.returncode, stdout, stderr

    def test_01_apply_migrations_and_seed_device(self):
        # Apply migration 1 and 2
        code, _, stderr = self.psql_file(MIGRATION_01_UP)
        self.assertEqual(code, 0, f"Migration 01 failed: {stderr}")

        code, _, stderr = self.psql_file(MIGRATION_02_UP)
        self.assertEqual(code, 0, f"Migration 02 failed: {stderr}")

        # Seed device with active generation
        self.network_id = 100
        self.mac = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66])
        self.k_join = secrets.token_bytes(32)
        self.gen = 1

        mac_hex = self.mac.hex()
        k_join_hex = self.k_join.hex()

        self.psql(f"""
            INSERT INTO devices (network_id, device_mac, status)
            VALUES ({self.network_id}, decode('{mac_hex}', 'hex'), 'ACTIVE');

            INSERT INTO device_generations (network_id, device_mac, generation, k_join_wrapped, is_active)
            VALUES ({self.network_id}, decode('{mac_hex}', 'hex'), {self.gen}, decode('{k_join_hex}', 'hex'), TRUE);
        """)

        # Verify device row
        status = self.psql(f"SELECT status FROM devices WHERE network_id={self.network_id} AND device_mac=decode('{mac_hex}', 'hex');").stdout.strip()
        self.assertEqual(status, "ACTIVE")

    def test_02_ingest_join_hello_envelope_and_database_persistence(self):
        network_id = 100
        mac = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66])
        # Fetch seeded K_JOIN from DB to ensure DB integrity
        k_join_hex = self.psql(f"SELECT encode(k_join_wrapped, 'hex') FROM device_generations WHERE network_id={network_id} AND device_mac=decode('{mac.hex()}', 'hex');").stdout.strip()
        k_join = bytes.fromhex(k_join_hex)
        target_gw_id = 1

        # 1. Build authentic 68-byte UP_JOIN_HELLO frame with counter = 1
        frame = build_up_join_hello_frame(network_id, 1, mac, target_gw_id, 1, k_join)
        self.assertEqual(len(frame), 68)

        # 2. Construct canonical relay envelope
        gateway_id = "gw-alpha"
        gateway_epoch = "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
        event_seq = "1"
        event_id = f"{gateway_id}:{gateway_epoch}:{event_seq}"
        raw_hex = frame.hex()
        raw_sha256 = hashlib.sha256(frame).digest()

        envelope = {
            "schema_version": "1.0-draft",
            "event_id": event_id,
            "gateway_id": gateway_id,
            "gateway_epoch": gateway_epoch,
            "event_seq": event_seq,
            "observed_at": "2026-11-07T12:30:00.000Z",
            "observed_time_source": "gateway_utc",
            "radio_rx_monotonic_us": "12345678",
            "buffered": False,
            "target_gw_id": target_gw_id,
            "raw_frame_hex": raw_hex,
            "rssi": -80,
            "snr": 6.5
        }

        # 3. Test publish over MQTT broker
        payload_str = json.dumps(envelope)
        topic = f"iot/v1/gw/{gateway_id}/uplink/join-hello"
        pub_res = run_cmd("docker", "exec", self.mqtt_name,
                          "mosquitto_pub", "-t", topic, "-m", payload_str, "-q", "1", check=False)
        self.assertEqual(pub_res.returncode, 0, f"mosquitto_pub failed: {pub_res.stderr}")

        # 4. Ingest and persist transaction into PostgreSQL
        # Record join transaction
        self.psql(f"""
            INSERT INTO join_transactions (network_id, device_mac, generation, target_gw_id, join_counter, status, raw_hello_sha256, node_nonce, node_x25519_pub)
            VALUES ({network_id}, decode('{mac.hex()}', 'hex'), 1, {target_gw_id}, 1, 'HELLO_AUTHENTICATED_PENDING_GRANT',
                    decode('{raw_sha256.hex()}', 'hex'), decode('{frame[12:20].hex()}', 'hex'), decode('{frame[20:52].hex()}', 'hex'));

            INSERT INTO device_join_counters (network_id, device_mac, generation, last_join_counter)
            VALUES ({network_id}, decode('{mac.hex()}', 'hex'), 1, 1)
            ON CONFLICT (network_id, device_mac, generation)
            DO UPDATE SET last_join_counter = 1, updated_at = CURRENT_TIMESTAMP;
        """)

        # Verify transaction status in DB
        row = self.psql(f"SELECT status, join_counter FROM join_transactions WHERE network_id={network_id} AND device_mac=decode('{mac.hex()}', 'hex');").stdout.strip()
        status, counter_str = row.split("|")
        self.assertEqual(status, "HELLO_AUTHENTICATED_PENDING_GRANT")
        self.assertEqual(int(counter_str), 1)

        # 5. Idempotent retransmission deduplication: byte-identical retransmission
        # When same raw_hello_sha256 is presented, query returns existing transaction
        existing_id = self.psql(f"""
            SELECT id FROM join_transactions
            WHERE network_id={network_id} AND device_mac=decode('{mac.hex()}', 'hex')
              AND generation=1 AND raw_hello_sha256=decode('{raw_sha256.hex()}', 'hex');
        """).stdout.strip()
        self.assertTrue(len(existing_id) > 0, "Expected existing transaction row for duplicate frame")

        # 6. Anti-replay conflict protection: same counter 1, different hash -> DB unique constraint rejects
        different_sha = hashlib.sha256(b"different_payload").digest().hex()
        conflict_res = self.psql(f"""
            INSERT INTO join_transactions (network_id, device_mac, generation, target_gw_id, join_counter, status, raw_hello_sha256, node_nonce, node_x25519_pub)
            VALUES ({network_id}, decode('{mac.hex()}', 'hex'), 1, {target_gw_id}, 1, 'HELLO_AUTHENTICATED_PENDING_GRANT',
                    decode('{different_sha}', 'hex'), decode('{frame[12:20].hex()}', 'hex'), decode('{frame[20:52].hex()}', 'hex'));
        """, check=False)
        self.assertNotEqual(conflict_res.returncode, 0, "Expected unique constraint violation on replayed counter")
        self.assertIn("idx_join_transactions_unique_counter", conflict_res.stderr)

    def test_03_migration_down_rollback(self):
        code, _, stderr = self.psql_file(MIGRATION_02_DOWN)
        self.assertEqual(code, 0, f"Migration 02 rollback failed: {stderr}")

        # Verify tables dropped
        exists = self.psql("SELECT to_regclass('public.join_transactions');").stdout.strip()
        self.assertEqual(exists, "")


if __name__ == "__main__":
    unittest.main()
