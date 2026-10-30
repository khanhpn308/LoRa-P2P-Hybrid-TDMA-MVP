# MQTT v1 — Semantic invariants & schema review (Issue #14 / Step A)

**Status:** `DRAFT / PENDING Gateway + Go Backend + Infrastructure/Security approval`. **MQTT version:** 5.0 Owner-accepted via ADR-0002. **Implementation, contract tests and RF/HIL:** `NOT_VERIFIED`. This file complements [topics.md](topics.md) and seven [schemas](schemas/); it is **not** permission to change Radio MAC. BM03 (learning document supplied for review), OASIS MQTT 5.0 and the existing repository contracts informed this specification.

## 1. Ownership and validation layers

| Check | Owner / gate | JSON Schema alone? |
|---|---|---|
| JSON UTF-8, required fields, types, enums, date-time with UTC `Z`, UUID format, conditional ACK fields | Gateway producer + Go consumer (draft) | YES with Draft 2020-12 and **enabled FormatChecker** |
| Topic ↔ authenticated principal ↔ payload `gateway_id` match | Mosquitto ACL + Backend/Gateway application check | NO |
| QoS 1, `Retain`, Message Expiry, SUBACK Granted QoS, Clean Start, Session Expiry, TLS cert/ACL | MQTT 5 transport and broker configuration | NO |
| Gateway-created durable Event ID vs RF frame identity; DB uniqueness; timestamp plausibility | Backend ingestion | NO |
| Schedule monotonic version, dedup request, expiry with trusted clock, collision, airtime, staged→active | Gateway executor + Backend planner | NO |
| Command action-specific parameters, authorization, command expiry, radio ACK and actuator safety | Backend + Gateway + Node | NO |

**Normative status:** all `MUST` statements below are *proposed* contract rules until required human sign-offs. JSON Schema PASS proves neither authorization nor schedule safety nor MQTT delivery.

## 2. Identity, durable receipt và telemetry payload

1. **Owner revision G06:** Gateway cấp **Event ID duy nhất tại lần persist đầu tiên** cho một uplink hợp lệ; Node **không** đưa Event ID vào RF frame. Gateway lưu bền `(gateway_id,node_id,security_session,frame_counter) → (event_id,payload)`, không gán ID mới cho cùng frame qua RF retry, mất ACK, reboot hoặc MQTT QoS1 replay. `event_id` của Telemetry/Alert dùng Gateway-origin identity; `gateway_epoch/event_seq` là các thành phần của ID gốc, phải bảo toàn khi phát lại, không chỉ là RX metadata mới.
2. **Backend:** dedup theo `(gateway_id,event_id)`, đối chiếu authenticated `node_id` và payload; conflicting duplicate phải quarantine. RF replay counter/identity và MQTT redelivery có lớp dedup khác nhau. Không suy từ MQTT PUBACK ra đã commit DB.
3. **Temperature only:** Telemetry `data = {"temp_x10": <signed int16>}`, giá trị nhiệt độ Celsius ×10 (35,5°C→355). RF không chứa ch1/ch2/ch3/battery/node_duty/slot metadata. `frame_counter` là counter RF metadata (uint32 DRAFT), không phải business Event ID; Alert RF wire/ACK chưa khóa. `trigger` của MQTT Alert tùy chọn và chỉ được tạo nếu có cấu hình ngưỡng đủ nguồn.
4. `observed_at` dùng RFC3339 UTC `Z` hoặc null; `observed_time_source` chỉ nguồn thời gian. `unknown` buộc `observed_at=null`; `radio_rx_monotonic_us` nằm trong clock domain Gateway. Không tự lấy ingest time thay thời gian sự kiện.
5. **Bảo vệ lỗi:** mất persisted event mapping/counter continuity → fail closed hoặc reconcile; không cấp Event ID thứ hai cho frame cũ. Gateway enqueue event bền vững trước khi Beacon đặt bit ACK =1. MQTT schema không tự xác nhận toàn vẹn RF, security session hay nguồn dữ liệu.

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

Gateway validates authenticated Gateway/topic/version/expiry, **Owner-approved activation_window**, full schedule non-overlap/airtime and trusted clock; persists Shadow before `STAGE_ACK`. **Owner countdown: exactly three complete announce Superframes 3→2→1 before cutover**, with start at a Superframe boundary; never treat countdown as proof of Node ACK. **Affected Node prepare ACK + old Slot Lease safely expired/terminated** are prerequisites for cutover at the Superframe boundary inside window; announcements alone do not establish readiness. Gateway never rewrites Slot Assignment/channel. `ACTIVE_REPORT` follows actual activation; planned versus actual boundaries are distinguished.

