# Kịch Bản Kiểm Thử Phần Cứng (Hardware Test Scenarios)
ESP32-WROOM-32E + SX1276 | LoRa P2P Hybrid TDMA MVP

---

## Danh Mục Phần Cứng & Cổng Mặc Định

| Thiết bị | Vai trò | Cổng Serial Mặc định | Chân Nút Bấm | Chân Kẹp Logic Analyzer (DIO0 / CS) |
|---|---|---|---|---|
| Board A | **Gateway Master** | `/dev/ttyUSB0` (hoặc COM3) | — | Ch 0 (DIO0: GPIO26), Ch 1 (CS: GPIO18) |
| Board B | **Sensor Node 1** | `/dev/ttyUSB1` (hoặc COM4) | GPIO 4 | Ch 2 (DIO0: GPIO26), Ch 3 (CS: GPIO18) |
| Board C | **Sensor Node 2** | `/dev/ttyUSB2` (hoặc COM5) | GPIO 4 | Ch 4 (DIO0: GPIO26), Ch 5 (CS: GPIO18) |

---

## Kịch Bản 1: Nạp Khóa Định Danh `K_JOIN` (Node Provisioning & NVS Flashing)

### 1. Trường hợp test
Nạp định danh mạng, `NETWORK_ID`, bộ đếm `JOIN_COUNTER` và khóa gốc `K_JOIN` vào phân vùng NVS của Sensor Node từ công cụ nạp nhà máy CLI, đăng ký thông tin với Backend.

### 2. Thư mục chạy
```bash
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP
```

### 3. Thông số cấu hình
* Phân vùng NVS: Offset `0x9000` (36864), Size `0x6000` (24576 bytes).
* Baud rate: `460800`.
* Network ID: `1`.

### 4. Lệnh chạy

#### Cách 1.1: Nạp offline (chưa cần kết nối Backend)
```bash
python3 tools/provisioning/provision_node.py \
    --port /dev/ttyUSB1 \
    --baud 460800 \
    --network-id 1 \
    --generation 1 \
    --initial-join-counter 0 \
    --skip-backend \
    --outdir /tmp/prov_node1 \
    --keep-artifacts
```

#### Cách 1.2: Nạp online (có Backend REST API đang chạy)
```bash
python3 tools/provisioning/provision_node.py \
    --port /dev/ttyUSB1 \
    --baud 460800 \
    --backend-url http://localhost:8080 \
    --token "<ADMIN_JWT_TOKEN>" \
    --network-id 1 \
    --generation 1 \
    --initial-join-counter 0
```

### 5. Thông số cần thu thập
* MAC address 12-hex đọc từ chip eFuse (ví dụ: `A4CF129B3C44`).
* File partition nhị phân sinh ra: `/tmp/prov_node1/nvs_partition.bin`.
* Log nạp: `Hash of data verified.` và `Wrote 24576 bytes...`.
* Trạng thái đăng ký Backend (nếu online): `HTTP 201 Created` trả về Device UUID.

---

## Kịch Bản 2: Node Mới Join Mạng (Join Handshake & Kích Hoạt Phiên)

### 1. Trường hợp test
Node chưa có khóa phiên phát tín hiệu Join Request (chứa Ephemeral Public Key X25519) qua sóng $\to$ Gateway tiếp nhận, chuyển tiếp lên Backend qua MQTT $\to$ Backend xác thực và phản hồi Join Accept $\to$ Gateway phát sóng Accept $\to$ Node xác lập khóa phiên `K_SESSION_UP` / `K_SESSION_DL`.

### 2. Thư mục chạy
* Backend Go: `backend-go`
* Gateway: `firmware/gateway_master`
* Node: `firmware/sensor_node`

### 3. Thông số menuconfig

#### Gateway (`firmware/gateway_master`):
```text
CONFIG_SX1276_RF_TX_ENABLE=y
CONFIG_SX1276_PA_PATH_BOOST=y
CONFIG_SX1276_TX_POWER_DBM=2
CONFIG_SX1276_CHANNEL_CH00=y
CONFIG_GATEWAY_ID="gw-a"
CONFIG_GATEWAY_WIFI_SSID="<WIFI_SSID>"
CONFIG_GATEWAY_WIFI_PASSWORD="<WIFI_PASSWORD>"
CONFIG_GATEWAY_BROKER_HOST="192.168.1.10"
CONFIG_GATEWAY_BROKER_PORT=8883
```

