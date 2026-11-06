# Custom LoRa P2P Radio MAC — Giao diện Node ↔ Gateway

**Revision 0.2.0-draft · V2 Protocol Architecture Integration · Issue #127 / Umbrella #125 · Gate G2: NOT_VERIFIED.**

---

## 1. Phạm vi và trách nhiệm hệ thống

Hệ thống hoạt động theo mô hình **Local Alarm Autonomy + Event-Only Remote Logging + Static DATA TDMA + Maintenance Superframe**:

- **Sensor Node (ESP32-WROOM-32E + SX1276)**:
  - Khi cảm biến phát hiện vượt ngưỡng, Node kích hoạt cảnh báo phần cứng tại chỗ tức thời (GPIO, còi buzzer, đèn LED, relay) hoàn toàn tự chủ mà không phụ thuộc vào trạng thái sóng LoRa RF hay ranh giới khe TDMA.
  - Giao diện RF chỉ truyền dữ liệu ứng dụng khi có sự kiện vi phạm (`UP_EVENT`, 0x41); chế độ truyền định kỳ liên tục (`DATA_TELEMETRY`) bị bãi bỏ hoàn toàn.
  - Node chỉ được phép truyền dữ liệu sự kiện trong khe tĩnh (`Static DATA Slot`) độc quyền của mình; không dùng cơ chế tranh chấp kênh (PCSS/CAD).
  - Duy trì hàng đợi sự kiện bền vững trong bộ nhớ NVS với mã tham chiếu cục bộ `EVENT_REF` (4 byte tăng đơn điệu) để theo dõi xác nhận và phát lại; không tự ý gán nhãn `event_id` toàn cục.
  - Tuân thủ nghiêm ngặt 8 tầng bảo vệ an toàn (`8-Fold Fail-Closed Guards`) trước khi bật bộ phát radio TX.
- **Gateway (ESP32-WROOM-32E / Linux Gateway Engine + SX1276)**:
  - Là nguồn cung cấp nhịp đồng hồ danh định và superframe cục bộ; vận hành bộ thu/phát bán song công trên một chip SX1276 duy nhất.
  - Là thẩm quyền duy nhất sinh ra và quản lý mã định danh sự kiện toàn cục (`event_id`) để xuất bản lên Backend MQTT.
  - Bắt buộc phải ghi nhận sự kiện vào bộ nhớ bền vững (WAL / SQLite) trước khi phát gói tin xác nhận `DOWN_EVENT_ACK` (0x42) ngay trong khe thời gian.
  - Phát sóng `DOWN_SYNC_BEACON` (0x43) mang chữ ký số Ed25519 tại đầu mỗi chu kỳ; thực thi lịch TDMA tích cực và lưu trữ lịch dự phòng (shadow schedule).
  - Bắt tay thỏa thuận khóa phiên cục bộ với Node thông qua X25519 ECDH; quản lý ranh giới kích hoạt khóa phiên (`INSTALLED_INACTIVE` $\to$ `ACTIVE`).
- **Backend Go Modular Monolith**:
  - Lập kế hoạch phân bổ lịch TDMA ở tầng vĩ mô và đẩy xuống Gateway qua MQTT 5.0 / TLS; tuyệt đối **không** tạo lệnh điều khiển TX/RX theo từng slot thời gian RF.
  - Tuân thủ nguyên tắc **Zero-Knowledge**: Backend **không sở hữu** bí mật dùng chung $Z$ và các khóa phiên dữ liệu unicast $K_{\text{SESSION\_UP}}$, $K_{\text{SESSION\_DOWN}}$ (`DEC-SEC-01`).
  - Xác thực bằng chứng nhận Finish từ Node (`BACKEND_READY_PROOF`) thông qua gói `UP_JOIN_READY` (0x49) trước khi đưa Node vào danh sách lập lịch hoạt động chính thức.
