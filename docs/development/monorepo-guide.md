# HƯỚNG DẪN MONOREPO — LoRa P2P Hybrid TDMA MVP

> **Baseline ESP-IDF (approved 2026-10-22):** v6.1 for Gateway and Sensor Node, controlled by `firmware/esp-idf-version.txt` and ADR-0003. Both firmware CI jobs use this pinned release; Harness automatically loads it. Any other process/guidance below must use v6.1 for firmware. This handbook's other Draft decisions remain Draft. Build success is not HIL/RF PASS.

> **Document ID:** DEV-MONOREPO-001  
> **Version:** 1.0 — Draft for team review  
> **Audience:** Nhóm phát triển ban đầu 6 người (Firmware / RF / Backend / Web / Mobile / QA kiêm nhiệm)  
> **Repository:** [khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP)  
> **Owner:** Project Lead; áp dụng sau khi Pull Request tài liệu được review/merge.  
> **Quan trọng:** Repo hiện là **foundation/scaffold**, chưa phải ứng dụng LoRa, TDMA, Backend hay Mobile đã chạy hoàn chỉnh.

## 1. Mục tiêu và phạm vi

Một Monorepo quản lý thống nhất **mã nguồn, hợp đồng giao tiếp, tài liệu, kiểm thử, cấu hình triển khai và quy tắc AI** để các thành viên phát triển đồng thời nhưng không phá vỡ tính tương thích xuyên tầng.

**Kiến trúc đã chọn:**

- 10–15 ESP32 + SX1276 Sensor Nodes, LoRa **P2P** với custom MAC.
- Một ESP32 + SX1276 Gateway **đồng thời là TDMA Master cục bộ**, điều khiển chính xác lịch phát/thu qua firmware.
- Backend **Go Modular Monolith** tính và phát hành lịch TDMA theo phiên bản; **không** điều khiển bật/tắt TX/RX cho từng slot qua Internet.
- Backhaul Wi-Fi → Mosquitto MQTT → Backend Go → PostgreSQL; web React/TypeScript; mobile Flutter là giai đoạn sau.
- **Không** dùng ChirpStack, LoRaWAN Gateway, OTAA/LoRaWAN MAC trong MVP.
- Các thông số như MAC Header 8B, superframe 10s, công suất/tần số, duty cycle, guard time, độ trễ cảnh báo < 3s **chưa được nghiệm thu**; yêu cầu số liệu RF/HIL và thẩm định quy định tương ứng.

**Nguồn tham chiếu:** [System Architecture](../architecture/system-overview.md), [Requirements/RTM](../requirements/requirements.md), [Release Gates](../verification/acceptance-gates.md), [ADR-0001](../adr/0001-hybrid-tdma.md).

## 2. Sơ đồ bố trí source — bản đồ trách nhiệm

~~~text
LoRa-P2P-Hybrid-TDMA-MVP/
├── .github/
│   ├── ISSUE_TEMPLATE/                 # Form tạo issue thống nhất
│   ├── workflows/                      # GitHub Actions
│   ├── CODEOWNERS                       # Người review theo đường dẫn
│   ├── pull_request_template.md
│   └── dependabot.yml
├── docs/
│   ├── architecture/                   # Kiến trúc 5 tầng, interfaces, deployment
│   ├── requirements/                   # Yêu cầu có ID/RTM
│   ├── adr/                            # Quyết định kiến trúc (ADR)
│   ├── verification/                   # Gates, báo cáo và bằng chứng
│   └── development/                    # Hướng dẫn lập trình/Monorepo
├── contracts/
│   ├── radio-mac/                      # Đặc tả LoRa MAC + golden test vectors
│   ├── mqtt/                           # Topics, schemas, semantics
│   └── api/                            # OpenAPI cho REST
├── firmware/
│   ├── components/
│   │   ├── sx1276_driver/              # SPI, IRQ, radio driver dùng chung
│   │   ├── lora_mac/                   # Serializer, parser, auth, version
│   │   ├── tdma_common/                # Kiểu dữ liệu/tính toán thời gian chung
│   │   └── airtime_policy/             # Giới hạn phát cục bộ
│   ├── gateway_master/                 # ESP-IDF app: Gateway + TDMA Executor
│   └── sensor_node/                    # ESP-IDF app: Node + Sync/TDMA Client
├── backend-go/
│   ├── cmd/server/                     # Entry point
│   ├── internal/                       # api, mqtt, scheduler, telemetry, alert...
│   ├── migrations/                     # Phiên bản schema PostgreSQL
│   └── go.mod
├── clients/
│   ├── web-dashboard/                  # React + TypeScript (planned)
│   └── mobile-app/                     # Flutter + Dart (planned)
├── simulator/
│   ├── radio-network/                  # Mô phỏng logic RF/MAC/TDMA (planned)
│   ├── gateway-mqtt/                   # MQTT test publisher (planned)
│   └── scenarios/                      # Kịch bản giả lập (planned)
├── tests/
│   ├── contract/                       # Tương thích giao thức
│   ├── integration/                    # Gateway-MQTT-Go-DB-API
│   └── hil/                            # Test ESP32/SX1276 trên phần cứng thật
├── deploy/
│   ├── compose.yaml                    # Local PostgreSQL, MQTT theo profile
│   └── mosquitto/                      # Cấu hình broker mẫu
├── scripts/                            # Công cụ dùng chung
├── .env.example                        # Ví dụ biến môi trường, KHÔNG có secrets
├── .gitignore
└── README.md                           # Entry point và liên kết tài liệu
~~~

