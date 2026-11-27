# Knowledge Domain 05 — Orchestration, Loops, Graphs, and Controlled Improvement

> **Status:** Informative local coursebook knowledge (non-normative). Approved policies (`AGENTS.md`), [HARNESS_SPEC.md](../../../harness/HARNESS_SPEC.md), [HARNESS_MASTER_PLAN.md](../../../harness/HARNESS_MASTER_PLAN.md), ADRs, and versioned `contracts/` remain authoritative.
> **Upstream provenance:** Extracted from [`walkinglabs/learn-harness-engineering`](https://github.com/walkinglabs/learn-harness-engineering) at pinned commit `fe2c4ebd2010aa877b504e141437729296c934e8` (`docs/en/`), MIT License, Copyright (c) 2025 WalkingLab (see [../README.md](../README.md)).
> **Sections covered:** `L13`, `L14`, `REF-ORC` (`docs/en/resources/reference/index.md`, `L13` p. `111`, p. `177`), `EXP/autoresearch`.
> **SPEC / Phase routing:** `H2-ORC-01..08`, `H2-FBK-09..11`, `H2-GOV-01`; Phases `P00`, `P01`, `P08`, `P09`, `P10`.

---

## 1. Loop Engineering (`L13`)

- **Upstream source:** `docs/en/lectures/lecture-13-loop-engineering/index.md` + `code/goal-template.md`, `code/loop-state-template.md`, `code/maker-prompt.md`, `code/checker-prompt.md` (historical PDF pp. `91–112`)
- **License / origin:** MIT (WalkingLab); synthesizes Addy Osmani (*Loop Engineering*, Jun 2026), Karpathy (`autoresearch`, Mar 2026), Boris Cherny (30-day 259 PRs / 497 commits), and Claude Code / Codex scheduling documentation.

### `/goal` vs. Traditional Prompts vs. `/loop`

Loop Engineering shifts the human from **inside the loop** (manually prompting each step) to **outside the loop** (defining goal, verification method, stopping condition, and reviewing outcomes).

| Dimension | Traditional Prompt | `/goal` (Goal-Based Loop) | `/loop` (Time-Based Loop) |
|---|---|---|---|
| **What you supply** | Next micro-step | Desired end state + verification + constraints | Small recurring check action + interval |
| **Execution** | One turn | Iterates until goal met or budget exhausted | Repeats independently on timer (no cumulative progress) |
| **Stop condition** | You interrupt / agent guesses | Independent evaluator confirms done, or max turns/no-progress | Manual stop, expiry (7d in Claude Code), or self-exit |
| **One-sentence test** | Exploratory / small edit | **"Does this thing have an end?" -> Yes** | **"Does this thing have an end?" -> No (monitoring)** |

**Four-stage organic evolution:** (1) Manual turn-by-turn -> (2) Multi-step long prompts -> (3) Agent self-reflection (failed on premature victory) -> (4) **Independent stopping judgment (`/goal`)**.
**Four loop categories:** Turn-based, Goal-based (`/goal`), Time-based (`/loop`, Codex Thread automation), Event-driven (webhooks/CI/PR triggers, Claude Cloud Routines, GitHub Actions / `codex exec` + cron).

### Six Primitives of a Loop (`L13`, Osmani)

External State is the spine supporting the other five:
1. **Automations (Heartbeat):** Scheduled or event-driven triggers (`/loop`, Desktop tasks, Cloud Routines, Codex Thread/Standalone automations, cron/CI).
2. **Worktrees (Isolation at scale):** Independent `git worktree` checkouts (`--worktree` / `isolation: worktree`) prevent multi-agent file collisions; **human review bandwidth remains the concurrency ceiling**.
3. **Skills (Codified intent):** `SKILL.md` folders packaging conventions, build steps, and "don't do X" lessons once instead of re-explaining every run.
4. **Connectors (MCP):** Protocol links to issue trackers, DBs, staging APIs, PR/messaging tools.
5. **Sub-agents (Maker/Checker split):** Explorer -> Implementer -> **Verifier** (fresh session/instructions, optionally different model). *"A model is its own output's best defense attorney; someone in your crew must not believe you."* Includes community "adversarial verify" pattern (N independent skeptics prompted to refute findings).
6. **External State (Memory):** Disk-backed markdown/issue-tracker state surviving across runs.

### Karpathy's `autoresearch` Ratchet Loop (`L13`, `EXP` pp. `104–107`)

A minimal self-improving research loop using three files:
- `prepare.py` (**read-only**): fixed data prep, tokenizer, eval harness.
- `train.py` (~630 lines, **agent-editable**): model/optimizer/training experiment surface.
- `program.md` (**human-editable methodology**): goal (`val_bpb`), constraints (don't touch `prepare.py`, VRAM limit, fixed `5-min` training wall clock), exploration directions, evaluation rules, iron rule (keep iterating).

**Nine-step forward-only ratchet:**
1. Read `program.md` -> 2. Survey `train.py` + `results.tsv` -> 3. Propose hypothesis -> 4. Edit `train.py` -> 5. `git commit` snapshot -> 6. Run fixed-budget training (`5 min`) -> 7. Evaluate (`val_bpb` improved?) -> 8a. **Keep** commit + log to `results.tsv` OR 8b. **Revert** (`git reset HEAD~1`) + log failure -> 9. Next round (`~12` experiments/hr; nanochat 8xH100 round reduced training time `2.02h -> 1.80h`, `~10.9%`).

### Four Silent Costs of Autonomous Loops

1. **Verification Debt:** Fast unattended generation tempts skipping machine-checkable verification ("looks fine"). Fix: enforce objective stopping gates.
2. **Comprehension Rot:** Code changes faster than the team's mental model; **fast loops require fast human reading/review**.
3. **Cognitive Surrender:** Using loops to stop thinking about architecture and tradeoffs rather than amplifying engineering judgment.
4. **Token Blowout:** If round history grows linearly, reprocessing full context across `N` rounds costs `O(N^2)` input tokens. Requires bounded context / compaction / external state handoffs from loop 1.

### Five-Step First Loop & Five-Level Maturity Ladder (`L13`, p. `110`)

- **5-step build:** (1) Pick recurring task (>=2x/week), (2) Write `goal.md` with stop conditions, (3) Split Maker and Checker, (4) Add markdown memory (`loop-state.md`), (5) Set timer (`/loop` or cron).
- **Maturity Ladder:**
  - **Level 1:** Goal Runner (`/goal` single task)
  - **Level 2:** Scheduled Single-Task (timer/cron)
  - **Level 3:** Multi-Agent Loop (Maker/Checker split, isolated worktrees)
  - **Level 4:** Self-Feeding Loop (auto-discovers next work from external state)
  - **Level 5:** Fleet Orchestration (multiple parallel loops sharing a memory/state layer)

### Loop Templates (`L13/code/`)

- **`goal-template.md`:** Goal, Acceptance Criteria (machine-verifiable checkboxes), Scope (`Fair game` vs `Hands off`), Verification Method (ordered commands), Stop Conditions (all AC pass, max turns `20`, no progress for `3` consecutive rounds, external blocker), How to Work.
- **`loop-state-template.md`:** Basic Info (loop name, started, current round `1/N`, status, elapsed), Goal, per-round Round Log (started, Maker action, verification result, issues found, next round plan, human intervention Yes/No), Cumulative Stats table, Blocker List, Final Result.
- **`maker-prompt.md`:** Read `AGENTS.md` -> explain plan -> write code -> run basic checks -> hand off Implementation Summary, Modified Files, Basic Verification, Known Issues & Risks.
- **`checker-prompt.md`:** Adversarial review role ("not here to praise; not finding problems is your failure"); 5-section checklist (Functional Correctness, Code Quality, Testing, Verification Commands, Safety & Impact); required per-issue fields (`Description`, `Location file:line`, `Evidence`, `Severity Critical/Medium/Minor`, `Suggestion`); Overall Verdict (`Pass` / `Fail` / `Minor issues, acceptable`) + Verification Command Results.

---

## 2. Graph Engineering and Orchestration Economics (`L14`)

- **Upstream source:** `docs/en/lectures/lecture-14-graph-engineering/index.md` + `code/index.md` (historical PDF pp. `113–132`)
- **License / origin:** MIT (WalkingLab); synthesizes Rohit (`@rohit4verse`), Eigent.ai (*Graph Engineering for AI Agents*), Anthropic (*Building Effective Agents*), iii.dev (*Loops, Graphs, and the Layer That Matters*), goddaehee fact-check (Jul 2026), and Addy Osmani (*The Orchestration Tax*, May 2026). `code/maker_checker_graph.py` is LangGraph reference code (inspected conceptually, not executed).

### Four-Layer Stack & Four Parts of a Graph

Each layer composes inside the next (with the **Harness** as foundation beneath them):
`Prompt Engineering` (instruction) -> `Context Engineering` (information) -> `Loop Engineering` (runtime iteration) -> `Graph Engineering` (multi-agent/tool/evaluator topology).

**Four Graph Primitives:**
1. **Node:** Deterministic code (tests/commit), model call, tool, or **a full self-looping agent** with private prompt/context/tools/memory.
2. **Edge:** Sequential, parallel fan-out/fan-in, conditional branching, failure retry, or explicit **rollback** to an earlier responsible node.
3. **Shared State:** Explicit common workspace passed between nodes, with **declared merge rules** (overwrite, append, sum) for concurrent writes. *Critical invariant:* **State is shared; node context is private**—specifically, the `verify` node MUST run in a **fresh context** isolated from `implement`'s reasoning.
4. **Routing Rules:** Explicit decision table (`(current node, condition) -> next node`).

**Loop vs. Graph:** A loop defers architectural decisions (hides failure/rollback paths inside one context window); a graph forces up-front decisions (puts ownership, dependencies, and rollback paths on paper).

### Three Structural Failures of Single Loops & Anchors (`L14`, pp. `118–119`)

Checkpoints inside one agent's brain cannot fix structural single-loop failures where judge and judged share context:
1. **Goodhart's Law:** Optimizing one proxy metric detaches from real outcomes (e.g., ticket-closure bot spikes churn by prematurely closing tickets).
2. **Blindness Upward:** A loop treats its target as sacred and cannot ask "is this the right goal/metric?"
3. **Inter-loop Conflict:** Independent loops optimize competing objectives (speed vs thoroughness, growth vs quality) and thrash the system.

**Four Graph Design Questions:** (1) Which loops feed which? (2) Which loops own the targets others chase? (3) Which loops can veto or roll back a change? (4) Which metrics may move vs must stay **frozen**?
**Anchors:** Mechanisms pinning loops to reality (ground-truth holdouts, real business/engineering outcomes, human spot-checks) to prevent mutual drift.

### Graph vs. Workflow & Anthropic's Five Patterns (`L14`, pp. `120–125`)

- **Anthropic workflow-vs-agent distinction:** Fixed-step code control flow = **workflow**; model-directed runtime control flow = **agent**. A **graph** contains deterministic workflow nodes, full agent nodes, and **human-in-the-loop (HITL) approval nodes**.
- **Anthropic's 5 patterns:** Prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer.
- **Six-step framework-agnostic graph build:** (1) Define shared state & merge rules -> (2) List nodes & private loops -> (3) Wire spine edges -> (4) Define conditional/rollback routing rules -> (5) Attach per-step checkpoints + pause-before-merge HITL gate -> (6) Run with explicit thread ID.
- **iii.dev counterargument:** Topology/shape is disposable; the load-bearing engineering capabilities are **replayability, observability, and crash recoverability**.
- **Fake-metric warning:** Course explicitly debunks viral `+18% accuracy, -85% cost` claims as mismatched baselines stitched from a chemical P&ID paper (`goddaehee`, Jul 2026).

### The Orchestration Tax & Five Graph Criteria (`L14`, pp. `127–129`)

- **The Orchestration Tax (Osmani):** Starting parallel agents is trivial; closing the loop (reviewing diffs, resolving architecture/merge conflicts, verifying integration) is expensive. **"You are the GIL of your AI agents"**—human judgment is a strictly serial bottleneck.
- **Five Criteria for When a Graph Is Justified (require `>=3`):**
  1. Decomposes into genuinely independent parallel work units
  2. Has explicit conditional branches or multi-hop rollback paths
  3. Intermediate state is worth checkpointing for pause/resume
  4. Node outputs are explicitly verifiable
  5. Parallel/coordination gains exceed coordination + review overhead
  *(A 20-step linear pipeline does NOT need a graph; a 5-node flow with real rollbacks, parallelism, and HITL approvals does.)*

---

## 3. Extended Industry Orchestration References (`REF-ORC`)

- **Upstream source:** `docs/en/resources/reference/index.md` (`2026 Extended References`, historical PDF pp. `176–180`, p. `177`) and `L13` p. `111`.
- **License / origin:** MIT (WalkingLab summary annotations of external 2026 industry posts; external full texts are not reproduced).

Key architectural patterns referenced for `P08–P09` design comparison:
- **OpenAI App Server & `Symphony`:** Reusable harness server protocol (thread lifecycle, resume, fork, diffs) and issue-tracker/board-driven multi-agent control plane.
- **Anthropic `Building a C compiler with parallel Claudes`:** Parallel agent teams using task locks, git synchronization, container isolation, and autonomous loops.
- **Anthropic `Managed Agents`:** Decoupling session, harness, and sandbox as swappable interfaces.
- **Claude Code Dynamic Workflows / Subagent Fan-out (`L13` p. `111`, `L14`):** Dynamic subagent dispatch and isolated worktrees.
- **Stripe `Minions` & Cognition `Multi-Agents`:** Devbox isolation, blueprint state machines combining deterministic steps + agent nodes, clean-context verifiers, manager-child boundaries.
- **Replit `Decision-Time Guidance` & Cursor `Continually improving our agent harness`:** Just-in-time rule injection via lightweight classifiers; offline evals + online metrics + tool-error taxonomy + model-specific tuning.

---

## 4. Project Adaptations (`X` for `H2-ORC-01..08`, `H2-FBK-09..11`)

- **`H2-ORC-01` (Logical Orchestrator):** Reuses Coordinator + deterministic Host (`quality_gates.py`, `agent_context.py`, `p1/`) for admission, routing, lifecycle, budget, retry, and escalation; **prohibits self-approval of scope or verdict**.
- **`H2-ORC-02` (Strict role separation):** Separates Owner, Planner, Orchestrator, Maker/Worker, Trusted Host/Verifier, and Fresh Checker/Auditor (`HARNESS_SPEC.md` §6.4). Cross-model checking is optional and **cannot replace process/context isolation**.
- **`H2-ORC-03` (Bounded multi-round Maker-Checker):** Operationalizes P07 Exp 3 (`>=5` recorded pilot rounds with seeded/controlled scenarios, immutable candidate per round, external round state, bounded `REVISE`/`BLOCK`/`ACCEPT` termination)—**NOT** forced to run 5 artificial rounds on routine Issues.
- **`H2-ORC-04` (6-dimension `0–2` rubric):** Uses `templates/evaluator-rubric.md` structure + hard gates independent of numeric score (`0–12`), calibrated over `3–5` human-labeled rounds (`OD-06`/`OD-09`).
- **`H2-ORC-05` (Restart reconciliation):** Adds crash/restart reconciliation, duplicate-dispatch prevention, stale-SHA receipt invalidation, and idempotent side-effect safety.
- **`H2-ORC-06 / H2-ORC-08` (Conditional Graph & Deferred Level 5 Fleet):** Core orchestration (Level 3 + controlled improvement) is mandatory in `P08`. Dynamic graphs (`H2-ORC-06`) and Level 5 Fleet (`H2-ORC-08`) require passing the 5 graph criteria, worktree isolation, ownership locks, versioned shared state, serialized human integration, and explicit **Owner approval** (or justified deferral in `P09`). Do NOT adopt Linear or external graph engines by default.
- **`H2-ORC-07` (Orchestration tax & WIP cap):** Must measure coordination, review, conflict, retry, token, and escaped-defect overhead, capping concurrency to human review capacity.
- **`H2-FBK-10 / H2-FBK-11` (`autoresearch` & Anti-Goodhart adaptations):** Borrows the hypothesis -> isolated experiment -> fixed-budget eval -> `KEEP`/`REJECT` ratchet—**rejecting** ML `val_bpb`, 5-min wall clock, and destructive `git reset` on `main`/user work. Experiments MUST run in disposable isolated branches/worktrees, MUST NOT modify the trusted test oracle/rubric/gates in the same run, require frozen holdout/safety invariants, and require normal Issue/PR/human review before promotion.
