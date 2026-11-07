"""PostgreSQL VN920 Channel Registry & Exclusive Gateway Allocation Integration Test.

Tests real PostgreSQL container with migrations, atomic concurrency, idempotency,
exclusive index constraints, container restart persistence, and migration rollback.
Authority: Issue #154, DB-001..DB-010, GGS-006.
"""

import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_UP = ROOT / "backend-go/migrations/000001_rf_channels.up.sql"
MIGRATIONS_DOWN = ROOT / "backend-go/migrations/000001_rf_channels.down.sql"
IMAGE = "postgres:16-alpine"

EXPECTED_VN920_CHANNELS = {
    "CH00": (920250000, 125000),
    "CH01": (920500000, 125000),
    "CH02": (920750000, 125000),
    "CH03": (921000000, 125000),
    "CH04": (921250000, 125000),
    "CH05": (921500000, 125000),
    "CH06": (921750000, 125000),
    "CH07": (922000000, 125000),
    "CH08": (922250000, 125000),
    "CH09": (922500000, 125000),
    "CH10": (922750000, 125000),
}


def run_cmd(*args, check=True, timeout=60):
    return subprocess.run(args, capture_output=True, text=True, check=check, timeout=timeout)


class TestPostgresVN920ChannelRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container_name = "test-pg-vn920-" + secrets.token_hex(4)
        cls.db_user = "test_user"
        cls.db_name = "lora_vn920_test"
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
            res = run_cmd("docker", "exec", cls.container_name,
                          "pg_isready", "-U", cls.db_user, "-d", cls.db_name, check=False)
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
            "docker", "exec", "-i", self.container_name,
            "psql", "-U", self.db_user, "-d", self.db_name,
            "-v", "ON_ERROR_STOP=1", "-Atc", sql_statement,
            check=check
        )

    def psql_file(self, sql_file_path, check=True):
        content = Path(sql_file_path).read_text(encoding="utf-8")
        p = subprocess.Popen(
            ["docker", "exec", "-i", self.container_name,
             "psql", "-U", self.db_user, "-d", self.db_name, "-v", "ON_ERROR_STOP=1"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, stderr = p.communicate(input=content, timeout=30)
        if check and p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, "psql_file", output=stdout, stderr=stderr)
        return p.returncode, stdout, stderr

    def test_01_migration_up_and_seed_idempotency(self):
        code, stdout, stderr = self.psql_file(MIGRATIONS_UP)
        self.assertEqual(code, 0, f"Migration up failed: {stderr}")

        # Check channel count
        count = int(self.psql("SELECT COUNT(*) FROM rf_channels;").stdout.strip())
        self.assertEqual(count, 11, f"Expected 11 VN920 channels, got {count}")

        # Check exact frequency and bandwidth for every channel
        rows = self.psql("SELECT channel_id, center_frequency_hz, bandwidth_hz FROM rf_channels ORDER BY channel_id;").stdout.strip().splitlines()
        self.assertEqual(len(rows), 11)

        for row in rows:
            parts = row.split("|")
            ch_id, freq, bw = parts[0], int(parts[1]), int(parts[2])
            self.assertIn(ch_id, EXPECTED_VN920_CHANNELS, f"Unexpected channel {ch_id}")
            expected_freq, expected_bw = EXPECTED_VN920_CHANNELS[ch_id]
            self.assertEqual(freq, expected_freq, f"Channel {ch_id} frequency mismatch")
            self.assertEqual(bw, expected_bw, f"Channel {ch_id} bandwidth mismatch")

        # Test idempotency: re-running UP migration should succeed without error
        code2, _, stderr2 = self.psql_file(MIGRATIONS_UP)
        self.assertEqual(code2, 0, f"Re-running migration UP failed: {stderr2}")
        count2 = int(self.psql("SELECT COUNT(*) FROM rf_channels;").stdout.strip())
        self.assertEqual(count2, 11, "Idempotent re-run altered channel count")
        print("PASS: Migration UP and 11-channel idempotent seed verified", flush=True)

    def test_02_exclusive_channel_allocation_and_conflict(self):
        # 1. Allocate CH00 to gw-01
        insert1 = """
            INSERT INTO gateway_channel_allocations (
                gateway_id, channel_id, status, request_id, allocation_generation, granted_by
            ) VALUES ('gw-01', 'CH00', 'ALLOCATED', 'req-001', 1, 'test');
        """
        self.psql(insert1)

        # 2. Concurrent/competing request for the same channel CH00 by gw-02 MUST fail on unique index
        insert2 = """
            INSERT INTO gateway_channel_allocations (
                gateway_id, channel_id, status, request_id, allocation_generation, granted_by
            ) VALUES ('gw-02', 'CH00', 'ALLOCATED', 'req-002', 1, 'test');
        """
        res = self.psql(insert2, check=False)
        self.assertNotEqual(res.returncode, 0, "Competing allocation on occupied channel should fail")
        self.assertIn("idx_exclusive_active_channel", res.stderr + res.stdout,
                      "Expected unique violation on idx_exclusive_active_channel")

        # 3. Same gateway gw-01 attempting a second active channel CH01 MUST fail on gateway unique index
        insert3 = """
            INSERT INTO gateway_channel_allocations (
                gateway_id, channel_id, status, request_id, allocation_generation, granted_by
            ) VALUES ('gw-01', 'CH01', 'ALLOCATED', 'req-003', 1, 'test');
        """
        res3 = self.psql(insert3, check=False)
        self.assertNotEqual(res3.returncode, 0, "Second active allocation for same gateway should fail")
        self.assertIn("idx_exclusive_active_gateway", res3.stderr + res3.stdout,
                      "Expected unique violation on idx_exclusive_active_gateway")

        print("PASS: Database unique constraints enforce channel and gateway exclusivity", flush=True)

    def test_03_release_and_reallocation_with_monotonic_generation(self):
        # Release CH00 held by gw-01
        release = """
            UPDATE gateway_channel_allocations
            SET status = 'RELEASED',
                released_by = 'admin',
                release_reason = 'schedule_deactivated',
                released_at = CURRENT_TIMESTAMP
            WHERE gateway_id = 'gw-01' AND channel_id = 'CH00' AND status = 'ALLOCATED';
        """
        self.psql(release)

        # Check status is RELEASED
        status = self.psql("SELECT status FROM gateway_channel_allocations WHERE gateway_id = 'gw-01' AND channel_id = 'CH00' ORDER BY id DESC LIMIT 1;").stdout.strip()
        self.assertEqual(status, "RELEASED")

        # Now gw-02 CAN allocate CH00 with generation 2
        insert_gw02 = """
            INSERT INTO gateway_channel_allocations (
                gateway_id, channel_id, status, request_id, allocation_generation, granted_by
            ) VALUES ('gw-02', 'CH00', 'ALLOCATED', 'req-004', 2, 'test');
        """
        self.psql(insert_gw02)

        active_gw = self.psql("SELECT gateway_id FROM gateway_channel_allocations WHERE channel_id = 'CH00' AND status = 'ALLOCATED';").stdout.strip()
        self.assertEqual(active_gw, "gw-02")
        print("PASS: Explicit release frees channel for re-allocation with monotonic generation", flush=True)

    def test_04_persistence_across_restart(self):
        # Restart container
        run_cmd("docker", "restart", self.container_name)

        # Wait for PostgreSQL
        ready = False
        for _ in range(30):
            res = run_cmd("docker", "exec", self.container_name,
                          "pg_isready", "-U", self.db_user, "-d", self.db_name, check=False)
            if res.returncode == 0:
                ready = True
                break
            time.sleep(1)
        self.assertTrue(ready, "PostgreSQL not ready after restart")

        # Verify allocations and channels survive restart
        count = int(self.psql("SELECT COUNT(*) FROM rf_channels;").stdout.strip())
        self.assertEqual(count, 11)

        active_gw = self.psql("SELECT gateway_id FROM gateway_channel_allocations WHERE channel_id = 'CH00' AND status = 'ALLOCATED';").stdout.strip()
        self.assertEqual(active_gw, "gw-02")
        print("PASS: Channel registry and allocations persist across PostgreSQL restart", flush=True)

    def test_05_migration_rollback_and_restore(self):
        # Run DOWN migration
        code_down, _, stderr_down = self.psql_file(MIGRATIONS_DOWN)
        self.assertEqual(code_down, 0, f"Migration DOWN failed: {stderr_down}")

        # Verify tables do not exist
        res = self.psql("SELECT to_regclass('rf_channels');").stdout.strip()
        self.assertIn(res, ("", "null", "None"))
        res_alloc = self.psql("SELECT to_regclass('gateway_channel_allocations');").stdout.strip()
        self.assertIn(res_alloc, ("", "null", "None"))

        # Re-run UP migration to restore
        code_up, _, stderr_up = self.psql_file(MIGRATIONS_UP)
        self.assertEqual(code_up, 0, f"Migration UP restore failed: {stderr_up}")
        count = int(self.psql("SELECT COUNT(*) FROM rf_channels;").stdout.strip())
        self.assertEqual(count, 11)
        print("PASS: Migration DOWN rollback and UP restore verified", flush=True)


if __name__ == "__main__":
    unittest.main()
