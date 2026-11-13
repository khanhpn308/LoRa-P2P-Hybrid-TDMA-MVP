# CCARS v1.4 — C Codebase Organization & Structural Refactoring Profile

| Field | Value |
|---|---|
| Status | DRAFT — repository adoption via Issue #367; mandatory Graph-First policy when activated; human review and local capability verification required |
| Repository | khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP |
| Intended path | docs/development/c-clean-code-refactoring-standard.md |
| Reviewed source baseline | 18d9eedd2b2cdc5a0b8ad2f886e491c587126a3b (GitHub main rechecked for this revision) |
| Supersedes | Proposed CCARS v1.0, v1.1, v1.2, and adopted v1.3 upon adoption |
| Purpose | Organize accepted C code without changing behavior; not a second coding-quality standard |

## 1. Purpose and scope

C Coding Standard V2 is the existing technical acceptance standard. CCARS is a structural organization profile for code that has already been accepted into the codebase. Its objectives are readability, discoverability, coherent module boundaries, maintainability and extensibility.

**Input premise (Owner clarification):** code admitted to the accepted codebase must have passed all applicable C Standard V2 Rule IDs through the existing acceptance process. Treat the accepted baseline as the starting point of structural refactoring. This policy premise is not proof that any particular historical commit actually passed; do not fabricate or retroactively assert test evidence.

CCARS MUST NOT initiate a second full C Standard V2 audit, re-certify unchanged code, repeat CERT C checks, or re-evaluate the correctness of existing algorithms, radio parameters, memory safety, security, RTOS or protocol decisions as its primary task. Existing technical standards remain authoritative for changes. If a potential defect or missing/conflicting evidence is encountered, record it separately and refer it to the existing review process. Do not fix it in a structural refactoring patch without separate authorization.

**Core distinction:** a compliant function can still be placed in an inappropriate file or mixed with unrelated responsibilities. CCARS addresses placement, grouping, ownership and dependency structure, not whether the function's original algorithm meets technical quality rules.

In scope: standardized ESP-IDF codebase organization across the three-tier component hierarchy (Application Entrypoint, Application-Specific Components, Shared Components), file and folder organization, entrypoint responsibilities, symbol placement, module cohesion, private/public boundaries, unnecessary structural coupling, discoverability, mechanical extraction, narrowly justified internal abstractions, and build-registration changes required by relocation.

Out of scope: feature development, algorithm optimization, bug fixes, protocol/security redesign, changing RF parameters, changing persistence or concurrency behavior, migrating the toolchain, enforcing new coding conventions retroactively, and replacing the existing Agent Harness or CI framework.

## 2. Authority and integration

Follow the current `AGENTS.md`, approved Issue scope, C Coding Standard V2, approved requirements/ADRs and contracts, exact SDK version, and existing Native Fast Lane/Host gates. This document does not change the meaning of any existing Rule ID. The existing Host decides applicable C Standard V2 rules for the actual diff under Owner #137; CCARS does not duplicate, bypass or waive those checks. Do not load the entire C Standard V2 or assign PASS on unchanged rules merely because the baseline was accepted.

Use the `REF-*` IDs below as supplemental structural review identifiers. They are not new C Standard V2 compliance IDs. The existing deterministic Host at the reviewed baseline only registers C and Go standard groups: do not submit REF IDs to that selector until an explicit, reviewed integration supports them. For adoption, link this profile in the scoped Issue/Agent instructions and record REF findings separately; reuse existing Host rule selection and quality gates for the actual diff. A new selector, MCP server or quality-gate framework is not required for the profile to guide structural review. Any future automatic enforcement must be separately approved and tested as a control-policy change.