**Không thêm thư mục trống chỉ để cho đủ cây:** Git không lưu thư mục rỗng. Các nhánh đang “planned” mới có README placeholder; chỉ bổ sung source khi có Issue và người phụ trách.

## 3. Quy tắc “file nào đặt ở đâu?”

| Nội dung | Nơi lưu chuẩn | Không nên đặt ở |
|---|---|---|
| Driver SX1276 chung cho Node/Gateway | firmware/components/sx1276_driver/ | Hai bản sao ở main/ mỗi ứng dụng |
| Codec/MAC frame và kiểm tra độ dài | firmware/components/lora_mac/ | Copy cùng logic riêng vào Node/Gateway |
| TDMA Master, beacon, schedule executor | firmware/gateway_master/ | backend-go/ |
| Node sensor, beacon sync, slot client | firmware/sensor_node/ | firmware/gateway_master/ |
| LoRa MAC byte/bit layout, phiên bản | contracts/radio-mac/ | README hoặc comment code là nguồn duy nhất |
| MQTT topic, message schema | contracts/mqtt/ | Hardcode thiếu tài liệu ở nhiều module |
| REST endpoints | contracts/api/openapi.yaml | Chỉ lưu trên màn hình Web |
| Lập lịch Go, alert, ingest | backend-go/internal/ | simulator/ hoặc firmware/ |
| Migration SQL | backend-go/migrations/ | SQL chạy tay không version |
| UI React / mobile Flutter | clients/ | backend-go/internal/ |
| Mô phỏng va chạm/đồng bộ/airtime | simulator/radio-network/ | Gọi nhầm “HIL passed” |
| Giả lập gateway MQTT cho Backend | simulator/gateway-mqtt/ | Giả định Node gửi MQTT trực tiếp |
| Kiểm thử trên bo mạch thực | tests/hil/ và báo cáo docs/verification/ | Chỉ thay bằng mô phỏng |
| Terraform/Compose/deployment | deploy/ | Trong thư mục firmware/ |
| Decision record / bản chốt yêu cầu | docs/adr/, docs/requirements/ | Chỉ ghi trong tin nhắn chat |

### Luật sở hữu dữ liệu (Single Source of Truth)

1. **Contract** quyết định giao diện trao đổi giữa các thành phần; implementation phải bám contract đã duyệt.
2. **Requirements + ADR** quyết định *vì sao* triển khai; không coi bản nháp giả định là thông số chắc chắn.
3. **Code + migration** là nơi định nghĩa hành vi thực thi và lược đồ dữ liệu.
4. **Test evidence** chứng minh yêu cầu; CI thành công không đồng nghĩa đạt kiểm thử RF, bảo mật hoặc HIL.
5. **GitHub Issues/Projects** theo dõi công việc và nghiệm thu; không tạo bảng tiến độ song song không được đồng bộ.

## 4. Quy hoạch source code theo miền và phụ thuộc

