-- Migration 000002: Device Registry, Device Generations, Join Counters & Join Transactions Idempotency
-- Project: LoRa-P2P-Hybrid-TDMA-MVP
-- Authority: Issue #214 / DEC-SEC-01 / DEC-SEC-06

-- 1. Device identity registry
CREATE TABLE IF NOT EXISTS devices (
    network_id BIGINT NOT NULL,
    device_mac BYTEA NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_devices PRIMARY KEY (network_id, device_mac),
    CONSTRAINT chk_device_mac_length CHECK (octet_length(device_mac) = 6),
    CONSTRAINT chk_device_status CHECK (status IN ('ACTIVE', 'SUSPENDED', 'REVOKED'))
);

-- 2. Device generations & key wrapping
CREATE TABLE IF NOT EXISTS device_generations (
    network_id BIGINT NOT NULL,
    device_mac BYTEA NOT NULL,
    generation INT NOT NULL DEFAULT 1,
    k_join_wrapped BYTEA NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_device_generations PRIMARY KEY (network_id, device_mac, generation),
    CONSTRAINT fk_device_generations_device FOREIGN KEY (network_id, device_mac)
        REFERENCES devices(network_id, device_mac) ON DELETE CASCADE,
    CONSTRAINT chk_device_generation_positive CHECK (generation >= 1 AND generation <= 65535),
    CONSTRAINT chk_k_join_wrapped_length CHECK (octet_length(k_join_wrapped) >= 32)
);

-- Invariant: Exactly one active generation per device
CREATE UNIQUE INDEX IF NOT EXISTS idx_device_single_active_generation
    ON device_generations (network_id, device_mac)
    WHERE is_active = TRUE;

-- 3. Monotonic join counter high-water tracking
CREATE TABLE IF NOT EXISTS device_join_counters (
    network_id BIGINT NOT NULL,
    device_mac BYTEA NOT NULL,
    generation INT NOT NULL,
    last_join_counter BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_device_join_counters PRIMARY KEY (network_id, device_mac, generation),
    CONSTRAINT fk_device_join_counters_gen FOREIGN KEY (network_id, device_mac, generation)
        REFERENCES device_generations(network_id, device_mac, generation) ON DELETE CASCADE,
    CONSTRAINT chk_last_join_counter_range CHECK (last_join_counter >= 0 AND last_join_counter <= 4294967295)
);

-- 4. Durable join transactions outbox & anti-replay idempotency log
CREATE TABLE IF NOT EXISTS join_transactions (
    id BIGSERIAL PRIMARY KEY,
    network_id BIGINT NOT NULL,
    device_mac BYTEA NOT NULL,
    generation INT NOT NULL,
    target_gw_id INT NOT NULL,
    join_counter BIGINT NOT NULL,
    status VARCHAR(48) NOT NULL DEFAULT 'HELLO_AUTHENTICATED_PENDING_GRANT',
    raw_hello_sha256 BYTEA NOT NULL,
    node_nonce BYTEA NOT NULL,
    node_x25519_pub BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_join_transactions_gen FOREIGN KEY (network_id, device_mac, generation)
        REFERENCES device_generations(network_id, device_mac, generation) ON DELETE CASCADE,
    CONSTRAINT chk_join_tx_mac_length CHECK (octet_length(device_mac) = 6),
    CONSTRAINT chk_join_tx_counter_valid CHECK (join_counter >= 1 AND join_counter <= 4294967294),
    CONSTRAINT chk_join_tx_gw_id CHECK (target_gw_id >= 1 AND target_gw_id <= 254),
    CONSTRAINT chk_join_tx_sha256_len CHECK (octet_length(raw_hello_sha256) = 32),
    CONSTRAINT chk_join_tx_nonce_len CHECK (octet_length(node_nonce) = 8),
    CONSTRAINT chk_join_tx_pub_len CHECK (octet_length(node_x25519_pub) = 32),
    CONSTRAINT chk_join_tx_status CHECK (status IN ('HELLO_AUTHENTICATED_PENDING_GRANT', 'GRANT_DISPATCHED', 'REJECTED'))
);

-- Invariant: Strict uniqueness (network_id, device_mac, generation, join_counter)
CREATE UNIQUE INDEX IF NOT EXISTS idx_join_transactions_unique_counter
    ON join_transactions (network_id, device_mac, generation, join_counter);

-- Index for lookup by raw_hello_sha256 for rapid idempotency deduplication
CREATE INDEX IF NOT EXISTS idx_join_transactions_lookup
    ON join_transactions (network_id, device_mac, generation, raw_hello_sha256);
