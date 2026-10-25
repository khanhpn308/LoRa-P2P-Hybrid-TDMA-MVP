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

**Context budget:** `AGENTS.md` + repository-wide instructions + applicable path-specific instructions → relevant Standard **§0** → exact `rg` Rule IDs/section ranges → direct dependencies/contracts. Never load legacy v1, traceability-only audits, training modules or [agent conformance scenarios](../verification/agent-conformance-scenarios.md) during ordinary implementation. A designated audit/evaluator Issue may authorize those sources.

## 1. Mandatory stage checks

| Stage | Required deterministic checks | Output / stop |
|---|---|---|
| T0 `INTAKE` | Record user objective, task route, deliverable, risks, read/write intent. Identify live GitHub Issue. | Missing Issue for write task → `BLOCKED_ISSUE`; read-only discovery is allowed |
| T1 `ISSUE_SCOPE` | Verify Issue, AC, exact root-relative `Target Directories (allowed paths)`, owner-approved scope, dependencies/contract approval, reviewers. Include tests/docs/migrations explicitly if needed. | Missing/ambiguous/unauthorized paths → `BLOCKED_SCOPE`; report needed path, **do not edit** |
| T2 `REPO_PREFLIGHT` | Validate repo/remote and baseline SHA; inspect current branch and entire worktree (tracked/untracked), HEAD against trusted base; Host creates Issue branch before Worker if approved. | Worker on `main` or dirty worktree → `BLOCKED_WORKTREE`; never clean/reset/stash user changes implicitly |
| T3 `SELECTIVE_CONTEXT` | Read relevant `AGENTS.md`, `.github/copilot-instructions.md`, path-specific instructions, Status/Rule IDs and authoritative Requirements/ADRs/contracts. Check exact ESP-IDF v6.1 or Go 1.27.3 pin **if toolchain affects task**. | Conflict/unavailable authoritative source → `BLOCKED_AUTHORITY` or `NOT_VERIFIED`; do not activate draft rules |
| T4 `IMPACT_DISCOVERY` | If MCP exposes `codegraph_explore`, inspect C/Go AST definitions, callers/callees/imports **first**. Check codebase for reusable symbols, composition root, radio ownership, ISR safety and cross-component impact. | Graph results outside allowed paths are **read-only**; required out-of-scope edit → `BLOCKED_SCOPE` |
| T5 `DECISION_GATE` | Classify interfaces/crypto/RF/legal, schema, D01–D13, backlog dependencies and resource/timing constraints; list test levels and human approvals. | Unresolved mandatory design choice → `BLOCKED_DECISION`; missing evidence required by AC → `BLOCKED_EVIDENCE` |
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
| C driver Issue depends on unapproved RF region/TX power | `BLOCKED_DECISION` for TX boundary; no unauthorized transmission |

**Exit criterion:** an operator can inspect the nine-field pre-edit report and the Host decision and unambiguously determine (a) whether code edits are authorized, (b) which files, (c) which rule/contract authority applies, (d) what remains BLOCKED, and (e) how evidence will be verified.
