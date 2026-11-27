# Harness V2.0 — Phase 01 As-Is Audit & Baseline Report

**Issue:** [#422](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/422) (`[Harness V2][P01-B]`) · **Mode:** `AUDIT_ONLY` (read-only audit subject; 3 authorized report artifacts only)
**Audited Main Commit:** `fdbc9a5c1266073f84e2d4e841671e75d6690d95` · **Tree SHA:** `d065262bdce0880113c755103fe587dbb4edffcd`
**Isolated Worktree / Branch:** `/home/khanh/projects/iot/LoRa-P2P-issue-422` (`docs/422-p01-baseline-audit`)
**Frozen Pre-Report Candidate Fingerprint:** `afb33c526b114da0146e6a57554f555d56610501d1645afeb04f0774d377207d`
**Authority Basis:** [HARNESS_SPEC.md](../HARNESS_SPEC.md) `v0.2.0`, [HARNESS_MASTER_PLAN.md](../HARNESS_MASTER_PLAN.md) `v0.2.0`, [P01_EXECUTION_PLAN.md](P01_EXECUTION_PLAN.md) `v0.3.0`, [P01_INDEPENDENT_AUDIT_PROTOCOL.md](P01_INDEPENDENT_AUDIT_PROTOCOL.md) `v0.3.0`, live `AGENTS.md` (`EV-001`)
**Companions:** [HARNESS_RTM.json](HARNESS_RTM.json) (45 rows) · [EVIDENCE_MANIFEST.json](EVIDENCE_MANIFEST.json) (26 evidence receipts)

---

## 0. Executive Summary & Verdicts

| Verdict Dimension | Status | Basis |
|---|---|---|
| **Audit Delivery** | `PARTIAL` (`AUDIT_NOT_VERIFIED`) | All 8 Work Packages (`A -> B -> H -> C -> D -> E -> F -> G`), 45/45 `H2-*` RTM rows, 12/12 `H-A01..H-A12` cases, local corpus offline check (`--network=none`), baseline critical triage, and external evidence manifest completed without mutating the audit subject. However, `invoke_subagent` returned `subagent "Fresh-Independent-Auditor" not found or not allowed to be invoked`, so fresh independent Auditor verification is `AUDIT_NOT_VERIFIED` (no self-certification). |
| **As-Is Conformance to SPEC v0.2.0** | `FAIL` | 0 `VERIFIED`, 24 `PARTIAL`, 16 `GAP`, 3 `FAIL` (`H2-INS-03`, `H2-ENV-02`, `H2-ENV-04`), 1 `NOT_VERIFIED` (`H2-FBK-05`), 1 `CONDITIONAL_NOT_EXERCISED` (`H2-ORC-08`). Two P0 blockers exist on `main`: absent runtime least-privilege sandboxing in Native Fast Lane (`H2-TOL-02`) and failing baseline gates (`SECRET-SCAN` false positive + Go CI `gofmt` failure, `H2-ENV-04`). |
| **HIL / RF / Live E2E / Production Security** | `NOT_VERIFIED` | No physical hardware, RF transmission, live Mosquitto/PostgreSQL restart E2E, or human security sign-off executed in P01. |
| **Ready to Merge** | `false` | Read-only audit deliverable; requires fresh Independent Auditor report and Owner review (no auto-merge). |

### Key Headline Findings

1. **Deterministic Host core is strong (416/416 unit tests PASS), but fragmented and bypassed in daily CLI use (`EV-012`, `EV-024`, `EV-025`):** `agent_context.py`, `standards_policy.py`, `quality_gates.py`, `pr_review.py`, and `p1/*` pass all 416 Harness unit tests and enforce fail-closed SHA/scope/partition invariants. However, Native Fast Lane relies on operator Full Access instructions rather than runtime Host interception, and `run.py` / `p1/cli.py` / `p1/auto_issue.py` are disconnected or blocked on live Issue #422.
2. **Baseline `main` fails two automated gates (`EV-011`, `EV-016`, `EV-017`):**
   - **`SECRET-SCAN` P0 (`quality_gates.py`):** Fails on `clients/web-dashboard/tests/integration.test.ts:31` (`access_token: "jwt-token-admin01-session"`). Confirmed **false positive** on a mocked unit-test response (`EV-013`). `verify_no_secrets.py` also fails on 6 tracked files (`service_test.go`, `login/page.tsx`, `users/page.tsx`, `types/api.ts`, `integration.test.ts`, `quality_gates.py` itself) due to loose `password[:=]` regex matching. `gitleaks --redact` flags 10 test/hash strings (`EV-014`). **Zero real credentials found.**
   - **Go CI (`CI - Backend Go Scaffold`):** Runs `46049348761`, `46048385376`, `46047680659` all failed at step `Go formatting` (`test -z "$(gofmt -l .)"`, exit 1) due solely to doc-comment list indentation in `backend-go/internal/presence/rf_tracker.go:140-145` (from commit `67e3bcf`). In pinned `golang:1.27.3-alpine`, `go vet ./...`, `go test ./...` (13 packages), and `go build ./cmd/server` all **PASS (exit 0)** (`EV-017`).
3. **Clean-checkout offline builds fail (`EV-018`, `EV-022`):** `toolchains/resolver.py` enforces `--network=none`, causing disposable ESP-IDF `v6.1` builds of `gateway_master` and `sensor_node` to fail (exit 2) fetching `espressif/mqtt (1.1.0)` when `managed_components/` is absent from a fresh worktree. Web `integration.test.ts` fails in a clean worktree (exit 1) because `node_modules` (`react`) is absent. Host `go` is `1.27.1` vs pinned `.go-version` `1.27.3` (`EV-004`).
4. **Authority drift (`ADR-0004` vs TDMA) & broken/missing references (`EV-006`, `EV-007`):** `snapshot.py` (`REFERENCES` -> `0001-hybrid-tdma.md`), `.agent-harness/auditor.md` (`backend-controlled schedule`), `standards_policy.py` (`TDMA`/`SC` rule groups), `docs/adr/README.md`, `docs/hardware/sx1276/README.md`, and `ESP32_LORA_ENGINEERING_PLAYBOOK.md` still carry superseded Hybrid TDMA guidance after ADR-0004 (#273). Two ADRs share number `0004`. `coding-standards.md` has a broken link to non-existent `.github/instructions/backend.instructions.md`; `harness-fast-lane.md` references non-existent `mcp_execution.py` and `harness_prepare_issue`.
5. **Local corpus offline sufficiency verified (`EV-025`, `EV-026`):** Under `docker run --network=none` against the frozen worktree (zero PDFs present), all `248/248` `knowledge/` heading anchors in `REFERENCE_INDEX.md` resolve cleanly and all `45/45` `H2-*` IDs match across `HARNESS_SPEC.md`, `HARNESS_MASTER_PLAN.md`, and `REFERENCE_INDEX.md`.

---

## 1. WP-A — Frozen Baseline, Capability Matrix & Inventory

### 1.1 Frozen Snapshot & G0 Host Context

| Item | Verified Value | Evidence |
|---|---|---|
| Base / Audited Commit | `fdbc9a5c1266073f84e2d4e841671e75d6690d95` (`docs(harness): publish P01 audit plan and protocol v0.3.0`) | `EV-001`, `EV-002` |
| Audited Tree SHA | `d065262bdce0880113c755103fe587dbb4edffcd` | `git rev-parse HEAD^{tree}` |
| Candidate Fingerprint (`--fingerprint-only`) | `afb33c526b114da0146e6a57554f555d56610501d1645afeb04f0774d377207d` (`changed_paths: []`) | `EV-002` |
| `AGENTS.md` Git Blob SHA | `14f2d7335c41a2ba38f3915ec023dd037603cfb7` | `EV-001` |
| `AGENTS.md` SHA-256 / Size | `09212ed3ac8b74476f915e2e168950bdb8d2d2cf26e6dba3f8efacccc30fcbe7` (`10,784` bytes, `33` lines) | `EV-001`, `EV-003` |
| Dirty Main Workspace Preserved | Canonical `/home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP` left untouched (`M firmware/gateway_master/sdkconfig.defaults` + untracked deploy/backfill files); audit executed in isolated clean worktree `/home/khanh/projects/iot/LoRa-P2P-issue-422`. | `EV-001` |

### 1.2 Approved Capability, Budget & Toolchains

- **Authorized outputs:** Only `HARNESS_BASELINE_REPORT.md`, `HARNESS_RTM.json`, `EVIDENCE_MANIFEST.json` under `docs/harness/phase-01/`. Raw logs stored externally in `/tmp/p01-evidence-422/`.
- **Timeouts & Cleanup:** Default command timeout `60s`, container build `120s`, Auditor `300s`; disposable `/tmp/p01-idf-copy` created and removed cleanly after `EV-018`.
- **Host & Container Toolchains (`EV-003`, `EV-004`, `EV-005`, `EV-008`):**

| Tool / Runtime | Observed Version / State | Pinned / Expected | Gap / Note |
|---|---|---|---|
| `git` / `python3` / `gh` | `git 2.43.0`, `Python 3.12.3`, `gh 2.45.0` | Python `>=3.10` | Ready (`EV-008`) |
| `agy` / `codex` | `agy 1.5.18` (PATH), `codex-cli 0.172.0` (`~/.local/bin/codex`) | Either CLI | `harness_doctor.py` warns `codex_cli` missing because `~/.local/bin` is not in default PATH (`EV-008`) |
| `go` (host vs Docker) | Host `/usr/local/go/bin/go` is `go1.27.1` (not in default PATH); Docker `golang:1.27.3-alpine` (`fa3d596898d9`) | `1.27.3` (`.go-version`, `backend-go/go.mod`) | Host Go `1.27.1` drifts from pinned `1.27.3` (`EV-004`, `EV-017`) |
| `espressif/idf:v6.1` | Docker `sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c` | `v6.1` (`firmware/esp-idf-version.txt`) | Image cached, but `managed_components/espressif__mqtt` absent in clean worktrees (`EV-018`) |
| `node` / `npm` | `v22.23.2` / `12.0.2` (`~/.gemini/antigravity/bin/`) | `clients/web-dashboard/package-lock.json` | No `node_modules` in clean worktree (`EV-022`) |
| `codegraph` | `1.6.2` (`~/.local/bin/codegraph` & `codegraph-mcp`) | Optional / mandatory for CCARS/GOCARS | Main checkout indexed (`393` files, `7,297` nodes); new worktree `initialized: false` (`EV-004`, WP-A) |
| `gitleaks` / `actionlint` | `gitleaks 8.30.1`, `actionlint v1.7.7` | Security / CI lint | Both installed in `~/.local/bin` / `~/go/bin` (`EV-004`) |

### 1.3 Active Repository Entrypoints, Roles, Policies, Scripts & State Stores

| Category | Paths (Verified at `fdbc9a5c`) | Role / Purpose | Status |
|---|---|---|---|
| **Root & Role Instructions** | `AGENTS.md` (10,784B), `.agent-harness/worker.md` (1,209B), `.agent-harness/auditor.md` (1,943B), `.agent-harness/security/provider-decision.md` (4,241B), `.agents/agents/harness-coordinator.md` (13,456B), `.agents/agents/c-structural-refactor.md` (8,296B), `.agents/agents/gocars-refactor/agent.md` (20,971B) | G0 root contract, legacy P0 pilot worker/auditor prompts, AGY provider boundary, Native Fast Lane & CCARS/GOCARS agents | Active; overlapping & contains stale TDMA/tool refs |
| **Harness Core & G0/Selector** | `scripts/agent_harness/agent_context.py`, `standards_policy.py`, `scope.py`, `snapshot.py`, `quality_gates.py` | G0 AGENTS SHA-256 check, C/Go V2 rule routing & ADR-0005 partitions, allowlist guard, audit snapshot, offline receipt validator | Active & unit-tested (416 tests PASS); `snapshot.py` & `standards_policy.py` retain TDMA |
| **Execution Runners & Adapters** | `scripts/agent_harness/run.py`, `pr_review.py`, `pr_review_policy.py`, `adapters/{codex.py,antigravity.py,audit.schema.json}`, `toolchains/{resolver.py,check.py}` | Codex+AGY supervised runner, read-only PR reviewer (PR-01..08), JSON schemas, Docker ESP-IDF resolver | `pr_review.py` active; `run.py` unused in Native Fast Lane |
| **P1 & MCP Subsystem** | `scripts/agent_harness/p1/{cli.py,state.py,worktrees.py,verify.py,host_gate.py,pilot.py,pilot_demo.py,auto_issue.py,draft_preview.py,process.py,runtime_boundary.py}`, `mcp_server.py`, `mcp_host.py`, `harness_mcp_setup.py` | P1-A SQLite worktree prep, P1-B2 simulated loop, P1-B3 Enterprise AGY (disabled), 3 read-only MCP stdio tools | Unit-tested; MCP SDK not installed; Enterprise runner missing `/etc/lora-harness/provider-policy.json` |
| **Doctor & Repo Guards** | `scripts/setup_harness.sh`, `scripts/harness_doctor.py`, `scripts/verify_structure.py`, `scripts/verify_no_secrets.py`, `scripts/setup_project_gate.sh` | Environment diagnostics, monorepo structure check, tracked secret scan | `doctor` & `structure` PASS; `verify_no_secrets.py` FAIL (6 false positives) |
| **CI Workflows (8)** | `.github/workflows/{ci-agent-harness.yml,ci-backend.yml,ci-clients.yml,ci-contracts.yml,ci-firmware.yml,ci-foundation.yml,ci-integration.yml,harness-issue.yml}` | GitHub Actions checks + disabled Enterprise issue workflow | Go CI failing on `gofmt`; `ci-clients` & `ci-integration` are stubs; `actionlint` flags `harness-isolated` |
| **Harness Tests & Fixtures** | `tests/agent_harness/test_*.py` (21 files, 416 tests), `fixtures/{pr_review,quality_gates,security_pilot}/` | Regression tests for G0, selector, gates, PR review, P1 state/pilot, adapters, configs | PASS (`416/416`, `EV-012`) |
| **State Stores** | `.lora-p1-state/state.sqlite` (external parent dir, `p1/state.py`), `/tmp/lora-harness-*/manifest.json` (`run.py`), `/tmp/harness-evidence-pr-*/` (`pr_review.py`) | SQLite WAL job/pilot ledger + ephemeral evidence dirs | Unused by Native Fast Lane; no repo `PROGRESS.md` or `feature_list.json` |
| **Product Consumers** | `firmware/{gateway_master,sensor_node,components/*}`, `backend-go/{cmd,internal,migrations}`, `clients/{web-dashboard,mobile-app}`, `contracts/{api,mqtt,radio-mac}`, `deploy/` | Embedded C/ESP-IDF v6.1, Go 1.27.3 Modular Monolith, Next.js Web / Android docs, Mosquitto TLS, PostgreSQL | Real code exists across firmware, Go, Web, contracts; `mobile-app` & `simulator` remain README stubs |

---

## 2. WP-B — Dependency, Authority & Conflict Analysis

### 2.1 Directed Dependency & Consumer Map (Summary)

- **G0 & Rules Chain:** `AGENTS.md` + `C_CODING_STANDARD_V2.md` + `GO_BACKEND_ENGINEERING_STANDARD_V2.md` → `standards_policy.py` → `agent_context.py` → consumed by `.agents/agents/{harness-coordinator,c-structural-refactor,gocars-refactor}`, `run.py`, `pr_review.py`, and `quality_gates.py` (`STANDARDS-CHECK`).
- **Scope & Quality Chain:** GitHub Issue body (`## Target Directories (allowed paths)`) → `scope.py` → `standards_policy.py` / `p1/cli.py` / `pr_review.py` → `quality_gates.py` (`SECRET-SCAN`, `DIFF-CHECK`, risk-routed checks).
- **Review & Audit Chain:** `pr_review.py` + `pr_review_policy.py` + `.github/CODEOWNERS` + `adapters/antigravity.py` + `audit.schema.json` → `Fresh-Independent-Auditor` → Host PR-01..PR-08 verdict (`ready_to_merge: false`).

### 2.2 Conflict, Redundancy & Stale Reference Register

| ID | Severity | Conflicting / Stale Artifact(s) | Authoritative Source | Observed Conflict / Defect | Evidence |
|---|---|---|---|---|---|
| **CNF-01** | `P1` | `scripts/agent_harness/snapshot.py:10`, `.agent-harness/auditor.md:7`, `scripts/agent_harness/standards_policy.py:24,50,55,64` | `docs/adr/0004-pure-cad-csma-ca-mac.md` (Owner #273) | Harness snapshot/auditor/selector still embed or route superseded Hybrid TDMA (`0001-hybrid-tdma.md`, `backend-controlled schedule`, `TDMA-001..010`, `SC-001..008`). | `EV-006`, Code read |
| **CNF-02** | `P1` | `docs/adr/0004-pure-cad-csma-ca-mac.md` vs `docs/adr/0004-theoretical-timing-guard-budget.md` & `docs/adr/README.md:15-18` | ADR numbering & ADR-0004 (#273) | Two ADRs share number `0004`; `docs/adr/README.md` lines 15–18 still describe static DATA slots, 300s SYNC_BEACON, and 50ms guards as current. | `EV-006` |
| **CNF-03** | `P2` | `docs/hardware/sx1276/README.md:3,45,63-75`, `docs/development/firmware/ESP32_LORA_ENGINEERING_PLAYBOOK.md:17-29`, `ESP32_SKILL_GAP_ANALYSIS_PLAN.md:39` | `docs/adr/0004-pure-cad-csma-ca-mac.md` & `firmware/components/` | Docs describe Event-only Static TDMA, Backend schedule authority, and placeholder `tdma_common`, whereas `tdma_common` does not exist and CAD/CSMA-CA components (`node_smart_backoff`, `node_cad_backoff`) are implemented. | `EV-005`, `EV-006` |
| **CNF-04** | `P2` | `docs/development/coding-standards.md:18-22` | `AGENTS.md` (Owner #137), `GO_BACKEND_ENGINEERING_STANDARD_V2.md` | **Broken link** to `../../.github/instructions/backend.instructions.md` (directory absent) and cites superseded `GO_BACKEND_ENGINEERING_STANDARD_V1.0.md` DRAFT. | `EV-007` |
| **CNF-05** | `P2` | `docs/development/harness-fast-lane.md:77` | `scripts/agent_harness/mcp_server.py` | Documents `harness_prepare_issue` and `scripts/agent_harness/mcp_execution.py` — **neither exists** in the repository (`mcp_server.py` has 3 read-only tools). | `EV-007` |
| **CNF-06** | `P2` | `quality_gates.py:24,35-36` vs repo layout | Actual tree | Lists non-existent `.github/copilot-instructions.md`, `.github/instructions/`, `.codex/` in `POLICY_FILES`/`POLICY_PREFIXES`. | `EV-007` |
| **CNF-07** | `P2` | `.github/workflows/ci-clients.yml:15`, `ci-backend.yml:33`, `ci-integration.yml:13` | Actual `clients/web-dashboard/`, `backend-go/`, `tests/integration/` | `ci-clients.yml` warns "No React or Flutter project exists" despite Next.js/React dashboard + tests; `ci-backend.yml` claims "Only main.go logging stub exists" despite 13 Go packages. | `EV-005`, Workflow read |
| **CNF-08** | `P2` | `docs/development/{AI_TASK_START_PROTOCOL.md,agent-harness-firmware.md,agent-harness-p1.md,agy-native-coordinator-sop.md,agy-supervised-pilot.md,harness-automatic-issue.md,harness-mcp-onboarding.md,harness-onboarding.md}` | `harness-fast-lane.md` + `HARNESS_SPEC.md` | 8+ overlapping SOP/protocol docs (multiple DRAFTs and superseded v1.0 SOP) cause instruction fragmentation. | `EV-006` |
| **CNF-09** | `P2` | `docs/development/firmware/C_CODING_STANDARD_V2.md` & `docs/adr/README.md:23` vs `AGENTS.md` | Owner #137 | `docs/adr/README.md` & `ESP32_SKILL_GAP_ANALYSIS_PLAN.md` label C V2 `DRAFT`, while `AGENTS.md` (Owner #137) mandates selected C/Go V2 rules (`GOV-010` itself cautions distinguishing DRAFT from approved policy). | `EV-006`, Code read |

---

## 3. WP-H — Engineering Knowledge, Standards & Skills Audit

### 3.1 H.1 Standards & H.2 Domain Knowledge Coverage

- **Standards Selection (`EV-024`):** `standards_policy.py` deterministically parses and hashes `C_CODING_STANDARD_V2.md` (11 groups, `106` Rule IDs — including `TDMA-001..010`) and `GO_BACKEND_ENGINEERING_STANDARD_V2.md` (14 groups, `148` Rule IDs — including `SC-001..008`), enforcing ADR-0005 bounded partitions (`<=4` partitions, `<=128` rules / `<=48 KB` each, `<=256` rules / `<=192 KB` aggregate). However, `C` V2 still lacks an active AST/linter enforcement beyond `quality_gates.py`, and `Go` V2's `GO-BE-002` AST CI check (`GOCARS`) is not activated in CI.
- **CCARS (`v1.4` DRAFT) & GOCARS (`v2.0` APPROVED_ON_OWNER_MERGE):** Both correctly isolate `REF-*` / `GO-ARCH-*` / `GO-BE-*` / `CG-*` from the C/Go deterministic selector (`EV-024`: `REF-001` & `GO-BE-002` rejected by `agent_context.py`). Both require CodeGraph, which is initialized on `main` (`393` files, `7,297` nodes) but **uninitialized (`initialized: false`)** on fresh isolated worktrees (`EV-004`, WP-A).
- **Domain Coverage across all 6 Domains:**

| Domain | Primary Repo Knowledge / Standard | Authority & Drift Findings | Domain Status |
|---|---|---|---|
| **C / firmware** | `C_CODING_STANDARD_V2.md`, `c-clean-code-refactoring-standard.md`, `ESP32_LORA_ENGINEERING_PLAYBOOK.md` | C V2 mandatory via Owner #137; playbook mixes current debug guides with stale TDMA refs (`FW-TDMA-001`). No repo `C` formatter/static-analyzer CI step. | `PARTIAL` |
| **ESP32 / ESP-IDF / FreeRTOS** | `docs/adr/0003-esp-idf-v6-1.md`, `firmware/esp-idf-version.txt`, `docs/verification/pcb-hw001-pinmap.md`, `ESP32_LORA_ENGINEERING_PLAYBOOK.md` | ESP-IDF `v6.1` pinned; HW-001 pins documented; offline build fails without cached `espressif/mqtt` (`EV-018`). Board schematic & HIL timing remain `NOT_VERIFIED`. | `PARTIAL` |
| **SX1276 / LoRa PHY / MAC** | `docs/adr/0004-pure-cad-csma-ca-mac.md`, `docs/hardware/sx1276/{README,ACTIVE_PROFILE,DRIVER_OPERATIONS,REGISTER_REFERENCE}.md`, `contracts/radio-mac/` | `ADR-0004` CAD/CSMA-CA approved, **but** `docs/hardware/sx1276/README.md` & `snapshot.py` & `standards_policy.py` retain TDMA. PA path & RF timing `TBD / NOT_VERIFIED`. | `PARTIAL` (`CNF-01/03`) |
| **Go / backend** | `GO_BACKEND_ENGINEERING_STANDARD_V2.md`, `GOCARS.md`, `.go-version`, `backend-go/go.mod`, `docs/architecture/interfaces.md` | Go `1.27.3` pinned; 13 Go packages pass `go vet/test/build` in Docker `1.27.3`, but host Go is `1.27.1` and `rf_tracker.go` fails `gofmt` in CI (`EV-017`). `coding-standards.md` points to broken `.github/instructions/`. | `PARTIAL` |
| **PostgreSQL / MQTT** | `docs/adr/0002-mqtt-5.md`, `docs/development/POSTGRESQL_OPERATIONS_GUIDE.md`, `contracts/mqtt/`, `backend-go/migrations/` | Contracts validate cleanly syntactically (`EV-019`, `EV-020`). Generated `docs/generated/db-schema.md` missing; `schedule` MQTT schemas marked superseded by ADR-0004 but still tested in `check_contracts.py`. Live DB/broker E2E `NOT_RUN`. | `PARTIAL` |
| **Web / Android / Security** | `clients/DESIGN.md`, `contracts/api/openapi.yaml`, `contracts/mqtt/session-key-security.md`, `docs/verification/session-key-*` | Web Next.js dashboard & tests exist (`ci-clients.yml` falsely claims none exist); `integration.test.ts` fails in clean worktree (`no node_modules`) and triggers `SECRET-SCAN` false positive. Android `mobile-app/` is README-only stub. No `docs/SECURITY.md` or `docs/FRONTEND.md`. | `PARTIAL` / `GAP` |

### 3.2 H.3 Artifact & Skill Lifecycle Inventory (Representative Key Entries)

| `artifact_id` | `kind` | `domain` | `path_or_locator` | `revision` | `approval_status` | `activation_status` | `conflicts` | `status` | `disposition` | `review_phase` |
|---|---|---|---|---|---|---|---|---|---|---|
| `ART-STD-C2` | `standard` | C / firmware / SX1276 | `docs/development/firmware/C_CODING_STANDARD_V2.md` | `fdbc9a5c` (blob `198L/27.9KB`) | Mandatory via Owner #137 (file metadata lacks active header) | Active via `standards_policy.py` | Retains `TDMA-001..010` | `PARTIAL` | `REFACTOR` (retire TDMA rules, fix metadata) | `P02` |
| `ART-STD-GO2` | `standard` | Go / backend / DB / MQTT | `docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V2.md` | `fdbc9a5c` (287L/51.3KB) | Mandatory via Owner #137 | Active via `standards_policy.py` | Retains `SC-001..008`; AR-006 mentions scheduler | `PARTIAL` | `REFACTOR` (retire SC rules) | `P02` |
| `ART-STD-CCARS` | `workflow` | C structural refactor | `docs/development/c-clean-code-refactoring-standard.md` + `.agents/agents/c-structural-refactor.md` | `v1.4 DRAFT` (`#367`) | DRAFT / candidate | Registered in `.agents/agents/`, requires CodeGraph | Worktree CodeGraph uninitialized (`EV-004`) | `PARTIAL` | `KEEP` (route separately from C selector) | `P02/P03` |
| `ART-STD-GOCARS` | `workflow` | Go structural refactor | `docs/development/backend-go/GOCARS.md` + `.agents/agents/gocars-refactor/agent.md` | `v2.0` (`#359`) | `APPROVED_ON_OWNER_MERGE` | Registered in `.agents/agents/`, requires CodeGraph | `GO-BE-002` CI AST gate inactive | `PARTIAL` | `KEEP` (activate CI gate separately) | `P02/P05` |
| `ART-KN-PLAYBOOK` | `knowledge` | ESP32 / SX1276 | `docs/development/firmware/ESP32_LORA_ENGINEERING_PLAYBOOK.md` | `fdbc9a5c` (252L/48.1KB) | Informative (`PROPOSED` rows) | Passive reference only | Stale TDMA & `tdma_common` placeholder text | `PARTIAL` | `REFACTOR` (align with ADR-0004) | `P02/P07` |
| `ART-KN-SX1276` | `knowledge` | SX1276 / PHY | `docs/hardware/sx1276/*.md` (4 files) | `fdbc9a5c` | Informative / selective routing in `AGENTS.md` | Active routing in `AGENTS.md` | `README.md` states Event-only Static TDMA | `PARTIAL` | `REFACTOR` (align `README.md` to CAD) | `P02` |
| `ART-SKL-GAP` | `knowledge` | ESP32 Skills gap plan | `docs/development/firmware/ESP32_SKILL_GAP_ANALYSIS_PLAN.md` | `v0.2.0` (`#97`) | `OWNER_SELECTED_FIVE_CANDIDATES_AUDIT_NOT_COMPLETE` | **NOT_INSTALLED / NOT_ACTIVE** (`read-only` per `AGENTS.md`) | Cites `0001-hybrid-tdma.md` & C V2 DRAFT | `NOT_VERIFIED` | `REFACTOR` / `KEEP` read-only | `P02/P03` |
| `ART-SKL-PROV-AGY` | `skill` | Non-LoRa (`paper-vocabulary`, plugins `agent-skills`, `ponytail`) | `~/.gemini/config/skills/` & `~/.gemini/config/plugins/` | Host local | Provider-local (unrelated to LoRa product) | Discovered/installed in AGY host session | Not governed by repo `scripts/agent_harness/` | `NOT_VERIFIED` (internals) | `KEEP_OUTSIDE_REPO` (no repo authority) | `P03` |
| `ART-SKL-PROV-CODEX` | `skill` | Non-LoRa (`academic-*`, `archify`, `nature-*`, `paper-vocabulary`) | `~/.codex/skills/` | Host local | Provider-local (unrelated to LoRa product) | Present on disk (`ls` only); not activated in repo | None of the 5 ESP32 candidate skills exist | `NOT_VERIFIED` | `KEEP_OUTSIDE_REPO` | `P03` |
| `ART-KN-CORPUS` | `knowledge` | Harness V2 corpus | `docs/references/harness-engineering/{README,REFERENCE_INDEX,knowledge/01..06}.md` | `fdbc9a5c` (`#419`) | Informative self-contained MIT extraction | Active offline local lookup (`EV-025`, `EV-026`) | Historical `#417` PDF git-history exposure remains open | `VERIFIED` (local anchors) | `KEEP` | `P01/P02` |

### 3.3 H.4 & H.5 — Independent Routing Test Matrix (`H-A01..H-A12`)

| Case | Scenario & Target | Expected | Actual Observed Result & Metrics | Status | Evidence |
|---|---|---|---|---|---|
| `H-A01` | Inventory & authority across instructions, standards, playbooks, provider/repo Skills | Exact paths/revisions, activation vs presence distinguished | All repo docs/scripts + host skill dirs inventoried; `SKILL.md` presence != repo activation; 0/5 ESP32 skills installed | `PARTIAL` | `EV-004`, `EV-006` |
| `H-A02` | C V2 deterministic selection + negative bounds (`sx1276_driver.c` + `RTOS-003`) | Deterministic bounded C rules; reject unknown/wrong-SHA/traversal | **PASS:** Selected `77` C rules (`32,131` B `agent_input`, schema v1); negative probes (`FAKE-999`, bad SHA, `../outside.c`) all exit `2` `BLOCKED`. Gap: interactive CLI lacks runtime enforcement hook | `PARTIAL` | `EV-024` |
| `H-A03` | Go V2 deterministic selection (`internal/mqtt/event_consumer.go`) | Bounded Go rules union (`MQ`, `CT`, `DB`, `RT`, `SE`, `TS`), zero C rules | **PASS:** Selected `140` Go rules (`63,815` B `agent_input`, schema v2 partitioned, `0` C rules); `140 > 128` triggers ADR-0005 partitioning cleanly | `PARTIAL` | `EV-024` |
| `H-A04` | C / ESP32 / ESP-IDF / FreeRTOS routing & build | Pin/SDK authority + C rules + v6.1 build | C rules select `RTOS/MEM/ERR`; `docs/hardware/sx1276/` & `ESP32_LORA_ENGINEERING_PLAYBOOK.md` found; `--network=none` clean build FAILS (`espressif/mqtt` uncached) | `FAIL` (offline build) | `EV-018`, `EV-024` |
| `H-A05` | SX1276 / LoRa / Custom MAC routing (`node_smart_backoff.c`) | Route to ADR-0004 CAD/CSMA-CA & SX1276 refs; flag stale TDMA | Selected `71` C rules (`30,570` B); however `snapshot.py`, `auditor.md`, `sx1276/README.md`, and playbook still conflict with ADR-0004 | `FAIL` (authority drift) | `EV-006`, `EV-024` |
| `H-A06` | Go backend / PostgreSQL / MQTT routing (`000003_event_storage_and_health.up.sql`) | Route to Go V2 `DB/CT/RT/SE/TS` rules & migration contracts | Selected `66` Go rules (`35,635` B, `0` C rules); Go `1.27.3` tests PASS in Docker; live PostgreSQL/Mosquitto integration `NOT_RUN` | `PARTIAL` | `EV-017`, `EV-024` |
| `H-A07` | CCARS / GOCARS workflow triggers & CodeGraph gate | Graph-first required; `REF-*`/`GO-BE-*` rejected by C/Go selector | Negative probes confirm `REF-001` & `GO-BE-002` exit `2` `BLOCKED`; however worktree CodeGraph is uninitialized (`initialized: false`), blocking mutation until indexed | `PARTIAL` | `EV-004`, `EV-024` |
| `H-A08` | Docs-only vs `contracts/` vs Harness control isolation | Docs-only loads 0 C/Go rules & low QG risks; `contracts/`/`AGENTS.md` trigger `SECURITY-CHECK`/`TOOLING-CHECK` | **PASS:** `HARNESS_BASELINE_REPORT.md` -> `0` rules (`10,952` B), QG risks `["all"]`; `contracts/mqtt/topics.md` -> `0` C/Go rules, QG `["all","infra","mqtt","security"]`; `AGENTS.md` -> `0` C/Go rules, QG `["all","security","tooling"]` | `VERIFIED` (selector + QG routing) | `EV-024` |
| `H-A09` | Skill trigger, least privilege & untrusted input | Missing capability blocks; active skill/Full Access cannot bypass runtime sandbox | `scope.py`/`pr_review_policy.py` prompt-injection & traversal unit tests PASS; however Native Fast Lane Full Access has **no OS/network sandbox** and provider skills have no repo permission registry | `GAP` | `EV-012`, `provider-decision.md` |
| `H-A10` | Knowledge quality, links & drift | Valid links, aligned SDK/architecture | `REFERENCE_INDEX.md` `248/248` anchors valid (`EV-026`); `coding-standards.md` has 1 broken link (`EV-007`); multiple docs retain TDMA or Go v1.0 draft refs (`EV-006`) | `PARTIAL` | `EV-006`, `EV-007`, `EV-026` |
| `H-A11` | Skill effectiveness & context budget baseline | Measure baseline rule counts, `agent_input` bytes, discovery cost | Measured `agent_input` sizes (`10,952`–`63,815` B) across probes (`EV-024`); discovery cost / token telemetry & ablation runs are `NOT_RUN` (protocol frozen in WP-F) | `NOT_VERIFIED` | `EV-024` |
| `H-A12` | Skill extensibility (`esp32-debugging` inert scenario) | Discover, register, version, route, verify, disable, rollback without core Harness edits | **`GAP`:** Repo has **no** `skill_registry` or `skill_router` in `scripts/agent_harness/`. Adding `esp32-debugging` today requires manual edits to `AGENTS.md`, `harness-coordinator.md`, `ESP32_SKILL_GAP_ANALYSIS_PLAN.md`, and `quality_gates.py` allowlists. **Proposed P02/P03/P05/P08 fix:** declarative version-pinned skill manifest + Host `skill_router` decoupled from mandatory `standards_policy.py` (preserving C/Go V2 gates intact) | `GAP` | `EV-005`, `ESP32_SKILL_GAP_ANALYSIS_PLAN.md` |

---

## 4. WP-C — Requirements Traceability Matrix Summary

Full 45-row machine-readable traceability is recorded in [HARNESS_RTM.json](HARNESS_RTM.json). Exact ID set equality (`45` unique `H2-*` IDs) was programmatically verified against `HARNESS_SPEC.md` §4, `HARNESS_MASTER_PLAN.md` §14, and `REFERENCE_INDEX.md` §2 (`EV-024`, `build_artifacts.py`).

| Subsystem | Total | `VERIFIED` | `PARTIAL` | `GAP` | `FAIL` | `NOT_VERIFIED` | `CONDITIONAL_NOT_EXERCISED` | Highest Severity |
|---|---|---|---|---|---|---|---|---|
| Instructions (`H2-INS-01..07`) | 7 | 0 | 5 | 1 | 1 (`H2-INS-03`) | 0 | 0 | `P1` |
| Tools (`H2-TOL-01..05`) | 5 | 0 | 4 | 1 (`H2-TOL-02`) | 0 | 0 | 0 | `P0` (`H2-TOL-02`) |
| Environment (`H2-ENV-01..05`) | 5 | 0 | 3 | 0 | 2 (`H2-ENV-02`, `H2-ENV-04`) | 0 | 0 | `P0` (`H2-ENV-04`) |
| State (`H2-STA-01..06`) | 6 | 0 | 4 | 2 | 0 | 0 | 0 | `P1` |
| Feedback (`H2-FBK-01..11`) | 11 | 0 | 4 | 6 | 0 | 1 (`H2-FBK-05`) | 0 | `P1` |
| Governance (`H2-GOV-01..03`) | 3 | 0 | 2 | 1 | 0 | 0 | 0 | `P1` |
| Orchestration (`H2-ORC-01..08`) | 8 | 0 | 2 | 5 | 0 | 0 | 1 (`H2-ORC-08`) | `P1` |
| **Total** | **45** | **0** | **24** | **16** | **3** | **1** | **1** | **2 P0 / 22 P1 / 20 P2 / 1 P3** |

---

## 5. WP-D — Baseline Verification & Critical Triage

### 5.1 Executed Checks & Offline Corpus Results

| Check / Command | Scope & Layer | Tool / Image | Exit | Outcome | Evidence |
|---|---|---|---|---|---|
| `agent_context.py --repo .` | G0 Host Context | Python 3.12.3 | `0` | `HOST_CONTEXT_LOADED` (`09212ed3...`) | `EV-001` |
| `harness_doctor.py --profile all --json` | Env preflight | Python 3.12.3 | `0` | `ready: true` (`codex_cli` WARN off-PATH) | `EV-008` |
| `verify_structure.py` | Static monorepo layout | Python 3.12.3 | `0` | `PASS` | `EV-009` |
| `unittest discover -s tests/agent_harness -v` | Harness unit suite | Python 3.12.3 | `0` | **416 tests OK** (`54.210s`) | `EV-012` |
| `quality_gates.py --repo . --base fdbc9a5c...` | Static gates | Python 3.12.3 | `1` | `BLOCKED`: `SECRET-SCAN` FAIL (`integration.test.ts:31`); `DIFF-CHECK` PASS | `EV-011` |
| `verify_no_secrets.py` | Tracked/index secret regex | Python 3.12.3 | `1` | `FAIL` on 6 files (all false positives) | `EV-010`, `EV-013` |
| `gitleaks detect --no-git --source . --redact` | External secret scan | gitleaks 8.30.1 | `1` | 10 `generic-api-key` hits (all test/SHA256 strings) | `EV-014` |
| `actionlint .github/workflows/*.yml` | GitHub Actions lint | actionlint v1.7.7 | `1` | 1 error: `harness-issue.yml:28` unknown label `harness-isolated` | `EV-023` |
| `contracts/tests/check_contracts.py` + `tests/contract` | Contract schema + unit | Python 3.12.3 | `0` | `check_contracts` PASS (12 schemas, 40 MQTT, 18 WS, 15 REST); 15/15 unit OK | `EV-019`, `EV-020` |
| `unittest discover -s tests/unit -v` | Firmware/tool Python+C unit | Python 3.12.3 | `0` | **44 tests OK** (`2.881s`) | `EV-021` |
| `docker golang:1.27.3-alpine` Go `vet/test/build` | Backend Go 1.27.3 | `golang:1.27.3-alpine` | `0` | `go vet`, `go test` (13 pkgs), `go build ./cmd/server` **all PASS** when modcache mounted | `EV-017` |
| `docker espressif/idf:v6.1 --network=none` | Clean-copy firmware build | `espressif/idf:v6.1` | `2` | **FAIL** on both `gateway_master` & `sensor_node`: `espressif/mqtt (1.1.0)` needs network | `EV-018` |
| `node --test --experimental-strip-types tests/*.test.ts` | Web dashboard unit tests | Node v22.23.2 | `1` | `api_client.test.ts` & `rf_quality.test.ts` PASS; `integration.test.ts` FAILS (`Cannot find package 'react'` in clean worktree) | `EV-022` |
| `docker --network=none` Corpus Check | Local knowledge offline proof | `python:3.12-slim` | `0` | `pdf_count=0`, 6 `knowledge/*.md`, `248/248` anchors valid; substantive template & Maker-Checker guidance verified | `EV-025`, `EV-026` |
| `p1/cli.py prepare --issue 422` & `run.py --issue 422` | Orchestrator dry-run preflight | Python 3.12.3 | `2` | `p1/cli.py` BLOCKED (`Malformed Issue or missing strict scope`); `run.py` BLOCKED (`Source secret/path scan failed`) | `EV-025` |

### 5.2 Critical Baseline Triage (`SECRET-SCAN` P0 & `go-format-vet-test-build` CI)

1. **`SECRET-SCAN` P0 (`clients/web-dashboard/tests/integration.test.ts:31`) — CONFIRMED FALSE POSITIVE (`EV-010`, `EV-011`, `EV-013`, `EV-014`):**
   - `quality_gates.py:56` matches `access_token: "jwt-token-admin01-session"` inside a mocked `globalThis.fetch` `Response` in `clients/web-dashboard/tests/integration.test.ts:31`. Inspection of lines `1-60` and `280-309` confirms synthetic test strings only (`"jwt-token-admin01-session"`, `"password123"`, `"Password123!"`); zero real credentials exist.
   - `verify_no_secrets.py:12` also flags 6 tracked files: `backend-go/internal/auth/service_test.go` (`passFixture`/`wrongPassFixture`), `clients/web-dashboard/src/app/login/page.tsx:75` (`password: password.trim()`), `clients/web-dashboard/src/app/users/page.tsx:305` (`password: newPassword`), `clients/web-dashboard/src/types/api.ts:14,44` (`password: string;`), `clients/web-dashboard/tests/integration.test.ts:296`, and `scripts/agent_harness/quality_gates.py:55` (the regex definition itself!).
   - **Remediation Proposal (separate scoped Issue, NOT in P01):** Refactor test fixtures to use non-literal/placeholder prefixes or `REPLACE_` / `mock_` conventions or narrow `verify_no_secrets.py` / `quality_gates.py` AST/string-literal rules **without** weakening real secret detection. No blanket waiver.
2. **`go-format-vet-test-build` CI Failure (`46049348761`, `46048385376`, `46047680659`) — ROOT CAUSE CONFIRMED (`EV-015`, `EV-016`, `EV-017`):**
   - All three CI runs (`d76ce89`, `332e09e`, `fdbc9a5c`) executed `setup-go@v5` (`go1.27.3`), passed `Verify pinned Go toolchain and module`, and failed identically at step `Go formatting` (`test -z "$(gofmt -l .)"`, exit code `1`) before `go vet`, `go test`, or `go build` executed.
   - Local `gofmt -l .` confirms the sole unformatted file is `backend-go/internal/presence/rf_tracker.go` (lines `140-145`, introduced in `67e3bcf` / PR #400): doc-comment bullets `// - ...` require `//   - ...` under Go 1.27 `gofmt`.
   - Running `go vet ./...`, `go test ./...`, and `go build ./cmd/server` in `golang:1.27.3-alpine` (`GOTOOLCHAIN=local`) with Go module cache available exits `0` across all 13 tested Go packages.
   - **Remediation Proposal (separate scoped Go Issue):** Run `gofmt -w backend-go/internal/presence/rf_tracker.go` under a `backend-go/`-scoped Issue and verify CI green.

---

## 6. WP-E — Orchestration, Role Isolation & Maturity Audit

- **Logical Orchestrators vs Actual Execution (`EV-003`, `EV-005`, `EV-025`):** Four separate orchestration surfaces exist: (1) `.agents/agents/harness-coordinator.md` (Native Fast Lane — instruction-driven, active default); (2) `scripts/agent_harness/run.py` (Codex Worker + AGY Auditor CLI runner — unused in Fast Lane, blocked by baseline `SECRET-SCAN`); (3) `scripts/agent_harness/p1/pilot.py` (simulated callback state machine with SQLite `PilotLedger`); (4) `scripts/agent_harness/p1/auto_issue.py` (Enterprise AGY CI — disabled until `HARNESS_ENTERPRISE_READY == 'true'` and `/etc/lora-harness/provider-policy.json`).
- **Role Isolation & Trust Boundaries:** `pr_review.py` + `antigravity.py` enforce strict read-only audit payload validation and SHA immutability (`EV-012`), and `harness-coordinator.md` delegates `Fresh-Independent-Auditor` via `invoke_subagent`. However, per `.agent-harness/security/provider-decision.md`, Native Full Access provides **context separation only, NOT OS/filesystem/network isolation** (`H2-TOL-02` `GAP`, `P0`).
- **ORC-01..08 & FBK-10..11 Assessment:**
  - `H2-ORC-01/05` (`PARTIAL`/`GAP`): `p1/state.py` SQLite CAS (`PLANNED`..`CANCELLED`) and `PilotLedger` (`READY`..`AWAIT_HUMAN`) exist only in unused/simulated P1 modules; Native Fast Lane lacks persistent run contracts or crash recovery.
  - `H2-ORC-03/04` (`GAP`): No external multi-round Maker-Checker loop (`>=5`-round pilot `NOT_RUN`), and `audit.schema.json` lacks the 6-dimension `0-2` evaluator rubric (`ACCEPT`/`REVISE`/`BLOCK`) and human calibration.
  - `H2-ORC-06/07/08` & `H2-FBK-10/11` (`GAP` / `CONDITIONAL_NOT_EXERCISED`): No pattern assessment, orchestration tax telemetry, concurrency cap, meta-improvement ratchet, or anti-Goodhart holdout suite exists.
- **Evidence-Based Maturity Rating:** **Level 1 (Goal Runner) operational with unintegrated Level 3 (Multi-Agent Loop) components** (`run.py`, `pr_review.py`, `p1/pilot.py`). Level 3 E2E is **NOT_VERIFIED**; Level 4 and Level 5 Fleet are **NOT_IMPLEMENTED / CONDITIONAL_NOT_EXERCISED**. Orchestration tax is **NOT_RUN**.

---

## 7. WP-F — Benchmark Protocol & OD-06 / OD-09 / OD-10 Proposal

All baseline benchmark metrics are **`NOT_RUN`** (no tuning, no fabricated measurements). The following frozen protocol is proposed for Owner approval under **OD-06** before P02 edits begin:

1. **Representative Evaluation Cohort (7 Frozen Tasks + 2 Held-Out Tasks):**
   - `T-FW-01` (Firmware): `sx1276_driver` IRQ/FIFO bounded change (tests `C` V2 + `docs/hardware/sx1276/`).
   - `T-FW-02` (Firmware MAC): `node_smart_backoff` CAD/CSMA-CA change (tests ADR-0004 vs stale TDMA conflict detection).
   - `T-GO-01` (Backend/DB): `internal/mqtt` + `migrations/` idempotent event ingestion (tests Go V2 partitioned union + DB rules).
   - `T-WEB-01` (Client Web): `clients/web-dashboard/` API/UI contract alignment (tests zero C/Go load + client tests).
   - `T-CON-01` (Contract): `contracts/mqtt/` schema & semantic update (tests security routing + human-review stop).
   - `T-DOC-01` (Docs-only): ordinary `docs/` update (tests 0 C/Go rule load, no Docker receipt demand).
   - `T-REC-01` (Harness/Recovery): seeded baseline failure + interrupted run recovery + negative scope escape.
   - **Holdout Set (`2` blind tasks reserved for P10):** 1 cross-component Firmware↔MQTT change + 1 Go auth/RBAC change.
2. **Seeded Negative Fixtures (Zero-Tolerance):** Unknown Rule ID, stale `AGENTS.md` SHA-256, out-of-scope file edit, TDMA/LoRaWAN reintroduction, unauthorized provider Skill activation, forged Host receipt.
3. **Matched Experimental Constants:** Same model, reasoning preset, starting commit SHA, container toolchain digests (`golang:1.27.3-alpine`, `espressif/idf:v6.1`), and frozen test oracle; `N = 3` repetitions per task/variant; report raw `numerator/denominator` (denominator `0` = `N/A`).
4. **Proposed Metrics & Non-Regression Thresholds (OD-06 Decision Inputs):**
   - **Mandatory Rule Recall:** `correctly injected applicable mandatory IDs / independently expected mandatory IDs` → **Required `1.00` (100%, zero tolerance)**.
   - **Unauthorized Activation Rejection:** `rejected negative cases / executed unauthorized cases` → **Required `1.00` (100%, zero tolerance)**.
   - **Routing Accuracy:** `correct source/procedure routing cases / eligible cases` → **Target `>= 0.90`**, non-regression vs P01 baseline.
   - **Irrelevant Load Ratio:** `unrelated loaded rule IDs or context bytes / total loaded IDs or bytes` (reported separately in IDs and UTF-8 bytes) → **Reduction target in P02**, zero mandatory rule loss.
   - **Fresh Session Test (`H2-GOV-03`):** `5/5` accurate answers + executable resume.
   - **Orchestration Tax (`H2-ORC-07`):** Wall-clock coordination time, human review rounds, conflict count, input/output tokens (where exposed by provider), retries, escaped defects.
   - **OD-09 / OD-10 Inputs:** Reuse `Harness Coordinator + deterministic Python Host` (`run.py`/`pr_review.py`/`p1/state.py` unified); provisional rubric threshold `12/12` + `0` P0/P1 hard-gate failures; max `3` Maker-Checker repair rounds; 1-variable-per-experiment isolated worktree ratchet with frozen holdout.

---

## 8. WP-G — Migration Map, Dispositions & Prioritized P02 Slices

### 8.1 Disposition Summary

| Disposition | Targets | Rationale & Verification Condition |
|---|---|---|
| **KEEP** | `agent_context.py`, `standards_policy.py` (core engine), `scope.py` (core), `quality_gates.py` (core), `pr_review.py`, `pr_review_policy.py`, `verify_structure.py`, `docs/references/harness-engineering/`, `tests/agent_harness/` (416 tests) | Proven deterministic Host gates; preserve exact G0 & ADR-0005 partition guarantees across migration. |
| **REFACTOR** | `AGENTS.md` (to 80–120 concise lines), `snapshot.py` (replace `0001-hybrid-tdma.md` with `0004-pure-cad-csma-ca-mac.md`), `.agent-harness/auditor.md` (remove TDMA directive), `standards_policy.py` (retire `TDMA`/`SC` after ADR-0004 reconciliation), `docs/adr/README.md` & `0004-*` numbering, `docs/hardware/sx1276/README.md`, `ESP32_LORA_ENGINEERING_PLAYBOOK.md`, `scope.py` (allow explanatory intro line or enforce strict template check), `toolchains/resolver.py` (offline component cache handling), `ci-clients.yml`/`ci-backend.yml` | Eliminate authority drift, broken links, and clean-worktree offline build failures while keeping existing tests green. |
| **CONSOLIDATE** | `docs/development/{harness-fast-lane,coding-standards,AI_TASK_START_PROTOCOL,agy-native-coordinator-sop,agent-harness-firmware,agent-harness-p1,harness-onboarding,harness-mcp-onboarding}.md` + `scripts/agent_harness/{run.py,p1/cli.py,p1/auto_issue.py}` | Single active SOP & unified startup/check CLI (`OD-01`, `OD-03`); remove references to non-existent `mcp_execution.py` and `.github/instructions/`. |
| **ADD** | Root `ARCHITECTURE.md` (`P02`/`P07`), `PROGRESS.md` & machine-readable `feature_list.json` (`P04`), declarative `skill_registry` + Host `skill_router` (`H-A12`, `P02/P03`), mechanical boundary checks (`P05`), 6-dimension `0-2` rubric in `audit.schema.json` (`P05/P08`), `QUALITY_SCORE.md` / debt tracker (`P07`), multi-round external loop & ratchet harness (`P08`) | Close the 16 `GAP` rows in `HARNESS_RTM.json` sequentially by phase. |
| **DEPRECATE / REMOVE** | Superseded TDMA rule groups (`TDMA-001..010`, `SC-001..008`), `agy-native-coordinator-sop.md` v1.0, `GO_BACKEND_ENGINEERING_STANDARD_V1.0.md` active links | Retire only after caller/dependency mapping and Owner disposition; rollback via branch revert. |
| **NOT_VERIFIED / DEFER** | `H2-ORC-08` (Level 5 Fleet), `H2-FBK-05` (HIL/RF & live Docker E2E) | Defer L5 Fleet to P09 5-criteria evaluation; keep HIL/RF explicitly `NOT_VERIFIED` until bench run. |

### 8.2 Prioritized Proposed Sequence (Before & Entering P02)

1. **Pre-P02 Baseline Unblockers (Separate Scoped Product/Tooling Issues — NOT in P01):**
   - **Pre-1 (Go CI Unblock):** Fix `gofmt` doc-comment spacing in `backend-go/internal/presence/rf_tracker.go:140-145` (`EV-017`).
   - **Pre-2 (`SECRET-SCAN` False Positive Remediation):** Remediate `clients/web-dashboard/tests/integration.test.ts:31` mock fixture and align `verify_no_secrets.py` false positives without weakening secret scanning (`EV-013`).
   - **Pre-3 (Owner Decisions):** Owner approves this P01 baseline report, resolves **OD-06** (benchmark cohort/thresholds) and **critical TDMA authority conflict disposition** (`CNF-01..03`).
2. **Proposed P02 Slices (Instructions & Knowledge Architecture, `H2-INS-01..07`):**
   - **P02-A:** Reconcile ADR-0004 numbering/README, retire TDMA references in `snapshot.py`, `.agent-harness/auditor.md`, `sx1276/README.md`, `ESP32_LORA_ENGINEERING_PLAYBOOK.md`, and `standards_policy.py`; fix `coding-standards.md` broken link and `harness-fast-lane.md` phantom `mcp_execution.py`.
   - **P02-B:** Add concise root `ARCHITECTURE.md` domain/layer map and consolidate overlapping Harness SOPs into single active routing docs.
   - **P02-C:** Refactor `AGENTS.md` to concise `80-120` lines (`<=10` invariant groups) while proving 100% G0 & mandatory rule coverage parity + baseline SNR comparison.
   - **P02-D (P02/P03 bridge for `H-A12`):** Define declarative, version-pinned Skill manifest & routing contract (`esp32-debugging` design) decoupled from mandatory `C/Go` V2 selection.

### 8.3 Blocker & `NOT_RUN` / `NOT_VERIFIED` Register

- **P0 Blockers:** (1) `H2-TOL-02` — Native Fast Lane lacks runtime filesystem/network least-privilege isolation (`provider-decision.md`); (2) `H2-ENV-04` — `main` fails `SECRET-SCAN` (`integration.test.ts:31`) and `CI - Backend Go Scaffold` (`rf_tracker.go` `gofmt`), blocking clean baseline verification.
- **P1 Blockers:** `H2-INS-03` (`ADR-0004` vs TDMA drift in Harness/docs), `H2-INS-05` (no runtime hook in interactive CLI), `H2-ENV-02` (clean worktree ESP-IDF `--network=none` & Web `node_modules` fail; host Go `1.27.1 != 1.27.3`), `H2-TOL-03` (`scope.py` blocks Issue #422), `H2-STA-01..05` (no `feature_list.json` or durable `PROGRESS.md`), `H2-FBK-01..05` (CI stubs, no mechanical layer guardrails, E2E unrun), `H2-GOV-01/03` (Fast Lane E2E & Fresh Session Test unverified), `H2-ORC-01..05` (fragmented orchestration, no 6-dim rubric, no multi-round external loop).
- **Explicitly `NOT_RUN` / `NOT_VERIFIED`:** HIL/RF bench timing & PA path (`NOT_VERIFIED`), live Mosquitto/PostgreSQL Docker E2E (`NOT_RUN`), `clients/mobile-app/` build (`NOT_RUN`, README stub), `H-A11` token/discovery-cost benchmark (`NOT_RUN`), `H2-ORC-08` Level 5 Fleet (`CONDITIONAL_NOT_EXERCISED`), provider-local `~/.codex/skills/` & `~/.gemini/config/plugins/` internals (`NOT_VERIFIED`).

---

## 9. Handoff & Independent Review Verification

- **Rollback:** Report-only branch `docs/422-p01-baseline-audit` adds only 3 files under `docs/harness/phase-01/`; rollback is reverting the branch or closing the Draft PR without touching `main` or the canonical worktree.
- **Independent Auditor Verification (`AUDIT_NOT_VERIFIED`):** Attempted `invoke_subagent(TypeName="Fresh-Independent-Auditor")`, which failed with `"subagent \"Fresh-Independent-Auditor\" not found or not allowed to be invoked"`; consumer `agy -p` auto-spawn is prohibited by `.agent-harness/security/provider-decision.md`. Therefore independent Auditor review remains `AUDIT_NOT_VERIFIED` and must be executed in a separate fresh operator-invoked `agy` / reviewer session against `fdbc9a5c`, `HARNESS_RTM.json`, `EVIDENCE_MANIFEST.json`, and `/tmp/p01-evidence-422/`.
- **Next Owner Decisions Required:**
  1. Review and accept P01 report + migration map after Independent Auditor verdict.
  2. Approve **OD-06** benchmark protocol & thresholds, and authorize separate scoped pre-P02 fixes (`rf_tracker.go` `gofmt` + `integration.test.ts` false-positive remediation).
  3. Authorize scoped **P02** Issue(s) before any Harness modification begins.
