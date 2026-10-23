# GO BACKEND ENGINEERING STANDARD v1.0

**Document ID:** BE-STD-001  
**Version:** 1.0.0  
**Status:** **DRAFT — PENDING HUMAN TECHNICAL REVIEW**  
**Prepared:** 2026-10-23  
**Repository:** `khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP`  
**Target Path:** docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V1.0.md  
**Scope:** `backend-go/**`; interfaces với `contracts/mqtt/**`, `contracts/api/**`, `contracts/radio-mac/**` và migrations; AI agents + human reviewers.  
**Baseline trên nhánh chuẩn hóa Issue #39 (DRAFT, chưa merge):** `backend-go/go.mod` khai báo **Go 1.27.3**, `.go-version` khóa `1.27.3`, CI phải xác minh đúng `go1.27.3` với `GOTOOLCHAIN=local`; `backend-go/README.md` và `cmd/server/main.go` là **scaffold only**, chưa có service production hoạt động. **Pre-approved Stack của standard v1.0 (định hướng mặc định, chưa đồng nghĩa đã khai báo trong `go.mod` hoặc được phê duyệt ở cấp repository):**
- **HTTP Routing:** `net/http` — `http.ServeMux` của stdlib Go 1.27.3. MUST NOT tự thêm Gin, Echo, Fiber hoặc router bên thứ ba.
- **PostgreSQL:** `github.com/jackc/pgx/v5` — ưu tiên `pgxpool`; MAY dùng adapter `stdlib` qua `database/sql` nếu có lý do cụ thể. Không sử dụng song song hai cách truy cập DB chỉ vì sở thích.
- **MQTT 5.0:** `github.com/eclipse/paho.golang/autopaho` + `github.com/eclipse/paho.golang/paho` (cùng Go module); MUST NOT dùng `github.com/eclipse/paho.mqtt.golang` (client MQTT 3.1.1) cho contract v1.
- **Khóa Go 1.27.3:** Toolchain được chốt chính xác tại `backend-go/go.mod`, `.go-version` và CI, không dùng `@latest` hoặc `1.27.x` để tự đổi phiên bản. Các thư viện trên là **pre-approved package names**, chưa phê duyệt phiên bản module cụ thể vì backend vẫn là scaffold. Khi cần cài, MUST chọn phiên bản module cố định có `go.mod` tương thích Go 1.27.3, kiểm tra transitive dependencies/security/license/API rồi chạy build/test thực tế; không tự nâng Go toolchain hoặc thêm dependency ngoài phạm vi Issue. Trạng thái khả năng tương thích runtime: **NOT_VERIFIED**.

> **Tuyên ngôn:** Viết lượng code **ít nhất đủ để giải quyết yêu cầu một cách đúng đắn, an toàn, dễ đọc, dễ kiểm thử và dễ debug**. Không tối ưu số dòng bằng cách giấu hành vi, mất error context hoặc bỏ failure handling.

## 0. Cách áp dụng, mức độ bắt buộc và thứ tự thẩm quyền

- **MUST / MUST NOT**: yêu cầu bắt buộc; vi phạm là blocker của PR trừ khi có ngoại lệ được owner phê duyệt.
- **SHOULD / SHOULD NOT**: mặc định áp dụng; ngoại lệ cần giải thích trong PR.
- **MAY**: tùy chọn, chỉ dùng khi chứng minh được ích lợi.
- **NOT_VERIFIED**: chưa có bằng chứng triển khai, build, chạy, test hoặc đo; tuyệt đối không tự chuyển thành PASS.
- Các chính sách dưới đây là **đề xuất v1.0**, chưa phải rulesets đang được GitHub enforce.

**Thứ tự xử lý xung đột:** (1) yêu cầu bảo mật và an toàn; (2) approved requirements/ADR và contracts đang áp dụng; (3) implementation/database migrations thực tế khi cần xác định hành vi hiện trạng; (4) tài liệu chuẩn nội bộ này; (5) Google Go Style Guide; (6) Uber Go Style Guide và Go Team guidance. Nếu status nguồn chưa được Approved, phải công khai trạng thái và yêu cầu cross-team review trước thay đổi ảnh hưởng interface.

**Ranh giới kiến trúc không được phá:** Go = **Modular Monolith** để hoạch định lịch TDMA trong tương lai, nhận telemetry và cung cấp API; Gateway ESP32 = **TDMA Executor** thời gian thực. MQTT 5.0 là quyết định `OWNER_ACCEPTED` trong ADR-0002 nhưng phần contract vẫn `PENDING CROSS-TEAM REVIEW`; đây không phải bằng chứng đã chạy integration. **Không** tự thêm LoRaWAN/ChirpStack/OTAA/ADR, Redis, InfluxDB, Kafka, Microservices, ORM hoặc message bus thứ hai. Không mặc định các thông số timing/RF chưa đo là fact.

## 1. Các nguyên tắc ưu tiên — rules GB-001..010

**GB-001 — Correctness > Safety > Reliability > Maintainability > Performance.** Code ngắn hơn nhưng dễ sai, mất dữ liệu, hoặc không truy vết được **không** được ưu tiên.

**GB-002 — YAGNI:** Chỉ triển khai acceptance criteria của Issue, invariant bắt buộc và failure paths cần thiết. Không xây dự phòng *future scalability* giả định.

**GB-003 — KISS:** Một bài toán có thể giải bằng logic thuần Go, một đường xử lý rõ ràng thì không dựng framework, plugin registry, event bus, factory chain hoặc nhiều adapter không cần thiết.

**GB-004 — Explicit > clever:** Ưu tiên tuần tự rõ ràng, tên có nghĩa, trạng thái hữu hạn, return sớm. Tránh reflection, generic helper, magic hook, middleware chain dài khi không có nhu cầu cụ thể.

