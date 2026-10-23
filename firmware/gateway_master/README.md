# Gateway Master firmware

**Toolchain:** ESP-IDF `v6.1` (ADR-0003; source of truth: `../esp-idf-version.txt`). Gateway and Node CI read the same value. No RF/HIL verification implied.

**Scaffold only.** `idf.py set-target esp32 && idf.py build` should compile a log-only app; it does NOT run a TDMA master or transmit RF.

Future components: authenticated custom radio MAC, local TDMA executor, beacon, guard/half-duplex state machine, airtime enforcement, validated active/shadow schedules, bounded uplink queue and TLS MQTT transport. Adapt pins to verified ESP32+SX1276 board pinout.
