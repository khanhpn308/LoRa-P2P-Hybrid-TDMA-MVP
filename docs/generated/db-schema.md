# Generated Database Schema Metadata

> **DO NOT HAND-EDIT.** This file is deterministically generated from migration SQL sources.
> Re-run the generation command below whenever `backend-go/migrations/` or `backend-go/Dockerfile` changes.

## Provenance & Freshness

- **Generated from:** `backend-go/migrations/*.up.sql` + `backend-go/Dockerfile` (`/app/migrate.sh`)
- **Migrations source commit:** `25d16622de5afdfd4dd34931c28ff7c4ceb7d6da`
- **Migrations tree SHA-256:** `4960b9e9de881dbdfc89ffd002515d1c806b2011f1854b829de64b29ef76c0dd`
- **Generation command:** `python3 scripts/agent_harness/advanced_pack.py generate-db-schema --repo . --output docs/generated/db-schema.md`
- **Freshness check command:** `python3 scripts/agent_harness/advanced_pack.py check-db-schema --repo . --schema docs/generated/db-schema.md`
- **Verification status:** `SOURCE_DERIVED_ONLY` (`LIVE_DB_INTROSPECTION: NOT_RUN`, `MIGRATION_EXECUTION: NOT_VERIFIED`)

## Migration Runner Semantics & Duplicate Numeric Prefixes

- **Actual runtime runner:** `backend-go/Dockerfile (/app/migrate.sh)` (`present=True`, `pg_advisory_lock=True`, `lexicographic_sort=True`, `full_filename_version_key=True`, `on_error_stop=True`).
- **Runner tracking table:** `schema_migrations (version VARCHAR(128) PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT NOW())` created under session advisory lock before applying pending `*.up.sql` files inside individual transactions.
- **Duplicate numeric prefix warning:** `000004` -> `000004_create_gateway_status.up.sql`, `000004_create_users_table.up.sql`, `000004_schedule_storage.up.sql`. Because `/app/migrate.sh` keys `schema_migrations.version` by full filename (`${base}`) and orders lexicographically (`sort`), multiple `000004_*` files execute deterministically in alphabetical order (`000004_create_gateway_status` -> `000004_create_users_table` -> `000004_schedule_storage`).
- **Documentation drift note:** `docs/development/POSTGRESQL_OPERATIONS_GUIDE.md` references `golang-migrate`, which rejects duplicate numeric prefixes (`000004_*`). The actual containerized runner in `backend-go/Dockerfile` is `/app/migrate.sh` (custom `psql` runner), **not** `golang-migrate`.

## Migration Inventory (Ordered Execution Sequence)

| # | Up Migration | Prefix | Down SQL | SHA-256 | DDL Summary |
|---|---|---|---|---|---|
| 1 | `000001_rf_channels.up.sql` | `000001` | YES | `706ec309b88b...` | CREATE rf_channels, gateway_channel_allocations |
| 2 | `000002_device_join_registry.up.sql` | `000002` | YES | `7b7fdb94c1a1...` | CREATE devices, device_generations, device_join_counters, join_transactions |
| 3 | `000003_event_storage_and_health.up.sql` | `000003` | YES | `a885b253fd2d...` | CREATE events, event_quarantine, node_health |
| 4 | `000004_create_gateway_status.up.sql` | `000004` | YES | `17c6500df062...` | CREATE gateway_status |
| 5 | `000004_create_users_table.up.sql` | `000004` | YES | `055417242bda...` | CREATE users |
| 6 | `000004_schedule_storage.up.sql` | `000004` | YES | `3556e6345ff5...` | CREATE schedules, schedule_slots, active_gateway_schedules, schedule_migration_transactions |
| 7 | `000005_gateways_registry.up.sql` | `000005` | YES | `865a0b6b99b4...` | CREATE gateways |
| 8 | `000006_add_user_full_name_and_email.up.sql` | `000006` | YES | `84e0d127bf11...` | ALTER users |
| 9 | `000007_device_join_requests.up.sql` | `000007` | YES | `766ad79511a8...` | CREATE device_join_requests |
| 10 | `000008_drop_last_seen_and_transient_status.up.sql` | `000008` | YES | `21cd6384c871...` | ALTER gateway_status, node_health |
| 11 | `000009_drop_tdma_schedules.up.sql` | `000009` | YES | `e7385cd11975...` | DROP schedule_migration_transactions, active_gateway_schedules, schedule_slots, schedules |

