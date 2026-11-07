"""PostgreSQL Discrete Event Ingestion, Idempotency, Quarantine & Health Integration Test.

Tests real PostgreSQL container with migrations 000001..000003, exact duplicate deduplication,
conflicting payload quarantine, concurrency safety, container restart persistence,
and migration rollback/restore.
Authority: Issue #18, Issue #125, DEC-127-01, DEC-MH-02, DB-001..DB-010.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_01_UP = ROOT / "backend-go/migrations/000001_rf_channels.up.sql"
MIGRATION_02_UP = ROOT / "backend-go/migrations/000002_device_join_registry.up.sql"
MIGRATION_03_UP = ROOT / "backend-go/migrations/000003_event_storage_and_health.up.sql"
MIGRATION_03_DOWN = ROOT / "backend-go/migrations/000003_event_storage_and_health.down.sql"
IMAGE = "postgres:16-alpine"


def run_cmd(*args, check=True, timeout=60):
    return subprocess.run(args, capture_output=True, text=True, check=check, timeout=timeout)


class TestPostgresEventStorageIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container_name = "test-pg-event-" + secrets.token_hex(4)
        cls.db_user = "postgres"
        cls.db_name = "lora_event_test"
        cls.db_password = secrets.token_hex(16)

        run_cmd(
            "docker", "run", "-d",
            "--name", cls.container_name,
            "-e", f"POSTGRES_USER={cls.db_user}",
            "-e", f"POSTGRES_PASSWORD={cls.db_password}",
            "-e", f"POSTGRES_DB={cls.db_name}",
            IMAGE
        )

        # Wait for PostgreSQL to be ready
        ready = False
        for _ in range(30):
            res = run_cmd(
                "docker", "exec", "-e", f"PGPASSWORD={cls.db_password}",
                cls.container_name, "pg_isready", "-h", "127.0.0.1", "-U", cls.db_user, "-d", cls.db_name,
                check=False
            )
            if res.returncode == 0:
                ready = True
                break
            time.sleep(1)

        if not ready:
            run_cmd("docker", "rm", "-f", cls.container_name, check=False)
            raise RuntimeError("PostgreSQL container failed to become ready")

    @classmethod
    def tearDownClass(cls):
        run_cmd("docker", "rm", "-f", cls.container_name, check=False)

    def psql(self, sql_statement, check=True):
        return run_cmd(
            "docker", "exec", "-i", "-e", f"PGPASSWORD={self.db_password}",
            self.container_name,
            "psql", "-h", "127.0.0.1", "-U", self.db_user, "-d", self.db_name,
            "-v", "ON_ERROR_STOP=1", "-Atc", sql_statement,
            check=check
        )

    def psql_file(self, sql_file_path, check=True):
        content = Path(sql_file_path).read_text(encoding="utf-8")
        p = subprocess.Popen(
            [
                "docker", "exec", "-i", "-e", f"PGPASSWORD={self.db_password}",
                self.container_name,
                "psql", "-h", "127.0.0.1", "-U", self.db_user, "-d", self.db_name,
                "-v", "ON_ERROR_STOP=1"
            ],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, stderr = p.communicate(input=content, timeout=30)
        if check and p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, "psql_file", output=stdout, stderr=stderr)
        return p.returncode, stdout, stderr

    def test_01_migrations_apply_cleanly(self):
        # Apply prerequisite migrations 01 and 02
        c1, out1, err1 = self.psql_file(MIGRATION_01_UP)
        self.assertEqual(c1, 0, f"Migration 01 failed: {err1}")

        c2, out2, err2 = self.psql_file(MIGRATION_02_UP)
        self.assertEqual(c2, 0, f"Migration 02 failed: {err2}")

        # Apply target migration 03
        c3, out3, err3 = self.psql_file(MIGRATION_03_UP)
        self.assertEqual(c3, 0, f"Migration 03 failed: {err3}")

        # Verify tables exist
        tables = self.psql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
        ).stdout.strip().split("\n")
        self.assertIn("events", tables)
        self.assertIn("event_quarantine", tables)
        self.assertIn("node_health", tables)

    def test_02_first_event_insert_and_retrieval(self):
        raw_hash = "\\x" + hashlib.sha256(b"event_01_payload").hexdigest()
        insert_sql = f"""
            INSERT INTO events (
                event_id, gateway_id, gateway_epoch, event_seq, node_id, superframe_seq,
                seq_num, schedule_version, severity, observed_at, observed_time_source,
                radio_rx_monotonic_us, buffered, radio_ack_sent, slot_id, sensor_status_mask,
                ch1_raw, ch2_raw, ch3_raw, battery_mv, node_duty_permille,
                raw_payload_sha256
            ) VALUES (
                'gw01:550e8400-e29b-41d4-a716-446655440000:1', 'gw01', '550e8400-e29b-41d4-a716-446655440000',
                1, 1, 100, 1, 1, 'P1_HIGH', NOW(), 'gateway_utc', 1234567, FALSE, TRUE, 1, 0,
                2500, 500, 100, 3300, 10, '{raw_hash}'
            ) RETURNING id;
        """
        row_id_raw = self.psql(insert_sql).stdout.strip()
        row_id = row_id_raw.splitlines()[0].strip() if row_id_raw else ""
        self.assertTrue(row_id.isdigit(), f"Expected numeric row_id, got {repr(row_id_raw)}")

        # Retrieve and verify
        count = int(self.psql("SELECT COUNT(*) FROM events WHERE gateway_id = 'gw01' AND node_id = 1;").stdout.strip())
        self.assertEqual(count, 1)

    def test_03_exact_duplicate_unique_constraint(self):
        # Attempt inserting exact duplicate (same gateway_id and event_id)
        raw_hash = "\\x" + hashlib.sha256(b"event_01_payload").hexdigest()
        duplicate_sql = f"""
            INSERT INTO events (
                event_id, gateway_id, gateway_epoch, event_seq, node_id, superframe_seq,
                seq_num, schedule_version, severity, observed_at, observed_time_source,
                radio_rx_monotonic_us, buffered, radio_ack_sent, slot_id, sensor_status_mask,
                ch1_raw, ch2_raw, ch3_raw, battery_mv, node_duty_permille,
                raw_payload_sha256
            ) VALUES (
                'gw01:550e8400-e29b-41d4-a716-446655440000:1', 'gw01', '550e8400-e29b-41d4-a716-446655440000',
                1, 1, 100, 1, 1, 'P1_HIGH', NOW(), 'gateway_utc', 1234567, TRUE, TRUE, 1, 0,
                2500, 500, 100, 3300, 10, '{raw_hash}'
            );
        """
        res = self.psql(duplicate_sql, check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("idx_events_gateway_event_id", res.stderr)

        # Count must remain exactly 1
        count = int(self.psql("SELECT COUNT(*) FROM events WHERE event_id = 'gw01:550e8400-e29b-41d4-a716-446655440000:1';").stdout.strip())
        self.assertEqual(count, 1)

    def test_04_conflicting_payload_quarantine(self):
        # Record conflict to event_quarantine
        conflicting_hash = "\\x" + hashlib.sha256(b"conflicting_bytes").hexdigest()
        quarantine_sql = f"""
            INSERT INTO event_quarantine (
                gateway_id, event_id, conflict_reason, conflicting_sha256, raw_payload
            ) VALUES (
                'gw01', 'gw01:550e8400-e29b-41d4-a716-446655440000:1',
                'CONFLICTING_PAYLOAD_HASH', '{conflicting_hash}', 'ch1=9999'
            ) RETURNING id;
        """
        qid_raw = self.psql(quarantine_sql).stdout.strip()
        qid = qid_raw.splitlines()[0].strip() if qid_raw else ""
        self.assertTrue(qid.isdigit(), f"Expected numeric qid, got {repr(qid_raw)}")

        # Verify quarantine count
        q_count = int(self.psql("SELECT COUNT(*) FROM event_quarantine WHERE conflict_reason = 'CONFLICTING_PAYLOAD_HASH';").stdout.strip())
        self.assertGreaterEqual(q_count, 1)

    def test_05_concurrent_duplicate_ingest_race(self):
        event_id = "gw01:550e8400-e29b-41d4-a716-446655440000:999"
        raw_hash = "\\x" + hashlib.sha256(b"event_999_payload").hexdigest()

        insert_sql = f"""
            INSERT INTO events (
                event_id, gateway_id, gateway_epoch, event_seq, node_id, superframe_seq,
                seq_num, schedule_version, severity, observed_at, observed_time_source,
                radio_rx_monotonic_us, buffered, radio_ack_sent, slot_id, sensor_status_mask,
                ch1_raw, ch2_raw, ch3_raw, battery_mv, node_duty_permille,
                raw_payload_sha256
            ) VALUES (
                '{event_id}', 'gw01', '550e8400-e29b-41d4-a716-446655440000',
                999, 2, 200, 1, 1, 'P2_MEDIUM', NOW(), 'gateway_utc', 999999, FALSE, TRUE, 2, 0,
                1200, 300, 50, 3300, 5, '{raw_hash}'
            );
        """

        def attempt_insert():
            return self.psql(insert_sql, check=False)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(attempt_insert) for _ in range(5)]
            results = [f.result() for f in futures]

        success_count = sum(1 for r in results if r.returncode == 0)
        self.assertEqual(success_count, 1, "Exactly one concurrent insert must succeed")

        count = int(self.psql(f"SELECT COUNT(*) FROM events WHERE event_id = '{event_id}';").stdout.strip())
        self.assertEqual(count, 1)

    def test_06_node_health_authenticated_update(self):
        upsert_sql = """
            INSERT INTO node_health (
                gateway_id, node_id, session_sel, frame_counter, maint_seq, status_flags,
                pending_event_count, health_status
            ) VALUES ('gw01', 2, 1, 500, 50, 0, 3, 'ONLINE')
            ON CONFLICT (gateway_id, node_id) DO UPDATE SET
                frame_counter = EXCLUDED.frame_counter,
                maint_seq = EXCLUDED.maint_seq,
                pending_event_count = EXCLUDED.pending_event_count,
                health_status = EXCLUDED.health_status,
                last_seen_at = CURRENT_TIMESTAMP;
        """
        self.psql(upsert_sql)

        pending = int(self.psql("SELECT pending_event_count FROM node_health WHERE gateway_id = 'gw01' AND node_id = 2;").stdout.strip())
        self.assertEqual(pending, 3)

        # Update with new FIFO depth
        update_sql = """
            INSERT INTO node_health (
                gateway_id, node_id, session_sel, frame_counter, maint_seq, status_flags,
                pending_event_count, health_status
            ) VALUES ('gw01', 2, 1, 505, 51, 0, 0, 'ONLINE')
            ON CONFLICT (gateway_id, node_id) DO UPDATE SET
                frame_counter = EXCLUDED.frame_counter,
                maint_seq = EXCLUDED.maint_seq,
                pending_event_count = EXCLUDED.pending_event_count,
                health_status = EXCLUDED.health_status,
                last_seen_at = CURRENT_TIMESTAMP;
        """
        self.psql(update_sql)

        pending_updated = int(self.psql("SELECT pending_event_count FROM node_health WHERE gateway_id = 'gw01' AND node_id = 2;").stdout.strip())
        self.assertEqual(pending_updated, 0)

    def test_07_persistence_across_restart(self):
        run_cmd("docker", "restart", self.container_name)

        # Wait for ready after restart
        ready = False
        for _ in range(30):
            res = run_cmd(
                "docker", "exec", "-e", f"PGPASSWORD={self.db_password}",
                self.container_name, "pg_isready", "-h", "127.0.0.1", "-U", self.db_user, "-d", self.db_name,
                check=False
            )
            if res.returncode == 0:
                ready = True
                break
            time.sleep(1)
        self.assertTrue(ready, "PostgreSQL failed to resume after restart")

        count = int(self.psql("SELECT COUNT(*) FROM events;").stdout.strip())
        self.assertGreaterEqual(count, 2)

    def test_08_migration_rollback_and_restore(self):
        # Rollback migration 03
        c_down, out_down, err_down = self.psql_file(MIGRATION_03_DOWN)
        self.assertEqual(c_down, 0, f"Rollback failed: {err_down}")

        # Verify tables dropped
        tables = self.psql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
        ).stdout.strip().split("\n")
        self.assertNotIn("events", tables)
        self.assertNotIn("event_quarantine", tables)
        self.assertNotIn("node_health", tables)
        # Prerequisite tables from migrations 01 and 02 remain intact
        self.assertIn("rf_channels", tables)
        self.assertIn("devices", tables)

        # Restore migration 03
        c_up, out_up, err_up = self.psql_file(MIGRATION_03_UP)
        self.assertEqual(c_up, 0, f"Restore failed: {err_up}")

        tables_restored = self.psql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
        ).stdout.strip().split("\n")
        self.assertIn("events", tables_restored)
        self.assertIn("event_quarantine", tables_restored)
        self.assertIn("node_health", tables_restored)


if __name__ == "__main__":
    unittest.main()
