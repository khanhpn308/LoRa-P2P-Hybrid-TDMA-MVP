# Knowledge Domain 04 — Verification, Feedback Loops, Observability, and Clean Handoff

> **Status:** Informative local coursebook knowledge (non-normative). Approved policies (`AGENTS.md`), [HARNESS_SPEC.md](../../../harness/HARNESS_SPEC.md), [HARNESS_MASTER_PLAN.md](../../../harness/HARNESS_MASTER_PLAN.md), ADRs, and versioned `contracts/` remain authoritative.
> **Upstream provenance:** Extracted from [`walkinglabs/learn-harness-engineering`](https://github.com/walkinglabs/learn-harness-engineering) at pinned commit `fe2c4ebd2010aa877b504e141437729296c934e8` (`docs/en/`), MIT License, Copyright (c) 2025 WalkingLab (see [../README.md](../README.md)).
> **Sections covered:** `L09`, `L10`, `L11`, `L12`, `EXP/DAW`.
> **SPEC / Phase routing:** `H2-FBK-01..08`, `H2-INS-06/07`, `H2-GOV-01..03`, `H2-ORC-02/04`; Phases `P00`, `P05`, `P06`, `P07`, `P10`.

---

## 1. Preventing Premature Completion Declarations (`L09`)

- **Upstream source:** `docs/en/lectures/lecture-09-why-agents-declare-victory-too-early/index.md` + `code/clean-state-checklist.md` (historical PDF pp. `61–67`)
- **License / origin:** MIT (WalkingLab); cites Guo et al. (2017) *On Calibration of Modern Neural Networks* and Anthropic *Harness design for long-running application development* (2026). `code/victory-detector.ts` is teaching code (not executed).

### Core Mechanisms & Definitions

- **Premature Completion Declaration:** Agent claims "done" while unmet correctness requirements remain, relying on local code-plausibility instead of global runtime verification.
- **Confidence Calibration Bias:** Modern neural networks are systematically overconfident (Guo et al., 2017); on complex multi-file tasks, agent self-confidence significantly exceeds actual correctness.
- **Termination Criteria:** Explicit, executable pass/fail predicates enforced externally by the harness—replacing subjective "looks fine."
- **Verification-Validation Dual Gate:**
  - *Verification:* Does code match specified unit/contract behavior?
  - *Validation:* Does full system-level runtime behavior satisfy end-to-end requirements? Both must pass.
- **Completion Priority Constraint:** First verify functional correctness, then performance, then style. **Do NOT refactor until core functionality passes verification** (premature refactoring breaks previously working paths and shifts verification boundaries).

### Three-Layer Termination Validation

Sequential, non-skipping gate hierarchy:
1. **Layer 1 — Syntax & Static Analysis:** Lint, formatting, type checking (`mypy` / `tsc`). Lowest cost; must pass before Layer 2.
2. **Layer 2 — Runtime Behavior Verification:** Unit tests, application startup checks, critical path execution.
3. **Layer 3 — System-Level Confirmation:** Integration and full end-to-end flow validation against live boundaries.

*Illustrative password-reset failure case:* Unit tests passed with mocks, but E2E failed on (1) untested reset-link flow, (2) half-applied DB migration, and (3) missing email service env config.

### Systematic Bias in Self-Evaluation & Worker/Checker Split

Anthropic (2026) observed that **an agent grading its own work systematically gives overly positive assessments** even when quality is visibly substandard.
- **Solution:** Separate **Worker (generator)** from **Checker (evaluator)**, tuning the Checker specifically to be "nitpicky."
- **Opus 4.5 retro-game comparison:** Bare single agent (`20 min`, `$9`, unresponsive entities) vs 3-agent architecture (`planner + generator + Playwright evaluator`, `6 hours`, `$200`, core gameplay working though physics/level edges remained).

### Clean State Checklist (`L09/code/clean-state-checklist.md`)

- App starts without manual repair
- Current progress is recorded
- No half-finished import or indexing step remains undocumented
- Next agent can run standard startup and verification path immediately

---

## 2. End-to-End Verification and Mechanical Boundary Enforcement (`L10`)

- **Upstream source:** `docs/en/lectures/lecture-10-why-end-to-end-testing-changes-results/index.md` + `code/architecture-rules.md`, `code/review-feedback-to-rule.md` (historical PDF pp. `68–74`)
- **License / origin:** MIT (WalkingLab). `code/e2e-runner.ts` is teaching code (not executed).

### Four Systematic Blind Spots of Unit Tests

Mocking dependencies makes unit tests fast but blind to cross-component defects:
1. **Interface Mismatch:** Caller emits relative path; callee expects absolute path (both pass mocked unit tests).
2. **State Propagation Errors:** Migration changes DB schema while ORM cache retains stale layout.
3. **Resource Lifecycle Issues:** File handle, socket, or DB connection leaks across module boundaries.
4. **Environment Dependency:** Config, latency, or OS permission differences in real vs mocked runs.

*Course Electron file-export table:* 5 defects (interface mismatch, IPC progress propagation, large-file handle leak, packaged permissions, service exception propagation) — **0/5 caught by unit tests, 5/5 caught by E2E**.

**Behavioral effect of E2E:** Knowing E2E tests will run causes agents while coding to reason about upstream/downstream interfaces, respect layer boundaries, and implement real error paths.

### Testing Adequacy Gradient & Architectural Boundary Rules

- **Testing Adequacy Gradient:** `Defects detectable by unit tests <= integration tests <= E2E tests`.
- **Day-1 Architectural Constraints (OpenAI):** Agents copy existing repo patterns—even messy ones—so boundaries must be defined on Day 1.
  - *Course example (Layered Domain Architecture):* `Types -> Config -> Repo -> Service -> Runtime -> UI`, with cross-cutting concerns entering via explicit `Providers` interfaces.
  - *Core rule:* **Enforce invariants; don't micromanage implementation** (e.g., require boundary parsing without prescribing a specific library).

### Review Feedback Promotion & Agent-Oriented Error Messages

- **Review Feedback Promotion (`L10` & `code/review-feedback-to-rule.md`):** Whenever human code review catches a recurring defect category (e.g., renderer importing `fs` directly instead of using preload bridge), promote the feedback into an automated lint/import/structural test so the harness strengthens permanently.
- **Agent-Oriented Error Messages (3 required elements):**
  ```text
  ERROR: <what violated and exact file:line>
  WHY:   <architectural/security reason>
  FIX:   <concrete remediation instruction, e.g. move to X and call via Y>
  ```
  Turning failure output into repair instructions creates an autonomous self-correction loop.

---

## 3. Layered Observability, Sprint Contracts, and Evaluator Rubrics (`L11`, `EXP/DAW`)

- **Upstream source:** `docs/en/lectures/lecture-11-why-observability-belongs-inside-the-harness/index.md` + `code/evaluator-rubric.md`, `code/sprint-contract.md` (historical PDF pp. `75–82`)
- **License / origin:** MIT (WalkingLab). `code/runtime-logger.ts` is teaching code (not executed).

### Four Costs of Missing Observability

1. Cannot distinguish "looks correct" in code review from "actually ran correctly."
2. Evaluation becomes non-reproducible mysticism without rubrics/evidence.
3. Retries turn into blind wandering, burning tokens on unrelated code.
4. Session handoffs hit an information cliff requiring full re-diagnosis.

### Two-Layer Observability Architecture

| Layer | Answers | Artifacts / Signals |
|---|---|---|
| **Runtime Observability** | "What did the system do?" | Structured logs, metrics, traces, process lifecycle events, health checks. |
| **Process Observability** | "Why should this change be accepted?" | Sprint contracts, execution plans, evaluator rubrics, acceptance evidence. |

**Five runtime signal categories to collect by default:**
1. Application lifecycle (`startup`, `ready`, `running`, `shutdown`)
2. Feature path execution (entry points, checkpoints, exits)
3. Cross-component data flow
4. Resource utilization (abnormal memory/queue growth)
5. Full error/exception context (not bare message strings)

**OpenTelemetry convention (course suggestion):** Session = trace, task = span, verification step = sub-span.

### Sprint Contracts & Evaluator Rubrics (`L11` & `code/`)

- **Sprint Contract (`L11` & `code/sprint-contract.md`):** Negotiated *before* coding begins between generator and evaluator (or planner), defining: **Scope** (target components/files), **Verification Standards** (runnable checks), and **Exclusions** (what NOT to touch/handle). Front-loads alignment and eliminates surprise rejections.
- **Evaluator Rubric (`L11`):**
  - *Course lecture example (A–D):* Code correctness, Architecture compliance, Test coverage.
  - *L11 `code/evaluator-rubric.md` (1–5 scale):* Grounding, Citation quality, Functionality, Product coherence.
  - *Minimal Pack `templates/evaluator-rubric.md` (0–2 scale across 6 dimensions):* Adopted by `HARNESS_SPEC.md` §7.3 (see Knowledge 06 & Project Adaptations below).

### Anthropic's Three-Agent DAW Case (`L11`, pp. `80–81`)

Updated March 2026 run on **Opus 4.6** ("build a browser-based DAW using Web Audio API"):
- **Evolution from Opus 4.5 -> Opus 4.6:** Opus 4.5 needed sprint decomposition; Opus 4.6 handled continuous building without sprints, so the sprint layer was simplified away while keeping the independent QA evaluator.
- **Updated Opus 4.6 run breakdown:** Planner `4.7 min` (`$0.46`) -> Build 1 `2h 7m` (`$71.08`) -> QA 1 `8.8 min` (`$3.24`) -> Build 2 `1h 2m` (`$36.89`) -> QA 2 `6.8 min` (`$3.09`) -> Build 3 `10.9 min` (`$5.88`) -> QA 3 `9.6 min` (`$4.06`). **Total: `3h 50m`, `$124.70`.**
- **Calibration lesson:** Early evaluators spotted real flaws then talked themselves into approving anyway. Fix: inspect evaluator logs against human judgment and tighten QA prompts across multiple rounds until scoring reliably catches presentational-only stubs and missing core interactions (e.g., clips not draggable, missing synth/drum UI and EQ/compressor controls).

---

## 4. Clean Session Handoff, Entropy Control, and Harness Simplification (`L12`)

- **Upstream source:** `docs/en/lectures/lecture-12-why-every-session-must-leave-a-clean-state/index.md` + `code/cleanup-loop.md`, `code/benchmark-comparison-template.md` (historical PDF pp. `83–90`)
- **License / origin:** MIT (WalkingLab); cites Lehman's laws of software evolution and OpenAI Codex engineering practices. `code/benchmark-runner.ts` and `code/cleanup-scanner.ts` are teaching code (not executed).

### Entropy Growth & OpenAI's Anti-Slop System

Agents mimic existing repo patterns—including messy ones (Broken Window / coffee-cup analogy). OpenAI initially spent Fridays (`~20%` of weekly capacity) manually cleaning "AI slop," then replaced manual cleanup days with three mechanisms:
1. Encode mechanical **"golden rules"** (prefer shared utilities; validate data at boundaries instead of guessing).
2. Run **periodic background cleanup** (scan for deviations, update quality scores, open targeted refactoring PRs).
3. **Capture human taste once, enforce continuously** (promote review comments into docs, then into automated checks).

### Clean State: Five Mandatory Exit Conditions

"The code compiles" is NOT clean state. Session exit requires all five:
1. **Build passes**
2. **All tests pass** (no regressions)
3. **Progress & feature state updated** in machine-readable artifacts
4. **No stale temporary artifacts** (debug logs, temp files, commented-out dead code, stray TODOs)
5. **Standard startup path remains operational**

- **Session Integrity:** Database-transaction semantics—either fully commit a verified clean state or roll back to the last consistent checkpoint.

### Dual-Mode Idempotent Cleanup & Quality Documents

- **Immediate cleanup (end of every session / "reference counting"):** Remove session temp artifacts, update progress/feature files, confirm build+tests pass.
- **Periodic cleanup (weekly / "tracing", `code/cleanup-loop.md`):** Scan stale docs and structural violations, update quality grades, open targeted cleanup PRs, rerun fixed benchmark slice.
- **Idempotence invariant:** Running cleanup multiple times produces the same safe state without errors (`rm -f`, targeted restores, re-verify tests).
- **Quality Document (`A–D`):** Continuously tracks module/domain grades across verification pass status, agent legibility, test stability, architectural boundary compliance, and code conventions so new sessions fix the weakest modules first.
- *Hypothetical 12-week Electron comparison (`L12`):* Illustrates entropy decay without cleanup (`Week 12: 68% build, 61% tests, 60+ min startup, 103 stale artifacts`) vs weekly cleanup (`97% build, 95% tests, 9 min startup, 11 stale artifacts`).

### Periodic Harness Simplification & Throughput Caveat

- **Monthly simplification loop (`L12`):** Every harness component compensates for a model limitation that may become obsolete (e.g., Opus 4.6 dropping Opus 4.5's sprint layer). Periodically disable one component, run benchmark tasks (`code/benchmark-comparison-template.md`: completion rate, average retries, bugs caught before review, cost), and remove if results do not degrade; restore if they do.
- **High-throughput merge caveat:** OpenAI favored lightweight merge gates when agent output (`3.5+` PRs/engineer/day) exceeded human review bandwidth and `cost(fast follow-up fix) < cost(waiting for human review)`. Course explicitly warns this is **irresponsible in low-throughput or safety-critical contexts**.

---

## 5. Project Adaptations (`X` for `H2-FBK-01..08`, `H2-GOV-01..03`, `H2-ORC-02/04`)

- **`H2-FBK-01 / H2-FBK-02` (Impact-selected checks & Host receipts):** Never skip required tests to claim PASS. All acceptance evidence MUST be collected by trusted Host scripts (`quality_gates.py` / `agent_context.py`) recording command identity, candidate SHA/diff, toolchain version, direct process exit code, and sanitized log SHA-256—blocking Worker self-attestation.
- **`H2-FBK-03 / H2-ORC-02/04` (Independent evaluation & 6-dimension rubric):** Auditor inspects a frozen candidate without mutating candidate or evidence; any affected code change invalidates prior audit verdicts. `HARNESS_SPEC.md` §7.3 adopts the 6-dimension `0–2` rubric (`Correctness`, `Verification`, `Scope discipline`, `Reliability`, `Maintainability`, `Handoff readiness`; `0 = failed/missing`, `1 = partial`, `2 = met with evidence`), outputting `ACCEPT` / `REVISE` / `BLOCK` plus explicit hard gates that **no total score (`0–12`) can override**.
- **`H2-FBK-04` (Mechanical boundary checks):** Applied with domain-specific negative fixtures (e.g., C/Go boundary rules, `quality_gates.py` scope/secret/symlink checks) rather than naive `grep` alone.
- **`H2-FBK-05` (V1–V4 Evidence Separation & High-Throughput Caveat Rejected for Safety):** Unit/simulation/CI PASS (`V1–V2`) MUST NEVER substitute for `V3` integration or `V4` hardware/HIL/RF/timing/security verification (`NOT_VERIFIED` when bench absent). OpenAI's "fast merge without blocking gates" pattern is **prohibited** for RF/ISR/SPI/timer/crypto/contract paths (`H2-GOV-03`, `AGENTS.md`).
- **`H2-FBK-06` (Redacted observability):** Reuse existing monorepo signals (UART, radio event logs, MQTT, PostgreSQL/Go/API, Web UI, Host receipts) with strict secret redaction; full OpenTelemetry stack is optional.
- **`H2-FBK-07` (Quality Score `NOT_VERIFIED`):** Adds `NOT_VERIFIED` alongside `A–D`; prohibits averaging across domains to hide blocking failures.
- **`H2-FBK-08` (Simplification protection):** Benchmark/ablation simplification MUST NOT disable or weaken mandatory safety, scope, or security guardrails.
