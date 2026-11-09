-- Migration 000008 Rollback
ALTER TABLE gateway_status ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE node_health ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_gateway_status_last_seen ON gateway_status (last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_node_health_last_seen ON node_health (last_seen_at DESC);
