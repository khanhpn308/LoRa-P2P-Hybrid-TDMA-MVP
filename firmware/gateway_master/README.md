# Gateway Master firmware

**Scaffold only.** `idf.py set-target esp32 && idf.py build` should compile a log-only app; it does NOT run a TDMA master or transmit RF.

Future components: authenticated custom radio MAC, local TDMA executor, beacon, guard/half-duplex state machine, airtime enforcement, validated active/shadow schedules, bounded uplink queue and TLS MQTT transport. Adapt pins to verified ESP32+SX1276 board pinout.
