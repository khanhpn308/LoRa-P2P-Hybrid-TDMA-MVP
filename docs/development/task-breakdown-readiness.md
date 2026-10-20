# Mức độ sẵn sàng trước khi phân rã nhiệm vụ (Task Breakdown) — Hybrid TDMA Monorepo

**Trạng thái:** `PARTIAL_WITH_FINDINGS`. **Người phụ trách:** Project Lead. **Nhánh được ghi trong bản gốc:** `research/ready-for-taskbreakdown`.

Danh sách kiểm tra này là điều kiện chuẩn bị trước khi tạo nhiệm vụ cho các nhóm và giao việc cho AI. Tài liệu **không** khẳng định rằng các yêu cầu về RF, MAC, bảo mật hoặc độ trễ đã được đáp ứng.

## A. Kiểm tra khả năng nhận diện các ESP-IDF component dùng chung

Dòng cấu hình sau phải xuất hiện trong **cả hai** tệp:
- `firmware/gateway_master/CMakeLists.txt`
- `firmware/sensor_node/CMakeLists.txt`

```cmake
set(EXTRA_COMPONENT_DIRS "../components")
```

Bốn component dùng chung được quy hoạch gồm:
`sx1276_driver`, `lora_mac`, `tdma_common`, `airtime_policy`.

**Điểm phân biệt quan trọng:** Biến CMake trên chỉ xác định thư mục tìm kiếm component, trong khi các thư mục `firmware/components/*/` hiện mới chứa tệp README khung (scaffold). ESP-IDF chỉ coi mỗi thư mục là component có thể build **sau khi có `CMakeLists.txt` hợp lệ cùng các tệp mã nguồn/thư mục include được đăng ký**. Vì vậy, những nhiệm vụ firmware đầu tiên phải tạo cấu hình component tối thiểu, mã nguồn và kiểm thử thực tế; đồng thời chứng minh lệnh `idf.py build` thành công cho **cả Gateway lẫn Node**. Không tạo implementation rỗng để giả lập tiến độ và không tuyên bố `HIL/PHY PASS` khi chưa có bằng chứng.

## B. Trường Gate — chính xác bảy lựa chọn trong GitHub Projects

Project: https://github.com/users/khanhpn308/projects/1

Tạo **một Custom Field kiểu single-select có tên `Gate`** với đúng các giá trị sau (không phải bảy GitHub Labels):

| Giá trị lựa chọn | Mục đích | Gate tương ứng |
|---|---|---|
| `G0: Scope` | Thiết lập yêu cầu cơ sở, trách nhiệm sở hữu và ma trận truy vết yêu cầu (RTM) | G0 |
| `G1: RF` | Xác minh tính khả thi của RF, airtime và yêu cầu pháp lý | G1 |
| `G2: Protocol` | Thiết kế MAC, TDMA, bảo mật và test vectors | G2 |
| `G3: Embedded` | Kiểm chứng hoạt động của ESP-IDF Gateway/Node và HIL | G3 |
| `G4: Integration` | Tích hợp MQTT, Go, PostgreSQL và các giao diện Client | G4 |
| `G5: Security/Reliability` | Threat model, các tình huống lỗi và soak tests | G5 |
| `G6: Pilot Acceptance` | Kiểm thử thực địa và phê duyệt nghiệm thu | G6 |

Để kiểm tra hoặc tạo trường này, hãy sử dụng **thông tin xác thực thuộc tài khoản sở hữu Project**:

```bash
gh auth status
gh auth refresh -s project      # Chỉ thực hiện nếu thiếu quyền truy cập Project
bash scripts/setup_project_gate.sh
gh project field-list 1 --owner khanhpn308 --format json
```

Script sẽ **kiểm tra xem trường `Gate` đã tồn tại hay chưa** trước khi thực hiện thao tác tạo. Nếu danh sách lựa chọn không khớp, script sẽ dừng thay vì ghi đè hoặc xóa dữ liệu. Không báo cáo trường này là `CREATED/VERIFIED` nếu lệnh chưa chạy thành công trên Project thực tế hoặc chủ sở hữu Project chưa xác nhận trên giao diện GitHub.

Giá trị Gate của mỗi nhiệm vụ trong GitHub Project phải là một trong bảy lựa chọn nêu trên. Việc công nhận Gate đã hoàn thành vẫn phải dựa trên bằng chứng theo `docs/verification/acceptance-gates.md`.

## C. CODEOWNERS — phụ thuộc vào việc thành viên chấp nhận lời mời

Tệp: `.github/CODEOWNERS`. Hiện tài liệu ghi nhận `@khanhpn308` là **người phụ trách tạm thời hợp lệ** cho tất cả các nhóm đường dẫn. **Không** tự đặt GitHub username hoặc thay thế bằng tài khoản của thành viên chưa chấp nhận lời mời cộng tác.

Sau khi năm thành viên còn lại chấp nhận lời mời và được cấp quyền truy cập repository:

