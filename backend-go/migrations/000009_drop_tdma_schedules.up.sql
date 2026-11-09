-- Migration 000009: Drop TDMA Schedules and Related Tables
-- Project: LoRa-P2P-Hybrid-TDMA-MVP
-- Authority: Issue #276 / ADR-0004 (Transition from Hybrid TDMA to Pure CAD + Random Backoff CSMA/CA)

DROP TABLE IF EXISTS schedule_migration_transactions CASCADE;
DROP TABLE IF EXISTS active_gateway_schedules CASCADE;
DROP TABLE IF EXISTS schedule_slots CASCADE;
DROP TABLE IF EXISTS schedules CASCADE;
DROP TABLE IF EXISTS tdma_schedules CASCADE;
