---
document_id: AI-TASK-START
version: 1.0.0-DRAFT
status: PROPOSED
approval: NOT_APPROVED
audience: HOST_COORDINATOR_AI_WORKER_AI_AUDITOR_HUMAN_REVIEWER
scope: repository-wide
source_issue: 70
activation: AGENTS.md_ROUTING_AFTER_HUMAN_REVIEW_AND_MERGE
---

# AI Task Start Protocol v1.0.0-DRAFT

> **Purpose:** An agent-readable, deterministic START gate. **Reading this runbook may be required by `AGENTS.md`; the runbook remains PROPOSED / NOT_APPROVED until human review.** It does not authorize unattended coding, new contracts, auto-merge, hardware flash, RF transmission or any G0–G6 approval. Approved Issue scope, Requirements, ADRs, contracts and current repository governance outrank this document.

## 0. Input → decision → permitted action

A task starts in `INTAKE`. No AI Worker may edit files until the deterministic Host/Human verifies `START_READY`. An agent describing itself as ready is **not** authorization. For conversational questions or read-only research, stop after reporting findings; do not invent an implementation Issue or make changes.

**One-line operator kickoff (recommended; the Issue should contain the remaining details):**

```text
Bắt đầu task #<issue-number>: <mục tiêu>. MODE=IMPLEMENT|REVIEW|RESEARCH.
Chạy Task Start Protocol và xuất Pre-Edit Report trước khi sửa bất kỳ file nào.
```

If the user supplies a clear objective but not an Issue, the agent may inspect relevant sources **read-only** and propose an Issue with exact allowed paths and AC. It must not pretend that a suggested scope is already approved.


```text
INTAKE → ISSUE_SCOPE → REPO_PREFLIGHT → SELECTIVE_CONTEXT
       → IMPACT_DISCOVERY → DECISION_GATE → PRE_EDIT_HANDOFF
                                              │
                     all conditions met ──────┤→ START_READY → scoped Worker
                     unmet or unknown ───────┘→ BLOCKED / READ_ONLY
```

**Separation of duties:** Host Coordinator = deterministic branch/scope/toolchain/evidence checks; Worker = scoped edits only in an authorized execution mode; independent Auditor = read-only immutable snapshot, findings/evidence; Human Engineer/Owner = permission and technical authority, HIL/RF/security/contract review, merge. Current operator-supervised `agy` pilot policy in `AGENTS.md` remains unchanged; this runbook does **not** activate autonomous execution.

### Choose task route from the Issue, not agent preference

| Route | Trigger | Required context (selectively loaded) | Execution boundary |
|---|---|---|---|
| `DOCS_ONLY` | Paths only in `docs/**`, `.github/**` or instructions | Scope/ADR/status sections actually affected; avoid programming Standard unless evaluating it | Do not change firmware/backend/contracts without new scope |
| `FIRMWARE_C` | Authorized `firmware/**` path | `AGENTS.md`, embedded instructions, [C Standard §0](firmware/C_CODING_STANDARD_V2.md) + relevant Rule IDs/§12/§13, exact silicon/API if relevant | SPI/ISR/security/RF and timing need appropriate human/HIL checks |
| `BACKEND_GO` | Authorized `backend-go/**` path | `AGENTS.md`, backend instructions, [Go Standard §0](backend-go/GO_BACKEND_ENGINEERING_STANDARD_V2.md) + relevant §2.x/§3/§4, exact `go.mod` | Contracts/DB migrations/new dependency not implicitly authorized |
| `CROSS_COMPONENT` | Issue explicitly allows both producer + consumer paths | Only relevant C + Go groups and approved `contracts/` or ADRs | Stop at unapproved interface boundary; coordinate owners |
| `RESEARCH_REVIEW` | No code implementation authorized | Target Issue/files and only necessary documentation/evidence | Read-only; no commit/branch push unless expressly authorized |
| `TOOLING_CI` | Issue explicitly allows scripts/CI/infra paths | Actual workflow/build instructions and relevant tool versions | No silent runner, permission, credential or deployment change |

### Architecture Context Gate — hành vi quyết định phần tài liệu cần đọc

Gắn một `TASK_ROUTE` hiện có ở bảng trên theo **phạm vi file**, rồi gắn một hoặc nhiều `ARCH_BEHAVIOR` từ bảng dưới theo **Issue Objective/AC và luồng sản phẩm bị tác động**. Các tag này chỉ là metadata routing trong handoff, **không** tạo route mới, Issue scope mới hoặc bắt buộc sửa contracts. Nếu task chạm cả producer và consumer nhưng allowlist không bao gồm hai phía, chỉ đọc phía ngoài scope, ghi impact và `BLOCKED_SCOPE` trước mọi edit bên ngoài.

