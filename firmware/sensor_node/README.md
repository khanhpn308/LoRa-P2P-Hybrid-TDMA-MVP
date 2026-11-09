# Sensor Node firmware

**Toolchain:** ESP-IDF `v6.1` (ADR-0003; source of truth: `../esp-idf-version.txt`). Gateway and Node CI read the same value. No RF/HIL verification implied.

Sensor Node operates using a Pure CAD CSMA/CA MAC protocol on 920.250 MHz (VN920 CH0). The node persists events in an RTC-backed FIFO across deep-sleep boots. When awakened by button press (EXT0) or periodic timer, it performs CAD with exponential random backoff (up to 3 retries), transmits encrypted UP_EVENT packets, listens for DOWN_EVENT_ACK (400ms window), puts the SX1276 into sleep mode, and enters ESP32 deep sleep. Initial onboarding uses an asynchronous OTA V2 Join Handshake.
