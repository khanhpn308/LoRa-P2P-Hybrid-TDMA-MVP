-- Migration 000005: Gateways Registry
-- Authority: Issue #247 / openapi.yaml

CREATE TABLE IF NOT EXISTS gateways (
    gateway_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    location VARCHAR(128) NOT NULL DEFAULT 'Khu vực chung',
    ip_address VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seed default known gateways including gw-a so existing hardware is recognized
INSERT INTO gateways (gateway_id, name, location, ip_address) VALUES
    ('GW-01', 'Trạm điều hành GW-01', 'Khu A - Phân xưởng Ép', '192.168.88.110'),
    ('GW-02', 'Trạm bơm GW-02', 'Khu B - Trạm Bơm & Thủy lực', '192.168.88.111'),
    ('GW-03', 'Trạm ngoài trời GW-03', 'Khu C - Trạm Thu phát Ngoài trời', '192.168.88.112'),
    ('gw-a', 'Trạm điều hành gw-a', 'Phòng Thí nghiệm / Demo', '192.168.88.113')
ON CONFLICT (gateway_id) DO NOTHING;
