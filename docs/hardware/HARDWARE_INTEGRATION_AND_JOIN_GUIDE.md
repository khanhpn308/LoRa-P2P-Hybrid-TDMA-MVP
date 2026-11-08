# Hướng Dẫn Tích Hợp Phần Cứng & Quy Trình V2 Join Protocol

Tài liệu này hướng dẫn chi tiết quy trình kết nối phần cứng, đăng ký danh tính (Provisioning), cấu hình Gateway và thực hiện bắt tay vô tuyến **V2 Join Protocol** cho hệ thống **LoRa P2P Hybrid TDMA (ESP32-WROOM-32E + Semtech SX1276)**.

---

## 1. Sơ Đồ Đấu Nối Phần Cứng Chuẩn HW-001 (Pinout)

Cả **Gateway Master** và **Sensor Node** đều sử dụng chung sơ đồ giao tiếp SPI giữa ESP32 và module Semtech SX1276:

| Chân SX1276 | Chân ESP32 (GPIO) | Ký hiệu Firmware | Ghi chú & Cảnh báo an toàn |
|---|:---:|---|---|
| **VCC** | **3.3V** | `3V3` | ⚠️ **Chỉ dùng 3.3V.** Tuyệt đối không cắm 5V làm hỏng chip. |
| **GND** | **GND** | `GND` | Nối chung mass. |
| **SCK** | **GPIO 5** | `BOARD_LORA_SCK` | SPI Clock. *(ESP32 strapping pin, không kéo trở lên nguồn khi khởi động)*. |
| **MISO** | **GPIO 19** | `BOARD_LORA_MISO` | SPI Master In / Slave Out. |
| **MOSI** | **GPIO 27** | `BOARD_LORA_MOSI` | SPI Master Out / Slave In. |
| **NSS / CS**| **GPIO 18** | `BOARD_LORA_CS` | SPI Chip Select (Active-Low). |
| **RST** | **GPIO 23** | `BOARD_LORA_RST` | Hardware Reset (Active-Low). |
| **DIO0** | **GPIO 26** | `BOARD_LORA_DIO0` | Ngắt cạnh lên phần cứng (TxDone / RxDone). |
| **DIO1 – DIO5** | *Bỏ trống* | `NOT_CONNECTED` | Không nối dây (chuẩn HW-001 không sử dụng). |

### Chân Nút Bấm Kích Hoạt (Wakeup Button trên Sensor Node):
* **Nút bấm rời ngoài:** Nối vào **GPIO 4** (nối xuống GND, kích hoạt mức 0 - Active Low).
* **Nút BOOT có sẵn:** Có thể dùng ngay **nút BOOT (GPIO 0)** trên board mạch ESP32 để kích hoạt thức giấc Deep-sleep mà không cần nối thêm linh kiện.

---

## 2. Thông Số Vô Tuyến Chuẩn MVP (VN920 V1)

Các thông số này đã được định nghĩa chuẩn trong firmware (`docs/hardware/sx1276/SX1276_ACTIVE_PROFILE.md`):
* **Băng tần:** 920.0 – 923.0 MHz (Kênh mặc định thử nghiệm: **CH00 = 920.250 MHz**).
* **Bandwidth (BW):** **125 kHz**.
* **Spreading Factor (SF):** **SF7**.
* **Coding Rate (CR):** **4/5**.
* **Sync Word:** **`0x12`** (Chuẩn LoRa P2P nội bộ; tuyệt đối không dùng `0x34` của LoRaWAN).
* **Preamble Length:** 8 symbols.
* **Payload CRC:** Bật (ON).

---

## 3. Quy Trình 3 Giai Đoạn Tích Hợp Hệ Thống

