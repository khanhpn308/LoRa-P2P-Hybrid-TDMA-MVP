# Báo cáo dự án tuần 2 — Quân

**Cập nhật sau bản tài liệu ban đầu:** đã có source C local bench tại `sensor_node_bench/`, `gateway_bench/` và `components/event_input`, `components/bench_console`. Xem [FIRMWARE.md](FIRMWARE.md) cho phạm vi và cách chạy. Các bảng dưới ghi hiện trạng lần bàn giao tài liệu ban đầu; không dùng chúng để phủ nhận code bổ sung hoặc khẳng định radio đã hoạt động.

**Dự án:** LoRa P2P Hybrid TDMA · **Tuần:** 26–30/10/2026 · **Ngày lập:** 29/10/2026.

## 1. Mục tiêu và phần việc

| Issue | Phần Quân phối hợp | Sản phẩm tuần 2 |
|---|---|---|
| #10 — Quân, Phước | Baseline SX1276, Radio Owner, IRQ/SPI, nhận diện 4 components | Code/PR, hai build, TX/RX/CAD/HIL khi đủ board |
| #11 — Quân, Phước, Khánh | Ma trận ToA, latency, turnaround, drift | Test plan; số đo chỉ khi thiết bị và driver sẵn sàng |
| #78 — nhóm MAC | Đánh giá truy cập ưu tiên ở Periodic ON/OFF | So sánh ≥3 phương án, state machine, pseudocode, simulation plan |

## 2. Hiện trạng đã xác minh

Baseline GitHub: `08e86af2fda8e40b89c0cf01b98e08311f03b7a9` trên `main`.
Bốn đường dẫn `firmware/components/{sx1276_driver,lora_mac,tdma_common,airtime_policy}` chỉ chứa README. Chưa có source, header hay CMake component trong baseline này.
Gateway/Node chỉ có `app_main` ghi log scaffold. Vì vậy chưa thể liên kết hoặc sử dụng một API driver chung có sẵn từ `main`.

Checkout cũ trong máy có nhiều thay đổi driver chưa commit; chúng không phải bằng chứng về nội dung đã có trên `main`. Bản bàn giao này dùng checkout sạch riêng và giữ nguyên toàn bộ thư viện chung.

## 3. Công việc đã thực hiện trong lần bàn giao

- Đọc hai tài liệu Word, Note.md và quy chuẩn C; đối chiếu #10/#78 trực tiếp trên GitHub.
- Kiểm kê baseline và xác định khoảng trống thư viện; lập phương án tái sử dụng đúng đường dẫn.
- Tạo bộ báo cáo cá nhân, kế hoạch RF/HIL, thiết kế Priority Access và ma trận minh chứng trong `firmware/event_bench/`.
- Đề xuất hybrid reserved opportunity + bounded CAD/backoff để nhóm đánh giá; chưa phê duyệt thuật toán hoặc hằng số RF.

## 4. Kiến trúc giữ nguyên

Node phát hiện Trigger tại biên, có Periodic ON/OFF. Gateway thực thi lịch thời gian thực cục bộ và là chủ sở hữu radio. Backend hoạch định lịch, quản lý thiết bị/cấu hình và dữ liệu.
Periodic OFF vẫn giữ Beacon, Alert, Discovery và Downlink phù hợp. Alert được ưu tiên tại cơ hội hợp lệ; không ngắt gói đang phát trên SX1276 half-duplex.

## 5. Chênh lệch tài liệu và quyết định cần duyệt

Note.md mô tả demo 6 Node, nút nhấn 55°C và ứng dụng điện thoại; tài liệu kiến trúc mô tả 10–15 Node, React và Mobile ngoài MVP ban đầu; kế hoạch tuần 2 giao UI Kotlin cho thành viên khác. Báo cáo này theo Wave 1 và phần việc Quân; yêu cầu demo được giữ thành bộ kiểm thử tích hợp tương lai, chưa mở rộng phạm vi sang Backend/Mobile.

Header 8 byte + CRC16 trong tài liệu kiến trúc là candidate cũ. Theo D01/D11 trong `contracts/OPEN_DECISIONS.md`, chưa đóng băng wire layout, authentication, nonce/replay hoặc schedule epoch. CRC không phải xác thực.
Không chọn tần số, công suất, GPIO, guard, slot hay SLA từ ví dụ. D03 và G1 cần owner RF/hardware giải quyết trước TX.

## 6. Trạng thái và vướng mắc

| Nhóm | Trạng thái lần bàn giao này | Điều kiện tiếp tục |
|---|---|---|
| Báo cáo/thiết kế cá nhân | DRAFT, đã viết | Review nhóm và mentor |
| #10 driver chung | Chưa có implementation trên baseline kiểm tra | Port/review driver theo scope #10 |
| Hai project cá nhân ESP-IDF | BUILD_VERIFIED: v6.1 PASS | Local bench, chưa RF |
| #11 phép đo | PLANNED / NOT_VERIFIED | Board, profile được duyệt, dụng cụ và raw logs |
| #78 thuật toán | PROPOSED, chưa mô phỏng | RF/Embedded/Backend/Security review |
| E2E, HIL, RF, timing, security | NOT_VERIFIED | Bằng chứng riêng từng loại |

Không gán phần trăm hoàn thành Issue từ số tài liệu đã viết. Chưa đủ bằng chứng nghiệm thu #10/#11/#78.

## 7. Kế hoạch tiếp theo

Quân và Phước rà soát driver hiện có trong máy, tách thay đổi theo #10 và chuẩn hóa single Radio Owner; build hai firmware. Quân chuẩn bị capture sheet và thực hiện các phép đo #11 sau khi RF owner duyệt profile. Nhóm #78 dùng kết quả đó để chọn tham số, chạy mô phỏng và trình mentor trước Wave 2.

Mentor/owner cần quyết định: PR driver nào làm baseline dùng chung; ai duyệt RF profile/pin map; điều kiện gỡ #11; lựa chọn thuật toán #78; phạm vi demo 6 Node và công nghệ Mobile thống nhất.

## Bổ sung firmware cá nhân

Đã triển khai module C event_input (debounce, FIFO bounded, overflow counters), bench_console và project Node/Gateway. Host unit tests và hai build ESP-IDF v6.1 đã PASS. Tùy chọn liên kết driver local đã build Node PASS nhưng chỉ gọi identity API; chưa nối luồng sự kiện qua LoRa. Xem FIRMWARE.md. Không coi kết quả này là hoàn thành driver chung #10 hoặc nghiệm thu HIL/RF.
