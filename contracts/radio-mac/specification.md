# Custom LoRa P2P Radio MAC — Giao diện Node ↔ Gateway

**Revision 0.4.0-draft · Pure CAD + Random Backoff (CSMA/CA) MAC & Gateway Continuous RX 24/7 · Issue #273 / DEC-273-01 / ADR-0004 · Gate G2: NOT_VERIFIED.**

---

## 1. Phạm vi và trách nhiệm hệ thống

Hệ thống hoạt động theo mô hình **Event-Only Remote Logging + Pure Event-Driven CAD + Exponential Random Backoff (CSMA/CA) kết hợp Gateway Continuous RX 24/7** (Quyết định Owner DEC-273-01 / [ADR-0004](../../docs/adr/0004-pure-cad-csma-ca-mac.md) tại Issue #273 bãi bỏ hoàn toàn mô hình Hybrid TDMA, khe thời gian tĩnh, superframe, Beacon đồng bộ và Schedule Migration; Quyết định Owner #230 bãi bỏ hoàn toàn cơ cấu cảnh báo phần cứng tại chỗ và cảm biến phức tạp):

- **Sensor Node (ESP32-WROOM-32E + SX1276)**:
  - Nguồn kích hoạt sự kiện duy nhất cho kiểm thử MVP là **Nút nhấn vật lý** (Button press qua GPIO/ngắt EXT0, `button_driver.c`). Cơ cấu cảnh báo tại chỗ (còi buzzer, đèn LED báo động, relay) và lấy mẫu cảm biến công nghiệp phức tạp (ADC, I2C, SPI) bị bãi bỏ hoàn toàn theo Quyết định Owner #230.
  - Khi nút bấm được kích hoạt và lọc dội phím thành công, Node ghi nhận sự kiện (`UP_EVENT`, 0x41, `EVENT_CODE=0x01`, `EVENT_VALUE=1`) vào hàng đợi bền vững `node_event_fifo` trong RTC RAM/NVS flash.
  - Giao diện RF chỉ truyền dữ liệu ứng dụng khi có sự kiện từ nút bấm (`UP_EVENT`, 0x41); chế độ truyền định kỳ liên tục (`DATA_TELEMETRY`) bị bãi bỏ hoàn toàn.
  - **Truy cập vô tuyến CAD + CSMA/CA (DEC-273-01 / ADR-0004):** Bãi bỏ khe tĩnh Static DATA Slot. Node thực hiện kiểm tra hoạt động kênh (CAD) trên SX1276. Nếu kênh bận, thực hiện Exponential Random Backoff ($CW \in [16\text{ ms}, 256\text{ ms}]$, tối đa 5 lần thử). Nếu kênh rỗi, phát sóng `UP_EVENT` (0x41) ngay lập tức, mở cửa sổ chờ ACK đơn ngắn ($T_{rx\_ack} \approx 200\text{ ms}$) để nhận `DOWN_EVENT_ACK` (0x42), nhận và xác thực ACK thành công rồi lập tức quay về ngủ sâu (Deep Sleep).
  - Duy trì hàng đợi sự kiện bền vững trong bộ nhớ NVS với mã tham chiếu cục bộ `EVENT_REF` (4 byte tăng đơn điệu) để theo dõi xác nhận và phát lại; không tự ý gán nhãn `event_id` toàn cục.
  - Tuân thủ nghiêm ngặt 8 tầng bảo vệ an toàn (`8-Fold Fail-Closed Guards`) trước khi bật bộ phát radio TX.
- **Gateway (ESP32-WROOM-32E / Linux Gateway Engine + SX1276)**:
  - **Vận hành Continuous RX 24/7 (DEC-273-01 / ADR-0004):** Duy trì chip SX1276 ở chế độ nhận liên tục (`MODE_RXCONTINUOUS`) trên kênh tĩnh VN920 được cấp phát độc quyền (CH00–CH10). Bãi bỏ hoàn toàn việc duy trì nhịp đồng hồ danh định TDMA, superframe và Beacon đồng bộ định kỳ.
  - Là thẩm quyền duy nhất sinh ra và quản lý mã định danh sự kiện toàn cục (`event_id`) để xuất bản lên Backend MQTT.
  - Bắt buộc phải ghi nhận sự kiện vào bộ nhớ bền vững (WAL / SQLite) trước khi chuyển radio sang TX để phát gói tin xác nhận `DOWN_EVENT_ACK` (0x42) ngay lập tức, sau đó quay lại Continuous RX 24/7.
  - Bắt tay thỏa thuận khóa phiên cục bộ với Node thông qua X25519 ECDH; quản lý ranh giới kích hoạt khóa phiên (`INSTALLED_INACTIVE` $\to$ `ACTIVE`).
- **Backend Go Modular Monolith**:
  - Không lập kế hoạch phân bổ lịch TDMA, không gửi cấu hình schedule qua MQTT; bãi bỏ hoàn toàn trách nhiệm phân bổ slot RF theo DEC-273-01 / ADR-0004.
  - Quản lý định danh Gateway, Node và cấp phát kênh VN920 tĩnh độc quyền qua REST API.
  - Tuân thủ nguyên tắc **Zero-Knowledge**: Backend **không sở hữu** bí mật dùng chung $Z$ và các khóa phiên dữ liệu unicast $K_{\text{SESSION\_UP}}$, $K_{\text{SESSION\_DOWN}}$ (`DEC-SEC-01`).
  - Xác thực bằng chứng nhận Finish từ Node (`BACKEND_READY_PROOF`) thông qua gói `UP_JOIN_READY` (0x49) trước khi đưa Node vào danh sách hoạt động chính thức.
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
| `0x01` / `0x21` | `BEACON` (14B / 28B Group-HMAC) | GW $\to$ Broadcast | **SUPERSEDED** | `0x43 DOWN_SYNC_BEACON` (32B, HMAC-SHA256-128) |
| `0x02` / `0x22` | `SCHED_ANNOUNCE` | GW $\to$ Broadcast | **OPEN_DECISION** | Thay bằng Backend-signed SCHEDULE_PREPARE/DECISION on demand |
| `0x03` / `0x23` | `DATA_TELEMETRY` (12B định kỳ) | Node $\to$ GW | **SUPERSEDED_HISTORICAL** | Bãi bỏ hoàn toàn; hệ thống chuyển sang Event-Only |
| `0x04` / `0x24` | `PRIORITY_ALERT` (trong PCSS) | Node $\to$ GW | **SUPERSEDED_HISTORICAL** | Bãi bỏ PCSS/CAD cho DATA Event; giữ CAD cho Join bất đồng bộ |
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
| `0x43` | `DOWN_SYNC_BEACON` | GW → Broadcast | **32** | Header16 + HMAC-SHA256-128 tag16 với `K_BEACON` per-Gateway | **OWNER_APPROVED_MVP_DESIGN** | #209, #208 (2026-11-07) |
| `0x44` | `UP_HEALTH_REPLY` | Node $\to$ GW | 21 | Ciphertext 6B + Thẻ CCM-8 (8B) dưới khóa $K_{\text{SESSION\_UP}}$ | **OWNER_APPROVED_DESIGN** | Owner Phê duyệt (2026-11-06, DEC-MH-02) |
| `0x45` | `UP_JOIN_HELLO` | Node $\to$ GW | 68 | X25519 Ephemeral Pub (32B) + Hello Tag (16B HMAC $K_{\text{JOIN}}$) | **OWNER_APPROVED_DESIGN** | Issue #127 Comment 6628167582 |
| `0x46` | `DOWN_JOIN_GRANT` | GW $\to$ Node | 66 | X25519 Ephemeral Pub (32B) + Backend Grant Proof (16B) | **OWNER_APPROVED_DESIGN** | Issue #127 Comment 6629944747 |
| `0x47` | `UP_JOIN_KEY_CONFIRM` | Node $\to$ GW | 31 | `GW_KC_TAG` (8B $K_{\text{KC\_UP}}$) + `BACKEND_PROOF` (16B $K_{\text{JCONFIRM}}$) | **OWNER_APPROVED_DESIGN** | Issue #127 Comment 6630055809 |
| `0x48` | `DOWN_JOIN_FINISH` | GW $\to$ Node | 31 | `GW_TAG8` (8B $K_{\text{KC\_DOWN}}$) + `BACKEND_TAG16` (16B $K_{\text{JFINISH}}$) | **OWNER_APPROVED_DESIGN** | Issue #127 Comment 6630280648 |
| `0x49` | `UP_JOIN_READY` | Node $\to$ GW | 31 | `GW_READY_TAG` (8B $K_{\text{KC\_UP}}$) + `BACKEND_READY_PROOF` (16B $K_{\text{JREADY}}$) | **OWNER_APPROVED_DESIGN** | Commit `f5dd608` (DEC-SEC-03 & DEC-SEC-04) |
| `0x4A` | `UP_DIAG_METRICS` | Node → GW | **23** | Header7 + ciphertext8 `[DROPPED_EVENT_COUNT:u32BE, DIAG_SEQ:u32BE]` + CCM8 | **OWNER_APPROVED_MVP_WIRE_DESIGN** | #204/#205 |
| `0x4B` | `DOWN_SCHED_PREPARE` | Backend-signed GW → Broadcast | **80** | Canonical header16 + Backend Ed25519 signature64 | **80B/CRYPTO APPROVED, TYPE CODE CANDIDATE** | #208 |
| `0x4C` | `UP_SCHED_READY` | Node → GW | **41** | Header7 + ciphertext26 (generation/target/status/reason/Backend proof16) + CCM8 | **OWNER_APPROVED_MVP_DESIGN** | #208 |
| `0x4D` | `DOWN_SCHED_DECISION` | Backend-signed GW → Broadcast | **80** | Canonical header16 + Backend Ed25519 signature64, COMMIT/ABORT | **80B/CRYPTO APPROVED, TYPE CODE CANDIDATE** | #208 |

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

#### 3. `DOWN_SYNC_BEACON` (0x43, **32 octets**) — SUPERSEDED / DEPRECATED (DEC-273-01 / ADR-0004)

> [!WARNING]
> **SUPERSEDED / DEPRECATED (Owner Decision DEC-273-01 / ADR-0004, Issue #273, 2026-11-09)**
> Bản tin Beacon đồng bộ 0x43 bị bãi bỏ hoàn toàn do hệ thống không còn sử dụng khe thời gian và superframe TDMA. Sensor Node hoạt động bất đồng bộ theo sự kiện kết hợp kiểm tra CAD; Gateway vận hành Continuous RX 24/7. Nội dung dưới đây được lưu giữ phục vụ đối chiếu lịch sử.

**Owner-approved MVP wire target (Lịch sử):** 16B header and a 16B truncated HMAC-SHA256 authentication tag. Beacon is *time synchronization only* and cannot authorize schedule COMMIT, rejoin or activation.

| Offset | Field | Size |
| --- | --- | ---: |
| 0 | `MAGIC = 0x43` | 1 |
| 1 | `GW_ID` | 1 |
| 2–5 | `EPOCH_SEC` (u32 Big-Endian) | 4 |
| 6–9 | `SF_SEQ` (u32 Big-Endian, anti-replay) | 4 |
| 10 | `SCHED_VER` (informational, not authorization) | 1 |
| 11 | `FLAGS`, bits7:6 reserved=0, bit5 emergency | 1 |
| 12 | `KEY_ID` for per-Gateway `K_BEACON` | 1 |
| 13–15 | `RESERVED = 0` | 3 |
| 16–31 | `TAG16 = LEFT16(HMAC-SHA256(K_BEACON, domain-separated NETWORK_ID/GW_ID/Header16 transcript))` | 16 |

`K_BEACON` is 256-bit CSPRNG per Gateway, securely provisioned out-of-band to Gateway and authorized Nodes. Never reuse Join/session/Backend signing keys. Check tag constant-time and reject stale `SF_SEQ`, timestamp rollback/unknown key epoch. Exact canonical domain/NETWORK_ID serializer and key-lifecycle rollover require Golden Vectors before enabling RF. Any compromised Node holding group HMAC key can spoof Beacon; do NOT use it as Backend schedule authorization. Automated RF key rotation is not MVP.


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

#### 6. `UP_DIAG_METRICS` (0x4A, **23 octets**) — OWNER-APPROVED MVP

Bytes 0..6: `0x4A | NODE_ID | SESSION_SEL | FRAME_COUNTER:u32BE` (AAD). Bytes 7..14: AES-128-CCM ciphertext of `DROPPED_EVENT_COUNT:u32BE | DIAG_SEQ:u32BE`. Bytes 15..22: CCM-8 authentication tag. Use `K_SESSION_UP` and V2 nonce `SESSION_NONCE_PREFIX8 || 0x01 || FRAME_COUNTER4`, **shared UP counter namespace** with 0x41/0x44 to avoid `(key,nonce)` reuse. Duplicate reports must not double count. Health 0x44 stays 21B. DIAG can only TX in explicitly authorized NORMAL Maintenance management opportunity; defer during Schedule Migration.

#### 7. Schedule Migration V2 — SUPERSEDED / DEPRECATED (DEC-273-01 / ADR-0004)

> [!WARNING]
> **SUPERSEDED / DEPRECATED (Owner Decision DEC-273-01 / ADR-0004, Issue #273, 2026-11-09)**
> Toàn bộ quy trình Schedule Migration (DOWN_SCHED_PREPARE 0x4B, UP_SCHED_READY 0x4C, DOWN_SCHED_DECISION 0x4D) bị bãi bỏ hoàn toàn theo DEC-273-01 / ADR-0004. Hệ thống chuyển đổi toàn diện sang Pure CAD + Random Backoff (CSMA/CA) kết hợp Gateway Continuous RX 24/7. Nội dung dưới đây được lưu giữ phục vụ đối chiếu lịch sử.

- `DOWN_SCHED_PREPARE`: **80B**, 16B canonical common header + **64B Backend Ed25519 signature**, broadcast by Gateway. Candidate type `0x4B` is reserved for wire compatibility review; backend-only private signing key, Node verifies pinned Backend public key; fields bind GW/NETWORK/PROFILE/SCHED_GENERATION/K_TARGET/W_MS/KEY_ID.
- `UP_SCHED_READY`: **41B**, **approved type 0x4C**, V2 unicast AAD 7B + encrypted 26B `[SCHED_GENERATION:u32, K_TARGET:u32, STATUS:u8, REASON:u8, BACKEND_READY_PROOF:16B]` + CCM8. A distinct Node↔Backend proof derived from `K_JOIN` must bind exact signed PREPARE, checked independently by Backend; Gateway verifies CCM.
- `DOWN_SCHED_DECISION`: **80B**, header16 + Backend Ed25519 signature64, candidate type `0x4D`, signed COMMIT(1)/ABORT(0) cryptographically bound to the exact signed PREPARE digest. Exactly one immutable terminal decision per transaction.
- Gateway may COMMIT **only when `VERIFIED_READY_SET == AFFECTED_NODE_SET` (100%)**, including offline still-authorized affected Nodes; `UP_JOIN_READY 0x49` is NOT `UP_SCHED_READY 0x4C`. Activate at common `K_TARGET`; prepared Nodes missing valid COMMIT must inhibit DATA TX from K_TARGET, including after reboot.
- No `3→2→1` Beacon countdown, no Schedule Lease. Shared Maintenance Control allocated only on demand; Join proceeds asynchronously via CAD at any time and can collide with scheduled traffic, leading to missing READY and ABORT/defer.
- Wire codepoint allocation 0x4B/0x4D, canonical Ed25519 signing transcript and `K_SCHED_READY` HKDF bytes must be frozen/tested before RF implementation. Their 80B signed Broadcast **format direction is approved**, not evidence of G2/HIL PASS.
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
| K_BEACON (HMAC-SHA256)  | 32B | PROVISIONED | PROVISIONED | metadata only | #209, group key compromise risk |
| Backend Ed25519 PubKey | 32B | PINNED | MAY VERIFY | PUBLIC | #208, PREPARE/DECISION verifier |
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
       - Project Owner đã chính thức phê duyệt định hướng áp dụng **bản tin quản trị/chẩn đoán riêng biệt có phiên bản (separate versioned diagnostic/management message)** để báo cáo `DROPPED_EVENT_COUNT` và `DIAG_SEQ` (không thêm retry/battery vào MVP 23B).
        - **Latest Owner decision (2026-11-07):** `UP_DIAG_METRICS 0x4A` **23B is APPROVED**; exact layout §3.3.6 and #204; 21B Health unchanged. Earlier candidate prohibition is superseded.

---

## 6. Ràng buộc Tần số, CAD + CSMA/CA và Thời gian Phản hồi — OWNER MVP BASELINE (DEC-273-01 / ADR-0004)

- **Bãi bỏ TDMA DATA Slots & Schedule Superframe (DEC-273-01 / ADR-0004):** Bãi bỏ hoàn toàn các thông số khe tĩnh `W_MS=500ms`, `G_MS=50ms`, chu kỳ 600ms/Node, 15 slots 9000ms, và khung READY 400ms/50ms.
- **Cơ chế truy cập vô tuyến CAD + Exponential Random Backoff (CSMA/CA):**
  - **Kiểm tra kênh (CAD):** Thời gian CAD trên SX1276 tương ứng $\sim 1.5 - 2$ ký hiệu LoRa ($\approx 1.5\text{ ms}$ tại SF7/BW 125kHz).
  - **Lùi ngẫu nhiên khi kênh bận:** Cửa sổ tranh chấp $CW_{\text{min}} = 16\text{ ms}$, $CW_{\text{max}} = 256\text{ ms}$. Lùi ngẫu nhiên theo hàm mũ tại lần thử $k$ ($CW_k = \min(CW_{\text{max}}, CW_{\text{min}} \cdot 2^{k-1})$), tối đa $\text{MAX\_CAD\_RETRIES} = 5$ lần thử.
  - **Phát sóng và Cửa sổ nhận ACK (Single RX Window):** Sau khi kênh rỗi, Node phát `UP_EVENT` (26 octets, ToA $\approx 50\text{ ms}$ tại SF7) và lập tức mở một cửa sổ RX đơn lẻ với thời gian chờ $T_{rx\_ack} \approx 200\text{ ms}$ để nhận `DOWN_EVENT_ACK` (0x42, 19 octets).
  - **Xử lý mất ACK (Event Retry):** Nếu hết thời gian chờ $T_{rx\_ack}$ mà không nhận được ACK hợp lệ, Node áp dụng thời gian lùi ngẫu nhiên ($1.000\text{ ms} - 3.000\text{ ms}$) và thử phát lại tối đa $\text{MAX\_EVENT\_RETRIES} = 3$ lần. Nếu vẫn không thành công, sự kiện được lưu giữ bền vững trong NVS FIFO theo chính sách `RING_BUFFER_DROP_OLDEST` (`DEC-127-04`).
- **Gateway Continuous RX 24/7:**
  - Gateway duy trì chip SX1276 ở chế độ nhận liên tục (`MODE_RXCONTINUOUS`) trên kênh tần số VN920 tĩnh đã được Backend cấp phát (CH00–CH10).
  - Khi nhận `UP_EVENT` hợp lệ: Gateway commit sự kiện vào bộ nhớ bền vững (WAL / SQLite), chuyển sang TX phát `DOWN_EVENT_ACK` (19 octets, ToA $\approx 36\text{ ms}$ tại SF7), sau đó lập tức hoàn trả radio về chế độ Continuous RX 24/7.
- **Join bất đồng bộ:** Asynchronous bất kỳ lúc nào qua SX1276 CAD + randomized bounded backoff, tối đa 3 lần thử lại. Sau khi hoàn tất Join V2 và kích hoạt phiên, Node sẵn sàng gửi sự kiện nút bấm qua CAD ngay lập tức mà không cần chờ lịch TDMA.
- **PHY SF7/SF8:** Công suất phát $\le +14\text{ dBm}$, tuân thủ hạn ngạch airtime pháp lý VN920 (Node $\le 1.0\%$, Gateway $\le 10\%$).

---

## 7. Tiêu chí Đóng băng Hợp đồng (Gate G2 Status)

- [x] Phê duyệt kiến trúc Event-Only, bãi bỏ PCSS và Local Alarm Autonomy vật lý (Quyết định Owner #230); nút bấm là nguồn sự kiện MVP.
- [x] **Phê duyệt chuyển đổi toàn diện từ Hybrid TDMA sang Pure CAD + Exponential Random Backoff (CSMA/CA) kết hợp Gateway Continuous RX 24/7 (Quyết định Owner DEC-273-01 / ADR-0004, Issue #273).**
- [x] Phê duyệt mã bản tin và bố cục gói tin Join V2 (0x45..0x48) và Post-Join (0x49).
- [x] Phê duyệt bộ quyết định an ninh mật mã `DEC-SEC-01` .. `DEC-SEC-07`.
- [x] Phê duyệt mã bản tin `UP_EVENT` (0x41) 26B, `DOWN_EVENT_ACK` (0x42) 19B, `UP_DIAG_METRICS` (0x4A) 23B; bãi bỏ `DOWN_SYNC_BEACON` (0x43) và Schedule Migration (`0x4B`/`0x4C`/`0x4D`).
- [x] Phê duyệt chính sách hàng đợi `RING_BUFFER_DROP_OLDEST` (`DEC-127-04`).
- [ ] Hoàn thành kiểm tra chéo Golden Vectors Go $\leftrightarrow$ ESP-IDF mbedTLS (Issue #173) $\to$ **NOT_VERIFIED**.
- [ ] Hoàn thành kiểm tra phân quyền ACL broker Mosquitto mTLS (Issue #174) $\to$ **NOT_VERIFIED**.
- [ ] Hoàn thành kiểm thử xung đột nguồn Gateway NVS HIL (Issue #175) $\to$ **NOT_VERIFIED**.
- [ ] Hoàn thành đo đạc vật lý thời gian thực RF và Guard Time (Issue #169) $\to$ **NOT_VERIFIED; không chặn bắt đầu lập trình MVP, nhưng không được tuyên bố RF/HIL PASS**.

**KẾT LUẬN G2: `NOT_VERIFIED`** — Tài liệu đã đối chiếu baseline thiết kế; còn cần wire Golden Vectors, session/Join/recovery security review; việc cấp chứng chỉ G2 PASS yêu cầu hoàn tất các bằng chứng kiểm thử thực tế từ các Issue phụ thuộc nêu trên.