~~~mermaid
flowchart TB
  RF["contracts/radio-mac"] --> FWC["firmware/components"]
  FWC --> GW["firmware/gateway_master"]
  FWC --> NODE["firmware/sensor_node"]
  MQ["contracts/mqtt"] --> GW
  MQ --> BE["backend-go"]
  API["contracts/api"] --> BE
  API --> WEB["clients/web-dashboard"]
  API --> MOB["clients/mobile-app"]
  BE --> DB["PostgreSQL migrations"]
  MQ --> SIM["simulator/gateway-mqtt"]
  RF --> RSIM["simulator/radio-network"]
~~~

**Giới hạn phụ thuộc bắt buộc:**

- Gateway và Node dùng chung low-level driver, codec và policy khi thật sự chung ngữ nghĩa; **không dùng chung** TDMA Executor (Master) với TDMA Client.
- Driver SX1276 không được phụ thuộc trực tiếp vào MQTT, PostgreSQL hoặc Web.
- Go Domain không phụ thuộc trực tiếp vào firmware C; trao đổi thông qua định dạng/hợp đồng phiên bản hóa.
- Client không kết nối trực tiếp vào MQTT Broker hoặc PostgreSQL. Mọi xác thực, RBAC và truy cập dữ liệu qua Backend.
- Hàng đợi trên ESP32 phải có giới hạn, timeout và quy tắc overflow; ưu tiên static buffers hoặc preallocated pools, hạn chế malloc/free lặp lại trong steady state.
- Một radio owner tuần tự hóa SPI/SX1276 state; ISR chỉ xử lý tối thiểu, không được blocking.

## 5. 6 người làm việc trên một Monorepo như thế nào?

| Vai trò tạm phân | Khu vực chính | Review chéo bắt buộc |
|---|---|---|
| Kỹ sư 1 — Gateway/TDMA | firmware/gateway_master/ | MAC/Node, RF và Backend khi đụng lịch |
| Kỹ sư 2 — Node/RF/MAC | firmware/sensor_node/, firmware/components/ | Gateway + QA/HIL |
| Kỹ sư 3 — Go Scheduler/API | backend-go/internal/scheduler/, api/ | Gateway + Go/Data |
| Kỹ sư 4 — MQTT/DB/DevOps | backend-go/internal/mqtt/, storage/, migrations/, deploy/, CI | Go + Security/Review |
| Kỹ sư 5 — Web | clients/web-dashboard/ | Backend/API |
| Kỹ sư 6 — Mobile / Test Coordination | clients/mobile-app/, hỗ trợ tests/ | Backend/API + Embedded/HIL |

Một thành viên có thể kiêm nhiều vai trò; bảng này là **đề xuất**, chưa phải nhân sự đã gán. Hiện [CODEOWNERS](../../.github/CODEOWNERS) dùng **@khanhpn308** làm fallback; cập nhật GitHub username thật của 6 người khi có quyền repository. Đừng mặc định 6 vai trò này đều là kỹ sư chuyên QA: giao trách nhiệm test theo tính độc lập và rủi ro.

## 6. Quy trình Git chuẩn: Issue → Branch → PR → CI → Review → Merge

### 6.1. Clone và kiểm tra

~~~bash
git clone https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP.git
cd LoRa-P2P-Hybrid-TDMA-MVP
git status
git fetch --all --prune
git switch main
git pull --ff-only
~~~

Không phát triển trực tiếp trên main. Không force push main; cấu hình branch protection/ruleset và required checks theo khả năng gói GitHub trước khi áp dụng chính thức.

### 6.2. Quy tắc nhánh

| Mục đích | Mẫu | Ví dụ |
|---|---|---|
| Tính năng | feature/<issue>-<ten-ngan> | feature/42-sx1276-rx |
| Lỗi | fix/<issue>-<ten-ngan> | fix/87-buffer-overflow |
| Tài liệu | docs/<issue>-<ten-ngan> | docs/61-mqtt-contract |
| CI, build, tooling | chore/<issue>-<ten-ngan> | chore/18-ci-esp-idf |
| Nghiên cứu | research/<issue>-<ten-ngan> | research/24-toa-sf7 |

~~~bash
git switch main
git pull --ff-only
git switch -c feature/42-sx1276-rx
# ... thay đổi theo Issue ...
git add firmware/ docs/
git diff --cached --check
git commit -m "feat(firmware): add sx1276 rx path (#42)"
git push -u origin feature/42-sx1276-rx
gh pr create --base main --fill
~~~

