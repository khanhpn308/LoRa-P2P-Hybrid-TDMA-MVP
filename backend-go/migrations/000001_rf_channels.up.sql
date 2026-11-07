-- Migration 000001: RF Channels and Gateway Channel Allocations
-- Project: LoRa-P2P-Hybrid-TDMA-MVP
-- Authority: Issue #154 (Owner-approved VN920 exclusive channel allocation)

CREATE TABLE IF NOT EXISTS rf_channels (
    channel_id VARCHAR(16) PRIMARY KEY,
    channel_plan_version VARCHAR(32) NOT NULL DEFAULT 'VN920_V1',
    center_frequency_hz BIGINT NOT NULL,
    bandwidth_hz BIGINT NOT NULL DEFAULT 125000,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_rf_channels_freq_positive CHECK (center_frequency_hz > 0),
    CONSTRAINT chk_rf_channels_bw_positive CHECK (bandwidth_hz > 0)
);

-- Idempotent seed of exactly 11 approved VN920_V1 channels (CH00..CH10)
-- Frequencies in exact integer Hz: 920.250 MHz to 922.750 MHz in 250 kHz steps, BW 125 kHz
INSERT INTO rf_channels (channel_id, channel_plan_version, center_frequency_hz, bandwidth_hz, is_enabled)
VALUES
    ('CH00', 'VN920_V1', 920250000, 125000, TRUE),
    ('CH01', 'VN920_V1', 920500000, 125000, TRUE),
    ('CH02', 'VN920_V1', 920750000, 125000, TRUE),
    ('CH03', 'VN920_V1', 921000000, 125000, TRUE),
    ('CH04', 'VN920_V1', 921250000, 125000, TRUE),
    ('CH05', 'VN920_V1', 921500000, 125000, TRUE),
    ('CH06', 'VN920_V1', 921750000, 125000, TRUE),
    ('CH07', 'VN920_V1', 922000000, 125000, TRUE),
    ('CH08', 'VN920_V1', 922250000, 125000, TRUE),
    ('CH09', 'VN920_V1', 922500000, 125000, TRUE),
    ('CH10', 'VN920_V1', 922750000, 125000, TRUE)
ON CONFLICT (channel_id) DO UPDATE SET
    channel_plan_version = EXCLUDED.channel_plan_version,
    center_frequency_hz = EXCLUDED.center_frequency_hz,
    bandwidth_hz = EXCLUDED.bandwidth_hz,
    is_enabled = EXCLUDED.is_enabled,
    updated_at = CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS gateway_channel_allocations (
    id BIGSERIAL PRIMARY KEY,
    gateway_id VARCHAR(64) NOT NULL,
    channel_id VARCHAR(16) NOT NULL REFERENCES rf_channels(channel_id),
    status VARCHAR(16) NOT NULL DEFAULT 'ALLOCATED',
    request_id VARCHAR(128) NOT NULL,
    allocation_generation BIGINT NOT NULL DEFAULT 1,
    granted_by VARCHAR(64) NOT NULL,
    released_by VARCHAR(64),
    release_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    released_at TIMESTAMPTZ,
    CONSTRAINT chk_allocation_status CHECK (status IN ('ALLOCATED', 'RELEASED')),
    CONSTRAINT chk_allocation_generation_positive CHECK (allocation_generation > 0)
);

-- Invariant 1: Exclusive channel allocation across the deployment for active allocations.
-- Exactly one active gateway allocation per channel.
CREATE UNIQUE INDEX IF NOT EXISTS idx_exclusive_active_channel
    ON gateway_channel_allocations (channel_id)
    WHERE status = 'ALLOCATED';

-- Invariant 2: Single SX1276 radio per gateway.
-- Exactly one active channel allocation per gateway.
CREATE UNIQUE INDEX IF NOT EXISTS idx_exclusive_active_gateway
    ON gateway_channel_allocations (gateway_id)
    WHERE status = 'ALLOCATED';

-- Monotonic channel generation tracking
CREATE UNIQUE INDEX IF NOT EXISTS idx_allocations_channel_generation
    ON gateway_channel_allocations (channel_id, allocation_generation);

-- Idempotency lookup by gateway and request_id
CREATE INDEX IF NOT EXISTS idx_allocations_gateway_request
    ON gateway_channel_allocations (gateway_id, request_id);
