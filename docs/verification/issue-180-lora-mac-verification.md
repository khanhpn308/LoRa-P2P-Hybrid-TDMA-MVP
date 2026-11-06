# LoRa MAC Framing Component Verification Report (Issue #180, #186)

> **Document Status:** `IMPLEMENTED_AND_BUILD_VERIFIED`
> **Source Issue:** [#180](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/180), [#186](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/186)
> **Component:** `firmware/components/lora_mac`
> **Toolchain:** ESP-IDF v6.1 (Official Docker image `espressif/idf:v6.1`)
> **Governing Authorities:** ADR-0003, C Coding Standard v2, contracts/radio-mac/specification.md (Revision 0.1.0-draft)

---

## 1. Summary

The `lora_mac` component defines the shared custom P2P MAC header framing protocol and parser/encoder for the LoRa P2P Hybrid TDMA MVP:
- **Magic byte validation:** `0xA5` (`LORA_MAC_MAGIC_BYTE`).
- **8-byte fixed header layout:** `[magic (8) | version (2) + msg_type (6) | flags (8) | src_id (8) | dst_id (8) | sched_ver (8) | seq_num (8) | payload_len (8)]`.
- **Bounded payload capacity:** maximum 48 bytes (`LORA_MAC_MAX_PAYLOAD_LEN = 48U`), conforming to candidate envelope specification in `contracts/radio-mac/specification.md` (maximum candidate frame size: 8-byte header + 48-byte payload + 2-byte CRC = 58 bytes, well within the SX1276 255-byte FIFO limit).
- **Strictly non-allocating parser & encoder:** `lora_mac_header_parse` and `lora_mac_header_encode` perform zero dynamic allocation (`malloc`/`free` forbidden per C Standard v2 `MEM-001`).
- **Standardized message types (`lora_mac_msg_type_t`):**
  - `LORA_MAC_TYPE_BEACON` (`0x01`): Gateway -> Broadcast: Superframe sync & ACK bitmap.
  - `LORA_MAC_TYPE_SCHED_ANNOUNCE` (`0x02`): Gateway -> Broadcast/Node: Slot allocation mapping update.
  - `LORA_MAC_TYPE_DATA_TELEMETRY` (`0x03`): Node -> Gateway: Periodic sensor telemetry payload in assigned TDMA slot.
  - `LORA_MAC_TYPE_PRIORITY_ALERT` (`0x04`): Node -> Gateway: High-priority alarm event in priority contention slot.
  - `LORA_MAC_TYPE_ACK_PACKET` (`0x05`): Gateway -> Node: Frame acknowledgment.
  - `LORA_MAC_TYPE_CMD_DOWNLINK` (`0x06`): Gateway -> Node: Downlink command from backend.
  - `LORA_MAC_TYPE_JOIN_SLOT_REQ` (`0x07`): Node -> Gateway: Initial dynamic join request.
  - `LORA_MAC_TYPE_JOIN_SLOT_RSP` (`0x08`): Gateway -> Node: Dynamic join response with slot assignment.

---

## 2. API Contract & Wire Format

### 2.1 Wire Envelope Format

| Byte Offset | Field Name | Description | Accepted / Checked Values |
|---:|---|---|---|
| 0 | `magic` | Frame synchronization / magic byte | Must equal `0xA5` (`LORA_MAC_MAGIC_BYTE`) |
| 1 | `ver_type` | Packed version (bits 7..6) + type (bits 5..0) | Version must be `0x01` (`LORA_MAC_PROTOCOL_VERSION_DRAFT`) or `0x00` (legacy test); types `0x01`..`0x08` |
| 2 | `flags` | Control flags | Bitmask (`ACK_REQ`, `IS_RETRY`, `PENDING_SCHED`, `DUTY_LIMITED`) |
| 3 | `src_id` | Source device identifier | `0x00` = Gateway, `1..254` = Node |
| 4 | `dst_id` | Destination device identifier | `0x00` = Gateway, `1..254` = Node, `0xFF` = Broadcast |
| 5 | `sched_ver` | TDMA schedule version tag | `uint8_t` version tag |
| 6 | `seq_num` | Frame sequence number | `uint8_t` frame sequence number |
| 7 | `payload_len` | Payload length in bytes | Bounded range `0..48` bytes (`LORA_MAC_MAX_PAYLOAD_LEN`) |

### 2.2 Error Semantics

- **`lora_mac_header_parse`**:
  - `ESP_ERR_INVALID_ARG`: NULL `raw_buf` or NULL `out_hdr`.
  - `ESP_ERR_INVALID_SIZE`: buffer length `< 8` bytes (`LORA_MAC_HEADER_LEN`), or parsed `payload_len > 48`.
  - `ESP_ERR_INVALID_VERSION`: `raw_buf[0] != 0xA5`, or version field `> 1` (bits 7..6).
  - `ESP_OK`: Valid header successfully unpacked.

- **`lora_mac_header_encode`**:
  - `ESP_ERR_INVALID_ARG`: NULL `hdr` or NULL `out_buf`.
  - `ESP_ERR_NO_MEM`: destination capacity `buf_size < 8` bytes (`LORA_MAC_HEADER_LEN`).
  - `ESP_ERR_INVALID_SIZE`: `hdr->payload_len > 48` bytes.
  - `ESP_OK`: 8 bytes written into `out_buf`, `*out_written` set to 8.

---

## 3. Unit Test Verification (Issue #186)

A dedicated test suite in `tests/unit/test_lora_mac.c` and `tests/unit/test_lora_mac.py` executes host and native unit tests:

1. **Lifecycle initialization:** `lora_mac_init()` executes and returns `ESP_OK`.
2. **Round-trip serialization & deserialization:**
   - Populates test header with known fields (`magic = 0xA5`, `version = 0x01`, `msg_type = 0x03`, `flags = 0x30`, `src_id = 0x0A`, `dst_id = 0x00`, `sched_ver = 0x02`, `seq_num = 0x42`, `payload_len = 16`).
   - Verifies exact wire byte representation.
   - Decodes wire bytes and asserts all struct fields match input.
3. **All Message Types:** Encodes and parses all 8 enum types (`0x01` through `0x08`) verifying message type preservation.
4. **Boundary conditions:** Tests payload length boundaries `0`, `1`, `47`, and `48` bytes (`LORA_MAC_MAX_PAYLOAD_LEN`).
5. **Parse negative test cases:**
   - NULL input buffer or NULL output struct pointer returns `ESP_ERR_INVALID_ARG`.
   - Truncated buffers (`0`, `1`, `7` bytes) return `ESP_ERR_INVALID_SIZE`.
   - Magic mismatches (`0x5A`, `0x00`, `0xFF`) return `ESP_ERR_INVALID_VERSION`.
   - Invalid versions (`0x02`, `0x03`) return `ESP_ERR_INVALID_VERSION`.
   - Oversized payload lengths (`49`, `100`, `255`) return `ESP_ERR_INVALID_SIZE`.
6. **Encode negative test cases:**
   - NULL header or NULL output buffer pointer returns `ESP_ERR_INVALID_ARG`.
   - Destination buffers smaller than header (`0`, `1`, `7` bytes) return `ESP_ERR_NO_MEM`.
   - Header with payload length exceeding 48 bytes (`49`, `100`, `255`) returns `ESP_ERR_INVALID_SIZE`.

---

## 4. C Coding Standard v2 Compliance Checklist

| Rule ID | Requirement | Verification Method | Status |
|---|---|---|---|
| `MEM-001` | Zero dynamic memory allocation (`malloc`/`free` forbidden) | Static inspection of `src/lora_mac.c` and `test_lora_mac.c` | **PASS** |
| `ERR-001` | Strict bounds and error code checking | Unit test coverage of all negative conditions | **PASS** |
| `SEC-001` | Reject invalid magic, version, and length before dispatch | Verified in `lora_mac_header_parse` | **PASS** |
| `SEC-002` | Explicit octet serialization; no raw struct casting to wire | Offset-by-offset byte packing in `src/lora_mac.c` | **PASS** |
| `C-002` | Namespaced identifiers (`lora_mac_*`) | Header and source symbol review | **PASS** |
| `C-007` | Fixed-width types (`uint8_t`, `size_t`) for binary protocols | Inspected in `lora_mac.h` | **PASS** |
| `QA-004` | Boundary and negative test verification | Validated with host unit tests | **PASS** |