**GB-005 — DRY hợp lý:** Tránh sao chép *business invariant*, codec contract hoặc SQL quan trọng; lặp vài dòng khai báo đơn giản chấp nhận được nếu abstraction làm khó đọc hơn.

**GB-006 — Không tạo abstraction để “sẽ có ngày dùng”.** Chỉ tách interface/package khi có boundary thực tế, nhu cầu test hoặc nhiều implementation thật; interface thường nằm ở consumer và đủ nhỏ, không tạo interface một-một cho mọi struct.

**GB-007 — Dependency tối thiểu / Pre-approved Stack:** MUST dùng `net/http` (`http.ServeMux`, Go 1.27.3) cho HTTP; `github.com/jackc/pgx/v5` (`pgxpool` mặc định, hoặc adapter `database/sql` khi có lý do) cho PostgreSQL; `github.com/eclipse/paho.golang/autopaho` + `paho` cho MQTT **5.0**. MUST NOT tự thêm Gin/Echo/Fiber, ORM hoặc `github.com/eclipse/paho.mqtt.golang` (MQTT 3.1.1). Đây là **allowlist thiết kế của standard DRAFT**, không phải bằng chứng repo đã phê duyệt/khai báo dependency. Ưu tiên stdlib ngoài các integration boundaries này. Phải pin các dependency ở phiên bản cụ thể tương thích với Go 1.27.3 (không mặc định `@latest`), kiểm tra transitive dependencies/security/license/API và xin duyệt thay đổi `go.mod` trong Issue scope. Dependency ngoài allowlist cần đánh giá stdlib, tính bảo trì, rủi ro và owner approval; không tự nâng Go toolchain hàng loạt.

**GB-008 — One responsibility, cohesive packages:** Tên package theo domain; hạn chế `util`, `common`, `helpers`, `manager`, `base`, `core` không rõ nghĩa.

**GB-009 — No silent fallback:** Không `return nil` khi lỗi, không ngầm bỏ bản tin, không cập nhật trạng thái thành công vì lệnh publish đã được broker nhận. Fallback phải được thiết kế, log/metric và test rõ ràng.

**GB-010 — Optimize verified bottlenecks only:** Benchmark/profiling trước khi pooling, batching, cache, custom allocator hoặc tối ưu có thể làm phức tạp code.

**Bài kiểm tra xoá code trước PR:** Mọi abstraction, dependency, goroutine, configuration knob, retry, branch hoặc wrapper mới phải trả lời được: “Nếu bỏ nó, acceptance criteria hoặc một invariant sẽ hỏng ở đâu?” Không có câu trả lời xác thực ⇒ cân nhắc xóa.

## 2. Source layout và module boundaries — rules AR-001..008

**AR-001.** Dùng module hiện có `backend-go/`, không tạo thêm `go.mod` hoặc multi-module workspace nếu không được duyệt.

**AR-002.** Giữ entrypoint ở `backend-go/cmd/server/`; entrypoint chỉ **load/validate config → construct dependencies → start services → wait signal → shutdown**, không chứa business logic.

**AR-003.** Đặt internal domain theo feature và quy hoạch sẵn, bổ sung **khi Issue cần**, không tạo package rỗng chỉ để đủ sơ đồ:

```text
backend-go/
  cmd/server/                  # Composition root, process lifecycle
  internal/
    scheduler/                 # Pure future schedule calculation + validation
    telemetry/                 # Ingest domain rules, event interpretation
    alert/                     # Alert transitions and business rules
    mqtt/                      # MQTT 5 transport adapter + parsing/ack
    api/                       # HTTP/WSS adapters + validation/RBAC
    storage/                   # PostgreSQL queries, transactions, migrations access
    domain/                    # Only truly cross-module domain types, if needed
  migrations/                  # Versioned SQL change set
  go.mod
```

**AR-004.** Dependency direction: adapters (`api`, `mqtt`, `storage`) phụ thuộc domain/service contracts khi có; domain **không** import HTTP handler, MQTT library hoặc SQL driver. Các domain giao tiếp bằng exported operations tối thiểu, không cần dựng nhiều layer *handler → service → usecase → manager → repository* nếu chỉ pass-through.

**AR-005.** Không import code firmware C để trao đổi; dùng contracts versioned. Không cho web/mobile truy cập trực tiếp DB hoặc MQTT.

**AR-006.** Một use case chỉ có **một nơi sở hữu invariant**: schedule transition thuộc scheduler, idempotency ingestion ở boundary dữ liệu + unique constraint DB, RBAC ở API/service authorization boundary.

**AR-007.** SQL và persistence chi tiết chỉ xuất hiện ở storage hoặc module được phê duyệt; không truy vấn DB trong request validation lặp lại vô ích.

**AR-008.** Không tạo generic `Repository[T]`, base controller, service locator hoặc singleton mutable toàn cục để làm “clean architecture”.

## 3. Idiomatic Go — rules GO-001..014

**GO-001.** MUST `gofmt`, import group hợp lý; CI kiểm tra thay vì tranh luận format. Dùng `MixedCaps/mixedCaps`; acronym theo quy ước nhất quán (`ID`, `URL`, `HTTP`, `MQTT`).

**GO-002.** Tên phải biểu đạt domain: `ScheduleVersion`, `EventID`, `ActivateAt`; tránh `data`, `obj`, `res`, `temp` ngoài scope rất ngắn.

**GO-003.** Giữ scope biến hẹp; dùng guard clauses/early return để tránh nested `if` sâu.

**GO-004.** Không viết wrapper/no-op chỉ để che 1 dòng code. Hàm nên làm một công việc đọc được; không áp hard limit số dòng nếu việc tách làm mất mạch xử lý.

**GO-005.** Comments giải thích **why/invariant/security/contract**, không tường thuật cú pháp. Exported identifiers nên có GoDoc khi public API thực sự cần.

**GO-006.** Dùng struct typed cho contract; JSON tags tường minh. Phân biệt DTO với DB row và domain value khi khác ngữ nghĩa; không biến mọi dữ liệu thành `map[string]any`.