#### Node (`firmware/sensor_node`):
```text
CONFIG_SX1276_RF_TX_ENABLE=y
CONFIG_SX1276_PA_PATH_BOOST=y
CONFIG_SX1276_TX_POWER_DBM=2
CONFIG_SX1276_CHANNEL_CH00=y
CONFIG_NODE_TDMA_NODE_ID=1
CONFIG_NODE_TDMA_GATEWAY_ID=1
```

### 4. Lệnh chạy

#### Cửa sổ 1 - Khởi động Backend:
```bash
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/backend-go
go run cmd/server/main.go
```

#### Cửa sổ 2 - Nạp & Bật Monitor Gateway:
```bash
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/firmware/gateway_master
idf.py -p /dev/ttyUSB0 flash monitor
```

#### Cửa sổ 3 - Nạp & Bật Monitor Node:
```bash
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/firmware/sensor_node
idf.py -p /dev/ttyUSB1 flash monitor
```

### 5. Thông số cần thu thập
* Node Serial: `JOIN_COUNTER` tăng 1 trong NVS flash, in mã `UP_JOIN_REQUEST (0x45)`.
* Gateway Serial: Nhận `UP_JOIN_REQUEST`, đẩy MQTT topic `iot/v1/gw/gw-a/join/request`.
* Backend Log: Xác minh HMAC thẻ Join, sinh bộ khóa phiên, publish `iot/v1/gw/gw-a/join/accept`.
* Gateway Serial: Nhận MQTT, phát `DOWN_JOIN_ACCEPT (0x46)` trên RF.
* Node Serial: Nhận `DOWN_JOIN_ACCEPT`, tính khóa chung ECDH X25519 thành công, chuyển trạng thái sang `INSTALLED_INACTIVE` $\to$ sẵn sàng nhận lịch.

---

## Kịch Bản 3: Phân Lịch & Cập Nhật Lịch TDMA (Schedule Distribution)

### 1. Trường hợp test
Backend lập lịch và phát hành bản lịch mới qua MQTT $\to$ Gateway tiếp nhận, lưu trữ và cập nhật vào chu kỳ phát sóng Superframe `DOWN_SYNC_BEACON` (Slot 0).

### 2. Thư mục chạy
```bash
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP
```

### 3. Thông số cấu hình
* Lập lịch 2 khe: Node 1 $\to$ Slot 1, Node 2 $\to$ Slot 2.
* Chu kỳ Superframe: 10,000 ms.
* Schedule Version: `2`.

### 4. Lệnh chạy
```bash
curl -X POST http://localhost:8080/api/v1/schedules \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "network_id": 1,
    "schedule_version": 2,
    "superframe_duration_ms": 10000,
    "beacon_window_ms": 500,
    "slot_duration_ms": 600,
    "slot_guard_ms": 50,
    "slots": [
      {"slot_index": 1, "node_id": 1},
      {"slot_index": 2, "node_id": 2}
    ]
  }'
```

### 5. Thông số cần thu thập
* Backend: HTTP Response `200 OK` kèm `schedule_id`.
* Gateway Monitor:
  * Log MQTT: `Downlink schedule received (X bytes)` trên topic `iot/v1/gw/gw-a/control/schedule`.
  * Log Master Engine: Cập nhật `sched_ver = 2`.
  * Log Beacon: `DOWN_SYNC_BEACON` phát ở đầu chu kỳ mang byte `SCHED_VER = 0x02`.

---

## Kịch Bản 4: Giao Tiếp Dữ Liệu Node $\leftrightarrow$ Gateway (`UP_EVENT` $\leftrightarrow$ `DOWN_EVENT_ACK`)

### 1. Trường hợp test
Node 1 đang ngủ Deep-Sleep $\to$ Nhấn nút vật lý $\to$ Wake up $\to$ Bắt Beacon $\to$ Chờ đúng Slot 1 $\to$ Bắn `UP_EVENT` (26B) $\to$ Gateway thu, kiểm tra chống phát lại, giải mã AES-CCM-8 $\to$ Phản hồi tức thì `DOWN_EVENT_ACK` (19B) $\to$ Node xóa hàng đợi và ngủ lại.

### 2. Thư mục chạy
* Gateway: `firmware/gateway_master`
* Node 1: `firmware/sensor_node`

