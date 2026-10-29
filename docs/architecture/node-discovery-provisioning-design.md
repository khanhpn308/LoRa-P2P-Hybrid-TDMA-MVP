# Onboarding Node có kiểm soát — đề xuất thiết kế tích hợp

**Issue:** [#79](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/79)
**Trạng thái:** `PROPOSED / NOT_VERIFIED`
**Phạm vi:** chỉ thiết kế; một Gateway và 10–15 Node trong mô hình star một hop.
**Review:** đang chờ review từ Node/Gateway/RF, Backend/API, Web/Mobile và Security. Tài liệu này ghi lại một đề xuất, không phải protocol hay implementation đã được phê duyệt.

## 1. Mục đích và ranh giới

Tài liệu này kết nối phần việc Node/Gateway trong [#90](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/90) với phần Backend/approval trong [#91](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/91). Cả hai issue thành phần hiện vẫn mở. Các tài liệu thiết kế riêng và bằng chứng cross-review của chúng chưa có trong repository; vì vậy, đề xuất tích hợp này không khẳng định các phần đó đã được chấp nhận và cũng không đóng issue cha.

Luồng đề xuất:

```mermaid
sequenceDiagram
    participant N as Node
    participant G as Gateway
    participant M as MQTT 5 Broker
    participant B as Backend
    participant U as Authorized User

    N->>G: Bounded Discovery attempt
    Note over N,G: Candidate exchange only; identity proof and RF format remain TBD
    G->>M: Report observed Discovery with stable event identity
    M->>B: QoS 1 delivery (duplicates possible)
    B->>B: Authenticate Gateway; deduplicate; create or update pending case
    U->>B: Review details; approve or reject (RBAC checked server-side)
    B->>B: Persist decision, actor, revision and audit record
    B->>M: Publish versioned, expiring provisioning command
    M->>G: Deliver command; broker ACK is transport evidence only
    G->>G: Validate identity, version, expiry, queue and local RF eligibility
    G->>N: Downlink at a locally selected eligible opportunity
    N->>G: RF ACK if defined by approved MAC; then apply and verify config
    N->>G: CONFIG_APPLIED bound to command and config revision
    G->>M: Forward correlated status
    M->>B: QoS 1 delivery (duplicates or reordering possible)
    B->>B: Verify trust proof, correlation, revision and current state
    B->>B: Mark ACTIVE only after all activation predicates pass
```

Gateway chịu trách nhiệm thực thi TDMA tại chỗ và quản lý radio half-duplex duy nhất. Backend chịu trách nhiệm approval, authorization, lifecycle record, ý định gửi command, expiry và đối soát trạng thái cuối. Backend không lập lịch từng RF slot. Web và Mobile gọi API Backend đã xác thực và nhận event từ Backend; chúng không truy cập trực tiếp MQTT hay PostgreSQL.

### Ranh giới tin cậy

`Device UID` là thuộc tính Discovery không đáng tin cậy, chỉ dùng làm gợi ý tra cứu. Nó không chứng minh danh tính, không cấp quyền tham gia và không phải đầu vào để tạo key, trừ khi một thiết kế riêng được phê duyệt cho phép rõ ràng. Approval của người dùng cho phép thực hiện nghiệp vụ nhưng không xác thực radio peer. Trước khi cấp credential production hoặc chuyển sang trạng thái `ACTIVE`, peer phải vượt qua cơ chế authentication, freshness và anti-replay được Security owner phê duyệt theo #12. Credential bootstrap, challenge, cryptographic suite, việc lưu nonce/counter, key rotation và quy tắc recovery cụ thể vẫn **TBD / BLOCKED**. Không dùng CRC, UID, MQTT TLS hay quan sát của Gateway thay cho xác thực Node.

## 2. Requirements, đầu vào, đầu ra và bất biến

### Đầu vào

- MQTT principal đã xác thực của Gateway và phạm vi Gateway mà principal đó được phép thao tác.
- Discovery observation: Device UID không đáng tin cậy, thời điểm/nguồn nhận, radio metadata được contract sau này cho phép, Gateway boot epoch, stable event ID và authentication result nếu có. Các trường RF và MQTT chính xác vẫn TBD.
- Thao tác người dùng đã xác thực, authorization context, record revision dự kiến, quyết định và idempotency key.
- Configuration snapshot đề xuất, application revision tăng đơn điệu, command ID, thời điểm tạo và expiry. Ngưỡng sensor, hysteresis/debounce, `periodic_enabled`, tham chiếu network/RF profile và validation policy là dữ liệu đầu vào, không phải giá trị do đề xuất này lựa chọn.
- Trạng thái/điều kiện của Gateway và phản hồi Node được correlation với command, configuration revision, authenticated session và Gateway identity.

### Đầu ra

- Lifecycle record bền vững ở trạng thái pending, rejected, provisioning, activating, active, expired, revoked hoặc recovery-required, kèm revision và audit history.
- Ý định command có giới hạn và expiry, gửi đến đúng ngữ cảnh Gateway/Node; dispatch và thực thi radio là hai quan sát riêng biệt.
- Tiến độ hiển thị cho người dùng dựa trên trạng thái Backend đã lưu, không dựa trên việc broker chuyển tin hay ACK không có correlation.
- Metrics và reason code cho deduplication, expiry, retry, queue overflow, phản hồi không hợp lệ/cũ và recovery. Không ghi secret hoặc dữ liệu credential thô vào log.

### Bất biến

1. `RF_ACK ≠ CONFIG_APPLIED ≠ ACTIVE`.
2. PUBACK của broker hoặc kết quả publish từ Gateway không chứng minh Node đã nhận hay áp dụng cấu hình.
3. `ACTIVE` yêu cầu status Node đã xác thực, gắn với command được duyệt hiện tại, configuration revision, Node record dự kiến và trust session chưa bị revoke. Thiếu bằng chứng thì phải từ chối an toàn (fail closed).
4. Mọi approval/command/state transition phải idempotent khi nhận bản tin trùng lặp và được bảo vệ khỏi ghi revision cũ. Hai quyết định đồng thời không thể cùng thắng trên một pending revision.
5. Ý định đã hết hạn, bị thay thế, bị reject hoặc revoke không được áp dụng mới. Phản hồi đến muộn phải được đối soát và audit; không được làm trạng thái lùi lại một cách mù quáng hoặc nâng một yêu cầu hết hạn lên trạng thái cao hơn.
6. Số lần retry, queue capacity, lịch sử event lưu giữ và thời gian chờ đều hữu hạn. Giới hạn số lượng và thời gian vẫn TBD, chờ contract được duyệt, giới hạn RF được đo và owner review.
7. Gateway chỉ được truyền khi kiểm tra MAC/TDMA tại chỗ, half-duplex, airtime và priority cho phép. Backend không chọn thời điểm RF.
8. Discovery trùng lặp hoặc QoS 1 redelivery không được tạo Node record, approval, command hay audit action trùng.
9. Reboot không được tự nâng cấu hình chưa chắc chắn hoặc mới áp dụng một phần thành active. Recovery phải xác minh lại revision bền vững, expiry và bằng chứng authentication.
10. Discovery input không đáng tin cậy không được cấp phát queue, pending case, dedup hay audit storage vô hạn. Quy tắc admission theo Gateway, thời gian lưu pending và xử lý overflow phải hữu hạn và được duyệt; giới hạn cụ thể vẫn TBD.

## 3. State machine

### Node (mang tính khái niệm; trạng thái xác thực cụ thể phụ thuộc #12)

| Trạng thái | Event / guard | Trạng thái tiếp theo và hành động |
|---|---|---|
| `UNPROVISIONED` | Boot; radio/profile tại chỗ cho phép Discovery | `DISCOVERY_BACKOFF`; khởi tạo counter có giới hạn, không tự tạo persistent identity hay production key. |
| `DISCOVERY_BACKOFF` | Hết backoff và vẫn còn lượt thử | `DISCOVERY_TX`; gửi một lần Discovery được phép. |
| `DISCOVERY_TX` | TX hoàn tất | `DISCOVERY_RX_WINDOW`; chỉ nghe trong receive opportunity có giới hạn theo chính sách MAC đã duyệt. |
| `DISCOVERY_RX_WINDOW` | Không có phản hồi hợp lệ | `DISCOVERY_BACKOFF`; retry có giới hạn với delay ngẫu nhiên. Hết lượt thì vào `RETRY_WAIT` cho đến điều kiện quay lại hữu hạn. |
| `DISCOVERY_RX_WINDOW` | Nhận phản hồi ứng viên | Kiểm tra length/type/version, destination, freshness và authentication đã duyệt trước khi chấp nhận; nếu không đạt thì loại bỏ và đếm reason. Chỉ UID là không đủ. |
| `PROVISIONING` | Nhận command đã xác thực, có correlation và chưa hết hạn | Xác thực toàn bộ cấu hình theo tính nguyên tử; từ chối revision/field không hỗ trợ, không áp dụng một phần. |
| `PROVISIONING` | Cấu hình đã áp dụng và kiểm tra read-back/consistency đạt | Lưu applied revision an toàn, sau đó gửi `CONFIG_APPLIED` đã xác thực và correlation với command/session. Chờ Backend quyết định activation; Node không tự tuyên bố Backend `ACTIVE`. |
| Bất kỳ trạng thái đã provision nào | Reboot, persistence hỏng, rollback, replay hoặc validation thất bại | `RECOVERY_REQUIRED`; không nhận là active hoặc truyền theo profile chưa xác minh. Thực hiện recovery/rejoin policy đang TBD. |
| Bất kỳ trạng thái nào | Nhận revoke/reject đã xác thực hoặc trust failure | `QUARANTINED` / safe state; loại bỏ công việc hết hạn và yêu cầu recovery đã duyệt. |

`DISCOVERING`, `PENDING_APPROVAL` và `ACTIVE` trong lifecycle cha là khái niệm cấp network. Node không thể suy ra Backend đã approve hay activate chỉ vì nó gửi Discovery hoặc nhận RF ACK.

### Gateway

Với việc chuyển observation: `READY → DISCOVERY_OBSERVED → REPORT_PENDING → REPORTED`. Khử trùng lặp trong giới hạn dựa trên stable Discovery/event identity được xác định sau này và authenticated Gateway epoch; giữ nguyên event ID khi retry. Cần dự kiến QoS 1 có bản trùng. Nếu mất backhaul, chỉ buffer trong giới hạn đã duyệt và báo counter overflow/drop; không tự quyết định approval tại chỗ.

Với command: `NOT_SEEN → QUEUED → ELIGIBLE → TX_ATTEMPTED → DELIVERY_UNKNOWN | NODE_ACKED → CONFIG_APPLIED_REPORTED`. Mỗi transition gắn với command ID/revision và expiry. Command bị queue đầy, hết hạn, sai Gateway, revision cũ hoặc radio tại chỗ không đủ điều kiện phải bị từ chối kèm reason có thể quan sát. `TX_ATTEMPTED` không chứng minh đã chuyển đến nơi nhận. Gateway chỉ lập lịch thử truyền tại chỗ sau khi kiểm tra TDMA hiện tại, half-duplex, airtime policy và Priority Alert policy. Nếu chưa có cơ hội phù hợp trước expiry thì chuyển `EXPIRED` hoặc `DELIVERY_UNKNOWN` theo quyết định contract, không được ghi đè lịch slot.

### Backend

`PENDING_APPROVAL → PROVISIONING → ACTIVATING → ACTIVE`, cùng các nhánh/trạng thái kết thúc `REJECTED`, `EXPIRED`, `REVOKED` và `RECOVERY_REQUIRED`. Node đã đăng ký nhưng mất kết nối vẫn là Node hiện hữu có connectivity status; không âm thầm quay lại quy trình onboarding thiết bị mới. Chính sách rejoin/replacement/factory-reset theo #12 vẫn TBD và phải phân biệt các tình huống này.

| Transition | Guard/bằng chứng bắt buộc |
|---|---|
| Discovery → `PENDING_APPROVAL` | Gateway principal đã xác thực và đúng scope; event hợp lệ, có giới hạn; identity hint đã khử trùng lặp. Danh tính Node vẫn chưa xác minh. Đối soát record hiện có, không tạo bản trùng. |
| Approve → `PROVISIONING` | Đúng role/resource scope; record revision dự kiến khớp; record chưa bị reject/revoke/expire; lưu nguyên tử action, actor audit cùng command intent và immutable config snapshot. |
| Reject → `REJECTED` | Cùng kiểm tra authorization phía server và revision; lưu bền vững reason category và audit. Approval trùng đến sau không thể ghi đè. Xem xét lại phải tạo revision mới có audit theo policy. |
| Dispatch accepted → `ACTIVATING` | Command intent hợp lệ đã được lưu và chuyển sang delivery workflow. Trạng thái này không có nghĩa Gateway đã nhận command. |
| `ACTIVATING` → `ACTIVE` | `CONFIG_APPLIED` đã xác thực chứng minh đúng command ID hiện tại, Node context, config revision và trust session; command chưa hết hạn/revoke; chưa bị revision mới thay thế; transition được lưu nguyên tử và audit. |
| Bất kỳ trạng thái pending nào → `EXPIRED` | Trusted time xác nhận TTL approval/command tương ứng đã hết. Cách xử lý expiry và sai số clock cho phép vẫn TBD. |
| Active → `REVOKED` / recovery | Revocation được cấp quyền hoặc mất trust đã xác minh; audit bền vững; command downstream có giới hạn và Gateway tại chỗ vẫn quyết định cơ hội truyền. Không thể cam kết revocation từ xa có hiệu lực tức thì khi offline. |

## 4. Thuật toán ứng viên và đề xuất lựa chọn

Các timer, retry cap, airtime budget, queue size, độ dài receive-window và priority policy được để ở dạng ký hiệu cho đến khi RF/MAC owners phê duyệt và đo đạc. Mọi implementation phải đặt giá trị hữu hạn đã duyệt; `TBD` không phải là quyền dùng giá trị mặc định vô hạn.

### Các phương án Discovery và receive-window

| Phương án | Cách hoạt động | Tính đúng đắn / bảo mật | Độ tin cậy / độ phức tạp | Airtime, độ trễ và tài nguyên | Đánh giá |
|---|---|---|---|---|---|
| A. Rendezvous request-response có giới hạn | Node gửi Discovery rồi mở RX window hữu hạn. Gateway chỉ phản hồi trong cơ hội đó nếu đã xác thực/đủ điều kiện theo MAC được duyệt; nếu không thì xếp công việc cho cơ hội sau. Retry dùng randomized backoff có cap và số lượt hữu hạn. | Correlation đơn giản, phản hồi nhanh. Vẫn cần challenge xác thực và chống replay; không được provision chỉ dựa trên UID. | Mất phản hồi thì thử lại ở lượt hữu hạn sau; độ tin cậy phụ thuộc retry và giả định kênh đã duyệt. Độ phức tạp vừa phải: RX theo lượt, correlation, dedup và queue state. | Độ trễ kỳ vọng thấp nếu kịp window; Node tốn một RX interval giới hạn mỗi lượt. Số lần thử và queue đều hữu hạn. | **Đề xuất ưu tiên** để đánh giá tính khả thi MVP, phụ thuộc RF timing/airtime và phê duyệt #12. Tài liệu này không chọn giá trị window hay bố trí RF cụ thể. |
| B. Rendezvous window theo lịch | Node nghe tại join opportunity lặp lại đã được thông báo; Gateway chỉ truyền trong các thời điểm đó; Node thử lại ở opportunity sau. | Admission tập trung và phân tích collision dễ hơn nếu có schedule đáng tin cậy. Node mới chưa đồng bộ cần bootstrap rendezvous an toàn; schedule cũ và replay phải bị fail closed. | Lặp lại qua nhiều opportunity có thể chịu được việc bỏ lỡ một window, nhưng recovery phụ thuộc schedule còn liên tục và hợp lệ. Phức tạp hơn: lấy schedule, thông báo, xử lý bỏ lỡ và schedule cũ. | Có thể giảm công RX lặp lại nhưng tăng thời gian chờ dịch vụ, đồng thời cần hỗ trợ MAC schedule/security chưa được duyệt. | Là phương án khả thi; chưa thể chọn đến khi thẩm quyền join-window và bootstrap timing được thiết kế trong #12/#90. |

### Các phương án provisioning và xác nhận

| Phương án | Cách hoạt động | Tính đúng đắn / độ tin cậy | Độ trễ, airtime, tài nguyên và độ phức tạp |
|---|---|---|---|
| 1. Gửi command ngay trong RX window sau Discovery | Command Backend đã sẵn sàng và chưa hết hạn; Gateway gửi trong receive opportunity giới hạn hiện tại của Node. | Correlation trực tiếp; nếu lỡ hoặc không rõ kết quả truyền thì giữ trạng thái unknown và đối soát, tuyệt đối không suy ra đã áp dụng. Chịu lỗi kém hơn khi lỡ window hoặc mất kết nối tạm thời. | Độ trễ kỳ vọng thấp nhất; tận dụng RX opportunity đang mở. Tăng tranh chấp scheduler và phụ thuộc thời điểm approval; vẫn cần dedup state hữu hạn. |
| 2. Store-and-forward tại rendezvous đã xác thực kế tiếp | Gateway lưu command bất biến có giới hạn; Node check-in/lắng nghe tại opportunity đã duyệt sau đó; chỉ retry khi chưa hết expiry và còn lượt hữu hạn. | Chịu được mất kết nối Backend/Gateway/Node tốt hơn khi command còn hiệu lực; độ tin cậy vẫn bị giới hạn bởi queue/retry hữu hạn và expiry, không thể đảm bảo khi outage vô hạn. | Độ trễ và mức dùng storage/queue cao hơn; lifecycle phức tạp hơn do dedup, expiry, supersession và reboot recovery. |

**Cách kết hợp đề xuất:** dùng Phương án 1 khi RX window hiện tại của Node và kiểm tra tại chỗ của Gateway cho phép; nếu không thì dùng Phương án 2. Mỗi Node context chỉ giữ một command active, trừ khi contract được duyệt quy định cách gộp an toàn. Cấu hình mới được approve sẽ thay thế công việc cũ chưa gửi; command đã thử gửi phải được đối soát bằng correlation và revision, không được mặc định là đã áp dụng. Đây là đề xuất, cần #90/#91 đồng thuận.

## 5. Pseudocode Backend và Gateway

Pseudocode quy định thứ tự và bất biến, không quy định database schema, API name hay wire field.

```text
on_discovery(event, authenticated_gateway):
    require gateway_scope_allows(authenticated_gateway, event.gateway_context)
    require bounded_valid_envelope(event)
    if per_gateway_admission_limit_reached(authenticated_gateway):
        ghi metric drop/abuse tổng hợp có giới hạn; không cấp phát case mới
        return rate_limited_result
    if event.id already recorded for gateway epoch:
        return previously_recorded_result
    record observation idempotently
    if no approved authenticated Node identity can be established:
        upsert pending case by untrusted UID hint + reviewable observation identity
        apply approved pending-case retention and queue limits
        do not create credentials or mark identity verified
    else:
        reconcile with existing Node record; do not create a second identity
    emit backend-owned pending-state event after durable commit

decide_onboarding(actor, case_id, expected_revision, decision, idempotency_key):
    require backend_RBAC_and_resource_scope(actor, decision, case_id)
    require valid idempotency_key and canonical_request_fingerprint
    begin transaction
        trả kết quả trước đó nếu key và fingerprint giống nhau
        từ chối do conflict nếu cùng key nhưng fingerprint khác
        lock hoặc compare-and-swap case tại expected_revision
        từ chối nếu case cũ, hết hạn, đã kết thúc hoặc không còn đủ điều kiện
        thêm actor/action/time/reason vào audit
        if decision == REJECT:
            lưu bền vững trạng thái REJECTED và revision
        else:
            xác thực config theo profile đã duyệt và giới hạn policy còn TBD
            tạo config snapshot bất biến, revision tăng đơn điệu,
                command_id duy nhất, expires_at hữu hạn và dispatch intent bền vững
            lưu nguyên tử trạng thái PROVISIONING, audit và outbox intent
    commit
    trả về trạng thái hiện được lưu (không khẳng định đã chuyển qua radio)

dispatch(command):
    nếu command hết hạn, bị thay thế, reject hoặc revoke: đánh dấu kết thúc; dừng
    chỉ publish đến route Gateway đã xác thực theo MQTT contract được duyệt
    khi dùng MQTT 5, Message Expiry phải phù hợp với application TTL còn lại
    không đánh dấu Node đã nhận/áp dụng chỉ dựa vào PUBACK của broker
    ghi kết quả publish; publish trùng giữ nguyên command_id và payload identity

gateway_receive(command, local_radio_state):
    xác thực route Backend và Gateway identity
    từ chối sai Gateway, revision không hợp lệ, command hết hạn/cũ hoặc queue overflow
    khử trùng lặp theo command_id và immutable payload fingerprint
    đưa vào queue trong giới hạn đã duyệt
    khi có receive opportunity cho Node:
        if local TDMA, half-duplex, airtime, priority and expiry checks pass:
            thử TX; chỉ ghi TX_ATTEMPTED / chưa chắc đã chuyển đến nơi nhận
        else:
            giữ đến opportunity đủ điều kiện kế tiếp hoặc expiry hữu hạn

on_config_applied(status):
    xác thực nguồn theo quy tắc trust/session đã duyệt trong #12
    khử trùng lặp stable event identity; từ chối replay và revision sai định dạng/cũ
    require status.command_id, node context, config_revision and trust session
        match current ACTIVATING record and immutable command snapshot
    kiểm tra lại trong transaction rằng chưa hết hạn/revoke/bị thay thế và revision khớp
    lưu nguyên tử status evidence, transition sang ACTIVE và audit
    nếu không đạt, giữ nguyên trạng thái và ghi reason có giới hạn để đối soát
```

### Quy tắc retry hữu hạn và recovery

- Discovery dừng retry khi đạt `MAX_DISCOVERY_ATTEMPTS` đã duyệt; delay ngẫu nhiên bị giới hạn bởi bound đã duyệt. Hết lượt thì vào trạng thái chờ yên lặng, không truyền liên tục.
- Gateway retry report với cùng stable event ID theo chính sách storage/retry có giới hạn. QoS 1 delivery trùng là an toàn. Overflow phải quan sát được và không được giả tạo report bị thiếu.
- Command retry dùng lại cùng command ID và snapshot chính xác. Chỉ retry khi chưa hết hạn, chưa bị thay/revoke, còn trong attempt/queue limit và tại opportunity hợp lệ do Gateway chọn. Giới hạn cụ thể TBD.
- Backend timeout không có nghĩa command đã áp dụng hoặc Node đã active. Ghi `DELIVERY_UNKNOWN`/`RECOVERY_REQUIRED`, đối soát report đến sau và không tạo command mới trừ khi cần quyết định/revision mới có audit.
- Khi reboot, Node và Gateway chỉ khôi phục revision/session continuity đã lưu và kiểm tra integrity. Persistence không chắc chắn, counter rollback, expiry mơ hồ hoặc mất continuity danh tính phải fail closed và theo quy trình rejoin/recovery đã duyệt.

## 6. Ma trận tác động đến contract và giao diện người dùng

Trạng thái dưới đây phản ánh tài liệu trong repository và tình trạng issue tại thời điểm thiết kế. Issue đã đóng không tự nó đồng nghĩa contract được duyệt: artifact #14 và #15 vẫn ghi các interface liên quan là draft/proposed và đang chờ review.

| Ranh giới | Baseline hiện có | Khoảng trống onboarding / follow-up đề xuất |
|---|---|---|
| RF / Radio MAC (#12) | `contracts/radio-mac/specification.md` mô tả candidate `JOIN_SLOT_REQ/RSP` và `CMD_DOWNLINK`; tài liệu nói rõ wire layout/security chưa được freeze. Issue #12 đang OPEN; D01/D11 chặn quyết định authentication, replay và version. | So sánh nhãn đề xuất `JOIN_DISCOVERY`, `CMD_DOWNLINK`, `PROVISION_STATUS` với `JOIN_SLOT_REQ/RSP` ứng viên; xác định join semantics hiện có có thể bao hàm Discovery và response hay không. Chỉ định nghĩa correlation cho command đã xác thực và semantics `CONFIG_APPLIED` sau review. Ở đây không gán message code, byte layout, key, nonce hay RF timing. Tạo/mở rộng quyết định trong #12/#90 với scope riêng sau Security/RF review. |
| MQTT (#14) | Root chuẩn `iot/v1/gw/{gateway_id}`, QoS 1, stable ID cấp ứng dụng, `downlink/command`, `uplink/command-ack`; MQTT 5.0 được owner chấp nhận, nhưng `topics.md` ở trạng thái `0.1.0-draft / PENDING CROSS-TEAM REVIEW`. Issue #14 đã CLOSED. Broker PUBACK không phải bằng chứng ở cấp ứng dụng; client không truy cập broker trực tiếp. | Bổ sung semantics cho Discovery report đã xác thực và provisioning status, correlation/revision/expiry/error field, dedup retention và authorization route. Topic/schema và retention chính xác là thay đổi contract, không được định nghĩa trong thiết kế này. Theo dõi bằng follow-up contract issue; xử lý duplicate, reorder và giao nhận offline. |
| REST (#15) | OpenAPI và semantics đang DRAFT/PENDING. Semantics đề xuất RBAC phía server, idempotency key và 202 biểu thị ý định đã xếp hàng cho ví dụ schedule/command hiện có; chưa có onboarding endpoint nào được duyệt. Issue #15 đã CLOSED. | Đề xuất API đọc danh sách/chi tiết pending, approve/reject và tiến độ; định nghĩa RBAC theo resource, expected revision, idempotency, lỗi conflict/expiry và khả năng xem audit. Endpoint, field và role matrix cụ thể cần Backend/API review. |
| WebSocket (#15) | WSS envelope/schema còn draft; server authorization, thứ tự event/reconnect và state reconciliation vẫn ở dạng đề xuất. | Đề xuất event trạng thái onboarding từ Backend với stable ID/revision; khi reconnect UI phải refresh bằng REST và xử lý event trùng/sai thứ tự. Không xem việc nhận WSS là bằng chứng RF/application. |
| Web / Mobile | Issue này chưa thiết lập contract màn hình onboarding nào được duyệt. | Hàng đợi pending, chi tiết Node/bằng chứng trust, approve/reject, reason, review config và màn hình tiến độ/lỗi/recovery. UI nên chặn gửi trùng để dễ dùng, nhưng Backend phải thực thi authorization/idempotency. UI phải phân biệt “command đã xếp hàng”, “Gateway đã thử gửi”, “Node đã áp dụng” và “active”. |
| Database / storage (#18) | Công việc PostgreSQL ingestion/idempotency được theo dõi riêng; thiết kế này không duyệt schema onboarding. | Lưu Node identity/trust state, observation, approval audit, config revision bất biến, command lifecycle, correlation và dedup key với retention hữu hạn. Định nghĩa uniqueness/transaction/outbox constraint trong issue migration riêng. Không thay đổi schema hay migration ở đây. |
| TLS / ACL (#16) | Identity và ACL của broker local thuộc Issue #16 đang OPEN; Gateway principal phải gắn với Gateway scope được cấp quyền. | Đảm bảo chỉ Gateway đã xác thực mới gửi report và nhận downlink của chính nó; API auth Backend và user RBAC độc lập với broker ACL. Thiết kế này không xác lập TLS/credential assurance production. |
| Planner / local TDMA (#19) | Issue #19 đang OPEN. ADR-0001 giao việc thực thi slot tại chỗ cho Gateway; MQTT/Backend không được định thời từng RF slot. | Phối hợp điều kiện command với schedule tại chỗ, half-duplex, airtime và Priority Alert policy. #19 có thể cung cấp metadata opportunity trong tương lai, nhưng onboarding không được phụ thuộc thời điểm slot do Backend quyết định. |

### Đề xuất workflow cho người dùng

1. Danh sách pending hiển thị provenance lần đầu/cuối thấy, UID hint chưa xác minh, Gateway, số lần trùng, trạng thái authentication và cờ rủi ro; ẩn dữ liệu nhạy cảm.
2. Màn hình chi tiết trình bày riêng trust/authentication evidence và nhãn do operator nhập. Người approve xem configuration snapshot có version và expiry.
3. Approve/reject cần Backend authorization và expected revision. Reject cần reason category có audit; chỉnh sửa sau approval tạo revision review mới.
4. Màn hình tiến độ dùng Backend state và timestamp rõ ràng, thể hiện unknown/offline/expired/recovery. Không bao giờ hiển thị radio ACK là “đã kích hoạt”.
5. Khi kết nối lại, client lấy snapshot REST và đối soát WSS event đã buffer theo object revision; WSS chỉ là best effort.

## 7. Failure trace và kế hoạch verification

Tất cả các dòng dưới đây là **kế hoạch kiểm thử**, không phải bằng chứng đã thực thi. Kết quả mong đợi giả định các contract security và interface sẽ được phê duyệt sau này. Không khẳng định đã chạy RF, HIL hay end-to-end.

| Tình huống | Kết quả mong đợi / bất biến | Mức bằng chứng dự kiến |
|---|---|---|
| Approve và apply bình thường | Một pending case; approval hợp lệ tạo đúng một command bất biến; Gateway chỉ gửi tại opportunity hợp lệ tại chỗ; `CONFIG_APPLIED` đã xác thực và correlation đưa Backend sang `ACTIVE`. | Unit + contract + integration; sau đó HIL/RF/security trước deployment. |
| Reject | Audit ghi actor/revision/reason; không phát provisioning command; approval trùng không thể ghi đè reject. | Backend unit/API contract + RBAC integration. |
| Discovery/status/command ACK QoS 1 bị trùng | Stable ID và idempotency trả kết quả cũ; không tạo Node, command hay audit transition trùng. | MQTT contract + storage integration. |
| Hai approver xử lý đồng thời | Chỉ một compare-and-swap theo expected revision thành công; bên kia nhận conflict/trạng thái hiện tại; chỉ có một command intent. | Backend concurrency/unit + DB integration. |
| UID giả, pending queue quá tải hoặc JOIN bị replay | UID vẫn không đáng tin cậy; proof thiếu/sai bị quarantine/reject; không cấp credential/cấu hình/ACTIVE. Admission theo Gateway và pending retention có giới hạn, có counter overflow/abuse. Replay bị từ chối theo session/counter policy đã duyệt. | Security negative test + RF simulator + bounded-load test; crypto policy production và giới hạn số vẫn TBD. |
| Node bỏ lỡ RX / Gateway offline | Command được giữ trong giới hạn và chưa hết hạn hoặc bị expire; chỉ retry tại opportunity phù hợp sau đó; không có lệnh slot từ Backend và không ACTIVE. | State-machine simulation + MQTT integration; sau đó HIL/RF. |
| Command/approval hết hạn hoặc bị thay thế | Gateway và Backend từ chối công việc cũ; phản hồi muộn được audit, không thể nâng trạng thái; revision mới vẫn hiện hành. | Unit + contract boundary-time test + integration. |
| RF ACK bị mất, trùng hoặc đến sau reboot | RF ACK chỉ cập nhật bằng chứng đã nhận nếu có authentication/correlation; config status được dedup độc lập; thiếu proof thì giữ ACTIVATING/unknown. | MAC contract + simulator/HIL fault injection. |
| Node reboot giữa lúc apply | Chính sách cấu hình/persistence nguyên tử chỉ cho ra revision trước đó đã xác minh hoặc recovery-required; không bao giờ coi cấu hình một phần là ACTIVE. | Node unit + power-fault HIL + security review. |
| Gateway queue đầy / cạnh tranh với Priority Alert | Từ chối/defer có reason; policy tại chỗ vẫn có thẩm quyền; không cấp phát memory vô hạn hoặc bypass priority. | Gateway unit/simulation + airtime/TDMA analysis. |
| Backend/MQTT ngắt rồi kết nối lại | Event/command identity bền vững được đối soát; công việc hết hạn không bị replay; event trùng không nhân đôi state. | Integration fault injection; cần persistence receipt. |
| WSS trùng/sai thứ tự/reconnect | UI không rollback revision mới hơn; REST snapshot khôi phục trạng thái hiện tại; UI event không cấp quyền hay kích hoạt. | API/WSS contract tests + Web/Mobile integration. |

Khi profile liên quan được duyệt, cần đo: số lần Discovery và airtime theo state, RX duty/energy, phân bố collision/retry, queue high-water/overflow, timestamp các stage end-to-end, số lần từ chối stale/replay và thời gian ở từng Backend state. Ngưỡng acceptance vẫn TBD; không tự đặt mục tiêu latency hoặc RF.

## 8. Quyết định, reviewer và bàn giao

### Quyết định còn mở / blocker

- **D01 / #12:** RF envelope đã xác thực, bootstrap identity/challenge, anti-replay và key/session provisioning đang BLOCKED; chưa thể hoàn thiện luồng credential production.
- **D11 / #12:** epoch/version đã xác thực và correlation command/config đơn điệu qua reboot/rollover đang BLOCKED.
- **D13 / #15/security:** production user authentication/token lifecycle đang BLOCKED; mô tả bearer API chỉ là tạm thời. Backend vẫn phải thực thi RBAC phía server.
- **#14:** MQTT 5.0 được owner chấp nhận, nhưng onboarding schema/topic và phê duyệt contract cross-team liên quan vẫn đang chờ.
- **#15:** onboarding REST/WSS endpoint/event, thời hạn lưu idempotency và UI event reconciliation cần thay đổi contract có scope riêng và consumer review.
- **#16:** thiết kế này chưa xác lập TLS/ACL triển khai hay credential assurance.
- **#18:** durable transaction/outbox, database schema và retention/uniqueness cần issue riêng.
- **#19 / Gateway/RF:** điều kiện tại chỗ, join receive opportunity, phân xử airtime/priority, timing và giá trị retry/TTL/queue cần owner thiết kế và cung cấp bằng chứng.
- Thiết kế thành phần #90 và #91 cùng đồng thuận cross-team về Discovery identity, correlation ID, RX window, expiry và status semantics vẫn còn thiếu.

### Biên bản review

| Phạm vi review | Reviewer bắt buộc | Quyết định / bằng chứng |
|---|---|---|
| Node/Gateway/RF/MAC | Owner #90 @khanhpn308; technical owner RF/MAC và Gateway/Node | `PENDING`; chưa có bằng chứng phê duyệt. |
| Backend/API/storage | Owner #91 @ngojames91-glitch; Backend/API owner | `PENDING`; chưa có bằng chứng phê duyệt. |
| Web/Mobile | Web và Mobile owners | `PENDING`; chưa có bằng chứng phê duyệt. |
| Security | Security owner có thẩm quyền theo #12/#16 | `PENDING / BLOCKED` về bootstrap identity, replay và credential production. |
| Cross-review tích hợp | Owner #90 ↔ #91 và parent coordinator | `PENDING`; chưa thống nhất correlation, RX/Downlink, TTL/version và ACK semantics. |

Mỗi review cần kết luận `APPROVE / REVISE / BLOCKED`, kèm reviewer identity, ngày, revision tài liệu chính xác, findings và issue follow-up. Đề xuất này chưa ghi nhận phê duyệt nào trong số đó.

### Các hạng mục bàn giao tiềm năng cho Wave 2

Sau khi owner liên quan duyệt thiết kế này, tạo issue có scope riêng cho: thông điệp onboarding RF/MAC đã xác thực và golden vector; MQTT Discovery/provisioning schema và semantics; REST/WSS contract onboarding và UI; Backend storage/idempotency/audit bền vững; implementation Gateway/Node cùng verification bằng simulation/HIL/RF/security. Mỗi issue cần nêu path chính xác, producer/consumer reviewer và bằng chứng cần có. Tài liệu này không tạo issue đó và không sửa contract.

## 9. Bằng chứng và kết luận

Artifact này chỉ là đề xuất thiết kế. Nó không chứng minh tính tương thích, phê duyệt security, implementation, JOIN thành công, hành vi HIL/RF hay latency. Issue cha vẫn chưa hoàn tất cho đến khi nội dung #90/#91 được tích hợp, cross-review và Security review được ghi nhận, các thay đổi contract còn mở được theo dõi và human reviewer bắt buộc đưa ra quyết định `APPROVE`.
