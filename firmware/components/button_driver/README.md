# button_driver

Reusable ESP-IDF component for hardware push-button handling, debounce qualification, and Deep-Sleep EXT0 wake-up management.

## Features
- **Pin Safety & Collision Prevention:** Rejects GPIO assignments conflicting with SX1276 SPI bus (GPIO 5, 18, 19, 23, 26, 27) and UART console (GPIO 1, 3).
- **RTC Wakeup Validation:** Validates selected pin is an RTC-capable GPIO for ESP32 Deep-Sleep EXT0 wake-up.
- **Hardware/Software Debounce:** Multi-sample qualification to reject mechanical contact bounce and electrical noise pulses.
- **Anti-Storm / Anti-Loop Protection:** Waits for button release before arming EXT0 sleep to prevent continuous wake storms when held down.
