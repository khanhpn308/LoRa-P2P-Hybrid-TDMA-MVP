-- Migration 000007: Device Join Requests for Admin Approval Flow
CREATE TABLE IF NOT EXISTS device_join_requests (
    id BIGSERIAL PRIMARY KEY,
    device_mac VARCHAR(12) NOT NULL,
    gateway_id VARCHAR(64) NOT NULL,
    rssi INT DEFAULT 0,
    snr NUMERIC(5, 2) DEFAULT 0.0,
    raw_frame_hex TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    assigned_node_id INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_join_req_status CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED'))
);

CREATE INDEX IF NOT EXISTS idx_device_join_requests_status
    ON device_join_requests (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_device_join_requests_mac
    ON device_join_requests (device_mac);
