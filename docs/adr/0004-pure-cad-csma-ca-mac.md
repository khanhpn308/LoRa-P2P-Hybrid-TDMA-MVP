# ADR 0004: Chuyển đổi toàn diện từ Hybrid TDMA sang Pure Event-Driven CAD + Random Backoff (CSMA/CA) kết hợp Gateway Continuous RX 24/7

- **Design status:** `OWNER_APPROVED_DESIGN` · Quyết định Project Owner chính thức tại [Issue #273](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/273) (2026-11-09).
- **Thẩm quyền kiến trúc (Authority):** Project Owner phê duyệt; làm căn cứ kỹ thuật tối cao bãi bỏ mô hình phân chia khe thời gian TDMA và thiết lập kiến trúc truy cập vô tuyến MAC V2 mới.
- **Thay thế và bãi bỏ (Supersedes):**
  - [ADR-0001: Hybrid TDMA](0001-hybrid-tdma.md) (Quyết định DEC-0001).
  - Khung ngân sách bảo vệ và khe TDMA lý thuyết trong [0004-theoretical-timing-guard-budget.md](0004-theoretical-timing-guard-budget.md).
  - Toàn bộ cơ chế lập lịch khe thời gian tĩnh (Static DATA Slot), Superframe, Beacon đồng bộ (`DOWN_SYNC_BEACON` 0x43) và giao thức di trú lịch Schedule Migration (`DOWN_SCHED_PREPARE` 0x4B, `UP_SCHED_READY` 0x4C, `DOWN_SCHED_DECISION` 0x4D) trong [specification.md](../../contracts/radio-mac/specification.md) và [tdma-schedule.md](../../contracts/radio-mac/tdma-schedule.md).
  - Các schema MQTT phân phối lịch TDMA: `contracts/mqtt/schemas/schedule.schema.json` và `contracts/mqtt/schemas/schedule-ack.schema.json`.
- **Ranh giới giữ nguyên (Preserved Architectural Invariants):**
  - **Kiến trúc Event-Only (Quyết định Owner #125 / #230):** Bãi bỏ hoàn toàn truyền định kỳ (`DATA_TELEMETRY`); nguồn kích hoạt sự kiện duy nhất của Node MVP là Nút nhấn vật lý (Button press qua GPIO/EXT0).
  - **Bảo mật phiên V2 (`DEC-SEC-01` .. `DEC-SEC-07`):** Thỏa thuận khóa Ephemeral X25519 ECDH tại biên, mã hóa xác thực AES-128-CCM-8, Nonce 13B, `FRAME_COUNTER` 32-bit tăng đơn điệu, Backend Zero-Knowledge đối với khóa phiên unicast.
  - **Quy hoạch tần số VN920 (920.250–922.750 MHz):** Kênh tĩnh độc quyền cho từng Gateway (CH00–CH10), BW 125 kHz, công suất phát $\le +14\text{ dBm}$, tuân thủ hạn ngạch airtime pháp lý (Node $\le 1.0\%$, Gateway $\le 10\%$).
  - **Bảo toàn tính bền vững dữ liệu:** Node quản lý `EVENT_REF` trong NVS FIFO (`DEC-127-04` `RING_BUFFER_DROP_OLDEST`); Gateway ghi nhận WAL/SQLite trước khi phát `DOWN_EVENT_ACK` (0x42) và sinh `event_id` toàn cục đẩy lên Backend MQTT.

---

## 1. Bối cảnh và Vấn đề (Context & Problem Statement)

### 1.1 Khái quát kiến trúc Hybrid TDMA lịch sử (ADR-0001)
Trong giai đoạn đầu của dự án, ADR-0001 đã lựa chọn giải pháp Hybrid TDMA nhằm kiểm soát thời gian chiếm dụng sóng RF, tránh xung đột vô tuyến bán song công trên transceiver Semtech SX1276 và đảm bảo tính tất định khi mạng có nhiều Node hoạt động. Mô hình này bao gồm Backend Planner lập lịch phân bổ khe thời gian vĩ mô, Gateway Executor thực thi lịch cục bộ qua superframe, và các Node đồng bộ thời gian dựa trên `DOWN_SYNC_BEACON` định kỳ.

### 1.2 Những bất cập và mâu thuẫn kỹ thuật của TDMA trong môi trường Event-Only
1. **Lưu lượng mạng thưa thớt (Sparse, Asynchronous Traffic):** Theo Quyết định Owner #125 và #230, dự án đã bãi bỏ toàn bộ việc đo kiểm dữ liệu cảm biến định kỳ liên tục (`DATA_TELEMETRY`) cũng như cơ cấu cảnh báo tại chỗ phức tạp. Nguồn phát sinh bản tin duy nhất của Node MVP là thao tác người dùng nhấn Nút nhấn vật lý (Button press qua GPIO/EXT0) khi có sự kiện khẩn cấp hoặc kiểm thử. Lưu lượng phát sinh có tính chất đột biến, ngẫu nhiên và mật độ rất thấp.
2. **Độ trễ truyền tải lớn và lãng phí năng lượng:** Với mô hình TDMA 15 khe (chu kỳ superframe lên tới 9.000 ms – 10.000 ms), khi người dùng nhấn nút, Node buộc phải chờ đợi đến đúng khe thời gian tĩnh được cấp phát mới được phép phát sóng `UP_EVENT`. Điều này gây ra độ trễ gửi báo động khẩn cấp không thể chấp nhận được trong các tình huống an toàn, đồng thời làm phức tạp máy trạng thái của Node pin khi phải giữ trạng thái thức hoặc lập lịch hẹn giờ chờ khe.
3. **Chi phí đồng bộ thời gian và rủi ro trôi dạt thạch anh (Clock Drift):** Để duy trì khe TDMA ổn định mà không xảy ra chồng lấn (overlap), hệ thống phải tiêu tốn tài nguyên lớn cho việc tính toán ngân sách thời gian bảo vệ (Guard Time Budget, ADR-0004 lý thuyết), đo kiểm jitter ngắt DIO0 và độ trôi thạch anh uncalibrated. Node phải định kỳ thức dậy lắng nghe Beacon đồng bộ, gây hao tổn dung lượng pin vô ích.
4. **Độ phức tạp vượt tầm của giao thức di trú lịch (Schedule Migration):** Để thêm mới hoặc thay đổi lịch TDMA, hệ thống đòi hỏi một quy trình di trú 3 pha phức tạp với chữ ký số Ed25519 (`DOWN_SCHED_PREPARE` 80B, xác nhận 100% `UP_SCHED_READY 0x4C` 41B, và `DOWN_SCHED_DECISION` 80B). Việc bảo trì chu trình này trên phần cứng vi điều khiển nhúng gây phát sinh nợ kỹ thuật lớn và tăng nguy cơ bế tắc mạng (network deadlock) khi một Node mất liên lạc.
5. **Gateway có nguồn điện lưới liên tục (Mains-powered):** Khác với Sensor Node dùng pin, Gateway được cấp nguồn điện ổn định 24/7 và hoàn toàn có khả năng duy trì trạng thái nhận sóng liên tục (Continuous RX) trên chip SX1276.

Do đó, việc duy trì kiến trúc Hybrid TDMA không còn phù hợp với thực tiễn yêu cầu kỹ thuật và bản chất hoạt động của hệ thống MVP.

---

## 2. Quyết định Kiến trúc (Decision)

Project Owner chính thức phê duyệt chuyển đổi toàn diện kiến trúc tầng truy cập vô tuyến (Radio MAC V2) từ Hybrid TDMA sang mô hình **Event-driven CAD + Exponential Random Backoff (CSMA/CA)** kết hợp **Gateway Continuous RX 24/7**:

```
+---------------------------------------------------------------------------------------------------+
|               KIẾN TRÚC RADIO MAC V2: PURE CAD + CSMA/CA VÀ CONTINUOUS RX 24/7                    |
+---------------------------------------------------------------------------------------------------+

     [ Sensor Node (Battery-powered) ]                      [ Gateway (Mains-powered) ]
                    |                                                    |
       [ Deep Sleep (EXT0 Wakeup) ]                                      |
                    |                                                    |
      (Button Press Trigger Event)                                       |
                    |                                                    |
     1. Build UP_EVENT (0x41, 26B)                                       |
        AES-128-CCM Encrypt & Tag                                        |
                    |                                                    |
     2. Radio Wakeup -> SX1276 CAD Check ------------------------+       |
        (Duration ~ 1.5 - 2 LoRa symbols)                        |       |
                    |                                            |       |
        [ Channel Busy? ]                                        |       |
          YES -> Exponential Random Backoff [CW_min, CW_max] ----+       |
                 (Retry CAD <= MAX_CAD_RETRIES)                          |
          NO  -> Channel Clear!                                          |
                    |                                                    |
     3. SX1276 TX Mode: Send UP_EVENT (0x41) --------------------------> | SX1276 Continuous RX 24/7
                    |                                                    | - Detect Preamble / PayloadReady
     4. Radio RX Single Window (Timeout T_RX_ACK)                        | - Authenticate AES-128-CCM
                    |                                                    | - Check Replay (FRAME_COUNTER)
                    |                                                    | - Write Event to WAL / SQLite
                    |                                                    |
                    | <----------------- Send DOWN_EVENT_ACK (0x42) -----+ - Switch to TX: Send ACK (19B)
                    |                    (Immediate RF Response)         | - Immediately Return to Continuous RX
     5. Verify ACK (AES-128-CCM)                                         |
        - Match EVENT_REF / FRAME_COUNTER                                | Publish to MQTT (uplink/events)
        - Commit ACK in NVS FIFO                                         |
                    |                                                    v
        [ Return to Deep Sleep ]                                [ Go Modular Monolith Backend ]
```

### 2.1 Bãi bỏ hoàn toàn mô hình Hybrid TDMA (Supersession of TDMA)
1. **Bãi bỏ phân chia khe thời gian:** Hủy bỏ toàn bộ khái niệm Static DATA Slot, Maintenance Slot, và Superframe chu kỳ. Không còn việc gán khe thời gian theo vị trí Node ID.
2. **Bãi bỏ Beacon đồng bộ:** Không phát `DOWN_SYNC_BEACON` (0x43) định kỳ phục vụ căn chỉnh đồng hồ TDMA.
3. **Bãi bỏ giao thức di trú lịch:** Hủy bỏ các gói tin điều khiển phân phối lịch: `DOWN_SCHED_PREPARE` (0x4B), `UP_SCHED_READY` (0x4C), `DOWN_SCHED_DECISION` (0x4D).
4. **Bãi bỏ hạ tầng lập lịch trên MQTT và Backend:** Đánh dấu bãi bỏ (`SUPERSEDED / DEPRECATED`) topic `downlink/schedule`, `uplink/schedule-ack`, cũng như các schema JSON tương ứng (`schedule.schema.json`, `schedule-ack.schema.json`). Backend Go loại bỏ hoàn toàn trách nhiệm phân bổ slot RF.

### 2.2 Cơ chế Event-driven CAD + Exponential Random Backoff (CSMA/CA) trên Sensor Node
Khi phát sinh sự kiện từ nút bấm, Sensor Node tuân thủ quy trình truy cập vô tuyến sau:
1. **Khởi tạo và đóng gói bản tin:**
   - Node thức dậy từ Deep Sleep thông qua ngắt ngoài GPIO (EXT0).
   - Bộ điều khiển nút nhấn thực hiện lọc dội phím phần cứng/phần mềm (`button_driver`).
   - Đóng gói bản tin `UP_EVENT` (0x41, 26 octets) với mã tham chiếu nội bộ `EVENT_REF` (u32 tăng đơn điệu) và bộ đếm khung `FRAME_COUNTER` (u32 tăng đơn điệu).
   - Mã hóa xác thực toàn văn gói tin bằng thuật toán AES-128-CCM với khóa phiên $K_{\text{SESSION\_UP}}$ và Nonce 13-byte V2 (`DEC-SEC-01`, `DEC-SEC-05`).
   - Lưu trữ bản tin vào hàng đợi bền vững `node_event_fifo` trong RTC RAM / NVS flash.
2. **Lắng nghe kiểm tra kênh (Channel Activity Detection - CAD):**
   - Chuyển SX1276 sang chế độ CAD (`RegOpMode = LORA_MODE_CAD`).
   - Thời gian thực hiện một lần CAD tương ứng khoảng 1.5 – 2 ký hiệu LoRa ($T_{\text{CAD}} \approx 1.5 \times \frac{2^{SF}}{BW}$ ms, xấp xỉ 1.5 ms tại SF7/125kHz).
   - Đọc ngắt `CadDone` và cờ `CadDetected` từ thanh ghi `RegIrqFlags`:
     - Nếu `CadDetected == 0` (Kênh rỗi): Node lập tức chuyển radio sang chế độ TX để phát sóng `UP_EVENT`.
     - Nếu `CadDetected == 1` (Kênh bận): Node thực hiện thuật toán lùi thời gian ngẫu nhiên (Backoff).
3. **Thuật toán Exponential Random Backoff:**
   - Cửa sổ tranh chấp ban đầu: $CW_{\text{min}} = 16\text{ ms}$, cửa sổ tối đa: $CW_{\text{max}} = 256\text{ ms}$.
   - Tại lần thử $k$ ($k = 1..\text{MAX\_CAD\_RETRIES}$, mặc định $\text{MAX\_CAD\_RETRIES} = 5$):
     $$CW_k = \min\left(CW_{\text{max}},\, CW_{\text{min}} \times 2^{k-1}\right)$$
     $$\text{Backoff\_Time} = \text{random\_uniform}(0,\, CW_k) \text{ ms}$$
   - Node tạm dừng (vTaskDelay hoặc hẹn giờ ngủ nông) trong khoảng thời gian $\text{Backoff\_Time}$, sau đó thực hiện lại bước CAD.
   - Nếu sau $\text{MAX\_CAD\_RETRIES}$ lần thử mà kênh vẫn bận: Node hủy phiên phát hiện tại, giữ nguyên sự kiện trong NVS FIFO, ghi nhận trạng thái kênh bận và chuyển về Deep Sleep để thử lại ở chu kỳ kế tiếp.
4. **Cửa sổ chờ nhận ACK đơn (Single RX Window):**
   - Ngay sau khi hoàn thành truyền tải gói tin `UP_EVENT` (ngắt `TxDone`), Node chuyển SX1276 sang chế độ RX đơn lẻ (`RXSINGLE`) để chờ gói tin xác nhận `DOWN_EVENT_ACK` (0x42, 19B) từ Gateway.
   - Thời gian chờ xác nhận: $T_{\text{rx\_ack}} = 200\text{ ms}$ (đủ bao quát thời gian xử lý của Gateway, ghi WAL và ToA của ACK 19B $\approx 36\text{ ms}$ tại SF7).
   - Nếu nhận được `DOWN_EVENT_ACK`:
     - Node giải mã và xác thực thẻ CCM-8 bằng khóa $K_{\text{SESSION\_DOWN}}$.
     - Kiểm tra tính tương ứng của `EVENT_REF` hoặc `FRAME_COUNTER`.
     - Đánh dấu sự kiện đã được xác nhận (hoặc xóa khỏi FIFO) trong NVS flash.
     - Đưa chip vào trạng thái ngủ sâu (Deep Sleep) để tối ưu hóa năng lượng.
   - Nếu hết thời gian $T_{\text{rx\_ack}}$ mà không nhận được ACK hợp lệ:
     - Node tăng bộ đếm số lần phát lại (Retry Counter).
     - Áp dụng thời gian lùi ngẫu nhiên phát lại (Retry Backoff: ví dụ ngẫu nhiên trong khoảng $1.000\text{ ms} - 3.000\text{ ms}$) và thực hiện lại toàn bộ quy trình phát (tối đa $\text{MAX\_EVENT\_RETRIES} = 3$ lần).
     - Nếu vượt quá số lần phát lại tối đa, sự kiện vẫn được giữ lại bền vững trong NVS FIFO theo quy tắc `RING_BUFFER_DROP_OLDEST` (`DEC-127-04`).

### 2.3 Cơ chế Gateway Continuous RX 24/7
1. **Duy trì bộ thu thường trực:**
   - Gateway vận hành chip SX1276 ở chế độ nhận liên tục (`MODE_RXCONTINUOUS`) trên kênh tần số VN920 tĩnh đã được Backend cấp phát (CH00–CH10).
   - Không thực hiện bất kỳ hoạt động chuyển đổi slot hay hẹn giờ superframe nào.
2. **Quy trình tiếp nhận và phản hồi tức thời:**
   - Khi có ngắt `RxDone` / `PayloadReady`, Gateway đọc toàn bộ gói tin từ FIFO SX1276.
   - Nhận dạng mã bản tin:
     - Với `UP_EVENT` (0x41): Gateway kiểm tra tính hợp lệ của Header V2 (7B), tra cứu khóa phiên $K_{\text{SESSION\_UP}}$ của Node tương ứng, xác thực thẻ CCM-8 và kiểm tra bộ đếm chống tua lại `FRAME_COUNTER`.
     - Với `UP_JOIN_HELLO` (0x45) / `UP_JOIN_READY` (0x49): Tiếp tục xử lý quy trình bắt tay Join V2 bất đồng bộ (`DEC-SEC-01` .. `DEC-SEC-07`).
   - Nếu gói `UP_EVENT` hợp lệ:
     - Gateway **bắt buộc ghi nhận bản tin vào bộ nhớ bền vững (WAL / SQLite)** trước khi phát tín hiệu phản hồi.
     - Gateway chuyển đổi trạng thái radio sang TX (`MODE_TX`), đóng gói và phát bản tin `DOWN_EVENT_ACK` (0x42, 19 octets) được mã hóa bằng $K_{\text{SESSION\_DOWN}}$ gửi trực tiếp tới Node.
     - Ngay sau khi phát xong ACK (`TxDone`), Gateway lập tức hoàn trả chip SX1276 về chế độ `MODE_RXCONTINUOUS`.
   - Gateway sinh mã định danh toàn cục `event_id` theo quy tắc định danh duy nhất:
     $$\text{event\_id} = \text{gateway\_id} + ":" + \text{gateway\_epoch} + ":" + \text{event\_seq}$$
     và xuất bản lên broker MQTT thông qua topic `uplink/events` (hoặc `uplink/event`).

### 2.4 Trách nhiệm của Go Backend
1. **Loại bỏ chức năng lập lịch TDMA:** Backend không còn chứa scheduler lập lịch, không nạp lịch dự phòng (shadow schedule), không kiểm tra xung đột khe thời gian, và không duy trì máy trạng thái `PROPOSED -> SENT -> STAGED -> ACTIVE`.
2. **Trọng tâm chức năng V2:**
   - Quản lý định danh Gateway, Node và cấp phát kênh VN920 tĩnh độc quyền qua REST API (`/api/v1/channels`, `/api/v1/gateways/{gw_id}/channel`).
   - Xác thực và lưu trữ khóa gốc $K_{\text{JOIN}}$, xác thực bằng chứng `BACKEND_READY_PROOF` trong gói `UP_JOIN_READY` (0x49) để kích hoạt trạng thái thiết bị trong hệ thống (`DEC-SEC-04`).
   - Tiếp nhận sự kiện từ Gateway qua MQTT `uplink/events`, thực hiện khử trùng lặp qua khóa duy nhất `UNIQUE(gateway_id, event_id)` trong cơ sở dữ liệu PostgreSQL.
   - Cung cấp API cảnh báo và truyền tải luồng sự kiện thời gian thực tới Web/Mobile Client qua WebSocket Hub.

---

## 3. Hệ quả và Đánh giá Tác động (Consequences)

### 3.1 Tác động tích cực (Positive)
- **Đơn giản hóa triệt để kiến trúc Firmware:** Bãi bỏ toàn bộ các module phức tạp gồm: bộ quản lý slot TDMA, bộ lập lịch superframe, bộ bù trôi dạt đồng hồ, cơ chế xử lý jitter DIO0, và máy trạng thái di trú lịch 3 pha. Firmware Node và Gateway trở nên tinh gọn, dễ bảo trì và loại bỏ hàng loạt rủi ro rò rỉ bộ nhớ hoặc bế tắc ngắt.
- **Tối ưu hóa thời gian phản hồi (Ultra-low Latency):** Thời gian từ khi người dùng bấm nút đến khi gói tin báo động được phát đi chỉ phụ thuộc vào thời gian lọc dội phím và thời gian kiểm tra CAD (~1.5 ms – 3 ms), thay vì phải chờ đợi khe TDMA có thể kéo dài tới 10 giây.
- **Tiết kiệm năng lượng vượt bậc cho Node pin:** Node hoàn toàn ngủ sâu (Deep Sleep với dòng điện $\sim \text{vài }\mu\text{A}$), chỉ thức dậy khi có ngắt nút bấm vật lý, phát sóng trong khoảng thời gian ToA ngắn ($\approx 50\text{ ms}$ tại SF7), chờ nhận ACK ($\approx 36\text{ ms}$ ToA) rồi lập tức ngủ lại. Node không bao giờ phải thức dậy định kỳ để đồng bộ Beacon.
- **Loại bỏ nợ kỹ thuật trên Backend & Hợp đồng MQTT:** Xóa bỏ toàn bộ luồng truyền tải và đồng bộ lịch TDMA qua MQTT, giải phóng Backend khỏi sự phụ thuộc vào hạ tầng lập lịch vô tuyến.

### 3.2 Đánh giá đánh đổi và Biện pháp giảm thiểu (Trade-offs & Mitigations)
- **Xung đột vô tuyến khi nhiều Node cùng phát sự kiện đồng thời (Contention & Collisions):**
  - *Đánh giá:* Trong kịch bản thực tế của MVP (hệ thống báo động nút nhấn sự kiện), xác suất nhiều người dùng cùng nhấn nút tại cùng một thời điểm mili-giây trên cùng một kênh Gateway là cực kỳ nhỏ.
  - *Biện pháp giảm thiểu:* Cơ chế kiểm tra kênh trước khi phát (CAD) ngăn chặn việc phát đè lên tín hiệu đang chiếm sóng. Thuật toán Exponential Random Backoff giải tỏa hiệu quả hiện tượng tranh chấp nếu có nhiều Node cùng thức dậy đồng thời. Nếu xảy ra mất gói do va chạm, cơ chế Single RX Timeout kết hợp Retry ngẫu nhiên của Node đảm bảo gói tin được truyền lại thành công.
- **Gateway bán song công (Half-duplex Blinding Interval):**
  - *Đánh giá:* Trong thời gian Gateway phát bản tin `DOWN_EVENT_ACK` (ToA $\approx 36\text{ ms}$ tại SF7), bộ thu SX1276 tạm thời không thể thu tín hiệu uplink từ các Node khác.
  - *Biện pháp giảm thiểu:* Bản tin ACK có kích thước tối giản (chỉ 19 byte). Khoảng thời gian chiếm sóng này là rất ngắn. Nếu một Node khác phát sóng trong khoảng mù này, Node đó sẽ không nhận được ACK và sẽ tự động thử lại sau khoảng thời gian lùi ngẫu nhiên.
- **Gateway Continuous RX tiêu thụ năng lượng thường trực:**
  - *Đánh giá:* Chip SX1276 ở chế độ nhận liên tục tiêu thụ dòng $\sim 10.8\text{ mA} - 12\text{ mA}$.
  - *Biện pháp giảm thiểu:* Gateway trong kiến trúc của hệ thống là thiết bị được cấp nguồn điện lưới liên tục (mains-powered), do đó mức tiêu thụ này hoàn toàn nằm trong giới hạn cho phép.

---

## 4. Bảng Đối chiếu Sự thay đổi giữa Baseline Cũ và ADR-0004

| Thành phần | Baseline Cũ (ADR-0001 / DEC-0001) | Baseline Mới (ADR-0004 / DEC-273-01) |
|---|---|---|
| **Cơ chế truy cập vô tuyến MAC** | Hybrid TDMA (Khe dữ liệu tĩnh + Khe dự phòng) | Pure Event-Driven CAD + Exponential Random Backoff (CSMA/CA) |
| **Đồng bộ thời gian mạng** | Bắt buộc; Gateway phát `DOWN_SYNC_BEACON` (0x43) định kỳ | Không đồng bộ; Node hoạt động hoàn toàn bất đồng bộ |
| **Cơ chế thu của Gateway** | Theo slot thời gian được lập lịch của Superframe | Continuous RX 24/7 trên kênh tĩnh VN920 |
| **Cơ chế phát của Node** | Chỉ phát trong khe Static DATA Slot tĩnh được cấp | Kiểm tra CAD rỗi thì phát ngay khi có sự kiện nút bấm |
| **Xác nhận sự kiện (Event ACK)** | Trong khe DATA của Node hoặc theo chu kỳ Beacon | Xác nhận tức thì `DOWN_EVENT_ACK` (0x42) trong cửa sổ RX đơn của Node |
| **Cơ chế thêm Node / Cập nhật lịch** | Schedule Migration 3 pha: PREPARE 80B $\to$ READY 41B $\to$ DECISION 80B | Node hoàn tất Join V2 là phát được ngay; không cần nạp lịch |
| **Vai trò của Go Backend** | Lập lịch khe thời gian vĩ mô, quản lý trạng thái lịch | Quản lý thiết bị, cấp kênh tĩnh VN920, tiếp nhận sự kiện |
| **Topics MQTT Lập lịch** | `downlink/schedule` và `uplink/schedule-ack` hoạt động | `SUPERSEDED / DEPRECATED` (Bãi bỏ hoàn toàn) |
| **Schemas MQTT Lập lịch** | `schedule.schema.json` & `schedule-ack.schema.json` | Đánh dấu `deprecated: true` |

---

## 5. Tham chiếu và Truy xuất Nguồn gốc (Traceability)

- **Issue căn cứ:** [Issue #273: Phê duyệt quyết định kiến trúc: Chuyển đổi từ Hybrid TDMA sang Pure CAD + Random Backoff CSMA/CA](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/273)
- **Quyết định Owner trong thanh ghi:** `DEC-273-01` tại [contracts/OPEN_DECISIONS.md](../../contracts/OPEN_DECISIONS.md)
- **Hợp đồng vô tuyến cập nhật:** [contracts/radio-mac/specification.md](../../contracts/radio-mac/specification.md)
- **Tài liệu lịch sử bãi bỏ:** [contracts/radio-mac/tdma-schedule.md](../../contracts/radio-mac/tdma-schedule.md)
- **Hợp đồng MQTT cập nhật:** [contracts/mqtt/topics.md](../../contracts/mqtt/topics.md), [contracts/mqtt/semantic-rules.md](../../contracts/mqtt/semantic-rules.md)
