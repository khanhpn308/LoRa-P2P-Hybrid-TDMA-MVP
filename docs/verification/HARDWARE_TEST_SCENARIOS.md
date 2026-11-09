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

## Kịch Bản 2: Node Mới Join Mạng & Duyệt Thiết Bị (Join Handshake & Web Dashboard Approval)

### 1. Trường hợp test
Node chưa có khóa phiên phát tín hiệu Join Request (chứa Ephemeral Public Key X25519) qua sóng $\to$ Gateway tiếp nhận, chuyển tiếp lên Backend qua MQTT topic `iot/v1/gw/{gateway_id}/join/request` $\to$ Admin xem xét và phê duyệt trên Web Dashboard (tab "Node mới" tại `/nodes`) $\to$ Backend xác thực và phản hồi Join Accept qua MQTT $\to$ Gateway phát sóng `DOWN_JOIN_ACCEPT (0x46)` $\to$ Node xác lập khóa phiên `K_SESSION_UP` / `K_SESSION_DOWN`, chuyển trạng thái sang sẵn sàng hoạt động (Event-Driven Pure CAD CSMA/CA).

### 2. Thư mục chạy
* Backend Go: `backend-go`
* Web Dashboard: `clients/web-dashboard`
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
CONFIG_NODE_DEVICE_ID=1
CONFIG_NODE_GATEWAY_ID=1
```

### 4. Lệnh chạy

#### Cửa sổ 1 - Khởi động Backend & Web Dashboard:
```bash
# Khởi động Backend Go
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/backend-go
go run cmd/server/main.go

# Khởi động Web Dashboard
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/clients/web-dashboard
npm run dev
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
* Web Dashboard: Xuất hiện thẻ Node mới tại mục `Node mới` (tab 2), hiển thị RSSI, SNR, Device MAC. Admin bấm "Phê duyệt thiết bị".
* Backend Log: Xác minh HMAC thẻ Join, sinh bộ khóa phiên, publish `iot/v1/gw/gw-a/join/accept`.
* Gateway Serial: Nhận MQTT, phát `DOWN_JOIN_ACCEPT (0x46)` trên RF.
* Node Serial: Nhận `DOWN_JOIN_ACCEPT`, tính khóa chung ECDH X25519 thành công, chuyển trạng thái sang `ACTIVE` $\to$ sẵn sàng phát sự kiện qua CAD CSMA/CA.

---

## Kịch Bản 3: Cấp Phát Kênh Tần Số VN920 Tĩnh (Static VN920 Channel Allocation & Commissioning)

### 1. Trường hợp test
Kiến trúc Pure CAD CSMA/CA (ADR-0004) bãi bỏ hoàn toàn subsystem lập lịch TDMA và endpoint `/api/v1/schedules`. Kênh tần số VN920 (CH00..CH10) được cấp phát tĩnh độc quyền cho từng Gateway thông qua REST API quản lý kênh, sau đó Gateway duy trì Continuous RX 24/7 trên kênh này.

### 2. Thư mục chạy
```bash
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP
```

### 3. Thông số cấu hình
* Kênh yêu cầu: `CH00` (Tần số 920.250 MHz, BW 125 kHz).
* Gateway ID: `gw-a`.

### 4. Lệnh chạy
```bash
# Yêu cầu cấp phát kênh tĩnh VN920 cho Gateway gw-a
curl -X POST http://localhost:8080/api/v1/channels/request \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "gateway_id": "gw-a",
    "channel_id": "CH00"
  }'
```

### 5. Thông số cần thu thập
* Backend: HTTP Response `200 OK` (hoặc `201 Created`) trả về `allocation_generation` và trạng thái `ALLOCATED`.
* Gateway Monitor:
  * Trạng thái hoạt động: Gateway duy trì chế độ `MODE_RXCONTINUOUS` tại tần số 920.250 MHz.
  * Không phát Beacon chu kỳ `DOWN_SYNC_BEACON`, không có các luồng di trú lịch TDMA.

---

## Kịch Bản 4: Giao Tiếp Dữ Liệu Node $\leftrightarrow$ Gateway qua Pure CAD + CSMA/CA (`UP_EVENT` $\leftrightarrow$ `DOWN_EVENT_ACK`)

### 1. Trường hợp test
Node 1 đang ngủ Deep-Sleep $\to$ Nhấn nút vật lý $\to$ Wake up $\to$ Lắng nghe kiểm tra kênh CAD SX1276 ($\sim 1.5 - 2$ ký hiệu LoRa) $\to$ Kênh rỗi $\to$ Phát tức thì `UP_EVENT` (26B, mã hóa AES-128-CCM-8) $\to$ Gateway Continuous RX 24/7 thu nhận, kiểm tra chống phát lại, ghi WAL/SQLite $\to$ Phản hồi tức thì `DOWN_EVENT_ACK` (19B) trong cửa sổ RX đơn của Node $\to$ Node xóa hàng đợi FIFO và trở về Deep Sleep $\to$ Gateway đẩy MQTT lên Backend $\to$ Web Dashboard cập nhật sự kiện Realtime qua WebSocket.

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
CONFIG_NODE_DEVICE_ID=1
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
  * `Executing CAD check on channel CH00... CAD Clear (Free)`
  * `TX UP_EVENT (0x41) 26 bytes sent`
  * `RX Single Window: DOWN_EVENT_ACK (0x42) received, CCM verified`
  * `Event Ref 1 committed in NVS FIFO. Entering Deep-Sleep mode.`
* **Gateway Monitor:**
  * Continuous RX: Nhận frame 26 bytes từ `Node ID = 1`, `FRAME_COUNTER` hợp lệ, CCM tag khớp.
  * Ghi WAL/SQLite hoàn tất.
  * Phát phản hồi `DOWN_EVENT_ACK` (19 bytes) ngay lập tức.
  * Publish MQTT topic `iot/v1/gw/gw-a/uplink/events`.