- **PHY Layer**: SX1276 LoRa P2P, không phải LoRaWAN. Băng tần quy hoạch VN920 (920.250–922.750 MHz), công suất phát $\le +14\text{ dBm}$, tuân thủ hạn ngạch airtime pháp lý (Node $\le 1.0\%$, Gateway $\le 10\%$).

---

## 2. Danh mục bản tin V1 Lịch sử — HISTORICAL PROVENANCE ONLY (SUPERSEDED)

> [!NOTE]
> Bảng phong bì và danh mục bản tin V1 dưới đây được lưu giữ phục vụ đối chiếu lịch sử và truy xuất nguồn gốc thiết kế theo Chỉ thị Owner (2026-11-04). **CẤM SỬ DỤNG TRONG MÔI TRƯỜNG V2 RUNTIME.**

### 2.1 Candidate Legacy Envelope (V1 — Bãi bỏ)
| Offset | Trường | Quy tắc Candidate V1 | Trạng thái V2 |
|---:|---|---|---|
| 0 | MAGIC | 0xA5 | Bãi bỏ (thay bằng Header V2) |
| 1 | VER_TYPE | b7..6 protocol version, b5..0 packet type | Bãi bỏ |
| 2 | CTRL_FLAGS | Priority, ACK_REQ, IS_RETRY, PENDING_SCHED, DUTY_LIMITED | Bãi bỏ |
| 3 | SRC_ID | 0x00 Gateway; 1..254 Node | Chuyển vào AAD Unicast Header |
| 4 | DST_ID | 0x00 Gateway; 1..254 Node; 0xFF broadcast | Chuyển vào ngữ cảnh phiên |
| 5 | SCHED_VER | 8-bit (không đủ xử lý wrap/epoch) | Thay bằng Epoch/Generation |
| 6 | SEQ_NUM | 8-bit | Thay bằng `FRAME_COUNTER` 32-bit |
| 7 | PAYLOAD_LEN | 0..48 byte | Quy định theo từng mã V2 |
| 8.. | PAYLOAD | Dữ liệu thô | Mã hóa xác thực AES-128-CCM |
| Cuối 2B | CRC16-CCITT | Không có xác thực mật mã | Thay bằng CCM-8 Tag / Ed25519 Sig |

### 2.2 Loại bản tin V1 và Trạng thái Chuyển đổi
| Mã V1 | Tên bản tin V1 | Chiều truyền | Trạng thái trong Kiến trúc V2 | Thay thế bởi V2 |
|:---:|---|:---:|:---:|---|
| `0x01` / `0x21` | `BEACON` (14B / 28B Group-HMAC) | GW $\to$ Broadcast | **SUPERSEDED** | `0x43 DOWN_SYNC_BEACON` (80B, ký số Ed25519) |
| `0x02` / `0x22` | `SCHED_ANNOUNCE` | GW $\to$ Broadcast | **OPEN_DECISION** | Chuyển vào kênh quản trị / Beacon countdown |
| `0x03` / `0x23` | `DATA_TELEMETRY` (12B định kỳ) | Node $\to$ GW | **SUPERSEDED_HISTORICAL** | Bãi bỏ hoàn toàn; hệ thống chuyển sang Event-Only |
| `0x04` / `0x24` | `PRIORITY_ALERT` (trong PCSS) | Node $\to$ GW | **SUPERSEDED_HISTORICAL** | Bãi bỏ PCSS/CAD; thay bằng `0x41 UP_EVENT` khe tĩnh |
| `0x05` / `0x25` | `ACK_PACKET` / `ACK_BITMAP` | GW $\to$ Node | **SUPERSEDED** | Thay bằng `0x42 DOWN_EVENT_ACK` ngay trong khe |
| `0x06` / `0x26` | `CMD_DOWNLINK` | GW $\to$ Node | **OPEN_DECISION** | Giữ riêng trong luồng xem xét bảo mật lệnh |
| `0x07` / `0x11` | `JOIN_SLOT_REQ` / Bootstrap V1 | Node $\to$ GW | **SUPERSEDED_HISTORICAL** | Thay bằng `0x45 UP_JOIN_HELLO` (68B X25519) |
| `0x08` / `0x12` | `JOIN_SLOT_RSP` / Accept V1 | GW $\to$ Node | **SUPERSEDED_HISTORICAL** | Thay bằng `0x46 DOWN_JOIN_GRANT` (66B) |

