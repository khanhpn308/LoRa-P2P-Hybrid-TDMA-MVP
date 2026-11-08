# OLED SSD1306 Component

Driver component for 0.96-inch 128x64 OLED display using SSD1306 controller over I2C on ESP-IDF v6.1.

## Authority & Scope
- **Issue**: #271 (`[Firmware][Node] Hiển thị giá trị nút nhấn và thời gian nhận sự kiện trên OLED SSD1306 I2C`)
- **Coding Standard**: C Coding Standard v2 (GOV-001..010, C-001..020, MEM-001..008, ERR-001..007, RTOS-003)
- **Framework**: ESP-IDF v6.1 (`driver/i2c_master.h` via `esp_driver_i2c`)

## Pin Assignment & Hardware Constraints
- Default SDA: **GPIO 21**
- Default SCL: **GPIO 22**
- Default I2C Address: **0x3C** (alternative: **0x3D**)
- **Validation**:
  - Rejects SPI Flash GPIOs (6..11)
  - Rejects Input-Only GPIOs (34..39)
  - Rejects SX1276 HW-001 Pins (SCK=5, CS=18, MISO=19, RST=23, DIO0=26, MOSI=27)
  - Rejects UART0 Console Pins (TX=1, RX=3)
  - Rejects Button Wakeup Pin conflict
  - Rejects identical SDA/SCL assignment

## Memory & Execution Context
- Framebuffer: 1024 bytes statically allocated within device handle.
- Zero dynamic heap allocation (`malloc`/`free` not used).
- Execution Context: FreeRTOS task/application context only. MUST NOT be invoked from ISR context (RTOS-003).

## Power & Deep-Sleep Notice
- ESP32 powers down the standard I2C peripheral upon entering Deep-Sleep.
- Whether the OLED panel remains lit or dark during deep sleep depends on external module wiring and VCC persistence.
- Per Issue #271 acceptance criteria: deep sleep display behavior must be verified on physical hardware (HIL); do not assume display stays on without measurement.
