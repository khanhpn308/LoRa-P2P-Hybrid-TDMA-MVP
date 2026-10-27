# Repository AI Agent Routing & Governance — Entry Point

> Status: P0 Issue #30 remains DRAFT. For the single **operator-supervised Issue #47 pilot**, the active choice is **Gemini Worker + Gemini Auditor through two separate direct Antigravity CLI sessions**. No unattended AGY Harness integration is authorized.

## Owner-selected native Full Access fast lane (2026-10-27)

For **ordinary GitHub Issue coding tasks**, the owner authorizes a native Codex/AGY Coordinator with the operator-selected **Full Access CLI preset** to complete Issue → separate branch/worktree → code → targeted local tests/build → fresh review → commit/push → Draft PR **without a per-Issue signer, manual pre-edit approval prompt or root GitHub login**. Trigger: `Chạy Issue #N`. Follow `docs/development/harness-fast-lane.md`.

This is a **native-agent workflow**, NOT a claim that the signed MCP `harness_prepare_issue` authorizes unsigned operations. Do not misrepresent the two execution paths. The owner controls actual CLI privileges; files inside this repository do not grant OS/MCP permissions. For normal work, perform required intake/standards/Issue-scope checks **internally**, without a mandatory human handshake or a long preliminary report, and report concise results in the Draft PR. Legacy P1-B2 supervised-pilot restrictions below are historical for that pipeline; they do not require operator approval for this explicit native fast lane. Sensitive RF/ISR/timer/PCB/security/contract changes still require human technical review, including scope/ADR compatibility, and no automatic merge, force-push to main, RF TX or flash is permitted. Never expose credentials; Full Access is not evidence that an Auditor is independent.

Always read `.github/copilot-instructions.md` and the active Issue's exact `Target Directories (allowed paths)` before routing.

## Task Start Gate — mandatory pre-edit handshake

Before any **write/implementation** task, AI Workers and Auditors MUST consult [AI Task Start Protocol](docs/development/AI_TASK_START_PROTOCOL.md) and the active Issue, then complete the scoped `INTAKE → ISSUE_SCOPE → REPO_PREFLIGHT → SELECTIVE_CONTEXT → IMPACT_DISCOVERY → DECISION_GATE → PRE_EDIT_HANDOFF` sequence. The deterministic Host/Human, not the Worker, decides `START_READY | READ_ONLY | BLOCKED`. Do not edit before `START_READY`; produce the canonical 9-field pre-edit report (see protocol §2) and preserve the exact unified final-report fields below. Ordinary answers and authorized research may remain `READ_ONLY` without creating or modifying repository files.

For `firmware/**` use only relevant C v2 Rule IDs; for `backend-go/**` use only relevant Go v2 Rule IDs; for cross-component work inspect both plus current contracts. Source graph and discovered paths never expand Issue scope. The new protocol is `PROPOSED / NOT_APPROVED`; mandatory consultation does not activate draft-only engineering requirements, autonomous harness execution, auto-merge, RF TX, flash or G0–G6 PASS.

## Context hygiene & Do-Not-Load files

To avoid context dilution and v1/v2 rule collisions during implementation or code review:
- **DO NOT read or load** `docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V1.0.md`, `docs/development/firmware/C_STANDARD_SOURCE_TRACEABILITY.md`, `docs/development/firmware/ARCHITECTURE_DOCUMENTATION_AUDIT.md`, or `docs/verification/agent-conformance-scenarios.md` unless an Issue explicitly authorizes historical documentation auditing, traceability review or harness grading.
- **Selective section loading:** Read §0 of the relevant v2 Standard, then only mapped module subsections/Rule IDs using a bounded file-range read or `rg`. Do not load the full Coding Standard for a narrowly scoped change. References to the v1 provenance base are locators for authorized audits, **not instructions to load legacy rules**.

## Go Backend standard routing — AI Workers and Auditors

For any Issue authorizing a change within `backend-go/**`, **every AI Worker and AI Auditor MUST read and assess** the applicable sections and Rule IDs of [Go Backend Engineering Standard v2.0.0-DRAFT](docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V2.md) before editing or issuing a verdict. Reading is an active routing requirement; **the standard remains `PROPOSED / NOT_APPROVED`** and does not supersede approved requirements, ADRs, versioned contracts or the Issue's allowed paths.

