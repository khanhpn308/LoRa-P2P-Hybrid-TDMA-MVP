| Group | Rule IDs |
|---|---|
| GGS | GGS-001..014 |
| GB | GB-001..010 |
| AR | AR-001..008 |
| GO | GO-001..014 |
| CT | CT-001..009 |
| MQ | MQ-001..012 |
| SC | SC-001..008 |
| DB | DB-001..010 |
| RT | RT-001..011 |
| OB | OB-001..012 |
| SE | SE-001..009 |
| TS | TS-001..011 |
| QG | QG-001..008 |
| AI | AI-001..012 |

Rule fields: `ID | scope | directive | verification | failure action | source`. `v1#Lnn` expands to [immutable v1](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/da566695a92bd54ee9226141c2340cfe6e67b399/docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V1.0.md#Lnn). `CARRIED`, `REVISED`, `VARIANT` preserve source disposition, not technical sign-off.

## 1. GGS — Google Go style

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| GGS-001 | `Go identifiers` | MUST use gofmt formatting for touched Go files | STATIC | `FIX` | [Google: NORMATIVE_CANONICAL](https://google.github.io/styleguide/go/guide#formatting) |
| GGS-002 | `Go identifiers` | MUST use MixedCaps/mixedCaps for identifiers, not C-style snake_case; acronym casing should follow established Go conventions | STATIC | `FIX` | [Google: NORMATIVE_CANONICAL](https://google.github.io/styleguide/go/guide#mixed-caps) |
| GGS-003 | `Go packages` | SHOULD choose short meaningful lowercase package names without underscores; avoid util/common dumping-ground package names | REVIEW | `FIX` | [Google: NORMATIVE_SUBORDINATE](https://google.github.io/styleguide/go/decisions#package-names) |
| GGS-004 | `Go receivers` | SHOULD use a short consistent receiver name for methods of a given type; avoid this/self | STATIC | `FIX` | [Google: NORMATIVE_SUBORDINATE](https://google.github.io/styleguide/go/decisions#receiver-names) |
| GGS-005 | `Go API naming` | SHOULD avoid Get prefix for simple property access; use a meaningful verb for expensive fetch/remote operations | REVIEW | `FIX` | [Google: NORMATIVE_SUBORDINATE](https://google.github.io/styleguide/go/decisions#getters) |
| GGS-006 | `Go code` | MUST handle and return errors explicitly rather than using panic for expected operational failures; explain any deliberately ignored error | STATIC,UNIT | `FIX` | [Google: NORMATIVE_SUBORDINATE](https://google.github.io/styleguide/go/decisions#errors) |
| GGS-007 | `Go error boundaries` | SHOULD choose %w only for intentionally exposed inspection chain; %v/translated errors at external boundary can avoid leaking internals; test errors.Is/As contracts | UNIT,REVIEW | `FIX` | [Google: ADVISORY_NONNORMATIVE](https://google.github.io/styleguide/go/best-practices#adding-information-to-errors) |
| GGS-008 | `Go functions` | MUST pass context.Context first in functions needing caller cancellation except designated entrypoint signatures; do not retain context in structs | STATIC,UNIT | `FIX` | [Google: NORMATIVE_SUBORDINATE](https://google.github.io/styleguide/go/decisions#contexts) |
| GGS-009 | `Go interfaces` | SHOULD use narrow interfaces with real consumer need, prefer concrete return types by default; document contracts and justified exception | REVIEW,UNIT | `FIX` | [Google: ADVISORY_NONNORMATIVE](https://google.github.io/styleguide/go/best-practices#interfaces) |
| GGS-010 | `Go code` | SHOULD prefer clarity then simplicity then concision then maintainability then consistency in code style, without overriding repo correctness/security requirements | REVIEW | `EXPLAIN` | [Google: NORMATIVE_CANONICAL](https://google.github.io/styleguide/go/guide#style-principles) |
| GGS-011 | `Go comments` | SHOULD document why/invariants and avoid comments that repeat what clear code already expresses | REVIEW | `FIX` | [Google: NORMATIVE_CANONICAL](https://google.github.io/styleguide/go/guide#clarity) |
| GGS-012 | `Go tests` | SHOULD create focused test helpers and doubles at actual interface boundaries rather than generic mock frameworks without need | UNIT,REVIEW | `FIX` | [Google: ADVISORY_NONNORMATIVE](https://google.github.io/styleguide/go/best-practices#test-double-and-helper-packages) |
| GGS-013 | `Go implementation` | SHOULD avoid package-prefix repetition in names and use scope-appropriate identifiers; allow longer names for wider scopes | REVIEW | `FIX` | [Google: ADVISORY_NONNORMATIVE](https://google.github.io/styleguide/go/best-practices#function-and-method-names) |
| GGS-014 | `Go implementation` | SHOULD use ordinary Go constructs and stdlib where sufficient; no speculative reflection/interface/factory chains | REVIEW | `EXPLAIN` | [Google: NORMATIVE_CANONICAL](https://google.github.io/styleguide/go/guide#least-mechanism) |

**Conflict examples:** (a) `GetThing` naming is not an unconditional ban when an HTTP GET or expensive fetch genuinely explains behavior; (b) `%w` is not mandatory for every error boundary; (c) all forms of `context.Background()` are not forbidden—process entrypoints/test signatures have legitimate exceptions; (d) Google recommends small interfaces but does not mandate one interface for each struct; (e) importing Google Best Practices does not imply a new lint rule or a guaranteed automated PASS.

## 2. Technical rule groups

### 2.1 GB — General Backend Principles (GB-001..010)

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| GB-001 | `backend-go/**` | Correctness > Safety > Reliability > Maintainability > Performance. Code ngắn hơn nhưng dễ sai, mất dữ liệu, hoặc không truy vết được không được ưu tiên. | REVIEW | `FIX_OR_EXPLAIN` | v1#L32 · CARRIED |
| GB-002 | `backend-go/**` | YAGNI: Chỉ triển khai acceptance criteria của Issue, invariant bắt buộc và failure paths cần thiết. Không xây dự phòng *future scalability* giả định. | REVIEW | `FIX_OR_EXPLAIN` | v1#L34 · CARRIED |
| GB-003 | `backend-go/**` | KISS: Một bài toán có thể giải bằng logic thuần Go, một đường xử lý rõ ràng thì không dựng framework, plugin registry, event bus, factory chain hoặc nhiều adapter không cần thiết. | REVIEW | `FIX_OR_EXPLAIN` | v1#L36 · CARRIED |
| GB-004 | `backend-go/**` | Explicit > clever: Ưu tiên tuần tự rõ ràng, tên có nghĩa, trạng thái hữu hạn, return sớm. Tránh reflection, generic helper, magic hook, middleware chain dài khi không có nhu cầu cụ thể. | REVIEW | `FIX_OR_EXPLAIN` | v1#L38 · CARRIED |
| GB-005 | `backend-go/**` | DRY hợp lý: Tránh sao chép *business invariant*, codec contract hoặc SQL quan trọng; lặp vài dòng khai báo đơn giản chấp nhận được nếu abstraction làm khó đọc hơn. | REVIEW | `FIX_OR_EXPLAIN` | v1#L40 · CARRIED |
| GB-006 | `backend-go/**` | Không tạo abstraction để “sẽ có ngày dùng”. Chỉ tách interface/package khi có boundary thực tế, nhu cầu test hoặc nhiều implementation thật; interface thường nằm ở consumer và đủ nhỏ, không tạo interface một-một cho mọi struct. | REVIEW | `FIX_OR_EXPLAIN` | v1#L42 · CARRIED |
| GB-007 | `backend-go/**` | PROPOSED_STACK: Go 1.27.3 pinned repo lock. net/http, pgx/v5, Eclipse Paho MQTT5 listed as candidate preferred dependencies in v1; concrete module versions not installed/approved. No new frameworks, ORMs or dependencies without scoped authorization and module/review evidence. | REVIEW | `FIX_OR_EXPLAIN` | v1#L44 · REVISED |
| GB-008 | `backend-go/**` | One responsibility, cohesive packages: Tên package theo domain; hạn chế `util`, `common`, `helpers`, `manager`, `base`, `core` không rõ nghĩa. | REVIEW | `FIX_OR_EXPLAIN` | v1#L46 · CARRIED |
| GB-009 | `backend-go/**` | No silent fallback: Không `return nil` khi lỗi, không ngầm bỏ bản tin, không cập nhật trạng thái thành công vì lệnh publish đã được broker nhận. Fallback phải được thiết kế, log/metric và test rõ ràng. | REVIEW | `FIX_OR_EXPLAIN` | v1#L48 · CARRIED |
| GB-010 | `backend-go/**` | Optimize verified bottlenecks only: Benchmark/profiling trước khi pooling, batching, cache, custom allocator hoặc tối ưu có thể làm phức tạp code. | REVIEW | `FIX_OR_EXPLAIN` | v1#L50 · CARRIED |

### 2.2 AR — Architecture & Package Boundaries (AR-001..008)

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| AR-001 | `backend-go/**` | Dùng module hiện có `backend-go/`, không tạo thêm `go.mod` hoặc multi-module workspace nếu không được duyệt. | STATIC,BUILD | `STOP_ON_SCOPE` | v1#L56 · CARRIED |
| AR-002 | `backend-go/**` | Giữ entrypoint ở `backend-go/cmd/server/`; entrypoint chỉ load/validate config → construct dependencies → start services → wait signal → shutdown, không chứa business logic. | STATIC,BUILD | `STOP_ON_SCOPE` | v1#L58 · CARRIED |
| AR-003 | `backend-go/**` | Đặt internal domain theo feature và quy hoạch sẵn, bổ sung khi Issue cần, không tạo package rỗng chỉ để đủ sơ đồ: | STATIC,BUILD | `STOP_ON_SCOPE` | v1#L60 · CARRIED |
| AR-004 | `backend-go/**` | Dependency direction: adapters (`api`, `mqtt`, `storage`) phụ thuộc domain/service contracts khi có; domain không import HTTP handler, MQTT library hoặc SQL driver. Các domain giao tiếp bằng exported operations tối thiểu, không cần dựng nhiều layer *handler → service → usecase → manager → repository* nếu chỉ pass-through. (STATIC: verify dependency import/call edges via `codegraph_explore` when available; else `NOT_RUN` and scoped source inspection.) | STATIC,BUILD | `STOP_ON_SCOPE` | v1#L77 · CARRIED |
| AR-005 | `backend-go/**` | Không import code firmware C để trao đổi; dùng contracts versioned. Không cho web/mobile truy cập trực tiếp DB hoặc MQTT. | STATIC,BUILD | `STOP_ON_SCOPE` | v1#L79 · CARRIED |
| AR-006 | `backend-go/**` | Một use case chỉ có một nơi sở hữu invariant: schedule transition thuộc scheduler, idempotency ingestion ở boundary dữ liệu + unique constraint DB, RBAC ở API/service authorization boundary. | STATIC,BUILD | `STOP_ON_SCOPE` | v1#L81 · CARRIED |
| AR-007 | `backend-go/**` | SQL và persistence chi tiết chỉ xuất hiện ở storage hoặc module được phê duyệt; không truy vấn DB trong request validation lặp lại vô ích. | STATIC,BUILD | `STOP_ON_SCOPE` | v1#L83 · CARRIED |
| AR-008 | `backend-go/**` | Không tạo generic `Repository[T]`, base controller, service locator hoặc singleton mutable toàn cục để làm “clean architecture”. | STATIC,BUILD | `STOP_ON_SCOPE` | v1#L85 · CARRIED |

### 2.3 GO — Go Language, Types, Errors & Context (GO-001..014)

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| GO-001 | `backend-go/**/*.go` | MUST `gofmt`, import group hợp lý; CI kiểm tra thay vì tranh luận format. Dùng `MixedCaps/mixedCaps`; acronym theo quy ước nhất quán (`ID`, `URL`, `HTTP`, `MQTT`). | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L89 · CARRIED |
| GO-002 | `backend-go/**/*.go` | Tên phải biểu đạt domain: `ScheduleVersion`, `EventID`, `ActivateAt`; tránh `data`, `obj`, `res`, `temp` ngoài scope rất ngắn. | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L91 · CARRIED |
| GO-003 | `backend-go/**/*.go` | Giữ scope biến hẹp; dùng guard clauses/early return để tránh nested `if` sâu. | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L93 · CARRIED |
| GO-004 | `backend-go/**/*.go` | Không viết wrapper/no-op chỉ để che 1 dòng code. Hàm nên làm một công việc đọc được; không áp hard limit số dòng nếu việc tách làm mất mạch xử lý. | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L95 · CARRIED |
| GO-005 | `backend-go/**/*.go` | Comments giải thích why/invariant/security/contract, không tường thuật cú pháp. Exported identifiers nên có GoDoc khi public API thực sự cần. | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L97 · CARRIED |
| GO-006 | `backend-go/**/*.go` | Dùng struct typed cho contract; JSON tags tường minh. Phân biệt DTO với DB row và domain value khi khác ngữ nghĩa; không biến mọi dữ liệu thành `map[string]any`. | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L99 · CARRIED |
| GO-007 | `backend-go/**/*.go` | Không dùng `panic` cho input, network hoặc DB error bình thường; chỉ `panic` cho programmer invariant cực kỳ bất thường nếu phù hợp, để entrypoint kiểm soát process exit. | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L101 · CARRIED |
| GO-008 | `backend-go/**/*.go` | Return useful typed errors; use errors.Is/As for classification. Use %w only when preserving the underlying error chain is an intentional API contract; otherwise translate boundary errors or annotate with %v where appropriate. Do not wrap redundant context. | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L103 · REVISED |
| GO-009 | `backend-go/**/*.go` | Handle error once: nơi phát hiện xử lý/return; log *một lần tại boundary chịu trách nhiệm* (HTTP/MQTT worker/process) thay vì log ở mọi layer. | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L105 · CARRIED |
| GO-010 | `backend-go/**/*.go` | Không `_ = fn()` cho I/O hoặc cleanup có hậu quả; nếu bỏ qua lỗi an toàn được thì comment rõ lý do/đưa vào test. | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L107 · CARRIED |
| GO-011 | `backend-go/**/*.go` | context.Context first for APIs requiring cancellation (except canonical handler/test entrypoint signatures); propagate deadlines, do not store context inside application structs or create unrelated Background mid-call-chain. Verify context lifetime and cancellation. | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L109 · VARIANT |
| GO-012 | `backend-go/**/*.go` | Tránh magic numbers trong invariant; đặt tên và đơn vị (`time.Duration`, bytes, microseconds). Chưa được chốt hoặc đo → configuration/validation/`NOT_VERIFIED`, không hardcode SLA. | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L111 · CARRIED |
| GO-013 | `backend-go/**/*.go` | Dùng UTC cho event/DB timestamps; lưu `time.Time`/UTC theo schema thực tế, có trường `time_source` khi contract yêu cầu; không coi monotonic boot-clock là wall-clock. | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L113 · CARRIED |
| GO-014 | `backend-go/**/*.go` | Target code dùng đúng Go 1.27.3: `backend-go/go.mod` (`go 1.27.3`), `.go-version` (`1.27.3`) và CI phải khớp. Không tự ý nâng toolchain hoặc sử dụng API chỉ có ở bản Go mới hơn nếu không có Issue phê duyệt. | STATIC,BUILD | `FIX_OR_EXPLAIN` | v1#L115 · CARRIED |

### 2.4 CT — API & MQTT Boundary Contracts (CT-001..009)

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| CT-001 | `backend-go/internal/api/**,backend-go/internal/mqtt/**` | `contracts/api/openapi.yaml` là interface proposal được versioned; không tự thay endpoint, field, status, auth model hoặc serialization khi chưa có Issue + consumer review. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L136 · CARRIED |
| CT-002 | `backend-go/internal/api/**,backend-go/internal/mqtt/**` | `contracts/mqtt/topics.md` và `schemas/` kiểm soát topic, QoS, Retain, expiry, event ID, message semantics. Mọi thay đổi backward-incompatible phải có migration/compatibility plan và contract tests. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L138 · CARRIED |
| CT-003 | `backend-go/internal/api/**,backend-go/internal/mqtt/**` | Validate input at trust boundary: HTTP body/query/path, MQTT topic/payload, DB external data. Không validate y nguyên lần nữa qua mọi layer, nhưng domain MUST enforce invariant khi được gọi từ nhiều entrypoints. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L140 · CARRIED |
| CT-004 | `backend-go/internal/api/**,backend-go/internal/mqtt/**` | Giới hạn kích thước body/message, array, string, pagination, time range, ID và worker queue. Reject unknown/invalid values theo schema đang áp dụng; không suy diễn field thiếu từ RF packet. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L142 · CARRIED |
| CT-005 | `backend-go/internal/api/**,backend-go/internal/mqtt/**` | Lỗi HTTP trả status/domain error nhất quán theo contract; client nhận thông báo an toàn, server log giữ error cause; không trả SQL query, stacktrace, credentials hoặc internal path. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L144 · CARRIED |
| CT-006 | `backend-go/internal/api/**,backend-go/internal/mqtt/**` | API admin/operator/viewer phải kiểm RBAC server-side trước data mutation hoặc sensitive read; UI visibility không phải authorization. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L146 · CARRIED |
| CT-007 | `backend-go/internal/api/**,backend-go/internal/mqtt/**` | HTTP server đặt read/header/body và idle timeouts theo cấu hình được review; outbound HTTP dùng context + timeout; WSS connection/read/write/heartbeat policy có giới hạn và test. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L148 · CARRIED |
| CT-008 | `backend-go/internal/api/**,backend-go/internal/mqtt/**` | Health có ý nghĩa phân biệt: liveness (`process alive`) ≠ readiness (`dependencies ready`) ≠ hệ thống RF healthy. Không hứa Gateway online qua DB last-known state. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L150 · CARRIED |
| CT-009 | `backend-go/internal/api/**,backend-go/internal/mqtt/**` | Mutation command/schedule có request ID; request IDs và state transitions phải truy vết từ HTTP → DB → MQTT → Gateway ACK/report, không suy diễn *published = executed*. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L152 · CARRIED |

### 2.5 MQ — MQTT 5.0 Transport, QoS1 & State (MQ-001..012)

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| MQ-001 | `backend-go/internal/mqtt/**` | Tuân theo `docs/adr/0002-mqtt-5.md`: Gateway ↔ Backend MQTT 5.0, TLS/client identity/ACL; không tự fallback MQTT 3.1.1 ngoài contract v1. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L156 · CARRIED |
| MQ-002 | `backend-go/internal/mqtt/**` | QoS 1 = at least once, xử lý duplicate và out-of-order. `event_id` ổn định qua retry/replay, cùng `gateway_id`; unique key `(gateway_id, event_id)` ở PostgreSQL. `event_seq` không được ép về `uint8` hoặc float64 không an toàn. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L158 · CARRIED |
| MQ-003 | `backend-go/internal/mqtt/**` | BLOCKED_DETAIL: Validate topic, authenticated Gateway binding, schema/version and payload before domain side effects. Poison/permanent vs transient MQTT QoS1 ACK policy, Paho callback/Client.Ack implementation and durable quarantine ordering MUST be reviewed and verified with exact dependency and broker tests; no unconditional early PUBACK or assumed NACK from callback error. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L160 · REVISED |
| MQ-004 | `backend-go/internal/mqtt/**` | Backpressure: bounded worker count, bounded queue, bounded message sizes. Nêu rõ chọn block/reject/drop và đo số message mất; không silently drop alert. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L165 · CARRIED |
| MQ-005 | `backend-go/internal/mqtt/**` | Bounded retry với jitter/backoff ở I/O boundary, chỉ retry transient và operation idempotent; không retry business validation hay unauthorized. Shutdown phải dừng retry được. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L167 · CARRIED |
| MQ-006 | `backend-go/internal/mqtt/**` | BLOCKED_DETAIL: Do not publish stale or retained downlink schedule/command. Candidate MQTT5 Message Expiry calculation and Retain=false rules require reviewed contract and trusted UTC; treat numerical expiry rounding semantics as proposed until producer/consumer tests. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L169 · REVISED |
| MQ-007 | `backend-go/internal/mqtt/**` | BLOCKED_DETAIL: Backend MQTT session profile (ClientID, Clean Start, Session Expiry), reconnect handling and queue budgets are proposed in contract; confirm broker/Paho version and actual tests before claiming READY. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L171 · REVISED |
| MQ-008 | `backend-go/internal/mqtt/**` | Broker PUBACK chỉ chứng minh transport ack; không tương đương Gateway `STAGE_ACK`, `ACTIVE_REPORT` hoặc RF ACK. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L173 · CARRIED |
| MQ-009 | `backend-go/internal/mqtt/**` | BLOCKED_CONTRACT_CONFLICT: Persist immutable schedule intent; transport PUBACK is not ACTIVE. Draft MQTT semantic-rules.md §4 currently specifies STAGED → ACTIVE on authenticated correlated ACTIVE_REPORT; the v1 permission to jump PROPOSED/SENT → ACTIVE is NOT accepted by this standard. Report reordered report as PENDING_RECONCILIATION; do not invent transitions including EXPIRED → ACTIVE. Resolve producer/consumer/state policy via separate scoped contract Issue and tests. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L175 · REVISED |
| MQ-010 | `backend-go/internal/mqtt/**` | Reconnect phải reconcile last-known/retained status và authoritative persisted state; không auto-send stale schedule/command sau restart. Chấp nhận duplicate ACK/reports an toàn. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L179 · CARRIED |
| MQ-011 | `backend-go/internal/mqtt/**` | Timestamp ingress phải phân biệt `observed_at` (có thể null/chất lượng clock khác nhau), `ingested_at` server clock, `radio_rx_monotonic_us` relative boot time. Không bịa thời gian đo. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L181 · CARRIED |
| MQ-012 | `backend-go/internal/mqtt/**` | MQTT adapter không quyết định slot activation, RF guard time hay radio hardware behavior. Đó là trách nhiệm Gateway Firmware/contract. | CONTRACT,INTEGRATION | `STOP_ON_CONTRACT` | v1#L183 · CARRIED |

### 2.6 SC — TDMA Scheduler Planning Logic (SC-001..008)

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| SC-001 | `backend-go/internal/scheduler/**` | Scheduler là pure deterministic planning logic khi có thể: `inputs + constraints → proposed schedule/result`. Clock/time/randomness truyền qua dependency rõ ràng, không ẩn trong logic cốt lõi. | UNIT,CONTRACT | `STOP_ON_CONTRACT` | v1#L187 · CARRIED |
| SC-002 | `backend-go/internal/scheduler/**` | Tất cả schedule version/slot/frequency/timing boundaries phải theo contract hiện hành; không tự đặt superframe, guard-time, duty limits hoặc alert latency làm thông số đã duyệt. | UNIT,CONTRACT | `STOP_ON_CONTRACT` | v1#L189 · CARRIED |
| SC-003 | `backend-go/internal/scheduler/**` | Validate completeness, non-overlap, node/gateway identity, version ordering, payload size, expiry và các giới hạn đã được phê duyệt trước publish. | UNIT,CONTRACT | `STOP_ON_CONTRACT` | v1#L191 · CARRIED |
| SC-004 | `backend-go/internal/scheduler/**` | Fail closed với unsupported version, invalid schedule, stale ACK, activation time không đáng tin hoặc thông tin không đủ. | UNIT,CONTRACT | `STOP_ON_CONTRACT` | v1#L193 · CARRIED |
| SC-005 | `backend-go/internal/scheduler/**` | Không ghép “scheduler planning” và “MQTT publish” thành một hàm lớn không thể unit-test; để adapter I/O riêng khỏi thuật toán. | UNIT,CONTRACT | `STOP_ON_CONTRACT` | v1#L195 · CARRIED |
| SC-006 | `backend-go/internal/scheduler/**` | PROPOSED_WITH_BLOCKER: Persist schedule intent and protect against delayed SENT worker downgrade; state CAS/monotonicity for ACK/reports must follow reviewed transition table. MQ-009 conflict remains BLOCKED; no implicit ACTIVE promotion. | UNIT,CONTRACT | `STOP_ON_CONTRACT` | v1#L197 · REVISED |
| SC-007 | `backend-go/internal/scheduler/**` | Không dùng wall-clock local `time.Now()` rải rác trong thuật toán; dùng `clock` injection chỉ khi thực sự cần test controlled time, không dựng framework đồng hồ tổng quát. | UNIT,CONTRACT | `STOP_ON_CONTRACT` | v1#L199 · CARRIED |
| SC-008 | `backend-go/internal/scheduler/**` | Test bắt buộc cho overlapping slots, exact boundaries, expiry, duplicate reports, unknown node, version mismatch, reboot/reconnect. Timing/RF/HIL chỉ PASS khi có evidence ngoài unit-test. | UNIT,CONTRACT | `STOP_ON_CONTRACT` | v1#L201 · CARRIED |

### 2.7 DB — PostgreSQL Persistence & Migrations (DB-001..010)

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| DB-001 | `backend-go/internal/storage/**,backend-go/migrations/**` | PostgreSQL là data store duy nhất cho MVP. Không tự thêm cache/distributed lock/queue DB khác. | UNIT,DB_INTEGRATION | `STOP_ON_SCHEMA` | v1#L205 · CARRIED |
| DB-002 | `backend-go/internal/storage/**,backend-go/migrations/**` | SQL parameterized; tuyệt đối không build SQL bằng string concat từ user input. Dynamic identifiers phải allowlist. | UNIT,DB_INTEGRATION | `STOP_ON_SCHEMA` | v1#L207 · CARRIED |
| DB-003 | `backend-go/internal/storage/**,backend-go/migrations/**` | Sử dụng DB pool được quản lý lifecycle; cấu hình max connections và timeout theo workload/test, không chọn số “chuẩn” thiếu evidence. | UNIT,DB_INTEGRATION | `STOP_ON_SCHEMA` | v1#L209 · CARRIED |
| DB-004 | `backend-go/internal/storage/**,backend-go/migrations/**` | PROPOSED_WITH_BLOCKER: Keep transaction short; persist intent before MQTT publish and protect concurrent updates; no DB↔MQTT atomicity assumption. CAS guards must conform to reviewed schedule transition table; MQ-009 unresolved. | UNIT,DB_INTEGRATION | `STOP_ON_SCHEMA` | v1#L211 · REVISED |
| DB-005 | `backend-go/internal/storage/**,backend-go/migrations/**` | Dùng unique index/constraint cho idempotency, FK/check constraints khi phù hợp, và xác minh `RowsAffected`/`RETURNING` để phân biệt inserted vs duplicate khi cần. | UNIT,DB_INTEGRATION | `STOP_ON_SCHEMA` | v1#L213 · CARRIED |
| DB-006 | `backend-go/internal/storage/**,backend-go/migrations/**` | Query có context/deadline, pagination và giới hạn kết quả. Không SELECT * cho API ổn định khi field contract cần kiểm soát. | UNIT,DB_INTEGRATION | `STOP_ON_SCHEMA` | v1#L215 · CARRIED |
| DB-007 | `backend-go/internal/storage/**,backend-go/migrations/**` | Migration tăng dần, versioned, reviewable; không sửa lại migration đã áp dụng; schema change cần forward/backward compatibility khi có deploy staggered. | UNIT,DB_INTEGRATION | `STOP_ON_SCHEMA` | v1#L217 · CARRIED |
| DB-008 | `backend-go/internal/storage/**,backend-go/migrations/**` | Không tự thêm ORM nếu SQL đơn giản/đã đủ. Query code dễ đọc và error detail an toàn hơn pattern repository tổng quát. | UNIT,DB_INTEGRATION | `STOP_ON_SCHEMA` | v1#L219 · CARRIED |
| DB-009 | `backend-go/internal/storage/**,backend-go/migrations/**` | Lưu timestamp UTC và consistent numeric units; tránh ép `event_seq` hoặc ID lớn thành float ở JSON/SQL. | UNIT,DB_INTEGRATION | `STOP_ON_SCHEMA` | v1#L221 · CARRIED |
| DB-010 | `backend-go/internal/storage/**,backend-go/migrations/**` | Integration test chạy DB thật cho uniqueness, transactions, migrations, rollback, concurrent inserts và SQL constraints; mock-only không đủ chứng minh SQL behavior. | UNIT,DB_INTEGRATION | `STOP_ON_SCHEMA` | v1#L223 · CARRIED |

### 2.8 RT — Runtime, Concurrency & Shutdown (RT-001..011)

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| RT-001 | `backend-go/**` | Concurrency không phải mặc định. Sequential code là lựa chọn đầu tiên khi throughput của MVP đáp ứng. Chỉ thêm goroutines khi có parallelism, I/O isolation hoặc shutdown requirement thật. | STATIC,RACE,INTEGRATION | `FIX_OR_REPORT` | v1#L227 · CARRIED |
| RT-002 | `backend-go/**` | Mỗi goroutine phải có owner, cancellation, error path và `Wait`/`Join` lúc shutdown; không fire-and-forget hoặc goroutine trong `init()`. | STATIC,RACE,INTEGRATION | `FIX_OR_REPORT` | v1#L229 · CARRIED |
| RT-003 | `backend-go/**` | Bound worker pool và queue; không tạo goroutine per MQTT message/request vô hạn. Một hàng đợi lớn không thay thế backpressure policy. | STATIC,RACE,INTEGRATION | `FIX_OR_REPORT` | v1#L231 · CARRIED |
| RT-004 | `backend-go/**` | Mutex giữ vùng critical section nhỏ; không gọi network/DB/blocking I/O dưới lock trừ khi đã review rủi ro deadlock. | STATIC,RACE,INTEGRATION | `FIX_OR_REPORT` | v1#L233 · CARRIED |
| RT-005 | `backend-go/**` | Context cancellation propagate đến SQL, MQTT request/retry, HTTP downstream và background workers khi adapter hỗ trợ. Không dùng `context.Background()` giữa request flow để trốn cancellation. | STATIC,RACE,INTEGRATION | `FIX_OR_REPORT` | v1#L235 · CARRIED |
| RT-006 | `backend-go/**` | Cleanup theo thứ tự rõ: stop accepting → stop ingest/start shutdown → drain bounded in-flight work → flush/close logs/DB/MQTT → exit; có tổng shutdown deadline. | STATIC,RACE,INTEGRATION | `FIX_OR_REPORT` | v1#L237 · CARRIED |
| RT-007 | `backend-go/**` | Startup fail fast khi invalid config, secret thiếu, migration/schema bất tương thích hoặc dependency bắt buộc không sẵn sàng; readiness false thay vì báo healthy giả. | STATIC,RACE,INTEGRATION | `FIX_OR_REPORT` | v1#L239 · CARRIED |
| RT-008 | `backend-go/**` | Retry chỉ ở một tầng có ownership và budget. Không stack nested retries làm nhân số lần thử lên ngoài kiểm soát. | STATIC,RACE,INTEGRATION | `FIX_OR_REPORT` | v1#L241 · CARRIED |
| RT-009 | `backend-go/**` | Timer/ticker phải được stop khi không còn sử dụng. Không dùng `time.Sleep` để chờ tính đúng đắn của event order hoặc trạng thái production. | STATIC,RACE,INTEGRATION | `FIX_OR_REPORT` | v1#L243 · CARRIED |
| RT-010 | `backend-go/**` | Các lỗi bất thường phải lên được tới caller hoặc supervisor, không nuốt lỗi trong goroutine callback. | STATIC,RACE,INTEGRATION | `FIX_OR_REPORT` | v1#L245 · CARRIED |
| RT-011 | `backend-go/**` | Dùng race detector trong CI trên runner hỗ trợ; kiểm tra leak/buffer pressure qua integration/soak khi có background workers. | STATIC,RACE,INTEGRATION | `FIX_OR_REPORT` | v1#L247 · CARRIED |

### 2.9 OB — Observability, Logging & Metrics (OB-001..012)

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| OB-001 | `backend-go/**` | Dùng structured logging, mặc định cân nhắc `log/slog` stdlib của Go 1.27.3 nếu không có stack đã approved. Không tự đưa logging framework mới chỉ để đổi format. | STATIC,INTEGRATION | `FIX_OR_EXPLAIN` | v1#L251 · CARRIED |
| OB-002 | `backend-go/**` | Log event tại system boundary và các state transition có ý nghĩa, không log từng lần gọi helper hoặc mọi SQL thành công ở INFO. | STATIC,INTEGRATION | `FIX_OR_EXPLAIN` | v1#L253 · CARRIED |
| OB-003 | `backend-go/**` | Chuẩn field snake_case: `timestamp`, `level`, `component`, `operation`, `request_id`, `gateway_id`, `event_id`, `schedule_version`, `duration_ms`, `error`, `error_kind` tùy event. Trường thiếu thì bỏ, không dựng ID giả. | STATIC,INTEGRATION | `FIX_OR_EXPLAIN` | v1#L255 · CARRIED |
| OB-004 | `backend-go/**` | Severity policy: DEBUG = context chi tiết opt-in; INFO = lifecycle/state meaningful; WARN = recoverable anomaly; ERROR = operation failed/action required. Không log cùng error ở 5 lớp. | STATIC,INTEGRATION | `FIX_OR_EXPLAIN` | v1#L257 · CARRIED |
| OB-005 | `backend-go/**` | Khi request/command từ HTTP đi tới MQTT: preserve correlation identifiers; DB record và log có key đủ để truy lại lineage. | STATIC,INTEGRATION | `FIX_OR_EXPLAIN` | v1#L259 · CARRIED |
| OB-006 | `backend-go/**` | Startup log version/commit/config profile không chứa secrets; shutdown log reason và số in-flight còn lại nếu có. | STATIC,INTEGRATION | `FIX_OR_EXPLAIN` | v1#L261 · CARRIED |
| OB-007 | `backend-go/**` | Không log password, bearer token, TLS private key, full raw telemetry/payload nhạy cảm, secret env, SQL bind sensitive. Debug raw packet chỉ ở môi trường có kiểm soát, masking và sampling. | STATIC,INTEGRATION | `FIX_OR_EXPLAIN` | v1#L263 · CARRIED |
| OB-008 | `backend-go/**` | Lỗi phải có `operation + stable identifiers + cause + retryability`; không chỉ `something went wrong`. | STATIC,INTEGRATION | `FIX_OR_EXPLAIN` | v1#L265 · CARRIED |
| OB-009 | `backend-go/**` | Metrics tối thiểu theo các tính năng thực sự tồn tại: ingest success/error/duplicate, MQTT reconnect/queue depth/dropped count, DB latency/errors, schedule transition failures, request error/latency. Không dựng hệ telemetry phức tạp cho scaffold. | STATIC,INTEGRATION | `FIX_OR_EXPLAIN` | v1#L267 · CARRIED |
| OB-010 | `backend-go/**` | Không ghi metric labels bằng IDs có cardinality vô hạn (event_id, request_id); các IDs này chỉ dùng trong logs/traces. | STATIC,INTEGRATION | `FIX_OR_EXPLAIN` | v1#L269 · CARRIED |
| OB-011 | `backend-go/**` | Có chiến lược debug repeatable: deterministic fixture → reproduce test → log lineage → inspect DB state → compare contracts → fix root cause → regression test. | STATIC,INTEGRATION | `FIX_OR_EXPLAIN` | v1#L271 · CARRIED |
| OB-012 | `backend-go/**` | pprof/expvar hay debug endpoints không được public exposure mặc định; chỉ enable bằng config rõ, loopback/admin auth và review. | STATIC,INTEGRATION | `FIX_OR_EXPLAIN` | v1#L273 · CARRIED |

### 2.10 SE — Security, AuthN/AuthZ & Secrets (SE-001..009)

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| SE-001 | `backend-go/**` | TLS ngoài dev-insecure profile localhost được cô lập; verify certificates, client identity và MQTT ACL; không `InsecureSkipVerify` trong production. | SECURITY,CONTRACT | `STOP_ON_SECURITY` | v1#L277 · CARRIED |
| SE-002 | `backend-go/**` | Secrets chỉ đi qua secret management/env/approved runtime injection; không commit, embed trong test fixtures, print config dump hoặc leak ở error logs. | SECURITY,CONTRACT | `STOP_ON_SECURITY` | v1#L279 · CARRIED |
| SE-003 | `backend-go/**` | Authentication, authorization, RBAC phải xác minh ở server; mọi privileged command phải có actor và audit event. | SECURITY,CONTRACT | `STOP_ON_SECURITY` | v1#L281 · CARRIED |
| SE-004 | `backend-go/**` | Input/payload validation trước xử lý; giới hạn size, nesting, number ranges, timestamp bounds; bảo vệ DoS do malformed input. | SECURITY,CONTRACT | `STOP_ON_SECURITY` | v1#L283 · CARRIED |
| SE-005 | `backend-go/**` | Do not assume CRC = cryptographic authentication; hệ thống dùng custom LoRa P2P, không tự khai báo bảo mật LoRaWAN hoặc dùng LoRaWAN key/nonce scheme ngoài approved contract. | SECURITY,CONTRACT | `STOP_ON_SECURITY` | v1#L285 · CARRIED |
| SE-006 | `backend-go/**` | SQL injection prevention, HTTP security headers/CORS policy, WebSocket Origin/auth checks theo deployment threat model và contract. | SECURITY,CONTRACT | `STOP_ON_SECURITY` | v1#L287 · CARRIED |
| SE-007 | `backend-go/**` | Không dùng log để chứa PII/credential. Redact error details client-facing. | SECURITY,CONTRACT | `STOP_ON_SECURITY` | v1#L289 · CARRIED |
| SE-008 | `backend-go/**` | Dependencies kiểm tra vulnerability/license khi thêm hoặc cập nhật. Remediation phải đánh giá reachability, severity và breaking changes. | SECURITY,CONTRACT | `STOP_ON_SECURITY` | v1#L291 · CARRIED |
| SE-009 | `backend-go/**` | Những thay đổi authentication/crypto/control plane có human technical review, threat model hoặc security tests phù hợp trước khi merge. | SECURITY,CONTRACT | `STOP_ON_SECURITY` | v1#L293 · CARRIED |

### 2.11 TS — Testing Strategy & Integration Proof (TS-001..011)

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| TS-001 | `backend-go/**/*_test.go` | Không viết test chỉ để tăng coverage; test phải chứng minh behavior + invariant + failure modes. | UNIT,CONTRACT,INTEGRATION | `FIX_OR_REPORT` | v1#L297 · CARRIED |
| TS-002 | `backend-go/**/*_test.go` | Unit tests cho pure domain functions, table-driven khi làm rõ các trường hợp; dùng test names mô tả behavior, failure output chứa input/expected/got. | UNIT,CONTRACT,INTEGRATION | `FIX_OR_REPORT` | v1#L299 · CARRIED |
| TS-003 | `backend-go/**/*_test.go` | Boundary tests: missing field, empty string, overflow, negative/zero, max length, invalid type, duplicate, reordered, expired, malformed JSON, unsupported version. | UNIT,CONTRACT,INTEGRATION | `FIX_OR_REPORT` | v1#L301 · CARRIED |
| TS-004 | `backend-go/**/*_test.go` | Contract tests dùng chính `contracts/mqtt` schemas, `contracts/api` OpenAPI và test vectors ở `contracts/radio-mac` khi phù hợp; consumer/producer cùng review. | UNIT,CONTRACT,INTEGRATION | `FIX_OR_REPORT` | v1#L303 · CARRIED |
| TS-005 | `backend-go/**/*_test.go` | Integration tests với PostgreSQL thật và MQTT 5.0 Mosquitto broker/profile thật để chứng minh reconnect, QoS1 replay/expiry, transaction & state transitions. MUST test poison JSON/schema/version ⇒ log + dropped metric + PUBACK, transient DB failure ⇒ bounded retry và không ACK quá sớm, và race `STAGE_ACK`/`ACTIVE_REPORT` tới trước `SENT` update ⇒ trạng thái không lùi. | UNIT,CONTRACT,INTEGRATION | `FIX_OR_REPORT` | v1#L305 · CARRIED |
| TS-006 | `backend-go/**/*_test.go` | Simulations dùng để thăm dò thuật toán; không đánh dấu RF timing/HIL compliance `PASS`. | UNIT,CONTRACT,INTEGRATION | `FIX_OR_REPORT` | v1#L307 · CARRIED |
| TS-007 | `backend-go/**/*_test.go` | Không phụ thuộc network/public APIs không kiểm soát trong unit tests. Dùng fake clock/harness ở nơi có timing effects; không random flakiness. | UNIT,CONTRACT,INTEGRATION | `FIX_OR_REPORT` | v1#L309 · CARRIED |
| TS-008 | `backend-go/**/*_test.go` | Khi parsing payload không tin cậy, nên có fuzz tests của decoding/validation nếu giá trị risk phù hợp. | UNIT,CONTRACT,INTEGRATION | `FIX_OR_REPORT` | v1#L311 · CARRIED |
| TS-009 | `backend-go/**/*_test.go` | Concurrency code: test cancellation, shutdown, race, blocked queue, retry budget, goroutine leak. | UNIT,CONTRACT,INTEGRATION | `FIX_OR_REPORT` | v1#L313 · CARRIED |
| TS-010 | `backend-go/**/*_test.go` | Bug fix MUST kèm regression test tái hiện bug trước fix nếu khả thi. Không mock đến mức test chỉ xác minh implementation details. | UNIT,CONTRACT,INTEGRATION | `FIX_OR_REPORT` | v1#L315 · CARRIED |
| TS-011 | `backend-go/**/*_test.go` | Report chính xác `PASS`, `FAIL`, `PARTIAL_WITH_FINDINGS`, `NOT_VERIFIED`, kèm command/environment/commit và giới hạn. Không đánh đồng `go test` với integration hoặc RF/HIL pass. | UNIT,CONTRACT,INTEGRATION | `FIX_OR_REPORT` | v1#L317 · CARRIED |

### 2.12 QG — Quality Gates & Toolchain Pinning (QG-001..008)

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| QG-001 | `backend-go/**,.github/workflows/ci-backend.yml` | Khóa Go 1.27.3 tại `backend-go/go.mod` và `.go-version`; CI phải chọn chính xác `1.27.3`, đặt `GOTOOLCHAIN=local` và kiểm tra `go env GOVERSION = go1.27.3` trước các quality gates. Pin GolangCI-Lint và govulncheck versions tương thích sau khi đánh giá, không dùng `@latest` tự động trong CI. | BUILD,STATIC | `STOP_ON_EVIDENCE` | v1#L321 · CARRIED |
| QG-002 | `backend-go/**,.github/workflows/ci-backend.yml` | Exact Go 1.27.3 toolchain; run gofmt (check empty output), go vet, go test, go test -race where supported; run approved installed security/lint tools only; report unavailable tools NOT_RUN rather than PASS. | BUILD,STATIC | `STOP_ON_EVIDENCE` | v1#L323 · VARIANT |
| QG-003 | `backend-go/**,.github/workflows/ci-backend.yml` | CI fail khi unformatted Go, build/vet/test fail, critical security finding chưa được triage, contract test fail hoặc migration validation fail. `gofmt -l .` chỉ in tên file sai format và vẫn có thể exit 0; CI MUST assert stdout rỗng, ngoài việc kiểm tra exit code. Không tự kích hoạt lint rule hàng loạt gây false positives mà chưa chốt baseline. | BUILD,STATIC | `STOP_ON_EVIDENCE` | v1#L334 · CARRIED |
| QG-004 | `backend-go/**,.github/workflows/ci-backend.yml` | `go test ./...` với scaffold chỉ chứng minh package hiện tại test được; không chứng minh MQTT/DB/Scheduler/API hoạt động. | BUILD,STATIC | `STOP_ON_EVIDENCE` | v1#L336 · CARRIED |
| QG-005 | `backend-go/**,.github/workflows/ci-backend.yml` | Mọi test `PASS` cần exact command, runner/tool version và commit SHA; `NOT_RUN`/`NOT_VERIFIED` phải nói rõ. | BUILD,STATIC | `STOP_ON_EVIDENCE` | v1#L338 · CARRIED |
| QG-006 | `backend-go/**,.github/workflows/ci-backend.yml` | Coverage theo critical paths, không áp threshold phần trăm cố định thiếu threat/risk analysis; review test quality. | BUILD,STATIC | `STOP_ON_EVIDENCE` | v1#L340 · CARRIED |
| QG-007 | `backend-go/**,.github/workflows/ci-backend.yml` | CI theo PR + required human review; không mặc định branch protection đang bật. Không AI self-approve/self-merge. | BUILD,STATIC | `STOP_ON_EVIDENCE` | v1#L342 · CARRIED |
| QG-008 | `backend-go/**,.github/workflows/ci-backend.yml` | HIL/RF/latency/reliability pilot evidence vẫn quản lý ở `docs/verification/` và G0–G6; code-only lint/test không chứng minh chúng. | BUILD,STATIC | `STOP_ON_EVIDENCE` | v1#L344 · CARRIED |

### 2.13 AI — Agent Execution & Scope Discipline (AI-001..012)

| Rule ID | Scope | Directive | Verify | Failure Action | Source |
|---|---|---|---|---|---|
| AI-001 | `backend-go/**` | Preflight: Đọc Issue + Acceptance Criteria + Target Directories (allowed paths), branch, working tree, project scope, `AGENTS.md`, relevant v2 Rule IDs, requirements/ADR/contracts liên quan và code hiện hành. Với vertical slice mới, MUST kiểm tra composition root `backend-go/cmd/server/main.go` (AR-002): cần startup/wiring dependencies nào và đường dẫn đó đã có trong allowed paths chưa; nêu mọi path cần bổ sung trong small design proposal AI-003 trước khi viết code. (Preflight: inspect `backend-go/cmd/server/main.go` dependency wiring via `codegraph_explore` if available; identify Issue-scope gaps.) | AUDIT,ISSUE | `STOP_ON_SCOPE` | v1#L348 · CARRIED |
| AI-002 | `backend-go/**` | No out-of-scope writes: Chỉ sửa file trong allowlist Issue. Nếu cần test/doc/migration hoặc composition-root wiring tại `backend-go/cmd/server/main.go` ngoài scope → STOP, chỉ rõ file + lý do trong AI-003 và yêu cầu owner mở rộng Issue allowed paths trước khi viết. Nếu `main.go` đã được cho phép, chỉ thực hiện minimal dependency construction/startup wiring theo AR-002; không nhét business logic vào `main.go`. Không tự mở scope hoặc sửa contract ngầm. | AUDIT,ISSUE | `STOP_ON_SCOPE` | v1#L350 · CARRIED |
| AI-003 | `backend-go/**` | Small design proposal: Trước code, mô tả bằng 5–10 dòng: input/output, invariant, error paths, modules/files, tests, composition-root wiring/allowed path gap (AI-001/002). Nếu thiết kế thêm framework/new lib, phải chứng minh không có phương án đơn giản hơn và tuân GB-007. | AUDIT,ISSUE | `STOP_ON_SCOPE` | v1#L352 · CARRIED |
| AI-004 | `backend-go/**` | Implement smallest vertical slice: Một use case hoàn chỉnh, buildable, reviewable, được wire ở composition root khi được phép. Nếu blocked do path chưa approved, báo `BLOCKED_SCOPE` thay vì sửa file trái phép hoặc tự nhận slice đã chạy. Không sinh code placeholder ở 7 tầng và nói đã implement. | AUDIT,ISSUE | `STOP_ON_SCOPE` | v1#L354 · CARRIED |
| AI-005 | `backend-go/**` | Search before create: Tìm model, helper, schema, query đã có; reuse nếu đúng ownership. Không duplicate contracts hoặc business logic. (Before new symbols, use `codegraph_explore` to locate existing Go models/helpers/queries if available; graph does not index contract/Markdown.) | AUDIT,ISSUE | `STOP_ON_SCOPE` | v1#L356 · CARRIED |
| AI-006 | `backend-go/**` | Avoid invented APIs: Xác minh Go version, dependency versions, function signatures từ source/`go doc`; không phỏng đoán thư viện. | AUDIT,ISSUE | `STOP_ON_SCOPE` | v1#L358 · CARRIED |
| AI-007 | `backend-go/**` | Stable contracts: Không đổi MQTT topic, frame layout, API schema, SQL migration hoặc state semantics nếu chưa được yêu cầu, không tương thích hoặc chưa review. | AUDIT,ISSUE | `STOP_ON_SCOPE` | v1#L360 · CARRIED |
| AI-008 | `backend-go/**` | Test the change: Unit + boundary + contract + integration tương ứng; run bằng tool thật khi được phép. Chưa chạy phải khai báo `NOT_RUN`. | AUDIT,ISSUE | `STOP_ON_SCOPE` | v1#L362 · CARRIED |
| AI-009 | `backend-go/**` | Explain failures, don't hide: Nếu build/test fail, xác định command, root cause, scope và phương án; không xóa assertions/lint rules để được PASS. | AUDIT,ISSUE | `STOP_ON_SCOPE` | v1#L364 · CARRIED |
| AI-010 | `backend-go/**` | Self-review deletion pass: Loại bỏ unused imports, dead code, abstraction vô lý, duplicate validation, speculative generalization, redundant errors/logging, retry lồng và config không dùng. | AUDIT,ISSUE | `STOP_ON_SCOPE` | v1#L366 · CARRIED |
| AI-011 | `backend-go/**` | Git discipline: Feature branch có Issue, `git status`, `git diff --check`, secret scanning, conventional commit, PR liên kết Issue. Không force-push `main`, tự merge hoặc destructive operations. | AUDIT,ISSUE | `STOP_ON_SCOPE` | v1#L368 · CARRIED |
| AI-012 | `backend-go/**` | Honest final report: Báo files changed, scope/AC mapping, commands/results, risks, untested cases, contract/migration impacts, reviewer requirements, SHA nếu thật sự commit. Không ghi “đã build/test/push/merged” khi chưa làm. | AUDIT,ISSUE | `STOP_ON_SCOPE` | v1#L370 · CARRIED |

## 3. Known high-risk deltas / blocked decisions

| Identifier | Current fact vs v1 language | Required agent action |
|---|---|---|
| MQ-009 | v1 proposes `PROPOSED/SENT/STAGED → ACTIVE` upon `ACTIVE_REPORT`; currently Draft [MQTT semantics §4](../../../contracts/mqtt/semantic-rules.md) gives only `STAGED → ACTIVE`, and delayed EXPIRED handling is unspecified policy | `STOP_ON_CONTRACT`; do not implement silent `PROPOSED/SENT/EXPIRED → ACTIVE`; producer/consumer decision + versioned test required |
| MQ-003 | v1 proposes ACK-after-quarantine of malformed QoS1 and manual Paho callback ACK behavior | `STOP_ON_CONTRACT` for exact ack/retry/quarantine semantics; verify Paho API per pinned module version, broker trace and security policy |
| MQ-006/MQ-007 | Expiry interval, Retain=false, session/reconnect profiles are proposed contract details under MQTT5 owner-accepted version | Keep MQTT 5.0; do not treat all details as approved/implemented merely from ADR-0002 |
| DB-004 / SC-006 | DB CAS after reordered ACK is safety critical | No custom state advancement outside reviewed transition table; no DB+MQTT atomicity claim |
| GO-008 | v1 prescribes `%w` too broadly | Adopt Go-style conditional exposure vs translation; see `GGS-007` |
| GB-007 | v1 preferred dependencies are a DRAFT allowlist, not proven installed versions | No new package/toolchain upgrade without Issue scope + version/security/licence checks |
| API/WSS auth | D13 in `contracts/OPEN_DECISIONS.md` is still BLOCKED | No production token/credential lifecycle selection; preserve server-side RBAC |
| D01/D11 | Custom Radio MAC crypto and version/nonce rules BLOCKED | Backend code must not silently invent wire codec or represent RF CRC as authentication |

**Data and architecture invariant:** Backend Go is Modular Monolith + PostgreSQL + Mosquitto MQTT5; Gateway ESP32 SX1276 is local TDMA executor; no LoRaWAN stack, ChirpStack, Redis/InfluxDB/Kafka/microservices/extra ORM unless approved in a separate scope. `backend-go/go.mod` and root `.go-version` on baseline declare `1.27.3`; actual runtime/tool availability, module compatibility and build PASS require evidence. This standard does not approve arbitrary Go dependencies.

## 4. Agent verification/evidence contract (for every implementation Issue)

**Before coding report:** `ISSUE_URL`, `BASE_SHA`, `BRANCH`, `ISSUE_ALLOWED_PATHS`, `APPLICABLE_RULE_IDS`, `RULE_APPROVAL_STATUS`, `CONTRACT_CONFLICTS`, `BLOCKED_DECISIONS`, `TEST_PLAN`.

**After coding report:** `TASK_ID`, `ISSUE_URL`, `BASE_SHA`, `HEAD_SHA`, `BRANCH`, `CHANGED_PATHS`, `SCOPE_CHECK`, `RULE_IDS_CONSULTED`, `RULE_IDS_APPLIED`, `CONFLICTS_OR_EXCEPTIONS`, `BLOCKED_DECISIONS`, `TOOLCHAIN_VERSION`, `TEST_COMMANDS`, `TESTS_RUN`, `NOT_RUN`, `KNOWN_LIMITATIONS`, `EVIDENCE_STATUS`, `EVIDENCE_URLS`, `REVIEWERS_REQUIRED`, `PR_URL`, `FINAL_STATUS`.

Minimum deterministic checks (only with authorized environment, exact version and actual output):

```bash
git remote -v
git branch --show-current
git status --porcelain=v1
git rev-parse HEAD origin/main
cat .go-version
cat backend-go/go.mod
cd backend-go
go env GOVERSION GOTOOLCHAIN
gofmt -l .   # must assert STDOUT is empty; exit=0 alone is insufficient
go vet ./...
go test ./...
go test -race ./... # only when toolchain/host supports it
```

Use approved pinned `golangci-lint` and `govulncheck` only if configured/available; never invent versions or run floating `@latest`. Changes to schemas/migrations/contracts are **not** authorized by merely running this command list. For behavior involving DB uniqueness/transactions use actual PostgreSQL integration. For MQTT QoS1, expiry, reconnect and callback acknowledgment use actual Mosquitto/Paho integration. HTTP/RBAC/WSS behavior needs negative security tests. CI scaffold PASS ≠ service complete, RF/HIL/TDMA latency PASS, or G0–G6. No fabricated test artifacts.

**Evidence dimensions:** `DOC_STATIC`, `GOFMT`, `BUILD`, `UNIT`, `RACE`, `CONTRACT`, `DB_INTEGRATION`, `MQTT_INTEGRATION`, `SECURITY`, `E2E`, `RF`, `HIL` independently classified as `PASS / FAIL / NOT_RUN / NOT_VERIFIED`. Use exact SHA, Go/runtime/version, fixtures, environment, timestamps, expected/actual and logs for each reported PASS.

## 5. Adversarial AI Agent Conformance scenarios — DESIGN_ONLY / NOT_EXECUTED

Adversarial AI Agent conformance scenarios (BE-CASE-01..16) are maintained in [agent-conformance-scenarios.md](../../verification/agent-conformance-scenarios.md) for Harness/Evaluator grading (`DESIGN_ONLY / NOT_EXECUTED`). AI Workers must not load that file during normal implementation tasks.