---

## 3. Đặc tả Giao thức LP2P Secure MAC V2 (Normative Specification)

Mọi gói tin V2 Unicast sử dụng **Header chuẩn 7 byte** không mã hóa (nằm trong AAD của thuật toán AES-128-CCM), theo sau bởi phần thân mã hóa và thẻ xác thực mật mã 8 byte (`CCM-8`, $M=8$ theo Quyết định Owner 2026-11-06).

### 3.1 Cấu trúc Header Unicast V2 (7 octets)
```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    VER_TYPE   |    NODE_ID    |  SESSION_SEL  |               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+               +
|                  FRAME_COUNTER (Big-Endian)                   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```
- `VER_TYPE` (1B): 3 bit phiên bản (`010` = Version 2) + 5 bit mã loại gói tin. Dải mã V2 là `0x40` đến `0x5F`, từ chối ngay lập tức mọi gói tin V1 (`0x20`..`0x3F`).
- `NODE_ID` (1B): Địa chỉ định danh phần cứng Node trong mạng cục bộ (`0x01`..`0xFE`).
- `SESSION_SEL` (1B): Chỉ định bộ khóa phiên đang hoạt động (`0` hoặc `1`) để hỗ trợ chuyển đổi khóa mượt mà (rekeying/cutover).
- `FRAME_COUNTER` (4B, Big-Endian): Bộ đếm khung tăng đơn điệu nghiêm ngặt trên mỗi phiên và hướng truyền, chống phát lại (Replay Protection).

---

### 3.2 Bảng Đăng ký Bản tin LP2P V2 (V2 Packet Registry)

| Mã Hex | Tên bản tin V2 | Chiều | Cỡ (B) | Cơ chế Mật mã & Xác thực | Trạng thái Phê duyệt | Nguồn phê duyệt |
|:---:|---|:---:|:---:|---|:---:|---|
| `0x41` | `UP_EVENT` | Node $\to$ GW | 26 | Ciphertext 11B + Thẻ CCM-8 (8B) dưới khóa $K_{\text{SESSION\_UP}}$ | **OWNER_APPROVED_DESIGN** | Owner Phê duyệt (2026-11-06, DEC-127-01 & DEC-127-02) |
| `0x42` | `DOWN_EVENT_ACK` | GW $\to$ Node | 19 | Ciphertext 4B + Thẻ CCM-8 (8B) dưới khóa $K_{\text{SESSION\_DOWN}}$ | **OWNER_APPROVED_DESIGN** | Owner Phê duyệt (2026-11-06, DEC-127-01 & DEC-127-02) |
| `0x43` | `DOWN_SYNC_BEACON` | GW $\to$ BC | 80 | 16B Thông tin + 64B Chữ ký số Ed25519 (Private Key của GW) | **OWNER_APPROVED_DESIGN** | Owner Phê duyệt (2026-11-06, DEC-MH-01) |
| `0x44` | `UP_HEALTH_REPLY` | Node $\to$ GW | 21 | Ciphertext 6B + Thẻ CCM-8 (8B) dưới khóa $K_{\text{SESSION\_UP}}$ | **OWNER_APPROVED_DESIGN** | Owner Phê duyệt (2026-11-06, DEC-MH-02) |
| `0x45` | `UP_JOIN_HELLO` | Node $\to$ GW | 68 | X25519 Ephemeral Pub (32B) + Hello Tag (16B HMAC $K_{\text{JOIN}}$) | **OWNER_APPROVED_DESIGN** | Issue #127 Comment 6628167582 |
| `0x46` | `DOWN_JOIN_GRANT` | GW $\to$ Node | 66 | X25519 Ephemeral Pub (32B) + Backend Grant Proof (16B) | **OWNER_APPROVED_DESIGN** | Issue #127 Comment 6629944747 |
| `0x47` | `UP_JOIN_KEY_CONFIRM` | Node $\to$ GW | 31 | `GW_KC_TAG` (8B $K_{\text{KC\_UP}}$) + `BACKEND_PROOF` (16B $K_{\text{JCONFIRM}}$) | **OWNER_APPROVED_DESIGN** | Issue #127 Comment 6630055809 |
| `0x48` | `DOWN_JOIN_FINISH` | GW $\to$ Node | 31 | `GW_TAG8` (8B $K_{\text{KC\_DOWN}}$) + `BACKEND_TAG16` (16B $K_{\text{JFINISH}}$) | **OWNER_APPROVED_DESIGN** | Issue #127 Comment 6630280648 |
| `0x49` | `UP_JOIN_READY` | Node $\to$ GW | 31 | `GW_READY_TAG` (8B $K_{\text{KC\_UP}}$) + `BACKEND_READY_PROOF` (16B $K_{\text{JREADY}}$) | **OWNER_APPROVED_DESIGN** | Commit `f5dd608` (DEC-SEC-03 & DEC-SEC-04) |