| `ARCH_BEHAVIOR` / tín hiệu task | Trích đúng phần kiến trúc | Bổ sung nguồn chuẩn theo tác động (không đọc hàng loạt) |
|---|---|---|
| `EVENT_PERIODIC` — sensing, Trigger, Alert, Periodic ON/OFF, Priority queue | [System overview: Chế độ vận hành và luồng thiết bị](../architecture/system-overview.md); [ADR-0001: Mô hình vận hành Event-Driven](../adr/0001-hybrid-tdma.md), chỉ hai chế độ báo cáo + alert | RTM `ALERT-001`, `MAC-007`; radio-mac phần Priority Access **chỉ khi** firmware/MAC thay đổi |
| `TDMA_SCHEDULE` — Gateway Executor, Beacon, slots, offline, state transition | ADR-0001: Quyết định / Autonomy và failure invariants; system overview: Ranh giới trách nhiệm | [TDMA schedule §§2–3](../../contracts/radio-mac/tdma-schedule.md), [MQTT semantic rules §4](../../contracts/mqtt/semantic-rules.md), RTM `MAC-001/003/004`, `SYS-001/002` theo code path |
| `DEVICE_LIFECYCLE` — Node discovery, Pending/Accept/Reject, provisioning, activation | System overview: Chế độ vận hành; ADR-0001: Discovery → Approval → Provisioning → Activation | API/Auth/RBAC semantics cho Backend/Web; Radio MAC Join và MQTT downlink chỉ khi thực sự nằm trên đường thay đổi; `D01/D11/D13` nếu áp dụng |
| `MQTT_EVENTS` — gateway uplink, event_id, retry, storage/dedup | System overview: Ranh giới trách nhiệm; ADR-0001: Control plane và data plane | [MQTT semantic rules §§1–3](../../contracts/mqtt/semantic-rules.md) + **chỉ** affected topic/schema; RTM `DATA-001/002`. Multi-Gateway dedup cần kiểm event identity xuyên Gateway |
| `API_WSS_CLIENT` — REST/WSS, Web approval, dashboard state | System overview: Chế độ vận hành và Ranh giới; ADR-0001 chỉ khi API tác động lịch/Node lifecycle | Affected [API semantics](../../contracts/api/contract-semantics.md)/[OpenAPI](../../contracts/api/openapi.yaml)/[WSS](../../contracts/api/websocket.md), RTM `INT-002`/`SEC-002` |
| `RADIO_SECURITY_RF` — MAC bytes, Short ID, crypto/replay, PHY, ISR, LBT, airtime | ADR-0001: Ranh giới giao thức và tham số chưa chốt + applicable safety invariants; system overview: Tham số chưa được nghiệm thu | [Radio MAC §§2–4](../../contracts/radio-mac/specification.md), relevant `D01/D03/D04/D11`; SX1276/ESP32 datasheet & actual board revision only when needed; G1/G2/G3/G5 |
| `MULTI_GW_MESH` — multiple Gateway reception, dedup, relay/hop | System overview: Chế độ vận hành (candidate); ADR-0001: Mở rộng số Gateway và phạm vi định tuyến | Affected MQTT event identity/ingestion semantics if dedup; routing/forwarding **not approved** for Mesh. No implicit new topic or protocol |
| `ARCH_DOCS` — chỉnh design/ADR/requirements mô tả behavior | Chỉ sections thực sự sửa của architecture/ADR/RTM | Contract references được ảnh hưởng để phát hiện mâu thuẫn; không tải toàn bộ firmware/Backend standards |
| `NONE` — unrelated Harness, CI, formatting, non-product tooling | **Không nạp** system overview hay ADR-0001 theo mặc định | Chỉ Issue, tool/SOP/workflow và dependency liên quan; nếu tooling thực sự thay đổi product behavior thì phân loại lại |

**Quy tắc chọn và giới hạn context:**

