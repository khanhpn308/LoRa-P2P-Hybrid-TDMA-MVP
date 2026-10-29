# Kiểm kê và tích hợp thư viện chung

Baseline: `08e86af2fda8e40b89c0cf01b98e08311f03b7a9`.

| Thành phần | Nội dung trên main | Trách nhiệm khi triển khai |
|---|---|---|
| sx1276_driver | README, pending port | Registers/SPI/IRQ và modem state, một Radio Owner |
| lora_mac | README, design pending | Codec/auth/replay theo contract được duyệt |
| tdma_common | README, planned | Kiểu lịch, đơn vị thời gian và validation dùng chung |
| airtime_policy | README, planned | Admission cho mọi TX, kể cả ACK/retry/Alert |

## Layout hiện tại và điểm tích hợp #10

```text
firmware/
  components/          # nguồn chung duy nhất
  event_bench/
    gateway_bench/     # project ESP-IDF bench Gateway
    sensor_node_bench/ # project ESP-IDF bench Node
    components/        # event_input và bench_console
    *.md               # bộ bàn giao hiện tại
```

Hai project dùng cấu hình chung `project.cmake`. Khi bật tùy chọn liên kết driver, cấu hình bổ sung thư mục thư viện chung bên cạnh `event_bench`:

```cmake
cmake_minimum_required(VERSION 3.22)
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../../components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(gateway_bench) # node dùng tên sensor_node_bench
```

Đoạn trên minh họa đường dẫn thư viện chung, không thay thế `project.cmake` hiện hành có kiểm tra phiên bản SDK và tùy chọn rõ ràng. Hướng dẫn build đầy đủ tại FIRMWARE.md. Kiểm tra dependency thật theo C-006 trước khi mở rộng tích hợp.

## Ranh giới tương thích

Không đổi public API hoặc copy driver vào thư mục cá nhân. Khi có API được review, adapter cá nhân chỉ nhận/gửi qua owner đó. Nếu API thiếu chức năng, đề xuất PR riêng vào thư viện chung, rà soát cả Gateway và Node theo GOV-007/C-019.

Producer/consumer: ứng dụng cá nhân → driver owner queue; ISR → owner notification; MAC → driver request; airtime admission → trước mỗi TX. Capacity, ownership, lifetime, timeout và queue-full policy phải được duyệt/test trước implementation. Mọi con số chưa có ngân sách đo giữ TBD.

## Đối chiếu code trong máy trước khi tái sử dụng

1. Xác định commit/PR và diff của từng bản driver; không ghép toàn bộ dirty checkout vào main.
2. Review ISR không SPI/blocking/allocation; mọi modem transition và SPI cùng một owner.
3. Kiểm tra DIO mapping theo mode, finite timeout, IRQ clear, recovery và shutdown khi callback còn chạy.
4. Chạy build cả hai firmware, unit/fault tests và HIL theo scope #10.
5. Sau merge, cập nhật SHA baseline trong báo cáo, rồi mới liên kết project Quân.