### 3. Thông số menuconfig

#### Gateway (`firmware/gateway_master`):
```text
CONFIG_SX1276_RF_TX_ENABLE=y
CONFIG_SX1276_PA_PATH_BOOST=y
CONFIG_SX1276_TX_POWER_DBM=2
CONFIG_SX1276_CHANNEL_CH00=y
```

#### Node 1 (`firmware/sensor_node`):
```text
CONFIG_SX1276_RF_TX_ENABLE=y
CONFIG_SX1276_PA_PATH_BOOST=y
CONFIG_SX1276_TX_POWER_DBM=2
CONFIG_SX1276_CHANNEL_CH00=y
CONFIG_NODE_TDMA_NODE_ID=1
CONFIG_NODE_BUTTON_GPIO=4
CONFIG_NODE_BUTTON_ACTIVE_LEVEL=0
CONFIG_NODE_BUTTON_DEBOUNCE_MS=50
CONFIG_NODE_BUTTON_HOLD_TIME_MS=20
CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC=0
```

### 4. Lệnh chạy

#### Terminal 1 - Nạp và theo dõi Gateway:
```bash
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/firmware/gateway_master
idf.py -p /dev/ttyUSB0 flash monitor
```

#### Terminal 2 - Nạp và theo dõi Node 1:
```bash
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/firmware/sensor_node
idf.py -p /dev/ttyUSB1 flash monitor
```

#### Thao tác:
Nhấn nút bấm vật lý (nối GPIO 4 xuống GND) trên Board Node 1.

### 5. Thông số cần thu thập
* **Node Monitor:**
  * `[WAKE CAUSE] EXT0 Button Wakeup detected on GPIO 4`
  * `>>> EVENT ENQUEUED <<< Ref: 1`
  * `Beacon sync successful (SF_SEQ: X, Epoch: Y)`
  * `Executing TDMA transmission cycle for 1 pending event(s)...`
  * `TDMA cycle completed (status: ESP_OK, client state: REARM_SLEEP, remaining pending: 0)`
  * `Entering Deep-Sleep mode.`
* **Gateway Monitor:**
  * Slot 0: Phát `DOWN_SYNC_BEACON` (32 bytes).
  * Slot 1: Nhận frame 26 bytes từ `Node ID = 1`, frame counter tăng hợp lệ, CCM tag khớp.
  * Phát phản hồi `DOWN_EVENT_ACK` (19 bytes) trong cùng Slot 1.
* **Logic Analyzer:**
  * Kẹp `DIO0` (GPIO26) của Node 1 và Gateway:
    * Đo ToA `UP_EVENT`: ~61.7 ms (SF7) hoặc ~113.2 ms (SF8).
    * Đo độ trễ xử lý (Turnaround) của Gateway: < 20 ms.
    * Đo ToA `DOWN_EVENT_ACK`: ~51.5 ms (SF7) hoặc ~102.9 ms (SF8).

---

## Kịch Bản 5: Phân Khe Tĩnh TDMA (Multi-Node Slotted Verification: Node 1 & Node 2)

### 1. Trường hợp test
Cấu hình 2 Node khác nhau: Node 1 gán Slot 1, Node 2 gán Slot 2. Kích hoạt cả hai phát dữ liệu. Xác minh mỗi Node phát đúng khe thời gian riêng biệt, không đè sóng nhau.

### 2. Thư mục chạy
```bash
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/firmware/sensor_node
```

### 3. Thông số menuconfig

#### Node 1:
```text
CONFIG_NODE_TDMA_NODE_ID=1
CONFIG_NODE_BUTTON_GPIO=4
CONFIG_SX1276_RF_TX_ENABLE=y
CONFIG_SX1276_PA_PATH_BOOST=y
CONFIG_SX1276_TX_POWER_DBM=2
```

#### Node 2:
```text
CONFIG_NODE_TDMA_NODE_ID=2
CONFIG_NODE_BUTTON_GPIO=4
CONFIG_SX1276_RF_TX_ENABLE=y
CONFIG_SX1276_PA_PATH_BOOST=y
CONFIG_SX1276_TX_POWER_DBM=2
```

### 4. Lệnh chạy

#### Bước 5.1: Nạp Node 1 (`/dev/ttyUSB1`):
```bash
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/firmware/sensor_node
# Đảm bảo CONFIG_NODE_TDMA_NODE_ID=1 trong sdkconfig
idf.py -p /dev/ttyUSB1 flash
```