---

### 3.3 Chi tiết Cấu trúc Tải trọng Bản tin V2 (Payload Layouts)

#### 1. `UP_EVENT` (0x41, 26 octets)
- **Header (7B):** `0x41 | NODE_ID:1 | SESSION_SEL:1 | FRAME_COUNTER:4`
- **Plaintext trước khi mã hóa (11B):**
  - `EVENT_REF` (4B, u32 Big-Endian): Mã tham chiếu sự kiện cục bộ của Node (tăng đơn điệu).
  - `EVENT_TIME` (4B, u32 Big-Endian): Epoch Unix thời điểm xảy ra sự kiện (hoặc `0xFFFFFFFF` nếu chưa đồng bộ giờ).
  - `EVENT_CODE` (1B, u8): Mã loại cảnh báo (VD: cháy, khói, nhiệt độ cao, rò rỉ khí).
  - `EVENT_VALUE` (2B, i16 Big-Endian): Giá trị đo cảm biến tại thời điểm vi phạm.
- **Thẻ xác thực:** `CCM-8 Tag` (8B).

#### 2. `DOWN_EVENT_ACK` (0x42, 19 octets)
- **Header (7B):** `0x42 | NODE_ID:1 | SESSION_SEL:1 | FRAME_COUNTER:4`
- **Plaintext trước khi mã hóa (4B):**
  - `EVENT_REF` (4B, u32 Big-Endian): Phản hồi đúng `EVENT_REF` mà Node đã truyền lên.
- **Thẻ xác thực:** `CCM-8 Tag` (8B).
- **Ràng buộc:** Gateway chỉ được phát gói tin này sau khi sự kiện đã được lưu bền vững vào WAL / SQLite.

#### 3. `DOWN_SYNC_BEACON` (0x43, 80 octets)
- **Thông tin đồng bộ không mã hóa (16B):**
  - `MAGIC` (1B): `0x43`
  - `GW_ID` (1B): Định danh Gateway phát sóng (`0x01`..`0xFE`).
  - `EPOCH_SEC` (4B, u32 Big-Endian): Thời gian thực Unix chuẩn từ Gateway (GPS/NTP/RTC).
  - `SF_SEQ` (4B, u32 Big-Endian): Số thứ tự Superframe toàn cục tăng đơn điệu.
  - `SCHED_VER` (1B, u8): Phiên bản lịch TDMA đang có hiệu lực.
  - `FLAGS` (1B): Bit 7..6: Đếm ngược chuyển đổi lịch ($3 \to 2 \to 1 \to 0$); Bit 5: Cờ cảnh báo khẩn; Bit 4..0: Dành riêng (=0).
  - `RESERVED` (4B): Đệm căn chỉnh 0x00000000.