1. Read v2 metadata/§0, Google source precedence/§1, affected v1-mapped rule groups/§2, contract conflict table/§3 and evidence contract/§4. Do **not** load 134 rules when only one module group is relevant.
2. Preflight: inspect real `backend-go/go.mod`, root `.go-version`, branch/worktree, correct Go toolchain, `.github/instructions/backend.instructions.md`, `contracts/mqtt/**` and `contracts/api/**` as relevant. Go's actual implementation behavior, source approval status and pending D01–D13 decisions matter more than a Draft rule.
3. **Unified reports:** Pre-edit: `ISSUE_URL`, `BASE_SHA`, `BRANCH`, `ISSUE_ALLOWED_PATHS`, `APPLICABLE_RULE_IDS`, `RULE_APPROVAL_STATUS`, `CONTRACT_CONFLICTS`, `BLOCKED_DECISIONS`, `TEST_PLAN`. Final task/review: `TASK_ID`, `ISSUE_URL`, `BASE_SHA`, `HEAD_SHA`, `BRANCH`, `CHANGED_PATHS`, `SCOPE_CHECK`, `RULE_IDS_CONSULTED`, `RULE_IDS_APPLIED`, `CONFLICTS_OR_EXCEPTIONS`, `BLOCKED_DECISIONS`, `TOOLCHAIN_VERSION`, `TEST_COMMANDS`, `TESTS_RUN`, `NOT_RUN`, `KNOWN_LIMITATIONS`, `EVIDENCE_STATUS`, `EVIDENCE_URLS`, `REVIEWERS_REQUIRED`, `PR_URL`, `FINAL_STATUS`. Record actual execution; never elevate `PROPOSED` to `APPROVED` or `NOT_RUN` to PASS.
4. **STOP_AND_REPORT** when a task requires unauthorized file/dependency, credentials/security scheme, RF/MAC wire changes or unapproved MQTT state/ACK transitions. In particular, v1 `MQ-009` does not authorize direct `PROPOSED/SENT/EXPIRED → ACTIVE` when draft MQTT semantics currently describe `STAGED → ACTIVE`; escalate reconciliation policy rather than choosing silently.
5. Do not auto-approve/merge, treat scaffold build as an integrated service, or infer HIL/RF/G4/G5 PASS. Current firmware Harness/pilot restrictions below remain unchanged and must **not** be interpreted as granting unattended Go Agent execution privileges.

