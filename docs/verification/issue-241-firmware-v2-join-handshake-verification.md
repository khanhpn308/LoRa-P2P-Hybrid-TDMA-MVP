# Issue #241: Firmware Over-the-Air (OTA) V2 Join Handshake Verification Dossier

- **Document ID:** `VERIFY-ISSUE-241-FIRMWARE-V2-JOIN-HANDSHAKE`
- **Issue Reference:** [#241: [Firmware] Over-the-Air (OTA) V2 Join Handshake Implementation across Sensor Node and Gateway Master](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/241)
- **Status:** `VERIFIED_PASS`
- **Component Target:** `firmware/sensor_node/`, `firmware/gateway_master/`, `firmware/components/lora_mac/`
- **Toolchain Target:** `ESP-IDF v6.1` (Official Docker `espressif/idf:v6.1`, image `sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c`)
- **Authority:** DEC-SEC-01..07, ADR-0003, C Coding Standard v2, `contracts/radio-mac/specification.md`, `contracts/mqtt/schemas/join-hello.schema.json`.

---

## 1. Overview and Architecture

In accordance with Owner-approved decisions for the Event-Only Hybrid TDMA system (DEC-SEC-01..07), this work delivers the complete Firmware Over-the-Air (OTA) V2 Join handshake across both the Sensor Node and Gateway Master.

The V2 Join protocol establishes a cryptographically secure, forward-secret, replay-protected session between the Sensor Node, the Gateway, and the Backend without requiring hardcoded session keys.

### 1.1 Five-Message Sequential Handshake Flow

```
 Sensor Node                                  Gateway Master                              Backend Core
(SX1276 Client)                               (SX1276 Relay)                               (MQTT/API)
      |                                              |                                         |
      |-- 1. CAD Check (Max 3 attempts, backoff) ----|                                         |
      |-- 2. Monotonic NVS JOIN_COUNTER commit ------|                                         |
      |                                              |                                         |
      |-- [0x45] UP_JOIN_HELLO (68B) --------------->|                                         |
      |   (X25519 Pub_Node, Nonce, JOIN_PROOF)       |-- Publish Join Relay MQTT ------------->|
      |                                              |   (iot/v1/gw/{id}/uplink/join-hello)    |
      |                                              |                                         |
      |<-- [0x46] DOWN_JOIN_GRANT (66B) -------------|                                         |
      |   (X25519 Pub_GW, Nonce, GRANT_PROOF)        |                                         |
      |                                              |                                         |
      | [Compute Z = X25519(priv, pub), RFC 7748]    | [Compute Z = X25519(priv, pub), RFC 7748]|
      | [Derive TH & Session Keys: K_UP, K_DL]       | [Derive TH & Session Keys: K_UP, K_DL]  |
      | [Commit keys to INSTALLED_INACTIVE]          | [Commit keys to INSTALLED_INACTIVE]     |
      |                                              |                                         |
      |-- [0x47] UP_JOIN_KEY_CONFIRM (31B) --------->|                                         |
      |   (GW_KC_TAG, BACKEND_PROOF)                 |-- (Verify GW_KC_TAG)                    |
      |                                              |                                         |
      |<-- [0x48] DOWN_JOIN_FINISH (31B) ------------|                                         |
      |   (GW_FINISH_TAG, BACKEND_FINISH_PROOF)      |                                         |
      |                                              |                                         |
      |-- [0x49] UP_JOIN_READY (31B) --------------->|                                         |
      |   (Dual tags binding FINISH31)               |-- (Verify GW_READY_TAG)                 |
      |                                              |                                         |
      v                                              v                                         v
 [INSTALLED_INACTIVE]                           [INSTALLED_INACTIVE]                      [ACTIVATED]
```

---

## 2. Wire Framing and Codec Specifications

All 5 frame serializers and deserializers enforce strict wire length invariants, network byte ordering, and bounds validation:

| Message Type | Byte 0 Type | Total Length | Wire Frame Layout | Codec Implemented |
|---|---|---|---|---|
| `UP_JOIN_HELLO` | `0x45` | **68 Bytes** | `VER_TYPE:1 \|\| DEVICE_MAC:6 \|\| TARGET_GW_ID:1 \|\| JOIN_COUNTER:4BE \|\| NODE_NONCE:8 \|\| NODE_X25519_PUB:32 \|\| JOIN_PROOF:16` | `lora_mac_v2_up_join_hello_serialize` / `deserialize` |
| `DOWN_JOIN_GRANT` | `0x46` | **66 Bytes** | `VER_TYPE:1 \|\| DEVICE_MAC:6 \|\| NODE_ID:1 \|\| JOIN_COUNTER:4BE \|\| GW_NONCE:6 \|\| GW_X25519_PUB:32 \|\| GRANT_PROOF:16` | `lora_mac_v2_down_join_grant_serialize` / `deserialize` |
| `UP_JOIN_KEY_CONFIRM` | `0x47` | **31 Bytes** | `VER_TYPE:1 \|\| GW_ID:1 \|\| NODE_ID:1 \|\| JOIN_COUNTER:4BE \|\| GW_KC_TAG:8 \|\| BACKEND_PROOF:16` | `lora_mac_v2_up_join_key_confirm_serialize` / `deserialize` |
| `DOWN_JOIN_FINISH` | `0x48` | **31 Bytes** | `VER_TYPE:1 \|\| GW_ID:1 \|\| NODE_ID:1 \|\| JOIN_COUNTER:4BE \|\| GW_FINISH_TAG:8 \|\| BACKEND_FINISH_PROOF:16` | `lora_mac_v2_down_join_finish_serialize` / `deserialize` |
| `UP_JOIN_READY` | `0x49` | **31 Bytes** | `VER_TYPE:1 \|\| GW_ID:1 \|\| NODE_ID:1 \|\| JOIN_COUNTER:4BE \|\| GW_READY_TAG:8 \|\| BACKEND_READY_PROOF:16` | `lora_mac_v2_up_join_ready_serialize` / `deserialize` |

---

## 3. Cryptographic Implementation and Standards Compliance

### 3.1 Key Expansion & HKDF Derivations (`SEC-004`)
1. **Root Expansion from Provisioned $K_{\text{JOIN}}$:**
   - $\text{SALT} = \text{"LP2P/V2/JOIN-ROOT"} \parallel \text{NETWORK\_ID}_{32\text{BE}} \parallel \text{DEVICE\_MAC}_6 \parallel \text{DEVICE\_GENERATION}_{16\text{BE}}$ (29 bytes).
   - $\text{PRK}_{\text{JOIN}} = \text{HKDF-Extract}(\text{salt}=\text{SALT}, \text{IKM}=K_{\text{JOIN}})$.
   - Subkeys expanded via HKDF-Expand:
     - $K_{\text{JREQ}} = \text{HKDF-Expand}(\text{PRK}_{\text{JOIN}}, \text{"LP2P/V2/JOIN-REQ"}, 32)$
     - $K_{\text{JGRANT}} = \text{HKDF-Expand}(\text{PRK}_{\text{JOIN}}, \text{"LP2P/V2/JOIN-GRANT"}, 32)$
     - $K_{\text{JCONF}} = \text{HKDF-Expand}(\text{PRK}_{\text{JOIN}}, \text{"LP2P/V2/JOIN-CONF"}, 32)$
     - $K_{\text{JFINISH}} = \text{HKDF-Expand}(\text{PRK}_{\text{JOIN}}, \text{"LP2P/V2/JOIN-FINISH"}, 32)$
     - $K_{\text{JREADY}} = \text{HKDF-Expand}(\text{PRK}_{\text{JOIN}}, \text{"LP2P/V2/JOIN-READY"}, 32)$

2. **Transcript Hash (TH) & Session Key Derivation:**
   - $\text{TH} = \text{SHA-256}(\text{"LP2P/V2/TH-JOIN"} \parallel \text{NETWORK\_ID}_{32\text{BE}} \parallel \text{HELLO}_{68} \parallel \text{GRANT}_{66})$ (32 bytes).
   - $\text{PRK}_{\text{SESSION}} = \text{HKDF-Extract}(\text{salt}=\text{TH}, \text{IKM}=Z)$.
   - $K_{\text{KC\_UP}} = \text{HKDF-Expand}(\text{PRK}_{\text{SESSION}}, \text{"LP2P/V2/KC-UP"}, 32)$.
   - $K_{\text{KC\_DOWN}} = \text{HKDF-Expand}(\text{PRK}_{\text{SESSION}}, \text{"LP2P/V2/KC-DOWN"}, 32)$.
   - $K_{\text{SESSION\_ROOT}} = \text{HKDF-Expand}(\text{PRK}_{\text{SESSION}}, \text{"LP2P/V2/SESSION-ROOT"}, 32)$.
   - $K_{\text{SESSION\_UP}} = \text{HKDF-Expand}(K_{\text{SESSION\_ROOT}}, \text{"LP2P/V2/SESSION-UP"}, 32)$.
   - $K_{\text{SESSION\_DL}} = \text{HKDF-Expand}(K_{\text{SESSION\_ROOT}}, \text{"LP2P/V2/SESSION-DL"}, 32)$.

### 3.2 RFC 7748 All-Zeros Shared Secret Abort (`DEC-SEC-07`)
- Strict compliance with RFC 7748 Section 6.1:
  - If peer public key is all zeros, scalar multiplication is rejected immediately.
  - If computed shared secret $Z = 0^{32}$, memory is zeroized, the handshake campaign is aborted immediately, and `ESP_ERR_INVALID_RESPONSE` is returned.
  - Verified via negative test vector with mock forced zero shared secret injection.

### 3.3 Monotonic NVS Counter Commit & Rollback Lockout (`DEC-SEC-06`, `SEC-003`)
- Monotonic `JOIN_COUNTER` tracking in NVS flash:
  - Counter increment must be durably committed to NVS **before** emitting any RF packet over the air (`node_v2_join_commit_counter`).
  - If read counter is less than previously committed counter or NVS read/write fails, the radio is **permanently locked out** (`radio_permanently_locked = true`), state becomes `NODE_V2_JOIN_STATE_LOCKED_OUT`, and all RF transmissions are inhibited fail-closed.

### 3.4 Radio Channel Assessment & Backoff (`RAD-003`)
- Channel Activity Detection (CAD) prior to UP_JOIN_HELLO emission:
  - Maximum 3 CAD retries (`NODE_V2_JOIN_MAX_CAD_RETRIES = 3`).
  - Exponential backoff between attempts ($50\text{ ms} \times 2^n$).
  - If channel remains busy after 3 attempts, state machine aborts with `ESP_ERR_TIMEOUT`, puts SX1276 into sleep mode, and emits 0 bytes over RF.

### 3.5 Session Key Staging & Isolation (`DEC-SEC-05`, `SEC-001`)
- Derived session keys committed strictly into `INSTALLED_INACTIVE` state.
- Transmission rights in normal TDMA slots remain strictly inhibited until TDMA schedule cutover occurs.

### 3.6 Memory Safety & Zeroization (`MEM-001`, `MEM-005`, `SEC-005`)
- Zero dynamic heap allocation (`malloc`/`calloc` forbidden).
- Ephemeral private keys and Diffie-Hellman intermediate shared secrets $Z$ are wiped from RAM immediately after derivation via `lora_mac_crypto_zeroize()` (`mbedtls_platform_zeroize()` on target).
- Constant-time comparison (`lora_mac_crypto_constant_time_memcmp`) for all authentication tags and proofs to prevent timing side-channels.

---

## 4. Gateway MQTT Relay Schema Conformance

The Gateway Relay Engine parses incoming `UP_JOIN_HELLO` frames and builds MQTT relay envelopes strictly adhering to `contracts/mqtt/schemas/join-hello.schema.json`:

```json
{
  "schema_version": "1.0-draft",
  "event_id": "gw-pilot-01:01234567-89ab-cdef-0123-456789abcdef:1",
  "gateway_id": "gw-pilot-01",
  "gateway_epoch": "01234567-89ab-cdef-0123-456789abcdef",
  "event_seq": "1",
  "observed_at": null,
  "observed_time_source": "gateway_utc",
  "radio_rx_monotonic_us": "123456789",
  "buffered": false,
  "target_gw_id": 1,
  "raw_frame_hex": "45112233445566010000002a0102030405060708...",
  "rssi": -75,
  "snr": 9.5
}
```

- Topic: `iot/v1/gw/{gateway_id}/uplink/join-hello`
- QoS: 1
- `raw_frame_hex`: exact 136 hexadecimal characters encoding the 68-byte frame.
- Tested and verified under unit tests.

---

## 5. Verification Evidence

### 5.1 C Host Unit Test Suite (`tests/unit/test_firmware_v2_join.c`)

```
=== Running Firmware V2 OTA Join Handshake Unit Tests ===

Running test_join_frame_codecs_roundtrip ... PASSED
Running test_join_crypto_derivations_and_proofs ... PASSED
Running test_rfc7748_all_zeros_shared_secret_abort ... PASSED
Running test_monotonic_nvs_counter_commit_and_rollback_lockout ... PASSED
Running test_cad_retry_exhaustion ... PASSED
Running test_node_complete_handshake_end_to_end ... PASSED
Running test_gateway_relay_engine_and_mqtt_schema ... PASSED

=== Test Results: ALL TESTS PASSED (Failures: 0) ===
```

### 5.2 Python Test Discovery Runner (`python3 -m unittest`)

```bash
$ python3 -m unittest discover tests/unit
Ran 31 tests in 1.711s
OK
```

All 31 unit tests across all firmware modules, codecs, drivers, and provisioning tools pass cleanly.

### 5.3 ESP-IDF v6.1 Docker Compilation Receipts

#### Gateway Master Compilation
```bash
docker run --rm --network=none -v /home/khanh/projects/iot:/home/khanh/projects/iot \
  -w /home/khanh/projects/iot/LoRa-P2P-issue-241/firmware/gateway_master \
  espressif/idf:v6.1 idf.py build
```
- **Exit Code:** `0`
- **Errors:** `0`
- **Warnings:** `0`
- **App Binary Size:** `0xe2010` bytes (925,712 bytes), 12% headroom remaining.

#### Sensor Node Compilation
```bash
docker run --rm --network=none -v /home/khanh/projects/iot:/home/khanh/projects/iot \
  -w /home/khanh/projects/iot/LoRa-P2P-issue-241/firmware/sensor_node \
  espressif/idf:v6.1 idf.py build
```
- **Exit Code:** `0`
- **Errors:** `0`
- **Warnings:** `0`
- **App Binary Size:** `0x4a990` bytes (305,552 bytes), 71% headroom remaining.

### 5.4 Scope & Quality Gate Verification

```bash
$ python3 scripts/agent_harness/quality_gates.py --repo /home/khanh/projects/iot/LoRa-P2P-issue-241 --base 821924b95e03e88073cc3a577d761579f7249b4c --fingerprint-only
{
  "source_sha": "821924b95e03e88073cc3a577d761579f7249b4c",
  "base_sha": "821924b95e03e88073cc3a577d761579f7249b4c",
  "candidate_sha256": "239d15b657cce13e330749601b61365b5db67a99bff0fd89751415d166caa5f7",
  "changed_paths": [
    "firmware/components/lora_mac/CMakeLists.txt",
    "firmware/components/lora_mac/include/lora_mac.h",
    "firmware/components/lora_mac/include/lora_mac_join_crypto.h",
    "firmware/components/lora_mac/src/lora_mac.c",
    "firmware/components/lora_mac/src/lora_mac_join_crypto.c",
    "firmware/gateway_master/main/CMakeLists.txt",
    "firmware/gateway_master/main/gateway_v2_join.c",
    "firmware/gateway_master/main/gateway_v2_join.h",
    "firmware/gateway_master/main/main.c",
    "firmware/sensor_node/dependencies.lock",
    "firmware/sensor_node/main/CMakeLists.txt",
    "firmware/sensor_node/main/main.c",
    "firmware/sensor_node/main/node_v2_join.c",
    "firmware/sensor_node/main/node_v2_join.h",
    "tests/unit/mock_esp/nvs.h",
    "tests/unit/mock_nvs.c",
    "tests/unit/test_firmware_v2_join.c",
    "tests/unit/test_firmware_v2_unit.py"
  ]
}
```

All modified and untracked files are strictly within the permitted 5 allowed directories:
- `firmware/components/lora_mac/`
- `firmware/sensor_node/`
- `firmware/gateway_master/`
- `tests/unit/`
- `docs/verification/`

---

## 6. Review & Acceptance Sign-Off Matrix

| Requirement / Criterion | Status | Evidence / Notes |
|---|---|---|
| Complete 5-Message V2 Join Handshake Implementation | **PASS** | State machines implemented in `node_v2_join.c` and `gateway_v2_join.c` |
| Monotonic NVS Counter Tracking & Rollback Lockout | **PASS** | DEC-SEC-06 enforced in `node_v2_join_commit_counter`, verified in unit test 4 |
| RFC 7748 All-Zeros Shared Secret Abort | **PASS** | DEC-SEC-07 enforced in `lora_mac_crypto_x25519_ecdh`, verified in unit test 3 |
| CAD Retry Exhaustion (3 attempts -> Sleep) | **PASS** | RAD-003 backoff & fail-closed sleep verified in unit test 5 |
| Gateway MQTT Relay Schema Conformance | **PASS** | Payload adheres to `join-hello.schema.json`, verified in unit test 7 |
| Session Keys Committed to `INSTALLED_INACTIVE` | **PASS** | DEC-SEC-05 verified in end-to-end test 6 |
| ESP-IDF v6.1 Docker Compilation | **PASS** | `gateway_master` and `sensor_node` compile with 0 errors, 0 warnings |
| Zero Dynamic Heap Allocation (`MEM-001`) | **PASS** | Bounded static/stack buffers across all join components |
| Secret Zeroization (`MEM-005`, `SEC-005`) | **PASS** | Private keys wiped via `lora_mac_crypto_zeroize` immediately after ECDH |
| Scoped Path Integrity | **PASS** | 100% of diff within allowed directories |
