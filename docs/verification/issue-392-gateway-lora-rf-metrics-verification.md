# Verification Report: Issue #392 — Gateway LoRa RF Metrics Publication

**Date:** 2026-11-14  
**Base Commit:** `d9c09cbae3cc8244744b5163d88541ef6f39f8be`  
**Branch:** `feature/392-gw-rf-metrics`  
**Authority:** Issue #392, Semtech SX1276 Datasheet §5.5.5, ADR-0004 (Event-driven CAD/CSMA-CA, Gateway Continuous RX), C Coding Standard v2 (Owner #137).

---

## 1. Scope & Allowed Paths

All changes are strictly confined to authorized directories for Issue #392:
- `firmware/components/sx1276_driver/`
- `firmware/gateway_master/components/gateway_radio_bridge/`
- `firmware/gateway_master/components/gateway_liveness/`
- `firmware/gateway_master/components/gateway_wal/`
- `firmware/components/gateway_transport/`
- `contracts/mqtt/`
- `contracts/tests/`, `tests/contract/`, `tests/unit/`, `docs/verification/`
- `deploy/mosquitto/acl`

---

## 2. Requirements & Implementations

### 2.1 Radio Owner RF Math & Negative SNR Rounding (RAD-001, RAD-002, RF-05)
- **SX1276 Registers Read:**
  - `RegPktSnrValue` (0x19): signed 2's complement raw value, representing quarter-dB SNR (`snr_db = raw / 4.0`, 0.25 dB resolution).
  - `RegPktRssiValue` (0x1A): unsigned raw packet RSSI indicator.
  - `RegRssiValue` (0x1B): instantaneous channel RSSI.
- **HF RSSI Calculation & Symmetric Nearest-Integer Rounding:**
  - For High Frequency band (> 525 MHz, active profile VN920): HF offset = `-157`.
  - When raw SNR $\ge 0$:
    $$\text{RSSI}_{\text{dBm}} = -157 + \text{RegPktRssi}$$
  - When raw SNR $< 0$:
    $$\text{RSSI}_{\text{dBm}} = -157 + \text{RegPktRssi} + \frac{\text{snr} - 2}{4}$$
    Using C integer arithmetic `(snr - 2) / 4` provides symmetric nearest-integer rounding towards the nearest integer (e.g. raw $-31 \to -7.75\text{ dB} \to -8\text{ dBm}$ correction).
  - Zero SNR ($0\text{ dB}$) is valid and handled without division error.
- **Fail-Closed SPI Reads:**
  - All SPI register reads check return codes. Any SPI failure aborts packet processing cleanly and never emits fabricated or zeroed pseudo-measurements.
- **Serialized Channel RSSI Sampling:**
  - `sx1276_read_channel_rssi()` delegates to the serialized Radio Owner task via `SX1276_CMD_READ_CHANNEL_RSSI`.
  - Rejects execution if modem state is not in continuous RX (`SX1276_STATE_RXCONT` / `RXSINGLE`). Fails closed in TX/SLEEP/STANDBY modes.
  - No direct SPI calls from ISR or timer callbacks (adheres to RTOS-003, RTOS-005).

### 2.2 Alert Payload RF Extension (RF-07)
- Extended `alert.schema.json` with an optional top-level `rf` object containing:
  - `channel_idx` (0..10)
  - `gateway_epoch` (UUID string)
  - `sample_seq` (decimal string)
  - `rx_monotonic_us` (decimal string)
  - `rssi_dbm` (integer -157..0)
  - `snr_db` (number -50.0..50.0)
- Buffer overflow protection: `snprintf` return check ensures `alert_len < sizeof(alert_payload)`. Truncated JSON is rejected fail-closed.
- Enqueue failures to MQTT transport are logged with `ESP_LOGW`.

### 2.3 Independent RF Metrics MQTT Topic (RF-01, RF-02, RF-03, RF-04)
- **Topic:** `iot/v1/gw/{gateway_id}/uplink/rf-metrics` (QoS 1, retain false).
- **Schema:** `contracts/mqtt/schemas/rf-metrics.schema.json` supporting:
  - `NODE_UPLINK`: `node_id`, `rssi_dbm`, `snr_db`, `source`, `validation` / `auth_provenance`.
  - `CHANNEL`: `channel_rssi_dbm`, `sample_context` (`RX_IDLE`, `RX_ACTIVE`).
  - Batching: `samples` array containing mixed node and channel observations.
- **Provenance & Auth Invariants:**
  - `UP_EVENT` uplinks (verified via session key MIC): `validation="VERIFIED"`, `auth_provenance="MIC_VERIFIED"`.
  - `UP_HEARTBEAT_ACK` uplinks (unverified / CRC only): `validation="UNVERIFIED"`, `auth_provenance="UNVERIFIED_CRC_ONLY"`.
  - CRC is never conflated with cryptographic security.
