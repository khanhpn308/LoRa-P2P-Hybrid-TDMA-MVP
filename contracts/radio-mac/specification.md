# Custom LoRa P2P Radio MAC — giao diện Node ↔ Gateway

**LEGACY DRAFT · NOT JOIN IMPLEMENTATION SOURCE.** Agent: use [Bootstrap Join](bootstrap-join-v1.md) + [gates](bootstrap-join-gates.md). Header 8B/CRC16 below is obsolete for Join; J01 Request 35B and J02 M_ACCEPT 57B are OWNER_APPROVED_DESIGN. No production Join/DATA.

**Revision 0.1.0-draft · SECURITY / WIRE LAYOUT NOT FROZEN · Issue #12 · Gate G2: NOT_VERIFIED.**

## Approved design overlay (2026-11-02; G2 NOT_VERIFIED)

This legacy `MAGIC:0xA5` + 8B header + CRC16 and type registry below are **historical, not current V1 Join RF framing**. For implementation use [bootstrap-join-v1.md](bootstrap-join-v1.md):

| Decision | Approved design | Record |
|---|---|---|
| J01 | `UP_JOIN_REQUEST` **35B** = `0x22/DEVICE_MAC6/COUNTER2BE/RANDOM10/JOIN_PROOF16` | [Owner J01](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/124#issuecomment-6570037473) |
| J02 | `DOWN_JOIN_ACCEPT` **22B**, internal `M_ACCEPT` **57B**, `AUTH_TAG=first16(HMAC-SHA256(K_JOIN_ASSIGN_DL,M_ACCEPT))` | [Owner J02](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/124#issuecomment-6570268130) |
| RF-VER-TYPE-01 | `VER_TYPE` 1B; high 3 bits version, low 5 bits packet type; approved V1 type allocation | [Owner registry](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568296930) |
| RF-BEACON-GWID-01 | Beacon fixed candidate `VER_TYPE1 + GW_ID1 + SF_EPOCH4 + SCHED_VER2 + ACK_BITMAP2 + CTRL_FLAGS1 = 11B` (without auth/extension/PHY overhead); **not** whole-Beacon freeze | [Owner decision](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6562886560) |
| RF-BEACON-AUTH-01 | **Selected Beacon profile: Group HMAC-SHA256/16B tag**; base frame **28B** = 11B core + 1B `BCN_KEY_ID` + 16B HMAC tag, NOT Ed25519 76B | [Owner selection](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6575398231) |
| RF-ALERT-01 | `UP_ALERT` application payload exactly **3B**: `ALERT_REASON1 + TEMP_X10:int16 2`; endian/invalid codes and full RF frame remain OPEN | [Owner decision](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6560942726) |

**Do not implement the legacy 14B Beacon or 12B Alert as approved on-air formats. The 28B Group-HMAC Beacon above is the selected design, not the completed G2 security contract.** J06 authenticated Gateway identity, J07 Counter lifecycle and full G2/G3/HIL/interop remain OPEN; Owner approval alone never enables DATA/Join TX.

### RF-BEACON-AUTH-01 — Lightweight Beacon profile (Owner-approved design; G2 NOT_VERIFIED)

**Chosen base RF Beacon MAC frame: 28B total.** Byte offsets are zero-based within SX1276 MAC payload; PHY preamble/header/CRC airtime is separate. No legacy 8B MAC header/CRC16.

| Offset | Field | Size | Rule / remaining decision |
|---:|---|---:|---|
| 0 | `VER_TYPE` | 1B | Exact `0x21`, GW→Node broadcast |
| 1 | `GW_ID` | 1B | Existing Owner-approved width; reserved values/provisioned mapping still require review |
| 2–5 | `SF_EPOCH` | 4B | Replay/sync counter; endian/reboot/holdover rules still require freeze |
| 6–7 | `SCHED_VER` | 2B | Owner-approved width; wrap/version mapping OPEN |
| 8–9 | `ACK_BITMAP` | 2B | Telemetry ACK only; not Join/Alert/Confirm |
| 10 | `CTRL_FLAGS` | 1B | Exact flag assignment and extension presence still OPEN |
| 11 | `BCN_KEY_ID` | 1B | Selector of a provisioned, versioned Group Beacon key; mapping/lifecycle OPEN |
| 12–27 | `BCN_AUTH_TAG` | 16B | First 16 bytes of HMAC-SHA256 under the selected group key over a domain-separated canonical Beacon transcript; **transcript bytes not yet frozen** |
| **Total** | | **28B** | **Owner-selected Group HMAC profile**; not G2/security/interop PASS |

**Algorithm choice locked:** Group HMAC-SHA256 with a 16B tag; **Ed25519 64B signature / 76B Beacon is not the selected V1 base profile**. This freezes the selected algorithm and base field widths, **not** the currently OPEN cryptographic transcript/byte order, trusted Gateway identity (J06), distribution/protection/rotation/revocation of the newly proposed `K_BEACON_GROUP`, persistent replay state, or active schedule authorizations. `K_BEACON_GROUP` must not be implicitly derived from `K_JOIN` or substituted by session keys without separate approved KDF/key lifecycle review.

**Security trade-off:** Any compromised Node holding the shared Beacon HMAC key can forge a tag-valid Beacon. A valid Group HMAC proves only **group-key possession**, not unique Gateway origin; it does not resolve J06. Unknown key selectors/bad tags/invalid length/replay must fail closed; compare tags in constant time and never grant TX solely because a Beacon tag validates.

**JOIN_OPEN extension:** Existing 16B JOIN_OPEN extension is a **candidate**, not selected as part of the 28B base frame. Illustrative extended Beacon length **44B** (11B core + 16B extension + 1B key selector + 16B tag), only after versioned presence/placement, authenticated transcript and lifetime rules are separately approved. Default `JOIN_CLOSED`. Do not append unauthenticated extension bytes or change Beacon length based on guesswork.

**Testing:** Complete ToA/guard budget across supported SF/BW/CR, single-SX1276 half-duplex scheduling, independent C↔Go golden vectors, human Security/RF review and regulatory/HIL evidence remain `NOT_VERIFIED`. Source: [Owner Beacon choice](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6575398231).

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
