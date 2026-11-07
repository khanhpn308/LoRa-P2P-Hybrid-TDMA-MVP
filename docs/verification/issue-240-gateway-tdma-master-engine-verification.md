# Issue #240: Gateway Master V2 Static TDMA Master Engine Verification Dossier

- **Document ID:** `VERIFY-ISSUE-240-GATEWAY-TDMA-MASTER-ENGINE`
- **Issue Reference:** [#240: [Firmware][Gateway] V2 Static TDMA Master Engine (Beacon Broadcast & Slot 1..15 ACK Loop)](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/240)
- **Status:** `VERIFIED_PASS`
- **Component Target:** `firmware/gateway_master/`, `firmware/components/tdma_common/`, `tests/unit/`
- **Toolchain Target:** `ESP-IDF v6.1` (Official Docker `espressif/idf:v6.1`, digest `sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c`)
- **Authority:** DEC-127-01, DEC-127-02, DEC-127-03, DEC-127-05, DEC-127-06, DEC-MH-01, DEC-MH-02, DEC-MH-03, DEC-MH-06, DEC-MH-07, DEC-MH-08, D12 §6.3, ADR-0003, C Coding Standard v2.

---

## 1. Overview and Architecture

In accordance with Owner-approved decisions for the Event-Only Hybrid TDMA system, the Gateway Master TDMA Engine operates as the authoritative local coordinator for high-resolution slot scheduling, broadcast synchronization, and immediate in-slot event acknowledgments on ESP-IDF v6.1.

The Master TDMA Engine operates under deterministic timing and fail-closed constraints:
1. **High-Resolution Master Epoch Loop:** Driven by high-resolution hardware timers (`esp_timer`) to establish recurring 10-second superframe reference epochs. Timer callbacks execute non-blocking FreeRTOS task notifications (`RTOS-001`, `RTOS-005`).
2. **Beacon Broadcast (`DOWN_SYNC_BEACON` 0x43):** Transmits a 32-octet HMAC-SHA256-128 Beacon frame at the start of each superframe under the provisioned 256-bit `K_BEACON` (`DEC-MH-01`, `DEC-MH-07`). Evaluates Gateway regulatory airtime policy (`airtime_policy_check()`, $\le 10.0\%$, `RAD-001`) prior to RF emission; suppresses Beacon emission fail-closed on budget exhaustion.
3. **Half-Duplex Turnaround Guard:** Enforces safe radio state transitions and turnaround guard time (`DEC-MH-06`) between TX Beacon and the start of Slot 1 RX.
4. **Static DATA Slot Reception (Slots 1..15):** Synchronizes 15 dedicated DATA slots (600ms duration each, offset = $\text{slot\_index} \times 600\text{ms}$). Opens continuous RX mode during the 500ms usable window (`DEC-127-03`, `DEC-127-06`) for assigned $\text{Node ID} = \text{Slot Index}$.
5. **Decryption and Authentication:** Parses 7-byte unencrypted AAD unicast header, enforces anti-replay frame counter monotonicity, resolves node active session keys from `session_key_store`, and verifies AES-128-CCM-8 tag (`DEC-127-01`, `DEC-127-02`). Corrupted packets or tag mismatches are rejected cleanly without ACK emission and without buffer modification.
6. **Bounded Uplink WAL Commit:** Verified event intent is committed into a bounded in-memory Write-Ahead Log (`gateway_wal_t`) prior to emitting the ACK (`DEC-127-05`). Enforces zero dynamic heap allocation (`MEM-001`) and monotonic drop counter tracking on ring buffer overflow (`D12 §6.3`).
7. **Immediate In-Slot ACK Loop:** Prepares and emits `DOWN_EVENT_ACK` (0x42, 19B) under $K_{\text{SESSION\_DL}}$ with unique downlink nonce direction `0x02` within the 500ms slot window.
8. **Slot Idle Advancement:** On slot timeout (no transmission from Node), closes RX, switches transceiver to STANDBY, advances slot pointer cleanly, records slot idle metric, and guarantees zero stray TX.
9. **Maintenance Superframe Management:** Recurrently (~300s per `DEC-MH-03`, every 30 superframes), coordinates maintenance slots for `UP_HEALTH_REPLY` (0x44, 21B) and `UP_DIAG_METRICS` (0x4A, 23B), validating drop counters and diagnostic sequence numbers per `DEC-MH-08`.

---

## 2. State Machine Transitions

| State | Event / Trigger | Next State | Action / Consequence |
|---|---|---|---|
| `GW_TDMA_STATE_IDLE` | Superframe epoch trigger (`esp_timer`) | `BEACON_TX` | Record epoch timestamp, evaluate maintenance cadence |
| `GW_TDMA_STATE_BEACON_TX` | `airtime_policy_check() == OK` | `BEACON_GUARD` | Compute HMAC-SHA256-128, emit Beacon 0x43 (32B), record airtime |
| `GW_TDMA_STATE_BEACON_TX` | Duty cycle budget exhausted | `BEACON_GUARD` | Suppress Beacon emission fail-closed, increment `beacon_blocked_count` |
| `GW_TDMA_STATE_BEACON_GUARD` | Turnaround elapsed $\to$ Slot 1 usable start | `SLOT_RX` | Transition SX1276 to STANDBY, align to Slot 1 usable window |
| `GW_TDMA_STATE_SLOT_RX` | Usable window open | `SLOT_PROCESS` | Open continuous RX, await packet or slot timeout |
| `GW_TDMA_STATE_SLOT_PROCESS` | Slot timeout (no frame received) | `SLOT_ADVANCE` | Close RX, switch to STANDBY, increment `slot_idle_count`, 0 stray TX |
| `GW_TDMA_STATE_SLOT_PROCESS` | Corrupt packet / invalid header / tag mismatch | `SLOT_ADVANCE` | Close RX, increment `corrupted_mic_count`, reject cleanly, 0 ACK, 0 WAL write |
| `GW_TDMA_STATE_SLOT_PROCESS` | Valid `UP_EVENT` (tag OK, ref OK) | `SLOT_ACK_TX` | Commit to bounded WAL, update replay counter, prepare `DOWN_EVENT_ACK` |
| `GW_TDMA_STATE_SLOT_ACK_TX` | `airtime_policy_check() == OK` | `SLOT_ADVANCE` | Encrypt ACK (0x42, 19B, dir=0x02), emit RF TX in slot, record airtime |
| `GW_TDMA_STATE_SLOT_ACK_TX` | Gateway airtime exhausted | `SLOT_ADVANCE` | Suppress ACK gracefully, increment `airtime_blocked_ack_count` |
| `GW_TDMA_STATE_SLOT_ADVANCE` | `slot < slot_count` | `SLOT_RX` | Advance to next slot boundary ($(\text{slot}+1) \times 600\text{ms}$) |
| `GW_TDMA_STATE_SLOT_ADVANCE` | `slot == slot_count` | `SUPERFRAME_COMPLETE` | Increment `superframe_seq++`, return to `IDLE` |

---

## 3. Mandatory C Coding Standard v2 Compliance

| Rule ID | Category | Requirement | Implementation Evidence |
|---|---|---|---|
| `GOV-001` | Governance | Exact issue allowlist | Edits strictly bounded to allowed paths (`firmware/gateway_master/`, `firmware/components/tdma_common/`, `tests/unit/`, `docs/verification/`) |
| `GOV-002` | Governance | No out-of-scope edits | Confirmed zero edits to contracts, backends, radio driver, or sensor node |
| `MEM-001` | Memory Safety | Zero dynamic memory allocation | Static FreeRTOS task, static WAL ring buffer (`gateway_wal_t`), static queues, stack-based crypto buffers |
| `MEM-002` | Memory Safety | Bounded ring buffers | `GATEWAY_WAL_CAPACITY = 64`, monotonic `overflow_dropped_count` per D12 §6.3 |
| `MEM-004` | Memory Safety | Strict stack limits | Tasks operate with statically allocated `GATEWAY_TASK_STACK_WORDS (2048 words)` |
| `MEM-005` | Memory Safety | Zeroize uninitialized structures | Explicit `memset(0)` across all structures on init (`gateway_wal_init`, `gateway_tdma_init`) |
| `ERR-001` | Error Handling | Check all return codes | All `esp_err_t` returns checked with `ESP_ERROR_CHECK` or handled fail-closed |
| `ERR-002` | Error Handling | Fail-closed on corrupted frame/MIC | Mismatched tag or invalid header rejects packet cleanly without ACK or WAL commit |
| `ERR-003` | Error Handling | Safe cleanup on lockup | Explicit radio standby transitions on timeouts or error branches |
| `RTOS-001`| Concurrency | Non-blocking timer callbacks | `gateway_epoch_timer_cb` performs single `vTaskNotifyGiveFromISR()` |
| `RTOS-002`| Concurrency | Mutex/serialized radio owner | Radio owner task serialized SPI interactions through `sx1276_driver` API |
| `RTOS-003`| Concurrency | Deterministic timeouts | Bounded timeouts on all radio read/write and task wait calls |
| `RTOS-005`| Concurrency | Static FreeRTOS tasks | `xTaskCreateStatic()` used for Gateway TDMA master task |
| `MAC-001` | Protocol | Strict V2 header validation | Parsed with `lora_mac_v2_header_parse()`, validates version (2), type (0x41/0x42/0x44/0x4A) |
| `MAC-002` | Protocol | Enforce 600ms slot boundaries | Exact $W=500\text{ms}$ usable window and $G=50\text{ms}$ guards enforced per DEC-127-03 |
| `RAD-001` | Radio | Gateway $\le 10.0\%$ duty cycle | `airtime_policy_init(100)` configured; pre-transmit checks enforce limits |
| `RAD-002` | Radio | Fail-closed standby default | Radio defaulted to STANDBY mode upon idle, errors, or timeouts |
| `SEC-001` | Security | Safe key isolation | Node session keys resolved per node ID; keys zeroized after use |
| `SEC-004` | Security | Unique downlink nonces | Downlink nonces strictly formatted with direction `0x02` and monotonic counter |
| `SEC-005` | Security | Zeroize sensitive buffers | Sensitive key/crypto buffers zeroized with `gateway_crypto_zeroize()` |

---

## 4. Test Execution Receipts

### 4.1 Host Unit Test Execution (`tests/unit/test_gateway_tdma_engine.c`)
- **Execution Command:**
  ```bash
  gcc -Wall -Wextra -Werror -pedantic -std=c11 \
      -I firmware/components/lora_mac/include \
      -I firmware/components/tdma_common/include \
      -I firmware/components/airtime_policy/include \
      -I firmware/gateway_master/main \
      -I tests/unit/mock_esp \
      firmware/components/lora_mac/src/lora_mac.c \
      firmware/components/lora_mac/src/node_event_fifo.c \
      firmware/components/tdma_common/src/tdma_common.c \
      firmware/components/airtime_policy/src/airtime_policy.c \
      firmware/gateway_master/main/gateway_wal.c \
      firmware/gateway_master/main/gateway_crypto.c \
      firmware/gateway_master/main/gateway_tdma_master.c \
      tests/unit/test_gateway_tdma_engine.c \
      -o /tmp/test_gateway_tdma_engine && /tmp/test_gateway_tdma_engine
  ```
- **Execution Output:**
  ```text
  ============================================================
  Running Gateway TDMA Master Engine Unit Tests (Issue #240)
  ============================================================
  Running test_crypto_operations_roundtrip ... PASSED
  Running test_wal_buffer_bounded_overflow ... PASSED
  Running test_superframe_beacon_broadcast ... PASSED
  Running test_slot_idle_advancement_zero_stray_tx ... PASSED
  Running test_up_event_valid_receipt_wal_commit_in_slot_ack ... PASSED
  Running test_corrupted_mic_and_invalid_header_rejection ... PASSED
  Running test_airtime_exhaustion_suppression ... PASSED
  Running test_maintenance_superframe_management ... PASSED
  Running test_tdma_v2_timing_boundaries ... PASSED
  ============================================================
  All Gateway TDMA Master Engine unit tests PASSED successfully!
  ============================================================
  ```
- **Exit Code:** `0`

### 4.2 Python Test Runner (`tests/unit/test_firmware_v2_unit.py`)
- **Execution Command:**
  ```bash
  python3 -m unittest tests/unit/test_firmware_v2_unit.py
  ```
- **Execution Output:**
  ```text
  ...
  ----------------------------------------------------------------------
  Ran 3 tests in 0.699s

  OK
  ```
- **Exit Code:** `0`

### 4.3 ESP-IDF v6.1 Docker Compilation
- **Target Image:** `espressif/idf:v6.1` (`sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c`)
- **Gateway Master Build Command:**
  ```bash
  docker run --rm --network=none -v $(pwd):/project -w /project/firmware/gateway_master espressif/idf:v6.1 idf.py build
  ```
  - Result: `gateway_master.bin` binary size `0x498b0` bytes. App partition `0x100000` bytes, `0xb6750` bytes (71%) free.
  - Exit Code: `0`
- **Sensor Node Build Command:**
  ```bash
  docker run --rm --network=none -v $(pwd):/project -w /project/firmware/sensor_node espressif/idf:v6.1 idf.py build
  ```
  - Result: `sensor_node.bin` binary size `0x31d20` bytes. App partition `0x100000` bytes, `0xce2e0` bytes (81%) free.
  - Exit Code: `0`

---

## 5. Acceptance Criteria Verification Matrix

| Acceptance Criterion | Verification Method | Result | Evidence |
|---|---|:---:|---|
| Gateway TDMA Master Engine implemented cleanly in `firmware/gateway_master/` | Source inspection, Docker ESP-IDF build | **PASS** | `gateway_tdma_master.c/.h`, `gateway_wal.c/.h`, `gateway_crypto.c/.h`, `main.c` |
| Superframe epoch trigger $\to$ Beacon 0x43 emission with valid HMAC | Unit Test `test_superframe_beacon_broadcast` | **PASS** | 32-octet Beacon emitted, HMAC-SHA256 verified |
| Slot 1..15 RX window open $\to$ valid `UP_EVENT` (0x41) receipt $\to$ WAL commit $\to$ immediate `DOWN_EVENT_ACK` (0x42) within 500ms window | Unit Test `test_up_event_valid_receipt_wal_commit_in_slot_ack` | **PASS** | WAL event committed, 19B ACK emitted, ref echoed correctly |
| Slot idle timeout advances slot pointer with 0 stray TX | Unit Test `test_slot_idle_advancement_zero_stray_tx` | **PASS** | `slot_idle_count == 15`, stray TX == 0 |
| Corrupted MIC / invalid header rejects cleanly without ACK emission and without buffer modification | Unit Test `test_corrupted_mic_and_invalid_header_rejection` | **PASS** | `corrupted_mic_count == 1`, ACK sent == 0, WAL count == 0 |
| Gateway airtime budget exhaustion blocks Beacon/ACK emissions gracefully | Unit Test `test_airtime_exhaustion_suppression` | **PASS** | `beacon_blocked_count == 1`, `airtime_blocked_ack_count == 1`, TX count == 0 |
| Bounded WAL buffer overflow increments drop counter without memory leak or crash | Unit Test `test_wal_buffer_bounded_overflow` | **PASS** | Drops oldest 5 events, increments drop count to 5 |
| ESP-IDF v6.1 Docker compilation succeeds with 0 errors for `gateway_master` and `sensor_node` | Docker build `espressif/idf:v6.1` | **PASS** | Both builds exit code 0 |
| Scope and secret scan checks pass without violations | Quality gates and diff check | **PASS** | Edits bounded strictly to allowed paths |
| Verification dossier delivered | Documentation inspection | **PASS** | `docs/verification/issue-240-gateway-tdma-master-engine-verification.md` |

---

## 6. Gate Status and Human Decisions Reserved

- `AUTO_CHECK_PASS`: **PASS** (100% of master engine unit tests pass, ESP-IDF v6.1 Docker builds pass).
- `SECRET_SCAN_PASS`: **PASS** (Zero production private keys committed; only standard RFC/FIPS test keys).
- `SECURITY_REVIEW_PASS`: **PENDING_HUMAN_REVIEW** (Radio scheduling, cryptographic nonce uniqueness, and master TDMA state transitions require expert human review per `ai:human-audit-req`).
- `HIL_RF_PASS`: **NOT_VERIFIED** (Microsecond hardware timer latency and physical SX1276 RF airtime require bench instrumentation bring-up).
