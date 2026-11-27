# Knowledge Domain 06 — Hands-On Labs, Minimal Templates, Advanced Pack, and SOPs

> **Status:** Informative local coursebook knowledge (non-normative). Approved policies (`AGENTS.md`), [HARNESS_SPEC.md](../../../harness/HARNESS_SPEC.md), [HARNESS_MASTER_PLAN.md](../../../harness/HARNESS_MASTER_PLAN.md), ADRs, and versioned `contracts/` remain authoritative.
> **Upstream provenance:** Extracted from [`walkinglabs/learn-harness-engineering`](https://github.com/walkinglabs/learn-harness-engineering) at pinned commit `fe2c4ebd2010aa877b504e141437729296c934e8` (`docs/en/`), MIT License, Copyright (c) 2025 WalkingLab (see [../README.md](../README.md)).
> **Sections covered:** `LAB-INTRO`, `LAB` (`P01–P08`), `MIN` (`resources/index.md`, `templates/`), `ADV` (`openai-advanced/` + 18 `repo-template/` docs), `SOP` (`sops/`).
> **SPEC / Phase routing:** `H2-INS-01/06/07`, `H2-ENV-01/03/05`, `H2-STA-01/04`, `H2-FBK-03/04/06/07`, `H2-ORC-03/04/06/08`; Phases `P00–P10`.

---

## 1. Hands-On Labs (`LAB-INTRO`, `P01–P08`)

- **Upstream source:** `docs/en/projects/index.md` and `docs/en/projects/project-01..08/index.md` (historical PDF pp. `133–163`); plus inspected `projects/project-05/solution/` rubric/sprint artifacts as data.
- **License / origin:** MIT (WalkingLab). Course projects use an Electron + TypeScript + React knowledge-base app as teaching vehicle; **treat project code as illustrative data only—do not execute or adopt Electron/Node structures in LoRa firmware/backend**. *(Note: `projects/index.md` overview lists 7 projects historically while 8 project pages `project-01..08` exist.)*

### Experimental Hygiene Rules (`P01`, `P02`)

1. **Separate directories, NOT Git branches, for A/B harness comparisons (`P01`, `P02`):** Agents have full filesystem/git access and can inspect sibling directories or branch refs; keep weak-harness and strong-harness runs in isolated directories run one at a time, archiving and deleting before the next run.
2. **Reset checked-in evidence before strong run (`P01`):** Set `feature_list.json` statuses to `not-started`, clear `evidence`/`testedAt` fields, and clear session logs in `claude-progress.md` so the agent actually executes the work.
3. **Hold code, prompt, model, and stop point constant (`P02`, `P05`):** Only the harness artifact under test varies. To isolate a single artifact (e.g., `session-handoff.md` vs expanded `AGENTS.md`), add a third ablation run.

### Summary of Projects `P01–P08`

| Project | Course Mechanism & Controlled Protocol | Measured Metrics & Key Takeaways |
|---|---|---|
| **`P01` Baseline vs Minimal Harness** (`pp.135–139`) | 4 features (window launch, document list, Q&A panel, local data dir). Weak (`task-prompt.md` only) vs Strong (`AGENTS.md`, `CLAUDE.md`, `init.sh`, `feature_list.json`, `claude-progress.md`, `docs/ARCHITECTURE.md`, `docs/PRODUCT.md`). | Completion, time to first `npm start`, retries, missing items, premature stop. Partial/broken weak run is valid experimental evidence. |
| **`P02` Agent-Readable Workspace** (`pp.140–144`) | 2-session task (Session A: import + detail view; Session B: persistence across restart, prompt `"Continue the work."`). Thin starter vs `AGENTS.md` + `session-handoff.md`. | Session B pickup time, rediscovery count, handoff quality, repeated work, final completion. |
| **`P03` Multi-Session Continuity** (`pp.145–146`) | 4 features (chunking, metadata extraction, index status UI, citation Q&A). Starter `feature_list.json` vs full restart/handoff (`init.sh`, `session-handoff.md`, `claude-progress.md`, `clean-state-checklist.md`). | Drift across features, state loss after restart, verification evidence before `passing`. |
| **`P04` Runtime Feedback & Scope** (`pp.147–148`) | Seeded large-file chunking bug. Starter weak diagnostics vs `logger.ts` structured logs + `check-architecture.sh` boundary check + `ARCHITECTURE.md` + `clean-state-checklist.md`. | Time to locate root cause; invasiveness of fix with vs without runtime signals & boundary checks. |
| **`P05` Self-Verification & Role Separation** (`pp.149–150`) | Constant feature: multi-turn Q&A conversation history. Compares 3 variants: `single-role` (`1.6/5` rubric) -> `gen-eval` (`3.3/5`, citations count-only) -> `plan-gen-eval` (`4.9/5` with `sprint-contract.md` and 3 revision cycles `4.2 -> 4.6 -> 4.8 -> 4.9`). | Role separation + upfront `sprint-contract.md` drives largest jump in feature completeness, edge-case coverage, and revision convergence. |
| **`P06` Capstone & Ablation** (`pp.151–152`) | Mostly complete app with weak harness starter vs full capstone (`AGENTS.md`, `CLAUDE.md`, `feature_list.json`, `init.sh`, `session-handoff.md`, `clean-state-checklist.md`, `quality-document.md`, `evaluator-rubric.md`, `benchmark.sh`, `cleanup-scanner.sh`) + 1-by-1 ablation. | Isolates operating harness impact on restartability, benchmark pass rate, and quality grades. |
| **`P07` First Automated Loop** (`pp.153–158`) | 3 branches: (1) `p07-goal-loop` (`goal.md` vs manual baseline, >=2 iterations), (2) `p07-timer-loop` (`/loop` 10–30m for >=2h, measure false positives/follow-up cost), (3) `p07-maker-checker` (**>=5 recorded rounds** in `loop-state.md`, Maker + Checker + Loop control prompts, stop on `N` consecutive passes or max rounds). | Turn count, human interventions, defect recall, loop ceiling (Maker vs Checker capability), runaway/stall risks. |
| **`P08` Workflow as a Graph** (`pp.159–163`) | 3 branches: (1) `p08-explicit-graph` (`graph.md` mermaid + node/edge tables + shared `state.md` + routing rules; identify >=1 previously implicit edge), (2) `p08-parallel` (fan-out/fan-in + `git worktree` isolation + wall-clock/token/quality vs overhead), (3) `p08-human-in-the-loop` (conditional **layer-targeted rollback edge** e.g. to `research` vs `implement`, **HITL approval node** before merge with timeout/auto-escalate rule, >=2 full passes). | Structural visibility, failure localization, coordination tax vs speed, HITL agreement with verify node. |

---

## 2. Minimal Pack Resource Library and Templates (`MIN`)

- **Upstream source:** `docs/en/resources/index.md`, `docs/en/resources/templates/index.md`, and all 9 template artifacts under `docs/en/resources/templates/` (historical PDF pp. `164–173`).
- **License / origin:** MIT (WalkingLab).

### Minimal Pack Adoption Criterion

Start with **4 core files** in repo root (`AGENTS.md` or `CLAUDE.md`, `init.sh`, `claude-progress.md`, `feature_list.json`); add `session-handoff.md`, `clean-state-checklist.md`, `evaluator-rubric.md`, and `quality-document.md` as complexity grows. Upgrade to Advanced Pack when multi-domain governance, active plan lifecycles, and quality/reliability tracking outgrow minimal files.

### Complete Template Specifications (Offline Reconstructible)

#### 2.1 `AGENTS.md` / `CLAUDE.md` (`templates/AGENTS.md`, `templates/CLAUDE.md`)
- **Sections:**
  1. Purpose (leave repo restartable without guessing)
  2. Startup Workflow (`pwd` -> read `claude-progress.md` -> read `feature_list.json` -> `git log --oneline -5` -> `./init.sh` -> baseline smoke; fix baseline first if broken)
  3. Working Rules (`WIP=1`, no code-only completion, keep in scope, do not weaken verification rules, durable artifacts over chat)
  4. Required Artifacts (`feature_list.json`, `claude-progress.md`, `init.sh`, optional `session-handoff.md`)
  5. Definition of Done (behavior implemented + required verification actually ran + evidence recorded + restartable from standard startup path)
  6. End of Session (update progress -> update feature list -> record unresolved risk/blocker -> commit safe state -> clean restart path)

#### 2.2 `init.sh` (`templates/init.sh`)
- **Variables:** `INSTALL_CMD`, `VERIFY_CMD`, `START_CMD`.
- **Behavior (`set -euo pipefail`):** Resolves `ROOT_DIR`, prints `$PWD`, runs `"${INSTALL_CMD[@]}"`, runs `"${VERIFY_CMD[@]}"`, prints `"${START_CMD[@]}"`, and executes `START_CMD` only when `RUN_START_COMMAND=1`. Nonzero verification stops further feature work.

#### 2.3 `claude-progress.md` (`templates/claude-progress.md`)
*(Note: Agent-agnostic session log; `HARNESS_SPEC.md` §5.1 proposes `PROGRESS.md` or Issue-local durable handoff.)*
- **Section 1 — Current Verified State:** `Repository root`, `Standard startup path`, `Standard verification path`, `Current highest-priority unfinished feature`, `Current blocker`.
- **Section 2 — Session Log (per `Session NNN`):** `Date`, `Goal`, `Completed`, `Verification run`, `Evidence captured`, `Commits`, `Files or artifacts updated`, `Known risk or unresolved issue`, `Next best step`.

#### 2.4 `feature_list.json` (`templates/feature_list.json`)
- **Top-level schema:**
  - `project` (string), `last_updated` (`YYYY-MM-DD`)
  - `rules`: `{ "single_active_feature": true, "passing_requires_evidence": true, "do_not_skip_verification": true }`
  - `status_legend`: `not_started`, `in_progress` *(maps to `active` in `HARNESS_SPEC.md` §6.2)*, `blocked`, `passing`
  - `features[]` item fields:
    - `id` (unique string, e.g. `chat-001`), `priority` (integer, lower = higher), `area`, `title`, `user_visible_behavior`, `status`, `verification` (ordered step array), `evidence` (array of verified proof refs), `notes`.
- **Rule:** Maximum **1** feature in `in_progress`/`active` at a time; transition to `passing` requires executed verification + recorded evidence.

#### 2.5 `session-handoff.md` (`templates/session-handoff.md`)
Five sections: (1) **Verified Now** (working + verification actually ran), (2) **Changed This Session** (product vs infra/harness), (3) **Broken Or Unverified** (known defect, unverified path, risk for next session), (4) **Next Best Step** (highest-priority feature, why next, what counts as passing, **what must not change**), (5) **Commands** (startup, verification, focused debug).

#### 2.6 `clean-state-checklist.md` (`templates/clean-state-checklist.md`)
Six exit checks:
- [ ] Standard startup path still works
- [ ] Standard verification path still runs
- [ ] Current progress recorded in progress log
- [ ] Feature state reflects actual passing vs unverified status
- [ ] No half-finished step left undocumented
- [ ] Next session can continue without manual repair

#### 2.7 `evaluator-rubric.md` (`templates/evaluator-rubric.md` & `templates/index.md`, pp. `171–172`)
Adopted as baseline schema by `HARNESS_SPEC.md` §7.3 (`H2-ORC-04`):
- **Six Dimensions (each scored `0–2`):**
  1. **Correctness:** Does implemented behavior match requested feature?
  2. **Verification:** Did required checks actually run, with evidence?
  3. **Scope discipline:** Did session stay inside chosen feature scope?
  4. **Reliability:** Does result survive restart or rerun without repair?
  5. **Maintainability:** Are code and docs clear enough for next session?
  6. **Handoff readiness:** Can a fresh session continue from repo artifacts only?
- **Verdict options:** `Accept`, `Revise`, `Block`.
- **Required Follow-Up:** `Missing evidence`, `Required fixes`, `Next review trigger`.
- **Calibration procedure (`3–5` tuning rounds):** Run evaluator on sprint -> compare scores with human judgment -> sharpen rubric pass/fail criteria where they diverge -> rerun and verify alignment -> track changes across `3–5` rounds.

#### 2.8 `quality-document.md` (`templates/quality-document.md`, pp. `172–173`)
- **Scale:** `A` (verified, clean, legible, stable), `B` (minor gaps), `C` (partial, known gaps/hard to read), `D` (broken or major structural issues). *(Project adds `NOT_VERIFIED` per `H2-FBK-07`.)*
- **Tables:**
  - *Product Domains:* `Domain | Grade | Verification | Agent Legibility | Test Stability | Key Gaps | Last Updated`
  - *Architectural Layers:* `Layer | Grade | Boundary Enforcement | Agent Legibility | Key Gaps | Last Updated`
  - *Change History:* `Changes | Domains promoted | Demoted | New gaps identified | Gaps closed`
- **Simplification Tie-in:** Snapshot quality -> remove 1 harness component -> run benchmark suite -> re-snapshot -> keep removed if grades unchanged, restore if degraded.

---

## 3. OpenAI Advanced Pack & Repo Template (`ADV`, Sections 32–50)

- **Upstream source:** `docs/en/resources/openai-advanced/index.md` and `docs/en/resources/openai-advanced/repo-template/**` (18 template files, historical PDF pp. `185–212`).
- **License / origin:** MIT (WalkingLab packaging OpenAI's *Harness engineering* repository topology).

### Target Layout & Copy Order (`ADV` pp. `185–187`, `212`)

1. Root `AGENTS.md` + `ARCHITECTURE.md`
2. `docs/` tree (`DESIGN.md`, `FRONTEND.md`, `PLANS.md`, `PRODUCT_SENSE.md`, `QUALITY_SCORE.md`, `RELIABILITY.md`, `SECURITY.md`, `design-docs/`, `exec-plans/`, `generated/`, `product-specs/`, `references/`)
3. Fill `PRODUCT_SENSE.md`, `QUALITY_SCORE.md`, `RELIABILITY.md` first -> create active plan under `docs/exec-plans/active/`.

### Artifact-by-Artifact Specification (`repo-template/`)

| Sec | Template Path | Core Structure & Operating Rules |
|---|---|---|
| 33 | `AGENTS.md` (`pp.188–190`) | Short router (~60 lines template): Startup Workflow (7 steps: `pwd` -> `ARCHITECTURE.md` -> `QUALITY_SCORE.md` -> `PLANS.md` + active plan -> `product-specs/` -> bootstrap/verify -> repair broken baseline first), 8-entry Routing Map, Working Contract, DoD, End of Session (update plan, `QUALITY_SCORE.md`, `tech-debt-tracker.md`, archive finished plans). |
| 34 | `ARCHITECTURE.md` (`pp.191–193`) | System Shape (product, workflow, runtime surfaces, spec path), Domain Map table, Layer Model (`Types -> Config -> Repo -> Service -> Runtime -> UI`), Hard Dependency Rules (strictly forward, no UI bypass, generic utils), Cross-Cutting Interfaces table (logging, auth, external APIs, feature flags), Current Hot Spots, Change Checklist. |
| 35 | `docs/design-docs/core-beliefs.md` (`p.194`) | 7 beliefs: repo = system of record; `AGENTS.md` = router; evidence > confidence; 1 bounded task > many half-done; repeated human feedback -> mechanical rules; cleanup/simplification = first-class; undiscoverable fact = operationally unavailable. |
| 36 | `docs/design-docs/index.md` (`p.195`) | Categorizes `Accepted`, `Proposed`, `Deprecated` (with replacement links); requires owner/update trigger per doc and active plan links. |
| 37 | `docs/DESIGN.md` (`p.196`) | Brief entry routing to `design-docs/index.md` & `core-beliefs.md`; 1 doc per decision area; promote operationally critical rules to automated checks / `ARCHITECTURE.md`. |
| 38 | `docs/exec-plans/active/` (`p.197`) | Holds active execution plans (1 clearly owned active step per plan). |
| 39 | `docs/exec-plans/completed/` (`p.198`) | Archives finished execution plans for future agent decision provenance. |
| 40 | `docs/exec-plans/tech-debt-tracker.md` (`p.199`) | Table: `Date | Area | Debt | Why Deferred | Risk | Next Trigger`. |
| 41 | `docs/FRONTEND.md` (`p.200`) | UI principles (clarity before novelty, reusable components, accessibility as normal verification), Guardrails (design-system doc in `references/`, 5 UI states: `empty/loading/success/error/retry`, consistent copy/keyboard), Verification Expectations (runtime/browser evidence, DOM/screenshot checks). |
| 42 | `docs/generated/db-schema.md` (`p.201`) | Header: `Generated from: <command/source>` + `Last refreshed: YYYY-MM-DD`; rule: **never hand-edit generated sections**, regenerate on schema change. |
| 43 | `docs/PLANS.md` (`pp.202–203`) | Plan required when work spans `>1` session, `>1` subsystem, non-trivial rollout/verification risk, or open decisions. Minimum sections: `objective`, `scope & out-of-scope`, `verification path`, `risks & blockers`, `progress log`, `open decisions`. |
| 44 | `docs/PRODUCT_SENSE.md` (`p.204`) | Product Core (`Primary user`, `Job to be done`, `Main frustration`, `Quality bar`), Product Rules (reliability > feature count; ambiguity = spec gap, never guess), No-Go Patterns (hidden destructive actions, silent failure, unclear state source, unexplainable features). |
| 45 | `docs/product-specs/index.md` (`p.205`) | Lists `Active Specs`; rules: describe user-visible behavior + AC, update spec or code in same session on divergence. |
| 46 | `docs/product-specs/new-user-onboarding.md` (`p.206`) | Template spec: `Goal`, `Entry Conditions`, `User Flow`, `Acceptance Criteria` (observable outcomes), `Failure States` (recoverable error + blocked fallback). |
| 47 | `docs/QUALITY_SCORE.md` (`pp.207–208`) | `A–D` grading scale + `Product Domains` table + `Architectural Layers` table + `Benchmark Snapshots` (`Date | Variant | Completion Rate | Retries | Defects Before Review | Notes`) + `Simplification Log` (`Date | Component Removed | Outcome | Decision`). |
| 48 | `docs/RELIABILITY.md` (`pp.209–210`) | Standard Paths (Bootstrap, Verification, Start, Debug/Inspect), Required Runtime Signals (structured logs, health checks, traces/timing, user-visible error states), Golden Journeys (repeatable path + failure signals), Reliability Rules (clean restart required, diagnosable from local signals, cleanup = reliability). |
| 49 | `docs/SECURITY.md` (`p.211`) | Secrets & Credentials (no hard-coded secrets, redact logs/screenshots), Untrusted Input (validate external content, fetch/execution boundaries, prompt/command injection guardrails), External Actions (approval-gated vs forbidden default commands, sandbox-safe debugging), Dependency & Review Rules (justify new deps in plan; repeated security comments -> checks). |
| 50 | `docs/references/*.txt` (`p.212` / `ADV`) | Model-friendly `*-llms.txt` extracts (`design-system-reference-llms.txt`, `nixpacks-llms.txt`, `uv-llms.txt`) for concise tool/UI rules refreshed on upstream change. |

---

## 4. OpenAI Advanced Standard Operating Procedures (`SOP`, Sections 51–55)

- **Upstream source:** `docs/en/resources/openai-advanced/sops/index.md` and the 4 SOP files under `sops/` (historical PDF pp. `213–221`).
- **License / origin:** MIT (WalkingLab).

### 4.1 `SOP: Chrome DevTools Validation Loop` (`Sec 51`, pp. `213–214`)
Use when UI work requires runtime DOM, console, and screenshot verification rather than code reading:
- **Required inputs:** stable startup command, reproducible UI journey, snapshot mechanism (DOM/console/screenshot), explicit "clean" definition.
- **8-step core loop:** (1) Select target page/instance -> (2) Clear stale console noise -> (3) Capture **BEFORE** state -> (4) Trigger **one** UI path -> (5) Observe runtime events -> (6) Capture **AFTER** state -> (7) Fix smallest responsible layer & restart if needed -> (8) Re-run until clean.
- **Clean criteria:** Intended visible state present, unexpected errors absent, console noise understood/cleared, repeatable result on rerun.
- **Update artifacts:** Active execution plan, `docs/RELIABILITY.md` (if golden path), product spec (if visible behavior changed).

### 4.2 `SOP: Encode Unseen Knowledge Into The Repo` (`Sec 52`, pp. `215–216`)
Use when context lives in chats, external docs, tickets, or human memory:
- **Trigger signals:** Agent repeatedly asks how system works; humans cite Slack/verbal decisions; reviews cite unwritten rules; new sessions repeat settled discovery.
- **5-step SOP:** (1) Inventory invisible sources -> (2) Classify (`architecture` -> `ARCHITECTURE.md`, `product behavior` -> `docs/product-specs/`, `design rationale` -> `docs/design-docs/`, `execution state` -> `docs/exec-plans/`, `external refs` -> `docs/references/`, `quality/reliability` -> `QUALITY_SCORE.md`/`RELIABILITY.md`) -> (3) Write concise, operationally actionable rules near governed code -> (4) Cross-link -> (5) Remove/deprecate stale copies (one truth).
- **DoD:** Fresh agent discovers rule without asking human; no contradictory duplicates; artifact lives near governed code/workflow.

### 4.3 `SOP: Layered Domain Architecture` (`Sec 54`, pp. `218–219`)
Use when agents violate module boundaries or duplicate cross-layer logic:
- **Course directional flow:** `Types -> Config -> Repo -> Service -> Runtime -> UI`; cross-cutting concerns enter via explicit providers/adapters; generic utils carry no domain logic.
- **7-step SOP:** (1) Map domains -> (2) Define allowed layer sequence -> (3) Route cross-cutting concerns via providers/adapters -> (4) Relocate ambiguous shared logic to owner domain or generic utils -> (5) Document in `ARCHITECTURE.md` -> (6) **Add >=1 executable guardrail for the highest-cost boundary violation** -> (7) Update `QUALITY_SCORE.md`.
- **DoD:** Fresh agent identifies layer owner; UI never touches repo/side effects directly; >=1 boundary mechanically enforced.

### 4.4 `SOP: Observability Feedback Loop` (`Sec 55`, pp. `220–221`)
Use when debugging is slow or agents claim success without runtime evidence:
- **Minimum stack:** Structured app logs + metrics/traces where feasible + local collection + local query interface + repeatable workload/golden journey.
- **7-step SOP:** (1) Define golden journeys -> (2) Add structured logs on startup & critical paths -> (3) Add latency/failure/queue-depth metrics -> (4) Add timing markers/traces on slow steps -> (5) Expose local query -> (6) Provide repeatable workload -> (7) Enforce loop: `query -> correlate -> reason -> implement -> restart -> rerun -> verify`.
- **6-Question Debug Checklist:** What failed? Which signal proves it? Which layer owns it? What changed after fix? Did app restart cleanly? Did same workload pass on rerun?

---

## 5. Project Adaptations & Non-Transferability (`X`)

- **Do NOT duplicate canonical LoRa docs (`H2-INS-06`, `OD-05`, `HARNESS_SPEC.md` §5.2):** Advanced Pack paths (`ARCHITECTURE.md`, `docs/design-docs/`, `docs/product-specs/`, `docs/PLANS.md`, `docs/QUALITY_SCORE.md`, `docs/RELIABILITY.md`, `docs/SECURITY.md`, `docs/FRONTEND.md`) are **logical target surfaces**. Existing authoritative LoRa directories (`docs/adr/`, `docs/requirements/`, `contracts/`, `docs/architecture/`, `docs/verification/`, `.agent-harness/`, `.agents/`, `scripts/agent_harness/`) are reused and mapped rather than duplicated.
- **Embedded/IoT non-transferability:** Course Electron (`Main/Preload/Renderer`), `npm`/`init.sh` defaults, and `Types->Config->Repo->Service->Runtime->UI` examples do **not** apply to ESP32/SX1276 firmware (`sx1276_driver`, `lora_mac`, `airtime_policy`, `gateway_master`, `sensor_node` under CCARS v1.4) or Go Modular Monolith (GOCARS). Chrome DevTools SOP applies only where Web Dashboard UI validation is in scope (`clients/web-dashboard/`).
- **Pre-edit baseline difference:** Unlike generic `AGENTS.md` / `CLAUDE.md` templates telling the agent to immediately fix a broken baseline, in this repository **out-of-allowlist baseline defects MUST be reported and blocked (`H2-ENV-04`, `GOV-001`), never edited without scope authorization**.
- **Rubric variant resolution:** Adopt `MIN templates/evaluator-rubric.md` (`6` dimensions `0–2` + `ACCEPT`/`REVISE`/`BLOCK` + hard gates in `HARNESS_SPEC.md` §7.3), NOT the 4-dimension `1–5` Q&A example in `L11/code/evaluator-rubric.md`.