**GO-007.** Không dùng `panic` cho input, network hoặc DB error bình thường; chỉ `panic` cho programmer invariant cực kỳ bất thường nếu phù hợp, để entrypoint kiểm soát process exit.

**GO-008.** Error trả về kiểu `error`, `fmt.Errorf("<operation>: %w", err)` khi có context hữu ích; `errors.Is/As` cho phân nhánh. Không wrap cùng một thông tin tại 3-4 tầng.

**GO-009.** **Handle error once:** nơi phát hiện xử lý/return; log *một lần tại boundary chịu trách nhiệm* (HTTP/MQTT worker/process) thay vì log ở mọi layer.

**GO-010.** Không `_ = fn()` cho I/O hoặc cleanup có hậu quả; nếu bỏ qua lỗi an toàn được thì comment rõ lý do/đưa vào test.

**GO-011.** `context.Context` là tham số đầu tiên của hàm có I/O hoặc cancellation; không lưu context trong struct, không tạo context mới làm mất deadline/trace; `defer cancel()` khi tạo timeout.

**GO-012.** Tránh magic numbers trong invariant; đặt tên và đơn vị (`time.Duration`, bytes, microseconds). Chưa được chốt hoặc đo → configuration/validation/`NOT_VERIFIED`, không hardcode SLA.

**GO-013.** Dùng UTC cho event/DB timestamps; lưu `time.Time`/UTC theo schema thực tế, có trường `time_source` khi contract yêu cầu; không coi monotonic boot-clock là wall-clock.

**GO-014.** Target code dùng đúng **Go 1.27.3**: `backend-go/go.mod` (`go 1.27.3`), `.go-version` (`1.27.3`) và CI phải khớp. Không tự ý nâng toolchain hoặc sử dụng API chỉ có ở bản Go mới hơn nếu không có Issue phê duyệt.

### Ví dụ canonical: validate → xử lý → trả error có ngữ cảnh

```go
func (s *Service) Ingest(ctx context.Context, event Event) error {
    if event.ID == "" || event.GatewayID == "" {
        return ErrInvalidEvent
    }

    if err := s.store.InsertEvent(ctx, event); err != nil {
        return fmt.Errorf("insert event %s: %w", event.ID, err)
    }
    return nil
}
```

Ví dụ chỉ minh hoạ style, **không** thay thế validation/idempotency/transaction đã được contract quy định; `Service`, `Event` và `ErrInvalidEvent` là loại giả lập, không khẳng định đã tồn tại.

## 4. API, contracts và data validation — rules CT-001..009

**CT-001.** `contracts/api/openapi.yaml` là interface proposal được versioned; không tự thay endpoint, field, status, auth model hoặc serialization khi chưa có Issue + consumer review.

**CT-002.** `contracts/mqtt/topics.md` và `schemas/` kiểm soát topic, QoS, Retain, expiry, event ID, message semantics. Mọi thay đổi backward-incompatible phải có migration/compatibility plan và contract tests.

**CT-003.** Validate input **at trust boundary**: HTTP body/query/path, MQTT topic/payload, DB external data. Không validate y nguyên lần nữa qua mọi layer, nhưng domain MUST enforce invariant khi được gọi từ nhiều entrypoints.

**CT-004.** Giới hạn kích thước body/message, array, string, pagination, time range, ID và worker queue. Reject unknown/invalid values theo schema đang áp dụng; không suy diễn field thiếu từ RF packet.

**CT-005.** Lỗi HTTP trả status/domain error nhất quán theo contract; client nhận thông báo an toàn, server log giữ error cause; không trả SQL query, stacktrace, credentials hoặc internal path.

**CT-006.** API admin/operator/viewer phải kiểm RBAC **server-side** trước data mutation hoặc sensitive read; UI visibility không phải authorization.

**CT-007.** HTTP server đặt read/header/body và idle timeouts theo cấu hình được review; outbound HTTP dùng context + timeout; WSS connection/read/write/heartbeat policy có giới hạn và test.

**CT-008.** Health có ý nghĩa phân biệt: liveness (`process alive`) ≠ readiness (`dependencies ready`) ≠ hệ thống RF healthy. Không hứa Gateway online qua DB last-known state.

**CT-009.** Mutation command/schedule có request ID; request IDs và state transitions phải truy vết từ HTTP → DB → MQTT → Gateway ACK/report, không suy diễn *published = executed*.

## 5. MQTT 5.0, idempotency và state transitions — rules MQ-001..012

**MQ-001.** Tuân theo `docs/adr/0002-mqtt-5.md`: Gateway ↔ Backend **MQTT 5.0**, TLS/client identity/ACL; không tự fallback MQTT 3.1.1 ngoài contract v1.

**MQ-002.** QoS 1 = **at least once**, xử lý duplicate và out-of-order. `event_id` ổn định qua retry/replay, cùng `gateway_id`; unique key `(gateway_id, event_id)` ở PostgreSQL. `event_seq` không được ép về `uint8` hoặc float64 không an toàn.

