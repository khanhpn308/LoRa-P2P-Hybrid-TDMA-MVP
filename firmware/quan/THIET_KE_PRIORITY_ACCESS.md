# Priority Access — đóng góp thiết kế #78

**PROPOSED / NOT_VERIFIED.** Tài liệu cá nhân để review nhóm; không thay thế đầu ra chính thức `docs/architecture/event-only-priority-access-design.md`. Không triển khai MAC, wire format hoặc tham số RF.

## Yêu cầu, I/O và bất biến

Input: mode ON/OFF từng Node, bounded pending queues, priority/deadline/event identity, authenticated schedule/epoch, sync validity, radio state, airtime admission và retry count. Output: opportunity/deferral/denial, bounded retry hoặc terminal reason.

Preconditions: provisioning hợp lệ, mapping lịch xác thực, cơ hội phát hợp lệ, RF policy cho phép. Gateway là executor; Backend chỉ hoạch định. Bộ nhớ/thời gian: queue capacity, deadline, retry budget, backoff cap, fairness quota đều TBD theo ngân sách được duyệt.

Invariants: một radio half-duplex và một owner; không ngắt TX; mọi TX tính airtime; không periodic TX khi OFF; OFF vẫn có Alert/Beacon/Join/Control hợp lệ; không dùng stale schedule; không cấp app TX cho Node chưa active; CAD clear không chứng minh không collision. Không tuyên bố absolute priority hoặc latency vô hạn định.

## So sánh 3 phương án cho 10–15 Node

| Phương án | Collision/reliability | Latency và RF/energy | Fairness/failure | Độ phức tạp |
|---|---|---|---|---|
| A: CAD + randomized bounded backoff | Hidden terminal và false-free vẫn gây collision | Ít reservation khi tải thấp; nhiều CAD/retry khi burst | Retry cap/age cần chống starvation; burst 15 Node có thể mất event | Thấp–vừa |
| B: reserved priority opportunities | Giảm tranh chấp nếu grant rõ; request window vẫn collision | Có thời gian đợi window; idle reservation tốn tài nguyên | Phân lượt/grant quota dễ kiểm soát; stale schedule nguy hiểm | Vừa |
| C: hybrid reservation + dynamic reclaim | Tách request/grant/data nhưng cần xử lý ACK loss/epoch | Có thể tái dùng periodic slots khi OFF; thêm overhead control | Aging và quota giữ fairness; mất lịch cần fail closed | Cao |

Đề xuất C để review, dùng CAD/backoff hữu hạn tại request opportunities được duyệt. Không chọn con số cửa sổ, backoff, guard hay SLA; dependency #11/#12/#19 và D01–D05/D11 chưa được gỡ bằng đề xuất này. Nếu overhead/recovery quá lớn, so sánh lại B qua mô phỏng.

## Opportunities theo mode

| Tài nguyên | ON | OFF |
|---|---|---|
| Beacon/sync | Có theo thiết kế được duyệt | Vẫn giữ |
| Alert request/grant/data | Có, ưu tiên tại opportunity hợp lệ | Có |
| Periodic telemetry | Chỉ active slot được cấp | Không TX periodic |
| Join/Discovery | Cửa sổ riêng, bounded | Vẫn giữ, không tự cho app TX |
| Control/provisioning/ACK | Theo lịch/airtime | Vẫn giữ |

Reclaim chỉ hiệu lực sau version staging/activation hợp lệ; không xem một Node im lặng là đã OFF. Mạng mixed ON/OFF vẫn giữ slot của Node ON và mapping thống nhất.

## State machine

```text
UNPROVISIONED -> DISCOVERY -> PENDING_APPROVAL -> CONFIG_PENDING -> ACTIVE_UNSYNCED
ACTIVE_UNSYNCED --authenticated sync + valid schedule--> READY_ON / READY_OFF
READY_* --event--> QUEUED --eligible opportunity--> CAD_BACKOFF
CAD_BACKOFF --busy--> DEFERRED --within budget--> QUEUED
CAD_BACKOFF --clear + grant + airtime allowed--> TX_PENDING -> WAIT_ACK
WAIT_ACK --matching authenticated ACK--> COMPLETE -> READY_*
WAIT_ACK --timeout + retry allowed--> DEFERRED
WAIT_ACK --budget/expiry exhausted--> TERMINAL_FAILURE
any active --sync/epoch invalid--> ACTIVE_UNSYNCED
READY_* --new config staged--> MODE_PENDING --activation verified--> READY_NEW_MODE
```