- **Chữ ký số Ed25519 (64B):** Ký trên toàn bộ 16 byte thông tin bằng khóa bí mật Ed25519 của Gateway. Mọi Node dùng khóa công khai của Gateway (đã được nạp cứng an toàn) để xác minh tính xác thực nguồn gốc.

#### 4. `UP_HEALTH_REPLY` (0x44, 21 octets)
- **Header (7B):** `0x44 | NODE_ID:1 | SESSION_SEL:1 | FRAME_COUNTER:4`
- **Plaintext trước khi mã hóa (6B):**
  - `MAINT_SEQ` (4B, u32 Big-Endian): Mã tuần tự của chu kỳ Maintenance Superframe hiện tại.
  - `STATUS_FLAGS` (1B): Trạng thái pin, cảm biến, lỗi phần cứng.
  - `PENDING_COUNT` (1B, u8): Số lượng sự kiện còn tồn đọng tức thời trong FIFO chưa được ACK ($0..255$).
- **Thẻ xác thực:** `CCM-8 Tag` (8B).
- **Ràng buộc trường và ngân sách byte (Bổ chính MAC-01 / DEC-MH-02):**
  - Toàn bộ ngân sách 21 byte đã được phân bổ trọn vẹn ($7\text{B Header} + 6\text{B Plaintext} + 8\text{B Tag} = 21\text{B}$).
  - `PENDING_COUNT` là chỉ số đo tức thời độ sâu hàng đợi, **tuyệt đối không phải** bộ đếm tích lũy sự kiện bị ghi đè/mất mát (`DROPPED_EVENT_COUNT`).
  - Bản tin 21B hiện thời **không có trường truyền tải `DROPPED_EVENT_COUNT`** trên đường truyền RF. Cơ chế truyền tải số liệu mất mát được quản lý dưới dạng quyết định mở `DEC-MH-08` (xem Mục 5.2). Cấm tùy tiện chèn byte hoặc định nghĩa lại các trường trong bản tin 21B mà không có phê duyệt từ Project Owner.

#### 5. `UP_JOIN_READY` (0x49, 31 octets)
- **Header (7B):** `0x49 | GW_ID:1 | NODE_ID:1 | JOIN_COUNTER:4 (Big-Endian)`
- **`GW_READY_TAG` (8B):** HMAC-SHA256 tính bằng khóa $K_{\text{KC\_UP}}$ trên ngữ cảnh `TH || FINISH31 || 0x49`, chứng minh cho Gateway rằng Node đã sẵn sàng.
- **`BACKEND_READY_PROOF` (16B):** HMAC-SHA256 tính bằng khóa $K_{\text{JREADY}}$ trên ngữ cảnh `NETWORK || TH || FINISH31`, cung cấp bằng chứng mật mã không thể giả mạo gửi lên Backend xác nhận Node đã nhận hợp lệ bản tin `DOWN_JOIN_FINISH`.

---

## 4. Ranh giới Mật mã & Thẩm quyền Khóa phiên (Cryptographic Authority)

Tuân thủ nghiêm ngặt các quyết định `DEC-SEC-01` .. `DEC-SEC-07` đã được Owner phê duyệt:

```
+-------------------------------------------------------------------------------------------------------+
|                                    MA TRẬN QUYỀN SỞ HỮU KHÓA MẬT MÃ V2                                |
+---------------------------+------+-----------------+-----------------+-----------------+-------------+
| Khóa / Bí mật mật mã      | Cỡ   | Sensor Node     | Gateway         | Backend Go      | Thẩm quyền  |
+---------------------------+------+-----------------+-----------------+-----------------+-------------+
| K_JOIN (Pre-Shared Key)   | 32B  | LƯU TRỮ TRONG NVS| KHÔNG SỞ HỮU    | LƯU TRỮ DB      | DEC-SEC-01  |
| Ephemeral Priv/Pub (ECDH) | 32B  | TỰ SINH CỤC BỘ  | TỰ SINH CỤC BỘ  | KHÔNG SỞ HỮU    | DEC-SEC-01  |
| Shared Secret Z (X25519)  | 32B  | TÍNH TOÁN ECDH  | TÍNH TOÁN ECDH  | **KHÔNG BIẾT**  | DEC-SEC-01  |
| K_SESSION_UP (AES-CCM)    | 16B  | PHÁI SINH TỪ Z  | PHÁI SINH TỪ Z  | **KHÔNG BIẾT**  | DEC-SEC-01  |
| K_SESSION_DOWN (AES-CCM)  | 16B  | PHÁI SINH TỪ Z  | PHÁI SINH TỪ Z  | **KHÔNG BIẾT**  | DEC-SEC-01  |
| K_KC_UP (Xác thực GW)     | 32B  | PHÁI SINH TỪ Z  | PHÁI SINH TỪ Z  | **KHÔNG BIẾT**  | DEC-SEC-01  |
| K_KC_DOWN (Xác thực Finish)| 32B | PHÁI SINH TỪ Z  | PHÁI SINH TỪ Z  | **KHÔNG BIẾT**  | DEC-SEC-01  |
| K_JREADY (Xác thực Backend)| 32B | PHÁI SINH K_JOIN| KHÔNG SỞ HỮU    | PHÁI SINH K_JOIN| DEC-SEC-03  |
| Gateway Ed25519 PrivKey   | 64B  | KHÔNG BIẾT      | LƯU BẢO MẬT     | KHÔNG SỞ HỮU    | DEC-MH-01   |
| Gateway Ed25519 PubKey    | 32B  | NẠP CỨNG AN TOÀN| CÔNG KHAI       | QUẢN LÝ / PIN   | DEC-MH-01   |
+---------------------------+------+-----------------+-----------------+-----------------+-------------+
```

1. **Backend Zero-Knowledge (`DEC-SEC-01`):** Backend tuyệt đối không tính toán, không nhận và không nắm giữ bí mật dùng chung $Z$ cũng như các khóa phiên truyền tin unicast.
2. **Kế thừa Hợp đồng MQTT (`DEC-SEC-02`):** Hợp đồng MQTT PR #123 (`session-keys.schema.json` 64B wrapped keys) được bảo lưu nghiêm ngặt chỉ dành cho V1. Giao thức V2 áp dụng **Alternative B (Session Binding Ticket)** thông qua Issue #128.
3. **Chống điểm suy biến ECDH (`DEC-SEC-07`):** Bắt buộc loại bỏ hoàn toàn các điểm toàn số 0 theo RFC 7748 Section 6.1:
   $$\text{Nếu } \text{X25519}(\text{priv}, \text{pub}) == 0^{32} \implies \text{FAIL CLOSED, hủy phiên tức thì.}$$
4. **Cấu trúc Nonce 13 byte (AES-CCM):**
   $$\text{Nonce} = \text{SESSION\_NONCE\_PREFIX (8B)} \parallel \text{DIRECTION (1B: 0x01=UP, 0x02=DOWN)} \parallel \text{FRAME\_COUNTER (4B)}$$
   Tuyệt đối cấm tái sử dụng cùng một cặp (Key, Nonce) cho các nội dung tin khác nhau. Phát lại (retry) bắt buộc phải truyền nguyên văn chuỗi byte mã hóa đã lưu đệm.
