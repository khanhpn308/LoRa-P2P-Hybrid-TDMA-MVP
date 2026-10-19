# Hardware in the loop (HIL)

Run on instrumented ESP32/SX1276 boards with test configuration, firmware SHA, UART log, timestamps and RF instrumentation. Hardware runner and bench setup are NOT present yet.

Gate G1: two-device TX/RX RF and measured time-on-air.
Gate G2/G3: 10–15 nodes, slot drift, simultaneous alerts, reset, lost beacon, local duty limits.
Never claim simulator PASS equals HIL PASS.
