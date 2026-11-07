# MQTT v1 — Semantic invariants & schema review (Issue #14 / Step A)

**Status:** `DRAFT / PENDING Gateway + Go Backend + Infrastructure/Security approval`. **MQTT version:** 5.0 Owner-accepted via ADR-0002. **Implementation, contract tests and RF/HIL:** `NOT_VERIFIED`. This file complements [topics.md](topics.md) and seven [schemas](schemas/); it is **not** permission to change Radio MAC. BM03 (learning document supplied for review), OASIS MQTT 5.0 and the existing repository contracts informed this specification.

## 1. Ownership and validation layers

| Check | Owner / gate | JSON Schema alone? |
|---|---|---|
| JSON UTF-8, required fields, types, enums, date-time with UTC `Z`, UUID format, conditional ACK fields | Gateway producer + Go consumer (draft) | YES with Draft 2020-12 and **enabled FormatChecker** |
| Topic ↔ authenticated principal ↔ payload `gateway_id` match | Mosquitto ACL + Backend/Gateway application check | NO |
| QoS 1, `Retain`, Message Expiry, SUBACK Granted QoS, Clean Start, Session Expiry, TLS cert/ACL | MQTT 5 transport and broker configuration | NO |
| `event_id` component equality; anti-duplicate DB uniqueness; timestamp plausibility | Backend ingestion | NO |
| Schedule monotonic version, dedup request, expiry with trusted clock, collision, airtime, staged→active | Gateway executor + Backend planner | NO |
| Command action-specific parameters, authorization, command expiry, radio ACK and actuator safety | Backend + Gateway + Node | NO |

**Normative status:** all `MUST` statements below are *proposed* contract rules until required human sign-offs. JSON Schema PASS proves neither authorization nor schedule safety nor MQTT delivery.

## 2. Event identity, buffering and clock

