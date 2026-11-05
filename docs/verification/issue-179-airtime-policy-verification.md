# Airtime Policy Component Verification Report (Issue #179)

> **Document Status:** `IMPLEMENTED_AND_BUILD_VERIFIED`
> **Source Issue:** [#179](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/179)
> **Component:** `firmware/components/airtime_policy`
> **Toolchain:** ESP-IDF v6.1 (Official Docker image `espressif/idf:v6.1`)

---

## 1. Summary

The `airtime_policy` component implements bounded duty cycle and Time-on-Air (ToA) airtime tracking for the LoRa P2P Hybrid TDMA system:
- Strict zero dynamic allocation (`malloc`/`free` forbidden).
- Enforces duty cycle ceiling (default 10 permille / 1%) per rolling 1-hour window (3,600,000 ms).
- Provides pre-flight check `airtime_policy_check(packet_toa_ms)` failing closed (`ESP_ERR_INVALID_STATE`) when projected TX exceeds budget.
- Integrates with ESP-IDF `esp_timer` monotonic timestamping.
- No direct radio transmission or hardware SPI dependency.

## 2. API Contract

- `esp_err_t airtime_policy_init(uint16_t max_permille)`: Initialize airtime window and permille limit (1-1000).
- `esp_err_t airtime_policy_check(uint32_t packet_toa_ms)`: Verify if prospective packet fits within remaining budget.
- `esp_err_t airtime_policy_record_tx(uint32_t packet_toa_ms)`: Accumulate airtime upon successful transmission.
- `uint32_t airtime_policy_get_remaining_budget_ms(void)`: Return remaining transmission budget in milliseconds.
- `uint32_t airtime_policy_get_accumulated_tx_ms(void)`: Return total airtime consumed in current window.
- `void airtime_policy_reset(void)`: Reset accumulator at start of window.
