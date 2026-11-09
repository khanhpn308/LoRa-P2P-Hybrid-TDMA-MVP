-- Migration 000008: Drop last_seen_at from database tables (Presence moved to in-memory)
-- Project: LoRa-P2P-Hybrid-TDMA-MVP

DROP INDEX IF EXISTS idx_gateway_status_last_seen;
DROP INDEX IF EXISTS idx_node_health_last_seen;

ALTER TABLE gateway_status DROP COLUMN IF EXISTS last_seen_at;
ALTER TABLE node_health DROP COLUMN IF EXISTS last_seen_at;
