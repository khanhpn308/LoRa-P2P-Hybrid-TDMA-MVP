# Sensor Node firmware

**Toolchain:** ESP-IDF `v6.1` (ADR-0003; source of truth: `../esp-idf-version.txt`). Gateway and Node CI read the same value. No RF/HIL verification implied.

**Scaffold only.** Target configuration assumes original ESP32 (verify actual board SKU); no radio transmission is enabled.

Future: sensing/threshold checks, beacon synchronization, approved custom MAC, priority contention/backoff, bounded queue, per-transmitter airtime limiter, secure onboarding, fail-safe lost-sync state.
