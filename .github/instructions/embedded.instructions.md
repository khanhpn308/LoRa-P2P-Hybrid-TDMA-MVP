---
applyTo: "firmware/**"
---
# Embedded / ESP-IDF rules

Target ESP32 + SX1276, C, ESP-IDF, FreeRTOS. **Single radio owner** serializes SPI and modem state. No blocking operations or SPI in ISR. Timer/IRQ handlers timestamp then notify a bounded task or queue. Prove priorities and jitter on device; do not promise microsecond timing from source inspection alone.

Prefer static buffers, fixed-sized queues and clear ownership; avoid repeated malloc/free in steady-state. Include capacity, timeout and overflow handling. Driver, Radio MAC, Gateway TDMA executor and Node TDMA client stay separate. Never bypass local airtime limits or transmit arbitrary RF frames without verified allowed configuration.

CRC is not cryptographic authentication. Reject unversioned/unvalidated schedule and radio commands. Test actual TX/RX state transitions on hardware.
