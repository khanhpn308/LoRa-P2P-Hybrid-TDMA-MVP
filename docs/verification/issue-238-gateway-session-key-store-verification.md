# Verification Dossier: Issue #238 — Gateway NVS Session Key Store & INSTALLED_INACTIVE State Machine

**Status:** `VERIFIED_LOCAL`  
**Issue:** #238  
**Component:** `firmware/components/session_key_store/`, `firmware/gateway_master/`  
**Target Platform:** ESP32-WROOM-32E, ESP-IDF v6.1 (`espressif/idf:v6.1`)  
**Authority:** DEC-SEC-05, DEC-SEC-06, ADR-0003, `contracts/mqtt/session-key-security.md`, C Coding Standard v2  
**Prerequisite Unblocked:** Issue #175 (HIL power-loss fault injection)

---

## 1. Executive Summary

This dossier documents the implementation and verification of the Gateway session key storage component (`firmware/components/session_key_store/`) and its integration into the Gateway Master application (`firmware/gateway_master/`) on ESP-IDF v6.1.

The component fulfills all functional requirements and acceptance criteria:
1. **Durable NVS Storage & State Machine (DEC-SEC-05):**
   - Supports atomic dual-slot staging (`staging` vs `active`) per Node for up to 15 nodes (`SK_STORE_MAX_NODES = 15`).
   - Staged sessions commit durably into ESP-IDF NVS flash in `INSTALLED_INACTIVE` prior to ACK emission.
   - Radio transmission rights remain strictly disabled in `INSTALLED_INACTIVE` (`session_key_store_get_active` returns `ESP_ERR_NOT_FOUND`).
   - Controlled promotion to `ACTIVE` enforces time validity window (`not_before_ms <= now_ms < expires_at_ms`).
2. **Anti-Replay & Anti-Rollback Monotonic Tracking:**
   - Durable monotonic high-water mark revision per node in NVS (`rev_<node_id>`).
   - Strictly rejects any install with `session_revision <= current_committed_revision` with `ESP_ERR_INVALID_VERSION`.
   - Detects idempotent duplicate installations (identical `install_id`, `session_id`, `session_revision`) and returns `ESP_OK` without writing to NVS or incrementing flash wear.
3. **Cryptographic Integration & Fail-Closed Memory Safety:**
   - Reconstructs canonical Install AAD V1 and decrypts wrapped session keys via AES-256-GCM.
   - Unwrapping occurs in temporary stack buffers; tag authentication failure or ciphertext corruption aborts immediately before modifying NVS or slot state.
   - Zero dynamic heap allocation (`MEM-001`); all slot tables and buffers are statically bounded.
   - Sensitive key buffers and temporary state are zeroized using `mbedtls_platform_zeroize()`.
   - Never logs raw key bytes to UART or `ESP_LOG`.
4. **Gateway Master Boot Integration:**
   - Initializes NVS flash (`nvs_flash_init()`) and session key store (`session_key_store_init()`) during `app_main()`.
   - Automatically restores durable staging, active, and revision high-water marks from NVS across reboots.

---

## 2. Architecture & File Inventory

### Production Components
- `firmware/components/session_key_store/include/session_key_store.h`: Public API for session key store, state machine enum, and record structures.
- `firmware/components/session_key_store/include/session_key_crypto.h`: PSA Crypto interface definitions for AAD building, AES-256-GCM wrap/unwrap, and ACK derivation/tagging.
- `firmware/components/session_key_store/src/session_key_store.c`: Core implementation of NVS persistence, state machine, and monotonic anti-rollback tracking.
- `firmware/components/session_key_store/src/session_key_crypto.c`: Production implementation of cryptographic routines for ESP-IDF v6.1 using PSA Crypto and `mbedtls_platform_zeroize`.
- `firmware/components/session_key_store/CMakeLists.txt`: ESP-IDF component registration requiring `nvs_flash`, `mbedtls`, `esp_hw_support`, and `log`.
- `firmware/gateway_master/main/main.c`: Boot sequence integration with NVS and `session_key_store_init()`.
- `firmware/gateway_master/main/CMakeLists.txt`: Project dependencies updated with `session_key_store` and `nvs_flash`.

