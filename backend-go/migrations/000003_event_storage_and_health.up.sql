-- Migration 000003: Discrete Event Storage, Idempotent Deduplication, Quarantine & Node Health
-- Project: LoRa-P2P-Hybrid-TDMA-MVP
-- Authority: Issue #18, Issue #125, DEC-127-01, DEC-MH-02, alert.schema.json, status.schema.json

-- 1. Discrete events table: durable idempotent event plane for UP_EVENT (0x41 26B)
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(128) NOT NULL,
    gateway_id VARCHAR(64) NOT NULL,
    gateway_epoch UUID NOT NULL,
    event_seq NUMERIC(20, 0) NOT NULL,
    node_id INT NOT NULL,
    superframe_seq BIGINT NOT NULL,
    seq_num INT NOT NULL,
    schedule_version BIGINT NOT NULL,
    severity VARCHAR(32) NOT NULL,
    observed_at TIMESTAMPTZ,
    observed_time_source VARCHAR(32) NOT NULL,
    radio_rx_monotonic_us NUMERIC(20, 0) NOT NULL,
    buffered BOOLEAN NOT NULL DEFAULT FALSE,
    radio_ack_sent BOOLEAN NOT NULL DEFAULT TRUE,
    event_ref BIGINT NOT NULL,
    event_code INT NOT NULL,
    event_value INT NOT NULL,
    -- Optional legacy columns retained as nullable for backward migration safety
    slot_id INT,
    sensor_status_mask INT,
    ch1_raw INT,
    ch2_raw INT,
    ch3_raw INT,
    battery_mv INT,
    node_duty_permille INT,
    trigger_channel INT,
    trigger_observed_raw INT,
    trigger_threshold_raw INT,
    raw_payload_sha256 BYTEA NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ack_status VARCHAR(32) NOT NULL DEFAULT 'UNACKNOWLEDGED',
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by VARCHAR(64),
    CONSTRAINT chk_events_node_id CHECK (node_id >= 1 AND node_id <= 254),
    CONSTRAINT chk_events_event_ref CHECK (event_ref >= 0 AND event_ref <= 4294967295),
    CONSTRAINT chk_events_event_code CHECK (event_code >= 0 AND event_code <= 255),
    CONSTRAINT chk_events_event_value CHECK (event_value >= -32768 AND event_value <= 32767),
    CONSTRAINT chk_events_severity CHECK (severity IN ('P0_EMERGENCY', 'P1_HIGH', 'P2_MEDIUM', 'P3_NORMAL')),
    CONSTRAINT chk_events_time_source CHECK (observed_time_source IN ('gateway_utc', 'node_utc', 'estimated', 'unknown')),
    CONSTRAINT chk_events_ack_status CHECK (ack_status IN ('UNACKNOWLEDGED', 'ACKNOWLEDGED')),
    CONSTRAINT chk_events_sha256_len CHECK (octet_length(raw_payload_sha256) = 32)
);

-- Invariant: Dedup key UNIQUE(gateway_id, event_id)
-- Prevents duplicate business records on QoS 1 retransmissions and concurrent replays.
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_gateway_event_id
    ON events (gateway_id, event_id);

-- Operational lookup indexes
CREATE INDEX IF NOT EXISTS idx_events_node_observed
    ON events (node_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_events_ingested_at
    ON events (ingested_at DESC);

-- 2. Event quarantine table: records conflicting replays, malformed envelopes, and unauthorized principals
CREATE TABLE IF NOT EXISTS event_quarantine (
    id BIGSERIAL PRIMARY KEY,
    gateway_id VARCHAR(64) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    conflict_reason VARCHAR(64) NOT NULL,
    expected_sha256 BYTEA,
    conflicting_sha256 BYTEA,
    raw_payload TEXT NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_quarantine_reason CHECK (conflict_reason IN (
        'CONFLICTING_PAYLOAD_HASH',
        'UNAUTHORIZED_GATEWAY_NODE',
        'MALFORMED_PAYLOAD',
        'SCHEMA_VALIDATION_FAILED'
    ))
);

CREATE INDEX IF NOT EXISTS idx_quarantine_gateway_event
    ON event_quarantine (gateway_id, event_id);

-- 3. Node health registry: records authenticated UP_HEALTH_REPLY (0x44 21B) status and FIFO pending depth
CREATE TABLE IF NOT EXISTS node_health (
    gateway_id VARCHAR(64) NOT NULL,
    node_id INT NOT NULL,
    session_sel INT NOT NULL,
    frame_counter BIGINT NOT NULL,
    maint_seq BIGINT NOT NULL,
    status_flags INT NOT NULL,
    pending_event_count INT NOT NULL,
    health_status VARCHAR(16) NOT NULL DEFAULT 'ONLINE',
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (gateway_id, node_id),
    CONSTRAINT chk_node_health_node_id CHECK (node_id >= 1 AND node_id <= 254),
    CONSTRAINT chk_node_health_status CHECK (health_status IN ('ONLINE', 'OFFLINE', 'UNKNOWN'))
);

CREATE INDEX IF NOT EXISTS idx_node_health_last_seen
    ON node_health (last_seen_at DESC);
