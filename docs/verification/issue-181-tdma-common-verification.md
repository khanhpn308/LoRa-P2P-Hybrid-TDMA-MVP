# TDMA Common Structures Component Verification Report (Issue #181)

> **Document Status:** `IMPLEMENTED_AND_BUILD_VERIFIED`
> **Source Issue:** [#181](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/181)
> **Related Issue:** [#187](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/187)
> **Component:** `firmware/components/tdma_common`
> **Toolchain:** ESP-IDF v6.1 (Official Docker image `espressif/idf:v6.1`)

---

## 1. Summary

The `tdma_common` component provides standard superframe, subframe, and slot timing calculations for the Hybrid TDMA architecture according to Profile P-10S-15 (`contracts/radio-mac/tdma-schedule.md`):
- Baseline timing constants:
  - Superframe duration: 10,000 ms (`TDMA_SUPERFRAME_MS`).
  - Subframes per superframe: 5 (`TDMA_SUBFRAME_COUNT`).
  - Subframe duration: 2,000 ms (`TDMA_SUBFRAME_MS`).
  - Slot duration: 400 ms (`TDMA_SLOT_DURATION_MS`).
  - Data slots per subframe: 3 (`TDMA_DATA_SLOTS_PER_SUBFRAME`).
  - Total data slots per superframe: 15 (`TDMA_TOTAL_DATA_SLOTS`).
- Subframe timing windows (ms from subframe start):
  - Beacon (SF0) or Downlink (SF1..SF4) window: 0..250 ms (`TDMA_BCN_DL_WINDOW_START_MS` .. `TDMA_BCN_DL_WINDOW_END_MS`).
  - Priority Contention Slot (PCSS) window: 250..650 ms (`TDMA_PCSS_WINDOW_START_MS` .. `TDMA_PCSS_WINDOW_END_MS`).
  - Dedicated DATA slots section: 650..1850 ms (`TDMA_DATA_SECTION_START_MS`, 3 × 400 ms slots).
- Intra-slot partitioning (400 ms total):
  - Leading guard: 0..25 ms (`TDMA_SLOT_LEADING_GUARD_MS`).
  - Node transmission budget: 25..125 ms (`TDMA_SLOT_TX_BUDGET_MS`).
  - Radio turnaround / RX setup: 125..145 ms (`TDMA_SLOT_TURNAROUND_MS`).
  - Gateway ACK budget: 145..245 ms (`TDMA_SLOT_ACK_BUDGET_MS`).
  - Trailing guard & margin: 245..400 ms (`TDMA_SLOT_TRAILING_GUARD_MS`).
- Monotonic millisecond slot offset calculation: `tdma_get_slot_start_offset_ms(slot_id, &out_offset_ms)`.
- Bilateral clock drift safety guard calculation: `tdma_calculate_drift_guard_ms(ppm, interval_s)` with minimum 5 ms base guard.
- Zero dynamic allocation (`malloc`/`free` forbidden).

## 2. API Contract

- `esp_err_t tdma_common_init(void)`: Initialize shared TDMA common structures (logs startup banner).
- `bool tdma_is_valid_slot_id(uint8_t slot_id)`: Check whether slot_id is within valid data slot range (`1 <= slot_id <= TDMA_TOTAL_DATA_SLOTS`).
- `esp_err_t tdma_get_slot_start_offset_ms(uint8_t slot_id, uint32_t *out_offset_ms)`: Calculate slot start offset in milliseconds within the 10,000 ms superframe (`ESP_ERR_INVALID_ARG` if slot_id invalid or out_offset_ms NULL).
- `uint32_t tdma_calculate_drift_guard_ms(uint32_t clock_drift_ppm, uint32_t interval_s)`: Compute bilateral clock drift safety guard in milliseconds based on crystal PPM drift and interval elapsed since last beacon.
