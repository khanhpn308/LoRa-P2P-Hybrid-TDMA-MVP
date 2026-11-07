# Issue #13 Verification Dossier: Shared MAC, TDMA Common, and Airtime Policy

> **Document Status:** `VERIFIED_FOR_REVIEW` / `AUDIT_READY`  
> **Source Issue:** [#13](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/13)  
> **Wave:** Wave 2 · **Project Gate:** `G3: Embedded`  
> **Governing Standards:** [C Coding Standard v2](../../docs/development/firmware/C_CODING_STANDARD_V2.md) (Owner #137)  
> **Architecture Authorities:** [ADR-0001](../../docs/adr/0001-hybrid-tdma.md), [ADR-0003](../../docs/adr/0003-esp-idf-v6-1.md), [ADR-0004](../../docs/adr/0004-theoretical-timing-guard-budget.md), [PR #198](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/198), [PR #200](../../docs/architecture/backlog-rebaseline-ledger.md), [PR #212](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/212)

---

## 1. Executive Summary & Provenance

Issue #13 defines and delivers the foundational, shared embedded components for the LoRa P2P Hybrid TDMA firmware:
1. **`firmware/components/lora_mac`**: Unicast MAC frame serializers, parsers, and codecs.
   - Historical V1 candidate envelope (8B header, CRC-16, message types `0x01`..`0x08`) integrated via PR #184 and verified via PR #186.
   - Production V2 normative codecs (`UP_EVENT` 0x41 26B, `DOWN_EVENT_ACK` 0x42 19B, `DOWN_SYNC_BEACON` 0x43 32B HMAC, `UP_HEALTH_REPLY` 0x44 21B, `UP_DIAG_METRICS` 0x4A 23B) and persistent Node Event FIFO integrated via PR #212 (Issue #131).
2. **`firmware/components/tdma_common`**: Shared superframe, subframe, and slot layout timing definitions and helpers under Profile P-10S-15 (`contracts/radio-mac/tdma-schedule.md`), integrated via PR #185 and verified with dedicated host C11 test suite.
3. **`firmware/components/airtime_policy`**: Local pre-transmit duty cycle enforcement engine with fail-closed regulatory blocking, wrap-around saturation protection, and zero dynamic memory allocation, integrated via PR #183 and enhanced with unit test coverage.

### Reconciliation with V2 Rebaseline (#199 / PR #200)
Per Owner Decision #125 / PR #133 and #127 / PR #198, periodic telemetry on RF has been eliminated in favor of Event-Only Static TDMA. The components in Issue #13 respect this boundary:
- Historical V1 framing is preserved for compatibility and negative regression testing; it is **not** asserted as production freeze.
- V2 Golden Vectors at byte level remain blocked pending Gate G2 freeze (`contracts/radio-mac/test-vectors/README.md`); V2 framing and codecs are verified against draft specifications in PR #198 / PR #212.
- No dedicated Priority Alert RF budget or out-of-schedule contention slot is provisioned; all traffic categories fail closed upon reaching duty limits.
- Neither Gateway Master TDMA execution nor Node Client scheduling is claimed as completed by this shared component issue.

---

## 2. Acceptance Criteria Conformance Matrix

| Acceptance Criterion | Verification Method | Result | Evidence / Details |
|---|---|---|---|
| **AC-1: Golden Vectors & Codecs**<br>100% Golden Vectors of approved contract version verified through C codec; V1 PASS ≠ V2 PASS; no V2 draft freeze claim | Host C11 unit test suites (`test_lora_mac.c`, `test_lora_mac_v2.c`, `test_node_event_fifo.c`) | **PASS** | - V1 framing: 8 message types, boundary payload sizes (0, 1, 47, 48B), version check, magic check (`0xA5`), length checks: **PASS** (1/1).<br>- V2 codecs: 0x41, 0x42, 0x43, 0x44, 0x4A roundtrip, nonce builder, FIFO drop-oldest: **PASS** (2/2).<br>- G2 status explicitly maintained as `NOT_VERIFIED`. |
| **AC-2: Regulatory Airtime Policy**<br>Policy rejects TX when reaching RF limit regardless of priority; test on clock reset, overflow, retransmission | Host C11 test suite (`test_airtime_policy.c`) and contract runner (`test_shared_mac_components.py`) | **PASS** | - `airtime_policy_check` returns `ESP_ERR_INVALID_STATE` when budget exceeded.<br>- No alert bypass: Priority Alert / emergency frames strictly denied when budget exhausted.<br>- Integer overflow protection: `(uint64_t)sum > UINT32_MAX` saturates accumulator at `UINT32_MAX`, preventing wrap-around.<br>- Reset restores budget cleanly. |
| **AC-3: Gateway & Node Builds**<br>Both Gateway and Node build cleanly; conditions & limits recorded; no false claim of TDMA Master/Client | Pinned ESP-IDF v6.1 toolchain in Docker container (`espressif/idf:v6.1`) | **PASS** | - `firmware/gateway_master`: Build exit code 0 (`gateway_master.bin` size: 0x2de40 bytes, 82% free partition).<br>- `firmware/sensor_node`: Build exit code 0 (`sensor_node.bin` size: 0x31d20 bytes, 81% free partition).<br>- TDMA Master & Node Client engines noted as unintegrated (`NOT_VERIFIED`). |

---

## 3. C Coding Standard v2 Compliance Checklist

| Rule ID | Rule Summary | Verification Evidence | Status |
|---|---|---|---|
| `MEM-001` | Zero dynamic memory allocation (`malloc`/`free` forbidden) | Static inspection of all three component `src/` directories. All state is bounded static or stack-allocated. | **PASS** |
| `ERR-001` | Explicit error return codes checked | All public APIs return `esp_err_t` or validated primitives; all error states handled fail-closed. | **PASS** |
| `SEC-001` | Buffer length and pointer boundary checks | Strict argument verification (`NULL` checks, buffer size validation, out-of-bounds slot IDs). | **PASS** |
| `SEC-002` | Explicit endian / octet serialization | All wire packing uses explicit offset-by-offset byte assignments; zero raw struct memory casting. | **PASS** |
| `C-002` | Consistent namespacing | Prefixes `lora_mac_*`, `tdma_*`, `airtime_policy_*` enforced across symbols and headers. | **PASS** |
| `C-007` | Fixed-width standard integer types | Used `uint8_t`, `uint16_t`, `uint32_t`, `size_t` from `<stdint.h>` and `<stddef.h>`. | **PASS** |
| `QA-004` | Boundary and negative test coverage | Host unit test suites test all negative arguments, zero ToA, budget saturation, and out-of-range slots. | **PASS** |

---

## 4. Test Execution & Build Verification Receipts

### 4.1 Host Unit & Contract Test Suites (Pytest)
Command:
```bash
python3 -m pytest tests/contract/ tests/unit/
```
Result:
```text
tests/contract/test_api_contract.py .....                                [ 16%]
tests/contract/test_mqtt_session_key_contract.py .........               [ 45%]
tests/contract/test_radio_mac_timing_consistency.py ............         [ 83%]
tests/contract/test_shared_mac_components.py ..                          [ 90%]
tests/unit/test_firmware_v2_unit.py ..                                   [ 96%]
tests/unit/test_lora_mac.py .                                            [100%]

======================== 31 passed, 1 warning in 1.41s =========================
```

### 4.2 C11 Host Component Unit Tests

#### `airtime_policy` Test Suite (`test_airtime_policy.c`)
Compiler: `gcc -Wall -Wextra -Werror -pedantic -std=c11`
```text
=== Starting airtime_policy Unit Tests ===
Running test_airtime_policy_init_nominal ... PASSED
Running test_airtime_policy_init_bounds ... PASSED
Running test_airtime_policy_zero_toa ... PASSED
Running test_airtime_policy_record_incremental ... PASSED
Running test_airtime_policy_budget_exhaustion ... PASSED
Running test_airtime_policy_no_alert_bypass ... PASSED
Running test_airtime_policy_overflow_protection ... PASSED
Running test_airtime_policy_reset ... PASSED
=== airtime_policy Unit Tests Completed: ALL PASSED (failures: 0) ===
```

#### `tdma_common` Test Suite (`test_tdma_common.c`)
Compiler: `gcc -Wall -Wextra -Werror -pedantic -std=c11`
```text
=== Starting tdma_common Unit Tests ===
Running test_tdma_common_init ... PASSED
Running test_tdma_is_valid_slot_id ... PASSED
Running test_tdma_get_slot_start_offset_nominal ... PASSED
Running test_tdma_get_slot_start_offset_negative ... PASSED
Running test_tdma_calculate_drift_guard ... PASSED
=== tdma_common Unit Tests Completed: ALL PASSED (failures: 0) ===
```

### 4.3 ESP-IDF v6.1 Firmware Target Builds
Docker Image: `espressif/idf:v6.1` (Hash `81893c71bb5e`)

- **`firmware/gateway_master`**:
  ```bash
  docker run --rm -v $(pwd):/project -w /project/firmware/gateway_master espressif/idf:v6.1 idf.py build
  ```
  Result:
  ```text
  [1049/1049] Generating binary image from built executable
  gateway_master.bin binary size 0x2de40 bytes. Smallest app partition is 0x100000 bytes. 0xd21c0 bytes (82%) free.
  Project build complete.
  ```

- **`firmware/sensor_node`**:
  ```bash
  docker run --rm -v $(pwd):/project -w /project/firmware/sensor_node espressif/idf:v6.1 idf.py build
  ```
  Result:
  ```text
  [1049/1049] Generating binary image from built executable
  sensor_node.bin binary size 0x31d20 bytes. Smallest app partition is 0x100000 bytes. 0xce2e0 bytes (81%) free.
  Project build complete.
  ```

---

## 5. Non-Goals & Verification Boundaries

1. **Gate G2 Specification Status:** The V2 binary contract remains draft (`v2.0.0-DRAFT`, `Gate G2: NOT_VERIFIED`) until formal review and lock by #201 and system architecture.
2. **Physical HIL Bench & RF Radiation:** No radio emissions were radiated during this verification (`Gate G1/HIL: NOT_VERIFIED`). Hardware bench measurements are owned by [Issue #169](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/169).
3. **State Machine Execution:** The components provide framing, timing math, and policy checks only. Neither Gateway TDMA Master execution nor Node Client synchronization is implemented in these shared libraries.