### Verification & Test Suite
- `tests/unit/test_session_key_store.c`: Comprehensive C unit test suite covering 100% of state transitions and edge cases.
- `tests/unit/test_session_key_store.py`: Python unittest runner compiling strict C11 host binary (`-Wall -Wextra -Werror -pedantic -std=c11`).
- `tests/unit/mock_esp/nvs.h`, `nvs_flash.h`, `mock_nvs.c`: Mock NVS subsystem verifying transaction commit counts, blob storage, and power loss recovery.
- `tests/unit/mock_crypto.c`: Mock crypto adapter enabling host-side deterministic tag validation and failure injection.

---

## 3. Unit Test Verification Results

All host unit tests executed cleanly via `python3 -m unittest discover tests/unit`:

```
Running Gateway Session Key Store Unit Tests...
  [PASS] test_install_valid_enters_installed_inactive
  [PASS] test_durability_and_reboot_restore
  [PASS] test_idempotent_duplicate_install
  [PASS] test_anti_rollback_rejects_stale_revision
  [PASS] test_tag_auth_failure_clean_rejection
  [PASS] test_promotion_lifecycle
  [PASS] test_expiration_and_revocation
  [PASS] test_ack_generation
  [PASS] test_parameter_bounds
ALL Gateway Session Key Store Unit Tests PASSED (100% state transitions verified).
```

### State Machine Coverage Matrix

| State Transition | Test Function | Result |
|---|---|---|
| Initial $\rightarrow$ `INSTALLED_INACTIVE` | `test_install_valid_enters_installed_inactive` | **PASS** |
| Reboot $\rightarrow$ Restore from NVS | `test_durability_and_reboot_restore` | **PASS** |
| Duplicate $\rightarrow$ Idempotent No-Op | `test_idempotent_duplicate_install` | **PASS** |
| Stale Revision $\rightarrow$ Rollback Rejection | `test_anti_rollback_rejects_stale_revision` | **PASS** |
| Tag Auth Failure $\rightarrow$ Fail-Closed / NVS Unaltered | `test_tag_auth_failure_clean_rejection` | **PASS** |
| `INSTALLED_INACTIVE` $\rightarrow$ `WAIT_TDMA` $\rightarrow$ `ACTIVE` | `test_promotion_lifecycle` | **PASS** |
| Guard Rejection (`now < not_before` / `now >= expires_at`) | `test_promotion_lifecycle` | **PASS** |
| `ACTIVE` $\rightarrow$ `EXPIRED` | `test_expiration_and_revocation` | **PASS** |
| `ACTIVE`/`STAGING` $\rightarrow$ `REVOKED` (keys zeroized, rev preserved) | `test_expiration_and_revocation` | **PASS** |
| ACK Transcript & HMAC-SHA256 Derivation | `test_ack_generation` | **PASS** |
| Input Parameter & Memory Bounds Validation | `test_parameter_bounds` | **PASS** |

---

## 4. ESP-IDF v6.1 Docker Compilation Receipts

Both firmware applications were compiled using the official `espressif/idf:v6.1` container:

### Gateway Master Build
- **Target:** `esp32`
- **Toolchain:** `xtensa-esp-elf-gcc (esp-15.2.0_20251204)`
- **Command:** `idf.py build` inside `espressif/idf:v6.1`
- **Output:**
  - `gateway_master.bin` size: `0x282e0` bytes (164,576 bytes).
  - App partition utilization: 16% used (84% free).
  - Static library: `libsession_key_store.a` linked successfully.
- **Result:** **PASS (0 errors, 0 warnings)**

### Sensor Node Build
- **Target:** `esp32`
- **Toolchain:** `xtensa-esp-elf-gcc (esp-15.2.0_20251204)`
- **Command:** `idf.py build` inside `espressif/idf:v6.1`
- **Output:**
  - `sensor_node.bin` size: `0x31d20` bytes (204,064 bytes).
  - App partition utilization: 19% used (81% free).
- **Result:** **PASS (0 errors, 0 warnings)**

---

## 5. Resolution of Prerequisites for Issue #175

Issue #175 specifies HIL power-loss fault injection testing for session key durability and flash recovery. This implementation establishes the necessary components:
- `nvs_commit()` is invoked atomically before any `SESSION_KEY_ACK` (`INSTALLED`) can be transmitted.
- High-water mark revision tracking guarantees that power loss occurring before `nvs_commit()` leaves the previous state intact, while power loss after `nvs_commit()` cleanly restores the new revision upon reboot.
- Idempotency handling allows MQTT QoS1 redeliveries to reconcile safely without flash corruption.

With this component verified, Issue #175 is **UNBLOCKED** for physical HIL fault-injection execution.