Không dùng lệnh git add . một cách mù quáng khi workspace chứa credentials, firmware build outputs hoặc logs; xem git status và diff trước khi commit.

### 6.3. Điều kiện PR được merge

- Liên kết Issue, requirement ID, phạm vi thay đổi và Acceptance Criteria.
- Có test hoặc nêu rõ vì sao chưa thể kiểm thử, kèm Issue theo dõi.
- CI áp dụng đã xanh, review độc lập và CODEOWNERS/required approvals đã hoàn tất.
- Contract/API/DB thay đổi đã được review bởi cả producer lẫn consumer; cập nhật schema, test vectors và migration.
- Không có secrets, số liệu đo bịa đặt, hình/firmware binary không rõ nguồn.
- PR ảnh hưởng ISR, timer, SX1276, bảo mật hoặc radio compliance phải có **human technical audit** và HIL khi phù hợp.
- Ưu tiên squash merge để lịch sử main rõ ràng; xóa feature branch sau merge nếu không còn sử dụng.

**Lưu ý:** PR/GitHub workflow mới chỉ thực sự enforced nếu repository có ruleset/branch protection phù hợp; tài liệu này là chính sách nhóm, không khẳng định enforcement đã bật.

### 6.4. Quy tắc Path-Scoped Issues bắt buộc

Từ trước Task Breakdown, mọi Issue (kể cả Bug/Research, tạo thủ công hoặc bằng AI) đều phải có mục **`Target Directories (allowed paths)`**, ghi rõ từng thư mục/tệp từ root repository. Chỉ được sửa các đường dẫn này. Nếu cần cập nhật thêm contract, tests, tài liệu hoặc migration, phải sửa scope Issue và xin phê duyệt trước; không mặc định `docs/` hoặc `tests/` luôn được phép.

Ví dụ: `firmware/components/sx1276_driver/` và `tests/hil/` cho nhiệm vụ thử driver; ngoài phạm vi: `backend-go/`, `clients/`. Pull Request phải nhắc lại các đường dẫn được phép và reviewer đối chiếu `Files changed`.

Cơ chế hiện tại là **required Issue Forms + policy AI + human PR review**, chưa có máy kiểm chứng tự động phạm vi theo Issue. Đọc [Pre-Task-Breakdown Readiness](task-breakdown-readiness.md).

## 7. GitHub Projects và Labels

**Gate field:** Project #1 phải có Custom Field single-select tên `Gate` với đúng `G0: Scope`, `G1: RF`, `G2: Protocol`, `G3: Embedded`, `G4: Integration`, `G5: Security/Reliability`, `G6: Pilot Acceptance`. Chạy `bash scripts/setup_project_gate.sh` khi GitHub CLI có Project scope; chưa coi là đã áp dụng trên GitHub nếu chưa kiểm tra lại kết quả. Mỗi Issue chọn đúng một Gate, không dùng bảy nhãn `gate:*`.

