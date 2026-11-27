# Knowledge Domain 03 — State Management, Scope Control, and Session Continuity

> **Status:** Informative local coursebook knowledge (non-normative). Approved policies (`AGENTS.md`), [HARNESS_SPEC.md](../../../harness/HARNESS_SPEC.md), [HARNESS_MASTER_PLAN.md](../../../harness/HARNESS_MASTER_PLAN.md), ADRs, and versioned `contracts/` remain authoritative.
> **Upstream provenance:** Extracted from [`walkinglabs/learn-harness-engineering`](https://github.com/walkinglabs/learn-harness-engineering) at pinned commit `fe2c4ebd2010aa877b504e141437729296c934e8` (`docs/en/`), MIT License, Copyright (c) 2025 WalkingLab (see [../README.md](../README.md)).
> **Sections covered:** `L05`, `L07`, `L08`.
> **SPEC / Phase routing:** `H2-STA-01..06`, `H2-GOV-01..03`, `H2-ORC-05`; Phases `P00`, `P04`, `P07`, `P10`.

---

## 1. Cross-Session Context Continuity (`L05`)

- **Upstream source:** `docs/en/lectures/lecture-05-why-long-running-tasks-lose-continuity/index.md` + `code/continuity-checklist.md`, `code/session-handoff.md` (historical PDF pp. `33–40`)
- **License / origin:** MIT (WalkingLab). `code/session-simulator.ts` is TypeScript teaching code (not executed).

### Why Continuity Breaks

1. **Finite context windows:** Even 128K–1M token windows saturate on multi-file exploration, tool output, and reasoning history.
2. **Compaction loses "why":** Summarizing conversation preserves *what* code changed, but strips *why* option B beat option A or why an optimization was skipped—causing subsequent sessions to revert deliberate choices.
3. **Duplicate work & silent drift:** Without progress and verification records, new sessions re-implement completed work or drift incrementally across boundaries.
4. **Context anxiety:** Observed by Anthropic on Sonnet 4.5—when agents sense context approaching limits, they rush to declare completion, skip verification steps, and pick shortcuts.

### Compaction vs. Context Reset (`L05`, Anthropic 2026)

| Strategy | Mechanism | Strength | Weakness / Model Sensitivity |
|---|---|---|---|
| **Compaction** | Summarizes earlier turns inside the same session. | Keeps continuity of "what" happened. | Often loses "why"; **does not cure context anxiety** on models like Sonnet 4.5. |
| **Context Reset** | Clears context, starts a fresh session rebuilding from disk artifacts. | Eliminates context anxiety; clean mental state. | Depends strictly on completeness of repo handoff artifacts. |

- **Empirical model nuance:** Anthropic observed Sonnet 4.5 required explicit context resets to overcome context anxiety, whereas Opus 4.5 showed much less anxiety and worked well with compaction. **Harness design must match the target model rather than using one rigid rule.**
- **Mixed strategy decision criterion:** Short tasks (<30 min) can finish in one session; long tasks spanning sessions require durable handoff artifacts. Prepare handoff once context usage exceeds **60% of the window**.

### Key Continuity Metrics & Four Artifacts

- **Rebuild Cost:** Time, tool calls, and tokens a fresh session spends reaching an executable state.
- **Drift:** Divergence between the agent's mental model and actual repository state.
- **Four Continuity Tools:**
  1. **`PROGRESS.md` / `claude-progress.md`:** Current state (commit hash, test status, lint), Completed, In Progress, Known Issues, Next Steps.
  2. **`DECISIONS.md`:** Concise "what decision, why, rejected alternatives, constraints" log.
  3. **Git commits as checkpoints:** Atomic commits per verified unit with explanatory messages.
  4. **Clock-in / Clock-out routine in `AGENTS.md`:** Read progress + decisions + `make check` at start; update progress + verify consistent state + commit at end.

### Course Cases & Continuity Checklist (`L05`)

- **Anthropic website-clone case:** Initializer expanded spec into `>200` features (all initially failing) + `init.sh` + progress file + initial commit; coding sessions resumed incrementally from repo history. *(Course notes the companion code is a teaching simulation and previously cited completion percentages were removed as unverified.)*
- **LangChain Terminal Bench 2.0 (`gpt-5.2-codex`, 89 tasks):** Score improved from `52.8%` to `66.5%` (`+13.7 pp`) via combined verification guidance, middleware, and context management (not progress files in isolation).
- **`code/continuity-checklist.md`:**
  - Can a fresh agent identify recent work in under five minutes?
  - Is the current stable startup path documented?
  - Is unfinished work clearly identified?
  - Is the next best task visible without reading old chat logs?

---

## 2. Task Boundaries and `WIP=1` Scope Control (`L07`)

- **Upstream source:** `docs/en/lectures/lecture-07-why-agents-overreach-and-under-finish/index.md` + `code/next-task-template.md`, `code/scope-surface-example.md` (historical PDF pp. `48–54`)
- **License / origin:** MIT (WalkingLab). `code/scope-tracker.ts` is TypeScript teaching code (not executed).

### Finite Attention Math & Failure Modes

If an agent has context/reasoning capacity `C` and activates `k` tasks simultaneously, each task receives roughly `C / k`. Once `C / k` falls below the threshold required for one task, **none finish cleanly**.

- **Overreach:** Activating multiple tasks or unsolicited refactors in one session (e.g., 5 features started, 0 passing end-to-end).
- **Under-finish:** Low ratio of end-to-end verified features to activated features.
- **Little's Law (`L = lambda * W`):** Higher WIP (`L`) increases lead time (`W`) per verified slice and compounds cross-file coupling.
- **Completion Pressure:** Harness constraints (`WIP=1` + executable completion evidence) forcing completion of the active unit before admitting the next.

### Four Scope-Control Rules & Scope Surface

1. **Enforce `WIP=1`:** Only **one** task may be in `active` (`in_progress`) state at a time per execution; forbid "while I'm here" refactoring of unrelated features.
2. **Require executable Completion Evidence:** "Code looks fine" is invalid; require a concrete runnable check (e.g., command exit / HTTP response / test pass).
3. **Externalize the Scope Surface:** Maintain a machine-readable DAG of work units and dependencies in the repo using four states: `not_started`, `active`, `blocked`, `passing`.
4. **Monitor Verified Completion Rate (`VCR`):** `VCR = verified tasks / activated tasks`. **Block new task activation whenever `VCR < 1.0`.**

*Course illustration (8-feature REST API):* Unconstrained mode activated 5 features at once (`~1,200` lines over 3 sessions, `37.5%` completion `3/8`); `WIP=1` mode finished 1 feature per slice (`~800` lines over 4 sessions, `87.5%` completion `7/8`, 8th blocked externally).

**`L07/code/next-task-template.md` fields:**
- Current highest-priority feature
- Why this feature is next
- What counts as passing
- What must not be changed during this step

**`L07/code/scope-surface-example.md` decomposition criterion:** Replace broad goals ("Implement indexing") with single-behavior slices ("Parse imported documents", "Split documents into chunks", "Persist chunk metadata", "Expose indexing status in UI", "Add reindex action").

---

## 3. Feature Lists as Executable Harness Primitives (`L08`)

- **Upstream source:** `docs/en/lectures/lecture-08-why-feature-lists-are-harness-primitives/index.md` + `code/feature_list.json`, `code/pass-gate-policy.md` (historical PDF pp. `55–60`)
- **License / origin:** MIT (WalkingLab). `code/feature-list-validator.ts` is TypeScript teaching code (not executed).

### Primitives vs. Human Memos

Human memos ("cart mostly done, still need payments") cannot be parsed by schedulers or verified across sessions. Treating `feature_list.json` as an **executable primitive** (analogous to a database constraint that cannot be bypassed by application code) anchors four harness subsystems:
1. **Scheduler:** Selects the next ready `not_started` item.
2. **Verifier:** Executes the item's verification steps and gates state transitions.
3. **Handoff reporter:** Summarizes verified vs active vs blocked items automatically.
4. **Progress tracker / Back-pressure:** Counts remaining non-passing items (`0` remaining = complete).

### The Feature Triple & Pass-State Gating

Every feature entry MUST carry the **triple**:
1. **Behavior description:** Observable user/system behavior (not implementation detail).
2. **Verification command / steps:** Exact repeatable check defining "done."
3. **Current state + evidence:** One of `not_started`, `active` (or template `in_progress`), `blocked`, `passing`.

**Pass-State Gating (`L08` & `code/pass-gate-policy.md`):**
- The Worker/coding agent **MUST NOT** directly flip a feature to `passing` (`passes: true`).
- Only the **harness / verifier** promotes `active -> passing` when:
  - The expected workflow has been exercised end-to-end
  - Evidence of success is recorded (commit hash, test log)
  - No blocking error exists in the tested path
  - The system is not left in a broken or ambiguous state
- **Single source of truth:** All "what remains to do" state derives from one authoritative list—never contradicting chat history or scattered `TODO` comments.
- **Granularity calibration:** Scope each feature item to **"completable in one session"** (neither an entire epic nor a single struct field).

---

## 4. Project Adaptations (`X` for `H2-STA-01..06`, `H2-ORC-05`)

- **`H2-STA-01` (Machine-readable feature surface):** Must include stable `id`, behavior, verification, state, evidence, and dependency/scope fields; `in_progress` in templates maps explicitly to `active` in `HARNESS_SPEC.md` §6.2.
- **`H2-STA-02` (`WIP=1` scope):** Enforced **per execution / active plan**—does not forbid separately authorized parallel product Issues in isolated worktrees. Transitions to `blocked` require documented reason and authorization.
- **`H2-STA-03` (Revision-bound `passing` — critical extension):** While `L08` p. `57` treats `passing` as irreversible once reached, this project binds current `passing` validity to **exact candidate revision / commit SHA**. Immutable historical PASS logs are preserved for audit, while any affected code change or test modification invalidates *current* validity (`STALE` / `NOT_VERIFIED`) until re-verified by the trusted Host.
- **`H2-STA-04 / H2-STA-05` (Plan lifecycle & non-destructive recovery):** Use `PROGRESS.md` or Issue-local durable handoff (`HARNESS_SPEC.md` §5.1) alongside Git checkpoints and Host SQLite journal (`scripts/agent_harness/p1/state.py`). Crash/interrupt recovery MUST preserve incomplete work in an isolated state marked `PARTIAL` or `BLOCKED`—**never** auto-merge or run destructive `git reset` / `stash drop` on user work.
- **`H2-STA-06` (Single source of truth per state domain):** Strict single-writer ownership separates GitHub Issues (backlog/scope authority), feature verification evidence (trusted Host verifier), and Host runtime journal (execution state), forbidding uncontrolled bidirectional sync.
