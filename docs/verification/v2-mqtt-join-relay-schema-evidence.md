# Verification Dossier: MQTT V2 Join Hello Relay Envelope Contract (#221)

> **Status:** `CONTRACT_VALIDATED` · **Issue:** [#221](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/221) · **Prerequisite for:** [#218](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/218) (Phase 2B)
> **Authority:** Owner-approved V2 Join Architecture (`DEC-SEC-01` .. `DEC-SEC-07`, [Issue #127](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6628167582), [PR #198](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/198))
> **Scope:** `contracts/README.md`, `contracts/mqtt/topics.md`, `contracts/mqtt/semantic-rules.md`, `contracts/mqtt/schemas/join-hello.schema.json`, `contracts/mqtt/examples/cases.json`, `docs/verification/v2-mqtt-join-relay-schema-evidence.md`

---

## 1. Mục đích và Bối cảnh

Issue #218 (Phase 2B: MQTT V2 Join relay envelope ingest & server wiring) trước đó bị chặn bởi điều kiện tiên quyết:
- **Thiếu JSON Schema và Topic hợp đồng** cho bản tin relay `UP_JOIN_HELLO` (0x45, 68B) từ Gateway lên Backend qua Mosquitto MQTT 5.0.
- Theo quy định nghiêm ngặt tại [`AGENTS.md`](../../AGENTS.md), không được tự ý sáng chế cấu trúc envelope và không được sửa `contracts/` ngoài scope cho phép của Issue #218.

Issue #221 giải quyết rào cản này bằng cách chính thức hóa:
1. Topic chuẩn: `iot/v1/gw/{gateway_id}/uplink/join-hello` (QoS 1, `Retain=false`).
2. JSON Schema: `contracts/mqtt/schemas/join-hello.schema.json` (Draft 2020-12).
3. Bất biến ngữ nghĩa: Quy tắc `JH-01` .. `JH-08` trong `contracts/mqtt/semantic-rules.md`.
4. Fixtures kiểm thử hợp đồng: 5 ca kiểm thử hợp đồng (1 positive, 4 negative) trong `contracts/mqtt/examples/cases.json`.

---

## 2. Đặc tả Giao diện & Ràng buộc Mật mã

### 2.1. Cấu trúc Khung tin V2 `UP_JOIN_HELLO` (0x45, 68B)
```text
VER_TYPE=0x45:1 | DEVICE_MAC:6 | TARGET_GW_ID:1 | JOIN_COUNTER:uint32BE:4 | NODE_NONCE:8 | NODE_X25519_PUB:32 | JOIN_PROOF:16
```
Tổng cộng: 68 bytes. Khung tin được mã hóa dưới dạng chuỗi thập lục phân 136 ký tự hex trong trường `raw_frame_hex`.

### 2.2. Trường dữ liệu Envelope (`join-hello.schema.json`)

| Trường | Kiểu dữ liệu | Ràng buộc / Định dạng | Ý nghĩa |
|---|---|---|---|
| `schema_version` | string | Const `"1.0-draft"` | Phiên bản schema |
| `event_id` | string | Pattern `<gw_id>:<epoch_uuid>:<seq>` | Định danh duy nhất ổn định qua QoS1 retry |
| `gateway_id` | string | `^[A-Za-z0-9_-]{1,32}$` | Định danh trạm phát (khớp với topic & mTLS cert) |
| `gateway_epoch` | string | UUID RFC 4122 | Epoch khởi động của Gateway |
| `event_seq` | string | Decimal uint64 | Bộ đếm tăng đơn điệu trong epoch |
| `observed_at` | string / null | RFC3339 UTC Z | Thời gian thu nhận nếu có nguồn tin cậy |
| `observed_time_source`| enum | `gateway_utc`, `node_utc`, `estimated`, `unknown` | Nguồn gốc đồng hồ |
| `radio_rx_monotonic_us`| string | Decimal uint64 | Microsecond cục bộ của Gateway SX1276 |
| `buffered` | boolean | true / false | Cờ đánh dấu sự kiện từ hàng đợi ngoại tuyến |
| `target_gw_id` | integer | `1 .. 254` (0x01 .. 0xFE) | Mã số Gateway mục tiêu (khớp byte 7 của raw frame) |
| `raw_frame_hex` | string | `^[0-9a-fA-F]{136}$` | Đúng 136 ký tự hex của khung `UP_JOIN_HELLO` 68B |
| `rssi` | integer | `-140 .. 0` dBm | Cường độ tín hiệu đo bởi SX1276 |
| `snr` | number | `-30.0 .. 30.0` dB | Tỷ số tín hiệu trên nhiễu đo bởi SX1276 |

---

## 3. Bất biến Ngữ nghĩa Bắt buộc (Rules JH-01 .. JH-08)

1. **JH-01 (Zero-Knowledge tại biên):** Gateway chỉ relay khung tin thô 68B; Gateway không có khóa $K_{\text{JOIN}}$ hay $K_{\text{JREQ}}$.
2. **JH-02 (Identity Binding):** Broker xác thực Gateway qua mTLS; topic và payload `gateway_id` phải khớp cert. Backend ánh xạ `gateway_id` sang `target_gw_id` và kiểm tra khớp byte 7 của RF frame.
3. **JH-03 (Frame Invariants):** `raw_frame_hex` phải đúng 136 hex; byte 0 là `0x45`, `target_gw_id` $\in [1..254]$, `join_counter` $\notin \{0, 0xFFFFFFFF\}$, MAC và PubKey khác $0^{all}$.
4. **JH-04 (HMAC Authentication):** Backend tra cứu thiết bị `ACTIVE`, phái sinh $K_{\text{JREQ}}$ qua HKDF, so sánh `JOIN_PROOF` bằng constant-time.
5. **JH-05 (Anti-Replay & Idempotency):**
   - `join_counter > last_join_counter`: ghi nhận `HELLO_AUTHENTICATED_PENDING_GRANT`, tăng counter.
   - `join_counter <= last_join_counter`: nếu `raw_hello_sha256` khớp từng byte, trả về kết quả idempotent; nếu khác, báo động Replay Attack.
6. **JH-06 (QoS 1 Dedup):** Khử trùng lặp qua `UNIQUE(gateway_id, event_id)`.
7. **JH-07 (Timing):** Nếu `observed_time_source=unknown` thì bắt buộc `observed_at=null`.
8. **JH-08 (No Data Grant):** Trạng thái sau Hello chỉ là `HELLO_AUTHENTICATED_PENDING_GRANT`; không cấp quyền phát sóng TDMA DATA.

---

## 4. Kết quả Thực thi Kiểm tra Tự động

Lệnh thực thi:
```bash
/usr/bin/python3 contracts/tests/check_contracts.py
```

Kết quả:
```text
PASS T-VALID (schema=True)
PASS T-MISSING-ID (schema=False)
PASS T-SEQ-OVERFLOW (schema=False)
PASS ALERT-VALID (schema=True)
PASS ALERT-SEVERITY-INVALID (schema=False)
PASS SCHEDULE-VALID (schema=True)
PASS SCHEDULE-DURATION-INVALID (schema=False)
PASS SCHEDULE-DUPLICATE-SLOT (schema=True)
PASS SCHEDULE-ACK-VALID (schema=True)
PASS SCHEDULE-ACK-INVALID-NACK-REASON (schema=False)
PASS STATUS-VALID (schema=True)
PASS COMMAND-VALID (schema=True)
PASS COMMAND-ACK-VALID (schema=True)
PASS SCHEDULE-ACK-ACTIVE-VALID (schema=True)
PASS SCHEDULE-ACK-ACTIVE-MISSING-ACTUAL (schema=False)
PASS SCHEDULE-ACK-STAGED-HAS-ACTUAL (schema=False)
PASS COMMAND-ACK-REJECTED-VALID (schema=True)
PASS COMMAND-ACK-REJECTED-WITH-NONE (schema=False)
PASS STATUS-UNKNOWN-TIME-VALID (schema=True)
PASS STATUS-UNKNOWN-TIME-HAS-TIMESTAMP (schema=False)
PASS COMMAND-BAD-PARAM-KEY (schema=False)
PASS SCHEDULE-NONUTC-TIMESTAMP (schema=False)
PASS TELEMETRY-BAD-EVENT-ID (schema=False)
PASS SCHEDULE-V2-VALID (schema=True)
PASS SCHEDULE-V2-OVERLAPPING-SLOT (schema=True)
PASS SCHEDULE-V2-INVALID-DURATION (schema=False)
PASS STATUS-V2-DIAGNOSTIC-VALID (schema=True)
PASS STATUS-V2-INVALID-CHANNEL (schema=False)
PASS JOIN-HELLO-VALID (schema=True)
PASS JOIN-HELLO-INVALID-HEX-LENGTH (schema=False)
PASS JOIN-HELLO-RESERVED-TARGET-GW (schema=False)
PASS JOIN-HELLO-UNKNOWN-TIME-HAS-TIMESTAMP (schema=False)
PASS JOIN-HELLO-MALFORMED-EVENT-ID (schema=False)
PASS WS-ALERT-VALID (schema=True)
PASS WS-ALERT-MISSING-ID (schema=False)
PASS WS-ALERT-UNKNOWN-TYPE (schema=False)
PASS WS-SCHEDULE-VALID (schema=True)
PASS WS-TELEMETRY-VALID (schema=True)
PASS WS-STATUS-VALID (schema=True)
PASS WS-TELEMETRY-BAD-SOURCE-EVENT-ID (schema=False)
PASS WS-TELEMETRY-BAD-READING-ID (schema=False)
PASS WS-SCHEDULE-ACTIVE-VALID (schema=True)
PASS WS-SCHEDULE-UNKNOWN-STATE (schema=False)
PASS WS-ALERT-NONUTC (schema=False)
PASS WS-COMMAND-VALID (schema=True)
PASS WS-COMMAND-NODE-ACKED-VALID (schema=True)
PASS WS-COMMAND-MISSING-REVISION (schema=False)
PASS WS-COMMAND-INVALID-UUID (schema=False)
PASS WS-COMMAND-INVALID-STATE (schema=False)
PASS WS-COMMAND-INVALID-REVISION (schema=False)
PASS WS-COMMAND-EXTRA-FIELD (schema=False)
PASS OpenAPI semantic spec + 18 HTTP operations
PASS: 11 schemas, 33 MQTT cases, 18 WS cases, 18 REST operations
NOT VERIFIED: device/auth/nonce/timing/RF, MQTT roundtrip, HTTP/WSS implementation.
```

---

## 5. Ranh giới Chứng cứ (Evidence Boundary)

- **Hợp đồng & Schema:** `PASS` (11 schemas, 33 MQTT cases được kiểm tra cú pháp và điều kiện format).
- **Backend Go Ingest Handler:** Triển khai tại [Issue #218](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/218) (Phase 2B).
- **Mosquitto mTLS ACL & End-to-end Integration:** Đo kiểm thực tế trong #218 và #174.
- **Phần cứng thật / HIL / RF:** `NOT_VERIFIED` (chờ đo kiểm trên bench phần cứng #169).