#### Bước 5.2: Cấu hình và Nạp Node 2 (`/dev/ttyUSB2`):
```bash
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/firmware/sensor_node
# Đổi CONFIG_NODE_TDMA_NODE_ID=2
idf.py menuconfig
idf.py -p /dev/ttyUSB2 flash
```

#### Bước 5.3: Mở 3 cửa sổ Terminal giám sát:
```bash
# Terminal 1:
idf.py -p /dev/ttyUSB0 monitor  # Gateway

# Terminal 2:
idf.py -p /dev/ttyUSB1 monitor  # Node 1

# Terminal 3:
idf.py -p /dev/ttyUSB2 monitor  # Node 2
```

### 5. Thông số cần thu thập
* **Logic Analyzer (Ch 0: GW DIO0, Ch 1: Node 1 DIO0, Ch 2: Node 2 DIO0):**
  * $t_0$: Xung Beacon của Gateway xuất hiện ở đầu chu kỳ.
  * $t_1$: Xung TX `UP_EVENT` của Node 1 xuất hiện trong khoảng $[550\text{ ms}, 1150\text{ ms}]$.
  * $t_2$: Xung TX `UP_EVENT` của Node 2 xuất hiện trong khoảng $[1150\text{ ms}, 1750\text{ ms}]$.
  * **Tiêu chuẩn PASS:** Hai xung TX cách nhau chính xác 1 độ rộng Slot ($600\text{ ms}$), vùng bảo vệ (guard band $50\text{ ms}$) hoàn toàn yên lặng, không có hiện tượng truyền trùng lặp.

---

## Kịch Bản 6: Gửi Cùng Một Lúc (Simultaneous Button Alert Contention Test)

### 1. Trường hợp test
Nhấn nút vật lý đồng thời trên cả Node 1 và Node 2 trong cùng một chu kỳ Superframe 10 giây. Chứng minh cơ chế Hybrid TDMA loại bỏ hoàn toàn xung đột trên không (zero on-air packet collision), các Node tự động xếp hàng theo khe tĩnh của mình.

### 2. Thư mục chạy
* Giữ nguyên cấu hình đã nạp ở **Kịch Bản 5**.

### 3. Thông số menuconfig
* Node 1: `CONFIG_NODE_TDMA_NODE_ID=1`
* Node 2: `CONFIG_NODE_TDMA_NODE_ID=2`
* Gateway: Chế độ Static Superframe 15 slots.

### 4. Lệnh chạy & Thao tác
1. Chạy `monitor` trên cả 3 thiết bị (`/dev/ttyUSB0`, `/dev/ttyUSB1`, `/dev/ttyUSB2`).
2. Quan sát thấy Gateway vừa phát một Beacon mới (bắt đầu chu kỳ 10s mới).
3. **Thao tác vật lý:** Dùng 2 tay nhấn nút bấm trên cả Node 1 và Node 2 cùng một lúc.

### 5. Thông số cần thu thập
* **Node 1 Serial:**
  * Nhận Beacon $\to$ Tính mốc Slot 1 $\to$ Bắn `UP_EVENT` $\to$ Nhận `DOWN_EVENT_ACK` ngay $\to$ Đi ngủ.
* **Node 2 Serial:**
  * Nhận cùng Beacon $\to$ Tính mốc Slot 2 $\to$ Đứng chờ qua Slot 1 $\to$ Đến đúng Slot 2 mới kích hoạt phát `UP_EVENT` $\to$ Nhận `DOWN_EVENT_ACK` $\to$ Đi ngủ.
* **Gateway Serial:**
  * Slot 1: Tiếp nhận và xử lý trọn vẹn `UP_EVENT` của Node 1, gửi ACK 1.
  * Slot 2: Tiếp nhận và xử lý trọn vẹn `UP_EVENT` của Node 2, gửi ACK 2.
  * Bộ đếm lỗi: `corrupted_packet_count = 0`.
  * Bộ đếm rớt gói: `overflow_dropped_count = 0`.
* **Tiêu chuẩn PASS:** Tỉ lệ phân phát gói thành công **PDR = 100% (2/2)** mặc dù sự kiện kích hoạt hoàn toàn đồng thời. Khẳng định tính đúng đắn của giao thức TDMA so với ALOHA/CSMA.