1. Coordinator đọc **trạng thái/phê duyệt** và một đoạn lõi liên quan của `system-overview.md` nếu task sửa hành vi sản phẩm. Chỉ thêm những đoạn ADR-0001, RTM ID, contract và hardware/API authority cần để quyết định cụ thể; mặc định **1–3 nguồn chính**, mở rộng khi có phụ thuộc trực tiếp hoặc xung đột và ghi lý do. Không đưa toàn bộ Markdown, tất cả Rule IDs, toàn bộ D01–D13 hay cả hai coding standards vào prompt.
2. Ghi chính xác `SOURCE_REF` (base/head commit), `SOURCE_PATH`, `SECTION_OR_LINES`, `BLOB_SHA` hoặc hash nội dung đọc, và `DESIGN_STATUS` của từng nguồn. Excerpt phải lấy từ checkout/ref được pin, không lấy summary của Agent khác; nếu thiếu nội dung hoặc status phải ghi `NOT_VERIFIED`, dừng tại ranh giới phụ thuộc.
3. **Worker:** trước khi coding, Coordinator truyền một `ARCH_CONTEXT_HANDOFF` có `TASK_ROUTE`, `ARCH_BEHAVIOR`, **đoạn trích thật/requirement text**, identifiers/hashes ở bước 2, applicable invariants, Issue AC, relevant contract version và conflicts. **Chỉ đưa link hoặc filename là không đạt handoff.** Worker có thể mở bổ sung phạm vi hẹp ở cùng ref; nếu cần scope hoặc quyết định mới, dừng để Host/Owner xử lý.
4. **Auditor độc lập:** từ Issue AC, affected paths và frozen candidate, Auditor phải **tự chọn và đọc lại** các đoạn cần thiết từ source/ref có thể xác minh, không dùng danh sách/diễn giải của Worker làm bằng chứng duy nhất. So sánh thực thi/diff với hành vi, contract, negative cases và status; nêu file:line của finding cùng các nguồn tương ứng. Nếu nguồn không thể đọc, audit chưa độc lập hoặc không có candidate snapshot, ghi `NOT_VERIFIED` thay vì `AUDIT_PASS`.
5. **Mâu thuẫn:** nếu tài liệu kiến trúc mới mô tả 2-byte Node ID/header ~10B hoặc multi-Gateway nhưng versioned radio/MQTT/API/DB contract hiện hành vẫn khác, phân loại `BLOCKED_DECISION`, ghi cả path/version/status và owners để adjudicate. Không tự sửa wire schema, state machine, API hoặc DB; source ở trạng thái `CANDIDATE/DRAFT` không override contract đã duyệt. Khi cả hai nguồn Draft hoặc approval chưa rõ, không suy ra lựa chọn kỹ thuật đã chốt.
6. Không thay chín trường của **Pre-edit Report** trong §2. `ARCH_CONTEXT_HANDOFF` là phụ lục có thể kiểm tra và đính kèm receipts; Host giữ quyền quyết định `START_READY` trên scope/authority thực tế. Đây là **quy tắc agent routing**, chưa là bằng chứng rằng Host tự động enforce hoặc snapshot context đã được tạo trong một run thực.

**Context budget:** `AGENTS.md` + repository-wide instructions + applicable path-specific instructions → relevant Standard **§0** → exact `rg` Rule IDs/section ranges → direct dependencies/contracts. Never load legacy v1, traceability-only audits, training modules or [agent conformance scenarios](../verification/agent-conformance-scenarios.md) during ordinary implementation. A designated audit/evaluator Issue may authorize those sources.

## 1. Mandatory stage checks