5. **Bảo vệ Bộ đếm Ghi nhớ trong NVS (`DEC-SEC-06`):** `JOIN_COUNTER` phải được ghi tăng bền vững vào NVS trước khi gửi bản tin Hello. Nếu phát hiện lỗi đọc hoặc giảm số bộ đếm, Node lập tức khóa cứng radio.

---

## 5. Quản lý Sự kiện & Chính sách Tràn hàng đợi (Queue Management)

1. **Phân tách Định danh Sự kiện (Event Identity Decoupling):**
   - Node chỉ duy trì mã tham chiếu nội bộ `EVENT_REF` (u32 tăng đơn điệu) lưu trong NVS flash.
   - Gateway là nguồn duy nhất phát hành `event_id` chuẩn doanh nghiệp lên Backend MQTT theo bộ ánh xạ:
     $$(\text{gateway\_id}, \text{node\_id}, \text{session\_sel}, \text{frame\_counter}) \longrightarrow \text{event\_id}$$
2. **Chính sách Tràn bộ nhớ đệm tại Node (`DEC-127-04` — Owner Phê duyệt 2026-11-06; Bổ chính MAC-01):**
   - Khi mạng mất kết nối kéo dài và hàng đợi NVS FIFO đầy tải, Node áp dụng chính sách **`RING_BUFFER_DROP_OLDEST`**: Ghi đè sự kiện cũ nhất để ưu tiên lưu giữ và truyền báo động mới nhất, đồng thời bắt buộc phải tăng và lưu trữ bền vững bộ đếm mất sự kiện `DROPPED_EVENT_COUNT` trong bộ nhớ NVS non-volatile.
   - **Bổ chính MAC-01 (Kênh truyền tải số liệu mất mát — `DEC-MH-08`):**
     - Bản tin sức khỏe định kỳ `UP_HEALTH_REPLY` (0x44, 21B) đã được Owner phê duyệt (`DEC-MH-02`) có bố cục cố định và **không có trường truyền tải `DROPPED_EVENT_COUNT`** (trường `PENDING_COUNT: 1B` chỉ phản ánh số lượng sự kiện hiện đang nằm trong FIFO chưa được ACK, không phải bộ đếm tích lũy sự kiện bị mất).
     - **Chủ trương định hướng đã duyệt (`DEC-MH-08` — `OWNER_APPROVED_DIRECTION / PLANNED_NOT_IMPLEMENTED`):**
       - Giữ nguyên 100% bản tin 21B `UP_HEALTH_REPLY` (`0x44`) để tối ưu thời gian chiếm sóng airtime (56.6ms tại SF7).
       - Project Owner đã chính thức phê duyệt định hướng áp dụng **bản tin quản trị/chẩn đoán riêng biệt có phiên bản (separate versioned diagnostic/management message)** để báo cáo số liệu mất mát `DROPPED_EVENT_COUNT`, thống kê retry và điện áp pin.
       - **Ranh giới thực thi:** Mã định danh `0x4A` (ví dụ `UP_DIAG_METRICS`) chỉ là mã loại gói tin ứng viên (candidate packet type only), chưa được phê duyệt hợp đồng chi tiết. **Tuyệt đối không phát hành, gán byte wire format, hoặc truyền nhận loại bản tin này trong phạm vi PR hiện tại.** Việc chuẩn hóa bố cục wire cho bản tin chẩn đoán sẽ được giao cho một Issue hợp đồng riêng biệt sau khi có phê duyệt từ Owner.

---

## 6. Ràng buộc Tần số và Thời gian RF (RF Spreading Factor & Timing)

