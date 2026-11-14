# ADR 0005: Verified Bounded Mandatory-Rule Partitions for Scoped Standards Selection

- **Status:** `OWNER_APPROVED_DESIGN` · Quyết định Project Owner chính thức tại [Issue #388](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/388) (2026-11-14).
- **Thẩm quyền kiến trúc (Authority):** Project Owner phê duyệt Option B Architecture; bác bỏ vĩnh viễn kiến trúc cắt tỉa AST (AST-pruning) và thiết lập cơ chế phân vùng luật bắt buộc có kiểm chứng (Verified Bounded Mandatory-Rule Partitions).
- **Phạm vi áp dụng (Scope):** `scripts/agent_harness/standards_policy.py`, `quality_gates.py`, `pr_review_policy.py`, `pr_review.py`, `run.py`, và adapter `codex.py`.
- **Ranh giới kế thừa và bảo toàn (Preserved Architectural Invariants):**
  - **Bảo toàn 100% hợp đóng phụ thuộc bảo thủ (Conservative Dependency Union):** Không cắt giảm ngữ nghĩa (semantic pruning), không miễn trừ package cứng (hardcoded package exemptions), không loại bỏ nhóm luật MQ.
  - **Không thực thi mã ứng dụng khi chọn luật:** Cấm tuyệt đối việc biên dịch, chạy mã Go/C ứng dụng hoặc gọi công cụ phân tích động trong pha tuyển chọn luật của Host.
  - **Không xâm phạm Candidate Candidate CG-P4 (Issue #384 / PR #385):** Candidate HEAD `f5575e593f42d61e90a5abd8f5381eac3d0a7d86` được giữ đóng băng (frozen); không sửa đổi, đồng bộ hay merge trong quá trình thực hiện ADR này.

---

## 1. Bối cảnh và Vấn đề Kỹ thuật (Context & Motivating Blocker)

Trong quá trình nghiệm thu PR #385 (tái cấu trúc domain Go backend thuộc Issue #384), hệ thống harness đã phát hiện điểm nghẽn kiến trúc nghiêm trọng:
1. **Quy mô hợp đóng phụ thuộc mở rộng:** Việc chạm vào 6 tệp tin Go cốt lõi (`app.go`, `wiring.go`, `config.go`, v.v.) kéo theo hợp đóng phụ thuộc bảo thủ bao gồm 44 đường dẫn liên quan.
2. **Số lượng luật vượt ngưỡng đơn phân vùng:** Quá trình tính toán luật bắt buộc độc lập từ phía Host (Host Standards Selection) sinh ra **140 unique mandatory Rule IDs** (bao gồm toàn bộ 12 luật MQ và các nhóm luật kiến trúc Go v2).
3. **Giới hạn cứng của Host Policy v1:**
   - Ngưỡng tối đa cho một lượt chọn đơn trong Policy v1 được cố định ở **128 Rule IDs** và **48.000 serialized rule-fragment bytes**.
   - Khi áp dụng 140 luật, hệ thống lập tức kích hoạt cổng chặn `SELECTED_RULE_COUNT_OVERFLOW` (140 > 128), khiến toàn bộ tiến trình Native Fast Lane bị đình trệ (`BLOCKED`).

Tình trạng này dẫn đến "nạn đói prompt" (prompt starvation) và bế tắc tự động hóa khi các thay đổi kiến trúc hợp lệ chạm ngưỡng giới hạn an toàn của một phiên bản prompt đơn.

---

## 2. Bác bỏ Kiến trúc Cắt tỉa AST (Rejection of AST Pruning Architecture)

Trước khi đi đến ADR này, kiến trúc cắt tỉa AST (AST-pruning architecture) đã được thử nghiệm tại PR #386 / PR #387 nhưng bị Project Owner **bác bỏ dứt khoát** vì các nguy cơ sau:
1. **Phá vỡ tính bảo thủ của chuẩn mã nguồn:** Việc dùng AST parser để loại bỏ các nhóm luật (ví dụ tự động bỏ qua nhóm luật MQ hoặc bỏ qua các package không gọi trực tiếp) tiềm ẩn rủi ro bỏ sót các vi phạm đồng quy, rò rỉ tài nguyên, hoặc sai lệch hợp đồng tầng vận chuyển.
2. **Lỗ hổng thực thi mã không tin cậy (Arbitrary Code Execution):** Kiến trúc AST-pruning đòi hỏi công cụ Host (`go_impact_analyzer.go`) phải nạp và phân tích cú pháp mã nguồn từ candidate worktree chưa qua kiểm chứng, tạo bề mặt tấn công injection vào môi trường Host.
3. **Gia tăng độ phức tạp phi tất định:** Tương tác AST phụ thuộc vào trạng thái build cục bộ, version công cụ Go, và cấu trúc cây phụ thuộc động, làm mất tính tất định (deterministic) của Host Standards Gate.

Do đó, kiến trúc cắt tỉa AST bị loại bỏ vĩnh viễn khỏi repository.

---

## 3. Bảo toàn Hợp đóng Luật Bảo thủ (Conservative Union Preservation)

Kiến trúc Lựa chọn B (Option B - Verified Bounded Mandatory-Rule Partitions) được phê duyệt duy trì toàn vẹn nguyên tắc bảo thủ:
- Toàn bộ 140 Rule IDs bắt buộc được giữ nguyên 100%, không loại trừ bất kỳ quy tắc an toàn, kiến trúc, hay MQ nào.
- Host tuyển chọn luật dựa thuần túy trên phân tích đường dẫn tĩnh (path-based routing), quan hệ module khai báo sẵn, và nhóm luật bắt buộc (mandatory baseline groups).
- Không có bất kỳ ngoại lệ mã hóa cứng (hardcoded exemptions) nào theo tên package hay chức năng nghiệp vụ.

---

## 4. Chính sách Tài nguyên và Giới hạn Băng thông (Approved Resource Policy)

Chính sách phân vùng quy định các ngưỡng giới hạn nghiêm ngặt sau:

| Thông số Giới hạn | Ngưỡng Tối đa (Policy Bound) | Cơ sở Kiểm soát / Mục đích |
|---|---|---|
| **Max Rules per Host Partition** | **128 Rule IDs** | Phù hợp với schema validator của adapter `codex.py` và `antigravity.py` |
| **Max Bytes per Host Partition** | **48.000 UTF-8 bytes** | Đảm bảo kích thước phân đoạn luật không gây tràn ngữ cảnh cục bộ |
| **Max Host Partitions** | **4 Partitions** | Ngăn chặn bùng nổ số lượng phân vùng và chi phí gọi LLM đa lượt |
| **Max Aggregate Mandatory Rules** | **256 Rule IDs** | Trần tối đa của hợp đóng luật cho một PR/Issue đơn |
| **Max Aggregate Partition Bytes** | **192.000 UTF-8 bytes** | Tổng dung lượng các phân vùng luật không vượt quá 192 KB |
| **Complete Worker / Auditor Prompt Bound** | **110.000 bytes** | Giới hạn cứng của prompt hoàn chỉnh đưa vào model (Worker & Auditor) |
| **Adapter Output Bound** | **160.000 bytes** | Giới hạn dung lượng đầu ra có cấu trúc của model |

> [!IMPORTANT]
> Ngân sách tổng 192.000 bytes của các phân vùng luật không ủy quyền cho một prompt đơn lẻ vượt quá ngưỡng giới hạn 110.000 bytes. Mọi prompt gửi đến Worker đều được kiểm soát dưới 110.000 bytes.

---

## 5. Động cơ Phân vùng Tất định (Deterministic Partition Engine)

Thuật toán phân vùng thực hiện theo cơ chế **Greedy Ordered Packing**:
1. **Bảo tồn thứ tự:** Danh sách Rule IDs bắt buộc sau khi hợp nhất từ các nguồn được sắp xếp từ điển tất định.
2. **Đo lường byte UTF-8 thực tế:** Mỗi phân vùng bao gồm định nghĩa nguyên tử của luật cùng với metadata đầy đủ của phân vùng (`partition_index`, `partition_count`, `rule_ids`, v.v.). Dung lượng được đo lường chính xác trên chuỗi JSON UTF-8 đã hoàn thiện, không ước lượng tạm thời.
3. **Tính bất biến của phân vùng:**
   - **Tính rời rạc tuyệt đối (Disjointness):** Giao của các tập luật giữa hai phân vùng bất kỳ luôn là tập rỗng ($\mathcal{P}_i \cap \mathcal{P}_j = \emptyset, \forall i \neq j$).
   - **Bảo toàn hợp (Union Equality):** Hợp của tất cả các phân vùng bằng đúng tập luật bắt buộc ($\bigcup \mathcal{P}_i = \mathcal{U}$).
   - **Fail-closed:** Nếu một quy tắc đơn lẻ có kích thước vượt quá 48.000 bytes, hoặc tổng số phân vùng vượt quá 4, hệ thống dừng ngay lập tức và báo lỗi `StandardsError`.

---

## 6. Biên nhận Tuyển chọn Phiên bản v2 (Versioned Selection Receipts)

Để đảm bảo khả năng tương thích ngược và tính toàn vẹn mật mã:
- **Tương thích v1:** Các lượt chọn luật vừa vặn trong ngân sách cũ ( $\le 128$ rules và $\le 48.000$ bytes) tiếp tục sinh biên nhận chuẩn v1 với mã băm payload không đổi.
- **Biên nhận v2 (`schema_version: 2`):**
  - Khai báo rõ ràng danh sách phân vùng `partitions` với `partition_hash` độc lập.
  - Mã băm liên kết tổng thể (`aggregate_union_hash` và `selection_sha256`) ràng buộc mật mã:
    - BASE SHA và Source HEAD SHA.
    - Candidate content identity (`candidate_sha256`).
    - Cumulative diff identity (`diff_sha256`).
    - Danh sách đường dẫn cho phép, đường dẫn thay đổi, và đường dẫn ảnh hưởng.
    - Mã băm nội dung của từng quy tắc nguyên tử (`rule_hashes`).
  - Sử dụng phương thức băm không tự tham chiếu (non-self-referential hashing).

---

## 7. Giao thức Giám sát Worker v2 (Supervised Worker Protocol)

Hệ thống phân tách rạch ròi giữa hai giai đoạn tương tác với Worker:

```
[ Host: Partition Engine ]
          |
          v
+---------------------------------------------------------------------------------+
| Giai đoạn A: Nạp Đầy đủ Ngữ cảnh Bắt buộc trước khi Chỉnh sửa (Full Context)    |
| - Injected Prompt: Chứa toàn bộ 140 luật (tất cả Partitions)                    |
| - Kích thước Prompt <= 110.000 bytes                                            |
| - Ghi nhận biên nhận Host: `worker-edit-input-{iteration}.json`                  |
+---------------------------------------------------------------------------------+
          |
          v (Authorized Code Mutation)
+---------------------------------------------------------------------------------+
| Giai đoạn B: Báo cáo Bị chặn theo Khung Phân vùng (Bounded Reporting)            |
| - Báo cáo thực thi gán tối đa 128 rules/lượt (tuân thủ giới hạn adapter schema) |
+---------------------------------------------------------------------------------+
```

Worker tuyệt đối không được phép thực hiện sửa đổi mã nguồn khi mới chỉ nhận được một phân vùng đơn lẻ.

---

## 8. Báo cáo Worker Sau Chỉnh sửa ở Chế độ Chỉ Đọc (Final Read-Only Reporting)

Sau khi Worker hoàn tất việc sửa đổi mã nguồn:
1. Host kiểm tra và đóng băng snapshot ứng viên cuối cùng (`final candidate snapshot`).
2. Tái tính toán tập luật áp dụng bắt buộc dựa trên diff thực tế.
3. Kích hoạt Worker ở **chế độ chỉ đọc** (`read_only=True`, kích hoạt cờ sandbox `--sandbox read-only` trong Codex adapter) để thu thập các báo cáo có cấu trúc độc lập cho từng phân vùng.
4. Mọi hành vi làm trôi dạt snapshot hoặc cố tình ghi tệp trong giai đoạn này đều bị Host từ chối và chặn quy trình.
5. Tổng hợp bằng chứng hoàn tất chỉ khi 100% các Rule IDs bắt buộc trong toàn bộ các phân vùng đều có bằng chứng đánh giá hợp lệ.

---

## 9. Tích hợp Độc lập với Fresh Auditor (Auditor Integration)

Auditor duy trì cơ chế phân đợt 2 chiều (2D Diff $\times$ Rule Batching):
- Mỗi phân vùng Host được chia nhỏ thành các tiểu đợt (sub-batches) với số lượng luật tối đa `MAX_BATCH_RULES = 25`.
- Mỗi công việc thẩm định (Audit Job) được định danh duy nhất bởi `job_execution_hash`, ràng buộc:
  - Aggregate selection identity.
  - Phân vùng Host cha (`parent_partition_index`, `parent_partition_hash`).
  - Tiểu đợt luật và mã băm nguyên tử từng dòng luật.
  - BASE SHA, HEAD SHA, Diff batch identity, và evidence inventory.
- Cơ chế tổng hợp bảo thủ: Bất kỳ kết quả `FAIL` nào ở bất kỳ tiểu đợt nào, hoặc sự thiếu hụt của bất kỳ job nào trong ma trận, đều dẫn đến kết luận chung cuộc là `FAIL`.

---

## 10. Ý nghĩa An ninh và Kiểm chứng (Security & Verification Implications)

1. **Kháng tấn công luồn lách chuẩn (Anti-Smuggling Defense):** Việc mã băm phân vùng và mã băm luật nguyên tử được xác minh độc lập tại Host ngăn chặn việc prompt injection làm sai lệch hoặc bỏ qua luật.
2. **Ngăn chặn tấn công hoán đổi công việc (Job Substitution Defense):** Khóa băm `job_execution_hash` bảo đảm báo cáo của tiểu đợt này không thể bị tráo đổi sang tiểu đợt khác.
3. **Phòng chống chạy đua TOCTOU (Time-of-Check to Time-of-Use):** BASE SHA và HEAD SHA được kiểm tra đối chiếu trực tiếp trước và sau khi chạy qua các cổng chất lượng.

---

## 11. Di trú, Rollback và Phê duyệt Chuyên gia (Migration, Rollback & Approvals)

- **Mã triển khai:** Issue #388, nhánh `feature/388-verified-rule-partitions`.
- **Khả năng tương thích ngược:** Toàn bộ các fixture v1 và các PR có số lượng luật $\le 128$ tiếp tục hoạt động mà không có bất kỳ sự gián đoạn nào.
- **Kế hoạch Rollback:** Nếu phát sinh lỗi hồi quy, hệ thống có thể quay về phiên bản v1 bằng cách giữ nguyên nhánh và revert commit của Issue #388; tuy nhiên, Issue #384 / PR #385 sẽ tiếp tục bị chặn cho đến khi kiến trúc phân vùng được tái kích hoạt.
- **Phê duyệt chuyên gia còn chờ:** Sau khi hoàn thành kiểm thử cục bộ và mở Draft PR, cần sự nghiệm thu của:
  - Architecture / Harness Specialist (xác nhận tính toàn vẹn của phân vùng và hợp đóng bảo thủ).
  - Security Specialist (xác nhận khả năng chống giả mạo biên nhận và tính độc lập của Auditor).