| Stage | Required deterministic checks | Output / stop |
|---|---|---|
| T0 `INTAKE` | Record user objective, task route, deliverable, risks, read/write intent. Identify live GitHub Issue. | Missing Issue for write task → `BLOCKED_ISSUE`; read-only discovery is allowed |
| T1 `ISSUE_SCOPE` | Verify Issue, AC, exact root-relative `Target Directories (allowed paths)`, owner-approved scope, dependencies/contract approval, reviewers. Include tests/docs/migrations explicitly if needed. | Missing/ambiguous/unauthorized paths → `BLOCKED_SCOPE`; report needed path, **do not edit** |
| T2 `REPO_PREFLIGHT` | Validate repo/remote and baseline SHA; inspect current branch and entire worktree (tracked/untracked), HEAD against trusted base; Host creates Issue branch before Worker if approved. | Worker on `main` or dirty worktree → `BLOCKED_WORKTREE`; never clean/reset/stash user changes implicitly |
| T3 `SELECTIVE_CONTEXT` | Apply Architecture Context Gate: classify behavior tag(s), read exact approved/draft source status and bounded architecture/RTM/contract ranges, prepare verified excerpts + refs for Worker and separate Auditor reading. Also load applicable agent instructions/Rule IDs and check toolchain only if needed. | Missing source/excerpts → `NOT_VERIFIED`/`BLOCKED_AUTHORITY`; no Worker implementation before context handoff; never elevate Draft rules |
| T4 `IMPACT_DISCOVERY` | If MCP exposes `codegraph_explore`, inspect C/Go AST definitions, callers/callees/imports **first**. Check codebase for reusable symbols, composition root, radio ownership, ISR safety and cross-component impact. | Graph results outside allowed paths are **read-only**; required out-of-scope edit → `BLOCKED_SCOPE` |
| T5 `DECISION_GATE` | Classify interfaces/crypto/RF/legal, D01–D13, architecture ↔ current versioned-contract compatibility, dependencies and timing constraints; list affected owners and test levels. | Architecture/contract conflict or unresolved mandatory choice → `BLOCKED_DECISION`; missing AC evidence → `BLOCKED_EVIDENCE` |
| T6 `PRE_EDIT_HANDOFF` | Publish the exact 9-field report below; Host independently confirms all gates and grants only the scoped Worker mode already authorized. | `START_READY` only with verified scope/branch/authority; otherwise `READ_ONLY`/`BLOCKED` |

**CodeGraph evidence:** `codegraph_explore` is source AST discovery, **not** a proof of build, callback runtime, RF, HIL, timing, hardware wiring, approved contract or security. It does not index `contracts/**`, `docs/adr/**` or Markdown standards. If unavailable: record `NOT_RUN: codegraph_explore`, use narrow read-only `rg`/code inspection where allowed. If the Issue explicitly requires graph evidence, `BLOCKED_EVIDENCE` until that tool/equivalent audited proof is available. Ignore `simulator/**` and `scripts/**` hits as evidence that production firmware/backend code exists. `.codegraph/` caches must remain ignored/untracked and are not test artifacts.

### Repo preflight commands (Host-owned; run only in a trusted local checkout)

```bash
git remote -v
git branch --show-current
git status --porcelain=v1          # empty output required before worker edits
git rev-parse HEAD
git rev-parse origin/main          # only after verifying remote/trust
git diff --name-only origin/main...HEAD
# Firmware task: cat firmware/esp-idf-version.txt
# Go task: cat .go-version backend-go/go.mod; verify go env GOVERSION
```

**Not running these commands means `NOT_RUN`, even if a GitHub PR comparison shows clean changed-file scope.** Host checks cannot be replaced by an AI statement. Never treat ignored `.codegraph/` as permission for other dirty or secret files.

## 2. Pre-edit handoff — canonical nine required fields

Copy these **exact field names** for all C, Go and cross-component work. Value `NOT_VERIFIED` means evidence unavailable, not approval.

```yaml
ISSUE_URL: "<real-open-issue-URL>"
BASE_SHA: "<verified-base-commit>"
BRANCH: "<actual-non-main-branch>"
ISSUE_ALLOWED_PATHS:
  - "<exact-repo-root-relative-path>"
APPLICABLE_RULE_IDS: ["<relevant-v2-rule-IDs>"]
RULE_APPROVAL_STATUS: "PROPOSED / NOT_APPROVED or reviewed source status"
CONTRACT_CONFLICTS: []  # Record exact contract/version/path when present
BLOCKED_DECISIONS: []  # D01–D13 / missing owner decisions as applicable
TEST_PLAN: ["<commands/fixtures/evidence levels permitted by Issue>"]
```

**Host-only gate result, additional to the nine fields:** `TASK_ROUTE` + `START_DECISION=START_READY | READ_ONLY | BLOCKED` + `STOP_REASON`. An AI Worker cannot grant its own `START_READY`. Any inapplicable field is `NONE / N/A` with reason, not invented values. An Issue URL or SHA must never be guessed from a template.

## 3. STOP_AND_REPORT decision table