A delayed, buffered `ACTIVE_REPORT` after Backend marked EXPIRED must be reconciled against Gateway current status and trustworthy reported activation epoch/sequence **before** any transition; no blind state flip. `expires_at` is the deadline for accepting/activating this proposal, **not** an unapproved periodic schedule lease (separate design needed for lease revocation). Boot/reconnect and active/shadow NVS recovery require idempotent reconciliation; a shadow proposal is never silently activated on reboot. If UTC is untrusted at acceptance, fail closed. A schedule may continue locally while backhaul is absent only under the separate active-schedule safety requirements.

Schedule `P-10S-15`, `superframe_ms=10000`, 400 ms slots and radio version mapping are **candidate values only**; **three announcement Superframes are an Owner decision, not an RF timing measurement**; no RF timing/airtime/G1/G2/G3 PASS is implied. Radio `SCHED_VER` wrap/truncation remains BLOCKED at #12/D11. JSON Schema cannot check overlap or half-duplex; the Gateway must do those checks.

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

`SET_PERIODIC_MODE(false)` disables periodic telemetry but keeps Alert. `SUSPEND_NODE`, `RESUME_NODE`, `REVOKE_NODE` require authenticated Backend RBAC, Gateway durable enforcement and local authorization validity; no automatic offline renewal. Reprovision/credential reset is a separate security-approved procedure OPEN G2. `command.params` keys are only syntactically constrained; action-specific semantic safety must be reviewed (physical actuator control is not approved under this command allowlist).

## 6. Review matrix for seven schemas (no test verdict asserted)

| File | Schema-layer checks | Semantic/integration rules outside schema |
|---|---|---|
| [telemetry](schemas/telemetry.schema.json) | Gateway Event ID, candidate 32-bit frame counter, temp_x10 int16, UTC conditional | Persistent mapping/dedup, measurement scale and DB commit |
| [alert](schemas/alert.schema.json) | Gateway Event ID, temperature-only data, severity, optional sourced trigger | No fabricated threshold/trigger, Alert RF/ACK still OPEN |
| [status](schemas/status.schema.json) | Mode/ranges + optional active/staged references | Retained snapshot not online; reconciliation/LWT |
| [schedule](schemas/schedule.schema.json) | UUIDs, deadlines RFC3339 UTC, candidate slot shape | expiry ordering, unique non-overlap, timing/airtime, version/epoch |
| [schedule-ack](schemas/schedule-ack.schema.json) | Stage/code conditional; actual activation field only required for ACTIVE_REPORT | Backend state transitions, reordered reports, actual activation verification |
| [command](schemas/command.schema.json) | Proposed action enum, params type/key shape, deadlines | per-action parameter allowlist, expiry/authorization/airtime |
| [command-ack](schemas/command-ack.schema.json) | Enumerated error codes and status-dependent constraints | Node acknowledgment evidence, duplicate command responses |

**Original examples** in [examples/cases.json](examples/cases.json): `T-VALID/T-MISSING-ID/T-FRAME-COUNTER-OVERFLOW`, `ALERT-VALID/ALERT-SEVERITY-INVALID`, `SCHEDULE-VALID/SCHEDULE-DURATION-INVALID/SCHEDULE-DUPLICATE-SLOT`, `SCHEDULE-ACK-VALID/SCHEDULE-ACK-INVALID-NACK-REASON`, `STATUS-VALID`, `COMMAND-VALID`, `COMMAND-ACK-VALID`. Additional schema-shape examples added here cover ACTIVE_REPORT/ACK invariants, enum errors, unknown-time, UTC, invalid command key and malformed event ID. Runtime behavior/replay/authorization tests and actual reports belong to **Step B**, `tests/contract/`. No official validator/CI/HIL result is claimed here.

### Cross-team review questions before APPROVED

1. Gateway/Node: can we report an actual `activated_at_superframe_seq` with reliable epoch, and preserve IDs/buffer across reset?
2. Backend: can it enforce dedup payload conflict detection, actual activation correlation and out-of-order ACK handling?
3. Infrastructure/Security: authenticate principal↔topic binding; test SUBACK downgrade, retained handling, LWT/session expiry and broker queue durability?
4. All: confirm application error-code names, action-specific params/permissions and RF version mapping with #12; revise draft schemas before freezing v1.
