-- Migration 000004: Gateway Status Table
-- Project: LoRa-P2P-Hybrid-TDMA-MVP
-- Authority: Issue #247 / openapi.yaml / status.schema.json / DEC-MH-02 / DEC-MH-08 / Issue #154

CREATE TABLE IF NOT EXISTS gateway_status (
    gateway_id VARCHAR(64) PRIMARY KEY,
    gateway_epoch UUID NOT NULL,
    mode VARCHAR(32) NOT NULL,
    active_schedule_version BIGINT NOT NULL DEFAULT 0,
    channel_id VARCHAR(16),
    rf_duty_permille INT NOT NULL DEFAULT 0,
    node_count INT NOT NULL DEFAULT 0,
    free_heap_bytes BIGINT NOT NULL DEFAULT 0,
    offline_queue_count INT NOT NULL DEFAULT 0,
    pending_event_count INT NOT NULL DEFAULT 0,
    dropped_event_count NUMERIC(20, 0) NOT NULL DEFAULT 0,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_gateway_status_mode CHECK (mode IN ('BOOTSTRAP', 'ACTIVE', 'AUTONOMOUS', 'RECOVERY', 'FAULT', 'OFFLINE')),
    CONSTRAINT chk_gateway_status_duty CHECK (rf_duty_permille >= 0 AND rf_duty_permille <= 1000),
    CONSTRAINT chk_gateway_status_nodes CHECK (node_count >= 0 AND node_count <= 254),
    CONSTRAINT chk_gateway_status_pending CHECK (pending_event_count >= 0 AND pending_event_count <= 255),
    CONSTRAINT chk_gateway_status_dropped CHECK (dropped_event_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_gateway_status_last_seen ON gateway_status (last_seen_at DESC);