## Active Source-Derived Tables (13 application tables + 1 runner table)

| Table | Source Migration | Source-Derived Columns |
|---|---|---|
| `schema_migrations` | `backend-go/Dockerfile` (`/app/migrate.sh`) | `version (VARCHAR(128))`, `applied_at (TIMESTAMPTZ)` |
| `device_generations` | `000002_device_join_registry.up.sql` | `network_id (BIGINT)`, `device_mac (BYTEA)`, `generation (INT)`, `k_join_wrapped (BYTEA)`, `is_active (BOOLEAN)`, `created_at (TIMESTAMPTZ)` |
| `device_join_counters` | `000002_device_join_registry.up.sql` | `network_id (BIGINT)`, `device_mac (BYTEA)`, `generation (INT)`, `last_join_counter (BIGINT)`, `updated_at (TIMESTAMPTZ)` |
| `device_join_requests` | `000007_device_join_requests.up.sql` | `id (BIGSERIAL)`, `device_mac (VARCHAR(12))`, `gateway_id (VARCHAR(64))`, `rssi (INT)`, `snr (NUMERIC(5, 2))`, `raw_frame_hex (TEXT)`, `status (VARCHAR(20))`, `assigned_node_id (INT)`, `created_at (TIMESTAMPTZ)`, `updated_at (TIMESTAMPTZ)` |
| `devices` | `000002_device_join_registry.up.sql` | `network_id (BIGINT)`, `device_mac (BYTEA)`, `status (VARCHAR(16))`, `created_at (TIMESTAMPTZ)`, `updated_at (TIMESTAMPTZ)` |
| `event_quarantine` | `000003_event_storage_and_health.up.sql` | `id (BIGSERIAL)`, `gateway_id (VARCHAR(64))`, `event_id (VARCHAR(128))`, `conflict_reason (VARCHAR(64))`, `expected_sha256 (BYTEA)`, `conflicting_sha256 (BYTEA)`, `raw_payload (TEXT)`, `quarantined_at (TIMESTAMPTZ)` |
| `events` | `000003_event_storage_and_health.up.sql` | `id (BIGSERIAL)`, `event_id (VARCHAR(128))`, `gateway_id (VARCHAR(64))`, `gateway_epoch (UUID)`, `event_seq (NUMERIC(20, 0))`, `node_id (INT)`, `superframe_seq (BIGINT)`, `seq_num (INT)`, `schedule_version (BIGINT)`, `severity (VARCHAR(32))`, `observed_at (TIMESTAMPTZ)`, `observed_time_source (VARCHAR(32))`, `radio_rx_monotonic_us (NUMERIC(20, 0))`, `buffered (BOOLEAN)`, `radio_ack_sent (BOOLEAN)`, `event_ref (BIGINT)`, `event_code (INT)`, `event_value (INT)`, `slot_id (INT)`, `sensor_status_mask (INT)`, `ch1_raw (INT)`, `ch2_raw (INT)`, `ch3_raw (INT)`, `battery_mv (INT)`, `node_duty_permille (INT)`, `trigger_channel (INT)`, `trigger_observed_raw (INT)`, `trigger_threshold_raw (INT)`, `raw_payload_sha256 (BYTEA)`, `ingested_at (TIMESTAMPTZ)`, `ack_status (VARCHAR(32))`, `acknowledged_at (TIMESTAMPTZ)`, `acknowledged_by (VARCHAR(64))` |
| `gateway_channel_allocations` | `000001_rf_channels.up.sql` | `id (BIGSERIAL)`, `gateway_id (VARCHAR(64))`, `channel_id (VARCHAR(16))`, `status (VARCHAR(16))`, `request_id (VARCHAR(128))`, `allocation_generation (BIGINT)`, `granted_by (VARCHAR(64))`, `released_by (VARCHAR(64))`, `release_reason (TEXT)`, `created_at (TIMESTAMPTZ)`, `updated_at (TIMESTAMPTZ)`, `released_at (TIMESTAMPTZ)` |
| `gateway_status` | `000004_create_gateway_status.up.sql + 000008_drop_last_seen_and_transient_status.up.sql` | `gateway_id (VARCHAR(64))`, `gateway_epoch (UUID)`, `mode (VARCHAR(32))`, `active_schedule_version (BIGINT)`, `channel_id (VARCHAR(16))`, `rf_duty_permille (INT)`, `node_count (INT)`, `free_heap_bytes (BIGINT)`, `offline_queue_count (INT)`, `pending_event_count (INT)`, `dropped_event_count (NUMERIC(20, 0))`, `updated_at (TIMESTAMPTZ)` |
| `gateways` | `000005_gateways_registry.up.sql` | `gateway_id (VARCHAR(64))`, `name (VARCHAR(128))`, `location (VARCHAR(128))`, `ip_address (VARCHAR(64))`, `created_at (TIMESTAMPTZ)`, `updated_at (TIMESTAMPTZ)` |
| `join_transactions` | `000002_device_join_registry.up.sql` | `id (BIGSERIAL)`, `network_id (BIGINT)`, `device_mac (BYTEA)`, `generation (INT)`, `target_gw_id (INT)`, `join_counter (BIGINT)`, `status (VARCHAR(48))`, `raw_hello_sha256 (BYTEA)`, `node_nonce (BYTEA)`, `node_x25519_pub (BYTEA)`, `created_at (TIMESTAMPTZ)` |
| `node_health` | `000003_event_storage_and_health.up.sql + 000008_drop_last_seen_and_transient_status.up.sql` | `gateway_id (VARCHAR(64))`, `node_id (INT)`, `session_sel (INT)`, `frame_counter (BIGINT)`, `maint_seq (BIGINT)`, `status_flags (INT)`, `pending_event_count (INT)`, `health_status (VARCHAR(16))`, `updated_at (TIMESTAMPTZ)` |
| `rf_channels` | `000001_rf_channels.up.sql` | `channel_id (VARCHAR(16))`, `channel_plan_version (VARCHAR(32))`, `center_frequency_hz (BIGINT)`, `bandwidth_hz (BIGINT)`, `is_enabled (BOOLEAN)`, `created_at (TIMESTAMPTZ)`, `updated_at (TIMESTAMPTZ)` |
| `users` | `000004_create_users_table.up.sql + 000006_add_user_full_name_and_email.up.sql` | `id (UUID)`, `username (VARCHAR(64))`, `password_hash (VARCHAR(255))`, `role (VARCHAR(16))`, `is_active (BOOLEAN)`, `created_at (TIMESTAMPTZ)`, `updated_at (TIMESTAMPTZ)`, `full_name (VARCHAR(128))`, `email (VARCHAR(128))` |

