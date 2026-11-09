-- Migration 000009: Drop TDMA schedule tables
-- Project: LoRa-P2P-Hybrid-TDMA-MVP
-- Authority: Issue #286 / Issue #276

DROP TABLE IF EXISTS schedule_migration_transactions CASCADE;
DROP TABLE IF EXISTS active_gateway_schedules CASCADE;
DROP TABLE IF EXISTS schedule_slots CASCADE;
DROP TABLE IF EXISTS schedules CASCADE;