```
 [Máy tính / Backend]                      [Gateway Master]                    [Sensor Node]
          |                                       |                                  |
          |====== GIAI ĐOẠN 1: PROVISIONING ======|                                  |
          |  (Lấy Token -> Chạy CLI nạp K_JOIN vào NVS qua cáp USB) ---------------->|
          |                                       |                                  |
          |====== GIAI ĐOẠN 2: GATEWAY ONLINE ====|                                  |
          |<-- Wi-Fi & MQTT (gw-a online) --------|                                  |
          |    (Web Dashboard nhảy Gateway 1/1)   |                                  |
          |                                       |                                  |
          |====== GIAI ĐOẠN 3: V2 JOIN HANDSHAKE =|                                  |
          |                                       |<-- [0x45] UP_JOIN_HELLO ---------|
          |<-- MQTT: uplink/join-hello -----------|                                  |
          |                                       |--- [0x46] DOWN_JOIN_GRANT ------>|
          |                                       |    (Hai bên tính khóa X25519)    |
          |                                       |<-- [0x47] KEY_CONFIRM -----------|
          |                                       |--- [0x48] FINISH --------------->|
          |                                       |<-- [0x49] READY -----------------|
          |<-- Kích hoạt ACTIVATED & Gán Slot ----|                                  |
          |    (Web Dashboard nhảy Node 1/1)      |                                  v
          v                                       v                             (Deep-Sleep)
```

---

### GIAI ĐOẠN 1: Provisioning (Đăng Ký Node & Nạp Khóa Gốc NVS)

Mỗi Sensor Node cần một **Khóa gốc Join** ($K_{\text{JOIN}}$ - 256-bit CSPRNG) được nạp vào phân vùng Flash NVS (`0x9000`), đồng thời Backend phải lưu thông tin này vào cơ sở dữ liệu.

1. **Lấy Token xác thực từ Backend (Chạy trong Ubuntu WSL):**
   ```bash
   cd ~/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP

   TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"admin"}' | jq -r .access_token)

   # Kiểm tra token:
   echo $TOKEN
   ```

2. **Cắm mạch Sensor Node vào máy tính qua cổng USB**.
   *(Kiểm tra cổng COM trên Windows, ví dụ `COM5` hoặc `/dev/ttyUSB0` trên Linux)*.

3. **Chạy công cụ Provisioning tự động:**
   ```bash
   python3 tools/provisioning/provision_node.py \
     --port COM5 \
     --backend-url http://localhost:8080 \
     --token "$TOKEN" \
     --network-id 1 \
     --firmware-bin firmware/sensor_node/build/sensor_node.bin
   ```
   **Công cụ sẽ tự động thực hiện:**
   * Đọc địa chỉ MAC phần cứng của chip qua `esptool`.
   * Sinh khóa mật mã ngẫu nhiên an toàn $K_{\text{JOIN}}$ (256-bit).
   * Gửi API `POST /api/v1/devices/provision` đăng ký Node lên Backend.
   * Tạo phân vùng NVS `nvs_credentials.bin` chứa $K_{\text{JOIN}}$, MAC, Network ID.
   * Nạp phân vùng NVS (`offset 0x9000`) và firmware vào Node.

---

### GIAI ĐOẠN 2: Cấu Hình & Khởi Động Gateway Master

1. **Kích hoạt môi trường ESP-IDF v6.1:**
   ```bash
   . /home/khanh/esp/esp-idf-v6.1/export.sh
   cd ~/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/firmware/gateway_master
   ```

2. **Mở menu cấu hình:**
   ```bash
   idf.py menuconfig
   ```
   Vào menu **`Gateway Master Configuration`** và chỉnh:
   * **Gateway Identity:** `gw-a`
   * **Gateway WiFi SSID:** Tên mạng Wi-Fi của bạn (băng tần 2.4 GHz).
   * **Gateway WiFi Password:** Mật khẩu mạng Wi-Fi.
   * **MQTT Broker URI override:** 
     ```text
     mqtt://192.168.88.113:1883
     ```
   *Lưu cấu hình (`S` -> Enter) và thoát (`Esc`)*.

