-- Migration 000004 Rollback: TDMA Schedule Storage
-- Project: LoRa-P2P-Hybrid-TDMA-MVP
-- Authority: Issue #246

DROP TABLE IF EXISTS schedule_migration_transactions;
DROP TABLE IF EXISTS active_gateway_schedules;
DROP TABLE IF EXISTS schedule_slots;
DROP TABLE IF EXISTS schedules;
