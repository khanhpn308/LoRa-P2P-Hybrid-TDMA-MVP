-- Migration 000003: Revert Discrete Event Storage, Quarantine & Node Health
-- Project: LoRa-P2P-Hybrid-TDMA-MVP
-- Authority: Issue #18, Issue #232, UP_EVENT 0x41

DROP TABLE IF EXISTS node_health CASCADE;
DROP TABLE IF EXISTS event_quarantine CASCADE;
DROP TABLE IF EXISTS events CASCADE;