Theo dõi nhiệm vụ trên [LoRa P2P Hybrid TDMA — MVP Development](https://github.com/users/khanhpn308/projects/1). Tạo Issue bằng .github/ISSUE_TEMPLATE/ trong đúng repository, không để công việc quan trọng chỉ trong chat.

- Nhãn **layer:** hw-rf, fw-gateway, fw-node, mac-tdma, mqtt-infra, backend-go, web-ui, mobile-app.
- Nhãn **type:** contract, feature, bug, research, test, docs.
- Nhãn **risk:** rf-compliance, security, reliability.
- Nhãn **flag:** blocked-hw, needs-hil-test, contract-change.
- Nhãn **ai:** ready-to-gen, human-audit-req.

Các nhóm trên là **bộ phân loại được đề xuất/chốt về quy ước**, không chứng minh trạng thái hiện tại của GitHub Label API. Một issue dùng **một type**, một hoặc nhiều layer; risk/flag/ai chỉ dùng khi cần. Không dùng labels để thay Status/Priority/Sprint/Gate nếu đã có GitHub Projects Custom Fields.

**Trạng thái làm việc:** Backlog → Ready/Todo → In Progress → Review → Testing → Done; Blocked là trạng thái hoặc flag được thống nhất, không nhân đôi tùy tiện.

### Ví dụ Issue thay đổi MAC

**[MAC][G2] Introduce authenticated frame v1**:
1. Nêu requirement + rủi ro + ảnh hưởng kích thước frame.
2. Sửa đặc tả contracts/radio-mac trước.
3. Test vectors C/Go và kiểm thử malformed/replay/wraparound.
4. Đánh giá airtime, duty limits, khả năng tương thích Node/Gateway.
5. Review liên nhóm; chỉ sau khi được phê duyệt mới khóa format và triển khai.

## 8. Quản lý thay đổi contract / version / schema

**Không sửa ngầm giao thức.** Với bất kỳ thay đổi nào về byte order, field width, frame header, CRC/tag, nonce, schema MQTT hoặc API:

1. Tạo Issue loại type:contract; nêu consumers bị ảnh hưởng.
2. Cập nhật đặc tả, đánh dấu DRAFT/APPROVED, tạo ADR nếu ảnh hưởng kiến trúc.
3. Đưa vào test vectors (valid, invalid, truncated, duplicate, stale, replay, version mismatch).
4. Cập nhật firmware/Backend/clients với chính sách compatibility; không tự giả định deployment đồng thời.
5. Chạy CI contract + integration; lưu bằng chứng thực đo/HIL nếu liên quan thời gian/PHY.
6. Phê duyệt, tag/release theo kế hoạch.

Radio **8-byte MAC header hiện chỉ là đề xuất**, không thay thế thiết kế xác thực/anti-replay. CRC16 kiểm lỗi ngẫu nhiên, **không** chứng minh tính toàn vẹn mật mã. MQTT QoS 1 có thể gửi trùng; backend dùng event ID/epoch và idempotent write.

Các tài liệu hợp đồng: [Radio MAC](../../contracts/radio-mac/specification.md) · [MQTT](../../contracts/mqtt/topics.md) · [OpenAPI](../../contracts/api/openapi.yaml).

## 9. Quản lý lưu trữ và dữ liệu

| Dữ liệu | Nơi quản lý | Chính sách |
|---|---|---|
| Source C/Go/TypeScript/Dart | Git tracked source đúng module | Review, versioned, không commit build output |
| Mẫu cấu hình | .env.example, sdkconfig.defaults, deploy/ | Chỉ placeholder không chứa mật khẩu |
| Secrets/keys/certs TLS thật | Secure secret store / máy phát triển / CI secrets | Không commit, không đính vào Issue/PR |
| DB schema | backend-go/migrations/ | Migration version, review và test restore |
| PostgreSQL dữ liệu local | Docker named volume pg_data | Không là Git; backup/restore được kiểm tra |
| Log và dữ liệu RF nhỏ đã ẩn thông tin nhạy cảm | docs/verification/ hoặc tests fixtures | Có board rev, FW SHA, tham số, ngày, người đo |
| Traces / logs / binary / waveform lớn | GitHub Actions artifacts hoặc kho lab có kiểm soát | Link + SHA-256 + retention; không đẩy vào Git |
| Firmware .bin, release notes và checksum | GitHub Releases sau gate nghiệm thu | Tag phiên bản, build provenance, HIL evidence |
| File/thư mục sinh tự động | .gitignore / CI artifacts | Không commit node_modules, build, sdkconfig... |
| Dữ liệu mẫu/tự tạo cho test | tests/ hoặc simulator/scenarios/ | Không dùng dữ liệu thật chứa định danh/secret |

### Chống lộ bí mật

~~~bash
git status --short
git diff --cached --name-only
git check-ignore -v .env
git ls-files | grep -E '(^|/)(\.env|sdkconfig$|secrets/)|\.(pem|key|p12|pfx)$' || true
~~~

Lệnh grep chỉ là **kiểm tra sơ bộ**, không thay thế secret scanner. Nếu secret đã push: **thu hồi/rotate ngay**, sau đó xử lý cả lịch sử Git khi cần; thêm .gitignore không xóa secret khỏi lịch sử.

## 10. Môi trường và build local (WSL Ubuntu / VS Code)

Các lệnh sau thực thi từ **root repository**. Đây là bootstrap **chưa có server/TDMA hoàn chỉnh**.

~~~bash
# Kiểm tra cấu trúc scaffold
python3 scripts/verify_structure.py

# Backend Go: unit/build stub; hiện mới log thông báo
cd backend-go
go test ./...
go run ./cmd/server
cd ..

# ESP-IDF (phải kích hoạt ESP-IDF environment)
cd firmware/gateway_master
idf.py set-target esp32
idf.py build
cd ../sensor_node
idf.py set-target esp32
idf.py build
cd ../..

# Local PostgreSQL (Docker)
cp .env.example .env
# SỬA POSTGRES_PASSWORD trong .env (mật khẩu local riêng)
docker compose --env-file .env -f deploy/compose.yaml up -d postgres

# MQTT KHÔNG TLS: chỉ cho máy local và kiểm thử, không kết nối gateway ngoài mạng
docker compose --env-file .env -f deploy/compose.yaml --profile dev-insecure up -d mqtt-dev
~~~

**Đặc biệt:** docker-compose hiện chỉ cung cấp PostgreSQL và các MQTT profiles; **chưa có backend Go production service**. MQTT TLS yêu cầu cert/key thật tự cấp phát và cấu hình ACL/identity, không chạy an toàn chỉ nhờ --profile tls. [Deployment notes](../architecture/deployment.md) và [Deploy README](../../deploy/README.md).

## 11. CI/CD, môi trường và mức độ chứng minh

| GitHub Workflow hiện có | Chức năng thực tế | Chưa chứng minh |
|---|---|---|
| ci-foundation.yml | Kiểm tra cấu trúc và JSON syntax | Feature completeness |
| ci-contracts.yml | Cú pháp schema/vectors JSON | C/Go protocol conformance |
| ci-firmware.yml | Build hai ESP-IDF log-only scaffolds | SX1276, TDMA, RF hoặc HIL |
| ci-backend.yml | Go fmt/vet/test/build scaffold | MQTT/PostgreSQL/API business |
| ci-clients.yml | Kiểm tra placeholder README | React/Flutter compile |
| ci-integration.yml | Manual placeholder kiểm tra README | End-to-end Integration |

CI phải trở thành gate bắt buộc khi nhóm cấu hình nhánh bảo vệ. HIL cần **self-hosted runner có thiết bị và dụng cụ đo**, không giả định GitHub-hosted runner có kết nối ESP32. Không release RF firmware chỉ vì CI build xanh.

## 12. Lưu trữ kết quả đo, test và quy trình release

Mỗi báo cáo thử nghiệm nên có: **Test ID, Issue/Requirement ID, mã commit, firmware SHA, board/revision, ESP-IDF version, RF configuration, môi trường đo, thiết bị đo, số mẫu, số liệu thô được kiểm soát, kết quả, người thực hiện, đánh giá PASS/FAIL/NOT_VERIFIED**.

Đối với cảnh báo khẩn cấp phân biệt KPI-RF (Node → Gateway), KPI-E2E (Node → Backend/UI), điều kiện một/nhiều Node, P50/P95/P99; không tuyên bố mục tiêu <3s đã đạt khi chưa có kiểm thử.

Các release gate kế hoạch: G0 scope; G1 RF; G2 protocol; G3 embedded; G4 integration; G5 security/reliability; G6 pilot acceptance. Xem [Acceptance gates](../verification/acceptance-gates.md).

**Phiên bản MVP:** dự kiến tag theo hệ thống, ví dụ v0.1.0 (đề xuất, chưa phát hành). Release phải ghi rõ các thành phần, commit SHA, firmware binary checksum, DB migration version, contract compatibility, known issues và link test evidence.

## 13. Cách dùng AI Coding Assistant an toàn

AI là trợ lý tạo đề xuất, không có quyền tự phê duyệt đúng/sai của RF, bảo mật, compliance, time-critical firmware. Quy tắc tại [AGENTS.md](../../AGENTS.md), theo C/Go Standards và ADR/contracts liên quan.

Trình tự nên dùng:

1. AI đọc Issue, RTM, Architecture, Contract và phạm vi thư mục cho phép.
2. AI trình bày thay đổi dự kiến, rủi ro, tests và yêu cầu xác minh.
3. AI thay đổi **đúng thư mục**, bổ sung test và cập nhật docs liên quan.
4. Chạy local checks/CI; AI phải phân biệt kết quả đã chạy và chưa chạy.
5. Human review/CODEOWNERS; những phần ISR/timer/TLS/radio-security cần audit chuyên sâu.
6. Merge qua Pull Request, không cho AI tự kết luận đã đạt các Gate.

Không đưa production keys, token, thông tin nhạy cảm hoặc toàn bộ log chứa bí mật vào AI không được tổ chức phê duyệt. Không tin kết quả “AI simulator passed” thay cho test thật.

## 14. Workstreams kỹ thuật và thứ tự triển khai

**Workstream** là nhóm lĩnh vực kỹ thuật để định tuyến công việc, không phải Phase bắt buộc hoàn thành tuần tự. **Wave** dùng để gom đợt công việc (ví dụ `W1-05` = Issue thứ 05 trong Wave 1), còn **Gate G0–G6** là điều kiện nghiệm thu. Thứ tự triển khai dựa vào dependencies, khả năng sẵn sàng và nhân lực, không dựa vào thứ tự số Issue.

| Workstream | Chủ đích | Thư mục ưu tiên |
|---|---|---|
| Repo / Governance | Chính sách Git, Issue, CI, docs/ADR, hợp đồng sơ bộ | .github/, docs/, contracts/ |
| RF / Driver | SX1276 SPI, IRQ, ToA, an toàn RF, 2-board TX/RX | firmware/components/, tests/hil/ |
| Protocol / MAC / TDMA | Frame authenticated, sync, Master/Client, alert contention | contracts/radio-mac/, firmware/ |
| Network / Backend | MQTT TLS, idempotency, Go scheduler, Postgres schema | contracts/mqtt/, backend-go/, deploy/ |
| Frontend / Clients | API/RBAC, Dashboard và sau đó Mobile | contracts/api/, clients/ |
| Reliability / Pilot | RF/HIL load, offline, power reset, compliance/evidence | tests/, docs/verification/ |

Các nhóm có thể làm song song khi **interface phiên bản hóa đã chốt**. Không biến kế hoạch tuần từ tài liệu đề xuất thành deadline chắc chắn nếu chưa có nguồn lực/capacity và bằng chứng.

## 15. Checklist onboarding cho thành viên mới

- [ ] Có quyền GitHub repository/Project phù hợp (repo hiện **public**, phải tránh push tài sản riêng).
- [ ] Clone repo, cài toolchain cho miền mình, kiểm tra build scaffold.
- [ ] Đọc README, document này, ADR-0001, architecture/requirements, contract liên quan.
- [ ] Xem CODEOWNERS, branch/ruleset, labels và Issue Templates.
- [ ] Tạo một Issue nhỏ, branch, commit, PR và trải qua CI/review.
- [ ] Biết ranh giới AI vs yêu cầu human review; không cam kết timing/RF/HIL thiếu số đo.
- [ ] Hiểu nơi lưu dữ liệu test, secrets, migrations và release artifacts.
- [ ] Xác nhận quy trình khôi phục nếu Wi-Fi/backend mất kết nối.

## 16. Tình huống thường gặp

**Sửa một trường MQTT:** sửa contracts/mqtt → cập nhật Go/Gateway → test schema/duplicate/recovery → PR review cả hai owner.

**Sửa MAC Header hoặc TDMA:** Issue type:contract + flag:contract-change → ADR nếu thay đổi kiến trúc → golden vectors + timing budget → update Node/Gateway → HIL → Gate review.

**Thêm cảm biến Node:** xử lý trong sensor_node, chỉ sửa common khi thật sự dùng lại; xác định versioned payload/compatibility và đo ToA mới.

**Backend chưa có phần cứng:** dùng simulator/gateway-mqtt với dữ liệu tổng hợp theo contract; không coi đó là kiểm chứng RF.

**Muốn tách nhiều repo/microservices:** chỉ quyết định sau khi số lượng thành viên, chu kỳ release hoặc CI/performance chứng minh nhu cầu. Monorepo hiện là baseline hợp lý cho nhóm 6 người.

---

**Quy tắc chốt:** Đúng thư mục → đúng contract → có Issue/PR → có test & bằng chứng → có human review → mới được merge/release. Nếu nguồn và bằng chứng chưa đủ, đánh dấu **NOT_VERIFIED**, tuyệt đối không tự đánh dấu PASS.