1. **Giới hạn Spreading Factor cho MVP V1 (`DEC-127-03` Lựa chọn A — Owner Phê duyệt 2026-11-06; Bổ chính TIM-01/TIM-02):**
   - Vận hành hệ thống MVP V1 được **giới hạn nghiêm ngặt ở SF7 và SF8**.
   - **Đối chiếu ToA khứ hồi hai chiều (Bổ chính TIM-01):**
     - Tại **SF7:** $\text{ToA}_{\text{EVENT}} (61.696\text{ms}) + \tau_{\text{turnaround}} (20\text{ms}) + \text{ToA}_{\text{ACK}} (51.456\text{ms}) \approx 133.152\text{ms} < 250\text{ms}$. Hoàn toàn bảo đảm hoàn thành an toàn trong khe 400ms và phong bì minh họa $[25, 245)\text{ms}$.
     - Tại **SF8:** $\text{ToA}_{\text{EVENT}} (113.152\text{ms}) + \tau_{\text{turnaround}} (20\text{ms}) + \text{ToA}_{\text{ACK}} (102.912\text{ms}) \approx 236.064\text{ms} > 220\text{ms}$. Dù tổng ToA RF lý thuyết ($216.064\text{ms}$) vẫn nằm trong khe 400ms, nó vượt quá phong bì minh họa $[25, 245)\text{ms}$ và từng cửa sổ con 100ms.
   - **Tham số hóa hình học khe (`DEC-127-06` — `OWNER_APPROVED_DIRECTION / NOT_HIL_VERIFIED`):** Thời gian khe TDMA không bị đóng băng cứng nhắc, mà tuân thủ mô hình tham số hóa được thẩm định tự động fail-closed. Bộ số ví dụ minh họa ($25+125+35+115+100=400\text{ms}$) chỉ là ví dụ ứng viên, không phải profile cố định.
   - Các cấu hình SF9+ tạm thời không kích hoạt trên luồng dữ liệu thời gian thực; việc điều chỉnh độ dài khe sẽ được tái đánh giá sau khi có số liệu đo đạc vật lý từ Issue #169.
2. **Độc lập Đo đạc Vật lý (#169):**
   - Mọi hằng số thời gian số học (ms) trong tài liệu này đều mang tính chất định danh biểu tượng (symbolic). Việc đóng băng chính thức các hằng số Guard Time và khe TDMA bị khóa (`BLOCKED`) chờ kết quả đo đạc thực tế từ Issue #169.

---

## 7. Tiêu chí Đóng băng Hợp đồng (Gate G2 Status)

- [x] Phê duyệt kiến trúc Event-Only, Local Alarm Autonomy và bãi bỏ PCSS/CAD.
- [x] Phê duyệt mã bản tin và bố cục gói tin Join V2 (0x45..0x48) và Post-Join (0x49).
- [x] Phê duyệt bộ quyết định an ninh mật mã `DEC-SEC-01` .. `DEC-SEC-07`.
- [x] Phê duyệt mã bản tin `UP_EVENT` (0x41), `DOWN_EVENT_ACK` (0x42), `DOWN_SYNC_BEACON` (0x43), `UP_HEALTH_REPLY` (0x44).
- [x] Phê duyệt giới hạn SF7/SF8 cho khe 400ms và chính sách hàng đợi `RING_BUFFER_DROP_OLDEST`.
- [ ] Hoàn thành kiểm tra chéo Golden Vectors Go $\leftrightarrow$ ESP-IDF mbedTLS (Issue #173) $\to$ **NOT_VERIFIED**.
- [ ] Hoàn thành kiểm tra phân quyền ACL broker Mosquitto mTLS (Issue #174) $\to$ **NOT_VERIFIED**.
- [ ] Hoàn thành kiểm thử xung đột nguồn Gateway NVS HIL (Issue #175) $\to$ **NOT_VERIFIED**.
- [ ] Hoàn thành đo đạc vật lý thời gian thực RF và Guard Time (Issue #169) $\to$ **BLOCKED**.

**KẾT LUẬN G2: `NOT_VERIFIED`** — Tài liệu hợp đồng đã được đồng bộ hóa toàn diện; việc cấp chứng chỉ G2 PASS yêu cầu hoàn tất các bằng chứng kiểm thử thực tế từ các Issue phụ thuộc nêu trên.