3. **Build và nạp code cho Gateway:**
   ```bash
   idf.py build
   idf.py -p COM7 flash monitor   # Thay COM7 bằng cổng của Gateway
   ```

4. **Kiểm tra trạng thái:**
   * Log Gateway sẽ báo: kết nối Wi-Fi thành công -> kết nối MQTT thành công -> gửi thông điệp `online` lên topic `iot/v1/gw/gw-a/uplink/status`.
   * Mở trình duyệt Dashboard (`http://localhost:3000`):
     👉 **Thẻ Gateway chuyển sang `1/1` (Đã kết nối: 1, Hoạt động: 1)**.

---

### GIAI ĐOẠN 3: Bắt Tay Vô Tuyến V2 Join Handshake

Khi Node được cấp nguồn lần đầu:
1. **Node phát `UP_JOIN_HELLO` (`0x45`, 68 Bytes):**
   * Quét kiểm tra kênh sạch (CAD).
   * Tăng biến đếm `JOIN_COUNTER` trong NVS chống tấn công lặp lại.
   * Sinh khóa tạm thời Curve25519 (`X25519 Pub_Node`, `Nonce`).
   * Tính mã xác thực `JOIN_PROOF` từ $K_{\text{JOIN}}$ và phát qua sóng LoRa.
2. **Gateway Relay lên Backend:**
   * Gateway thu được gói tin qua SX1276 -> Bắn MQTT lên `iot/v1/gw/gw-a/uplink/join-hello`.
3. **Gateway trả lời `DOWN_JOIN_GRANT` (`0x46`, 66 Bytes):**
   * Gửi về `X25519 Pub_GW`, `GW_NONCE` và `GRANT_PROOF`.
4. **Phái sinh khóa phiên Session Keys:**
   * Hai bên tính khóa chung bí mật $Z = \text{X25519}(\text{priv}, \text{pub})$.
   * Dùng HKDF SHA-256 tạo cặp khóa phiên:
     * $K_{\text{SESSION\_UP}}$ (mã hóa gói tin gửi lên).
     * $K_{\text{SESSION\_DL}}$ (mã hóa gói tin gửi xuống).
5. **Hoàn tất bắt tay và Cấp phát Slot TDMA:**
   * Hai bên xác thực các gói tin cuối: `KEY_CONFIRM` (`0x47`) -> `FINISH` (`0x48`) -> `READY` (`0x49`).
   * Backend kích hoạt Node sang **`ACTIVATED`** và gán khe thời gian TDMA (`assigned_slot_id`).
   * Node lưu session keys vào RTC RAM và chuyển sang trạng thái ngủ Deep-Sleep.
   * 👉 **Trên Web Dashboard:** Thẻ **Node** tự động nhảy số thành **`1/1`**.

---

## 4. Thử Nghiệm Kích Hoạt Sự Kiện Báo Động (Live Alarm Test)

Sau khi Join thành công:
1. Nhấn nút bấm trên Node (GPIO 4 hoặc nút BOOT GPIO 0).
2. **Quan sát luồng xử lý:**
   * Node thức giấc (`Button Wakeup`) -> Đóng gói bản tin sự kiện -> Mã hóa bằng khóa $K_{\text{SESSION\_UP}}$.
   * Chờ đến khe thời gian TDMA của mình -> Phát sóng LoRa tới Gateway.
   * Gateway nhận gói tin -> Bắn MQTT lên Backend -> Backend lưu DB và đẩy qua WebSocket.
3. **Hiệu ứng trên Web Dashboard:**
   * Mốc thời gian **"Cập nhật: HH:MM:SS"** tự động nhảy sang thời gian thực.
   * Thẻ **Sự kiện lỗi** tăng số (từ 0 lên 1).
   * Popup Toast thông báo màu đỏ hiển thị tức thì trên màn hình:
     `[Realtime] Cảnh báo mới từ Node #...`.
