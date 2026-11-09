-- Migration 000009 Rollback: Re-create TDMA Schedule Storage Tables
-- Project: LoRa-P2P-Hybrid-TDMA-MVP
-- Authority: Issue #276 / Issue #246

-- 1. Schedules table
CREATE TABLE IF NOT EXISTS schedules (
    schedule_id VARCHAR(20) PRIMARY KEY,
    gateway_id VARCHAR(64) NOT NULL,
    network_id BIGINT NOT NULL DEFAULT 1,
    schedule_version BIGINT NOT NULL,
    schedule_generation BIGINT NOT NULL DEFAULT 1,
    channel_id VARCHAR(16) NOT NULL REFERENCES rf_channels(channel_id),
    profile_id VARCHAR(32) NOT NULL,
    superframe_ms INTEGER NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'PROPOSED',
    review_state VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    reject_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_schedule_id_pattern CHECK (schedule_id ~ '^(0|[1-9][0-9]{0,19})$'),
    CONSTRAINT chk_schedule_version_range CHECK (schedule_version >= 0 AND schedule_version <= 4294967295),
    CONSTRAINT chk_schedule_generation_positive CHECK (schedule_generation > 0),
    CONSTRAINT chk_superframe_ms CHECK (superframe_ms IN (9000, 10000)),
    CONSTRAINT chk_schedule_state CHECK (state IN ('PROPOSED', 'SENT', 'STAGED', 'ACTIVE', 'REJECTED', 'EXPIRED')),
    CONSTRAINT chk_schedule_review_state CHECK (review_state IN ('PENDING', 'APPROVED', 'REJECTED'))
);

CREATE INDEX IF NOT EXISTS idx_schedules_gateway_version
    ON schedules (gateway_id, schedule_version DESC);

-- 2. Schedule slots
CREATE TABLE IF NOT EXISTS schedule_slots (
    schedule_id VARCHAR(20) NOT NULL REFERENCES schedules(schedule_id) ON DELETE CASCADE,
    slot_id INTEGER NOT NULL CHECK (slot_id >= 1 AND slot_id <= 15),
    node_id INTEGER NOT NULL CHECK (node_id >= 1 AND node_id <= 254),
    offset_ms INTEGER NOT NULL CHECK (offset_ms >= 0 AND offset_ms <= 10000),
    duration_ms INTEGER NOT NULL CHECK (duration_ms IN (400, 500)),
    PRIMARY KEY (schedule_id, slot_id)
);

CREATE INDEX IF NOT EXISTS idx_schedule_slots_node
    ON schedule_slots (schedule_id, node_id);

-- 3. Active gateway schedules (Invariant: 1 active schedule per gateway)
CREATE TABLE IF NOT EXISTS active_gateway_schedules (
    gateway_id VARCHAR(64) PRIMARY KEY,
    schedule_id VARCHAR(20) NOT NULL REFERENCES schedules(schedule_id),
    schedule_version BIGINT NOT NULL,
    schedule_generation BIGINT NOT NULL,
    channel_id VARCHAR(16) NOT NULL REFERENCES rf_channels(channel_id),
    activated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    superframe_seq BIGINT NOT NULL,
    CONSTRAINT chk_active_version_range CHECK (schedule_version >= 0 AND schedule_version <= 4294967295),
    CONSTRAINT chk_active_superframe_seq CHECK (superframe_seq >= 0 AND superframe_seq <= 4294967295)
);

-- 4. Schedule migration transactions
CREATE TABLE IF NOT EXISTS schedule_migration_transactions (
    transaction_id VARCHAR(128) PRIMARY KEY,
    gateway_id VARCHAR(64) NOT NULL,
    schedule_id VARCHAR(20) NOT NULL REFERENCES schedules(schedule_id),
    schedule_generation BIGINT NOT NULL,
    k_target BIGINT NOT NULL,
    state VARCHAR(32) NOT NULL,
    state_reason TEXT NOT NULL,
    prepare_digest BYTEA NOT NULL,
    prepare_frame BYTEA NOT NULL,
    decision_type SMALLINT,
    decision_frame BYTEA,
    affected_nodes INTEGER[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_tx_prepare_digest_len CHECK (octet_length(prepare_digest) = 32),
    CONSTRAINT chk_tx_prepare_frame_len CHECK (octet_length(prepare_frame) = 80),
    CONSTRAINT chk_tx_decision_frame_len CHECK (decision_frame IS NULL OR octet_length(decision_frame) = 80),
    CONSTRAINT chk_tx_state CHECK (state IN ('DRAFT', 'PREPARED', 'STAGED', 'COLLECTING_READY', 'READY_COMPLETE', 'COMMITTED', 'ABORTED', 'ACTIVE', 'SUPERSEDED'))
);

CREATE INDEX IF NOT EXISTS idx_migration_tx_gateway_sched
    ON schedule_migration_transactions (gateway_id, schedule_id);
