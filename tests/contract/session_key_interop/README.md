# MQTT Session Key Interoperability Verification Suite

**Authority:** Issue #173, PR #123 (`contracts/mqtt/session-key-security.md`), ADR-0003.

This directory contains deterministic Golden Vectors and executable cross-language contract test adapters verifying byte-level cryptographic interoperability between Go (Backend) and ESP-IDF mbedTLS (Gateway) for MQTT session-key installation and acknowledgement.

---

## 1. Cryptographic Contracts & Roles

| Protocol Message | MQTT Topic | Producer | Consumer | Cryptographic Primitive |
| :--- | :--- | :--- | :--- | :--- |
| `SESSION_KEY_INSTALL` | `iot/v1/gw/{gateway_id}/downlink/session-key-install` | Backend (Go) | Gateway (ESP32) | AES-256-GCM (Wrap `K_SESSION_UP[32] \|\| K_SESSION_DL[32]` with AAD) |
| `SESSION_KEY_ACK` | `iot/v1/gw/{gateway_id}/uplink/session-key-ack` | Gateway (ESP32) | Backend (Go) | HKDF-SHA256 (`K_ACK`) + Truncated HMAC-SHA256 (16B) over `M_ACK` |

### Key Invariants
1. **AEAD Wrap:** $K_{\text{GW\_WRAP}}$ is a 32-byte secret. The 64-byte plaintext consists strictly of operational keys ($K_{\text{SESSION\_UP}} \parallel K_{\text{SESSION\_DL}}$). Root secret $K_{\text{JOIN}}$ is never transmitted.
2. **Canonical Install AAD V1:** Exactly 21 fields serialized with deterministic big-endian fixed integers and length-prefixed (`LP: U16 len || ASCII`) strings. Length for reference case: 232 bytes.
3. **ACK Key Derivation:**
   $$\text{ACK\_PRK} = \text{HKDF-Extract}(\text{salt}=\text{"LP2P/MQTT/V1/ACK-SALT"}, \text{IKM}=K_{\text{GW\_WRAP}})$$
   $$K_{\text{ACK}} = \text{HKDF-Expand}(\text{ACK\_PRK}, \text{info}=\text{LP("LP2P/MQTT/V1/KEY-INSTALL-ACK")} \parallel U32(\text{wrap\_key\_id}) \parallel \text{LP}(\text{gateway\_id}), 32)$$
4. **Canonical ACK Transcript $M_{\text{ACK}}$:** Exactly 11 fields serialized deterministically. Length for reference case: 138 bytes.
5. **ACK Authentication Tag:**
   $$\text{ack\_tag} = \text{first16}(\text{HMAC-SHA256}(K_{\text{ACK}}, M_{\text{ACK}}))$$
   Verified in constant time.

---

## 2. Directory Structure

```text
tests/contract/session_key_interop/
├── go.mod                     # Isolated Go module for test adapter
├── session_key_crypto.go      # Go cryptographic implementation and serializers
├── session_key_crypto_test.go # Go test suite (positive & negative cases)
├── session_key_vectors.json   # Deterministic Golden Vectors & negative fixtures
├── runner.py                  # End-to-end Python test runner and verifier
├── README.md                  # This documentation
└── esp_idf_adapter/           # ESP-IDF v6.1 mbedTLS / PSA Crypto test project
    ├── CMakeLists.txt
    ├── sdkconfig.defaults
    └── main/
        ├── CMakeLists.txt
        ├── session_key_crypto.h # C crypto API definitions
        ├── session_key_crypto.c # C implementation (PSA AEAD & HMAC/HKDF)
        └── test_main.c          # ESP32 test runner executing in QEMU
```

---

## 3. Running the Verification Suite

### Automated Full Suite
```bash
python3 tests/contract/session_key_interop/runner.py
```
This executes:
1. Deterministic Golden Vector verification against Python `cryptography` library.
2. Go test adapter execution (`go test -v ./...`).
3. ESP-IDF mbedTLS build and headless execution on simulated ESP32 in QEMU.
4. Cross-language artifact verification and evidence manifest generation.

### Running Go Tests Manually
```bash
cd tests/contract/session_key_interop
go test -v ./...
```

### Building & Running ESP-IDF mbedTLS Adapter
```bash
cd tests/contract/session_key_interop/esp_idf_adapter
idf.py build
cd build
esptool --chip esp32 merge-bin -o qemu_flash.bin @flash_args
truncate -s 2M qemu_flash.bin
qemu-system-xtensa -nographic -machine esp32 -drive file=qemu_flash.bin,if=mtd,format=raw -serial mon:stdio -no-reboot
```

---

## 4. Test Coverage & Negative Test Matrix

| ID | Category | Stimulus | Expected Behavior |
| :--- | :--- | :--- | :--- |
| **GV-POS-01** | Positive | Valid Install envelope | AAD reconstructed (232B), GCM unwrap yields exact session keys |
| **GV-POS-02** | Positive | Valid ACK (`INSTALLED` / `NONE`) | $M_{\text{ACK}}$ reconstructed (138B), $K_{\text{ACK}}$ derived, HMAC verified |
| **GV-POS-03** | Positive | Valid ACK (`REJECTED` / `EXPIRED`) | Rejection transcript signed and authenticated |
| **GV-NEG-01** | Negative | 1-bit flipped in ciphertext | AES-GCM tag verification fails, returns `SK_ERR_GCM_AUTH_FAILED` |
| **GV-NEG-02** | Negative | 1-bit flipped in GCM tag | AES-GCM tag verification fails, returns `SK_ERR_GCM_AUTH_FAILED` |
| **GV-NEG-03** | Negative | Incorrect $K_{\text{GW\_WRAP}}$ key | AES-GCM tag verification fails, returns `SK_ERR_GCM_AUTH_FAILED` |
| **GV-NEG-04** | Negative | Tampered topic in AAD | AAD mismatch causes GCM tag failure |
| **GV-NEG-05** | Negative | Tampered `gateway_id` in AAD | AAD mismatch causes GCM tag failure |
| **GV-NEG-06** | Negative | Tampered `session_id` in AAD | AAD mismatch causes GCM tag failure |
| **GV-NEG-07** | Negative | Tampered `session_revision` in AAD | AAD mismatch causes GCM tag failure |
| **GV-NEG-08** | Negative | Tampered `expires_at` in AAD | AAD mismatch causes GCM tag failure |
| **GV-NEG-09** | Negative | 1-bit flipped in `ack_tag` | Constant-time HMAC comparison fails, returns `SK_ERR_TAG_MISMATCH` |
| **GV-NEG-10** | Negative | Tampered status in $M_{\text{ACK}}$ | HMAC verification fails |
| **GV-NEG-11** | Negative | Tampered reason in $M_{\text{ACK}}$ | HMAC verification fails |
| **GV-NEG-12** | Negative | Truncated ciphertext (<64B) | Bounded memory check rejects before decryption |

---

## 5. Verification Boundaries

- **In-Scope (VERIFIED):**
  - Canonical wire-level binary serialization of Install AAD and ACK transcripts.
  - AES-256-GCM encryption/decryption cross-compatibility between Go and ESP-IDF mbedTLS.
  - HKDF-SHA256 and HMAC-SHA256 cross-compatibility.
  - Complete fail-closed negative tamper rejection.
- **Out-of-Scope (Separate Issues):**
  - Mosquitto MQTT 5.0 broker TLS/ACL integration (#174).
  - ESP32 hardware NVS Flash atomic persistence and power-loss fault injection (#175).
  - Production backend and gateway database/NVS wiring.
