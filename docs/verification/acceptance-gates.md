# Các cổng nghiệm thu (Release Gates) và bằng chứng bắt buộc

Bằng chứng phải bao gồm mã Issue, mã commit hoặc mã băm (hash) của firmware, phiên bản bo mạch (board revision), phiên bản ESP-IDF/toolchain, cấu hình kiểm thử, log, thời điểm kiểm thử, người phụ trách kiểm thử, tiêu chí đánh giá và kết luận. Không được đánh dấu kết quả là `PASS` chỉ dựa trên dự đoán của AI.

| Gate | Mục đích | Bằng chứng cần có |
|---|---|---|
| G0 | Xác lập phạm vi cơ sở, trách nhiệm và ma trận truy vết yêu cầu (RTM) | Requirements và ADR đã được phê duyệt |
| G1 | Xác minh tính khả thi của phần cứng, RF và thời gian phát sóng (airtime) | Đánh giá quy định RF, tính toán ToA và số liệu đo thực tế |
| G2 | Xác minh giao thức Custom MAC và TDMA có quản lý phiên bản | Bố cục bit/byte, các trạng thái lỗi, phương án bảo mật và test vectors |
| G3 | Kiểm chứng hệ nhúng và Gateway có khả năng vận hành tự chủ | Báo cáo kiểm thử phần cứng, log timing và log khởi động lại |
| G4 | Tích hợp Backend và Client | Kiểm tra chống trùng lặp MQTT, phân quyền API, migration/restore và kiểm thử end-to-end (E2E) |
| G5 | Bảo mật và độ tin cậy | Threat model, kiểm tra replay/nonce, fault injection và soak tests |
| G6 | Nghiệm thu thử nghiệm thực địa (Pilot) | Số liệu đo thực địa, phân phối độ trễ và biên bản quyết định |

Các trạng thái được phép: `PASS`, `PARTIAL_WITH_FINDINGS`, `FAIL`, `NOT_VERIFIED`. Không được tự động nâng trạng thái nghiệm thu chỉ dựa vào kiểm tra mã nguồn (code-only checks) đối với các Gate liên quan đến RF, bảo mật hoặc HIL.

Lưu các báo cáo đo kiểm nhỏ trong `docs/verification/`. Đối với các trace/log dung lượng lớn, sử dụng GitHub Actions artifacts hoặc kho lưu trữ phòng thí nghiệm có kiểm soát.

## Trường Gate trong GitHub Projects — kiểu chọn một giá trị (single-select)

GitHub Project #1 phải có **duy nhất một** Custom Field mang tên `Gate`, với **chính xác bảy lựa chọn** dưới đây:

| Giá trị của trường trong GitHub Project | Ý nghĩa của Gate |
|---|---|
| `G0: Scope` | Xác lập phạm vi, yêu cầu và trách nhiệm |
| `G1: RF` | Tính khả thi RF và bằng chứng tuân thủ quy định |
| `G2: Protocol` | Kiểm chứng thiết kế MAC và TDMA |
| `G3: Embedded` | Tích hợp firmware và phần cứng |
| `G4: Integration` | Kiểm thử tích hợp MQTT/Backend/Client từ đầu đến cuối (E2E) |
| `G5: Security/Reliability` | Bằng chứng về bảo mật và độ tin cậy |
| `G6: Pilot Acceptance` | Nghiệm thu kiểm thử thực địa |

Chạy lệnh `bash scripts/setup_project_gate.sh` tại thư mục gốc repository sau khi GitHub CLI đã được cấp quyền truy cập Project. Không thể khẳng định trường `Gate` đã tồn tại trên Project thực tế cho đến khi được GitHub xác nhận. Việc gán một Gate cho Issue chỉ là phân loại phạm vi nghiệm thu, **không đồng nghĩa với việc Gate đó đã đạt `PASS` về mặt kỹ thuật**.