**MQ-003.** Parse topic và validate JSON envelope/schema/version trước domain writes; malformed payload phải được xử lý có kiểm soát, không crash hoặc loop vô hạn. **Phân loại lỗi trước ACK**:
- **Transient** (DB/network I/O, timeout có thể hồi phục): chỉ retry idempotent, **bounded backoff + jitter** theo MQ-005. Chỉ PUBACK sau khi có kết quả xử lý bền vững (commit thành công / duplicate đã xác nhận). Khi vượt budget, MUST báo metric/log và chuyển sang cơ chế recovery có kiểm soát (ví dụ: ngừng nhận, reconnect với session/persistence đã kiểm chứng hoặc durable retry/quarantine được phê duyệt); MUST NOT báo xử lý thành công, tight-redelivery loop hay âm thầm mất alert. MQTT QoS 1 một mình không bảo đảm vô hạn thời gian lưu trữ.
- **Permanent poison** (malformed JSON, schema invalid, unsupported version; cả lỗi dữ liệu chắc chắn không retry được): MUST structured log `error_kind` + stable message identifiers nếu an toàn, **không log raw secret/payload**; tăng `invalid/dropped` metrics theo MQ-004/OB-009; MUST hoàn tất xử lý bằng **PUBACK** cho QoS 1 để tránh kẹt message và redelivery vô hạn. Chỉ ACK sau khi đã ghi nhận kết quả drop/quarantine theo failure policy đã duyệt; lỗi security-sensitive cần audit/alert phù hợp, không biến drop thành ingestion success.
- **Paho v5 ACK semantics:** `paho` có chế độ **automatic ACK sau khi callback trả về** và chế độ `EnableManualAcknowledgment` + `Client.Ack(...)`. Nếu cần hoãn ACK tới sau DB commit/classification, MUST dùng **manual acknowledgment** (kiểm tra API trong phiên bản pin), hoặc xử lý đồng bộ xong trước khi callback return nếu chọn auto ACK. Không đẩy message vào goroutine/queue rồi return để thư viện auto-ACK trước khi xử lý bền vững. Manual ACK phải đảm bảo thứ tự ACK và bounded in-flight; MUST test với Mosquitto thật để xác minh ACK, reconnect, duplicate và poison. Không giả định `return error` từ callback tự phát MQTT NACK.

**MQ-004.** Backpressure: bounded worker count, bounded queue, bounded message sizes. Nêu rõ chọn block/reject/drop và đo số message mất; **không silently drop alert**.

**MQ-005.** Bounded retry với jitter/backoff ở **I/O boundary**, chỉ retry transient và operation idempotent; không retry business validation hay unauthorized. Shutdown phải dừng retry được.

**MQ-006.** MQTT PUBLISH `downlink/schedule`/`downlink/command`: **Retain=false**, có **Message Expiry Interval** (số giây >0, ≤ thời hạn thực còn lại đến `expires_at`); không publish khi đã hết hạn hoặc còn <1s.

**MQ-007.** Backend MQTT CONNECT: stable client ID, Clean Start=0, Session Expiry>0; phải giới hạn queue/persistence và xác minh broker behavior. Gateway config khác, không áp backend policy lên gateway.

**MQ-008.** Broker PUBACK chỉ chứng minh transport ack; không tương đương Gateway `STAGE_ACK`, `ACTIVE_REPORT` hoặc RF ACK.

**MQ-009.** Schedule lifecycle: `PROPOSED → SENT → STAGED → ACTIVE` hoặc `REJECTED / EXPIRED`. MUST áp dụng **monotonic state progression** cho cùng `(gateway_id, request_id, schedule_version)`: chỉ được đi tới trạng thái tiến hơn, không rollback bởi publish worker/ACK tới trễ. Khi nhận `STAGE_ACK` hợp lệ, được chuyển **`PROPOSED` hoặc `SENT` → `STAGED`**; khi nhận `ACTIVE_REPORT` hợp lệ (khớp identity/version/request ID **và activation evidence theo contract**), được chuyển **`PROPOSED`, `SENT` hoặc `STAGED` → `ACTIVE`**. Đây là xử lý ACK/report đến trước khi publish worker kịp ghi `SENT`; intent/version MUST đã được commit trước publish.
- Dùng conditional `UPDATE`/compare-and-swap hoặc transaction có khóa/điều kiện tương đương, kiểm tra `RowsAffected`, bảo đảm update muộn `SENT` không ghi đè `STAGED/ACTIVE`. Duplicate hợp lệ = idempotent; mismatched/stale evidence bị từ chối và log/metric. `REJECTED`/`EXPIRED` xử lý như terminal theo contract, không tự hồi sinh khi gặp report muộn; nếu Gateway report mâu thuẫn, đưa vào reconciliation/human review, không lặng lẽ đổi trạng thái.
- Invariant **không đổi**: Broker `PUBACK` chỉ là transport ACK (MQ-008); `STAGE_ACK` **không** chứng minh ACTIVE; **chỉ `ACTIVE_REPORT` hợp lệ** mới chứng minh activation và được cập nhật ACTIVE. Không thực hiện network publish trong DB transaction (DB-004).

**MQ-010.** Reconnect phải reconcile last-known/retained status và authoritative persisted state; không auto-send stale schedule/command sau restart. Chấp nhận duplicate ACK/reports an toàn.

**MQ-011.** Timestamp ingress phải phân biệt `observed_at` (có thể null/chất lượng clock khác nhau), `ingested_at` server clock, `radio_rx_monotonic_us` relative boot time. Không bịa thời gian đo.

**MQ-012.** MQTT adapter không quyết định slot activation, RF guard time hay radio hardware behavior. Đó là trách nhiệm Gateway Firmware/contract.

## 6. TDMA Scheduler — rules SC-001..008

**SC-001.** Scheduler là **pure deterministic planning logic** khi có thể: `inputs + constraints → proposed schedule/result`. Clock/time/randomness truyền qua dependency rõ ràng, không ẩn trong logic cốt lõi.

**SC-002.** Tất cả schedule version/slot/frequency/timing boundaries phải theo contract hiện hành; không tự đặt superframe, guard-time, duty limits hoặc alert latency làm thông số đã duyệt.

**SC-003.** Validate completeness, non-overlap, node/gateway identity, version ordering, payload size, expiry và các giới hạn đã được phê duyệt trước publish.

**SC-004.** Fail closed với unsupported version, invalid schedule, stale ACK, activation time không đáng tin hoặc thông tin không đủ.

**SC-005.** Không ghép “scheduler planning” và “MQTT publish” thành một hàm lớn không thể unit-test; để adapter I/O riêng khỏi thuật toán.

