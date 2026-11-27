# Knowledge Domain 01 — Foundations, System of Record, and Instruction Architecture

> **Status:** Informative local coursebook knowledge (non-normative). Approved policies (`AGENTS.md`), [HARNESS_SPEC.md](../../../harness/HARNESS_SPEC.md), [HARNESS_MASTER_PLAN.md](../../../harness/HARNESS_MASTER_PLAN.md), ADRs, and versioned `contracts/` remain authoritative.
> **Upstream provenance:** Extracted from [`walkinglabs/learn-harness-engineering`](https://github.com/walkinglabs/learn-harness-engineering) at pinned commit `fe2c4ebd2010aa877b504e141437729296c934e8` (`docs/en/`), MIT License, Copyright (c) 2025 WalkingLab (see [../README.md](../README.md)).
> **Sections covered:** `INTRO` (`/en/`), `L01`, `L02`, `L03`, `L04`, `START/Method Map`, `START/Prompt Calibration`.
> **SPEC / Phase routing:** `H2-INS-01..07`, `H2-FBK-08`, `H2-GOV-02..03`; Phases `P00`, `P01`, `P02`, `P10`.

---

## 1. Course Overview and Closed-Loop Harness Mechanism (`INTRO`)

- **Upstream source:** `docs/en/index.md` (`Welcome to Learn Harness Engineering`)
- **License / origin:** MIT (WalkingLab); cites OpenAI (*Harness engineering: leveraging Codex in an agent-first world*), Anthropic (*Effective harnesses for long-running agents*, *Harness design for long-running application development*), and *Awesome Harness Engineering*.

### Source-Backed Concepts

A harness does not change model weights or "make the model smarter"; it establishes a closed-loop working system around the model:

1. **Clear Objective (`AGENTS.md`)** -> **Initialization (`init.sh`)** -> **Run Tasks (AI Agent)**
2. On failure: **Runtime Feedback (CLI / Logs)** -> auto-fix loop back to **AI Agent**
3. On completion claim: **Verify & QA (Test suite)** -> if failed, back to **Runtime Feedback**; if passed, **Cleanup & Handoff (`claude-progress.md`)**

Five core competencies taught across the course:
1. Constrain agent behavior with explicit rules and boundaries.
2. Maintain context across long-running, multi-session tasks.
3. Stop agents from declaring victory too early.
4. Verify work using full-pipeline tests and independent evaluation.
5. Make runtime observable and debuggable.

- **Render-only / excluded:** Interactive VitePress HTML cards and Mermaid styling classes from `/en/`; non-English routes.

---

## 2. Why Capable Agents Still Fail (`L01`)

- **Upstream source:** `docs/en/lectures/lecture-01-why-capable-agents-still-fail/index.md` + `code/underspecified-task.md`, `code/failure-signals-checklist.md` (historical PDF pp. `7–12`)
- **License / origin:** MIT (WalkingLab); summarizes Anthropic Opus 4.5 retro-game comparison, OpenAI million-line Codex experiment, and Claude Sonnet 4.5 SWE-bench context (paraphrased external references).

### Key Definitions & Mechanisms

| Term | Definition | Operational Significance |
|---|---|---|
| **Capability Gap** | Gulf between benchmark scores (clear specs, ready tests) and real-world repo performance (vague specs, implicit conventions, missing tests). | Benchmark accuracy does not guarantee delivery in an unharnessed repo. |
| **Harness** | Everything outside model weights: instructions, tools, environment, state management, verification feedback. | Determines how much of the model's latent capability is realized. |
| **Harness-Induced Failure** | Model is capable, but structural defects in the execution environment cause failure. | Fix the harness layer before swapping to a more expensive model. |
| **Verification Gap** | Gap between an agent's self-reported completion confidence and actual correctness. | Most common failure mode ("I'm done" when tests/runtime fail). |
| **Diagnostic Loop** | Execute -> observe failure -> attribute to a specific harness layer -> fix that layer -> re-execute. | Converts agent mistakes into permanent harness improvements. |
| **Definition of Done** | Explicit, command-verifiable conditions (tests, lint, type checks, runtime behavior). | Prevents the agent from inventing subjective "looks fine" criteria. |

### Five Failure Modes and Five Failure-Diagnosis Layers

When an agent fails (given the same model succeeds on structured tasks), attribute the failure to one of five defense/diagnosis layers rather than blaming model intelligence:

1. **Task specification unclear:** Vague prompts force guessing; wrong guesses cause costly rework. (Example from `code/underspecified-task.md`: ad hoc directories, compiles but doesn't start, UI shell without working backend/ingest path, stops after cosmetic success.)
2. **Context insufficient / implicit conventions:** Unwritten conventions (framework version, auth rules, error patterns) live in Slack or engineers' heads, invisible to the agent.
3. **Execution environment incomplete:** Missing deps, mismatched toolchains, or broken setup consume context window on environment debugging.
4. **Verification feedback missing:** Without executable test/lint/build commands, the agent stops when code looks plausible; **context anxiety** near window limits also causes rushed completion and skipped checks.
5. **Cross-session state lost:** Without persistent state, each new session re-explores the codebase from scratch; failure rates spike on long (>30 min) tasks.

### Failure Signals Checklist (`L01/code/failure-signals-checklist.md`)

Use to review a weak harness run:
- Did the agent ask, or infer incorrectly, how to start the app?
- Did it create directories or abstractions that do not match the intended product?
- Did it stop after making a visible UI shell without a complete workflow?
- Did it leave notes or artifacts that help a future run continue?
- Could a fresh session understand what happened in under five minutes?

### Course Case Evidence & Attribution Caveats

- **Anthropic 2D retro game editor (Opus 4.5):** Bare run took 20 min (`$9`) and opened with unresponsive entities; 3-agent harness (planner + generator + evaluator) ran 6 hours (`$200`) with working core gameplay (physics/level edges remained unfinished). Same model, different harness.
- **OpenAI Million-Line Experiment (Aug 2025–early 2026):** 3 engineers (growing to 7) using Codex only; ~1M LOC, ~1,500 merged PRs (~3.5 PRs/engineer/day) over 5 months by decomposing work into small verified building blocks and encoding missing capabilities into the repo.
- **FastAPI + PostgreSQL + Redis (~15K LOC) example:** Illustrative scenario showing shift from vague 1-sentence prompt to `AGENTS.md` + explicit `pytest` / `mypy` commands + ADRs.

### Project Adaptation (`X`)

- Product-example stacks (FastAPI, SQLAlchemy 2.0, OAuth 2.0, `pytest`, `mypy`) are **not** applicable to ESP32/SX1276 (`C/FreeRTOS/ESP-IDF v6.1`), Go Backend, or Next.js/Kotlin clients. In this repository, failure attribution maps to `AGENTS.md`, Host `agent_context.py` / `quality_gates.py`, `standards_policy.py`, `firmware/` / `backend-go/` toolchains, and Hardware/HIL boundaries (`V1–V4` in `HARNESS_SPEC.md` §7.1).

---

## 3. Five-Subsystem Harness Model and Ablation (`L02`)

- **Upstream source:** `docs/en/lectures/lecture-02-what-a-harness-actually-is/index.md` + `code/harness-components.md` (historical PDF pp. `13–18`)
- **License / origin:** MIT (WalkingLab). `code/harness-vs-no-harness.ts` and `code/minimal-harness-loop.ts` are TypeScript teaching simulations (inspected as data, not executed).

### The Five Subsystems

A harness is NOT just a prompt file. It comprises five distinct subsystems (`HARNESS_SPEC.md` §3):

1. **Instructions (`AGENTS.md` / `CLAUDE.md`):** Project overview, tech stack & versions, startup/verification commands, non-negotiable hard constraints, and links to topic docs ("give a map, not a manual", ~100 lines).
2. **Tools:** Sufficient tool access (shell, file read/write, git, test runners, linters) constrained by **least privilege** — neither crippled nor unrestricted.
3. **Environment:** Self-describing, reproducible runtime (locked dependencies, pinned runtime versions, containers/devcontainers where appropriate).
4. **State:** Durable progress tracking (`PROGRESS.md`, git checkpoints, feature state) read at session start and updated before session end.
5. **Feedback (highest ROI):** Explicit verification commands (tests, type checks, lint, unified check) and **worker/checker separation** ("enforce invariants, don't micromanage implementation").

### Affordance Analysis & Tool Landscape

- **Gulf of Execution:** Agent wants to follow a rule (e.g., parameterized SQL) but lacks concrete examples/APIs in context.
- **Gulf of Evaluation:** Agent changed code but lacks signals/commands to verify correctness.
- **Tool comparisons (course snapshot):** Claude Code (`CLAUDE.md`, shell, session history, needs explicit test commands), Cursor (`.cursorrules`, terminal, weak cross-session state), Codex (git worktree isolation + local observability + `AGENTS.md`), AutoGPT (cautionary example of unbounded context and missing feedback loops).

### Controlled Variable Exclusion Test (Ablation)

- **Procedure:** Hold model fixed; remove one subsystem at a time (instructions, feedback, state, etc.) and measure performance drop.
- **Decision criterion:** Largest drop indicates highest marginal value for the current task. **Critical caveat:** Near-zero drop does NOT prove a component is useless (it may be unexercised or poorly implemented), and ablation alone cannot prove where the bottleneck is — **always pair ablation with failure logs and root-cause attribution**.
- **Course 4-stage illustration (GPT-4o, ~20K LOC TypeScript/React):** Stage 1 README-only (`1/5 = 20%`) -> Stage 2 `AGENTS.md` (`60%`) -> Stage 3 verification commands (`80%`) -> Stage 4 progress templates (`80–100%`). Illustrative progression, not a cross-repo benchmark guarantee.

---

## 4. Repository as the Single Source of Truth (`L03`)

- **Upstream source:** `docs/en/lectures/lecture-03-why-the-repository-must-become-the-system-of-record/index.md` + `code/system-of-record-checklist.md`, `code/repo-knowledge-layout.txt` (historical PDF pp. `19–25`)
- **License / origin:** MIT (WalkingLab). `code/repo-reader.ts` is TypeScript teaching code (not executed).

### Core Mechanics & Metrics

An agent has only three input channels: (1) system prompt & task description, (2) repository file contents, and (3) tool execution output. Knowledge living only in Slack, Confluence, Jira, or engineers' heads **does not exist** for the agent.

- **Knowledge Visibility Gap:** `(Implicit/external required knowledge items not in repo) / (Total enumerated required items)`. Target: `< 10%` (course exercise rule of thumb).
- **Discovery Cost:** Context budget (time, tool calls, input tokens) spent locating a key piece of knowledge. Deeply buried docs inflate discovery cost.
- **Knowledge Decay Rate:** Proportion of repo docs becoming stale per unit time. Outdated documentation actively misleads agents and is worse than no documentation.

### Fresh Session Test (`H2-GOV-03`, `HARNESS_SPEC.md` §7.2)

Open a brand-new session with **zero verbal context** (repo artifacts only) and test five questions:
1. **What is this system?** -> `AGENTS.md` / `README`
2. **How is it organized?** -> `ARCHITECTURE.md` / module docs
3. **How do I run it?** -> `Makefile` / `init.sh` / package scripts
4. **How do I verify it?** -> Test, lint, check commands
5. **Where are we now?** -> `PROGRESS.md` / feature list / git history

Companion 7-item `system-of-record-checklist.md` adds: *What the app should do for users? How health is checked? What quality standards matter?*

### Four Map-Drawing Principles & Layout

1. **Knowledge lives next to code:** Module-level `ARCHITECTURE.md` / `CONSTRAINTS.md` beats a distant 500-page wiki.
2. **Standardized entry file:** `AGENTS.md` (50–100 lines) answers what the project is, how to run it, and how to verify it.
3. **Minimal but complete:** Remove rules whose deletion causes no decision degradation, while keeping all 5 Fresh Session answers present.
4. **Update with code:** Couple doc updates to code PRs and CI freshness checks.

Example course layout (`code/repo-knowledge-layout.txt`):
```text
AGENTS.md
docs/ (ARCHITECTURE.md, PRODUCT.md, RELIABILITY.md, references/, plans/active/, plans/completed/)
src/
scripts/
```

### ACID Analogy for Agent State

- **Atomicity:** Commit a logical work unit (code + tests) only when complete and verified; discard or isolate failed attempts rather than partial merges.
- **Consistency:** Explicit verification predicates (all tests + lint pass) checked after operations; never commit broken intermediate states.
- **Isolation:** Separate progress files or git branches/worktrees for concurrent agents to prevent write races.
- **Durability:** Track critical knowledge and decisions in git-versioned files, not ephemeral session chat.

---

## 5. Splitting Instructions & Progressive Disclosure (`L04`, `START/Prompt Calibration`, `START/Method Map`)

- **Upstream source:** `docs/en/lectures/lecture-04-why-one-giant-instruction-file-fails/index.md` + `code/AGENTS-short.md`, `code/anti-patterns.md`, `docs/en/resources/reference/prompt-calibration.md`, `docs/en/resources/reference/method-map.md` (historical PDF pp. `26–32`, `183–184`)
- **License / origin:** MIT (WalkingLab). Cites Liu et al. (2023) *Lost in the Middle*, ETH Zurich (Gloaguen et al. 2026), and Lulla et al. (2026).

### Five Failure Modes of Monolithic Instruction Files

The "add a rule after every mistake" vicious cycle turns `AGENTS.md` into a 600-line dumping ground:
1. **Context budget eaten:** 600 lines (~10K–20K tokens) consumes ~8–15% of a 128K context window before reading any source code.
2. **Lost in the Middle (Liu et al., 2023):** LLMs recall tokens at the beginning and end of long prompts far better than rules buried in the middle (e.g., a security invariant at line 300).
3. **Priority conflicts:** Red-line constraints ("never use `eval()`"), style preferences, and one-off historical bugs look identical; the agent cannot distinguish hard invariants from suggestions.
4. **Maintenance decay:** Outdated rules are rarely deleted out of fear ("something might depend on it"), steadily lowering signal quality.
5. **Contradiction accumulation:** Rules added across months contradict each other, causing random compliance.

### Core Solutions & Metadata Contract

- **Instruction Signal-to-Noise Ratio (SNR):** `(Relevant loaded instruction units for task) / (All loaded instruction units)`.
- **Entry File as Router:** Keep `AGENTS.md` short (course target: `50–200` lines, ~100 lines; `≤15` global hard rules). Include: Project Overview, Quick Start commands, Hard Constraints, and Topic Docs with one-line applicability conditions.
- **Reveal on Demand (Progressive Disclosure):** Place topic docs (`50–150` lines each) in `docs/` or module directories; load only when applicability matches. Keep type/interface constraints directly in code comments where the agent already reads them.
- **Top/Bottom Placement:** Any rule that must stay in the root file belongs at the top or bottom, never in the middle.
- **Rule Lifecycle Metadata:** Every instruction must document:
  - **Source** ("why was this rule added?")
  - **Applicability condition** ("when is it needed?")
  - **Expiry / review condition** ("when can it be retired or consolidated?")
- **Instruction Anti-Patterns (`code/anti-patterns.md`):** Putting all repo knowledge in one file; repeating rules across files; keeping obsolete unaudited rules; hyper-specific rare conditionals; embedding long tool manuals in startup context.

### Empirical Research Caveats (`L04`)

- **ETH Zurich (Gloaguen et al., 2026):** Found repository context files did not generally improve task success in evaluated settings and increased inference cost by `>20%`; recommends keeping human-written requirements minimal and testing instructions on actual target tasks.
- **Lulla et al. (2026, Table 1):** Paired study (`gpt-5.2-codex`, 124 PR tasks ≤100 LOC / ≤5 files across 10 repos) reported median runtime dropping from `98.57 s` to `70.34 s` (`-28.64%`) and median output tokens from `2,925` to `2,440` (`-16.58%`) with `AGENTS.md`; measured efficiency only, not full functional correctness.

### Prompt Calibration (`START/Prompt Calibration`)

| Keep in Root `AGENTS.md` | Move Out to Topic / Module Docs |
|---|---|
| Repository purpose & scope | Long historical edge cases |
| Startup path & verification path | Topic-specific implementation details |
| Non-negotiable hard constraints | Local architecture notes near code |
| Required state artifacts & end-of-session rules | Single-subsystem examples |

### Failure-Mode Method Map (`START/Method Map`)

Operating principle: **Add the smallest artifact that directly addresses the observed failure mode** rather than dumping more rules into one global file.

| Failure Mode | Observable Symptom | Primary Fix | Supporting Artifact |
|---|---|---|---|
| Cold-start confusion | New session rediscovers setup and status | Make repo the system of record | `claude-progress.md` |
| Scope sprawl | Agent starts several features, finishes none | Restrict active scope (`WIP=1`) | `feature_list.json` |
| Premature completion | Claims done after edits without runnable proof | Bind completion to evidence | `clean-state-checklist.md` |
| Fragile startup | Re-learns how to boot project every session | Standardize setup & verification | `init.sh` |
| Weak handoff | Next session cannot tell verified vs broken vs next | End with explicit handoff | `session-handoff.md` |
| Subjective review | Review depends on taste or memory | Score output with fixed categories | `evaluator-rubric.md` |

### Project Adaptations (`X` for `H2-INS-01..07`)

- **`H2-INS-02` Tightened Budget:** Project targets `80–120` lines for root `AGENTS.md`, `≤10` invariant groups, tracked line/byte/token inventory, and mandatory exception review so splitting never drops mandatory rules.
- **`H2-INS-03` Decision-Type Authority Routing (`HARNESS_SPEC.md` §3.1):** Authority depends on decision type (Scope -> OPEN Issue; Product/Arch -> ADRs/Owner; Interfaces -> Approved Contracts; Hardware/SDK -> Datasheets/Pinned SDK; Policy -> Mandatory Rule IDs; Actual behavior -> Verified code/evidence; Execution -> Active plan; Supporting knowledge -> Index/SOPs). Conflicts trigger `STOP_AND_REPORT`.
- **`H2-INS-05` Deterministic Rule Injection Preserved:** Host `agent_context.py` + `standards_policy.py` (Owner #137, ADR-0005) enforces full `AGENTS.md` SHA-256 verification and deterministic C/Go standard rule partitioning (`<=128` rules / `48 KB` per partition, up to `4` partitions / `256` aggregate rules) rather than relying on soft model recall alone.
- **`H2-INS-06` Domain Boundaries:** Domain maps cover ESP32/SX1276 firmware, Go Modular Monolith, MQTT/PostgreSQL/API contracts, and Next.js/Kotlin clients—never web-app sample layer lists directly.
