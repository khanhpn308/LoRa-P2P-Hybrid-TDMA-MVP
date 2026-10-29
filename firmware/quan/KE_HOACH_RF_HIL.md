# Kế hoạch RF/HIL — đóng góp #10 và #11

**Trạng thái: PLANNED. Không có số đo thực trong tài liệu này.**

## Điều kiện trước phép đo

- Hai board có revision/serial được ghi lại; xác minh SX1276 và wiring được owner duyệt.
- Driver và ESP-IDF v6.1 có SHA/toolchain/build logs; Radio Owner hoạt động và xử lý lỗi.
- RF owner duyệt profile, địa điểm/điều kiện thử và quyền TX. Chưa có duyệt: chỉ kiểm tra offline, không flash/TX.
- Logic analyzer/oscilloscope có sample rate và calibration được ghi; phân biệt timestamp ISR phần mềm với capture phần cứng.

## Ma trận đo

| Ca | Cách thực hiện sau khi đủ điều kiện | Raw evidence | Tiêu chí dự kiến |
|---|---|---|---|
| H01 init/identity | SPI identity, reset, mode transitions | SPI trace, return codes | Đúng datasheet/revision; không tự chọn register defaults |
| H02 TX/RX | Hai chiều với payload kiểm soát | TX start/end, RxDone, bytes/CRC, RSSI/SNR nếu có | Phân biệt TxDone và peer receipt |
| H03 RX timeout | Không có peer trong RX Single | deadline/IRQ/status | Timeout hữu hạn; owner về trạng thái xác định |
| H04 CAD | Có/không tín hiệu, overlap khác thời điểm | CadDone/CadDetected và trace DIO | Mapping đúng mode; CAD clear không bảo đảm kênh trống |
| H05 lỗi SPI/queue | Fault injection, queue đầy, late IRQ | reason/counter/recovery trace | Không OOB, deadlock hoặc TX ngoài quyền |
| T01 ToA | Profile và payload length được duyệt | RF envelope + IRQ trace | So lý thuyết và thực nghiệm, ghi uncertainty |
| T02 IRQ latency | Capture DIO edge và task handler | edge→ISR→task→SPI times | P50/P95/P99/max theo tải; chưa đặt ngưỡng |
| T03 turnaround | RX→TX và TX→RX | mode command→radio ready | Đủ trace và uncertainty; chưa suy ra guard cố định |
| T04 drift | Hai clock qua thời gian/nhiệt/tải | timestamp pairs và điều kiện | Phân bố drift, mất Beacon/holdover |
| T05 ACK/retry | Mất ACK và phát lại | event identity, attempt, TX airtime | Retry hữu hạn; không coi ACK là actuator execution |

## ToA lý thuyết

Đầu vào bắt buộc: SF, BW_Hz, coding-rate denominator, preamble symbols, payload bytes, explicit/implicit header, CRC và low-data-rate optimization. Tất cả profile hiện TBD.

Tính theo Semtech SX1276 datasheet đúng revision do RF owner xác nhận: symbol duration = 2^SF/BW; tổng ToA gồm preamble và payload symbols, với rounding/LDRO/header/CRC đúng công thức datasheet. Chưa có profile được duyệt nên không xuất bảng số ToA giả.

| Profile ID | SF/BW/CR/preamble/header/CRC/LDRO | Payload bytes | ToA lý thuyết | ToA đo | Sai số |
|---|---|---|---|---|---|
| TBD-owner | TBD | TBD | NOT_CALCULATED | NOT_MEASURED | TBD |

Guard cần tổng hợp ToA/turnaround, jitter, clock drift, khoảng holdover và uncertainty của đo; không chốt từ một mẫu max hoặc benchmark demo.

## Capture sheet cho từng run

Run ID; timestamp + timezone; Issue; source SHA; ESP-IDF/compiler; board revisions; instrument/sample rate; approved profile reference; payload length; command; expected/actual; repetitions; dropped samples; raw log/trace path + SHA256; reviewer; failure reason.

Số repetitions và tiêu chí PASS do RF/Embedded owner duyệt trước run. Không tính percentile/loss khi thiếu raw samples hoặc denominator.

## Demo Note.md sau tích hợp

Thử 10 lần nhấn hợp lệ trên mỗi Node trong 6 Node (60 events); 2–3 Node gần đồng thời; replay không tăng DB count; tắt notification vẫn lưu DB; lọc tháng/năm theo thời gian Backend và múi giờ Việt Nam. Ghi riêng RF delay và E2E delay. Những ca này còn cần Backend/Mobile, không thuộc kết quả HIL hiện tại.
