# ADR-0001: Hybrid TDMA planning and execution

- **Status:** Accepted as architectural direction; radio performance still NOT_VERIFIED.
- **Context:** Gateway ESP32+SX1276 is a one-radio half-duplex TDMA Master and MQTT bridge.
- **Decision:** Go Backend calculates future versioned slot schedules. Gateway validates/stages/executes them and continues operating without backend connectivity. Nodes timestamp beacon and follow locally authorized slots.
- **Consequences:** A local fallback/bootstrap schedule and RF state machine are mandatory; MQTT message delivery is not a precise TX/RX scheduling clock.
- **Alternatives rejected for MVP:** Cloud-based per-slot activation; ChirpStack/LoRaWAN; Redis/microservices as defaults.
- **Evidence gates:** G1/G2/G3 and timing HIL.