**SC-006.** Schedule publish/ack/report transition được lưu bền vững và chỉ đổi trạng thái khi invariant đúng; transaction/conditional update phải giải quyết concurrent updates, kể cả report tới trước update `SENT` (MQ-009).

**SC-007.** Không dùng wall-clock local `time.Now()` rải rác trong thuật toán; dùng `clock` injection **chỉ khi** thực sự cần test controlled time, không dựng framework đồng hồ tổng quát.

**SC-008.** Test bắt buộc cho overlapping slots, exact boundaries, expiry, duplicate reports, unknown node, version mismatch, reboot/reconnect. Timing/RF/HIL chỉ PASS khi có evidence ngoài unit-test.

## 7. PostgreSQL và migrations — rules DB-001..010

**DB-001.** PostgreSQL là data store duy nhất cho MVP. Không tự thêm cache/distributed lock/queue DB khác.

**DB-002.** SQL parameterized; tuyệt đối không build SQL bằng string concat từ user input. Dynamic identifiers phải allowlist.

**DB-003.** Sử dụng DB pool được quản lý lifecycle; cấu hình max connections và timeout theo workload/test, không chọn số “chuẩn” thiếu evidence.

**DB-004.** Transaction ngắn, có rollback khi lỗi, xử lý commit error; tránh network I/O trong transaction khi chưa chứng minh lý do. MUST persist **schedule intent + request/version** trước publish; dùng conditional update/CAS trong PostgreSQL cho trạng thái tiến đơn điệu theo MQ-009, không để publish worker ghi `SENT` đè lên `STAGED/ACTIVE`. Phải có phương án cho publish-vs-DB-commit failure; **không** hứa atomicity giữa DB và MQTT. Outbox chỉ khi Issue yêu cầu reliable delivery và đánh giá tradeoff.

**DB-005.** Dùng unique index/constraint cho idempotency, FK/check constraints khi phù hợp, và xác minh `RowsAffected`/`RETURNING` để phân biệt inserted vs duplicate khi cần.

**DB-006.** Query có context/deadline, pagination và giới hạn kết quả. Không SELECT * cho API ổn định khi field contract cần kiểm soát.

**DB-007.** Migration tăng dần, versioned, reviewable; không sửa lại migration đã áp dụng; schema change cần forward/backward compatibility khi có deploy staggered.

**DB-008.** Không tự thêm ORM nếu SQL đơn giản/đã đủ. Query code dễ đọc và error detail an toàn hơn pattern repository tổng quát.

**DB-009.** Lưu timestamp UTC và consistent numeric units; tránh ép `event_seq` hoặc ID lớn thành float ở JSON/SQL.

**DB-010.** Integration test chạy DB thật cho uniqueness, transactions, migrations, rollback, concurrent inserts và SQL constraints; mock-only không đủ chứng minh SQL behavior.

## 8. Concurrency, runtime lifecycle và reliability — rules RT-001..011

**RT-001.** Concurrency không phải mặc định. Sequential code là lựa chọn đầu tiên khi throughput của MVP đáp ứng. Chỉ thêm goroutines khi có parallelism, I/O isolation hoặc shutdown requirement thật.

**RT-002.** Mỗi goroutine phải có owner, cancellation, error path và `Wait`/`Join` lúc shutdown; không fire-and-forget hoặc goroutine trong `init()`.

**RT-003.** Bound worker pool và queue; không tạo goroutine per MQTT message/request vô hạn. Một hàng đợi lớn không thay thế backpressure policy.

**RT-004.** Mutex giữ vùng critical section nhỏ; không gọi network/DB/blocking I/O dưới lock trừ khi đã review rủi ro deadlock.

**RT-005.** Context cancellation propagate đến SQL, MQTT request/retry, HTTP downstream và background workers khi adapter hỗ trợ. Không dùng `context.Background()` giữa request flow để trốn cancellation.

**RT-006.** Cleanup theo thứ tự rõ: stop accepting → stop ingest/start shutdown → drain bounded in-flight work → flush/close logs/DB/MQTT → exit; có tổng shutdown deadline.

**RT-007.** Startup fail fast khi invalid config, secret thiếu, migration/schema bất tương thích hoặc dependency bắt buộc không sẵn sàng; readiness false thay vì báo healthy giả.

**RT-008.** Retry chỉ ở một tầng có ownership và budget. Không stack nested retries làm nhân số lần thử lên ngoài kiểm soát.

**RT-009.** Timer/ticker phải được stop khi không còn sử dụng. Không dùng `time.Sleep` để chờ tính đúng đắn của event order hoặc trạng thái production.

**RT-010.** Các lỗi bất thường phải lên được tới caller hoặc supervisor, không nuốt lỗi trong goroutine callback.

**RT-011.** Dùng race detector trong CI trên runner hỗ trợ; kiểm tra leak/buffer pressure qua integration/soak khi có background workers.

## 9. Logging, debugging, observability — rules OB-001..012

**OB-001.** Dùng **structured logging**, mặc định cân nhắc `log/slog` stdlib của Go 1.27.3 nếu không có stack đã approved. Không tự đưa logging framework mới chỉ để đổi format.

**OB-002.** Log event tại **system boundary** và các state transition có ý nghĩa, không log từng lần gọi helper hoặc mọi SQL thành công ở INFO.

**OB-003.** Chuẩn field snake_case: `timestamp`, `level`, `component`, `operation`, `request_id`, `gateway_id`, `event_id`, `schedule_version`, `duration_ms`, `error`, `error_kind` tùy event. Trường thiếu thì bỏ, không dựng ID giả.

**OB-004.** Severity policy: DEBUG = context chi tiết opt-in; INFO = lifecycle/state meaningful; WARN = recoverable anomaly; ERROR = operation failed/action required. Không log cùng error ở 5 lớp.

**OB-005.** Khi request/command từ HTTP đi tới MQTT: preserve correlation identifiers; DB record và log có key đủ để truy lại lineage.

