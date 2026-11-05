# TDMA Common Structures Component Verification Report (Issue #181)

> **Document Status:** `IMPLEMENTED_AND_BUILD_VERIFIED`
> **Source Issue:** [#181](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/181)
> **Component:** `firmware/components/tdma_common`
> **Toolchain:** ESP-IDF v6.1 (Official Docker image `espressif/idf:v6.1`)

---

## 1. Summary

The `tdma_common` component provides standard superframe, subframe, and slot timing calculations for the Hybrid TDMA architecture (Profile P-10S-15):
- Baseline timing constants:
  - Superframe duration: 10,000 ms (`TDMA_SUPERFRAME_MS`).
  - Subframes per superframe: 2 (`TDMA_SUBFRAMES_PER_SUPERFRAME`).
  - Subframe duration: 5,000 ms (`TDMA_SUBFRAME_MS`).
  - Beacon duration: 250 ms (`TDMA_BEACON_DURATION_MS`).
  - Contention Access Period (CAP): 750 ms (`TDMA_CAP_DURATION_MS`).
  - Slot duration: 500 ms (`TDMA_SLOT_DURATION_MS`).
  - Slots per subframe: 8 (`TDMA_DATA_SLOTS_PER_SUBFRAME`).
  - Total data slots per superframe: 16 (`TDMA_TOTAL_DATA_SLOTS`).
- Monotonic microsecond slot offset conversion: `tdma_get_slot_start_offset_ms(slot_id, &out_offset_ms)`.
- Bilateral clock drift safety guard calculation: `tdma_calculate_drift_guard_ms(ppm, interval_s)` with minimum 5 ms base guard.
- Zero dynamic allocation (`malloc`/`free` forbidden).
