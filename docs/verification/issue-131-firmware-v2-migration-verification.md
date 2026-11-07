# Issue #131 Verification Report: Firmware V2 MAC Framing, Codecs, and Persistent Event FIFO

## 1. Executive Summary

This report documents the verification and compliance results for **Issue #131** (`[Migration][Firmware] Persistent Event queue, own-slot ACK retry and Maintenance execution (#125)`).
The firmware implementation delivers:
1. **Normative V2 Radio MAC Framing & Codecs** (`lora_mac.h`, `lora_mac.c`):
   - 7-octet unencrypted AAD Unicast Header (`lora_mac_v2_header_t`).
   - 13-octet AES-128-CCM nonce construction (`lora_mac_v2_build_nonce`) with 8-byte session prefix, 1-byte direction indicator (0x01 uplink, 0x02 downlink), and 4-byte big-endian monotonic frame counter.
   - Codecs for wire messages:
     - `UP_EVENT` (0x41, 11-byte plaintext payload / 26B total wire frame).
     - `DOWN_EVENT_ACK` (0x42, 4-byte plaintext payload / 19B total wire frame).
     - `DOWN_SYNC_BEACON` (0x43, 16-byte header + 16-byte HMAC tag = 32B total wire frame).
     - `UP_HEALTH_REPLY` (0x44, 6-byte plaintext payload / 21B total wire frame).
     - `UP_DIAG_METRICS` (0x4A, 8-byte plaintext payload / 23B total wire frame per DEC-MH-08).
   - Preserves superseded V1 framing for backwards compatibility.
2. **Bounded Node Persistent Event FIFO** (`node_event_fifo.h`, `node_event_fifo.c`):
   - Capacity of 16 events (`NODE_EVENT_FIFO_CAPACITY`).
   - Zero dynamic memory allocation (`MEM-001`).
   - Drop-oldest overflow strategy (`RING_BUFFER_DROP_OLDEST`) per Owner DEC-127-04.
   - Monotonic `event_ref` tracking, observable `dropped_event_count` retention across reboots/reconnects.
   - Retries tracked per event without mutating event identity or sensor reading.
   - Out-of-order ACK cascade handling.

## 2. Standards Compliance Matrix

| Rule ID | Requirement | Implementation Evidence | Status |
| :--- | :--- | :--- | :--- |
| **MEM-001** | Zero dynamic heap allocation in runtime path | Static ring buffer `items[NODE_EVENT_FIFO_CAPACITY]`, bounded stack buffers | PASS |
| **SEC-001** | Input bounds validation | Strict length validation (`< 7B`, `< 11B`, `< 4B`, etc.) before buffer reads | PASS |
| **SEC-002** | Type range checking | `ver_type` checked against `0x40..0x5F`, protocol version verified = 2 | PASS |
| **SEC-003** | Direction validation | Nonce builder strictly enforces `0x01` (uplink) or `0x02` (downlink) | PASS |
| **DEC-127-01**| Wire lengths and framing | Exact match to normative spec Table 3.2 | PASS |
| **DEC-127-02**| AES-128-CCM tag and nonce | 8-byte tag (CCM-8, M=8), 13-byte nonce (L=2) | PASS |
| **DEC-127-04**| Persistent event queue policy | Bounded ring buffer, drop-oldest, observable dropped count | PASS |
| **DEC-MH-08** | Diagnostic metrics codec | 8-byte payload: 4B dropped_event_count + 4B diag_seq | PASS |

## 3. Test Verification Results

### 3.1 Host C11 Strict Unit Tests (`test_firmware_v2_unit.py`)
Compiled with `gcc -Wall -Wextra -Werror -pedantic -std=c11`:
- `test_lora_mac_v2_header_roundtrip`: PASS
- `test_lora_mac_v2_header_negative`: PASS (NULL checks, short buffer, invalid version)
- `test_lora_mac_v2_build_nonce`: PASS (13-byte nonce layout, direction validation)
- `test_lora_mac_v2_up_event_roundtrip`: PASS (11B serialize/deserialize, negative temperature/sensor values)
- `test_lora_mac_v2_down_event_ack_roundtrip`: PASS (4B echo ref)
- `test_lora_mac_v2_up_health_reply_roundtrip`: PASS (6B battery/uptime/pending)
- `test_lora_mac_v2_up_diag_metrics_roundtrip`: PASS (8B metrics)
- `test_lora_mac_v2_beacon_roundtrip`: PASS (32B sync beacon + HMAC tag)
- `test_fifo_init`: PASS
- `test_fifo_push_and_peek`: PASS
- `test_fifo_ack_in_order`: PASS
- `test_fifo_ack_out_of_order`: PASS (head cascade behavior)
- `test_fifo_overflow_drop_oldest`: PASS (capacity 16, drops oldest on overflow, tracks dropped count)
- `test_fifo_retry_count`: PASS (monotonic retry count retention)
- `test_fifo_negative_and_bounds`: PASS

### 3.2 Regression Suites
- `tests/unit/test_lora_mac.py`: PASS (1/1)
- `tests/contract/test_radio_mac_timing_consistency.py`: PASS (12/12)

### 3.3 Hardware & Build Targets
- Target Toolchain: ESP-IDF v6.1 (Docker `espressif/idf:v6.1`).
- Target SoCs: ESP32-WROOM-32E + SX1276.
- Physical HIL Bench / RF Transmission: Gate G3 / RF HIL remains `NOT_VERIFIED` (requires bench board #169). No RF radiated.

