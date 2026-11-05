# LoRa MAC Framing Component Verification Report (Issue #180)

> **Document Status:** `IMPLEMENTED_AND_BUILD_VERIFIED`
> **Source Issue:** [#180](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/180)
> **Component:** `firmware/components/lora_mac`
> **Toolchain:** ESP-IDF v6.1 (Official Docker image `espressif/idf:v6.1`)

---

## 1. Summary

The `lora_mac` component defines the shared custom P2P MAC header and framing protocol:
- Magic byte validation: `0xA5` (`LORA_MAC_MAGIC_BYTE`).
- 8-byte fixed header: `[magic (8) | version (2) + msg_type (6) | flags (8) | src_id (8) | dst_id (8) | sched_ver (8) | seq_num (8) | payload_len (8)]`.
- Bounded payload capacity: maximum 247 bytes (`LORA_MAC_MAX_PAYLOAD_LEN`), conforming to Semtech SX1276 255-byte FIFO limit (`8 + 247 = 255`).
- Strictly non-allocating parser `lora_mac_header_parse` and encoder `lora_mac_header_encode`.
- Protocol message types: Beacon (`0x01`), Join Request (`0x02`), Join Accept (`0x03`), Uplink Data (`0x04`), Downlink Ack (`0x05`), Emergency Alert (`0x06`), Schedule Update (`0x07`).
- Zero dynamic allocation (`malloc`/`free` forbidden).
