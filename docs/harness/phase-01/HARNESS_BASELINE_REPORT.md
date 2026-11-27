# Harness V2.0 — Phase 01 As-Is Audit & Baseline Report

**Issue:** [#422](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/422) (`[Harness V2][P01-B]`) · **Mode:** `AUDIT_ONLY` (read-only audit subject; 3 authorized report artifacts only)
**Audited Main Commit:** `fdbc9a5c1266073f84e2d4e841671e75d6690d95` · **Tree SHA:** `d065262bdce0880113c755103fe587dbb4edffcd`
**Isolated Worktree / Branch:** `/home/khanh/projects/iot/LoRa-P2P-issue-422` (`docs/422-p01-baseline-audit`)
**Frozen Pre-Report Candidate Fingerprint:** `afb33c526b114da0146e6a57554f555d56610501d1645afeb04f0774d377207d`
**Authority Basis:** [HARNESS_SPEC.md](../HARNESS_SPEC.md) `v0.2.0`, [HARNESS_MASTER_PLAN.md](../HARNESS_MASTER_PLAN.md) `v0.2.0`, [P01_EXECUTION_PLAN.md](P01_EXECUTION_PLAN.md) `v0.3.0`, [P01_INDEPENDENT_AUDIT_PROTOCOL.md](P01_INDEPENDENT_AUDIT_PROTOCOL.md) `v0.3.0`, live `AGENTS.md` (`EV-001`)
**Companions:** [HARNESS_RTM.json](HARNESS_RTM.json) (45 rows, schema `1.1.0`) · [EVIDENCE_MANIFEST.json](EVIDENCE_MANIFEST.json) (29 receipt records, manifest `1.1.0`)
**Revision:** Targeted Remediation (`F01–F05` + Owner GitHub Actions `OWNER_WAIVED` record on PR #423; prior candidate `66e0ee959f2f3b9a22ddd378cfda7c1fcecc7713`)

---

## 0. Executive Summary & Verdicts

| Verdict Dimension | Status | Basis |
|---|---|---|
| **Audit Delivery** | `PARTIAL` (`DELTA_AUDIT_NOT_VERIFIED`) | All 8 Work Packages (`A -> B -> H -> C -> D -> E -> F -> G`), 45/45 `H2-*` RTM rows, 12/12 `H-A01..H-A12` cases, offline `--network=none` local corpus check, baseline critical triage, and external evidence manifest completed without mutating the audit subject. Candidate 1 (`66e0ee95`) received Focused Independent Audit findings `F01–F05`; remediation delta `F01–F05` on Candidate 2 requires fresh independent Auditor delta verification (`AUDIT_NOT_VERIFIED` if subagent unavailable in session). |
| **As-Is Conformance to SPEC v0.2.0** | `FAIL` | 0 `VERIFIED`, 24 `PARTIAL`, 16 `GAP`, 3 `FAIL` (`H2-INS-03`, `H2-ENV-02`, `H2-ENV-04`), 1 `NOT_VERIFIED` (`H2-FBK-05`), 1 `CONDITIONAL_NOT_EXERCISED` (`H2-ORC-08`). Two P0 blockers exist on `main`: absent runtime least-privilege sandboxing in Native Fast Lane (`H2-TOL-02`) and failing local baseline gate (`SECRET-SCAN`, `H2-ENV-04`). |
| **GitHub Actions CI** | `OWNER_WAIVED` *(quota exhausted; NOT `CI_PASS`)* | Owner temporarily waived GitHub Actions CI due to exhausted quota. Prior verified Go findings (`gofmt` FAIL on `rf_tracker.go:140-145`; `go vet/test/build` PASS in `golang:1.27.3-alpine`) remain recorded unchanged with zero Go edits. Local `SECRET-SCAN`, Mandatory G0, and local Quality Gates are **NOT waived**. |
| **HIL / RF / Live E2E / Production Security** | `NOT_VERIFIED` | No physical hardware, RF transmission, live Mosquitto/PostgreSQL restart E2E, or human security sign-off executed in P01. |
| **Ready to Merge** | `false` | Read-only audit deliverable; requires fresh Independent Auditor delta verification of `F01–F05` and Owner review (no auto-merge). |

### Key Headline Findings

1. **Deterministic Host core is strong (416/416 unit tests PASS), but fragmented and bypassed in daily CLI use (`EV-012`, `EV-024`, `EV-025B`, `EV-025C`):** `agent_context.py`, `standards_policy.py`, `quality_gates.py`, `pr_review.py`, and `p1/*` pass all 416 Harness unit tests and enforce fail-closed SHA/scope/partition invariants. However, Native Fast Lane relies on operator Full Access instructions rather than runtime Host interception, and `run.py` / `p1/cli.py` / `p1/auto_issue.py` are disconnected or blocked on live Issue #422.
2. **Baseline `main` fails local `SECRET-SCAN` & Go `gofmt` (`EV-011`, `EV-016`, `EV-017`):**
   - **`SECRET-SCAN` P0 (`quality_gates.py` — NOT waived):** Fails on `clients/web-dashboard/tests/integration.test.ts:31` (`access_token: "jwt-token-admin01-session"`). Confirmed **false positive** on a mocked unit-test response (`EV-013`). `verify_no_secrets.py` also fails on 6 tracked files (`service_test.go`, `login/page.tsx`, `users/page.tsx`, `types/api.ts`, `integration.test.ts`, `quality_gates.py` itself) due to loose `password[:=]` regex matching. `gitleaks --redact` flags 10 test/hash strings (`EV-014`). **Zero real credentials found.**
   - **Go CI (`CI - Backend Go Scaffold` — Actions `OWNER_WAIVED`):** Runs `46049348761`, `46048385376`, `46047680659` all failed at step `Go formatting` (`test -z "$(gofmt -l .)"`, exit 1) due solely to doc-comment list indentation in `backend-go/internal/presence/rf_tracker.go:140-145` (from commit `67e3bcf`). In pinned `golang:1.27.3-alpine`, `go vet ./...`, `go test ./...` (13 packages), and `go build ./cmd/server` all **PASS (exit 0)** (`EV-017`).
3. **Clean-checkout offline builds fail (`EV-018`, `EV-022`):** `toolchains/resolver.py` enforces `--network=none`, causing disposable ESP-IDF `v6.1` builds of `gateway_master` and `sensor_node` to fail (exit 2) fetching `espressif/mqtt (1.1.0)` when `managed_components/` is absent from a fresh worktree. Web `integration.test.ts` fails in a clean worktree (exit 1) because `node_modules` (`react`) is absent. Host `go` is `1.27.1` vs pinned `.go-version` `1.27.3` (`EV-004`).
4. **Authority drift (`ADR-0004` vs TDMA) & broken/missing references (`EV-006`, `EV-007`):** `snapshot.py` (`REFERENCES` -> `0001-hybrid-tdma.md`), `.agent-harness/auditor.md` (`backend-controlled schedule`), `standards_policy.py` (`TDMA`/`SC` rule groups), `docs/adr/README.md`, `docs/hardware/sx1276/README.md`, and `ESP32_LORA_ENGINEERING_PLAYBOOK.md` still carry superseded Hybrid TDMA guidance after ADR-0004 (#273). Two ADRs share number `0004`. `coding-standards.md` has a broken link to non-existent `.github/instructions/backend.instructions.md`; `harness-fast-lane.md` references non-existent `mcp_execution.py` and `harness_prepare_issue`.
5. **Local corpus offline sufficiency verified (`EV-025A`, `EV-026`):** Under `docker run --rm --network=none` against the frozen worktree (zero PDFs present), all `248/248` `knowledge/` heading anchors in `REFERENCE_INDEX.md` resolve cleanly and all `45/45` `H2-*` IDs match across `HARNESS_SPEC.md`, `HARNESS_MASTER_PLAN.md`, and `REFERENCE_INDEX.md`.

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
| Dirty Main Workspace Preserved | Canonical `/home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP` left untouched (`M firmware/gateway_master/sdkconfig.defaults` + untracked deploy/backfill files); `EV-001` ran from canonical checkout targeting `--repo /home/khanh/projects/iot/LoRa-P2P-issue-422`. | `EV-001` |

### 1.2 Approved Capability, Budget & Toolchains

- **Authorized outputs:** Only `HARNESS_BASELINE_REPORT.md`, `HARNESS_RTM.json`, `EVIDENCE_MANIFEST.json` under `docs/harness/phase-01/`. Raw logs stored externally in `/tmp/p01-evidence-422/` remain unmodified.
- **Timeouts & Cleanup:** Default command timeout `60s`, container build `120s`, Auditor `300s`; disposable `/tmp/p01-idf-copy` created and removed cleanly after `EV-018`.
- **Host & Container Toolchains (`EV-003`, `EV-004`, `EV-005`, `EV-008`):**

| Tool / Runtime | Observed Version / State | Pinned / Expected | Gap / Note |
|---|---|---|---|
| `git` / `python3` / `gh` | `git 2.43.0`, `Python 3.12.3`, `gh 2.45.0` | Python `>=3.10` | Ready (`EV-008`) |
| `agy` / `codex` | `agy 1.5.18` (PATH), `codex-cli 0.172.0` (`~/.local/bin/codex`) | Either CLI | `harness_doctor.py` warns `codex_cli` missing because `~/.local/bin` is not on default PATH (`EV-003`, `EV-008`) |
| `go` (host vs Docker) | Host `/usr/local/go/bin/go` is `go1.27.1` (not on default PATH); Docker `golang:1.27.3-alpine` (`fa3d596898d9`) | `1.27.3` (`.go-version`, `backend-go/go.mod`) | Host Go `1.27.1` drifts from pinned `1.27.3` (`EV-003`, `EV-004`, `EV-017`) |
| `espressif/idf:v6.1` | Docker `sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c` | `v6.1` (`firmware/esp-idf-version.txt`) | Image cached, but `managed_components/espressif__mqtt` absent in clean worktrees (`EV-018`) |
| `node` / `npm` | `v22.23.2` / `12.0.2` (`~/.gemini/antigravity/bin/`) | `clients/web-dashboard/package-lock.json` | No `node_modules` in clean worktree (`EV-022`) |
| `codegraph` | `1.6.2` (`~/.local/bin/codegraph` & `codegraph-mcp`) | Optional / mandatory for CCARS/GOCARS | Main checkout indexed (`393` files, `7,297` nodes); new worktree `initialized: false` (`EV-004`, WP-A) |
| `gitleaks` / `actionlint` | `gitleaks 8.30.1`, `actionlint v1.7.7` | Security / CI lint | Both installed in `~/.local/bin` / `~/go/bin` (`EV-004`); `semgrep` absent (`EV-004`) |

### 1.3 Active Repository Entrypoints, Roles, Policies, Scripts & State Stores

| Category | Paths (Verified at `fdbc9a5c`) | Role / Purpose | Status |
|---|---|---|---|
| **Root & Role Instructions** | `AGENTS.md` (10,784B), `.agent-harness/worker.md` (1,209B), `.agent-harness/auditor.md` (1,943B), `.agent-harness/security/provider-decision.md` (4,241B), `.agents/agents/harness-coordinator.md` (13,456B), `.agents/agents/c-structural-refactor.md` (8,296B), `.agents/agents/gocars-refactor/agent.md` (20,971B) | G0 root contract, legacy P0 pilot worker/auditor prompts, AGY provider boundary, Native Fast Lane & CCARS/GOCARS agents | Active; overlapping & contains stale TDMA/tool refs |
| **Harness Core & G0/Selector** | `scripts/agent_harness/agent_context.py`, `standards_policy.py`, `scope.py`, `snapshot.py`, `quality_gates.py` | G0 AGENTS SHA-256 check, C/Go V2 rule routing & ADR-0005 partitions, allowlist guard, audit snapshot, offline receipt validator | Active & unit-tested (416 tests PASS); `snapshot.py` & `standards_policy.py` retain TDMA |
| **Execution Runners & Adapters** | `scripts/agent_harness/run.py`, `pr_review.py`, `pr_review_policy.py`, `adapters/{codex.py,antigravity.py,audit.schema.json}`, `toolchains/{resolver.py,check.py}` | Codex+AGY supervised runner, read-only PR reviewer (PR-01..08), JSON schemas, Docker ESP-IDF resolver | `pr_review.py` active; `run.py` unused in Native Fast Lane |
| **P1 & MCP Subsystem** | `scripts/agent_harness/p1/{cli.py,state.py,worktrees.py,verify.py,host_gate.py,pilot.py,pilot_demo.py,auto_issue.py,draft_preview.py,process.py,runtime_boundary.py}`, `mcp_server.py`, `mcp_host.py`, `harness_mcp_setup.py` | P1-A SQLite worktree prep, P1-B2 simulated loop, P1-B3 Enterprise AGY (disabled), 3 read-only MCP stdio tools | Unit-tested; MCP SDK not installed; Enterprise runner missing `/etc/lora-harness/provider-policy.json` |
| **Doctor & Repo Guards** | `scripts/setup_harness.sh`, `scripts/harness_doctor.py`, `scripts/verify_structure.py`, `scripts/verify_no_secrets.py`, `scripts/setup_project_gate.sh` | Environment diagnostics, monorepo structure check, tracked secret scan | `doctor` & `structure` PASS; `verify_no_secrets.py` FAIL (6 false positives) |
| **CI Workflows (8)** | `.github/workflows/{ci-agent-harness.yml,ci-backend.yml,ci-clients.yml,ci-contracts.yml,ci-firmware.yml,ci-foundation.yml,ci-integration.yml,harness-issue.yml}` | GitHub Actions checks + disabled Enterprise issue workflow | `OWNER_WAIVED` (quota); Go CI failing on `gofmt`; `ci-clients` & `ci-integration` are stubs; `actionlint` flags `harness-isolated` |
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

- **Standards Selection (`EV-024`):** `standards_policy.py` deterministically parses and hashes `C_CODING_STANDARD_V2.md` (11 groups, **`104`** Rule IDs: `GOV:10 + C:20 + MEM:8 + ERR:7 + RTOS:10 + ARCH:7 + SEC:8 + RAD:9 + MAC:7 + TDMA:10 + QA:8 = 104`) and `GO_BACKEND_ENGINEERING_STANDARD_V2.md` (14 groups, **`148`** Rule IDs: `GGS:14 + GB:10 + AR:8 + GO:14 + CT:9 + MQ:12 + SC:8 + DB:10 + RT:11 + OB:12 + SE:9 + TS:11 + QG:8 + AI:12 = 148`), enforcing ADR-0005 bounded partitions (`<=4` partitions, `<=128` rules / `<=48 KB` each, `<=256` rules / `<=192 KB` aggregate). However, `C` V2 still lacks an active AST/linter enforcement beyond `quality_gates.py`, and `Go` V2's `GO-BE-002` AST CI check (`GOCARS`) is not activated in CI.
- **CCARS (`v1.4` DRAFT) & GOCARS (`v2.0` APPROVED_ON_OWNER_MERGE):** Both correctly isolate `REF-*` / `GO-ARCH-*` / `GO-BE-*` / `CG-*` from the C/Go deterministic selector (`EV-024`: `REF-001` & `GO-BE-002` rejected by `agent_context.py`). Both require CodeGraph, which is initialized on `main` (`393` files, `7,297` nodes) but **uninitialized (`initialized: false`)** on fresh isolated worktrees (`EV-004`, WP-A).
- **Domain Coverage across all 6 Domains:**

| Domain | Primary Repo Knowledge / Standard | Authority & Drift Findings | Domain Status |
|---|---|---|---|
| **C / firmware** | `C_CODING_STANDARD_V2.md`, `c-clean-code-refactoring-standard.md`, `ESP32_LORA_ENGINEERING_PLAYBOOK.md` | C V2 (104 rules) mandatory via Owner #137; playbook mixes current debug guides with stale TDMA refs (`FW-TDMA-001`). No repo `C` formatter/static-analyzer CI step. | `PARTIAL` |
| **ESP32 / ESP-IDF / FreeRTOS** | `docs/adr/0003-esp-idf-v6-1.md`, `firmware/esp-idf-version.txt`, `docs/verification/pcb-hw001-pinmap.md`, `ESP32_LORA_ENGINEERING_PLAYBOOK.md` | ESP-IDF `v6.1` pinned; HW-001 pins documented; offline build fails without cached `espressif/mqtt` (`EV-018`). Board schematic & HIL timing remain `NOT_VERIFIED`. | `PARTIAL` |
| **SX1276 / LoRa PHY / MAC** | `docs/adr/0004-pure-cad-csma-ca-mac.md`, `docs/hardware/sx1276/{README,ACTIVE_PROFILE,DRIVER_OPERATIONS,REGISTER_REFERENCE}.md`, `contracts/radio-mac/` | `ADR-0004` CAD/CSMA-CA approved, **but** `docs/hardware/sx1276/README.md` & `snapshot.py` & `standards_policy.py` retain TDMA. PA path & RF timing `TBD / NOT_VERIFIED`. | `PARTIAL` (`CNF-01/03`) |
| **Go / backend** | `GO_BACKEND_ENGINEERING_STANDARD_V2.md`, `GOCARS.md`, `.go-version`, `backend-go/go.mod`, `docs/architecture/interfaces.md` | Go `1.27.3` pinned; 13 Go packages pass `go vet/test/build` in Docker `1.27.3`, but host Go is `1.27.1` and `rf_tracker.go` fails `gofmt` in CI (`EV-017`). `coding-standards.md` points to broken `.github/instructions/`. | `PARTIAL` |
| **PostgreSQL / MQTT** | `docs/adr/0002-mqtt-5.md`, `docs/development/POSTGRESQL_OPERATIONS_GUIDE.md`, `contracts/mqtt/`, `backend-go/migrations/` | Contracts validate cleanly syntactically (`EV-019`, `EV-020`). Generated `docs/generated/db-schema.md` missing; `schedule` MQTT schemas marked superseded by ADR-0004 but still tested in `check_contracts.py`. Live DB/broker E2E `NOT_RUN`. | `PARTIAL` |
| **Web / Android / Security** | `clients/DESIGN.md`, `contracts/api/openapi.yaml`, `contracts/mqtt/session-key-security.md`, `docs/verification/session-key-*` | Web Next.js dashboard & tests exist (`ci-clients.yml` falsely claims none exist); `integration.test.ts` fails in clean worktree (`no node_modules`) and triggers `SECRET-SCAN` false positive. Android `mobile-app/` is README-only stub. No `docs/SECURITY.md` or `docs/FRONTEND.md`. | `PARTIAL` / `GAP` |

### 3.2 H.3 Complete Inventoried Artifact, Skill & Standard Register (`ART-*`)

| `artifact_id` | `kind` | `domain` | `path_or_locator` | `revision` | `approval_status` | `owner` | `activation_status` | `dependencies` | `verification_condition` | `status` | `disposition` | `review_phase` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `ART-INS-AGENTS` | `instruction` | All | `AGENTS.md` | `fdbc9a5c` (33L/10.8KB) | Active Repo Policy | Owner + Coordinator | Active (G0 SHA-checked) | `agent_context.py`, C/Go V2, ADRs | G0 byte/SHA parity + 100% rule recall | `PARTIAL` | `REFACTOR` | `P02` |
| `ART-AGT-COORD` | `instruction` | Orchestration | `.agents/agents/harness-coordinator.md` | `fdbc9a5c` (76L/13.5KB) | `OWNER-SELECTED` | Coordinator / Owner | Active (Native Fast Lane) | `AGENTS.md`, `quality_gates.py`, `pr_review.py` | Smoke + fresh-session + E2E rehearsal | `PARTIAL` | `REFACTOR` | `P02/P08` |
| `ART-AGT-WORKER` | `instruction` | Firmware | `.agent-harness/worker.md` | `fdbc9a5c` (10L/1.2KB) | Pilot P0 DRAFT | Harness / Firmware | Active in `run.py` only | `run.py`, `AGENTS.md` | Align with Codex/AGY unified worker contract | `PARTIAL` | `CONSOLIDATE` | `P02/P03` |
| `ART-AGT-AUDITOR` | `instruction` | Firmware / PR | `.agent-harness/auditor.md` | `fdbc9a5c` (19L/1.9KB) | Pilot P0 DRAFT | Harness / Auditor | Active in `run.py` only | `run.py`, `audit.schema.json`, `ADR-0004` | Remove TDMA schedule text + rubric alignment | `FAIL` | `REFACTOR` | `P02/P05` |
| `ART-SEC-PROVIDER` | `policy` | Security | `.agent-harness/security/provider-decision.md` | `fdbc9a5c` (65L/4.2KB) | `OWNER-SELECTED / NOT_VERIFIED` | Security / Owner | Informative boundary | `agy`, `codex` CLI, `auto_issue.py` | OS/container sandbox negative tests | `GAP` | `KEEP` (update on P03) | `P03` |
| `ART-STD-C2` | `standard` | C / SX1276 | `docs/development/firmware/C_CODING_STANDARD_V2.md` | `fdbc9a5c` (198L/27.9KB, 104 IDs) | Mandatory via Owner #137 | Embedded + QA | Active via `standards_policy.py` | `standards_policy.py`, `ADR-0004` | Clean parse + zero lost mandatory IDs | `PARTIAL` | `REFACTOR` | `P02` |
| `ART-STD-GO2` | `standard` | Go / DB / MQTT | `docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V2.md` | `fdbc9a5c` (287L/51.3KB, 148 IDs) | Mandatory via Owner #137 | Backend + QA | Active via `standards_policy.py` | `standards_policy.py`, `ADR-0004` | Clean parse + retire `SC` rules | `PARTIAL` | `REFACTOR` | `P02` |
| `ART-DOC-CODING-STD` | `standard` | General | `docs/development/coding-standards.md` | `fdbc9a5c` (23L/2.3KB) | Active legacy guide | Docs / Owner | Passive | Points to missing `.github/instructions/` | Fix broken link + point to Go V2 | `FAIL` | `CONSOLIDATE` | `P02` |
| `ART-STD-CCARS` | `workflow` | C refactor | `docs/development/c-clean-code-refactoring-standard.md` + `.agents/agents/c-structural-refactor.md` | `v1.4 DRAFT` (`#367`) | DRAFT / candidate | Embedded | Registered in `.agents/agents/` | `codegraph` (`initialized: false` in new worktree) | Graph-first preflight + regression | `PARTIAL` | `KEEP` | `P02/P03` |
| `ART-STD-GOCARS` | `workflow` | Go refactor | `docs/development/backend-go/GOCARS.md` + `.agents/agents/gocars-refactor/agent.md` | `v2.0` (`#359`) | `APPROVED_ON_OWNER_MERGE` | Backend | Registered in `.agents/agents/` | `codegraph`, `GO-BE-002` AST gate (inactive) | Graph preflight + GO-BE-002 CI test | `PARTIAL` | `KEEP` | `P02/P05` |
| `ART-KN-PLAYBOOK` | `knowledge` | ESP32 / SX1276 | `docs/development/firmware/ESP32_LORA_ENGINEERING_PLAYBOOK.md` | `fdbc9a5c` (252L/48.1KB) | Informative (`PROPOSED`) | Embedded | Passive reference | `ADR-0004`, `SX1276` docs | Align `FW-TDMA-001` & `tdma_common` | `PARTIAL` | `REFACTOR` | `P02/P07` |
| `ART-KN-SX1276` | `knowledge` | SX1276 / PHY | `docs/hardware/sx1276/*.md` (4 files) | `fdbc9a5c` | Informative / routed by `AGENTS.md` | Embedded / RF | Active routing in `AGENTS.md` | `ADR-0004`, Semtech Rev.7 datasheet | Update `README.md` from TDMA to CAD | `PARTIAL` | `REFACTOR` | `P02` |
| `ART-KN-CORPUS` | `knowledge` | Harness V2 | `docs/references/harness-engineering/{README,REFERENCE_INDEX,knowledge/01..06}.md` | `fdbc9a5c` (`#419`) | Informative MIT extraction | Harness | Active offline lookup (`EV-025A/026`) | `HARNESS_SPEC.md`, `HARNESS_MASTER_PLAN.md` | `docker --network=none` 248/248 anchors PASS | `VERIFIED` | `KEEP` | `P01/P02` |
| `ART-ADR-0004-MAC` | `authority` | Radio MAC | `docs/adr/0004-pure-cad-csma-ca-mac.md` | `fdbc9a5c` (`#273`) | `OWNER_APPROVED_DESIGN` | Owner / RF | Active MAC V2 authority | Supersedes `ADR-0001`, `0004-theoretical-*` | All Harness/doc consumers aligned | `VERIFIED` | `KEEP` | `P02` |
| `ART-ADR-README` | `authority` | Architecture | `docs/adr/README.md` + `0004-theoretical-timing-guard-budget.md` | `fdbc9a5c` | Mixed (`#60` R1 + `#273`) | Architecture / Owner | Active index | `docs/adr/*` | Resolve duplicate `0004` + TDMA summary | `FAIL` | `REFACTOR` | `P02` |
| `ART-DOC-ARCH` | `knowledge` | Architecture | `docs/architecture/{system-overview,interfaces,deployment,event-driven-edge-design}.md` | `fdbc9a5c` | Mixed (`R1 DRAFT` / `#230`) | Architecture | Passive | `ADR-0004`, `contracts/` | Create root `ARCHITECTURE.md` index | `GAP` | `ADD` (`ARCHITECTURE.md`) | `P02/P07` |
| `ART-SOP-FASTLANE` | `sop` | Workflow | `docs/development/harness-fast-lane.md` | `v1.2` | `OWNER-SELECTED / E2E_NOT_VERIFIED` | Coordinator | Active default SOP | `AGENTS.md`, `quality_gates.py`, `pr_review.py` | Remove missing `mcp_execution.py` ref + E2E | `PARTIAL` | `CONSOLIDATE` | `P02/P03` |
| `ART-SOP-QG` | `sop` | Feedback | `docs/development/harness-quality-gates.md` | `fdbc9a5c` | Active runbook | Harness | Active | `quality_gates.py`, `standards_policy.py` | Remove non-existent `.github/instructions/` refs | `PARTIAL` | `KEEP` | `P02/P05` |
| `ART-SOP-OLD` | `sop` | Legacy SOPs | `AI_TASK_START_PROTOCOL.md`, `agy-native-coordinator-sop.md`, `agent-harness-{firmware,p1}.md`, `agy-supervised-pilot.md`, `harness-{automatic-issue,mcp-onboarding,onboarding}.md` | `fdbc9a5c` | DRAFT / Superseded | Harness | Passive / overlapping | `harness-fast-lane.md` | Deprecate/consolidate after mapping | `PARTIAL` | `DEPRECATE` / `CONSOLIDATE` | `P02` |
| `ART-SKL-GAP` | `knowledge` | ESP32 Skills | `docs/development/firmware/ESP32_SKILL_GAP_ANALYSIS_PLAN.md` | `v0.2.0` (`#97`) | `AUDIT_NOT_COMPLETE` | Embedded | **NOT_INSTALLED / NOT_ACTIVE** | Cites `0001-hybrid-tdma.md` | Complete external audit or build `skill_registry` | `NOT_VERIFIED` | `REFACTOR` | `P02/P03` |
| `ART-SKL-PROV-AGY` | `skill` | Provider local | `~/.gemini/config/skills/` & `~/.gemini/config/plugins/` | Host local | Provider-local (non-LoRa) | Host user | Installed in AGY host | Outside repo `scripts/agent_harness/` | External to repo; no repo authority | `NOT_VERIFIED` | `KEEP_OUTSIDE_REPO` | `P03` |
| `ART-SKL-PROV-CODEX` | `skill` | Provider local | `~/.codex/skills/` | Host local | Provider-local (non-LoRa) | Host user | Present on disk (`ls` only) | Outside repo; 0/5 ESP32 skills | External to repo; no repo authority | `NOT_VERIFIED` | `KEEP_OUTSIDE_REPO` | `P03` |
| `ART-SCR-G0` | `script` | G0 Gate | `scripts/agent_harness/agent_context.py` | `fdbc9a5c` | Active | Harness Host | Active + unit-tested | `AGENTS.md`, `standards_policy.py` | 416/416 suite + negative SHA/symlink tests | `PARTIAL` | `KEEP` | `P02/P03` |
| `ART-SCR-SELECTOR` | `script` | Rule Selector | `scripts/agent_harness/standards_policy.py` | `fdbc9a5c` | Active (`ADR-0005`) | Harness Host | Active + unit-tested | `C_CODING_STANDARD_V2.md`, `GO_*_V2.md`, `scope.py` | Unit tests + retire `TDMA`/`SC` after ADR-0004 | `PARTIAL` | `REFACTOR` | `P02` |
| `ART-SCR-SCOPE` | `script` | Scope Guard | `scripts/agent_harness/scope.py` | `fdbc9a5c` | Active | Harness Host | Active + unit-tested | GitHub Issue body | Fix prose-before-bullet handling (`EV-025B`) | `PARTIAL` | `REFACTOR` | `P03` |
| `ART-SCR-SNAPSHOT` | `script` | Audit Snapshot | `scripts/agent_harness/snapshot.py` | `fdbc9a5c` | Active | Harness Host | Active in `run.py` | `REFERENCES` (`0001-hybrid-tdma.md`) | Replace `0001` with `0004-pure-cad-csma-ca-mac.md` | `FAIL` | `REFACTOR` | `P02` |
| `ART-SCR-QG` | `script` | Quality Gates | `scripts/agent_harness/quality_gates.py` | `fdbc9a5c` | Active (`#88`) | Harness Host | Active + unit-tested | `scope.py`, `standards_policy.py`, `adapters/antigravity.py` | Clean baseline (`SECRET-SCAN`) + remove phantom policy prefixes | `PARTIAL` | `KEEP` | `P02/P05` |
| `ART-SCR-PR` | `script` | PR Review | `scripts/agent_harness/pr_review.py` + `pr_review_policy.py` | `fdbc9a5c` | Active | Harness Host | Active + unit-tested | `gh`, `CODEOWNERS`, `antigravity.py`, `standards_policy.py` | Add 6-dim rubric + live E2E audit check | `PARTIAL` | `KEEP` | `P05/P08` |
| `ART-SCR-RUN` | `script` | Orchestrator | `scripts/agent_harness/run.py` | `fdbc9a5c` | Active (unused in Fast Lane) | Harness | Blocked at baseline `SECRET-SCAN` (`EV-025C`) | `codex.py`, `antigravity.py`, `quality_gates.py`, `resolver.py` | Consolidate with `p1/pilot.py` + `p1/state.py` | `GAP` | `CONSOLIDATE` | `P08` |
| `ART-SCR-ADAPT-CODEX` | `script` | Adapter | `scripts/agent_harness/adapters/codex.py` | `fdbc9a5c` | Active | Harness | Unit-tested | `antigravity.py`, `codex` CLI (`~/.local/bin`) | Dual-provider E2E smoke test | `PARTIAL` | `KEEP` | `P03` |
| `ART-SCR-ADAPT-AGY` | `script` | Adapter/Schema | `scripts/agent_harness/adapters/{antigravity.py,audit.schema.json}` | `fdbc9a5c` | Active | Harness | Unit-tested | `audit.schema.json` | Extend with 6-dim 0–2 rubric (`H2-ORC-04`) | `PARTIAL` | `REFACTOR` | `P05/P08` |
| `ART-SCR-RESOLVER` | `script` | Toolchain | `scripts/agent_harness/toolchains/{resolver.py,check.py}` | `fdbc9a5c` | Active | Harness / FW | Active (`--network=none` fails on `espressif/mqtt`) | `espressif/idf:v6.1`, `firmware/esp-idf-version.txt` | Vendor/cache `managed_components` for offline build | `FAIL` | `REFACTOR` | `P03` |
| `ART-SCR-P1-CLI` | `script` | P1 Prep | `scripts/agent_harness/p1/cli.py` + `host_gate.py` | `fdbc9a5c` | Active (P1-A) | Harness | Blocked on Issue #422 (`EV-025B`) | `scope.py`, `p1/state.py`, `p1/worktrees.py` | Consolidate into unified startup/control plane | `PARTIAL` | `CONSOLIDATE` | `P03/P08` |
| `ART-SCR-P1-STATE` | `script` | State Store | `scripts/agent_harness/p1/state.py` | `fdbc9a5c` | Active (P1 SQLite) | Harness | Unit-tested; unused in Fast Lane | `.lora-p1-state/state.sqlite` | Couple to `feature_list.json` & Orchestrator | `PARTIAL` | `EXTEND` | `P04/P08` |
| `ART-SCR-P1-WT` | `script` | Worktrees | `scripts/agent_harness/p1/worktrees.py` + `verify.py` + `draft_preview.py` | `fdbc9a5c` | Active (P1) | Harness | Unit-tested | `git worktree` | Reuse in P03/P04/P08 | `PARTIAL` | `KEEP` | `P03/P04` |
| `ART-SCR-P1-PROC` | `script` | Process Guard | `scripts/agent_harness/p1/process.py` + `runtime_boundary.py` | `fdbc9a5c` | Active (P1) | Harness | Unit-tested | `subprocess`, `docker` | Extend timeout/cancel tracking to Coordinator | `PARTIAL` | `KEEP` | `P03` |
| `ART-SCR-P1-PILOT` | `script` | Simulated Loop | `scripts/agent_harness/p1/{pilot.py,pilot_demo.py}` | `fdbc9a5c` | Simulated (`SIMULATED` only) | Harness | Unit-tested (mock callbacks) | `p1/state.py`, `antigravity.py` | Replace with real Maker-Checker loop (`P08`) | `GAP` | `REFACTOR` | `P08` |
| `ART-SCR-P1-AUTO` | `script` | Enterprise CI | `scripts/agent_harness/p1/auto_issue.py` | `fdbc9a5c` | Disabled (`Enterprise AGY only`) | Harness | Blocked (no `/etc/lora-harness/provider-policy.json`) | `harness-issue.yml`, `agy -p` | Retain disabled until Enterprise path verified | `NOT_VERIFIED` | `KEEP_DISABLED` | `P03/P08` |
| `ART-SCR-MCP` | `script` | MCP Bridge | `scripts/agent_harness/{mcp_server.py,mcp_host.py,mcp_smoke.py}` + `scripts/harness_mcp_setup.py` | `fdbc9a5c` | Optional P0 | Harness | SDK not installed; AGY entry blocked | `p1/cli.py`, `p1/host_gate.py`, `mcp==2.3.0` | Align docs (`OD-01`); remove phantom `harness_prepare_issue` | `PARTIAL` | `CONSOLIDATE` | `P03` |
| `ART-SCR-DOCTOR` | `script` | Env Doctor | `scripts/harness_doctor.py` | `fdbc9a5c` | Active | Harness | PASS (`EV-008`), misses Go/Web/off-PATH `codex` | `AGENTS.md`, `docker`, `gh` | Add Go `1.27.3`, Web deps, off-PATH `codex` checks | `PARTIAL` | `REFACTOR` | `P03` |
| `ART-SCR-SETUP` | `script` | Bootstrap | `scripts/setup_harness.sh` + `setup_project_gate.sh` | `fdbc9a5c` | Active | Harness | Read-only `--json` works | `harness_doctor.py`, `harness_mcp_setup.py` | Wrap/unify `init` + baseline smoke (`OD-03`) | `PARTIAL` | `REFACTOR` | `P03` |
| `ART-SCR-STRUCT` | `script` | Structure Guard | `scripts/verify_structure.py` + `verify_no_secrets.py` | `fdbc9a5c` | Active | Harness / CI | `structure` PASS (`EV-009`); `secrets` FAIL 6 FP (`EV-010`) | `ci-foundation.yml`, `ci-agent-harness.yml` | Fix false positives without weakening secret regex | `PARTIAL` | `KEEP` / `REFACTOR` | `P02/P05` |
| `ART-CI-HARNESS` | `ci` | Harness CI | `.github/workflows/{ci-agent-harness.yml,ci-foundation.yml,ci-contracts.yml,ci-firmware.yml}` | `fdbc9a5c` | `OWNER_WAIVED` (quota) | Repo / CI | Local equivalents PASS except IDF offline | `tests/agent_harness`, `contracts/`, `firmware/` | Keep aligned with unified check CLI (`P05`) | `PARTIAL` | `KEEP` | `P05` |
| `ART-CI-BACKEND` | `ci` | Backend CI | `.github/workflows/ci-backend.yml` | `fdbc9a5c` | `OWNER_WAIVED` (quota) | Backend | Fails `gofmt` on `rf_tracker.go:140-145`; `vet/test/build` PASS in `1.27.3` | `backend-go/`, `.go-version` | Fix `rf_tracker.go` in Go Issue; update stub notice | `FAIL` | `REFACTOR` | `Pre-P02/P05` |
| `ART-CI-CLIENTS` | `ci` | Client CI | `.github/workflows/ci-clients.yml` | `fdbc9a5c` | `OWNER_WAIVED` (quota) | Clients | Placeholder README check only | `clients/web-dashboard/` | Replace stub with real Next.js lint/test/build | `GAP` | `REFACTOR` | `P05` |
| `ART-CI-INTEG` | `ci` | Integration CI | `.github/workflows/{ci-integration.yml,harness-issue.yml}` | `fdbc9a5c` | `OWNER_WAIVED` (quota) | Infra / Harness | Stub warning + disabled Enterprise runner (`actionlint` err) | `tests/integration/`, `actionlint` | Wire Docker E2E + add `actionlint.yaml` | `GAP` | `REFACTOR` | `P05/P06` |

### 3.3 H.4 & H.5 — Independent Routing Test Matrix (`H-A01..H-A12`)

| Case | Scenario & Target | Expected | Actual Observed Result & Metrics | Status | Evidence |
|---|---|---|---|---|---|
| `H-A01` | Inventory & authority across instructions, standards, playbooks, provider/repo Skills | Exact paths/revisions, activation vs presence distinguished | All 45 `ART-*` repo/host surfaces inventoried; `SKILL.md` presence != repo activation; 0/5 ESP32 skills installed | `PARTIAL` | `EV-004`, `EV-006` |
| `H-A02` | C V2 deterministic selection + negative bounds (`sx1276_driver.c` + `RTOS-003`) | Deterministic bounded C rules; reject unknown/wrong-SHA/traversal | **PASS:** Selected `77` C rules (`32,131` B `agent_input`, schema v1); negative probes (`FAKE-999`, bad SHA, `../outside.c`) all exit `2` `BLOCKED`. Gap: interactive CLI lacks runtime enforcement hook | `PARTIAL` | `EV-024` |
| `H-A03` | Go V2 deterministic selection (`internal/mqtt/event_consumer.go`) | Bounded Go rules union (`MQ`, `CT`, `DB`, `RT`, `SE`, `TS`), zero C rules | **PASS:** Selected `140` Go rules (`63,815` B `agent_input`, schema v2 partitioned, `0` C rules); `140 > 128` triggers ADR-0005 partitioning cleanly | `PARTIAL` | `EV-024` |
| `H-A04` | C / ESP32 / ESP-IDF / FreeRTOS routing & build | Pin/SDK authority + C rules + v6.1 build | C rules select `RTOS/MEM/ERR`; `docs/hardware/sx1276/` & `ESP32_LORA_ENGINEERING_PLAYBOOK.md` found; `--network=none` clean build FAILS (`exit 2`, `espressif/mqtt` uncached) | `FAIL` (offline build) | `EV-018`, `EV-024` |
| `H-A05` | SX1276 / LoRa / Custom MAC routing (`node_smart_backoff.c`) | Route to ADR-0004 CAD/CSMA-CA & SX1276 refs; flag stale TDMA | Selected `71` C rules (`30,570` B); however `snapshot.py`, `auditor.md`, `sx1276/README.md`, and playbook still conflict with ADR-0004 | `FAIL` (authority drift) | `EV-006`, `EV-024` |
| `H-A06` | Go backend / PostgreSQL / MQTT routing (`000003_event_storage_and_health.up.sql`) | Route to Go V2 `DB/CT/RT/SE/TS` rules & migration contracts | Selected `66` Go rules (`35,635` B, `0` C rules); Go `1.27.3` `vet/test/build` PASS in Docker; live PostgreSQL/Mosquitto integration `NOT_RUN` | `PARTIAL` | `EV-017`, `EV-024` |
| `H-A07` | CCARS / GOCARS workflow triggers & CodeGraph gate | Graph-first required; `REF-*`/`GO-BE-*` rejected by C/Go selector | Negative probes confirm `REF-001` & `GO-BE-002` exit `2` `BLOCKED`; however worktree CodeGraph is uninitialized (`initialized: false`), blocking mutation until indexed | `PARTIAL` | `EV-004`, `EV-024` |
| `H-A08` | Docs-only vs `contracts/` vs Harness control isolation | Docs-only loads 0 C/Go rules & low QG risks; `contracts/`/`AGENTS.md` trigger `SECURITY-CHECK`/`TOOLING-CHECK` | **PASS:** `HARNESS_BASELINE_REPORT.md` -> `0` rules (`10,952` B), QG risks `["all"]`; `contracts/mqtt/topics.md` -> `0` C/Go rules, QG `["all","infra","mqtt","security"]`; `AGENTS.md` -> `0` C/Go rules, QG `["all","security","tooling"]` | `VERIFIED` (selector + QG routing) | `EV-024` |
| `H-A09` | Skill trigger, least privilege & untrusted input | Missing capability blocks; active skill/Full Access cannot bypass runtime sandbox | `scope.py`/`pr_review_policy.py` prompt-injection & traversal unit tests PASS; however Native Fast Lane Full Access has **no OS/network sandbox** and provider skills have no repo permission registry | `GAP` | `EV-012`, `ART-SEC-PROVIDER` |
| `H-A10` | Knowledge quality, links & drift | Valid links, aligned SDK/architecture | `REFERENCE_INDEX.md` `248/248` anchors valid (`EV-026`); `coding-standards.md` has 1 broken link (`EV-007`); multiple docs retain TDMA or Go v1.0 draft refs (`EV-006`) | `PARTIAL` | `EV-006`, `EV-007`, `EV-026` |
| `H-A11` | Skill effectiveness & context budget baseline | Measure baseline rule counts, `agent_input` bytes, discovery cost | Measured `agent_input` sizes (`10,952`–`63,815` B) across probes (`EV-024`); discovery cost / token telemetry & ablation runs are `NOT_RUN` (protocol frozen in WP-F) | `NOT_VERIFIED` | `EV-024` |
| `H-A12` | Skill extensibility (`esp32-debugging` inert scenario) | Discover, register, version, route, verify, disable, rollback without core Harness edits | **`GAP`:** Repo has **no** `skill_registry` or `skill_router` in `scripts/agent_harness/`. Adding `esp32-debugging` today requires manual edits to `AGENTS.md`, `harness-coordinator.md`, `ESP32_SKILL_GAP_ANALYSIS_PLAN.md`, and `quality_gates.py` allowlists. **Proposed P02/P03/P05/P08 fix:** declarative version-pinned skill manifest + Host `skill_router` decoupled from mandatory `standards_policy.py` (preserving C/Go V2 gates intact) | `GAP` | `EV-005`, `ART-SKL-GAP` |

---

## 4. WP-C — Requirements Traceability Matrix Summary

Full 45-row machine-readable traceability is recorded in [HARNESS_RTM.json](HARNESS_RTM.json) (`schema_version: 1.1.0`). Each record binds `wp_h_artifact_refs` (`ART-*`), `wp_h_case_refs` (`H-A01..H-A12`), `applicable_rule_ids`, `routing_receipt_refs`, `evidence_refs`, per-ID `evidence_hashes` (`{ev_id: sha256}`), and an unambiguous `evidence_hash` (`direct_artifact_sha256` for 1 receipt or `sha256_of_sorted_evidence_hashes_map` for multiple receipts). Exact ID set equality (`45` unique `H2-*` IDs) was verified against `HARNESS_SPEC.md` §4, `HARNESS_MASTER_PLAN.md` §14, and `REFERENCE_INDEX.md` §2 (`EV-024`, `build_artifacts.py`).

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
| `agent_context.py --repo <candidate>` | G0 Host Context | Python 3.12.3 | `0` | `HOST_CONTEXT_LOADED` (`09212ed3...`), cwd `/home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP` | `EV-001` |
| `harness_doctor.py --profile all --json` | Env preflight | Python 3.12.3 | `0` | `ready: true` (`codex_cli` WARN off-PATH) | `EV-008` |
| `verify_structure.py` | Static monorepo layout | Python 3.12.3 | `0` | `PASS` | `EV-009` |
| `unittest discover -s tests/agent_harness -v` | Harness unit suite | Python 3.12.3 | `0` | **416 tests OK** (`54.210s`) | `EV-012` |
| `quality_gates.py --repo . --base fdbc9a5c...` | Static gates (NOT waived) | Python 3.12.3 | `1` | `BLOCKED`: `SECRET-SCAN` FAIL (`integration.test.ts:31`); `DIFF-CHECK` PASS | `EV-011` |
| `verify_no_secrets.py` | Tracked/index secret regex | Python 3.12.3 | `1` | `FAIL` on 6 files (all false positives) | `EV-010`, `EV-013` |
| `gitleaks detect --no-git --source . --redact` | External secret scan | gitleaks 8.30.1 | `1` | 10 `generic-api-key` hits (all test/SHA256 strings) | `EV-014` |
| `actionlint .github/workflows/*.yml` | GitHub Actions lint | actionlint v1.7.7 | `1` | 1 error: `harness-issue.yml:28` unknown label `harness-isolated` | `EV-023` |
| `contracts/tests/check_contracts.py` + `tests/contract` | Contract schema + unit | Python 3.12.3 | `0` | `check_contracts` PASS (12 schemas, 40 MQTT, 18 WS, 15 REST); 15/15 unit OK | `EV-019`, `EV-020` |
| `unittest discover -s tests/unit -v` | Firmware/tool Python+C unit | Python 3.12.3 | `0` | **44 tests OK** (`2.881s`) | `EV-021` |
| `docker golang:1.27.3-alpine` Go `vet/test/build` | Backend Go 1.27.3 | `golang:1.27.3-alpine` | `0` (subcmds) | `go vet`, `go test` (13 pkgs), `go build ./cmd/server` **all PASS** when modcache mounted; `gofmt -d` flags `rf_tracker.go` | `EV-017` |
| `docker espressif/idf:v6.1 --network=none` | Clean-copy firmware build | `espressif/idf:v6.1` | `2` (each build) | **FAIL** on both `gateway_master` (`exit 2`) & `sensor_node` (`exit 2`): `espressif/mqtt (1.1.0)` needs network | `EV-018` |
| `node --test --experimental-strip-types tests/*.test.ts` | Web dashboard unit tests | Node v22.23.2 | `1` | `api_client.test.ts` & `rf_quality.test.ts` PASS; `integration.test.ts` FAILS (`Cannot find package 'react'` in clean worktree) | `EV-022` |
| `docker --network=none` Corpus Check | Local knowledge offline proof | `python:3.12-slim` | `0` | `pdf_count=0`, 6 `knowledge/*.md`, `248/248` anchors valid | `EV-025A`, `EV-026` |
| `p1/cli.py prepare --issue 422` | P1-A dry-run preflight | Python 3.12.3 | `2` | **BLOCKED (`exit 2`):** `Malformed Issue or missing strict scope` (`EV-025` wrapper exited `0` via `\|\| echo`) | `EV-025B` |
| `run.py --issue 422` | Supervised runner preflight | Python 3.12.3 | `2` | **BLOCKED (`exit 2`):** `Source secret/path scan failed` (`EV-025` wrapper exited `0` via `\|\| echo`) | `EV-025C` |

### 5.2 Critical Baseline Triage (`SECRET-SCAN` P0 & `go-format-vet-test-build` CI)

1. **`SECRET-SCAN` P0 (`clients/web-dashboard/tests/integration.test.ts:31`) — CONFIRMED FALSE POSITIVE (`EV-010`, `EV-011`, `EV-013`, `EV-014`):**
   - `quality_gates.py:56` matches `access_token: "jwt-token-admin01-session"` inside a mocked `globalThis.fetch` `Response` in `clients/web-dashboard/tests/integration.test.ts:31`. Inspection confirms synthetic test strings only; zero real credentials exist.
   - `verify_no_secrets.py:12` also flags 6 tracked files: `backend-go/internal/auth/service_test.go`, `clients/web-dashboard/src/app/login/page.tsx:75`, `clients/web-dashboard/src/app/users/page.tsx:305`, `clients/web-dashboard/src/types/api.ts:14,44`, `clients/web-dashboard/tests/integration.test.ts:296`, and `scripts/agent_harness/quality_gates.py:55`.
   - **Remediation Proposal (separate scoped Issue, NOT in P01):** Refactor test fixtures to use non-literal/placeholder prefixes (`REPLACE_` / `mock_`) or narrow `verify_no_secrets.py` AST/string-literal rules **without** weakening real secret detection. Not waived.
2. **`go-format-vet-test-build` CI Failure (`46049348761`, `46048385376`, `46047680659`) — ROOT CAUSE CONFIRMED (`EV-015`, `EV-016`, `EV-017`):**
   - All three CI runs (`d76ce89`, `332e09e`, `fdbc9a5c`) executed `setup-go@v5` (`go1.27.3`), passed `Verify pinned Go toolchain and module`, and failed identically at step `Go formatting` (`test -z "$(gofmt -l .)"`, exit code `1`) before `go vet`, `go test`, or `go build` executed.
   - Local `gofmt -l .` confirms the sole unformatted file is `backend-go/internal/presence/rf_tracker.go` (lines `140-145`, introduced in `67e3bcf` / PR #400): doc-comment bullets `// - ...` require `//   - ...` under Go 1.27 `gofmt`.
   - Running `go vet ./...`, `go test ./...`, and `go build ./cmd/server` in `golang:1.27.3-alpine` (`GOTOOLCHAIN=local`) with Go module cache mounted exits `0` across all 13 tested Go packages.
   - **Owner Decision:** GitHub Actions CI is **`OWNER_WAIVED`** (exhausted quota; NOT `CI_PASS`), while `gofmt` FAIL and Go `vet/test/build` PASS remain accurately recorded with zero Go edits in #422. Remediation (`gofmt -w backend-go/internal/presence/rf_tracker.go`) belongs to a separate scoped Go Issue.

---

## 6. WP-E — Orchestration, Role Isolation & Maturity Audit

- **Logical Orchestrators vs Actual Execution (`EV-003`, `EV-005`, `EV-025B`, `EV-025C`):** Four separate orchestration surfaces exist: (1) `.agents/agents/harness-coordinator.md` (Native Fast Lane — instruction-driven, active default); (2) `scripts/agent_harness/run.py` (Codex Worker + AGY Auditor CLI runner — unused in Fast Lane, blocked by baseline `SECRET-SCAN`); (3) `scripts/agent_harness/p1/pilot.py` (simulated callback state machine with SQLite `PilotLedger`); (4) `scripts/agent_harness/p1/auto_issue.py` (Enterprise AGY CI — disabled until `HARNESS_ENTERPRISE_READY == 'true'` and `/etc/lora-harness/provider-policy.json`).
- **Role Isolation & Trust Boundaries:** `pr_review.py` + `antigravity.py` enforce strict read-only audit payload validation and SHA immutability (`EV-012`), and `harness-coordinator.md` delegates `Fresh-Independent-Auditor` via `invoke_subagent`. However, per `.agent-harness/security/provider-decision.md`, Native Full Access provides **context separation only, NOT OS/filesystem/network isolation** (`H2-TOL-02` `GAP`, `P0`).
- **ORC-01..08 & FBK-10..11 Assessment:**
  - `H2-ORC-01/05` (`PARTIAL`/`GAP`): `p1/state.py` SQLite CAS (`PLANNED`..`CANCELLED`) and `PilotLedger` (`READY`..`AWAIT_HUMAN`) exist only in unused/simulated P1 modules; Native Fast Lane lacks persistent run contracts or crash recovery.
  - `H2-ORC-03/04` (`GAP`): No external multi-round Maker-Checker loop (`>=5`-round pilot `NOT_RUN`), and `audit.schema.json` lacks the 6-dimension `0-2` evaluator rubric (`ACCEPT`/`REVISE`/`BLOCK`) and human calibration.
  - `H2-ORC-06/07/08` & `H2-FBK-10/11` (`GAP` / `CONDITIONAL_NOT_EXERCISED`): No pattern assessment, orchestration tax telemetry, concurrency cap, meta-improvement ratchet, or anti-Goodhart holdout suite exists.
- **Evidence-Based Maturity Rating:** **Level 1 (Goal Runner) operational with unintegrated Level 3 (Multi-Agent Loop) components** (`run.py`, `pr_review.py`, `p1/pilot.py`). Level 3 E2E is **NOT_VERIFIED**; Level 4 and Level 5 Fleet are **NOT_IMPLEMENTED / CONDITIONAL_NOT_EXERCISED**. Orchestration tax is **NOT_RUN**.

---

## 7. WP-F — Benchmark Protocol & Metric Specifications (`HARNESS_SPEC.md §7.3` / `OD-06`)

All baseline benchmark metrics are **`NOT_RUN`** (no tuning, no fabricated measurements). The frozen protocol below is proposed for Owner resolution of **OD-06** before P02 edits begin:

### 7.1 Representative Task Cohort, Seeded Defects & Experimental Controls

- **7 Frozen Cohort Tasks:** `T-FW-01` (`sx1276_driver` IRQ/FIFO), `T-FW-02` (`node_smart_backoff` CAD/CSMA-CA vs ADR-0004), `T-GO-01` (`internal/mqtt` + `migrations/` idempotent ingest), `T-WEB-01` (`clients/web-dashboard/` API/UI alignment), `T-CON-01` (`contracts/mqtt/` schema + security gate), `T-DOC-01` (ordinary docs-only isolation), `T-REC-01` (seeded baseline failure + interrupted run recovery + scope escape).
- **2 Held-Out Blind Tasks (reserved for P10):** 1 cross-component Firmware↔MQTT change + 1 Go auth/RBAC change.
- **Seeded Negative Fixtures (zero-tolerance):** Unknown Rule ID, stale `AGENTS.md` SHA-256, out-of-scope file edit, TDMA/LoRaWAN reintroduction, unauthorized provider Skill activation, forged Host receipt.
- **Matched Constants:** Same model, reasoning preset, starting commit SHA, container toolchain digests (`golang:1.27.3-alpine`, `espressif/idf:v6.1`), and frozen test oracle; `N = 3` repetitions per task/variant. Zero denominator is reported as `N/A` with rationale, never `100%`.

### 7.2 Complete Metric Definitions, Units, Procedures & Proposed Thresholds (`HARNESS_SPEC.md §7.3`)

| Metric | Definition | Unit | Numerator | Denominator | Measurement Procedure | Proposed Acceptance Threshold | Baseline |
|---|---|---|---|---|---|---|---|
| **Instruction SNR** | Ratio of task-relevant instruction units loaded to all loaded instruction units | Ratio `[0,1]` (report bytes & units separately) | Task-relevant loaded instruction units/bytes (per frozen relevance rubric) | Total instruction units/bytes injected into initial Worker context | Snapshot `agent_context.py` + `AGENTS.md` + Skill context per task; label each section against frozen task rubric | Increase vs P01 baseline with `0` mandatory rule drops | `NOT_RUN` |
| **Knowledge Visibility Gap** | Share of required task knowledge items absent from repository | Ratio `[0,1]` (zero denom = `N/A`) | Required engineering/product knowledge items missing or external-only | Total enumerated required knowledge items for cohort task | Expert checklist per task (pins, SDK version, ADR, contracts, startup/verify cmds) audited against repo files only | `< 0.10` (`< 10%`), `0` on safety/authority items | `NOT_RUN` |
| **Context Rebuild Cost** | Cost for a fresh session (no prior chat) to identify exact next executable step & startup/verify path | Tool calls, Wall time (`s`), Input tokens | Sum of tool calls / seconds / tokens until valid startup + `5/5` Fresh Session answers | `1` per fresh-session trial (aggregate mean & max across `N=3` trials) | Launch fresh zero-history session with repo artifacts only (`HARNESS_SPEC.md §7.2`); measure until `5/5` verified + first smoke cmd | `5/5` Fresh Session accuracy; measurable reduction vs P01 (`P06/P10`) | `NOT_RUN` |
| **Discovery Cost** | Cost to locate required authoritative files/APIs/contracts for a task | Tool calls, Wall time (`s`), Input tokens | Tool calls / seconds / tokens from task start to first edit or valid plan | `1` per task trial (report unavailable token telemetry separately) | Instrument session logs from task prompt to pre-edit freeze; exclude build execution time | Non-regression / decrease vs P01 baseline | `NOT_RUN` |
| **Verified Completion Rate (VCR)** | Share of activated feature slices achieving trusted Host `passing` | Ratio `[0,1]` (zero denom = `N/A`) | Activated feature slices passing all required Host checks + independent audit | Total activated feature slices in evaluation cohort | Compute from trusted `feature_list.json` / Host receipts at cohort end | `= 1.00` for ready non-blocked cohort slices (`H2-STA-02` blocks next activation when `<1.0`) | `NOT_RUN` |
| **Verification Gap** | Rate of premature/false completion claims by Worker without passing evidence | Ratio `[0,1]` (zero denom = `N/A`) | Worker completion claims rejected by trusted Host checks or Auditor | All Worker completion declarations in cohort | Compare Worker final handoff status against deterministic Host receipts & Auditor findings | `= 0.00` (zero unverified completion accepted) | `NOT_RUN` |
| **Time to First Passing Test** | Elapsed wall-clock time from clean checkout startup to first required smoke PASS | Seconds (`s`) | `t(first required smoke check exit 0) - t(clean checkout start)` | `1` per clean-checkout trial | Time clean worktree bootstrap (`init` / `doctor` + baseline smoke) in isolated container/worktree | Bounded startup SLA (frozen per profile in P03) & decreasing trend | `NOT_RUN` |
| **Mandatory Rule Recall** | Fraction of expected applicable mandatory C/Go V2 rules injected by Host | Ratio `[0,1]` (zero denom = `N/A`) | Correctly injected applicable mandatory Rule IDs | Independently derived expected mandatory Rule IDs for task diff | Compare `agent_context.py` `selected_ids` against independent expert oracle across cohort | **`1.00` (100% — zero tolerance for missing mandatory rules)** | `NOT_RUN` |
| **Skill Routing Accuracy** | Fraction of eligible tasks selecting exact authorized Knowledge/Skill/Procedure | Ratio `[0,1]` (zero denom = `N/A`) | Tasks selecting exact expected authorized source/Skill without irrelevant load | Total eligible routing tasks in cohort (`H-A01..H-A12`) | Compare coordinator/router selection against frozen routing oracle (`positive` + `docs-only` + `conflict` cases) | `>= 0.90`, `0` unauthorized Skill activations (`1.00` rejection on negative fixtures) | `NOT_RUN` |
| **Irrelevant Load Ratio** | Share of unrelated rule IDs or bytes loaded into prompt | Ratio `[0,1]` (units & bytes separate) | Unrelated Rule IDs or UTF-8 bytes loaded (e.g. C rules on Go/docs task) | Total Rule IDs or UTF-8 bytes loaded in Worker context | Inspect `standards_policy` + Skill payload against task domain oracle | `0.00` cross-domain bleed (C<->Go<->docs) | `NOT_RUN` |
| **Orchestration Tax** | Total coordination, review, conflict, retry, and resource overhead vs sequential baseline | Wall `s`, Person-min, Retries, Tokens/USD, Defects | Sum of dispatch + wait + review + merge-reconciliation time/cost/retries/escaped defects | Verified slices delivered (or matched sequential baseline) | Measure end-to-end across matched sequential vs multi-round orchestrated cohort (`P08-E`, `P09`) | Report raw vector; parallel/graph allowed only if net verified throughput > tax (`H2-ORC-07`) | `NOT_RUN` |
| **Evaluator Calibration & Meta-Loop** | Checker defect recall, human-verdict agreement, round count, Keep/Reject ratio | Ratio / Count | True defects caught / human-agreed verdicts / rounds to ACCEPT / kept experiments | Seeded+real defects / total audited runs / total rounds / total experiments | `3–5` human-labeled calibration rounds (`P05/P08`); `>=5`-round pilot; holdout check (`H2-FBK-10/11`) | `0` missed P0/P1 defects; `0` Goodhart guardrail regressions | `NOT_RUN` |

---

## 8. WP-G — Migration Map, Open Decisions & Prioritized P02 Slices

### 8.1 Migration Disposition Map (`45 ART-*` Complete Coverage)

Complete per-artifact `disposition`, `owner`, `approval_status`, `dependencies`, and `verification_condition` are recorded in **§3.2 (`ART-*` table)**. Summary by disposition:
- **`KEEP` (`8`):** `ART-KN-CORPUS`, `ART-ADR-0004-MAC`, `ART-SEC-PROVIDER`, `ART-STD-CCARS`, `ART-STD-GOCARS`, `ART-SOP-QG`, `ART-SCR-G0`, `ART-SCR-QG`, `ART-SCR-PR`, `ART-SCR-ADAPT-CODEX`, `ART-SCR-P1-WT`, `ART-SCR-P1-PROC`, `ART-CI-HARNESS` *(+ `ART-SCR-P1-AUTO` `KEEP_DISABLED`; `ART-SKL-PROV-*` `KEEP_OUTSIDE_REPO`)*.
- **`REFACTOR` (`15`):** `ART-INS-AGENTS`, `ART-AGT-COORD`, `ART-AGT-AUDITOR`, `ART-STD-C2`, `ART-STD-GO2`, `ART-KN-PLAYBOOK`, `ART-KN-SX1276`, `ART-ADR-README`, `ART-SKL-GAP`, `ART-SCR-SELECTOR`, `ART-SCR-SCOPE`, `ART-SCR-SNAPSHOT`, `ART-SCR-ADAPT-AGY`, `ART-SCR-RESOLVER`, `ART-SCR-DOCTOR`, `ART-SCR-SETUP`, `ART-SCR-P1-PILOT`, `ART-CI-BACKEND`, `ART-CI-CLIENTS`, `ART-CI-INTEG`.
- **`CONSOLIDATE` / `DEPRECATE` (`6`):** `ART-AGT-WORKER`, `ART-DOC-CODING-STD`, `ART-SOP-FASTLANE`, `ART-SOP-OLD`, `ART-SCR-RUN`, `ART-SCR-P1-CLI`, `ART-SCR-MCP`.
- **`EXTEND` (`1`):** `ART-SCR-P1-STATE` (preserve SQLite WAL CAS, extend in P04/P08).
- **`ADD` (`6+`):** Root `ARCHITECTURE.md` (`ART-DOC-ARCH`, P02/P07), `PROGRESS.md` & `feature_list.json` (P04), declarative `skill_registry` + Host `skill_router` (`H-A12`, P02/P03), mechanical boundary checks (P05), 6-dim `0-2` rubric (P05/P08), `QUALITY_SCORE.md` / debt tracker (P07), meta-improvement ratchet (P08).

### 8.2 Open Decisions Register (`OD-01..OD-10` — `OPEN`, Not Self-Approved)

| OD | Topic | Due | Current As-Is Evidence & Alternatives Observed | Status (P01) | Required Owner Decision |
|---|---|---|---|---|---|
| `OD-01` | Native Fast Lane vs P1/MCP execution ownership | `P01/P03` | Native Fast Lane is active default; `run.py`, `p1/cli.py`, and read-only `mcp_server.py` (SDK uninstalled) are disconnected. | `OPEN` | Select default single control plane reusing Coordinator + Host scripts (`P03`). |
| `OD-02` | Feature/progress source, storage & single writer | `P04` | Issues are prose-only; `p1/state.py` tracks Issue prep only; no `feature_list.json` or `PROGRESS.md`. | `OPEN` | Approve Issue + versioned `feature_list.json`/`PROGRESS.md` + SQLite writer split (`P04`). |
| `OD-03` | Unified bootstrap/check CLI & profile matrix | `P03/P05` | `harness_doctor.py` misses Go `1.27.1!=1.27.3`, Web `node_modules`, offline ESP-IDF `espressif/mqtt`. | `OPEN` | Approve thin wrapper / unified `init` & `check` targets (`P03/P05`). |
| `OD-04` | Runtime sandbox across Codex / AGY providers | `P03` | `provider-decision.md` shows Native Full Access lacks OS/network isolation (`H2-TOL-02` P0). | `OPEN` | Approve fail-closed sandbox or bounded container/exception policy (`P03`). |
| `OD-05` | Advanced Pack file names vs existing indexes | `P02/P07` | `docs/adr/`, `docs/requirements/`, `contracts/` exist; `ARCHITECTURE.md`, `QUALITY_SCORE.md`, `SECURITY.md`, `RELIABILITY.md` absent. | `OPEN` | Approve minimal index mapping without duplicating ADRs (`P02/P07`). |
| `OD-06` | Benchmark tasks, repetitions, rubric & thresholds | **`P01` (pre-P02)** | Proposed in WP-F (§7): 7 cohort + 2 holdout tasks, `N=3`, recall=`1.00`, unauthorized rejection=`1.00`, routing `>=0.90`. | `OPEN` | **Resolve with Owner before P02 edits.** |
| `OD-07` | HIL/RF equipment & external service bench access | `P05/P06` | Hardware/RF/PA path & live Mosquitto/PG E2E remain `NOT_VERIFIED`. | `OPEN` | Define dedicated bench workflow; keep `NOT_VERIFIED` until measured (`P05/P06`). |
| `OD-08` | Retry budgets, checkpoint format, crash recovery & graph need | `P04/P08/P09` | `run.py` max_repairs=1; `pilot.py` max_repairs=2; no wall/token budget or interactive checkpoint. | `OPEN` | Freeze finite per-task budgets & checkpoint schema (`P04/P08`). |
| `OD-09` | Orchestrator control-plane, 6-dim rubric thresholds & concurrency | `P01/P05/P08/P09` | No 6-dim `0-2` rubric in `audit.schema.json`; concurrency cap & calibration absent. | `OPEN` | Approve Coordinator+Host role mapping, `12/12` + `0` P0/P1 gate, bounded sequential default (`P05/P08`). |
| `OD-10` | Meta-improvement ratchet protocol, holdout & promotion | `P01/P08/P10` | No experiment ratchet or holdout suite exists. | `OPEN` | Approve 1-change/experiment isolated worktree ratchet with frozen oracle (`P08/P10`). |

### 8.3 Prioritized Pre-P02 & P02 Sequence + Remaining Blockers

1. **Pre-P02 Separate Baseline Issues (NOT in P01):** (1) `gofmt -w backend-go/internal/presence/rf_tracker.go` (Go CI unblock); (2) Remediate `clients/web-dashboard/tests/integration.test.ts:31` & `verify_no_secrets.py` false positives without weakening secret scanning; (3) Owner resolves **OD-06** and **TDMA conflict disposition (`CNF-01..03`)**.
2. **Proposed P02 Slices:** `P02-A` (ADR-0004 reconciliation in `snapshot.py`, `auditor.md`, `adr/README.md`, `sx1276/README.md`, playbook, `standards_policy.py`, broken links); `P02-B` (`ARCHITECTURE.md` + SOP consolidation); `P02-C` (trim `AGENTS.md` to 80–120 lines with 100% G0/rule recall parity); `P02-D` (`H-A12` declarative skill manifest/router design).
3. **Remaining Open Blockers:** `P0`: `H2-TOL-02` (no OS runtime sandbox in Native Fast Lane), `H2-ENV-04` (local `SECRET-SCAN` false positive + Go `gofmt` fail; GitHub Actions `OWNER_WAIVED` only); `P1`: `H2-INS-03`, `H2-ENV-02` (offline IDF/Web clean worktree builds, host Go `1.27.1!=1.27.3`), `H2-TOL-03` (`scope.py` on #422), `H2-STA-01..05`, `H2-FBK-01..05`, `H2-GOV-01/03`, `H2-ORC-01..05`.

---

## 9. Finalization — Remediation & Audit Delta Log

- **Prior Audited Candidate (`66e0ee959f2f3b9a22ddd378cfda7c1fcecc7713`, PR #423 initial):** Focused Independent Audit identified five remediation items (`F01` C rule count `106→104`; `F02` RTM traceability & unambiguous `evidence_hash`; `F03` `EV-025`/`EV-003`/`EV-001` receipt integrity; `F04` complete artifact dispositions & `OD-01..OD-10` register; `F05` complete `HARNESS_SPEC.md §7.3` benchmark metric specs).
- **Remediation Candidate (Delta `F01–F05`):** Updated **only** `HARNESS_BASELINE_REPORT.md`, `HARNESS_RTM.json`, and `EVIDENCE_MANIFEST.json`; zero modifications to Harness Core, product code, policies, standards, Skills, tests, contracts, or raw `/tmp/p01-evidence-422/` logs. Recorded Owner decision `GitHub Actions = OWNER_WAIVED` (quota) while keeping `SECRET-SCAN`, G0, and local Quality Gates active.
- **Independent Delta Audit Status:** Requires fresh Independent Auditor verification limited to delta `F01–F05` (no re-execution of full P01); recorded accurately as `DELTA_AUDIT_NOT_VERIFIED` if `Fresh-Independent-Auditor` subagent capability remains unavailable in this session.
- **Rollback:** Revert remediation commit or close Draft PR #423 without touching `main`.
