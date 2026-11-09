# Gateway Master firmware

**Toolchain:** ESP-IDF `v6.1` (ADR-0003; source of truth: `../esp-idf-version.txt`). Gateway and Node CI read the same value. No RF/HIL verification implied.

Gateway master operates in 24/7 Continuous RX mode on the designated LoRa channel (920.250 MHz VN920), receiving asynchronous CAD + Exponential Backoff event uplinks and OTA join handshakes. Immediate DOWN_EVENT_ACK is returned to nodes upon event reception, and events are committed to local WAL and forwarded to Backend via MQTT.