Tách pending queue khỏi radio operation: loss-of-sync không xóa event đã chờ, nhưng chặn application TX. Discovery/rejoin tuân cơ chế riêng được duyệt. Reboot vô hiệu mapping cũ tới khi epoch/persistence được xác minh; không tạo identity/replay scheme mới trong thiết kế này.

## Pseudocode (không phải implementation)

```text
on event(event):
    validate activation and event metadata
    if queue full: apply reviewed bounded loss policy; count QUEUE_FULL
    else enqueue immutable event identity and bounded deadline

on allowed scheduling opportunity:
    if not active or authenticated sync/schedule invalid: return UNSYNCED
    if radio busy: return DEFER_RADIO_BUSY
    select eligible alert first; apply reviewed aging/quota among competing senders
    normal event precedes telemetry; control must retain required safety windows
    if mode OFF: exclude periodic telemetry
    if event expired: terminate EXPIRED
    if retry budget exhausted: terminate RETRY_EXHAUSTED
    if airtime denied: defer AIRTIME_DENIED until expiry, without transmitting
    if request opportunity requires CAD:
        if busy: bounded randomized backoff within permitted window; return DEFER_CAD
    validate grant, remaining window (TX + ACK + guards), sync and airtime again
    submit once to single Radio Owner; increment attempt only under reviewed semantics
    if submission rejected: count OWNER_REJECTED; preserve bounded deadline
    else await matching authenticated ACK with finite deadline

on ACK timeout:
    retain same logical event identity; never count retry as new event
    retry only at next permitted opportunity within retry/airtime/expiry budgets

on mode/schedule change:
    stage version and activation mapping; verify compatibility
    keep prior valid mapping until approved activation; do not reclaim early
    at activation: if new mapping missing/invalid, suppress application TX
    OFF cancels future periodic admission, never cancels alert/control readiness

on backhaul loss:
    gateway uses only still-valid local approved schedule; no indefinite renewal
    bounded storage with overflow counters; reconcile before accepting new schedule
```

Random source, retry counting, persistence/reboot identity, expiry, fairness quota và schedule activation cần owner quyết định trong contract, chưa tự freeze.

## Verification matrix — toàn bộ PLANNED

| Scenario | Expected invariant | Evidence cần có |
|---|---|---|
| 10–15 Node alert cùng lúc | Bounded retry/queue, grant không overlap | SIM traces; collision/loss, latency P50/P95/P99 |
| Mixed ON/OFF | OFF không periodic; Alert/Control còn hoạt động | SIM + contract cases + HIL |
| CAD false-free/hidden terminal | Không coi CAD là peer receipt; xử lý collision | SIM + RF |
| ACK loss/duplicate | Retry cùng event, không ACK nhầm epoch | UNIT/CONTRACT + integration/security |
| RF budget hết | Không phát dù Alert pending; reason rõ | UNIT + HIL |
| Beacon loss/stale epoch | Chặn app TX; recovery đúng contract | SIM + HIL/security |
| Switch ON/OFF giữa chu kỳ | Không reclaim sớm hoặc dùng slot cũ | CONTRACT/SIM + HIL |
| Burst liên tục từ một Node | Aging/quota hữu hạn, đo starvation | SIM fairness per node, max wait/drop |
| Reboot/mất backhaul/queue full | Không reset sai event identity; loss hữu hạn có log | Fault HIL + integration |

Simulation phải lưu seed, input workload, model/commit, ToA assumptions, raw traces, sample count và metric definitions. Chưa có mô phỏng chạy; không có PASS threshold hay số đo giả.

## Review và handoff

RF/HIL: assumptions ToA/guard/CAD; Embedded Node/Gateway: owner, bounded state và half-duplex; Backend Planner: version/activation/reclaim; Security: auth/replay/event identity. Quyết định từng reviewer: PENDING, chưa có APPROVE/REVISE. Chỉ chuyển Wave 2 sau duyệt; mọi sửa contract/ADR qua scope riêng.