* **Web Dashboard:**
  * WebSocket nhận sự kiện `ALERT_TRIGGERED`.
  * Chỉ số sự kiện trên Dashboard nhảy tăng lập tức mà không cần F5 tải lại trang.
* **Logic Analyzer:**
  * Kẹp `DIO0` (GPIO26) của Node 1 và Gateway:
    * Đo ToA `UP_EVENT`: ~61.7 ms (SF7) hoặc ~113.2 ms (SF8).
    * Đo độ trễ xử lý (Turnaround) của Gateway: < 20 ms.
    * Đo ToA `DOWN_EVENT_ACK`: ~51.5 ms (SF7) hoặc ~102.9 ms (SF8).

---

## Kịch Bản 5: Kiểm Thử Tranh Chấp Sóng & Lùi Ngẫu Nhiên (Exponential Random Backoff Verification)

### 1. Trường hợp test
Mô phỏng trường hợp kênh RF đang bận khi Node cần truyền sự kiện. Node thực hiện kiểm tra CAD, phát hiện năng lượng sóng (`CadDetected == 1`), áp dụng thuật toán Exponential Random Backoff ($CW_{\text{min}} = 16\text{ ms}$, $CW_{\text{max}} = 256\text{ ms}$) lùi thời gian ngẫu nhiên trước khi thử lại CAD, không phát đè sóng gây nghẽn mạng.

### 2. Thư mục chạy
```bash
cd /home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/firmware/sensor_node
```

### 3. Thông số menuconfig

#### Node 1 & Node 2:
```text
CONFIG_NODE_BUTTON_GPIO=4
CONFIG_SX1276_RF_TX_ENABLE=y
CONFIG_SX1276_PA_PATH_BOOST=y
CONFIG_SX1276_TX_POWER_DBM=2
CONFIG_SX1276_CHANNEL_CH00=y
```

### 4. Lệnh chạy & Thao tác
1. Mở monitor trên cả Node 1, Node 2 và Gateway.
2. Tạo lưu lượng RF giả lập hoặc kích hoạt Node 1 phát bản tin có ToA dài (SF8).
3. Trong lúc Node 1 đang phát sóng, kích hoạt nút bấm trên Node 2.

### 5. Thông số cần thu thập
* **Node 2 Monitor:**
  * `Executing CAD check on channel CH00... CAD Busy (CadDetected=1)`
  * `Backoff attempt 1/5: waiting X ms (CW=16ms)`
  * `CAD Retry: CAD Clear (Free) -> TX UP_EVENT (0x41)`
  * `RX Single Window: DOWN_EVENT_ACK (0x42) received`
* **Tiêu chuẩn PASS:** Node 2 không phát đè lên sóng của Node 1, cả hai gói tin `UP_EVENT` đều được Gateway thu nhận và phản hồi ACK thành công mà không bị hỏng CRC.

---

## Kịch Bản 6: Bấm Nút Đồng Thời Trên Nhiều Node (Simultaneous Button Alert Contention Test qua Pure CAD + CSMA/CA)

### 1. Trường hợp test
Nhấn nút vật lý đồng thời trên cả Node 1 và Node 2. Chứng minh cơ chế Pure CAD kết hợp Exponential Random Backoff phân giải tranh chấp hoàn toàn bất đồng bộ, cả hai sự kiện đều được gửi đến Gateway và hiển thị trên Web Dashboard với tỉ lệ thành công 100%.

### 2. Thư mục chạy
* Giữ nguyên cấu hình đã nạp ở **Kịch Bản 5**.

### 3. Thông số menuconfig
* Node 1: `CONFIG_NODE_DEVICE_ID=1`
* Node 2: `CONFIG_NODE_DEVICE_ID=2`
* Gateway: Chế độ Continuous RX 24/7 trên kênh CH00.

### 4. Lệnh chạy & Thao tác
1. Chạy `monitor` trên cả 3 thiết bị (`/dev/ttyUSB0`, `/dev/ttyUSB1`, `/dev/ttyUSB2`).
2. Mở Web Dashboard trên trình duyệt tại trang `/monitoring` và `/`.
3. **Thao tác vật lý:** Dùng 2 tay nhấn nút bấm trên cả Node 1 và Node 2 cùng một lúc.

### 5. Thông số cần thu thập
* **Node 1 Serial:**
  * CAD Clear $\to$ Phát `UP_EVENT` ngay $\to$ Nhận `DOWN_EVENT_ACK` $\to$ Ngủ Deep-Sleep.
* **Node 2 Serial:**
  * Phát hiện kênh bận $\to$ Lùi ngẫu nhiên $X$ ms $\to$ CAD Clear $\to$ Phát `UP_EVENT` $\to$ Nhận `DOWN_EVENT_ACK` $\to$ Ngủ Deep-Sleep.
* **Gateway Serial:**
  * Nhận sự kiện từ Node 1, gửi ACK 1, ghi WAL, publish MQTT `uplink/events`.
  * Nhận sự kiện từ Node 2, gửi ACK 2, ghi WAL, publish MQTT `uplink/events`.
  * Bộ đếm lỗi: `corrupted_packet_count = 0`.
* **Web Dashboard:**
  * Cả hai sự kiện từ Node 1 và Node 2 hiển thị đồng thời trên bảng sự kiện thời gian thực.
* **Tiêu chuẩn PASS:** Tỉ lệ phân phát gói thành công **PDR = 100% (2/2)** mặc dù sự kiện kích hoạt hoàn toàn đồng thời. Khẳng định hiệu năng của cơ chế Pure CAD + Exponential Random Backoff (CSMA/CA).