1. Xác nhận chính xác GitHub username của từng người (URL trang cá nhân và quyền truy cập repository).
2. Phân công owner thực tế cho các khu vực Firmware dùng chung, Gateway, Node, Go, Infrastructure, Web, Mobile, Contracts, Docs và Tests. Một người có thể phụ trách nhiều khu vực.
3. Cập nhật `.github/CODEOWNERS` thông qua Pull Request để có thể review; tài khoản được khai báo cho mỗi đường dẫn phải có quyền truy cập repository hợp lệ.
4. Với các thay đổi trong `contracts/` hoặc liên quan đến timing/bảo mật, bổ sung reviewer đại diện cho tất cả giao diện producer/consumer bị ảnh hưởng.
5. Bật cơ chế yêu cầu review/approval theo CODEOWNERS thông qua ruleset hoặc branch protection mà repository hỗ trợ. Chỉ có tệp CODEOWNERS **không đồng nghĩa** việc phê duyệt đã được hệ thống bắt buộc thực thi.

**Phụ thuộc đang chặn:** Tài liệu kiến trúc hiện chưa cung cấp đầy đủ năm GitHub username đã chấp nhận lời mời. Trạng thái này vẫn là `PENDING_TEAM_IDENTITIES`; không thể tự động coi là hoàn thành chỉ bằng cách chờ đợi.

## D. Quy định phạm vi đường dẫn của Issue (Path-Scoped Issue) — bắt buộc từ thời điểm này

Mỗi Issue thuộc loại Task, Research hoặc Bug phải có trường bắt buộc **`Target Directories (allowed paths)`**.

```markdown
### Target Directories (allowed paths)
- firmware/components/sx1276_driver/
- tests/hil/

### Out of Scope
- firmware/sensor_node/ (trừ khi được bổ sung rõ ràng vào Issue)
- backend-go/
```

**Quy tắc:**

- Khai báo **đường dẫn tường minh, tính từ thư mục gốc của repository**. Liệt kê trước các đường dẫn liên quan đến tests, docs, migrations hoặc contracts khi thực sự cần thiết.
- Owner hoặc AI **chỉ được chỉnh sửa** những đường dẫn đã khai báo. Không tự ý format hoặc refactor toàn repository nếu chưa được phê duyệt rõ ràng.
- Nếu cần thay đổi thêm thư mục ngoài phạm vi, **phải cập nhật phạm vi Issue trước** và xin phê duyệt của owner liên quan giữa các nhóm trước khi sửa. Chỉ trao đổi trong comment không mặc nhiên được coi là quyền thay đổi phạm vi.
- PR template phải nhắc lại danh sách `Target Directories`; reviewer đối chiếu mục `Files changed` với phạm vi đã được chấp thuận trong Issue.
- Quy định Path-Scoped Issue hiện được áp dụng thông qua **quy trình được ghi thành văn bản + Issue Forms có trường bắt buộc + review của con người**. Chưa có GitHub rule tự động nào được xác nhận là có thể chứng minh mọi tệp thay đổi đều thuộc danh sách đường dẫn cho phép của Issue.

Năm Issue Forms trong `.github/ISSUE_TEMPLATE/` có trường bắt buộc này. Với Issue được tạo thủ công hoặc do AI tạo, phần khai báo tương tự cũng **bắt buộc**.

## E. Trạng thái sẵn sàng và yêu cầu xác minh

| Hạng mục kiểm tra | Đánh giá ghi nhận | Bằng chứng để hoàn tất |
|---|---|---|
| Cấu hình CMake `EXTRA_COMPONENT_DIRS` trong cả hai project | `PRESENT` | Diff của tệp và kiểm tra cấu trúc trên CI |
| Bốn thư viện dùng chung có thể build đầy đủ | **`NOT_IMPLEMENTED`** | Component `CMakeLists.txt`, mã nguồn và kết quả `idf.py build` cho cả hai ứng dụng |
| Trường Gate G0–G6 trên GitHub Project thực tế | **`NOT_VERIFIED`** | Kết quả lệnh `gh` hoặc ảnh chụp giao diện Project |
| Ánh xạ CODEOWNERS dự phòng | `PRESENT` | Tệp đã được review |
| Năm GitHub username thực tế đã chấp nhận quyền cộng tác trong CODEOWNERS | **`PENDING_TEAM_IDENTITIES`** | Xác nhận thành viên và bảng ánh xạ owner đã review |
| Năm Issue Forms có trường Path-Scoped | `PREPARED` | Tệp YAML trong repo và kiểm tra giao diện GitHub Issue Form |
| Quy định phạm vi chỉnh sửa trong PR/AI | `PREPARED` | Diff quy định và phê duyệt của owner |

Chỉ triển khai Task Breakdown khi đã nêu rõ những điều kiện tiên quyết còn chưa hoàn tất. Issue khởi tạo firmware đầu tiên phải kiểm thử khả năng ESP-IDF nhận diện các component dùng chung; việc build thành công scaffold **không** đồng nghĩa đã triển khai đầy đủ một giao thức.