| Code | When to stop | Next permitted action |
|---|---|---|
| `BLOCKED_ISSUE` | No approved writable Issue, AC or target paths | Read-only analysis; produce an Issue/scope proposal |
| `BLOCKED_SCOPE` | Needed path (including tests/docs/migration) outside Issue, or scope mismatch | Request Owner to amend Issue **before** edits |
| `BLOCKED_WORKTREE` | Worker branch is main, dirty/untrusted tree, wrong repo/remote/branch | Report exact problem; no force-clean, reset, stash or destructive Git |
| `BLOCKED_AUTHORITY` | Approved sources conflict, current source missing, or draft mistaken for approved | Cite conflicting sources/status and required owner |
| `BLOCKED_DECISION` | Pending RF/legal, radio MAC, security, MQTT state/ACK, credential or versioned interface choice | Request domain/contract owner decision; no invented fallback |
| `BLOCKED_TOOLCHAIN` | Required exact ESP-IDF/Go compiler/SDK unavailable or wrong for implementation validation | Report actual version and remediation; docs-only may continue without compile |
| `BLOCKED_EVIDENCE` | Acceptance demands a verification method/device/graph not actually available | Report `NOT_RUN`; do not convert to PASS |
| `BLOCKED_SECURITY` | Secrets exposure, unexpected privileged tool, untrusted execution environment | Stop mutation/execution, escalate |

**Bounded autonomy:** A cleared `START_READY` permits only the Issue-approved files, APIs and tests within the existing supervised run. It does **not** authorize modifying `main`, cross-component contracts, CODEOWNERS/CI/dependencies, transmitting RF, flashing boards, unattended AGY integration, merging or release. Required human technical review still applies to ISR/SPI/Radio Owner, auth/crypto, contracts, RF/clock/timing.

## 4. Handoff after start (do not conflate gates)

Once the authorized Worker finishes: validate actual diff against Issue allowlist (including symlinks/untracked artifacts), build/test with exact pinned toolchain if available, record commands and failures, then submit immutable code+logs for independent read-only Auditor. Only Host-owned deterministic checks can assert software gate PASS. Final PR remains Draft until human review.

**Canonical final report keys** (same as both v2 Coding Standards):

```text
TASK_ID, ISSUE_URL, BASE_SHA, HEAD_SHA, BRANCH, CHANGED_PATHS,
SCOPE_CHECK, RULE_IDS_CONSULTED, RULE_IDS_APPLIED,
CONFLICTS_OR_EXCEPTIONS, BLOCKED_DECISIONS, TOOLCHAIN_VERSION,
TEST_COMMANDS, TESTS_RUN, NOT_RUN, KNOWN_LIMITATIONS,
EVIDENCE_STATUS, EVIDENCE_URLS, REVIEWERS_REQUIRED, PR_URL,
FINAL_STATUS
```

`CODE_WRITTEN`, `BUILD_VERIFIED`, `AUDIT_PASS`, `SIMULATION_VERIFIED`, `HIL_VERIFIED`, `RF_VERIFIED`, `SECURITY`, `CONTRACT` are **separate claims** requiring matching artifacts. A build, graph or Auditor PASS is not G0–G6, legal RF or timing approval.

## 5. Quick negative cases (runbook assertions; NOT_EXECUTED)

| Input condition | Required result |
|---|---|
| "Fix MQTT broker handling" but Issue allows only `firmware/` | `BLOCKED_SCOPE`; no Go/backend edits |
| Working tree contains an untracked secret; `.codegraph/` is ignored | `BLOCKED_WORKTREE`/`BLOCKED_SECURITY`, not clean |
| AI sees `MQ-009` v1 and proposes `EXPIRED → ACTIVE` | `BLOCKED_DECISION`; reviewed state contract required |
| CodeGraph unavailable but codebase can be reviewed via scoped reads | Report `NOT_RUN`; continue only if AC does not require graph proof |
| User asks only "review design" | `READ_ONLY`; do not write or push |
| Sensor Trigger Issue, Worker receives only link to `system-overview.md` | No implementation handoff: Coordinator must include bounded Event-Driven/Periodic excerpt with SHA and status |
| Multi-Gateway design proposes 2-byte ID / ~10B header while Radio MAC draft still uses 1B / 8B | `BLOCKED_DECISION`; escalate protocol to Node/Gateway/Security owners, do not change codec |
| Fresh Auditor relies only on Worker-supplied architecture summary | Architecture conformance `NOT_VERIFIED`; Auditor re-reads pinned source and frozen diff |
| Pure Harness onboarding/CI Issue with no product behavior impact | `ARCH_BEHAVIOR=NONE`; skip product architecture and unrelated C/Go Standards |
| C driver Issue depends on unapproved RF region/TX power | `BLOCKED_DECISION` for TX boundary; no unauthorized transmission |

**Exit criterion:** an operator can inspect the nine-field pre-edit report and the Host decision and unambiguously determine (a) whether code edits are authorized, (b) which files, (c) which rule/contract authority applies, (d) what remains BLOCKED, and (e) how evidence will be verified.
