# Harness Engineering Coursebook — Reference Index

> **Issue:** [#415](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/415) (`[Harness V2][P00-B]`) · **Companion:** [README.md](README.md)
> **Normative SPEC:** [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) (`v0.2.0`) · **Master Plan:** [HARNESS_MASTER_PLAN.md](../../harness/HARNESS_MASTER_PLAN.md) (`v0.2.0`)
> **Source PDF:** `learn-harness-engineering-en.pdf` (`221` physical pages, SHA-256 `777e654c404c167020e29d0b0b4519e22c0c72bbcca383d83d873536cd012b67`)

**Page numbering convention:** Physical PDF page numbers (`1–221`, 1-based) are primary and match [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) §2 and §4. Section-relative printed footer labels (`1/N … N/N`) are shown in parentheses for cross-checking against rendered pages. Load only the sections needed for the active task—never all 221 pages by default.

---

## 1. Verified PDF Structure (Cover/TOC + All 55 Sections)

### SPEC Reference Code Legend

- `L01–L14`: Lectures 01–14 (pp. `7–132`)
- `LAB`: Projects 01–08 (pp. `135–163`, preceded by Welcome to Projects pp. `133–134`)
- `MIN`: English Resource Library & Template Guide (pp. `164–173`)
- `START`: Coding Agent Startup Flow (`174–175`), Initializer Agent Playbook (`181–182`), Method Map (`183`), Prompt Calibration (`184`)
- `ADV`: OpenAI Advanced Pack & Repo Template (pp. `185–212`)
- `SOP`: OpenAI Advanced SOPs (pp. `213–221`)
- `ORC`: Orchestration patterns, maturity ladder & orchestration tax (pp. `110`, `120–121`, `127–129`)
- `EXP`: Three-agent DAW case (`80–81`), `autoresearch` ratchet (`104–107`), Maker-Checker lab (`156–158`)
- `REF-ORC`: `Claude Code: Dynamic Workflows and Orchestration` (p. `111`), OpenAI `Symphony` & parallel-agent references (p. `177`)

### Complete 221-Page Section Inventory

| # | SPEC Code | Physical Pages | Printed Footer | Section Title | Upstream Route |
|---:|---|---:|---|---|---|
| — | `TOC` | `1–3` | *(none)* | Cover & Included sections (`1–55`) | — |
| 1 | `INTRO` | `4–6` | `1/3–3/3` | Welcome to Learn Harness Engineering | `/en/` |
| 2 | `L01` | `7–12` | `1/6–6/6` | Lecture 01. Strong Models Don't Mean Reliable Execution | `/en/lectures/lecture-01-why-capable-agents-still-fail/` |
| 3 | `L02` | `13–18` | `1/6–6/6` | Lecture 02. What a Harness Actually Is | `/en/lectures/lecture-02-what-a-harness-actually-is/` |
| 4 | `L03` | `19–25` | `1/7–7/7` | Lecture 03. Making the Repository the Single Source of Truth | `/en/lectures/lecture-03-why-the-repository-must-become-the-system-of-record/` |
| 5 | `L04` | `26–32` | `1/7–7/7` | Lecture 04. Split Instructions Across Files | `/en/lectures/lecture-04-why-one-giant-instruction-file-fails/` |
| 6 | `L05` | `33–40` | `1/8–8/8` | Lecture 05. Keeping Context Alive Across Sessions | `/en/lectures/lecture-05-why-long-running-tasks-lose-continuity/` |
| 7 | `L06` | `41–47` | `1/7–7/7` | Lecture 06. Make the Agent Initialize Before Every Work Session | `/en/lectures/lecture-06-why-initialization-needs-its-own-phase/` |
| 8 | `L07` | `48–54` | `1/7–7/7` | Lecture 07. Draw Clear Task Boundaries for Agents | `/en/lectures/lecture-07-why-agents-overreach-and-under-finish/` |
| 9 | `L08` | `55–60` | `1/6–6/6` | Lecture 08. Use Feature Lists to Constrain What the Agent Does | `/en/lectures/lecture-08-why-feature-lists-are-harness-primitives/` |
| 10 | `L09` | `61–67` | `1/7–7/7` | Lecture 9. Preventing Agents from Declaring Victory Too Early | `/en/lectures/lecture-09-why-agents-declare-victory-too-early/` |
| 11 | `L10` | `68–74` | `1/7–7/7` | Lecture 10. Only a Full Pipeline Run Counts as Real Verification | `/en/lectures/lecture-10-why-end-to-end-testing-changes-results/` |
| 12 | `L11` | `75–82` | `1/8–8/8` | Lecture 11. Making the Agent's Runtime Observable | `/en/lectures/lecture-11-why-observability-belongs-inside-the-harness/` |
| 13 | `L12` | `83–90` | `1/8–8/8` | Lecture 12. Leave a Clean Handoff at the End of Every Session | `/en/lectures/lecture-12-why-every-session-must-leave-a-clean-state/` |
| 14 | `L13` | `91–112` | `1/22–22/22` | Lecture 13. From Manual Prompting to Autonomous Loops | `/en/lectures/lecture-13-loop-engineering/` |
| 15 | `L14` | `113–132` | `1/20–20/20` | Lecture 14. From Single Loops to Graph Engineering | `/en/lectures/lecture-14-graph-engineering/` |
| 16 | `LAB-INTRO` | `133–134` | `1/2–2/2` | Welcome to Projects | `/en/projects/` |
| 17 | `LAB` (P01) | `135–139` | `1/5–5/5` | Project 01. Prompt-Only vs. Rules-First: How Much Difference Does It Make | `/en/projects/project-01-baseline-vs-minimal-harness/` |
| 18 | `LAB` (P02) | `140–144` | `1/5–5/5` | Project 02. Make the Project Readable and Pick Up Where You Left Off | `/en/projects/project-02-agent-readable-workspace/` |
| 19 | `LAB` (P03) | `145–146` | `1/2–2/2` | Project 03. Keep the Agent Working Across Session Restarts | `/en/projects/project-03-multi-session-continuity/` |
| 20 | `LAB` (P04) | `147–148` | `1/2–2/2` | Project 04. Use Runtime Feedback to Correct Agent Behavior | `/en/projects/project-04-incremental-indexing/` |
| 21 | `LAB` (P05) | `149–150` | `1/2–2/2` | Project 05. Make the Agent Verify Its Own Work | `/en/projects/project-05-grounded-qa-verification/` |
| 22 | `LAB` (P06) | `151–152` | `1/2–2/2` | Project 06. Build a Complete Agent Harness (Capstone) | `/en/projects/project-06-runtime-observability-and-debugging/` |
| 23 | `LAB` (P07) | `153–158` | `1/6–6/6` | Project 07. Build Your First Automated Loop | `/en/projects/project-07-loop-engineering-first-loop/` |
| 24 | `LAB` (P08) | `159–163` | `1/5–5/5` | Project 08. Draw Your Workflow as a Graph | `/en/projects/project-08-graph-engineering-first-graph/` |
| 25 | `MIN` | `164–165` | `1/2–2/2` | English Resource Library | `/en/resources/` |
| 26 | `MIN` | `166–173` | `1/8–8/8` | Template Guide | `/en/resources/templates/` |
| 27 | `START` | `174–175` | `1/2–2/2` | Coding Agent Startup Flow | `/en/resources/reference/coding-agent-startup-flow` |
| 28 | `REF-ORC` | `176–180` | `1/5–5/5` | English Reference | `/en/resources/reference/` |
| 29 | `START` | `181–182` | `1/2–2/2` | Initializer Agent Playbook | `/en/resources/reference/initializer-agent-playbook` |
| 30 | `START` | `183` | `1/1` | Method Map | `/en/resources/reference/method-map` |
| 31 | `START` | `184` | `1/1` | Prompt Calibration | `/en/resources/reference/prompt-calibration` |
| 32 | `ADV` | `185–187` | `1/3–3/3` | OpenAI Advanced Pack | `/en/resources/openai-advanced/` |
| 33 | `ADV` | `188–190` | `1/3–3/3` | AGENTS.md | `/en/resources/openai-advanced/repo-template/AGENTS` |
| 34 | `ADV` | `191–193` | `1/3–3/3` | ARCHITECTURE.md | `/en/resources/openai-advanced/repo-template/ARCHITECTURE` |
| 35 | `ADV` | `194` | `1/1` | Core Beliefs | `/en/resources/openai-advanced/repo-template/docs/design-docs/core-beliefs` |
| 36 | `ADV` | `195` | `1/1` | Design Docs Index | `/en/resources/openai-advanced/repo-template/docs/design-docs/` |
| 37 | `ADV` | `196` | `1/1` | DESIGN.md | `/en/resources/openai-advanced/repo-template/docs/DESIGN` |
| 38 | `ADV` | `197` | `1/1` | Active Plans | `/en/resources/openai-advanced/repo-template/docs/exec-plans/active/` |
| 39 | `ADV` | `198` | `1/1` | Completed Plans | `/en/resources/openai-advanced/repo-template/docs/exec-plans/completed/` |
| 40 | `ADV` | `199` | `1/1` | Tech Debt Tracker | `/en/resources/openai-advanced/repo-template/docs/exec-plans/tech-debt-tracker` |
| 41 | `ADV` | `200` | `1/1` | FRONTEND.md | `/en/resources/openai-advanced/repo-template/docs/FRONTEND` |
| 42 | `ADV` | `201` | `1/1` | Database Schema | `/en/resources/openai-advanced/repo-template/docs/generated/db-schema` |
| 43 | `ADV` | `202–203` | `1/2–2/2` | PLANS.md | `/en/resources/openai-advanced/repo-template/docs/PLANS` |
| 44 | `ADV` | `204` | `1/1` | PRODUCT_SENSE.md | `/en/resources/openai-advanced/repo-template/docs/PRODUCT_SENSE` |
| 45 | `ADV` | `205` | `1/1` | Product Specs Index | `/en/resources/openai-advanced/repo-template/docs/product-specs/` |
| 46 | `ADV` | `206` | `1/1` | New User Onboarding | `/en/resources/openai-advanced/repo-template/docs/product-specs/new-user-onboarding` |
| 47 | `ADV` | `207–208` | `1/2–2/2` | QUALITY_SCORE.md | `/en/resources/openai-advanced/repo-template/docs/QUALITY_SCORE` |
| 48 | `ADV` | `209–210` | `1/2–2/2` | RELIABILITY.md | `/en/resources/openai-advanced/repo-template/docs/RELIABILITY` |
| 49 | `ADV` | `211` | `1/1` | SECURITY.md | `/en/resources/openai-advanced/repo-template/docs/SECURITY` |
| 50 | `ADV` | `212` | `1/1` | Advanced Repo Template | `/en/resources/openai-advanced/repo-template/` |
| 51 | `SOP` | `213–214` | `1/2–2/2` | SOP: Chrome DevTools Validation Loop | `/en/resources/openai-advanced/sops/chrome-devtools-validation-loop` |
| 52 | `SOP` | `215–216` | `1/2–2/2` | SOP: Encode Unseen Knowledge Into The Repo | `/en/resources/openai-advanced/sops/encode-knowledge-into-repo` |
| 53 | `SOP` | `217` | `1/1` | OpenAI Advanced SOPs | `/en/resources/openai-advanced/sops/` |
| 54 | `SOP` | `218–219` | `1/2–2/2` | SOP: Layered Domain Architecture | `/en/resources/openai-advanced/sops/layered-domain-architecture` |
| 55 | `SOP` | `220–221` | `1/2–2/2` | SOP: Observability Feedback Loop | `/en/resources/openai-advanced/sops/observability-feedback-loop` |

---

## 2. Complete Mapping of 45/45 `H2-*` Requirements ([HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) §4)

Source classification follows [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) §2 & §4:
- **`REFERENCE` (`R`):** Derived directly from cited coursebook sections (`11` IDs).
- **`MIXED (R + X)`:** Coursebook primary concept extended with project-specific engineering/Embedded/IoT/governance guards (`26` IDs).
- **`MIXED (X + R)`:** Project-specific requirement primary, informed by cited coursebook sections (`8` IDs).

Coverage check: `7 INS + 5 TOL + 5 ENV + 6 STA + 11 FBK + 3 GOV + 8 ORC = 45/45` (`11 REFERENCE`, `26 MIXED (R + X)`, `8 MIXED (X + R)`).

### 2.1 Instructions (`H2-INS-01..07`)

| H2 ID | Topic | Source Class | SPEC Source Ref | Exact PDF Sections & Physical Pages (Printed Labels) | `PROJECT_EXTENSION (X)` Rationale / Adaptation |
|---|---|---|---|---|---|
| `H2-INS-01` | Root `AGENTS.md` required sections | `REFERENCE` | `R L02/L04, MIN, ADV 188–190` | `L02` pp. `13–18` (`1/6–6/6`, esp. p. `15` `3/6`); `L04` pp. `26–32` (`1/7–7/7`, esp. p. `29` `4/7`); `MIN` pp. `164–173` (`1/2–2/2`, `1/8–8/8`, esp. pp. `166–167` `1/8–2/8`); `ADV` Sec 33 pp. `188–190` (`1/3–3/3`) | — *(pure `R`; fields adapted to actual monorepo stack and commands)* |
| `H2-INS-02` | `AGENTS.md` size budget & priority placement | `MIXED (R + X)` | `R L04 26–32; X ngân sách` | `L04` pp. `26–32` (`1/7–7/7`; p. `27` `2/7` & p. `29` `4/7` specify 50–200 lines; p. `30` `5/7` ~100 lines & top/bottom recall) | Course allows 50–200 lines; project extension tightens internal target to `80–120` lines, `≤10` invariant groups, byte/token inventory, and mandatory exception review so no mandatory rule is dropped. |
| `H2-INS-03` | Authority hierarchy & conflict stop | `MIXED (R + X)` | `R L03/L04; X §3.1` | `L03` pp. `19–25` (`1/7–7/7`, esp. p. `19` `1/7`, p. `21` `3/7` System of Record); `L04` pp. `26–32` (`1/7–7/7`, esp. p. `27` `2/7` priority conflicts) | SPEC §3.1 defines decision-type authority routing (Issue/ADR/contracts/datasheets/policy/code/plans/references) and mandatory `STOP_AND_REPORT` conflict escalation so plans/code cannot override approved invariants. |
| `H2-INS-04` | Applicability routing & rule metadata | `REFERENCE` | `R L04, START 184` | `L04` pp. `26–32` (`1/7–7/7`, esp. pp. `28–30` `3/7–5/7` reveal-on-demand, source/applicability/expiry); `START` Sec 31 `Prompt Calibration` p. `184` (`1/1`) | — *(pure `R`)* |
| `H2-INS-05` | Preserve G0 & deterministic rule selection | `MIXED (X + R)` | `X existing Harness; R L04` | `L04` pp. `26–32` (`1/7–7/7`, esp. pp. `28–30` `3/7–5/7` SNR & selective context) | Preserves existing Host G0 `AGENTS.md` byte/SHA gate and deterministic C/Go rule selection, partitions, and pre/post receipts (Owner #137 / ADR-0005) instead of soft model-only compliance. |
| `H2-INS-06` | Architecture/domain map & dependency boundaries | `REFERENCE` | `R L03, L10, ADV 191–196, SOP 218–219` | `L03` pp. `19–25` (`1/7–7/7`, esp. pp. `21–22` `3/7–4/7`); `L10` pp. `68–74` (`1/7–7/7`, esp. pp. `71–72` `4/7–5/7`); `ADV` Sec 34–37 pp. `191–196` (`1/3–3/3`, `1/1`, `1/1`, `1/1`); `SOP` Sec 54 pp. `218–219` (`1/2–2/2`) | — *(pure `R`; domain maps target actual firmware/Go/client boundaries rather than sample web layers)* |
| `H2-INS-07` | Encode unseen knowledge & retire stale docs | `REFERENCE` | `R L03, SOP 215–216` | `L03` pp. `19–25` (`1/7–7/7`, esp. pp. `21–22` `3/7–4/7` decay & update with code); `SOP` Sec 52 pp. `215–216` (`1/2–2/2`) | — *(pure `R`)* |

### 2.2 Tools (`H2-TOL-01..05`)

| H2 ID | Topic | Source Class | SPEC Source Ref | Exact PDF Sections & Physical Pages (Printed Labels) | `PROJECT_EXTENSION (X)` Rationale / Adaptation |
|---|---|---|---|---|---|
| `H2-TOL-01` | Capability disclosure, role ownership & probes | `MIXED (R + X)` | `R L02; X` | `L02` pp. `13–18` (`1/6–6/6`, esp. p. `15` `3/6` Tool subsystem) | Requires explicit role capability/prerequisite declaration and fail-closed `BLOCKED` probe when a required tool is missing, reusing existing registry when sufficient. |
| `H2-TOL-02` | Runtime least-privilege enforcement | `MIXED (R + X)` | `R L02, ADV 211; X` | `L02` p. `15` (`3/6` least privilege); `ADV` Sec 49 `SECURITY.md` p. `211` (`1/1`) | Enforces filesystem, process, network, and credential isolation per role (Worker writes only granted candidate; Auditor cannot mutate candidate/evidence; post-diff check alone is insufficient). |
| `H2-TOL-03` | Exact scope guard, Host trust & untrusted data | `MIXED (X + R)` | `X; R ADV 211` | `ADV` Sec 49 `SECURITY.md` p. `211` (`1/1` Untrusted Input & External Actions) | Protects monorepo integrity boundaries: symlink/traversal rejection, forged-receipt rejection, exact allowlist enforcement, and treating Issue/PR/tool output as untrusted data. |
| `H2-TOL-04` | Identity-scoped timeout, cancel & cleanup | `MIXED (X + R)` | `X; R L11/L12` | `L11` pp. `75–82` (`1/8–8/8`, esp. p. `78` `4/8` process/resource signals); `L12` pp. `83–90` (`1/8–8/8`, esp. pp. `87–88` `5/8–6/8` idempotent cleanup) | Ties timeout, cancellation, and cleanup strictly to execution identity so concurrent runs and other worktrees are never harmed. |
| `H2-TOL-05` | Dual Codex / Antigravity shared interface | `MIXED (X + R)` | `X; R L13` | `L13` pp. `91–112` (`1/22–22/22`, esp. pp. `93` `3/22`, `99–101` `9/22–11/22` Codex/Claude comparison) | Supports both Codex and Antigravity (`agy`) via a shared interface where actually used, while blocking MCP/provider profiles from becoming independent policy authorities. |

### 2.3 Environment (`H2-ENV-01..05`)

| H2 ID | Topic | Source Class | SPEC Source Ref | Exact PDF Sections & Physical Pages (Printed Labels) | `PROJECT_EXTENSION (X)` Rationale / Adaptation |
|---|---|---|---|---|---|
| `H2-ENV-01` | Separate initialization phase & unified startup | `REFERENCE` | `R L06, MIN, START` | `L06` pp. `41–47` (`1/7–7/7`); `MIN` Sec 26 pp. `166–167` (`1/8–2/8` `init.sh`); `START` Sec 27 pp. `174–175` (`1/2–2/2`) & Sec 29 pp. `181–182` (`1/2–2/2`) | — *(pure `R`)* |
| `H2-ENV-02` | Pinned toolchains, locks & reproducible profile | `MIXED (R + X)` | `R L02; X` | `L02` pp. `13–18` (`1/6–6/6`, esp. p. `15` `3/6` Environment subsystem) | Pins ESP-IDF v6.1, Go, and Web toolchains/lockfiles (`firmware/esp-idf-version.txt`, `.go-version`, `go.mod`), using Docker/devcontainers only where appropriate. |
| `H2-ENV-03` | Verified standard bootstrap/start/test/check CLI | `REFERENCE` | `R L02/L06` | `L02` pp. `15–16` (`3/6–4/6`); `L06` pp. `44–45` (`4/7–5/7`) | — *(pure `R`; requires every documented command in `AGENTS.md` to exist and document side effects)* |
| `H2-ENV-04` | Pre-edit baseline check & scope-locked repair | `MIXED (R + X)` | `R L06, START; X` | `L06` pp. `41–47` (`1/7–7/7`); `START` Sec 27 p. `174` (`1/2` step 7); `ADV` Sec 33 p. `188` (`1/3` step 7) | Blocks work on relevant baseline failure and forbids fixing out-of-allowlist baseline defects without a separate authorized Issue. |
| `H2-ENV-05` | Dev/test/prod & hardware safety isolation | `MIXED (X + R)` | `X; R ADV 211` | `ADV` Sec 49 `SECURITY.md` p. `211` (`1/1` External Actions & Sandbox) | Prevents bootstrap/verification from deploying, flashing ESP32, transmitting RF, touching production DB, or auto-installing unauthorized tools. |

### 2.4 State (`H2-STA-01..06`)

| H2 ID | Topic | Source Class | SPEC Source Ref | Exact PDF Sections & Physical Pages (Printed Labels) | `PROJECT_EXTENSION (X)` Rationale / Adaptation |
|---|---|---|---|---|---|
| `H2-STA-01` | Versioned machine-readable feature surface | `REFERENCE` | `R L07/L08, MIN 168–170` | `L07` pp. `50–52` (`3/7–5/7`); `L08` pp. `55–60` (`1/6–6/6`, esp. pp. `57–58` `3/6–4/6`); `MIN` Sec 26 pp. `168–170` (`3/8–5/8`) | — *(pure `R`)* |
| `H2-STA-02` | `WIP=1` per execution & controlled `blocked` | `MIXED (R + X)` | `R L07/L08, START; X` | `L07` pp. `48–54` (`1/7–7/7`); `L08` pp. `56–59` (`2/6–5/6`); `START` Sec 27 p. `174` (`1/2` steps 8–9) | Scopes `WIP=1` per execution/active plan (without banning separately authorized parallel product Issues) and requires documented authorization for `blocked` transitions. |
| `H2-STA-03` | Trusted verifier gating & revision-bound `passing` | `MIXED (R + X)` | `R L08 57–58; X revision handling` | `L08` pp. `57–58` (`3/6–4/6` Pass-state gating) | Coursebook defines `passing` as irreversible (`p. 57`); project extension binds current `passing` validity to exact candidate revision/SHA so regressions invalidate current status while preserving immutable history. |
| `H2-STA-04` | Plan lifecycle, durable progress & handoff | `REFERENCE` | `R L05, L12, ADV 197–203` | `L05` pp. `33–40` (`1/8–8/8`); `L12` pp. `83–90` (`1/8–8/8`, esp. pp. `84–87` `2/8–5/8`); `ADV` Sec 38–40 & 43 pp. `197–199`, `202–203` (`1/1`, `1/1`, `1/1`, `1/2–2/2`) | — *(pure `R`)* |
| `H2-STA-05` | Atomic checkpoints, isolation & non-destructive recovery | `MIXED (R + X)` | `R L03/L05/L12; X` | `L03` p. `23` (`5/7` ACID); `L05` p. `37` (`5/8` Git commits); `L12` p. `85` (`3/8` Session integrity) | Forbids unauthorized destructive resets/merges during crash recovery; preserves incomplete work in isolated recovery state marked `PARTIAL`/`BLOCKED`. |
| `H2-STA-06` | Single source of truth per state domain | `MIXED (X + R)` | `X; R L03/L08` | `L03` p. `21` (`3/7` System of Record); `L08` p. `57` (`3/6` Single source of truth) | Assigns strict single-writer ownership across Issues (scope/backlog), feature evidence, and Host runtime journal to eliminate uncontrolled bidirectional sync. |

### 2.5 Feedback (`H2-FBK-01..11`)

| H2 ID | Topic | Source Class | SPEC Source Ref | Exact PDF Sections & Physical Pages (Printed Labels) | `PROJECT_EXTENSION (X)` Rationale / Adaptation |
|---|---|---|---|---|---|
| `H2-FBK-01` | Impact-selected checks & no-skip acceptance matrix | `MIXED (R + X)` | `R L02/L09/L10; X` | `L02` p. `16` (`4/6`); `L09` pp. `62, 65` (`2/7, 5/7`); `L10` pp. `68–74` (`1/7–7/7`) | Selects checks by domain/diff impact and approved acceptance matrix across firmware, Go, Web, and infra while banning skipped required tests to claim PASS. |
| `H2-FBK-02` | Deterministic Host receipts & anti-forgery | `MIXED (X + R)` | `X; R L09` | `L09` pp. `64–66` (`4/7–6/7` Externalized judgment & runtime signals) | Enforces Host-collected receipts (command identity, candidate SHA/diff, toolchain, exit status, log SHA-256) and blocks Worker self-reported or stale/forged evidence. |
| `H2-FBK-03` | Independent delivery evaluation & revision invalidation | `MIXED (R + X)` | `R L09/L11, MIN 171–172; X` | `L09` pp. `63–64` (`3/7–4/7`); `L11` pp. `76–81` (`2/8–7/8`); `MIN` Sec 26 pp. `171–172` (`6/8–7/8`) | Requires frozen candidate evaluation, strict non-mutation by Auditor, evidence-backed rubric verdict, and invalidation of stale audit results when affected code changes. |
| `H2-FBK-04` | Promote recurring review findings to mechanical checks | `REFERENCE` | `R L10, SOP 218–219` | `L10` pp. `70–73` (`3/7–6/7` Boundary rules, Review Feedback Promotion, Agent-Oriented Error Messages); `SOP` Sec 54 pp. `218–219` (`1/2–2/2`) | — *(pure `R`; applied with negative fixtures per domain rather than shallow grep checks)* |
| `H2-FBK-05` | Lifecycle/E2E verification & HW/security separation | `MIXED (R + X)` | `R L09/L10/L12; X` | `L09` pp. `63–66` (`3/7–6/7`); `L10` pp. `68–73` (`1/7–6/7`); `L12` pp. `84–85` (`2/8–3/8`) | Prevents unit/simulation/CI results from being equated to HIL, RF/timing, or production security verification (`NOT_VERIFIED` if hardware bench absent). |
| `H2-FBK-06` | Redacted runtime/process observability | `MIXED (R + X)` | `R L11, SOP 220–221; X` | `L11` pp. `75–82` (`1/8–8/8`, esp. pp. `78–79` `4/8–5/8`); `SOP` Sec 55 pp. `220–221` (`1/2–2/2`) | Reuses existing monorepo collectors (UART/radio/MQTT/DB/Go/UI + Host logs), enforces provenance and secret redaction, and makes full OpenTelemetry optional. |
| `H2-FBK-07` | Quality score, tech debt & separate rubric | `REFERENCE` | `R L12, MIN 171–173, ADV 199/207–208` | `L12` p. `87` (`5/8`); `MIN` Sec 26 pp. `171–173` (`6/8–8/8`); `ADV` Sec 40 p. `199` (`1/1`) & Sec 47 pp. `207–208` (`1/2–2/2`) | — *(pure `R`; SPEC §7.3 adds `NOT_VERIFIED` grade and forbids averaging away blocking failures)* |
| `H2-FBK-08` | Controlled benchmark, attribution & simplification | `MIXED (R + X)` | `R L01/L02/L04/L12; X` | `L01` pp. `9–12` (`3/6–6/6`); `L02` pp. `15–18` (`3/6–6/6`); `L04` pp. `30–32` (`5/7–7/7`); `L12` pp. `88–90` (`6/8–8/8`) | Requires matched baseline/candidate constants, failure attribution, and strict protection preventing simplification from removing safety/security controls. |
| `H2-FBK-09` | Bounded diagnostic/repair loops & graph gating | `MIXED (R + X)` | `R L13/L14; X` | `L13` pp. `91–112` (`1/22–22/22`); `L14` pp. `113–132` (`1/20–20/20`) | Requires explicit external retry/timeout/budget stop conditions and permits graphs only when measurably justified and Owner-approved. |
| `H2-FBK-10` | Controlled Harness meta-improvement ratchet | `MIXED (R + X)` | `R L01/L02/L13, EXP 104–107; X` | `L01` pp. `9–10` (`3/6–4/6`); `L02` pp. `15–16` (`3/6–4/6`); `L13` pp. `104–107` (`14/22–17/22` Karpathy `autoresearch`) | Adapts `autoresearch`'s ratchet loop without ML `val_bpb`, 5-minute wall clock, or destructive `git reset`, forbidding self-modification of the trusted oracle/evaluator in the same experiment. |
| `H2-FBK-11` | Anti-Goodhart & self-modification drift guards | `MIXED (R + X)` | `R L14 113–128; X` | `L14` pp. `113–128` (`1/20–16/20`, esp. pp. `118–119` `6/20–7/20` Goodhart, Blindness Upward, Anchors) | Protects against metric gaming and drift via frozen holdouts, invariant safety gates, independent evaluation, bounded experiment budgets, and Owner-reviewed promotion (no auto-merge to `main`). |

### 2.6 Cross-Cutting Governance (`H2-GOV-01..03`)

| H2 ID | Topic | Source Class | SPEC Source Ref | Exact PDF Sections & Physical Pages (Printed Labels) | `PROJECT_EXTENSION (X)` Rationale / Adaptation |
|---|---|---|---|---|---|
| `H2-GOV-01` | End-to-end delivery flow & G0–G6 continuity | `MIXED (X + R)` | `X; R L07/L09` | `L07` pp. `49–53` (`2/7–6/7`); `L09` pp. `64–66` (`4/7–6/7`) | Preserves `Issue → branch → implement → trusted verify → independent audit → post-audit check → Draft PR → human review` and existing G0–G6 semantics until migration is approved. |
| `H2-GOV-02` | Versioned SPEC/plan, RTM & rollback control | `MIXED (X + R)` | `X; R L03/L12` | `L03` pp. `21–24` (`3/7–6/7`); `L12` pp. `84–88` (`2/8–6/8`) | Separates `proposed` vs `approved` vs `verified` states, requires full Requirement Traceability Matrix (RTM), and mandates controlled changes/rollback. |
| `H2-GOV-03` | Fresh-session, clean-handoff & human sign-off | `MIXED (R + X)` | `R L03/L05/L12/START; X` | `L03` pp. `20–21` (`2/7–3/7`); `L05` pp. `34–37` (`2/8–5/8`); `L12` pp. `84–87` (`2/8–5/8`); `START` Sec 29 p. `182` (`2/2`) | Couples course fresh-session/clean-handoff checks with mandatory human approval for RF, security/crypto, contracts, destructive actions, and production operations. |

### 2.7 Orchestration — Control Plane (`H2-ORC-01..08`)

| H2 ID | Topic | Source Class | SPEC Source Ref | Exact PDF Sections & Physical Pages (Printed Labels) | `PROJECT_EXTENSION (X)` Rationale / Adaptation |
|---|---|---|---|---|---|
| `H2-ORC-01` | Logical Orchestrator control-plane contract | `MIXED (R + X)` | `R L13/L14; X role contract` | `L13` pp. `97–103` (`7/22–13/22`); `L14` pp. `114–125` (`2/20–13/20`) | Assigns admission, routing, lifecycle, handoff, budget, retry, and escalation to a logical Orchestrator (reusing Coordinator/Host) while barring self-approval of scope or verdict. |
| `H2-ORC-02` | Role separation & fresh-context Checker | `REFERENCE` | `R L09/L11/L14, EXP 80–81` | `L09` p. `64` (`4/7`); `L11` pp. `80–81` (`6/8–7/8` Anthropic DAW case); `L14` p. `123` (`11/20` fresh verify context) | — *(pure `R`; SPEC §6.4 clarifies cross-model evaluation is optional and does not replace isolation)* |
| `H2-ORC-03` | Bounded multi-round Maker-Checker loop | `MIXED (R + X)` | `R LAB 156–158; X` | `LAB` Sec 23 `Project 07` pp. `156–158` (`4/6–6/6` Exp 3 Maker-Checker Loop) | Operationalizes Project 07's 5-round lab with external round state, immutable candidate per round, structured feedback, and bounded termination (>=5-round pilot, not forced on routine Issues). |
| `H2-ORC-04` | Structured 6-dimension rubric & calibration | `MIXED (R + X)` | `R MIN 171–172, L11; X` | `L11` pp. `79, 81` (`5/8, 7/8`); `MIN` Sec 26 pp. `171–172` (`6/8–7/8` `evaluator-rubric.md`) | Defines machine-readable 6-dimension `0–2` schema (`ACCEPT`/`REVISE`/`BLOCK`), explicit hard gates independent of numeric score, and 3–5 round human calibration against held-out cases. |
| `H2-ORC-05` | Persistent run contract & restart reconciliation | `MIXED (R + X)` | `R L05/L13/L14; X` | `L05` pp. `34–37` (`2/8–5/8`); `L13` p. `102` (`12/22`); `L14` p. `125` (`13/20` checkpoints) | Adds crash/restart reconciliation, duplicate-dispatch prevention, stale-receipt rejection, and idempotent side-effect safety. |
| `H2-ORC-06` | Pattern evaluation & conditional dynamic graph | `MIXED (R + X)` | `R L14 120–128; X` | `L14` pp. `120–128` (`8/20–16/20` Anthropic patterns, workflow vs. agent, five criteria) | Evaluates standard patterns while gating dynamic graph/fan-out on measured justification and Owner approval (`N/A` allowed only for extended graph, never core orchestration). |
| `H2-ORC-07` | Orchestration tax & review-bandwidth cap | `MIXED (R + X)` | `R L14 127–129; X` | `L14` pp. `127–129` (`15/20–17/20` Orchestration Tax, "You are the GIL") | Requires measuring coordination/review/conflict/token/defect overhead and capping concurrency to human review capacity. |
| `H2-ORC-08` | Level 5 Fleet Orchestration & safe deferral | `MIXED (R + X)` | `R L13 110; X` | `L13` p. `110` (`20/22` The Maturity Ladder Level 5) | Frames Level 5 Fleet as a conditional target requiring worktree isolation, ownership locks, versioned shared state, deterministic fan-in, and serialized integration approval—or Owner-approved deferral. |

---

## 3. Complete Mapping of 11/11 Migration Phases (`P00–P10`, [HARNESS_MASTER_PLAN.md](../../harness/HARNESS_MASTER_PLAN.md))

| Phase | Workstream | Owned / Rechecked H2 Scope | Primary PDF Sections & Physical Pages (Printed Labels) | Purpose of Each Lookup |
|---|---|---|---|---|
| `P00` | Specification & Planning | `H2-GOV-02` (seed), all 45 IDs defined | Whole TOC pp. `1–3`; `L01–L14` pp. `7–132`; `LAB` pp. `135–163`; `MIN` pp. `164–173`; `START` pp. `174–175, 181–184`; `ADV` pp. `185–212`; `SOP` pp. `213–221` | Baseline design synthesis establishing the five-subsystem architecture, 45 `H2-*` requirements, Minimal/Advanced target mapping, and `OD-01..10` gates (completed design baseline under Issue #413; reference indexing under Issue #415). |
| `P01` | Independent As-is Audit & Baseline | `H2-GOV-02` (+ inventory of all `45` IDs, `OD-06`, `OD-09/10` inputs) | `L01` pp. `7–12` (`1/6–6/6` failure attribution); `L02` pp. `13–18` (`1/6–6/6` five-subsystem audit, ablation); `L03` pp. `20–21` (`2/7–3/7` visibility gap, Fresh Session Test); `L04` p. `32` (`7/7` SNR audit); `START` `Method Map` p. `183` (`1/1`); `LAB` `P01` pp. `135–139` (`1/5–5/5` baseline protocol); `ADV` `QUALITY_SCORE.md` pp. `207–208` (`1/2–2/2`) | Structure the read-only as-is inventory, failure-layer attribution, SNR/visibility baseline measurement, and matched benchmark protocol before any Harness edits. |
| `P02` | Instruction & Knowledge Architecture | `H2-INS-01..07` | `L03` pp. `19–25` (`1/7–7/7`); `L04` pp. `26–32` (`1/7–7/7`); `MIN` pp. `166–167` (`1/8–2/8`); `START` `Prompt Calibration` p. `184` (`1/1`); `ADV` `AGENTS.md` pp. `188–190` (`1/3–3/3`), `ARCHITECTURE.md` pp. `191–193` (`1/3–3/3`), `Core Beliefs`/`Design Docs`/`DESIGN.md` pp. `194–196` (`1/1`); `SOP` `Encode Knowledge` pp. `215–216` (`1/2–2/2`), `Layered Domain Architecture` pp. `218–219` (`1/2–2/2`) | Trim root `AGENTS.md` into a concise router (`80–120` lines target), align domain/architecture maps and authority routing, encode unseen repo knowledge, and preserve G0/selective rules without rule loss. |
| `P03` | Initialization, Tools & Environment | `H2-TOL-01..05`, `H2-ENV-01..05` | `L02` p. `15` (`3/6` tool & env subsystems); `L06` pp. `41–47` (`1/7–7/7` dedicated initialization); `MIN` `init.sh` p. `167` (`2/8`); `START` `Startup Flow` pp. `174–175` (`1/2–2/2`) & `Initializer Playbook` pp. `181–182` (`1/2–2/2`); `ADV` `SECURITY.md` p. `211` (`1/1`); `L13` pp. `93, 99–101` (`3/22, 9/22–11/22` Codex/Claude tools) | Separate clean bootstrap/smoke from feature edits, align pinned toolchains and standard startup commands, and design role-specific least-privilege/sandbox/timeout/cleanup guards across Codex and Antigravity. |
| `P04` | Feature State & Session Continuity | `H2-STA-01..06` (incl. `H2-ORC-05` state prep) | `L03` p. `23` (`5/7` ACID state); `L05` pp. `33–40` (`1/8–8/8`); `L07` pp. `48–54` (`1/7–7/7` `WIP=1`, Scope Surface); `L08` pp. `55–60` (`1/6–6/6` feature primitive, pass-state gating); `LAB` `P02` pp. `140–144` (`1/5–5/5`) & `P03` pp. `145–146` (`1/2–2/2`); `MIN` pp. `168–170` (`3/8–5/8`); `ADV` `Active/Completed Plans` & `PLANS.md` pp. `197–198, 202–203` | Establish single-writer state ownership, `WIP=1` execution gating, trusted verifier control of `passing` transitions (with revision binding), atomic checkpoints, and crash-resilient cross-session continuity. |
| `P05` | Verification & Feedback | `H2-FBK-01..05`, `H2-ORC-02`, `H2-ORC-04`, `H2-INS-06` (enforcement), `H2-ENV-03` (check) | `L09` pp. `61–67` (`1/7–7/7` three-layer termination, worker/checker split); `L10` pp. `68–74` (`1/7–7/7` E2E & review-feedback promotion); `L11` pp. `76–81` (`2/8–7/8` DAW case & scoring); `LAB` `P04` pp. `147–148` (`1/2–2/2`) & `P05` pp. `149–150` (`1/2–2/2`); `MIN` `evaluator-rubric.md` pp. `171–172` (`6/8–7/8`); `SOP` `Layered Domain Architecture` pp. `218–219` (`1/2–2/2`) | Build the impact-based check interface, mechanical boundary guardrails with actionable errors, Host receipt verification, independent fresh-context audit, and 6-dimension `0–2` rubric calibrated against human reviews. |
| `P06` | Observability & Clean Handoff | `H2-FBK-06`, `H2-GOV-03` | `L11` pp. `75–82` (`1/8–8/8` runtime & process observability); `L12` pp. `83–90` (`1/8–8/8` clean state, dual-mode cleanup); `LAB` `P06` pp. `151–152` (`1/2–2/2`); `MIN` `clean-state-checklist.md` p. `170` (`5/8`); `SOP` `Chrome DevTools` pp. `213–214` (`1/2–2/2`) & `Observability Feedback Loop` pp. `220–221` (`1/2–2/2`) | Instrument redacted runtime/process signals for repeatable golden journeys and failure attribution, enforce clean session exit/cleanup idempotence, and verify 5/5 Fresh Session Test + restart resume. |
| `P07` | Advanced Pack Integration | `H2-FBK-07`, recheck `H2-INS-06/07`, `H2-STA-04/06`, `H2-GOV-02` | `ADV` pp. `185–212` (Pack overview `185–187`, `AGENTS`/`ARCHITECTURE`/`DESIGN` `188–196`, `exec-plans`/`tech-debt` `197–199`, `FRONTEND`/`db-schema`/`PLANS`/`PRODUCT_SENSE`/`product-specs` `200–206`, `QUALITY_SCORE`/`RELIABILITY`/`SECURITY` `207–211`, `Repo Template` `212`); `MIN` `quality-document.md` pp. `172–173` (`7/8–8/8`); `SOP` pp. `213–221` | Map or establish logical Advanced Pack surfaces (without duplicating canonical ADRs/contracts), operationalize domain/layer `QUALITY_SCORE` and tech-debt tracking, and verify link/freshness hygiene. |
| `P08` | Orchestrator, Multi-Round Maker-Checker & Improvement Pilot | `H2-FBK-09/10/11`, `H2-ORC-01/03/05/07`, integrated `H2-ORC-02/04` & `H2-GOV-01` | `L13` pp. `91–112` (`1/22–22/22`, esp. pp. `97–107` six primitives & `autoresearch` ratchet); `L14` pp. `113–129` (`1/20–17/20`, esp. pp. `118–119` Goodhart/anchors & `127–129` Orchestration Tax); `L11` `DAW` pp. `80–81` (`6/8–7/8`); `LAB` `P07` pp. `153–158` (`1/6–6/6` goal/timer/maker-checker) | Implement logical Orchestrator control plane, run >=5-round Maker-Checker pilot with bounded stops & crash recovery, execute controlled `KEEP`/`REJECT` meta-improvement experiment with anti-Goodhart holdouts, and measure orchestration tax. |
| `P09` | Pattern Assessment & Advanced Graph / Fleet Pilot *(conditional)* | `H2-ORC-06/08`, graph part of `H2-FBK-09`, recheck `H2-ORC-07` | `L13` p. `110` (`20/22` Maturity Ladder L1–L5) & p. `111` (`21/22` Claude Code Workflows ref); `L14` pp. `120–129` (`8/20–17/20` workflow vs. agent, five criteria, orchestration tax); `LAB` `P08` pp. `159–163` (`1/5–5/5` explicit graph, fan-out/fan-in, rollback, HITL); `REF-ORC` p. `177` (`2/5` `Symphony` & parallel Claudes) | Evaluate the 5 graph criteria and orchestration patterns; either pilot isolated parallel worktrees/rollback/HITL nodes with conflict/fan-in verification or record Owner-approved deferral of L4/L5 Fleet. |
| `P10` | Independent System Acceptance & Simplification | `H2-FBK-08`, final verification of all `45` `H2-*` IDs | `L01` pp. `7–12` (`1/6–6/6`); `L02` pp. `15–18` (`3/6–6/6` ablation); `L04` pp. `30–32` (`5/7–7/7`); `L12` pp. `88–90` (`6/8–8/8` periodic simplification); `MIN` p. `173` (`8/8` simplification tie-in); `LAB` `P01–P06` pp. `135–152` | Conduct final independent system audit against the P01 baseline and RTM, verify controlled component simplification without guardrail regression, and issue `PASS` / `PASS_WITH_LIMITATIONS` / `FAIL`. |

---

## 4. Topical Quick-Lookup (Core Harness V2 Themes)

| Theme | Exact PDF Sections & Physical Pages (Printed Labels) | When to Load |
|---|---|---|
| **Minimal Pack** | `MIN` Sec 25–26 pp. `164–173` (`1/2–2/2`, `1/8–8/8`); `START` Sec 27, 29–31 pp. `174–175, 181–184`; `LAB` `P01–P02` pp. `135–144` (`1/5–5/5`) | `P01–P04` when establishing root `AGENTS.md`, bootstrap script, feature list, durable progress, and session handoff. |
| **Advanced Pack** | `ADV` Sec 32–50 pp. `185–212`; `SOP` Sec 51–55 pp. `213–221` | `P02`, `P05–P07` when mapping or aligning design/product/plan/debt/quality/reliability/security/frontend surfaces and repo SOPs. |
| **Orchestration** | `L13` pp. `97–103` (`7/22–13/22`); `L14` pp. `114–129` (`2/20–17/20`); `L11` `DAW` pp. `80–81` (`6/8–7/8`); `REF-ORC` pp. `111, 177` (`21/22, 2/5`); `LAB` `P08` pp. `159–163` (`1/5–5/5`) | `P08–P09` when designing logical Orchestrator contracts, pattern selection, orchestration-tax accounting, or conditional graph routing. |
| **Maker-Checker Rubric** | `L09` pp. `64–66` (`4/7–6/7`); `L11` pp. `76–81` (`2/8–7/8`); `MIN` `evaluator-rubric.md` pp. `171–172` (`6/8–7/8`); `LAB` `P05` pp. `149–150` (`1/2–2/2`) & `P07` Exp 3 pp. `156–158` (`4/6–6/6`) | `P05`, `P08`, `P10` when implementing role separation, 6-dimension `0–2` scoring, calibration rounds, and >=5-round Maker-Checker pilots. |
| **Fleet** | `L13` p. `110` (`20/22` Level 5 Fleet Orchestration); `L14` pp. `127–129` (`15/20–17/20` GIL / review bottleneck); `REF-ORC` p. `177` (`2/5` `Symphony` & `Building a C compiler with a team of parallel Claudes`) | `P09` only when assessing conditional L4/L5 readiness, worktree isolation, ownership locks, and integration review capacity. |
| **Controlled Self-Improvement** | `L01` pp. `9–10` (`3/6–4/6` Diagnostic Loop); `L02` pp. `15–16` (`3/6–4/6` Ablation); `L12` pp. `88–90` (`6/8–8/8` Simplification); `MIN` p. `173` (`8/8`); `L13` pp. `104–107` (`14/22–17/22` `autoresearch`); `L14` pp. `118–119` (`6/20–7/20` Goodhart & Anchors) | `P08`, `P10` when running fixed-budget `KEEP`/`REJECT` harness experiments or periodic simplification without weakening safety gates. |
