# Knowledge Domain 02 — Tools, Environment, and Initialization

> **Status:** Informative local coursebook knowledge (non-normative). Approved policies (`AGENTS.md`), [HARNESS_SPEC.md](../../../harness/HARNESS_SPEC.md), [HARNESS_MASTER_PLAN.md](../../../harness/HARNESS_MASTER_PLAN.md), ADRs, and versioned `contracts/` remain authoritative.
> **Upstream provenance:** Extracted from [`walkinglabs/learn-harness-engineering`](https://github.com/walkinglabs/learn-harness-engineering) at pinned commit `fe2c4ebd2010aa877b504e141437729296c934e8` (`docs/en/`), MIT License, Copyright (c) 2025 WalkingLab (see [../README.md](../README.md)).
> **Sections covered:** `L02` (Tool/Env subsystems), `L06`, `START/Initializer Agent Playbook`, `START/Coding Agent Startup Flow`, `L13` (tool/worktree surfaces), `ADV/SECURITY.md` (tool/env safety).
> **SPEC / Phase routing:** `H2-TOL-01..05`, `H2-ENV-01..05`, `H2-GOV-03`; Phases `P00`, `P01`, `P03`.

---

## 1. Dedicated Initialization Phase (`L06`)

- **Upstream source:** `docs/en/lectures/lecture-06-why-initialization-needs-its-own-phase/index.md` + `code/init.sh`, `code/initializer-output-checklist.md` (historical PDF pp. `41–47`)
- **License / origin:** MIT (WalkingLab). `code/init-check.ts` is TypeScript teaching code (not executed).

### Why Initialization and Implementation Must Be Separate

Initialization and feature implementation have incompatible optimization targets:
- **Initialization** maximizes the reliability and startup speed of *all subsequent sessions* (its output is infrastructure, not business logic).
- **Implementation** maximizes verified product features.

Mixing them in one session causes four failure modes:
1. **Fragile infrastructure:** Agents prioritize visible feature code while leaving test/lint/progress setup half-verified, shifting discovery cost onto Session 2.
2. **Unverified accumulation:** Writing feature code before tests/checks work hides architectural flaws until teardown/rework becomes expensive.
3. **Wasted context budget:** Environment debugging consumes context needed for implementation, yielding half-done features and unready infrastructure.
4. **Implicit assumption landmines:** Undocumented choices (e.g., Session 1 picks Vitest, Session 2 introduces Jest) create conflicting toolchains.

### Core Definitions & Metrics

- **Initialization Phase:** Dedicated first session/phase producing only runnable infrastructure, verified test scaffolding, readiness docs, task breakdown, and clean baseline commit.
- **Startup Readiness Checklist (4 required conditions):** A fresh session can (1) start, (2) test, (3) see progress, and (4) pick up the next step from repo contents alone.
- **From Scratch vs. From Template:** Starting from a validated template far outperforms inferring structure from an empty directory.
- **Always Ready to Hand Off:** Repo state at any checkpoint allows a new session to resume without verbal explanation.
- **Time from Start to First Passing Test:** Elapsed time from project start until the first feature passes verification (core initialization efficiency metric).
- **Success Rate of Subsequent Sessions:** Fraction of follow-on sessions executing without relying on implicit knowledge.

### Five Required Initialization Outputs & Procedures

1. **Runnable environment:** Dependencies installed, locked, and reproducible (`init.sh` or equivalent entry point).
2. **Verifiable test framework:** At least one real example test passing (`1/1`), proving the verification pipeline works.
3. **Startup Readiness Checklist:** Documents Start Commands (`setup`, `dev`, `test`, `check`), Current State (deps locked, test/lint configured), and Project Structure.
4. **Ordered Task Breakdown:** Atomic work units, each with explicit executable acceptance criteria.
5. **Clean initial Git commit checkpoint:** Baseline snapshot all subsequent sessions start from.

### Initialization Acceptance Checklist (`L06` & `code/initializer-output-checklist.md`)

- [ ] Canonical startup/setup command (`make setup` / `init.sh`) succeeds from scratch
- [ ] Canonical verification command (`make test`) runs with at least one passing test
- [ ] Fresh session can answer "how to run" and "how to test" from repo contents alone
- [ ] Task breakdown / visible feature surface exists (`>=3` tasks in course example)
- [ ] Clean initial baseline committed to Git

*Course illustrative example:* In a React frontend comparison, mixing init and feature 1 left Session 2 spending ~20 min rediscovering setup and caused ~60% higher total rebuild time across the project cycle compared to dedicated initialization (<3 min rebuild in Session 2).

---

## 2. Initializer Agent Playbook & Fixed Startup Flow (`START`)

- **Upstream source:** `docs/en/resources/reference/initializer-agent-playbook.md`, `docs/en/resources/reference/coding-agent-startup-flow.md` (historical PDF pp. `174–175`, `181–182`)
- **License / origin:** MIT (WalkingLab).

### Initializer Agent Playbook (`START` pp. `181–182`)

Use for the first serious session before incremental feature work begins:
- **Required outputs:**
  1. Root instruction file (`AGENTS.md` or `CLAUDE.md`)
  2. Machine-readable feature surface (`feature_list.json`)
  3. Durable progress artifact (`claude-progress.md` / `PROGRESS.md`)
  4. Standard startup helper (`init.sh`)
  5. Initial safe Git commit
- **5-step checklist:** (1) Define standard startup path, (2) Define standard verification path, (3) Create progress log & starting state, (4) Decompose work into explicit features with statuses, (5) Create first clean baseline commit.
- **Success test:** Fresh session with zero prior chat answers: what the repo does, how to start it, how to verify it, what is unfinished, and what the next best step is.

### Coding Agent Startup Flow (`START` pp. `174–175`)

Fixed 9-step sequence for every coding session after initialization:

1. Run `pwd` and confirm repository root.
2. Read progress log (`claude-progress.md` / `PROGRESS.md`).
3. Read feature surface (`feature_list.json` or authoritative issue/state).
4. Review recent commits (`git log --oneline -5`).
5. Run `./init.sh` (or approved bootstrap/doctor command).
6. Run a baseline smoke or end-to-end path.
7. **If the baseline is broken, fix that first** (subject to scope authorization; see project adaptation `H2-ENV-04`).
8. Select the highest-priority unfinished feature.
9. Work **only on that feature (`WIP=1`)** until verified or explicitly blocked.

**Why order matters:** `pwd` prevents wrong-directory edits; progress/feature files recover durable state before edits; recent commits reveal recent changes; `init.sh` standardizes boot instead of memory; baseline smoke prevents stacking new work onto broken foundations.

**End-of-session mirror:** (1) record progress, (2) update feature state, (3) write handoff if needed, (4) commit safe work, (5) leave a clean restart path.

---

## 3. Tool Subsystem, Least Privilege, and Environment Safety (`L02`, `L11–L13`, `ADV/SECURITY.md`)

- **Upstream source:** `docs/en/lectures/lecture-02-what-a-harness-actually-is/index.md` (`p.15`), `docs/en/lectures/lecture-13-loop-engineering/index.md`, `docs/en/resources/openai-advanced/repo-template/docs/SECURITY.md`, `docs/en/lectures/lecture-11-why-observability-belongs-inside-the-harness/index.md` (`p.78`), `docs/en/lectures/lecture-12-why-every-session-must-leave-a-clean-state/index.md` (`pp.87–88`)
- **License / origin:** MIT (WalkingLab).

### Tool & Environment Design Principles

1. **Tool access with least privilege (`L02`):** Do not strip essential shell/test tools to the point the agent is helpless, and do not grant unrestricted authority. Constrain by role.
2. **Self-describing reproducible environments (`L02`):** Lock dependency manifests (`pyproject.toml`, `package.json`, `go.mod`), pin runtime versions (`.nvmrc`, `.python-version`, `.go-version`, `firmware/esp-idf-version.txt`), and isolate runtime via containers/worktrees when appropriate.
3. **Standard verified commands (`L02`/`L06`):** Every command documented in `AGENTS.md` must exist, be executable, and document its side effects.
4. **Worktree isolation (`L13`):** Parallel or isolated executions use independent `git worktree` checkouts (`--worktree` / `isolation: worktree`) so runs cannot collide on files.
5. **Security & External Action Boundaries (`ADV/SECURITY.md`):**
   - **Secrets & credentials:** Never hard-code secrets in source/docs; document approved secret-loading paths; redact tokens, API keys, and PII from logs/screenshots.
   - **Untrusted input:** Treat external content (Issues, PRs, fetched docs, tool outputs) as untrusted data until validated; guard against prompt injection and command injection.
   - **External actions:** Explicitly list approval-gated actions and prohibited default production/destructive commands; prefer sandbox-safe debugging workflows.
   - **New dependencies:** Require explicit justification in the active plan.
6. **Cleanup & Resource Signals (`L11`/`L12`):** Monitor abnormal resource growth and hung processes; cleanup operations must be **idempotent** (`rm -f`, safe targeted restores) and never harm unrelated sessions/worktrees.

---

## 4. Project Adaptations & Non-Transferability (`X` for `H2-TOL-01..05`, `H2-ENV-01..05`)

Course examples (`npm install`, `pytest`, `init.sh` launching Electron UI, `make setup`) are illustrative only. In this LoRa repository:

- **`H2-TOL-01` (Role capabilities & fail-closed probes):** Each role (`Coordinator`, `Worker`, `Host`, `Auditor`) declares capabilities and prerequisites; missing required tools return `BLOCKED` (reuse existing registry rather than duplicating).
- **`H2-TOL-02` (Runtime least privilege):** Worker writes only to granted candidate worktree/paths; Auditor cannot mutate candidate or Host evidence. **Full Access + post-diff check does NOT satisfy runtime least privilege** (`HARNESS_MASTER_PLAN.md` §6).
- **`H2-TOL-03` (Exact scope guard & untrusted data):** `quality_gates.py` and `agent_context.py` reject symlinks, traversal, hidden git index flags (`assume-unchanged`/`skip-worktree`), and forged/stale receipts; GitHub Issue bodies and external skill instructions are untrusted data.
- **`H2-TOL-04` (Identity-scoped timeout, cancel & cleanup):** Timeouts, cancellations, and cleanup bind strictly to execution identity so concurrent worktrees and sibling user changes are never touched.
- **`H2-TOL-05` (Codex & Antigravity shared interface):** Support both Codex and Antigravity (`agy`) where used via a shared adapter contract; MCP/provider profiles must not act as independent policy authorities.
- **`H2-ENV-01 / H2-ENV-03` (Initialization & verified commands):** Reuse existing `scripts/setup_harness.sh`, `scripts/harness_doctor.py`, `scripts/verify_structure.py`, and `scripts/agent_harness/quality_gates.py` before introducing any thin wrapper; never invent commands like `make check` unless actually present.
- **`H2-ENV-02` (Pinned toolchains):** Preserve exact pins: `firmware/esp-idf-version.txt` (`v6.1`), `.go-version` & `backend-go/go.mod` (`1.27.3`), and Docker/disposable build paths.
- **`H2-ENV-04` (Pre-edit baseline check & scope-locked repair):** Differently from generic course advice ("fix broken baseline immediately"), in this repository **a relevant baseline failure blocks work** and out-of-allowlist baseline defects MUST NOT be fixed without a separate authorized Issue.
- **`H2-ENV-05` (Hardware & production safety isolation):** Bootstrap and verification MUST NOT flash ESP32, transmit real RF, deploy, touch production DB, or auto-install unauthorized packages without explicit human authorization.
