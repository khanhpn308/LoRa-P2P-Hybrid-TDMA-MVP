# Custom LoRa P2P Radio MAC — giao diện Node ↔ Gateway

**LEGACY DRAFT · NOT JOIN IMPLEMENTATION SOURCE.** Agent: use [Bootstrap Join](bootstrap-join-v1.md) + [gates](bootstrap-join-gates.md). Header 8B/CRC16 below is obsolete for Join; Request 35B candidate and `M_ACCEPT` OPEN. No production Join/DATA.

**Revision 0.1.0-draft · SECURITY / WIRE LAYOUT NOT FROZEN · Issue #12 · Gate G2: NOT_VERIFIED.**

## 1. Phạm vi và trách nhiệm

- **Node**: thu Beacon, đồng bộ, chỉ TX trong slot được phân hoặc cửa sổ ưu tiên được phép, theo dõi ACK, backoff, giới hạn airtime cục bộ.
- **Gateway**: nguồn thời gian/superframe cục bộ, RX/TX trên một SX1276 bán song công, validate MAC, ACK, lưu active/shadow schedule, phát Beacon và fallback khi mất MQTT.
- **Backend**: không được tạo lệnh bật/tắt TX/RX theo slot. Định nghĩa JSON lịch trên MQTT; radio schedule do Gateway thực thi.
- **PHY**: SX1276 LoRa P2P, không phải LoRaWAN. Tần số, SF, BW, CR, preamble, sync word, power, header mode, CRC PHY phải được provision nhất quán và G1 phê duyệt.

## 2. Candidate legacy envelope — KHÔNG ĐƯỢC DÙNG NHƯ PRODUCTION v1

Tài liệu đính kèm §6.1 đề xuất chuỗi octet (offset từ 0):

| Offset | Trường | Quy tắc candidate |
|---:|---|---|
| 0 | MAGIC | 0xA5 |
| 1 | VER_TYPE | b7..6 protocol version, b5..0 packet type |
| 2 | CTRL_FLAGS | b7..6 priority; b5 ACK_REQ; b4 IS_RETRY; b3 PENDING_SCHED; b2 DUTY_LIMITED; b1..0 reserved=0 |
| 3 | SRC_ID | 0x00 Gateway; 1..254 Node |
| 4 | DST_ID | 0x00 Gateway; 1..254 Node; 0xFF broadcast |
| 5 | SCHED_VER | chỉ 8-bit, **không đủ** để giải quyết wrap/epoch |
| 6 | SEQ_NUM | chỉ 8-bit, **không phải** replay/identity key |
| 7 | PAYLOAD_LEN | 0..48 byte được đề xuất |
| 8.. | PAYLOAD | độ dài PAYLOAD_LEN |
| last 2 | CRC16-CCITT | phụ thuộc tham số init/reflection/xor/endian **chưa chốt** |

Tổng kích thước candidate: 8 + n + 2 byte (tối đa 58). `CRC16` và PHY CRC **chỉ phát hiện lỗi ngẫu nhiên**, không bảo vệ khỏi sửa dữ liệu có chủ ý, giả mạo Beacon/ACK/Schedule/Command hoặc replay. Giá trị đầu ra "8 bytes" và giả định ToA 22B từ tài liệu là giả thuyết và có thể phải thay hoàn toàn sau khi thêm MIC, counters và network/session identity. **Cấm xuất bản codec production từ bảng trên khi D01/D11 còn BLOCKED.**

### Loại bản tin candidate

| Type | Mã candidate | TX → RX | Ý nghĩa |
|---|---|---|---|
| BEACON | 0x01 | GW → Broadcast | Superframe, active/pending version, ACK bitmap |
| SCHED_ANNOUNCE | 0x02 | GW → Broadcast/Node | Bảng mapping node/slot cho lịch sẽ kích hoạt |
| DATA_TELEMETRY | 0x03 | Node → GW | Định kỳ trong slot riêng |
| PRIORITY_ALERT | 0x04 | Node → GW | Cảnh báo trong PCSS hoặc retry slot riêng |
| ACK_PACKET | 0x05 | GW → Node | Xác nhận RF cụ thể theo frame/session |
| CMD_DOWNLINK | 0x06 | GW → Node | Lệnh được Backend duyệt qua GW |
| JOIN_SLOT_REQ | 0x07 | Node → GW | Gia nhập/khôi phục có rate limit |
| JOIN_SLOT_RSP | 0x08 | GW → Node | Thông tin cấp slot/trạng thái |