**OB-006.** Startup log version/commit/config profile **không chứa secrets**; shutdown log reason và số in-flight còn lại nếu có.

**OB-007.** Không log password, bearer token, TLS private key, full raw telemetry/payload nhạy cảm, secret env, SQL bind sensitive. Debug raw packet chỉ ở môi trường có kiểm soát, masking và sampling.

**OB-008.** Lỗi phải có `operation + stable identifiers + cause + retryability`; không chỉ `something went wrong`.

**OB-009.** Metrics tối thiểu theo các tính năng thực sự tồn tại: ingest success/error/duplicate, MQTT reconnect/queue depth/dropped count, DB latency/errors, schedule transition failures, request error/latency. Không dựng hệ telemetry phức tạp cho scaffold.

**OB-010.** Không ghi metric labels bằng IDs có cardinality vô hạn (event_id, request_id); các IDs này chỉ dùng trong logs/traces.

**OB-011.** Có chiến lược debug repeatable: deterministic fixture → reproduce test → log lineage → inspect DB state → compare contracts → fix root cause → regression test.

**OB-012.** pprof/expvar hay debug endpoints **không** được public exposure mặc định; chỉ enable bằng config rõ, loopback/admin auth và review.

## 10. Security — rules SE-001..009

**SE-001.** TLS ngoài dev-insecure profile localhost được cô lập; verify certificates, client identity và MQTT ACL; không `InsecureSkipVerify` trong production.

**SE-002.** Secrets chỉ đi qua secret management/env/approved runtime injection; không commit, embed trong test fixtures, print config dump hoặc leak ở error logs.

**SE-003.** Authentication, authorization, RBAC phải xác minh ở server; mọi privileged command phải có actor và audit event.

**SE-004.** Input/payload validation trước xử lý; giới hạn size, nesting, number ranges, timestamp bounds; bảo vệ DoS do malformed input.

**SE-005.** Do not assume CRC = cryptographic authentication; hệ thống dùng custom LoRa P2P, không tự khai báo bảo mật LoRaWAN hoặc dùng LoRaWAN key/nonce scheme ngoài approved contract.

**SE-006.** SQL injection prevention, HTTP security headers/CORS policy, WebSocket Origin/auth checks theo deployment threat model và contract.

**SE-007.** Không dùng log để chứa PII/credential. Redact error details client-facing.

**SE-008.** Dependencies kiểm tra vulnerability/license khi thêm hoặc cập nhật. Remediation phải đánh giá reachability, severity và breaking changes.

**SE-009.** Những thay đổi authentication/crypto/control plane có **human technical review**, threat model hoặc security tests phù hợp trước khi merge.

## 11. Testing theo rủi ro — rules TS-001..011

**TS-001.** Không viết test chỉ để tăng coverage; test phải chứng minh **behavior + invariant + failure modes**.

**TS-002.** Unit tests cho pure domain functions, table-driven khi làm rõ các trường hợp; dùng test names mô tả behavior, failure output chứa input/expected/got.

**TS-003.** Boundary tests: missing field, empty string, overflow, negative/zero, max length, invalid type, duplicate, reordered, expired, malformed JSON, unsupported version.

**TS-004.** Contract tests dùng chính `contracts/mqtt` schemas, `contracts/api` OpenAPI và test vectors ở `contracts/radio-mac` khi phù hợp; consumer/producer cùng review.

**TS-005.** Integration tests với PostgreSQL thật và MQTT 5.0 Mosquitto broker/profile thật để chứng minh reconnect, QoS1 replay/expiry, transaction & state transitions. MUST test poison JSON/schema/version ⇒ log + dropped metric + PUBACK, transient DB failure ⇒ bounded retry và **không ACK quá sớm**, và race `STAGE_ACK`/`ACTIVE_REPORT` tới trước `SENT` update ⇒ trạng thái không lùi.

**TS-006.** Simulations dùng để thăm dò thuật toán; không đánh dấu RF timing/HIL compliance `PASS`.

**TS-007.** Không phụ thuộc network/public APIs không kiểm soát trong unit tests. Dùng fake clock/harness ở nơi có timing effects; không random flakiness.

**TS-008.** Khi parsing payload không tin cậy, nên có fuzz tests của decoding/validation nếu giá trị risk phù hợp.

**TS-009.** Concurrency code: test cancellation, shutdown, race, blocked queue, retry budget, goroutine leak.

**TS-010.** Bug fix MUST kèm regression test tái hiện bug trước fix nếu khả thi. Không mock đến mức test chỉ xác minh implementation details.

**TS-011.** Report chính xác `PASS`, `FAIL`, `PARTIAL_WITH_FINDINGS`, `NOT_VERIFIED`, kèm command/environment/commit và giới hạn. Không đánh đồng `go test` với integration hoặc RF/HIL pass.

## 12. Go quality gates và tooling — rules QG-001..008

**QG-001.** Khóa **Go 1.27.3** tại `backend-go/go.mod` và `.go-version`; CI phải chọn chính xác `1.27.3`, đặt `GOTOOLCHAIN=local` và kiểm tra `go env GOVERSION = go1.27.3` trước các quality gates. Pin GolangCI-Lint và govulncheck versions tương thích sau khi đánh giá, **không dùng `@latest` tự động trong CI**.

**QG-002.** Mandatory local baseline (ở `backend-go/` nếu tooling có sẵn):

```bash
gofmt -l .
go vet ./...
go test ./...
go test -race ./...       # runner hỗ trợ race/cgo
golangci-lint run ./...  # nếu đã cài và có config approved
govulncheck ./...        # nếu đã cài
```

**QG-003.** CI fail khi unformatted Go, build/vet/test fail, critical security finding chưa được triage, contract test fail hoặc migration validation fail. **`gofmt -l .` chỉ in tên file sai format và vẫn có thể exit 0; CI MUST assert stdout rỗng**, ngoài việc kiểm tra exit code. Không tự kích hoạt lint rule hàng loạt gây false positives mà chưa chốt baseline.