1. Uplink `event_id` is a stable tuple encoded as `<gateway_id>:<gateway_epoch>:<event_seq>`; the three components **MUST** match their respective fields. Schema checks its syntax, Backend checks component equality. `gateway_epoch` is one random UUID per **Gateway boot**, not per MQTT reconnect. `event_seq` is an unsigned 64-bit decimal string incremented once per newly captured logical event, with no silent wrap/reuse. RNG/counter persistence correctness remains `NOT_VERIFIED`.
2. When an event is written to a durable offline queue, the record **MUST** preserve its original ID, boot epoch, seq, node info, measured payload and timestamps through reboot/retransmission. Re-publishing the *same* event cannot mint another event ID. `buffered` describes queue history and may switch false→true on retry; it is **not** identity. The consumer dedup key is `UNIQUE(gateway_id,event_id)`; mismatching immutable business payloads under one key **MUST** be quarantined/flagged rather than silently overwriting a previously committed record (DB implementation in #18).
3. A new MQTT Packet Identifier or DUP flag does not define application identity. RF `seq_num` (8-bit) and `superframe_seq` are **not** sufficient DB keys. Duplicate RF packets and duplicate MQTT deliveries are distinct dedup layers.
4. `observed_at` is an RFC3339 UTC `Z` time or `null`, `observed_time_source` identifies its provenance. `unknown` **MUST** imply `observed_at=null`. `radio_rx_monotonic_us` is gateway-local time only, not wall-clock or a cross-boot sequence. Backend sets `ingested_at` with its own UTC clock; never replace an unknown occurrence timestamp with ingest time without preserving provenance.
5. Uplink with missing/invalid schema, wrong authenticated Gateway/topic, ambiguous identity or conflicting duplicate payload is rejected/quarantined per backend policy; it cannot mutate schedule/actuator state.

## 3. MQTT 5.0 transport, ACL, staleness

- Names: `iot/v1/gw/{gateway_id}/{uplink|downlink}/{type}` exactly as [topics.md](topics.md). Broker must authorize by authenticated username or verified certificate and bind it to the Gateway namespace; a self-declared `ClientID`/payload alone is **not** a security principal. Gateway `gw01` publishing `gw02` data is denied.
- All topics use QoS 1. For a required QoS 1 subscription, `SUBACK 0x01` is success; `0x00` (Granted QoS 0), `0x02` (unexpected QoS 2) and error codes must not be silently reported as the agreed `READY` profile. Subscription verification is required after reconnect; `Session Present` alone is insufficient.
- Gateway uses `Clean Start=1`, `Session Expiry=0`, resubscribes after reconnect; Backend uses stable ClientID, `Clean Start=0`, `Session Expiry>0` with bounded/persistent broker queue. Concrete duration, capacity, LWT profile and broker crash behavior require integration measurements/approval.
- Backend publishes `downlink/schedule` and `downlink/command` with **Retain=false** and MQTT 5 `Message Expiry Interval = floor(expires_at - publish_time in seconds)`, bounded to 1..4294967295 and never exceeding remaining validity. Do **not** publish if less than one whole second remains or trusted UTC is missing. Gateway independently checks payload `expires_at` against trusted UTC at processing time; broker expiry does not make payload safe.
- On downlink subscription set `Retain Handling=2` (avoid historical retained messages on SUBSCRIBE); reject any improperly retained schedule/command if delivered. A previously retained legacy schedule must be cleared under an explicit broker operations procedure, not silently activated. `Retain As Published` and retained flag do **not** alone establish data freshness.
- `uplink/status` Retain=true is **last-known snapshot**, not online proof. LWT, heartbeat, broker session state and Backend ingress-time freshness require a separate verified presence policy. MQTT Will Delay can be truncated by session termination (`Session Expiry=0`). No unsupported claim of prompt/discrete disconnect detection.
- MQTT `PUBACK` confirms a single transport hop; Backend persistence and Node command execution require separate evidence. Use durable commit-before-ACK/error quarantine and bounded retry as proposed implementation for #18; none is verified by this document.

## 4. TDMA schedule state machine

**Backend durable states:** `PROPOSED`, `SENT`, `STAGED`, `ACTIVE`, `REJECTED`, `EXPIRED`.

| From | Event / validation | To | Critical rule |
|---|---|---|---|
| PROPOSED | Published valid proposal with same stable `request_id` on retry | SENT | MQTT PUBACK is **not** STAGED |
| SENT | Gateway `STAGE_ACK`, matching gateway/request/schedule/version | STAGED | Gateway validated and durably staged; **not ACTIVE** |
| SENT/STAGED | `VERIFY_NACK` or local validation/security failure | REJECTED | Record `reason_code`; old active schedule unchanged |
| SENT/STAGED | Acceptance deadline passes before real activation | EXPIRED | Do not auto-activate; reconcile delayed reports safely |
| STAGED | `ACTIVE_REPORT` matching request/version/gateway/epoch and actual local superframe activation | ACTIVE | This is the **only transition** to ACTIVE |
| ACTIVE | Duplicate/late `STAGE_ACK`, old ACK/NACK/replay | ACTIVE | Never regress a newer active version from stale messages |

Gateway validates gateway/topic/auth provenance, schema, monotonic **Backend** schedule version, identity, expiry and a safe activation horizon; persists shadow schedule, announces for at least `min_announce_superframes` **complete** superframes, then switches at a local boundary. It reports `STAGE_ACK` only after durable staging, and `ACTIVE_REPORT` only after actual local switch. `activate_at_superframe_seq` = planned boundary; new `activated_at_superframe_seq` = actual observed boundary and is **required only on ACTIVE_REPORT**. `reason_code=NONE` for ACK/ACTIVE; NACK requires a non-NONE reason. `activated_at_superframe_seq` is null or absent for ACK/NACK.

A delayed, buffered `ACTIVE_REPORT` after Backend marked EXPIRED must be reconciled against Gateway current status and trustworthy reported activation epoch/sequence **before** any transition; no blind state flip. `expires_at` is the deadline for accepting/activating this proposal, **not** an unapproved periodic schedule lease (separate design needed for lease revocation). Boot/reconnect and active/shadow NVS recovery require idempotent reconciliation; a shadow proposal is never silently activated on reboot. If UTC is untrusted at acceptance, fail closed. A schedule may continue locally while backhaul is absent only under the separate active-schedule safety requirements.

Schedule `P-10S-15` (superframe_ms=10000, 400 ms slots) là **hình học ứng viên lịch sử V1** phục vụ kiểm tra tương thích ngược. Kiến trúc V2 chuẩn hóa hình học **`V2-VN920-STATIC-15N`** (Owner MVP baseline #206, #208):
- Độ rộng khe hữu dụng `W_MS = 500ms`, `G_MS = 50ms` bảo vệ mỗi bên $\to$ chu kỳ khe `600ms/Node`.
- 15 vị trí tĩnh chiếm trọn **9000ms** của superframe DATA (`start(i) = (i-1)*600 + 50`, `end(i) = start(i) + 500`).
- Mỗi khe W_MS tích hợp: phát `UP_EVENT 0x41` (26B), Gateway xác thực + ghi bền vững WAL, đảo chiều RX/TX và phát ngay `DOWN_EVENT_ACK 0x42` (19B) trong cùng khe.
- Khe READY trong chuyển đổi lịch: `R_MS = 400ms` hữu dụng + `G_R_MS = 50ms` mỗi bên $\to$ chu kỳ khe `500ms/Node` (7500ms cho 15 Node), kích hoạt theo yêu cầu trong chu kỳ Maintenance. Yêu cầu 100% Node bị ảnh hưởng báo READY trước khi ký COMMIT tại `K_TARGET`.
- Chu kỳ Maintenance danh định ~300s. Mất >3 Beacon liên tiếp $\to$ chuyển trạng thái mất đồng bộ, cấm phát DATA khi độ tin cậy đồng hồ không đảm bảo; lịch ACTIVE không tự động xóa bỏ.
- Join khởi tạo bất đồng bộ qua CAD (tối đa 3 lần thử lại). Reboot đưa Node về trạng thái RX-only cho đến khi Backend xác thực kích hoạt lại. JSON Schema kiểm tra khuôn dạng; kiểm tra ranh giới, không chồng lấn và bảo vệ vật lý do Validator và Gateway đảm nhiệm.

## 5. Error codes and ACK semantics

`schedule-ack.stage` is one of `STAGE_ACK | VERIFY_NACK | ACTIVE_REPORT`. `reason_code` is an **application code**, not MQTT 5 reason code:

| Code(s) | Meaning / owner |
|---|---|
| `NONE` | Successful STAGE_ACK or ACTIVE_REPORT only |
| `BAD_SCHEMA`, `BAD_VERSION`, `WRONG_GATEWAY` | Gateway local parsing/version/identity failure |
| `UNTRUSTED_CLOCK`, `INVALID_TIME_WINDOW`, `EXPIRED` | Missing trusted UTC, inconsistent validity, or expired proposal |
| `STALE_VERSION`, `REPLAYED_REQUEST`, `RETAINED_STALE` | Old/conflicting version, replayed request, or stale retained proposal |
| `OVERLAPPING_SLOT`, `AIRTIME_LIMIT`, `UNSUPPORTED_PROFILE`, `INSUFFICIENT_ANNOUNCEMENT_HORIZON` | Invalid local schedule/airtime/timing profile |
| `PERSIST_FAILED`, `INTERNAL_ERROR` | Staging durability/runtime failure |
| `BAD_AUTH` | Only when a Gateway-side application identity/auth validation can legitimately detect it; broker ACL denial is observed at Broker/Publisher, not guaranteed to produce a Gateway NACK |

`command-ack.status` is one of `QUEUED | DISPATCHED | NODE_ACKED | REJECTED | EXPIRED | UNKNOWN`. Success/queueing states require `reason_code=NONE`; rejected/expired/unknown require a specific error, and EXPIRED uses `EXPIRED`. Draft error enum: `BAD_SCHEMA, BAD_AUTH, WRONG_GATEWAY, EXPIRED, STALE_COMMAND, DUPLICATE_CONFLICT, UNSUPPORTED_ACTION, BAD_PARAMS, AIRTIME_LIMIT, NODE_NACK, NODE_TIMEOUT, UNTRUSTED_CLOCK, INTERNAL_ERROR` (plus NONE). `NODE_ACKED` is **Node-level** acknowledgment, not Gateway MQTT PUBACK. No arbitrary string accepted as an error code.

`command.params` keys are only syntactically constrained by JSON Schema. Their action-specific allowlist, actuator safety and permissions **MUST** be reviewed before real command execution; schema validation alone never enables `SET_RELAY`. No unstated signing/MIC mechanism is assumed: MQTT TLS+broker identity are transport properties; Radio MAC authentication is separately BLOCKED #12.

## 6. Review matrix for seven schemas (no test verdict asserted)

| File | Schema-layer checks | Semantic/integration rules outside schema |
|---|---|---|
| [telemetry](schemas/telemetry.schema.json) | Mandatory envelope, 8-bit RF seq bound, raw measurement ranges, UTC source conditional | RF dedup vs MQTT dedup; sensor scaling/config and DB commit |
| [alert](schemas/alert.schema.json) | Severity enum, mandatory envelope, optional trigger object | No fabricated trigger from missing RF payload; P0 prioritization/ACK |
| [status](schemas/status.schema.json) | Mode/ranges + optional active/staged references | Retained snapshot not online; reconciliation/LWT |
| [schedule](schemas/schedule.schema.json) | UUIDs, deadlines RFC3339 UTC, candidate slot shape | expiry ordering, unique non-overlap, timing/airtime, version/epoch |
| [schedule-ack](schemas/schedule-ack.schema.json) | Stage/code conditional; actual activation field only required for ACTIVE_REPORT | Backend state transitions, reordered reports, actual activation verification |
| [command](schemas/command.schema.json) | Proposed action enum, params type/key shape, deadlines | per-action parameter allowlist, expiry/authorization/airtime |
| [command-ack](schemas/command-ack.schema.json) | Enumerated error codes and status-dependent constraints | Node acknowledgment evidence, duplicate command responses |

**Original examples** in [examples/cases.json](examples/cases.json): `T-VALID/T-MISSING-ID/T-SEQ-OVERFLOW`, `ALERT-VALID/ALERT-SEVERITY-INVALID`, `SCHEDULE-VALID/SCHEDULE-DURATION-INVALID/SCHEDULE-DUPLICATE-SLOT`, `SCHEDULE-ACK-VALID/SCHEDULE-ACK-INVALID-NACK-REASON`, `STATUS-VALID`, `COMMAND-VALID`, `COMMAND-ACK-VALID`. Additional schema-shape examples added here cover ACTIVE_REPORT/ACK invariants, enum errors, unknown-time, UTC, invalid command key and malformed event ID. Runtime behavior/replay/authorization tests and actual reports belong to **Step B**, `tests/contract/`. No official validator/CI/HIL result is claimed here.

### Cross-team review questions before APPROVED

1. Gateway/Node: can we report an actual `activated_at_superframe_seq` with reliable epoch, and preserve IDs/buffer across reset?
2. Backend: can it enforce dedup payload conflict detection, actual activation correlation and out-of-order ACK handling?
3. Infrastructure/Security: authenticate principal↔topic binding; test SUBACK downgrade, retained handling, LWT/session expiry and broker queue durability?
4. All: confirm application error-code names, action-specific params/permissions and RF version mapping with #12; revise draft schemas before freezing v1.

## 7. Session key install extension — Owner-approved architecture, draft codec

**New MQTT interfaces:** `downlink/session-key-install` and `uplink/session-key-ack`, QoS1/Retain=false, under existing `iot/v1/gw/{gateway_id}`. Full versioned schema, canonical AAD/ACK byte encoding, state transitions and inter-field checks: [session-key-security.md](session-key-security.md#5-cross-field-and-environment-rules-must-enforce-outside-json-schema), particularly **SK-01…SK-15**. Reconciled with Event-Only architecture and V2 Join Protocol (#125, #126, #127, #128, #136, #154).

Specific invariants:
1. **Identity & Channel:** Trusted MQTT string Gateway principal must map to RF uint8 `target_gw_id` via Backend-authenticated mapping. Each Gateway holds an exclusive VN920 channel (CH00–CH10, 920.250–922.750 MHz) registered persistently in PostgreSQL (Issue #154).
2. **Handshake Confirmation Trigger & V1/V2 Boundaries:** Key installation is triggered only after authentic Node key confirmation (`UP_JOIN_CONFIRM:19B` in V1, or `UP_JOIN_KEY_CONFIRM:31B` / `DOWN_JOIN_FINISH:31B` in V2 #127/#136). Gateway receives only `K_SESSION_UP[32] || K_SESSION_DL[32]` wrapped by `K_GW_WRAP`; never `K_JOIN` or `K_JOIN_CONFIRM`. The 64B Backend-issued envelope is an Owner-approved V1 design; in V2, ephemeral ECDH shared secret $Z$ is known only to Node and Gateway, so V2 session key delivery vs local derivation remains an **`OPEN_DECISION / BLOCKED_BY_#127`**.
3. **Envelope & Nonce:** AES-256-GCM uses independently provisioned per-Gateway 32B wrapping key with nonce uniqueness (`WRAP_KEY_EPOCH:4B || WRAP_SEQUENCE:8B`) across reboot and crash recovery. Retries reuse identical envelope and `install_id`.
4. **Durable Inactive Persistence & Eligibility:** Gateway commits protected inactive key-slot (`INSTALLED_INACTIVE`) in NVS before sending authenticated `INSTALLED` ACK. Application ACK is authenticated using separately derived 32B MAC key (`K_ACK`). Pre-staging before `not_before` is allowed in `INSTALLED_INACTIVE` state, but keys MUST NOT transition to `ACTIVE` or encrypt/decrypt frames before `not_before` or after `expires_at`.
5. **Post-Install Activation & Event-Only Invariant:** Key installation cannot grant TDMA DATA slot or active lease. In V2 flow (#136, #208), Node readiness `UP_JOIN_READY` (0x49, 31B, verified at edge via `K_KC_UP`, not installed data session keys) and Backend TDMA schedule staging occur strictly after key installation. Schedule cutover uses signed `DOWN_SCHED_PREPARE` → 100% verified affected `UP_SCHED_READY` (0x4C) → signed `DOWN_SCHED_DECISION` committing at $K_{\text{TARGET}}$ (countdown 3→2→1 is superseded per Owner Decision #208 / PR #206). Under Event-Only architecture (#125), data slots carry local-alarm-triggered event reports (`Event TX → ACK RX`) and periodic business telemetry is superseded.
6. **Limits:** FormatChecker/JSON Schema alone cannot verify cryptographic authenticity, NVS persistence, broker ACLs, or RF timing.

Review: Gateway / Backend Go / Infra-Security / CODEOWNERS. G2 security audit, Golden Vectors, MQTT broker/G4 integration, Flash fault injection and RF/HIL remain **NOT_VERIFIED**.

## 8. Kế hoạch chuyển đổi, hủy bỏ (Deprecation Policy) & Ranh giới V2 (Issue #128)

1. **Hủy bỏ chế độ định kỳ (Zero Periodic Telemetry):**
   - Topic `iot/v1/gw/{gateway_id}/uplink/telemetry` và schema `telemetry.schema.json` được đánh dấu `DEPRECATED_HISTORICAL`. Active V2 nodes và firmware mới tuyệt đối **không phát dữ liệu lên topic này**. Backend Go duy trì topic và schema `1.0-draft` cho mục đích đọc và giải mã log lịch sử.
   - Hành động `SET_PERIODIC_MODE` trong `command.schema.json` bị bãi bỏ (`DEPRECATED_UNSUPPORTED`). Khi nhận lệnh này, Node/Gateway phản hồi `command-ack` với `status=REJECTED`, `reason_code=UNSUPPORTED_ACTION`.
   - `SET_SAMPLE_PERIOD` trong `command.schema.json`: chỉ quy định chu kỳ đọc cảm biến ADC cục bộ tại Node để đánh giá vượt ngưỡng. Đây là tham số lấy mẫu phần cứng nội bộ, **hoàn toàn không phải tần suất phát sóng vô tuyến RF định kỳ**.
2. **Phân định hai chỉ số giám sát bảo trì V2:**
   - `PENDING_COUNT` trong `UP_HEALTH_REPLY` (0x44, 21B, trường `pending_event_count` trong status schema): là **độ sâu hàng đợi FIFO tức thời** tại thời điểm phản hồi bảo trì.
   - `DROPPED_EVENT_COUNT` trong `UP_DIAG_METRICS` (0x4A, 23B, trường `dropped_event_count` trong status schema): là **bộ đếm tích lũy số sự kiện bị hủy** do tràn hàng đợi ring-buffer qua các chu kỳ.
   - Hai chỉ số này đo lường hai hiện tượng hoàn toàn khác nhau; cấm gộp trường hoặc đánh đồng `PENDING_COUNT` thành số sự kiện bị mất.
3. **Phân định bốn tầng xác nhận (Four-Layer Confirmation Model):**
   - **RF ACK (`DOWN_EVENT_ACK 0x42`, 19B):** Gateway xác nhận ngay cùng khe sau khi đã commit bền vững sự kiện vào WAL cục bộ.
   - **MQTT Transport PUBACK:** Mosquitto xác nhận hop truyền mạng QoS 1; không chứng minh Backend đã ghi nhận CSDL.
   - **Backend DB Commit:** Backend Go khử trùng lặp qua `UNIQUE(gateway_id, event_id)` và lưu trữ bền vững vào PostgreSQL.
   - **UI Acknowledgement:** Người vận hành gọi `POST /api/v1/alerts/{id}/acknowledge` làm thay đổi trạng thái xử lý người dùng; không phát sinh bất kỳ bản tin RF ACK nào.
4. **Đăng ký kênh độc quyền VN920_V1 (#154):**
   - Backend Go quản lý cấp phát độc quyền một trong các kênh CH00–CH10 (920.250–922.750 MHz) qua REST API (`POST /api/v1/gateways/{id}/channels/request`) có hỗ trợ `X-Idempotency-Key`.
   - Phân định rõ thứ bậc trạng thái: `CHANNEL_ALLOCATED` $\to$ `SCHEDULE_STAGED` $\to$ `SCHEDULE_ACTIVE` $\to$ `RF_AUTHORIZED`.
   - Việc được cấp kênh không tự động cho phép Gateway phát sóng RF nếu thiếu lịch ACTIVE hợp lệ, đồng hồ tin cậy và kiểm soát duty-cycle. Thu hồi kênh bị từ chối nếu lịch đang ở trạng thái ACTIVE (trừ khi dùng force deactivation).

## 9. V2 Join Hello Relay Envelope & Ingest Invariants (#221)

Interface: `iot/v1/gw/{gateway_id}/uplink/join-hello`, QoS 1, `Retain=false`, schema `join-hello.schema.json`.

Các bất biến nghiệp vụ bắt buộc:
1. **JH-01 (Scope & Zero-Knowledge):** Gateway chỉ đóng vai trò chuyển tiếp vô tuyến (RF relay) cho bản tin `UP_JOIN_HELLO` (0x45, 68B). Gateway tuyệt đối không lưu, không phái sinh và không được gửi kèm khóa gốc $K_{\text{JOIN}}$ hay khóa yêu cầu $K_{\text{JREQ}}$.
2. **JH-02 (Identity & Topic Binding):** Broker MQTT bắt buộc xác thực danh tính Gateway qua mTLS client certificate / username. `gateway_id` trong topic và trường `gateway_id` trong payload phải trùng khớp với danh tính được broker xác thực. Backend độc lập đối chiếu `gateway_id` sang mã số `target_gw_id` (0x01..0xFE) và từ chối gói tin nếu có sự sai lệch với byte 7 (`TARGET_GW_ID`) của khung tin RF.
3. **JH-03 (Frame Wire Invariants):** `raw_frame_hex` phải là chuỗi đúng 136 ký tự hex (tương ứng 68 byte). Byte 0 phải là `0x45` (`VER_TYPE`), `TARGET_GW_ID` $\in [0x01, 0xFE]$, `JOIN_COUNTER` $\notin \{0, 0xFFFFFFFF\}$, `DEVICE_MAC` và `NODE_X25519_PUB` khác $0^{all}$ (RFC 7748 §6.1).
4. **JH-04 (HMAC Authentication):** Backend giải mã hex, tra cứu thông tin thiết bị đang hoạt động (`ACTIVE`) và thế hệ hiện tại (`generation`), phái sinh $K_{\text{JREQ}}$ qua HKDF-Extract/Expand từ $K_{\text{JOIN}}$, và xác thực thẻ `JOIN_PROOF` (16B) bằng so sánh thời gian hằng số (`subtle.ConstantTimeCompare`).
5. **JH-05 (Anti-Replay & Idempotency):**
   - Bộ đếm `JOIN_COUNTER` phải tăng đơn điệu đối với mỗi cặp `(network_id, device_mac, generation)`.
   - Nếu `JOIN_COUNTER > last_join_counter`: ghi nhận giao dịch mới ở trạng thái `HELLO_AUTHENTICATED_PENDING_GRANT`, nâng `last_join_counter`.
   - Nếu `JOIN_COUNTER <= last_join_counter`: kiểm tra `raw_hello_sha256`. Nếu khớp hoàn toàn từng byte (byte-identical retransmission), Backend trả về kết quả idempotent của giao dịch trước đó. Nếu khác hash, Backend fail-closed và cảnh báo phát hiện tấn công phát lại (Replay Detected).
6. **JH-06 (QoS 1 Dedup):** Khử trùng lặp tầng mạng thông qua `(gateway_id, event_id)` với `event_id` theo định dạng `<gateway_id>:<gateway_epoch>:<event_seq>`.
7. **JH-07 (Timing & Metadata):** `radio_rx_monotonic_us` ghi nhận thời gian nhận tương đối tại Gateway trong `gateway_epoch`. `observed_at` chỉ ghi nhận khi có nguồn thời gian UTC tin cậy, nếu `observed_time_source=unknown` thì bắt buộc `observed_at=null`.
8. **JH-08 (No Data Grant):** Việc xác thực thành công `UP_JOIN_HELLO` chỉ đưa trạng thái giao dịch vào `HELLO_AUTHENTICATED_PENDING_GRANT`. Tuyệt đối không tự động cấp phát khe TDMA DATA hay kích hoạt quyền phát sóng cho Node tại bước này.