## Dropped Historical Tables (Superseded TDMA Cleanup)

| Table | Dropped In |
|---|---|
| `active_gateway_schedules` | `000009_drop_tdma_schedules.up.sql` |
| `schedule_migration_transactions` | `000009_drop_tdma_schedules.up.sql` |
| `schedule_slots` | `000009_drop_tdma_schedules.up.sql` |
| `schedules` | `000009_drop_tdma_schedules.up.sql` |

## Explicit Limitations

- **Static source derivation only:** Derived offline from `backend-go/migrations/*.up.sql` and `backend-go/Dockerfile`; no live or production PostgreSQL database was accessed (`LIVE_DB_INTROSPECTION: NOT_RUN`).
- **Does not prove migration runtime success:** Applying migrations against PostgreSQL 16 (including constraints, seeds, and rollback `.down.sql` parity) requires an authorized integration test run (`MIGRATION_EXECUTION: NOT_VERIFIED` by this generator).
- **Column summary scope:** Parses top-level `CREATE TABLE` / `ALTER TABLE` / `DROP TABLE` DDL; constraints, triggers, and seed rows live in the authoritative `.up.sql` files.
<!-- GENERATED_BODY_SHA256: 77200fb20a4cb259d74a5b55220208bc61d4d5c1e9a92de954d02e8b1978638a -->