**QG-004.** `go test ./...` với scaffold chỉ chứng minh package hiện tại test được; không chứng minh MQTT/DB/Scheduler/API hoạt động.

**QG-005.** Mọi test `PASS` cần exact command, runner/tool version và commit SHA; `NOT_RUN`/`NOT_VERIFIED` phải nói rõ.

**QG-006.** Coverage theo critical paths, không áp threshold phần trăm cố định thiếu threat/risk analysis; review test quality.

**QG-007.** CI theo PR + required human review; không mặc định branch protection đang bật. Không AI self-approve/self-merge.

**QG-008.** HIL/RF/latency/reliability pilot evidence vẫn quản lý ở `docs/verification/` và G0–G6; code-only lint/test không chứng minh chúng.

## 13. Quy trình bắt buộc cho mọi AI agent — rules AI-001..012

**AI-001 — Preflight:** Đọc Issue + Acceptance Criteria + **Target Directories (allowed paths)**, branch, working tree, project scope, `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`, requirements/ADR/contracts liên quan và code hiện hành. Với vertical slice mới, MUST kiểm tra **composition root** `backend-go/cmd/server/main.go` (AR-002): cần startup/wiring dependencies nào và **đường dẫn đó đã có trong allowed paths chưa**; nêu mọi path cần bổ sung trong small design proposal AI-003 **trước khi viết code**.

**AI-002 — No out-of-scope writes:** Chỉ sửa file trong allowlist Issue. Nếu cần test/doc/migration hoặc **composition-root wiring tại `backend-go/cmd/server/main.go`** ngoài scope → STOP, chỉ rõ file + lý do trong AI-003 và yêu cầu owner mở rộng Issue allowed paths **trước khi viết**. Nếu `main.go` đã được cho phép, chỉ thực hiện minimal dependency construction/startup wiring theo AR-002; không nhét business logic vào `main.go`. Không tự mở scope hoặc sửa contract ngầm.

**AI-003 — Small design proposal:** Trước code, mô tả bằng 5–10 dòng: input/output, invariant, error paths, modules/files, tests, **composition-root wiring/allowed path gap (AI-001/002)**. Nếu thiết kế thêm framework/new lib, phải chứng minh không có phương án đơn giản hơn và tuân GB-007.

**AI-004 — Implement smallest vertical slice:** Một use case hoàn chỉnh, buildable, reviewable, được wire ở composition root **khi được phép**. Nếu blocked do path chưa approved, báo `BLOCKED_SCOPE` thay vì sửa file trái phép hoặc tự nhận slice đã chạy. Không sinh code placeholder ở 7 tầng và nói đã implement.

**AI-005 — Search before create:** Tìm model, helper, schema, query đã có; reuse nếu đúng ownership. Không duplicate contracts hoặc business logic.

**AI-006 — Avoid invented APIs:** Xác minh Go version, dependency versions, function signatures từ source/`go doc`; không phỏng đoán thư viện.

**AI-007 — Stable contracts:** Không đổi MQTT topic, frame layout, API schema, SQL migration hoặc state semantics nếu chưa được yêu cầu, không tương thích hoặc chưa review.

**AI-008 — Test the change:** Unit + boundary + contract + integration tương ứng; run bằng tool thật khi được phép. Chưa chạy phải khai báo `NOT_RUN`.

**AI-009 — Explain failures, don't hide:** Nếu build/test fail, xác định command, root cause, scope và phương án; không xóa assertions/lint rules để được PASS.

**AI-010 — Self-review deletion pass:** Loại bỏ unused imports, dead code, abstraction vô lý, duplicate validation, speculative generalization, redundant errors/logging, retry lồng và config không dùng.

**AI-011 — Git discipline:** Feature branch có Issue, `git status`, `git diff --check`, secret scanning, conventional commit, PR liên kết Issue. Không force-push `main`, tự merge hoặc destructive operations.

**AI-012 — Honest final report:** Báo files changed, scope/AC mapping, commands/results, risks, untested cases, contract/migration impacts, reviewer requirements, SHA nếu thật sự commit. Không ghi “đã build/test/push/merged” khi chưa làm.

### Bản mẫu báo cáo mỗi tác vụ AI

```text
ISSUE / BRANCH / BASE_SHA:
SCOPE / ALLOWED_PATHS:
REQUIREMENTS & CONTRACTS READ:
DESIGN: (ngắn, không framework thừa)
FILES CHANGED:
INVARIANTS & ERROR PATHS:
TESTS EXECUTED: <command + result, or NOT_RUN>
SECURITY / COMPATIBILITY / MIGRATION IMPACT:
NOT_VERIFIED / BLOCKERS:
REVIEWERS REQUIRED:
```

## 14. PR checklist / Definition of Done (DoD)

- [ ] Issue/AC/allowed paths được đối chiếu; thay đổi chỉ trong scope đã duyệt.
- [ ] Code thực hiện use case cần thiết; không thừa abstraction/logic/dep; độ phức tạp được giải thích.
- [ ] Errors và context cancellation đầy đủ; không error swallowing hoặc hidden retry.
- [ ] Concurrency bounded, goroutine có owner; shutdown được kiểm soát khi có service chạy nền.
- [ ] Input validation đúng boundary; security/RBAC/secrets được kiểm soát.
- [ ] Contracts, DB constraints, migrations và compatibility được kiểm tra nếu ảnh hưởng.
- [ ] Log/correlation/error paths đủ debug; không lộ dữ liệu nhạy cảm.
- [ ] Unit/boundary/contract/integration tests phù hợp và bằng chứng thực thi có thật.
- [ ] gofmt/vet/test/race/lint/vuln checks đã chạy **hoặc** ghi rõ NOT_RUN/NOT_VERIFIED.
- [ ] Human review với control plane/MQTT/crypto/TDMA/reliability interface.
- [ ] Không tự tuyên bố production-ready, latency SLA, RF/HIL PASS.