- **Mosquitto ACL:** `deploy/mosquitto/acl` updated to grant `gw-a`, `gw-b` write permission and `backend` read permission on `uplink/rf-metrics`.

### 2.4 In-Memory WAL Event Identity Preservation (DEC-127-05)
- `gateway_wal_event_t` updated with:
  - `channel_idx`
  - `rx_monotonic_us`
  - `sample_seq`
- Ensures identical measurement identity across real-time alert and WAL offline replay.

---

## 3. Verification Test Evidence

### 3.1 Contract Schema & Semantic Rules Validation
- **Command:** `python3 contracts/tests/check_contracts.py`
- **Result:**
  ```text
  PASS RF-METRICS-NODE-UPLINK-VALID (schema=True)
  PASS RF-METRICS-CHANNEL-VALID (schema=True)
  PASS RF-METRICS-BATCH-VALID (schema=True)
  PASS RF-METRICS-INVALID-CHANNEL-IDX (schema=False)
  PASS RF-METRICS-INVALID-RSSI (schema=False)
  PASS ALERT-WITH-RF-VALID (schema=True)
  PASS ALERT-WITH-RF-INVALID-SNR (schema=False)
  PASS: 12 schemas, 40 MQTT cases, 18 WS cases, 15 REST operations
  ```
- **Exit Code:** `0`

### 3.2 Pytest Contract Suite
- **Command:** `python3 -m pytest tests/contract/`
- **Result:** `27 passed, 1 warning in 1.92s`
- **Exit Code:** `0`

### 3.3 Unit Tests (Driver Math, Alert Format, Schema Validation, Transport)
- **Command:** `python3 -m pytest tests/unit/`
- **Result:**
  - `test_gateway_rf_metrics.py`: 4 passed (raw SNR conversion, negative SNR nearest-integer rounding, alert schema with/without rf, rf-metrics schema validation).
  - `test_gateway_transport.py`: passed (includes `gateway_transport_publish_rf_metrics` bounds and queuing).
  - Total: `34 passed in 2.76s`
- **Exit Code:** `0`

### 3.4 Gateway Master Firmware Build
- **Toolchain:** Docker `espressif/idf:v6.1` (`sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c`)
- **Command:** `docker run --rm --network=none -v $(pwd):/workspace -w /workspace/firmware/gateway_master espressif/idf:v6.1 idf.py build`
- **Result:**
  ```text
  Successfully created ESP32 image.
  Generated /workspace/firmware/gateway_master/build/gateway_master.bin
  gateway_master.bin binary size 0xf68e0 bytes. Smallest app partition is 0x100000 bytes. 0x9720 bytes (4%) free.
  Project build complete.
  ```
- **Exit Code:** `0`

---

## 4. Quality Gates & Security Invariants

| Rule ID | Description | Status | Evidence |
|---|---|---|---|
| `SEC-001` | Parameter & bounds checking | PASS | `tests/unit/test_gateway_transport.py`, `tests/unit/test_gateway_rf_metrics.py` |
| `SEC-003` | CRC not treated as cryptographic auth | PASS | Heartbeat ACK marked `validation="UNVERIFIED"`, `auth_provenance="UNVERIFIED_CRC_ONLY"` |
| `MEM-001` | Zero dynamic heap allocation in fast path | PASS | Static buffers and static mutex used in `gateway_rf_metrics.c` |
| `MEM-002` | Bounded queues and buffers | PASS | Cache bounded to 32 nodes $\times$ 11 channels; fixed JSON buffers with overflow checks |
| `RTOS-001` | Single Radio Owner serializing SPI | PASS | All radio operations and channel RSSI reads routed through `sx1276_owner_task` |
| `RTOS-003` | No SPI or blocking in ISR / timer | PASS | Channel RSSI is called from task context; timer only triggers event / cadence |
| `RAD-002` | Serialized SPI modem transitions | PASS | Radio state machine validated before reading `RegRssiValue` |
| `RAD-008` | RSSI/SNR alone not regulatory proof | PASS | Documented as raw physical indicators, not calibrated noise floor |

---

## 5. Non-verified Items (Reserved Technical Owner Decisions)

- **Physical HIL / RF Over-The-Air Transmission:**
  Physical transmission on actual SX1276 hardware requires bench instruments (spectrum analyzer / SDR / RF chamber) and hardware-in-the-loop harness. Marked `NOT_VERIFIED (HIL/RF)` in accordance with AGENTS.md policy.
- **Backend Consumer Integration:**
  Subject to Issue #393 (Backend Go RF metrics ingest and persistence).
- **Human Technical Review:**
  Reserved for technical owner review prior to production deployment.
