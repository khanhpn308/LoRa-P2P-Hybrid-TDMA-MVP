# Sensor Node firmware

**Toolchain:** ESP-IDF `v6.1` (ADR-0003; source of truth: `../esp-idf-version.txt`). Gateway and Node CI read the same value. No RF/HIL verification implied.

**Scaffold only.** Target configuration assumes original ESP32 (verify actual board SKU); no radio transmission is enabled.

Future under [#125](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/125): detect violations and trigger local alarm independently; persist Events in a bounded FIFO; transmit only pending Events in approved static DATA slots (W500/G50), receive durable Gateway ACK and retry the same Event only in the next valid own slot. Exhausted retry budget leaves durable pending for recovery. Maintenance Superframes target 300s authenticated 32B HMAC SYNC_BEACON plus a scheduled HEALTH_REPLY / 23B Diagnostic from each Node. Initial Join uses asynchronous CAD (up to 3 retries). Secure onboarding, current rights, airtime admission and fail-closed lost-sync/reboot behavior remain required; N_MISSED > 3 indicates disconnected observability while DATA TX suppresses earlier if drift exceeds guard without reliable sync. No periodic application telemetry or normal priority contention/backoff access path is planned.