## 15. Các anti-pattern bị từ chối mặc định

| Anti-pattern | Thay bằng |
|---|---|
| `handler → controller → service → usecase → manager → repository` chỉ pass-through | Một handler/adapter + domain operation rõ ràng + storage adapter thực sự cần |
| `interface` cho mọi struct | Concrete type mặc định; interface nhỏ khi consumer cần thay dependency |
| Generic repository / ORM để viết một vài SQL | Explicit SQL/query methods + transaction boundaries |
| `go func()` mỗi incoming message | Bounded worker pool hoặc xử lý tuần tự có đo đạc |
| `recover()` toàn hệ thống để che panic | Fix bug, xử lý errors tường minh; scoped recover nếu boundary bắt buộc |
| `log.Printf` ở từng layer và `return err` | Log một lần tại boundary, wrap có operation context |
| `time.Sleep` để “đảm bảo ACK đã tới” | Explicit state/event/timeout và correlation IDs |
| Retry mọi error mãi mãi | Retry transient/idempotent với budget và observability |
| `interface{}`/`map[string]any` cho schema ổn định | Typed struct + schema validation |
| Accept MQTT PUBACK như RF execution | Wait/validate Gateway stage/active reports |
| “Tối ưu” bằng cache, goroutine, reflection trước benchmark | Đo bottleneck trước, giữ path đơn giản |
| Sửa schema/contracts ngoài Issue | Cross-team change control + compatibility tests |

## 16. Đề xuất adoption / rollout (chưa thực thi)

1. **Review** v1.0 bởi Backend Lead, Gateway/Protocol Owner, Security/DevOps và Reviewer của repo. Giải quyết chênh lệch với ADR/contract hiện hành.
2. **Approve** một standard duy nhất, đồng bộ instruction đang có ở `.github/instructions/backend.instructions.md`; **không tạo file mới cạnh tranh cùng `applyTo`**.
3. **Create task/Issue** liệt kê chính xác allowed paths gồm policy docs, `.github/instructions`, quality tooling, test harness; không sửa ngoài Issue.
4. **Trial** trên một vertical slice nhỏ (vd. MQTT envelope validator + duplicate ingestion path khi Issue cho phép), đo review noise, debug latency, maintainability.
5. **Tune** linters và CI theo Go 1.27.3/tool versions pin; chia checks fast/slow và evidence G0–G6.

## 17. Nguồn và traceability

### Nguồn bên ngoài (tham chiếu đã kiểm tra, không được hiểu là tất cả rules đều từ các nguồn này)

- Go Team, *Effective Go*: <https://go.dev/doc/effective_go>
- Go Team, *Go Code Review Comments*: <https://go.dev/wiki/CodeReviewComments>
- Google, *Go Style Guide* (normative foundation): <https://google.github.io/styleguide/go/guide>
- Google, *Go Style Best Practices* (non-normative): <https://google.github.io/styleguide/go/best-practices>
- Uber, *Uber Go Style Guide*: <https://github.com/uber-go/guide/blob/master/style.md>
- Go Team, *Organizing a Go Module*: <https://go.dev/doc/modules/layout>
- Go Team, *Managing Dependencies*: <https://go.dev/doc/modules/managing-dependencies>
- Go Team, *Data Race Detector*: <https://go.dev/doc/articles/race_detector>
- Go Team, *Database SQL Transactions*: <https://go.dev/doc/database/execute-transactions>
- Go Team, *Avoiding SQL Injection*: <https://go.dev/doc/database/sql-injection>
- Go Team, *Structured Logging with slog*: <https://go.dev/blog/slog>
- Go Team, *Vulnerability Management*: <https://go.dev/doc/security/vuln/>
- OWASP, *ASVS 5.0.0*: <https://asvs.owasp.org/>
- GolangCI-Lint configuration: <https://golangci-lint.run/docs/configuration/file/>
- Go Team, *gofmt command*: <https://go.dev/cmd/gofmt/> (đường dẫn thư mục được duyệt đệ quy; `-l` không tự fail khi có unformatted files).
- Eclipse Paho Go MQTT 5 client & ack semantics: <https://github.com/eclipse-paho/paho.golang> và <https://pkg.go.dev/github.com/eclipse/paho.golang/paho>.
- Go 1.27 release history: <https://go.dev/doc/devel/release>; download: <https://go.dev/dl/>. Dependency versions will be selected and tested in a separate implementation Issue.

### Nguồn nội bộ (đã đối chiếu trên default branch khi biên soạn)

- `backend-go/go.mod` (`go 1.27.3`), `backend-go/README.md`, `backend-go/cmd/server/main.go` (scaffold).
- `.github/copilot-instructions.md` (allowed paths + human review), `.github/instructions/backend.instructions.md` (existing targeted agent rules).
- `docs/architecture/system-overview.md` (design draft, baseline 1.1).
- `docs/requirements/requirements.md` (requirements draft, các trạng thái NOT_VERIFIED).
- `docs/adr/0002-mqtt-5.md` (`OWNER_ACCEPTED`, cross-team review pending, implementation NOT_VERIFIED).
- `contracts/mqtt/topics.md` (`0.1.0-draft`, MQTT 5.0 semantics, topics, idempotency, schedule ACK/report).
- `contracts/api/openapi.yaml` (`1.0.0-draft`, not implemented).
- `docs/verification/acceptance-gates.md` (G0–G6 và evidence).
- User-provided `esp32_sx1762.md` (architecture reference); `monorepo-guide.md` (v1.0 draft planning reference, not adopted policy).

**Tuyên bố trạng thái:** Tài liệu này là **biên soạn/chưa được merge**. Chưa chạy build, test, security scan, integration, RF hoặc HIL cho bất kỳ implementation mới nào. Repo không được sửa bởi việc tạo bản tài liệu này.