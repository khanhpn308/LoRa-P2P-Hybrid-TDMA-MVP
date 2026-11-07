-- Migration 000001 Rollback: RF Channels and Gateway Channel Allocations
-- Project: LoRa-P2P-Hybrid-TDMA-MVP
-- Authority: Issue #154 (Owner-approved VN920 exclusive channel allocation)

DROP TABLE IF EXISTS gateway_channel_allocations CASCADE;
DROP TABLE IF EXISTS rf_channels CASCADE;