If the v2 Draft source cannot be read or conflicts with approved authority, mark `NOT_VERIFIED/BLOCKED` as appropriate rather than asserting conformance. Google Go Style [Guide](https://google.github.io/styleguide/go/guide) governs canonical style, [Decisions](https://google.github.io/styleguide/go/decisions) supplements it, and [Best Practices](https://google.github.io/styleguide/go/best-practices) are advisory; none defines radio/network business contracts.

## Firmware standard routing — AI Workers and Auditors

Read `.github/copilot-instructions.md`, `.github/instructions/embedded.instructions.md`, `docs/architecture/system-overview.md`, `docs/verification/acceptance-gates.md`, and `docs/development/agent-harness-firmware.md` before firmware tasks.

For an Issue whose approved `Target Directories (allowed paths)` include `firmware/**` or a file beneath `firmware/`, **every AI Worker and AI Auditor MUST read and assess** the applicable parts of [C Firmware Coding Standard v2.0.0-DRAFT](docs/development/firmware/C_CODING_STANDARD_V2.md) **before proposing code changes or issuing a review verdict**. This read requirement is active as an agent-routing instruction; the Standard itself remains `PROPOSED / NOT_APPROVED` and is **not an approved engineering-policy replacement**.

1. Read the Standard's metadata/status, §0 agent entrypoint, the applicable module/rule-ID tables, §12 blocked decisions, and §13 evidence/report contract; use selective loading rather than copying the entire document into each task.
2. Cross-check each relevant Rule ID against the Issue's exact allowed paths, approved Requirements/ADRs, current `contracts/`, exact ESP-IDF v6.1 API documentation and silicon/board authority where applicable. Prefer higher-authority approved sources whenever the Draft conflicts or lacks support.
3. **Unified reports:** Pre-edit: `ISSUE_URL`, `BASE_SHA`, `BRANCH`, `ISSUE_ALLOWED_PATHS`, `APPLICABLE_RULE_IDS`, `RULE_APPROVAL_STATUS`, `CONTRACT_CONFLICTS`, `BLOCKED_DECISIONS`, `TEST_PLAN`. Final task/review: `TASK_ID`, `ISSUE_URL`, `BASE_SHA`, `HEAD_SHA`, `BRANCH`, `CHANGED_PATHS`, `SCOPE_CHECK`, `RULE_IDS_CONSULTED`, `RULE_IDS_APPLIED`, `CONFLICTS_OR_EXCEPTIONS`, `BLOCKED_DECISIONS`, `TOOLCHAIN_VERSION`, `TEST_COMMANDS`, `TESTS_RUN`, `NOT_RUN`, `KNOWN_LIMITATIONS`, `EVIDENCE_STATUS`, `EVIDENCE_URLS`, `REVIEWERS_REQUIRED`, `PR_URL`, `FINAL_STATUS`. Record actual execution; never elevate `PROPOSED` to `APPROVED` or `NOT_RUN` to PASS.
4. If a requested action depends on an unresolved protocol, RF/legal, ISR/timing, security, pinout or interface decision, or requires edits outside authorized paths, **STOP_AND_REPORT** the decision/owner and seek explicit authorization. Reading the Draft never grants permission to change contracts, transmit RF, flash hardware, auto-merge or upgrade G0–G6.

If the Standard is unavailable or cannot be read, record the blocker and request the missing source; do not silently claim conformance. Existing supervised-agent pilot constraints, Host/Auditor separation, and human review/merge controls below remain unchanged.

## CodeGraph MCP usage (`codegraph_explore`) — discovery vs. authority

1. **Primary code discovery, when available:** MUST use `codegraph_explore` as the first-pass source-discovery tool when it is available, rather than broad grep/find/full-file reads to locate C/Go symbol definitions and source-AST callers/callees. For Go inspect `backend-go/cmd/server/main.go` composition-root wiring (`AI-001`, `AR-002`), reusable types (`AI-005`), import/dependency direction (`AR-004`). For C inspect Single Radio Owner and SX1276 SPI/state-transition callers (`RTOS-001`, `RAD-002`), ISR/ESP_TIMER_ISR paths (`RTOS-003`, `RTOS-006`, `RAD-003`) and component dependencies (`ARCH-007`).
2. **Graph visibility ≠ edit authorization:** Source graph results may reveal cross-component callers/consumers (`GOV-007`, `ARCH-004`) but files outside the Issue's exact `Target Directories (allowed paths)` remain read-only. If changes outside scope are required, **STOP_AND_REPORT** and request owner-approved scope expansion (`GOV-001`, `AI-002`).
3. **Static graph ≠ contract/runtime evidence:** CodeGraph's C/Go AST graph does **not** index `contracts/**`, ADRs or Markdown rulebooks, and may miss dynamic dispatch, external calls, build tags and runtime behavior. Disregard simulator/scripts hits as proof of production `firmware/**`/`backend-go/**`. A clean graph never establishes `BUILD_VERIFIED`, `CONTRACT`, `HIL_VERIFIED`, `RF_VERIFIED`, timing or security PASS.
4. **Unavailable tool:** If `codegraph_explore` is not exposed in the agent's tool environment, report `NOT_RUN` for graph checks and use narrow read-only `rg` and code inspection where sufficient; do not claim graph-backed verification. Stop if an acceptance criterion explicitly requires CodeGraph evidence.
5. **Index/worktree hygiene:** `.codegraph/` SQLite index/WAL artifacts must be ignored by `.gitignore`, remain untracked, never staged/committed and never cited as test evidence. An ignored cache does not excuse other dirty worktree paths.

## Architecture and authority
- ESP32 + SX1276, ESP-IDF/FreeRTOS, pure C; custom LoRa **P2P**, not LoRaWAN. Gateway executes real-time hybrid TDMA locally; Go backend plans/version-controls schedules.
- Approved requirements/ADRs and versioned `contracts/` outrank Agent output. Semtech datasheet (correct revision) governs register semantics. Human verification governs real RF/HIL/timing claims.
- Current repository firmware is a **scaffold**. Never claim imported SX1276 driver, tested RF or TDMA implementation exists.
- Experimental driver from `khanhpn308/esp32e_sx1768-915Mhz` is reference only. Do not copy code or modify wire protocol without a separate scoped Issue and review.
- DO NOT change PCB pin mapping, RF band/power, cryptographic fields, MAC frame layout, MQTT/API/DB contracts, firmware target version, or branch settings on an Agent's initiative.
- **Approved toolchain baseline: ESP-IDF `v6.1` (ADR-0003, owner 2026-10-22)**. Read `firmware/esp-idf-version.txt`; Gateway/Node CI and Harness must use exactly this release. Do not silently downgrade, use floating `release-v6.1`, or treat a build as HIL/RF evidence.

## Roles and execution order
1. **Host Coordinator (deterministic):** Issue/scope validation, clean branch/worktree, bounded process timeouts, compiler/test logs, diff checks, evidence manifest, human stop gates.
2. **Worker (Issue #47: Gemini via operator-direct `agy` CLI):** creates only the Issue-approved harmless README change in a controlled branch under human-supervised permissions. Cannot certify its own code. The Codex Worker and adapters in P0/P1 historical draft are legacy and NOT the Worker for this pilot.
3. **Auditor (fresh operator-direct Antigravity `agy` Gemini session):** review immutable, read-only snapshot without sharing the Worker's conversation or writable working tree. No edits/tools granted. Return PASS/FAIL/INCONCLUSIVE with file:line findings and gaps. Sessions differ, but Gemini Worker and Auditor are **not model/provider-independent**.
4. **Human engineer:** RF/hardware/ISR/timer/security/contract decisions, HIL measurement approval, PR review and merge.

The Host, never an Agent's text or exit code alone, decides whether a gate passed. `agy` must return `status=SUCCESS`, schema-valid `structured_output` and complete exact `reviewed_scope`. AGY's read-only instruction is NOT a security boundary; a disposable environment is required for unattended execution. Flow: Issue -> isolated branch -> Worker -> scope gate -> deterministic tests/build -> independent Auditor -> evidence -> DRAFT PR -> human review. A failed or unavailable gate is NOT_VERIFIED/FAIL and blocks acceptance.

## Stop conditions
- Changed file outside approved Issue `Target Directories (allowed paths)`, secrets, external symlink, untrusted tool configuration, unauthorized radio command, unapproved version/contract change.
- `main` branch, dirty worktree before run, missing toolchain or test logs, unbounded retries, model/tool failure, unsupported hardware assumptions.
- Never auto-merge, auto-flash, auto-transmit RF, or bypass branch protections. Do not run Agent with host-global credentials or unreviewed shell permissions.

## Verification semantics
`CODE_WRITTEN` / `BUILD_VERIFIED` / `AUDIT_PASS` / `SIMULATION_VERIFIED` / `HIL_VERIFIED` / `RF_VERIFIED` are **independent evidence dimensions**. Missing proof is `NOT_VERIFIED`. Build or audit never implies hardware RF PASS.

See historical P0 workflow: [Firmware Agent Harness](docs/development/agent-harness-firmware.md). **Current supervised pilot instructions:** [Dual AGY Pilot](docs/development/agy-supervised-pilot.md).


## Integration guard — Issue #54

On `main`, the selected user-facing supervised model is **Gemini Worker via
operator-direct official `agy`** and a separate **Gemini Auditor via a fresh
operator-direct `agy`** context. This is **not** the legacy P0
`scripts/agent_harness/run.py --execute` pipeline, which still runs Codex
Worker and is NOT approved for the dual-AGY workflow. The selected P1-B2
`p1/pilot.py` is a **fake/simulated** deterministic coordinator, not a
live provider adapter. Neither component may be passed off as autonomous
Gemini-to-Gemini Harness execution. Consumer AGY credentials must never
be embedded into a third-party autonomous Harness. H01/H02/H04 are
NOT_VERIFIED. See `docs/development/agy-supervised-pilot.md` for the
historical Issue #47 operator-only runbook.