Architecture follows approved current decisions, not historical repository names. At the reviewed baseline, ADR `0004-pure-cad-csma-ca-mac.md` (Owner #273) supersedes Hybrid TDMA with Pure CAD + Random Backoff and Gateway Continuous RX. Some AGENTS/standard/routing language remained historical. Do not introduce TDMA/Beacon components merely to organize code. If an authority conflict affects the proposed extraction, STOP_AND_REPORT under existing rules; do not reconcile architecture in the cleanup patch. The separate architecture reconciliation and runtime hardening backlog remains separate from CCARS's purpose.

## 3. Structural rules

MUST/MUST NOT describe mandatory structural rules after adoption; SHOULD is a strong default with documented exceptions. Each finding should name the relevant rule and source location. Verification here means structural review, not re-certification of pre-existing code.

| Rule ID | Structural directive | Acceptance evidence |
|---|---|---|
| REF-001 | Keep application `main/` focused strictly on application entrypoint, composition and bootstrap. The `main/` directory MUST contain only `main.c`, `CMakeLists.txt`, and entrypoint configuration files (e.g. `Kconfig.projbuild`). `main.c` MUST contain only `app_main()` and minimal bootstrap logic; it MUST NOT contain implementation of subsystems. Subsystem implementations belong to dedicated application-specific or shared components. | Before/after entrypoint, bootstrap logic verification, and responsibility map. |
| REF-002 | Organize components according to the ESP-IDF three-tier architecture: (1) Application entrypoint (`firmware/<app>/main/`); (2) Application-specific components (`firmware/sensor_node/components/` and `firmware/gateway_master/components/`); (3) Shared/reusable components (`firmware/components/`). Functions and data within a component MUST be grouped by cohesive responsibility, ownership, and hidden design decisions. A component MAY contain multiple `.c`/`.h` files sharing a cohesive responsibility domain; do NOT dogmatically enforce 'one source file = one component' or create unnecessary micro-components. | Target component/module rationale, component boundary, and file map. |
| REF-003 | Every moved function/type/state MUST have one clear owner. Identify callers, symbol visibility, data dependencies, attributes, callback registration and lifecycle needed to relocate it safely. | Symbol-to-owner mapping with callers and move constraints. |
| REF-004 | Keep public interfaces small and meaningful. Do not promote private symbols to public merely to make a move compile. Keep related private helpers with their owner and use component-private declarations when required. | Public/private API and external-symbol delta. |
| REF-005 | Preserve or improve dependency direction across the component hierarchy: (1) Shared components (`firmware/components/`) MUST NOT depend on application-specific components or application `main/`; (2) Application-specific components (`firmware/<app>/components/`) MAY depend on shared components or sibling application components, but MUST NOT depend on application `main/`; (3) Application `main/` orchestrates and depends on application-specific and shared components, never vice-versa. Avoid new unjustified project-owned dependency cycles; distinguish include, component-link (`CMakeLists.txt` `REQUIRES`/`PRIV_REQUIRES`), and runtime-call graphs. | Before/after direct dependencies, component registration requirements, and any known cycles or unresolved indirect edges. |
| REF-006 | Preserve behavior and existing contracts. Do not alter algorithms, values, side effects, call order, failure semantics, execution context, resource lifetime, persistence, or approved timing/security behavior under the guise of organization. | Invariants, reviewed diff and applicable regression evidence. |
| REF-007 | Use consistent file layout and meaningful function grouping. Review complexity indicators as signals; do not split or wrap code mechanically to satisfy a metric. | Navigable file layout and qualitative justification. |
| REF-008 | Make incremental, cohesive extractions. Separate formatting-only changes, mechanical moves, structural changes and defect fixes. Prefer minimal diffs that make moved code recognizable. | Small scoped patch with movement traceability. |
| REF-009 | Document the resulting module/file map, changed symbol ownership, dependency and build-registration changes, and remaining structural issues. Do not claim full graph coverage when only direct edges are known. | Before/after report and precise limitations. |
| REF-010 | Accept a refactoring only when structural improvement is demonstrable and existing verification applicable to the changed scope has passed or is handled through the existing authorized review process. No CCARS-specific second technical certification. | Structural review + existing scoped Host/PR evidence; unresolved mandatory checks block acceptance. |
| REF-011 | MUST use CodeGraph as the primary structural discovery mechanism, before exploratory source reads. MUST establish index identity, freshness and relevant coverage; MUST NOT substitute a bulk LLM file scan when graph access is unavailable. See §3.1. | CodeGraph preflight/query receipts, scoped symbol/impact maps, recorded targeted-read exceptions and before/after graph evidence. |

## 3.1 Mandatory Graph-First discovery (REF-011)

**Scope:** every CCARS structural inventory, plan, refactor and post-refactor structural verification. This is a stricter task-specific requirement than the repository's general optional CodeGraph guidance. Ordinary coding tasks remain governed by existing policy. CodeGraph is a discovery/indexing tool, not a new technical compliance checker, authorization mechanism or proof of runtime behavior.

### Graph-first operating rules

| Rule | Required behavior |
|---|---|
| CG-01 — Preflight | Confirm installed CodeGraph product/version, actual tool availability, exact repository/worktree root, baseline HEAD and source fingerprint or equivalent candidate identity. Verify an initialized, current index for that root and scope; check C/H coverage and representative symbols, not only total node count. A stale, missing, wrong-root or insufficient index blocks affected structural discovery. |
| CG-02 — Inventory | Use indexed file/symbol metadata and focused graph queries first. Inventory component/file boundaries, entrypoints, definitions, callers/callees and relevant dependency relationships in bounded batches. Retain compact structured results outside model context where supported. Do not send the entire graph, repository archive, or all function bodies to the model. |
| CG-03 — Context retrieval | Use `codegraph_explore` as the primary MCP query; use focused metadata/symbol/impact tools if actually exposed. Ask one question about one subsystem or responsibility group at a time; narrow results when truncated. Use the returned verbatim source as already-read context; do not repeat identical grep/read requests. |
| CG-04 — Impact before move | For every MOVE/SPLIT/GROUP, inspect definition, references, callers/callees, state ownership and affected modules. Record unresolved/indirect edges, existing API, linkage and build boundaries. Unknown callers or incomplete coverage that affect safe relocation => DEFER/BLOCKED for that candidate. |
| CG-05 — Targeted source exceptions | Direct reads are allowed for mandatory authority/configuration files, CMake/Kconfig/build inputs, exact edit spans, diff review, and material graph gaps such as macro expansion, conditional compilation, function-pointer registration or linker/RTC/ISR attributes. State the reason and scope. Never use recursive bulk source reading as a substitute for an unavailable graph. Do not invent source or assume graph absence proves no caller. |
| CG-06 — Freshness after edits | Revalidate the exact candidate/worktree index after each cohesive patch and before graph-based acceptance. Use supported sync/reindex only when authorized; confirm changed/new/deleted paths and representative relocated symbols are reflected. Repeat affected impact queries, not the entire inventory. If a graph cannot be brought current, stop graph-based acceptance. |
| CG-07 — Budget | Keep the Coordinator context to concise inventory, ownership/impact summary, proposed changes and receipts. Retrieve complete bodies only for the current extraction and relevant callers. Limit discovery by subsystem and pagination; do not request whole-graph exports into the LLM. Reuse query results only when source identity still matches. |
| CG-08 — Evidence and limits | Record engine/version, tool/operation, root, baseline/candidate identity, scope, query, result summary, unresolved edges, status and direct-read exceptions. CodeGraph results support structural decisions only; existing Host checks, actual source/build configuration and regression tests remain authoritative for changed code. |

**Failure policy:** if CodeGraph cannot be used in MCP, a verified equivalent CLI of the same approved CodeGraph engine is permitted under Host command policy. No fallback to bulk `read_file`/`grep`/`find`/recursive cat or asking another model to read the full repository. Report `BLOCKED_CODEGRAPH` for graph-dependent discovery; report `DEFER` for individual unresolved moves. No automatic install, global config edits, tool upgrades, broad reindex or scope expansion without authorization. Initialization may write derived index/config/ignore state; keep index outside tracked source and comply with Issue scope and secret exclusions. Do not index secrets, unrelated private workspaces, generated build output, managed dependencies or SDK caches unnecessarily; verify actual exclusion configuration and coverage.

**Tool capability contract:** the upstream `colbymchenry/codegraph` MCP normally exposes `codegraph_explore` only. Additional tools (`codegraph_status`, `codegraph_files`, `codegraph_search`, `codegraph_node`, `codegraph_callers`, `codegraph_callees`, `codegraph_impact`) can be exposed by supported configuration or accessed by approved equivalent CLI; inspect the installed tool schema rather than inventing names or arguments. Use `codegraph status`, `codegraph explore`, `codegraph query`, `codegraph callers`, `codegraph callees`, `codegraph impact` and `codegraph sync` only if verified against the installed version and the authorized root. An index can contain unresolved edges: C macros, conditional builds, function pointers and external/precompiled code may not be fully resolved. Inspect actual source/CMake where required; distinguish include graph, link dependencies and runtime calls.

**Enforcement:** REF-011 and CG-01..08 are CCARS profile directives, not registered C Standard V2 IDs. The Agent must fail closed as instructed. Hard enforcement requires trusted Host observation of real graph operations, index/scope checks and receipts before edits; a prompt or model self-attestation is insufficient. Do not change existing Host rule routing without separate reviewed scope. An independent Auditor may use a frozen graph evidence summary and exact diff; do not weaken its read-only/no-shell/MCP permission boundary to satisfy a discovery requirement. If the Auditor itself is tasked with graph-dependent structural verification, supply a trusted read-only graph service/Host evidence or report the missing capability.

## 4. Organization conventions

### 4.1 Entry point

The `main/` directory of each application (`firmware/sensor_node/main/`, `firmware/gateway_master/main/`) serves strictly as the application entry point and composition root.

Key architectural requirements:
- The `main/` directory MUST contain only `main.c`, `CMakeLists.txt`, and entrypoint configuration files required for the application entry point (such as `Kconfig.projbuild`). It MUST NOT house subsystem implementations.
- `main.c` MUST contain only `app_main()` and minimal bootstrap logic (such as essential hardware initialization, NVS flash init, system event loops, and invoking application coordinators).
- Subsystem logic (such as UI screens, radio transactions, CAD/backoff algorithms, WAL storage, and packet routing) MUST NOT be implemented in `main.c`; it must be relocated to dedicated application-specific components or shared components.

Target pattern (illustrative; use existing APIs and preserve lifecycle):

```c
#include "esp_err.h"
#include "esp_log.h"
#include "node_app.h"

void app_main(void)
{
    ESP_ERROR_CHECK(node_app_init());
    node_app_run();
}
```

`node_app_run` is a proposed example, not an existing API. An error-returning application launcher may use the existing error policy; do not introduce aborts, tasks or changed return behavior simply to achieve the example. `app_main()` may call several cohesive bootstrap functions. One function definition in `main.c` is the preferred organization, not an ESP-IDF requirement, but all logic beyond bootstrap orchestration belongs in components.

### 4.2 Three-tier component organization and placement

ESP-IDF codebase architecture is structured into three distinct tiers:

1. **Application Entrypoint (`firmware/<app>/main/`):**
   - Contains only `main.c`, `CMakeLists.txt`, and entrypoint configuration.
   - Responsible solely for `app_main()` and minimal bootstrap orchestration.
   - Example paths: `firmware/sensor_node/main/`, `firmware/gateway_master/main/`.

2. **Application-Specific Components (`firmware/<app>/components/<component_name>/`):**
   - Components owned by and dedicated to a single application.
   - Located at:
     - `firmware/sensor_node/components/`
     - `firmware/gateway_master/components/`
   - ESP-IDF automatically discovers components in the project's own `components/` directory (`${CMAKE_SOURCE_DIR}/components`).
   - Houses application-specific subsystems such as application UI (`node_ui`), application radio state machines/CAD backoff (`node_cad_backoff`), write-ahead log (`gateway_wal`), or downlink dispatchers.

3. **Shared / Reusable Components (`firmware/components/<component_name>/`):**
   - Components shared across multiple applications (e.g. `firmware/components/lora_mac/`, `firmware/components/sx1276_driver/`, `firmware/components/oled_ssd1306/`, `firmware/components/airtime_policy/`, `firmware/components/session_key_store/`, `firmware/components/button_driver/`).
   - Discovered by application build systems via `set(EXTRA_COMPONENT_DIRS "../components")` in project-level `CMakeLists.txt`.
   - Shared components MUST NOT depend on application-specific components or application `main/`.

### 4.3 Component structure and multi-file flexibility

- **Cohesive Subsystem Units:** A component represents a coherent functional domain or subsystem, NOT an arbitrary 1:1 mapping to a single source file. A component MAY contain multiple `.c` and `.h` files that collaborate on the same responsibility.
- **No Dogmatic 1-File = 1-Component Rule:** Do NOT mechanically create an isolated ESP-IDF component for every single source file. For example, a UI component may consist of `node_ui.c`, `node_ui_screens.c`, and public header `include/node_ui.h`; a radio manager component may contain `node_radio_cad.c`, `node_radio_backoff.c`, and public header `include/node_radio.h`. Creating micro-components for single helper files creates unnecessary CMake overhead and fragments cohesive subsystems.
- **Component Layout:**
  - `CMakeLists.txt`: component registration via `idf_component_register(SRCS ... INCLUDE_DIRS "include" REQUIRES ... PRIV_REQUIRES ...)`.
  - `include/`: public headers exposed to callers outside the component.
  - `src/` (or component root): implementation source files (`.c`) and private/internal headers.
- **Information Hiding & Scope:** Keep internal types, constants, state, and private helpers static within `.c` files or declared in private component headers. Expose only the minimal necessary public API in `include/`.
- **Dependencies:** Use `PRIV_REQUIRES` in `CMakeLists.txt` for dependencies required only by private implementation; use `REQUIRES` only when public headers include headers from another component.

### 4.4 Decide whether to extract

- **Subsystems in `main/` or `main.c`:** MUST be extracted to dedicated application-specific components under `firmware/<app>/components/<name>/`.
- **Cross-application logic:** If logic is genuinely shared between Sensor Node and Gateway Master without coupling to application-specific state, place it in `firmware/components/<name>/`. Do NOT place application-specific logic in shared components.
- **Multi-file vs. New Component:** When a component grows, first split it into multiple cohesive `.c`/`.h` files within that SAME component. Only create a new component when there is a distinct responsibility domain with separate ownership and clean interfaces.
- Extract only if it improves cohesion, owner clarity, dependency direction or discoverability. Keep a function in place if moving it would increase cross-module state, API surface or indirection without a clear benefit. Avoid speculative abstractions and do not deduplicate code whose semantics or constraints differ.

## 5. Structural review indicators

These are review triggers, not quality grades or universal limits. They require Owner approval before mandatory enforcement. Do not retroactively split unrelated code.

| Metric | Trigger | Interpretation |
|---|---|---|
| `main/` directory files | Any file other than `main.c`, `CMakeLists.txt`, entrypoint configs | Violation of entrypoint isolation; move subsystem to an application component. |
| `main.c` function definitions | >1 | Review whether extra definitions are genuine bootstrap helpers. Subsystems must be moved to components. |
| `main.c` SLOC | >50 | Review mixed responsibilities; subsystem implementation leaking into entrypoint. |
| Function SLOC | >50 | Review grouping and responsibility; not a forced split. |
| Cyclomatic complexity | >10 | Optional signal to investigate organization, not to rewrite algorithms. |
| Control nesting | >4 | Optional signal to investigate readability, not to change execution flow. |
| New external symbols | Each addition | Check if moving code unnecessarily widened the interface. |
| New project-owned dependency cycles | No unjustified new cycle | Review dependency delta across component tiers; existing exceptions not silently rewritten. |

SLOC excludes blank/comment-only lines using a documented parser convention; physical line counts are separate. Record tool/version/configuration if metrics are measured. No aggregate clean score. Warnings, heap/stack/flash budgets, latency and technical correctness are not CCARS cleanliness metrics; they remain existing technical checks when relevant to the actual diff.

## 6. Structural workflow (existing Agent Harness)

Default `AUDIT_ONLY` means a structural inventory only; no source edits or technical re-audit. `PLAN_ONLY` proposes moves and boundaries. `REFACTOR` requires the existing OPEN Issue, exact approved paths, isolated workspace and Host authority. `VERIFY` checks structure and applicable regression evidence; no source edits by independent Auditor.

1. Identify accepted baseline, current Issue scope, actual files and applicable current instructions. Reuse existing G0/context/Host selection; do not initiate full re-certification of the baseline.
2. Run REF-011/§3.1 CodeGraph preflight and graph-first inventory; stop if the required graph is unavailable. Inventory responsibilities, component/file boundaries, symbols, callers and state dependencies across the three tiers. Distinguish direct source evidence from inference. Classify each candidate KEEP, MOVE, SPLIT, GROUP or DEFER.
3. Query CodeGraph impact for each candidate move before proposing the smallest cohesive patch. Record target component owner, needed private API, expected dependency changes, preserved invariants and regression tests. Classify risk (R0 cosmetic, R1 mechanical relocation, R2 boundary/state ownership, R3 radio/ISR/timer/security/protocol/persistence/time-sensitive). Defer changes needing separate approval.
4. Apply only authorized changes. Prefer copying/moving existing bodies unchanged; compare with original and explain every nonmechanical change. Update only necessary includes, declarations and build registration (`CMakeLists.txt`). Keep unrelated changes intact.
5. Refresh and re-query the candidate graph for affected symbols; verify structural outcomes and reuse existing scoped Host checks, build/tests/contract/HIL and human review as applicable to the actual changed code. These checks establish that the new candidate has not regressed; they are not a second baseline quality audit. Do not mark a check PASS without execution evidence. Missing required evidence blocks the existing acceptance path.
6. Report baseline/changed files, structural findings resolved, before/after map, API/dependency delta, invariants, actual regression results, deferred technical findings and limitations. Existing Draft PR/human review workflow remains unchanged.

### Minimal report schema

```text
Baseline SHA / Issue / Allowed paths
Mode: AUDIT_ONLY | PLAN_ONLY | REFACTOR | VERIFY
Graph receipt: engine/version | root | source identity | coverage/freshness | operations/results
Finding: REF-ID | file:line | responsibility | evidence
Graph impact / unresolved edges / targeted-read exceptions
Decision: KEEP | MOVE | SPLIT | GROUP | DEFER
Target owner / affected callers / dependency delta
Preserved behavior and relevant state/context constraints
Before/after structure and public interface delta
Regression evidence: actual commands/results or NOT_RUN/NOT_VERIFIED
Deferred technical findings (separate Issue; no hidden fixes)
Structural outcome: IMPROVED | NO_CHANGE | BLOCKED
Existing PR/Host acceptance status (reported independently)
```

## 7. Repository-specific application (source-derived examples)

The earlier static review of baseline `f8f85e0` found 945 physical lines in Node `main.c` and 1,199 in Gateway `main.c`. These counts identify review candidates, not quality failures. The following are organizational examples under the CCARS v1.4 three-tier architecture, not authorized patches or new technical requirements.

### Sensor Node

| Existing source | Candidate disposition | Reason/constraint |
|---|---|---|
| `main.c:345–361` `node_update_oled_unjoined` | MOVE to application component `firmware/sensor_node/components/node_ui` | UI presentation has a coherent owner; preserve OLED Kconfig, init/draw/refresh/deinit sequence. |
| `main.c:827–845` OLED event presentation | GROUP with `node_ui` if separately scoped | Preserve error/log semantics and current event-flow order; do not change driver. |
| `main.c:76–129` radio adapter callbacks | DEFER / candidate application radio adapter | Callback signatures, queue drain and Continuous RX behavior must remain unchanged. Do not reinterpret the name `prod_radio_rx_single`. |
| `main.c:131–344` CAD/Event/ACK routine | DEFER / candidate application component `firmware/sensor_node/components/node_cad_backoff` | Existing `node_arq`, `node_smart_backoff`, `node_v2_join`, `lora_mac` and `airtime_policy` already own relevant responsibilities; do not recreate them. |
| `main.c:31–37` RTC retained state | KEEP until owner/lifetime/placement are reviewed | No storage-class or linker changes as cosmetic cleanup. |
| `main.c:484–945` `app_main()` | SPLIT incrementally into lifecycle helpers after pilot | Preserve boot/wake/join/event/deep-sleep lifecycle; no new perpetual task. |

Preferred pilot: extract only `node_update_oled_unjoined` and necessary declarations/build registration from `firmware/sensor_node/main/main.c` into a dedicated application-specific component at `firmware/sensor_node/components/node_ui/`. Use existing OLED driver from `firmware/components/oled_ssd1306/`. Do not change OLED text, coordinates, calls, errors or caller ordering. No new shared component unless a concrete cross-application reuse need is established.

Target file layout:

```text
firmware/sensor_node/
  CMakeLists.txt
  sdkconfig.defaults
  main/
    CMakeLists.txt
    main.c
  components/
    node_ui/
      CMakeLists.txt
      include/
        node_ui.h
      src/
        node_ui.c
    node_cad_backoff/
      CMakeLists.txt
      include/
        node_cad_backoff.h
      src/
        node_cad_backoff.c
```

### Gateway

Existing registry, downlink callbacks, session persistence, WAL, liveness timers and packet dispatch are candidate ownership groups. Keep shared transport/join/crypto modules in `firmware/components/` as existing owners. Application-specific subsystems such as `gateway_wal` are organized into application-specific components under `firmware/gateway_master/components/gateway_wal/`. Preserve the static RX task, callback/timer contexts and order of persistence/ACK operations. Do not mix any correctness fix, such as a suspected unhandled WAL failure, into structural extraction.

Target file layout:

```text
firmware/gateway_master/
  CMakeLists.txt
  sdkconfig.defaults
  main/
    CMakeLists.txt
    main.c
  components/
    gateway_wal/
      CMakeLists.txt
      include/
        gateway_wal.h
      src/
        gateway_wal.c
```

## 8. Regression verification and runtime boundaries

Use the repository's existing test runners and gates; do not define duplicate QA IDs or an additional test framework. The reviewed baseline pins ESP-IDF `v6.1` and CI builds both `firmware/sensor_node` and `firmware/gateway_master` with `idf.py --version && idf.py build` (ESP32). For a Node-only UI move, select Node build and relevant OLED tests, plus other existing gates required by actual scope. Shared component edits require applicable consumer builds/tests per existing policy. Driver/ISR/timing/security changes require existing additional technical review and verification; do not assume such changes are necessary for organization.

Use the existing MCP read-only/Host/worker boundaries. CCARS is a structural profile, not an authorization mechanism and not a runtime sandbox specification. Runtime hardening, branch protection and architecture reconciliation are separate governance/security work items; this document neither implements nor waives them. Never use a model prompt as a hard security boundary. No direct main edits, flash, auto-merge or unauthorized operations. If safe execution is unavailable, limit to read-only structural analysis and report the blocker.

## 9. Adoption

Project Owner approves profile wording, metrics, mandatory graph policy and Issue scope; verify installed CodeGraph/AGY capability, index scope/freshness and fail-closed behavior before activating the agent; existing firmware CODEOWNERS review affected firmware. Place this document at the intended path via approved docs Issue/PR, reference it in the existing Agent instructions as appropriate, and keep structural findings separate from existing C Standard V2 evidence. If registering REF IDs as automatic Host rules later, use a separately reviewed integration with current indexes/hashes/routing and tests; do not claim automatic enforcement from documentation alone.

Repository adoption: Issue #367 introduces CCARS v1.4, standardizing the three-tier ESP-IDF codebase organization architecture (application entrypoint `main/`, application-specific components `firmware/<app>/components/`, and shared components `firmware/components/`) and synchronizing the project AGY refactor agent. See [Graph-First adoption and local acceptance](ccars-graph-first-adoption.md). CodeGraph version/live AGY tool availability on the operator host remain NOT_VERIFIED until local smoke evidence exists. No build/HIL or hard runtime enforcement claim follows from adoption.

## References

Project baseline: https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/tree/18d9eedd2b2cdc5a0b8ad2f886e491c587126a3b — AGENTS.md, C_CODING_STANDARD_V2.md, approved ADRs, contracts, CMake and source, existing Harness runbooks.

Design rationale: Robert C. Martin, *Clean Architecture*, ch. 26; John Ousterhout, *A Philosophy of Software Design*, 2nd ed., ch. 4–6; James W. Grenning, *Test-Driven Development for Embedded C*; ISO/IEC 25010:2023 maintainability model; ESP-IDF Build System guide. These motivate structural principles, not the proposed numeric thresholds. Technical C compliance remains governed by the existing C Standard V2.

CodeGraph upstream references (capabilities, not proof of local installation): https://github.com/colbymchenry/codegraph/blob/main/site/src/content/docs/reference/mcp-server.md ; https://github.com/colbymchenry/codegraph/blob/main/site/src/content/docs/reference/cli.md ; https://github.com/colbymchenry/codegraph/blob/main/site/src/content/docs/getting-started/your-first-graph.md .