Payload candidate từ §6.2: BEACON 14B (`superframe_seq:u32`, `epoch_sec:u32`, `superframe_dur_ms:u16`, `pending_sched_ver:u8`, `countdown:u8`, `ack_bitmap:u16`); DATA/ALERT 12B (`slot_id:u8`, `sensor_status_mask:u8`, `ch1:i16`, `ch2:u16`, `ch3:u16`, `battery_mv:u16`, `node_duty_permille:u16`). Byte order, signedness và scale trong bảng chỉ mô tả **đề xuất**, chưa có vector chuẩn.

## 3. Security acceptance requirements trước khi freeze v1

1. Mỗi gói điều khiển (**Beacon, Schedule, Join response, Downlink, ACK**) và gói data phải có xác thực nguồn và toàn vẹn mật mã; **không** chỉ CRC, MQTT TLS hoặc sync word. Quyết định AEAD/tag length, nonce và MIC/AAD bằng ADR security review.
2. Nonce phải duy nhất **trên cùng khóa**, bao gồm **sau mất điện/reset**, phiên/mạng, chiều GW→Node vs Node→GW và rollover counter. Chặn TX nếu không chứng minh được nonce uniqueness; cấm tự reset counter về 0 trên khóa cũ.
3. Rx giữ replay window theo identity + crypto session + hướng; đồng hồ không được dùng làm replay protection duy nhất. Retry có thể trùng packet/ciphertext, nhưng không tái sử dụng nonce cho **plaintext khác**. ACK được liên kết session + message ID/sequence, tránh ACK giả.
4. Key provisioning, rotate/revoke, node join trust bootstrap, gateway replacement, key storage và MAC tag verification **chưa phê duyệt**; không tự sinh khóa mặc định dùng production.
5. Parser kiểm version, direction, destination, reserved bits, payload length, auth tag, replay window, bounds **trước** xử lý payload. Serialize từng octet rõ ràng, không cast raw FIFO thành `packed struct`; integer endian phải được G2 chốt.
6. Thống kê rejected reason bằng mã cố định (`BAD_LENGTH`, `UNSUPPORTED_VERSION`, `BAD_AUTH`, `REPLAY`, `WRONG_DEST`, `STALE_SCHEDULE`, `UNSYNCED`, `AIRTIME_DENIED`). Không xuất tag, key hay nonce bí mật vào log.

## 4. Timing/safety và acceptance

Xem [tdma-schedule.md](tdma-schedule.md) để biết profile thời gian *đề xuất*, staged switch, xử lý mất Beacon. Giới hạn airtime áp dụng **mọi** gói RF, kể cả alert/join/retry/ACK/beacon; lỗi policy là **deny TX** và log. CAD không bảo đảm kênh rỗi; Gateway chỉ RX/TX một chế độ tại một thời điểm. ISR chỉ ghi timestamp/chuyển sự kiện, không SPI hay MQTT blocking.

### Freeze checklist (chưa đạt)

- [ ] ADR security + byte layout endianness + key/nonce/replay lifecycle + boot persistence (D01/D11).
- [ ] RF airtime/guard/antenna/frequency/power/duty G1 + HIL timing.
- [ ] Canonical test vectors thực có valid/bad MIC/truncated/wrong version/replay/wrap/reset; C và Go đối chiếu byte-đối-byte.
- [ ] Review bởi Node, Gateway, Security, Backend và QA; ghi nhận chứng cứ G2.

Test-plan hiện tại: [test-vectors/README.md](test-vectors/README.md); chưa có golden byte vectors vì thiết kế xác thực chưa được chốt.
