# Issue #239: Sensor Node V2 Static TDMA Slot Client & Event Loop Verification Dossier

- **Document ID:** `VERIFY-ISSUE-239-NODE-TDMA-SLOT-CLIENT`
- **Issue Reference:** [#239: [Firmware][Node] V2 Static TDMA Slot Client & Event Transmission Loop](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/239)
- **Status:** `VERIFIED_PASS`
- **Component Target:** `firmware/sensor_node/`, `firmware/components/lora_mac/`
- **Toolchain Target:** `ESP-IDF v6.1` (Official Docker `espressif/idf:v6.1`, digest `sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c`)
- **Authority:** DEC-127-01, DEC-127-02, DEC-127-03, DEC-127-06, DEC-127-04, DEC-MH-01, DEC-MH-04, DEC-MH-07, DEC-EVENT-01, DEC-NODE-01, ADR-0003, C Coding Standard v2.

---

## 1. Overview and Architecture

In accordance with Owner-approved decisions for the Event-Only Hybrid TDMA system, the Sensor Node does not emit periodic application telemetry or utilize contention slots for data. Instead, events enqueued in the persistent event ring buffer (`node_event_fifo`) from physical button triggers are transmitted exclusively in the Node's assigned **Static DATA Slot** ($1 \le \text{Slot Index} = \text{Node ID} \le 15$).

The transmission loop operates under strict fail-closed constraints:
1. **Beacon Synchronization:** Listens for Gateway `DOWN_SYNC_BEACON` (0x43, 32B), validating its HMAC-SHA256-128 tag with provisioned `K_BEACON` and enforcing anti-replay on `sf_seq`.
2. **Deterministic Slot Boundary:** Aligns local clock to Beacon arrival and calculates assigned slot boundaries:
   $$\text{Offset} = \text{Beacon Window} + (\text{Node ID} - 1) \times 600\text{ ms} + 50\text{ ms (leading guard)}$$
3. **Airtime Regulatory Gate:** Queries `airtime_policy_check()` prior to emission; suppresses TX fail-closed if duty cycle budget is exhausted.
4. **Encrypted Wire Transmission:** Builds `UP_EVENT` (0x41, 26B, 7B AAD header + 11B ciphertext + 8B CCM-8 tag) under $K_{\text{SESSION\_UP}}$ using V2 nonce (direction byte `0x01` and monotonic frame counter).
5. **Immediate In-Slot Acknowledgment:** Switches SX1276 to RX within the 500 ms slot window, awaits `DOWN_EVENT_ACK` (0x42, 19B), verifies CCM-8 tag under $K_{\text{SESSION\_DOWN}}$, and checks echoed `event_ref`.
6. **FIFO Pop or Retry:** On valid ACK, calls `node_event_fifo_pop()` and commits the monotonic frame counter. On timeout or corrupt ACK, records retry on FIFO head and retains event for the next superframe.
7. **Beacon Loss & Clock Drift Lock:** If consecutive missed Beacons $N_{\text{MISSED}} > 3$, marks state as `DISCONNECTED` and inhibits all DATA TX emissions (`DEC-MH-04`). If estimated crystal drift exceeds 50 ms guard, TX is suppressed until fresh Beacon synchronization.
8. **Low-Power Deep-Sleep Return:** Transitions SX1276 to SLEEP mode, arms EXT0 wakeup on button GPIO, and enters ESP32 deep-sleep.

---

## 2. State Machine Transitions

| Current State | Event / Condition | Next State | Action / Consequence |
|---|---|---|---|
| `DEEP_SLEEP` | Wakeup (Button EXT0 or Timer) | `WAKE_CHECK` | Increment boot count, initialize drivers |
| `WAKE_CHECK` | Always | `FIFO_EVAL` | Inspect persistent RTC FIFO depth |
| `FIFO_EVAL` | `pending_count == 0` | `REARM_SLEEP` | Sleep radio, arm EXT0, enter deep-sleep |
| `FIFO_EVAL` | `pending_count > 0` & disconnected | `DISCONNECTED` | Lock DATA TX, retain event, go to sleep |
| `FIFO_EVAL` | `pending_count > 0` & healthy | `BEACON_SYNC` | Enable radio single RX for Gateway Beacon |
| `BEACON_SYNC` | Valid Beacon 0x43 (valid HMAC) | `SLOT_SCHEDULER` | Align clock, reset $N_{\text{MISSED}}=0$, sync=true |
| `BEACON_SYNC` | Missed Beacon & $N_{\text{MISSED}} \le 3$ & drift $\le 50\text{ms}$ | `SLOT_SCHEDULER` | Maintain holdover, align to estimated slot |
| `BEACON_SYNC` | Missed Beacon & drift $> 50\text{ms}$ | `REARM_SLEEP` | Inhibit TX, retain event, go to sleep |
| `BEACON_SYNC` | Missed Beacon & $N_{\text{MISSED}} > 3$ | `DISCONNECTED` | Lock DATA TX fail-closed, retain event |
| `SLOT_SCHEDULER` | Within usable slot window | `AIRTIME_CHECK` | Proceed to pre-transmit safety checks |
| `SLOT_SCHEDULER` | Out of usable slot boundary | `REARM_SLEEP` | Suppress TX (Zero out-of-slot RF emission) |
| `AIRTIME_CHECK` | `airtime_policy_check() == OK` | `EVENT_TX` | Proceed to construct and emit packet |
| `AIRTIME_CHECK` | Duty cycle budget exhausted | `REARM_SLEEP` | Suppress TX, retain event in FIFO |
| `EVENT_TX` | Transmission complete | `ACK_RX` | Record TX airtime, switch radio to RX |
| `ACK_RX` | Frame received or timeout | `ACK_EVAL` | Process received buffer |
| `ACK_EVAL` | Valid ACK 0x42 (tag OK, ref match) | `REARM_SLEEP` | `node_event_fifo_pop()`, counter++ |
| `ACK_EVAL` | Timeout or Corrupted ACK | `REARM_SLEEP` | `node_event_fifo_record_retry()`, retain |
| `REARM_SLEEP` | Always | `DEEP_SLEEP` | Sleep SX1276, arm EXT0 wakeup, deep-sleep |

---

## 3. Cryptographic Implementation and Standards Compliance

### 3.1 Nonce Construction & Replay Protection (`SEC-004`)
- Nonce size: 13 octets ($L=2$).
- Format: `SESSION_NONCE_PREFIX (8B) || DIRECTION (1B) || FRAME_COUNTER (4B BE)`.
- Uplink direction: `0x01` (`LORA_MAC_V2_DIR_UPLINK`).
- Downlink direction: `0x02` (`LORA_MAC_V2_DIR_DOWNLINK`).
- Uplink frame counter committed monotonically and preserved across deep-sleep in RTC memory.

### 3.2 Key Protection & Zeroization (`SEC-001`, `SEC-005`)
- Sensitive buffers and keys cleared immediately after cryptographic operations using `node_crypto_zeroize()` (`mbedtls_platform_zeroize()` on ESP-IDF).
- Zero dynamic heap allocation (`MEM-001`): all contexts, buffers, and state structures are statically allocated or stored in RTC memory attributes (`RTC_DATA_ATTR`).

### 3.3 Target vs Host Dual Cryptographic Engine
- **ESP-IDF v6.1 Target:** Employs PSA Crypto (`PSA_ALG_AEAD_WITH_SHORTENED_TAG(PSA_ALG_CCM, 8)` and `PSA_ALG_HMAC(PSA_ALG_SHA_256)`) with hardware cryptographic engine acceleration.
- **Host Unit Test Mode:** Employs clean, self-contained, portable RFC 3610 AES-128-CCM and FIPS 180-4 / RFC 2104 HMAC-SHA256 implementations with zero external host library dependencies.

---

## 4. Test Verification Evidence

### 4.1 Host Unit Test Suite (`tests/unit/test_node_tdma_client.c`)
- **Execution Command:**
  ```bash
  gcc -Wall -Wextra -Werror -pedantic -std=c11 \
    -I firmware/components/lora_mac/include \
    -I firmware/components/tdma_common/include \
    -I firmware/components/airtime_policy/include \
    -I firmware/sensor_node/main \
    -I tests/unit/mock_esp \
    firmware/components/lora_mac/src/lora_mac.c \
    firmware/components/lora_mac/src/node_event_fifo.c \
    firmware/components/tdma_common/src/tdma_common.c \
    firmware/components/airtime_policy/src/airtime_policy.c \
    firmware/sensor_node/main/node_crypto.c \
    firmware/sensor_node/main/node_tdma_client.c \
    tests/unit/test_node_tdma_client.c \
    -o /tmp/test_node_tdma_client && /tmp/test_node_tdma_client
  ```
- **Execution Output:**
  ```text
  ============================================================
  Running Node TDMA Slot Client Unit Tests (Issue #239)
  ============================================================
  Running test_node_tdma_client_init_and_config ... PASSED
  Running test_node_tdma_slot_boundary_calculation ... PASSED
  Running test_crypto_operations_roundtrip ... PASSED
  Running test_state_transition_success_pop ... PASSED
  Running test_state_transition_missed_and_corrupted_ack_retry ... PASSED
  Running test_state_transition_airtime_exhaustion_suppression ... PASSED
  Running test_state_transition_beacon_loss_lock ... PASSED
  Running test_zero_out_of_slot_rf_transmission ... PASSED
  ============================================================
  All Node TDMA Slot Client unit tests PASSED successfully!
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
  Ran 3 tests in 0.784s

  OK
  ```
- **Exit Code:** `0`

### 4.3 ESP-IDF v6.1 Docker Compilation
- **Target Image:** `espressif/idf:v6.1` (`sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c`)
- **Sensor Node Compilation Command:**
  ```bash
  docker run --rm --network=none -v $(pwd):/project -w /project/firmware/sensor_node espressif/idf:v6.1 idf.py build
  ```
  - Result: `sensor_node.bin` binary size `0x4a5e0` bytes. App partition `0x100000` bytes, `0xb5a20` bytes (71%) free.
  - Exit Code: `0`
- **Gateway Master Compilation Command:**
  ```bash
  docker run --rm --network=none -v $(pwd):/project -w /project/firmware/gateway_master espressif/idf:v6.1 idf.py build
  ```
  - Result: `gateway_master.bin` binary size `0x2de40` bytes. App partition `0x100000` bytes, `0xd21c0` bytes (82%) free.
  - Exit Code: `0`

---

## 5. Acceptance Criteria Verification Matrix

| Acceptance Criterion | Verification Method | Result | Evidence |
|---|---|:---:|---|
| Node TDMA slot client implemented and cleanly integrated into `firmware/sensor_node/` | Source inspection, ESP-IDF build | **PASS** | `node_tdma_client.c/.h` and `main.c` integration, clean compilation |
| Button event in FIFO $\to$ Beacon sync $\to$ static slot TX $\to$ ACK reception $\to$ FIFO pop | Unit Test `test_state_transition_success_pop` | **PASS** | Pending count drops $1 \to 0$, frame counter advances |
| Missed ACK / corrupted ACK $\to$ retry counter increment, event retained in FIFO | Unit Test `test_state_transition_missed_and_corrupted_ack_retry` | **PASS** | Pending count remains 1, retry count increments $0 \to 1 \to 2$ |
| Airtime budget exhaustion $\to$ TX suppressed, event retained in FIFO | Unit Test `test_state_transition_airtime_exhaustion_suppression` | **PASS** | `s_tx_count == 0`, event preserved |
| Beacon loss ($N_{\text{MISSED}} > 3$) $\to$ fail-closed lock on DATA TX emissions | Unit Test `test_state_transition_beacon_loss_lock` | **PASS** | Transitions to `DISCONNECTED`, DATA TX emissions locked |
| Zero out-of-slot RF transmission | Unit Test `test_zero_out_of_slot_rf_transmission` | **PASS** | `s_out_of_slot_tx_count == 0` strictly verified |
| ESP-IDF v6.1 Docker compilation succeeds with 0 errors for `sensor_node` and `gateway_master` | Docker build `espressif/idf:v6.1` | **PASS** | Both builds exit code 0 |
| Secret scan and git-diff scope checks pass without violations | `agent_context.py` and quality gates | **PASS** | Edits bounded to allowed paths |
| Verification dossier delivered | Documentation inspection | **PASS** | `docs/verification/issue-239-node-tdma-slot-client-verification.md` |

---

## 6. Gate Status and Human Decisions Reserved

- `AUTO_CHECK_PASS`: **PASS** (100% of unit tests pass, ESP-IDF v6.1 builds pass).
- `SECRET_SCAN_PASS`: **PASS** (Zero hardcoded production keys; only standard test vectors used).
- `SECURITY_REVIEW_PASS`: **PENDING_HUMAN_REVIEW** (RF transmission and cryptographic state machines require expert human review per `ai:human-audit-req`).
- `HIL_RF_PASS`: **NOT_VERIFIED** (Physical over-the-air RF measurements and microsecond oscilloscope timing require bench hardware bringup).
