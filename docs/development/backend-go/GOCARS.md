# GOCARS v2.0 — Go Codebase Architecture & Refactoring Standard

| Metadata | Value |
|---|---|
| Standard ID | `GOCARS-2.0` |
| Status | APPROVED_ON_OWNER_MERGE — effective only after owner approval and merge of the Issue #359 integration PR; otherwise PROPOSED |
| Scope | Structural organization and behavior-preserving refactoring of an integrated Go backend |
| Target repository | `khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP` |
| Primary paths | `backend-go/` |
| Canonical location | `docs/development/backend-go/GOCARS.md` |
| Authority | Supplemental structural profile; Go Backend Engineering Standard V2 remains authoritative for engineering quality |
| Supersedes upon adoption | GOCARS-1.0 and GOCARS-1.1; does not supersede Go Engineering Standard V2 |
| Date | 2026-11-12 |

## 0. Purpose, scope and authority

### 0.1. Mission

An integrated codebase accumulates features, dependencies and implementation decisions through individually reviewed changes. Even when every change has satisfied its applicable engineering rules, the aggregate source layout may become difficult to navigate, understand, maintain and extend. GOCARS addresses this structural problem.

**Mission:** reorganize the existing, engineering-reviewed backend into a cohesive, navigable, maintainable and extensible codebase without changing its externally observable behavior or approved architecture. Reduce accidental structural complexity, not the number of lines, files, functions or packages for its own sake.

**Operating premise:** the integrated source is the accepted baseline of the repository's existing Go engineering review process. GOCARS consumes that baseline; it does not perform a second full-codebase engineering compliance audit, recertify historical changes or establish that every historical runtime scenario was tested. Existing review receipts may be reused for unchanged code. Never manufacture historical PASS evidence.

### 0.2. Division of responsibility

| Responsibility | Go Backend Engineering Standard V2 | GOCARS |
|---|---|---|
| Correctness, security, reliability, Go language/style and technical contracts | Governs | Inherits; does not redefine or reassess wholesale |
| New code and changed behavior | Governs implementation and verification | Not a feature/fix mandate |
| Package/file organization and navigability | Existing architectural constraints remain binding | Primary focus |
| Cohesion, dependency direction, responsibility placement and composition | Existing constraints remain binding | Primary focus, applied to accumulated source |
| Regression verification after structural edits | Existing applicable checks remain mandatory | Defines scoped before/after evidence for the refactor |
| Historical rule compliance of untouched code | Existing review/verification records | Out of scope |

The authoritative Go standard is [`GO_BACKEND_ENGINEERING_STANDARD_V2.md`](GO_BACKEND_ENGINEERING_STANDARD_V2.md), mandated by root `AGENTS.md`. Approved requirements, ADRs and versioned contracts retain their repository-defined authority. GOCARS cannot waive an applicable V2 rule or override the Host, Auditor, Issue allowlist or human review policy. If a structural change conflicts with an approved decision, stop that change and report the conflict; continue independent authorized work where possible.

Normative terms after adoption: **MUST** = required; **MUST NOT** = prohibited; **SHOULD** = default with documented rationale for deviation; **MAY** = optional. These are project-local rules. Approval of this document is separate from activation in the Host/CI and authorization to modify the repository.

### 0.3. In scope and out of scope

| In scope | Out of scope for structural cleanup |
|---|---|
| Package and file responsibility maps | Whole-backend re-audit against all Go V2 Rule IDs |
| Moving existing functions/types into their owning packages | Reimplementing business rules or adding features |
| Thin entry point, composition root and configuration placement | Security hardening, changing credential policies or cryptographic schemes |
| Meaningful file names, coherent grouping, private helper organization | Changing retries, cancellation, timeouts, readiness or failure policy |
| Simplifying internal call graphs and removing proven redundant structure | Changing HTTP/MQTT contracts, SQL semantics, migrations or persistent data |
| Consolidating genuinely equivalent implementations and proven dead code | Dependency/toolchain upgrades, framework migration, microservices |
| Updating imports, internal call sites and associated tests for moves | Re-running unrelated historical audits or hardware/RF verification |

A structural edit that also changes a technical invariant is not a pure refactor. Split it into a separately authorized engineering change. Incidental defects are reported, not opportunistically fixed. Urgent security/safety/data-loss findings must be escalated promptly; this document does not authorize delaying necessary containment.

## 1. Agent operation contract

| ID | Level | Structural rule |
|---|---|---|
| GO-AGT-001 | MUST | Default to `AUDIT_ONLY` without edit authorization. Treat the accepted source as the baseline; audit structure, not historical engineering compliance. Establish Issue/AC, allowed paths, mode and exclusions. |
| GO-AGT-002 | MUST | Before editing, inspect the actual repository/branch/HEAD, working tree, scoped instructions, package graph, source ownership, callers, relevant tests and integration boundaries. Never overwrite unrelated changes. |
| GO-AGT-003 | MUST | Establish affected-target regression baseline using the actual pinned toolchain and existing test commands. Reuse valid evidence for the same SHA/configuration where applicable. Record unavailable checks; do not requalify unrelated code. |
| GO-AGT-004 | MUST | Record structural findings with Rule IDs, path:line, observed structure, maintenance impact, proposed owner/action, affected callers, risk and regression evidence needed. Do not create findings solely because a historical V2 receipt is missing. |
| GO-AGT-005 | MUST | Make the smallest coherent structural change. Separate formatting, mechanical moves/renames, responsibility extraction and any behavior-changing fix. Prefer reviewable diffs. |
| GO-AGT-006 | MUST NOT | Invent requirements, APIs, findings, approvals or results; broaden scope into features, hardening, new dependencies or redesign without authorization. |
| GO-AGT-007 | MUST | Preserve baseline evidence and report regressions, unavailable checks and incidental issues separately. Never report a missing or failing check as PASS. |
| GO-AGT-008 | MUST NOT | Edit directly on `main` or perform unauthorized Git writes, deployment, migrations or destructive operations. Follow the existing repository/Host authorization rules. |
| GO-AGT-009 | MUST | Route R2 architecture changes through existing architecture review and R3 technical changes through separate scoped approval and human review. Structural relocation of sensitive code requires risk assessment; do not treat a move as automatically safe. |
| GO-AGT-010 | MUST | Preserve behavior and approved contracts. When a discovered defect or conflict requires semantic change, create a separate finding/decision request and exclude the fix from pure cleanup. |
| GO-AGT-011 | MUST | Revalidate the plan, base SHA and allowed paths before applying edits. Stop affected changes if assumptions about ownership or equivalence no longer hold. |

Modes: `AUDIT_ONLY` (structural inventory and findings, read-only); `PLAN_ONLY` (current-to-target mapping, read-only); `REFACTOR` (authorized scoped changes); `VERIFY` (structural and regression checks, no source edits). No mode confers extra permissions. Follow the repository's existing Issue → branch → test → PR → human review workflow. Do not repeat a broad V2 compliance audit in any mode.

## 2. Architecture and package organization

| ID | Level | Structural rule |
|---|---|---|
| GO-ARCH-001 | MUST | Keep the executable entry point separate from implementation packages. Supporting packages must not depend on the executable. |
| GO-ARCH-002 | MUST | Group functions, types and state by a cohesive responsibility or hidden design decision. Separate business policy, application orchestration, transport and persistence where the distinction clarifies ownership. [S1,S2] |
| GO-ARCH-003 | MUST | Make static dependency direction explicit. Keep business-policy packages independent of concrete transport, SQL driver and bootstrap implementation where the approved architecture requires that boundary. Move code without expanding coupling. |
| GO-ARCH-004 | MUST NOT | Introduce import cycles or hide dependencies behind registries or global indirection to evade them. Resolve dependencies using meaningful ownership and narrow interfaces when necessary. |
| GO-ARCH-005 | MUST | Hide implementation details behind a small cohesive package API. Avoid exporting private helpers or mutable state merely to make a move compile. [S2] |
| GO-ARCH-006 | SHOULD | Extract a package only when independent responsibilities, ownership, test seams or information hiding justify it. Prefer additional files within a cohesive package when a separate package adds no value. |
| GO-ARCH-007 | SHOULD | Consolidate implementations only after demonstrating equivalent semantics, invariants, error behavior and lifecycle. Keep superficially similar but independently evolving logic separate. |
| GO-ARCH-008 | MUST | Preserve approved APIs, MQTT/radio-facing contracts, persisted data, resource requirements and externally observable behavior across structural moves. This is a preservation constraint, not a mandate to recertify these contracts. |
| GO-ARCH-009 | SHOULD | Use purpose-specific package names. Avoid `utils`, `common`, `helpers`, `components`, `interfaces` or `manager` as dumping grounds for unrelated responsibilities. [S3,S4] |
| GO-ARCH-010 | MUST | Distinguish static imports from runtime calls. Runtime callbacks, events and injected implementations do not justify a reversed source dependency or shared ownership. |
| GO-ARCH-011 | MUST NOT | Replace the approved Modular Monolith, introduce a DI container, additional datastore or generic framework just to reorganize source. |
| GO-ARCH-012 | SHOULD | Make composition explicit using existing constructors. Extract a narrow consumer-owned interface only when a real dependency boundary or existing test need justifies it. [S5] |

### 2.1. Organization principles

Prefer feature ownership and high cohesion over a universal layer template. A package may contain multiple files that share a responsibility. A source file is a navigation unit; a Go package is a compilation and visibility unit. Splitting a file does not create a new architecture boundary, and a new package adds a dependency/API cost.

When adding a new feature later, a developer should be able to find its implementation owner and add it without editing unrelated packages. Extensibility means low-impact changes at real extension points, not speculative abstractions for imagined future requirements.

## 3. Source and function organization

| ID | Level | Structural rule |
|---|---|---|
| GO-SRC-001 | MUST | Give each function, type and state one logical owner. Place code and associated tests in that package; name files for their responsibilities. |
| GO-SRC-002 | MUST | Apply `gofmt` to touched Go files and use existing formatting gates. Do not perform repository-wide formatting churn as a structural cleanup shortcut. |
| GO-SRC-003 | MUST | Preserve or reduce unnecessary exported surface after checking all callers and method sets; do not change a public compatibility boundary just to hide implementation. |
| GO-SRC-004 | SHOULD | Rename internal symbols or files only when the change materially improves navigation, ownership or comprehension. Follow existing V2 naming rules; do not perform a repository-wide naming/style audit. |
| GO-SRC-005 | SHOULD | Simplify reading order and call flow. Use cohesive private helpers, avoid artificial forwarding chains and unnecessary indirection, and retain long but coherent algorithms when splitting would make them harder to understand. |
| GO-SRC-006 | MUST | Delete existing code only when its lack of supported callers/use is demonstrated, including relevant build tags, registrations, reflection, tests, scripts, generated consumers and contracts. An analyzer warning is not sufficient proof. |
| GO-SRC-007 | MUST NOT | Remove deprecated compatibility behavior, error branches, regression tests or scaffolds with an approved purpose merely to reduce LOC. |
| GO-SRC-008 | SHOULD | Maintain package/file documentation and comments needed to navigate the new structure. Preserve intent, invariants and legal notices; remove only demonstrably obsolete comments. |
| GO-SRC-009 | MUST | Preserve build tags, platform variants, generated markers, `go:embed`, `go:generate`, cgo and vendor/upstream provenance when moving source. Generated/vendor/cryptographic copies are not routine cleanup targets. |
| GO-SRC-010 | MUST NOT | Change Go toolchain, module path or dependency versions merely for cleanup. Any necessary unrelated dependency change requires separate authorization. |
| GO-API-001 | MUST | Extract functions around a coherent task with explicit inputs and outputs; preserve effects, ordering and failure behavior. Do not split solely by LOC. |
| GO-API-002 | SHOULD | Reduce awkward dependency/parameter lists using meaningful ownership or cohesive typed groups. A parameter struct that merely hides a long dependency list is not an improvement. |
| GO-API-005 | SHOULD | Reduce incidental nesting and needless call indirection where equivalence is demonstrable. Do not rewrite branch conditions or error paths for style alone. |
| GO-API-006 | MUST | Preserve a single logical owner and existing lifetime for mutable state when extracting code. No new global mutable state or duplicate caches merely to simplify wiring. |
| GO-API-007 | SHOULD | Separate already-existing pure computation from I/O if that creates a useful reading/test boundary without changing behavior. Avoid speculative ports or wrappers. |
| GO-API-012 | MUST | When moving or narrowing internal interfaces, verify actual callers, receiver method sets, nil semantics and constructor behavior. Do not alter interface contracts simply for a cleaner signature. |

### 3.1. File-level organization example

```text
internal/api/
├── router.go               # route assembly
├── middleware.go           # existing shared HTTP middleware
├── monitoring_handler.go   # monitoring transport
├── alert_handler.go        # alert transport
└── router_test.go          # route composition regression tests
```

Illustrative only. Use current names and existing package owners where suitable. Do not create empty files, split every handler into its own package, or reorder functions purely to match a template. Locate related declarations near their consumers when that improves readability.

## 4. Backend-specific structure

| ID | Level | Structural rule |
|---|---|---|
| GO-BE-002 | MUST | `backend-go/cmd/server/main.go` contains exactly one top-level function declaration: non-generic `func main()` with no parameters, results or receiver and with a body. No other function/method declarations, `init()` or package-level `var` in that file. |
| GO-BE-003 | MUST NOT | Place business policy, SQL queries, CORS implementation, route registration, MQTT resolution, cryptographic implementation or worker logic directly in `main.go`. Do not satisfy GO-BE-002 by moving the same monolithic function elsewhere. |
| GO-BE-004 | MUST | Use a single explicit Composition Root near the executable, preferably `internal/app` for this backend if no suitable owner exists. It assembles existing dependencies; it must not become a business-logic dumping ground. [S1,S5] |
| GO-BE-005 | MUST | Place existing environment parsing, defaults and configuration representation in a coherent configuration owner, preferably `internal/config`. Inject existing settings. Preserve their values, precedence, fallback and failure behavior; policy correction is separate work. |
| GO-BE-006 | MUST | Organize existing initialization, runtime and teardown into clearly owned application lifecycle code. Preserve start/stop ordering, context lifetime, error handling and cleanup behavior. Changing those semantics requires a separate engineering issue. |
| GO-BE-008 | SHOULD | Expose a small application-facing composition/run API when useful. Keep implementation helpers private; avoid a giant relocated `main` and avoid gratuitous wrapper layers. |
| GO-BE-009 | MUST | Preserve existing executable path, Go module, environment interface, build/deployment invocation and supported operating modes. Update only affected callers/tests for structural moves. |
| GO-HTTP-001 | MUST | Organize route registration, HTTP middleware, request/response DTO conversion and transport-specific code under the existing HTTP adapter. Extract independently owned business orchestration only where evidence supports the separation. |
| GO-HTTP-003 | SHOULD | Assemble handler dependencies at the Composition Root and give the router ready-to-use handlers where this reduces coupling. Preserve route and middleware registration order. |
| GO-DB-001 | MUST | Organize existing SQL and persistence mapping under the persistence owner. Keep transaction logic cohesive and preserve transaction boundaries, ordering and observable behavior; no query/schema redesign. |
| GO-MQTT-001 | MUST | Organize existing MQTT connection, subscription, publish and codec mechanics under the MQTT adapter. Separate independently owned event/use-case orchestration only with a verified mapping of call and state ownership. |
| GO-LORA-001 | MUST | Keep the approved project architecture and current contracts intact. ADR `0004-pure-cad-csma-ca-mac.md` / Owner Issue #273 supersedes Hybrid TDMA with Event-Driven CAD/CSMA-CA and Gateway Continuous RX. Do not restore historical scheduling, periodic Beacon Sync or LoRaWAN features during cleanup. Revalidate authority at the task SHA. |
| GO-LORA-003 | MUST | Preserve the backend/Gateway/Node responsibility boundary: backend event ingestion, monitoring, management and persistence; Gateway/Node own RF execution. Do not move RF access policy into Go backend code. |

GO-BE-002 is a local entry-point convention, not a Go language mandate. It applies specifically to the file, not every file in a `package main`. Moving business logic into a sibling executable file to evade GO-BE-003 is not acceptable. `GO-BE-002` can be checked with Go AST; GO-BE-003 and actual cohesion require structural review.

### 4.1. Illustrative target layout

```text
backend-go/
├── cmd/server/main.go
├── internal/
│   ├── app/          # composition and lifecycle, if justified
│   ├── config/       # existing configuration ownership
│   ├── api/          # HTTP transport and router
│   ├── auth/         # existing identity/access owner
│   ├── domain/       # existing shared domain concepts
│   ├── alert/        # alert ownership, if justified by actual implementation
│   ├── presence/     # device presence
│   ├── mqtt/         # MQTT adapter
│   ├── realtime/     # realtime transport/hub
│   ├── security/     # existing security ownership; sensitive moves need review
│   ├── storage/      # persistence adapters
│   └── jsonboundary/ # existing decoding boundary
├── migrations/       # preserved; not a cleanup target
├── go.mod
└── go.sum
```

This is not a current repository inventory or a mandatory directory template. Do not create every listed package mechanically or delete unlisted packages. Preserve existing owners if they are suitable. Example entry point (illustrative API, not a verified implementation):

```go
func main() {
    // Load existing configuration.
    // Construct the application with explicit dependencies.
    // Launch the application and coordinate process termination.
}
```

## 5. Preservation constraints and incidental defects

This section inherits the existing Go V2 and approved contracts; it does not introduce a second set of security, concurrency, SQL, MQTT or API implementation rules.

During a move, identify the behavior actually affected by the move: input/output, errors and status codes, route registration, auth order, defaults, SQL transactions, publish/ack ordering, state ownership, goroutine/worker lifecycle, context lifetime, resource closing and serialization as applicable. Keep those invariants unchanged. No need to review all of those topics for every untouched package.

| Situation | Required disposition |
|---|---|
| Existing code is accepted and no affected invariant changes | Reuse accepted behavior; no historical Rule ID re-audit |
| A mechanical move changes package visibility or callers | Verify the affected compilation/test behavior |
| An incidental defect is observed | Record a separate `INCIDENTAL_DEFECT` with path, evidence and engineering-standard routing; do not count it as a GOCARS structural finding unless a distinct organization issue exists |
| A fix would change security, timing, data integrity, delivery semantics or other critical behavior | Separate issue with approval under existing engineering governance; exclude it from pure refactoring |
| New regression introduced by cleanup | Resolve within scope before acceptance; never waive it merely because the old code was approved |
| Approved contract conflicts with the existing behavior | Stop affected changes; request a decision. Do not invent a compatibility policy or claim a defect is acceptable. |

Example: moving broker URL resolution into a configuration owner is structural. Removing a hard-coded fallback changes configuration behavior and is a separate engineering issue. Moving a key wrapper is sensitive even if intended to preserve behavior; changing key derivation or rotation is not a cleanup operation. Changing `log.Fatalf` in an HTTP worker to a returned error changes failure/lifecycle behavior; do not include that change merely to make the code look cleaner.

## 6. Refactor decision matrix and risk

| Structural observation | Default response | Escalation |
|---|---|---|
| Unrelated functions in the same file | Group into cohesive files, keeping package where suitable | New package/API boundary requires dependency assessment |
| Entry point contains implementation | Extract configuration, routing and composition by owner | Lifecycle/security semantics must remain unchanged |
| Repeated equivalent code | Consolidate only after comparing actual behavior and callers | Independent invariants or side effects require separate design |
| Large file/function | Review cohesion and reading flow; no automatic split | Sensitive algorithm or execution context requires stronger review |
| Public symbol used only locally | Narrow visibility after proving caller compatibility | External or generated consumers unclear: retain |
| Obsolete code candidate | Trace all relevant consumers and approved compatibility requirements | Unclear use: keep and record |
| New package proposal | Show why same-package file split is insufficient | Avoid package proliferation and speculative extension points |

Risk tiers: `R0` cosmetic/formatting or file documentation; `R1` mechanical file move/private rename with no semantic change; `R2` package boundaries, interfaces, composition or ownership restructure; `R3` changes that may affect security, authorization, protocol, persistent data, concurrency/lifecycle or other critical behavior. Use highest applicable tier. R3 is normally outside pure cleanup; a demonstrably mechanical relocation of sensitive code may proceed only through the required review/approval and equivalence evidence, not through automatic authorization. Risk reflects the proposed change, not merely the severity of an existing issue.

## 7. Metrics — structure review only

| Metric | Initial review trigger | Disposition |
|---|---|---|
| `main.go` top-level function declarations | Anything other than exactly one `func main()` | Hard local rule GO-BE-002 after adoption/activation |
| Entry-point code lines | >50 nonblank/noncomment lines | Review orchestration responsibilities |
| Function code lines | >50 nonblank/noncomment lines | Review cohesion and reading flow |
| Cyclomatic complexity | >10 | Review control-flow clarity, not automatic extraction |
| Nesting depth | >4 | Review readability; preserve semantics |
| Constructor parameters | >7, variadic counts once | Review dependency cohesion |
| Exported API growth | Any new exported symbol | Justify owner and actual consumer |
| Import cycle | Any new cycle | Reject; existing Go build constraint |

Thresholds are local review heuristics, not universal Go requirements. The numeric triggers are not CI failure thresholds, goals, or reasons to request approval for each long function once the policy is adopted. Use the same measurement definitions/tools before and after. Exclude generated/vendor source from structural metrics unless scoped. Record measurable improvement only with baseline evidence. Prefer fewer cross-package dependencies, clearer ownership and easier navigation; no target LOC reduction, package count, test coverage percentage or complexity score. Do not install a linter solely to enforce arbitrary length limits.

## 8. Workflow: structural audit → plan → refactor → regression verification

1. **Discover:** read current scoped instructions, Issue/AC, applicable architecture/ADRs, relevant contracts and existing V2/Host requirements. Identify base SHA, worktree, pinned toolchain, package inventory and test commands. Treat existing code as the integrated baseline.
2. **AUDIT_ONLY:** for the initial backend-wide cleanup, inventory all `backend-go/` packages, files, entry points, public/internal symbols, import relationships, responsibility placement, duplicate/dead-code candidates and test locations. Inspect tests/config/migrations only to understand consumers and invariants. Do not perform a full semantic quality/compliance audit. Classify each package as `RETAIN`, `REORGANIZE`, or `NEEDS_EVIDENCE` with a reason.
3. **PLAN_ONLY:** create an ordered current-to-target map, identifying existing owner, destination, affected symbols/callers, expected structural benefit, risk, allowed paths, invariants, relevant V2 delta rules via existing Host selection, regression checks and rollback approach. Mark items not justified as `RETAIN`; do not manufacture work. Separate incidental defects and R3 policy changes.
4. **REFACTOR:** only after the initial audit and plan handoff and authorized scope. Implement the smallest coherent changes on an Issue branch/worktree. Move existing code first, update imports/references/tests, and verify each meaningful change group. No rewrite of accepted logic to satisfy stylistic preferences.
5. **VERIFY:** compare structure and affected behavior against the baseline. Run repository-required gates for the changed diff, including selected V2 rules as required by Host/Auditor; do not reselect every historical rule for untouched code. Use the existing required CI even if it runs the entire module. Report `NOT_RUN`/`BLOCKED` truthfully.
6. **HANDOFF:** report structural findings resolved, current-to-target mapping, measured benefits where available, changed files, before/after regression evidence, exclusions, incidental issues, and remaining structural debt. Use existing PR/Host/Auditor/human review governance.

Initial pilot: thin `cmd/server/main.go`; move router and middleware to the existing HTTP owner; move configuration and composition into appropriate owners; preserve existing lifecycle; then evaluate other packages only where structural findings warrant changes. Do not modify crypto, migration history, delivery semantics or deprecated route behavior as part of this pilot.

### 8.1. Required planning record

| Field | Required content |
|---|---|
| Finding | GOCARS Rule ID, actual path:line, structural evidence, impact |
| Move | Current owner → proposed owner; symbols, imports, consumers |
| Justification | What becomes easier to locate, understand, change or test |
| Invariants | Exact behavior and interfaces to preserve |
| Risk | R0–R3 and required review |
| Verification | Affected build/test/contract checks, relevant existing V2 delta rules |
| Scope | Issue, allowed paths, base SHA, exclusions, rollback method |

## 9. Acceptance and regression evidence

GOCARS acceptance means the authorized structure is improved and affected behavior is preserved to the extent established by evidence. It does not mean the entire backend is newly certified compliant. The existing engineering review process remains authoritative for changed code. Do not weaken or bypass it.

| Gate | Evidence | Applicability |
|---|---|---|
| GO-G0 Scope | Issue/AC, base SHA, allowed paths, authorization, Host receipts | All changes |
| GO-G1 Structure | Before/after ownership and import mapping, justified extractions, no new dumping grounds; AST check for entry-point work | Structural changes |
| GO-G2 Build/static | Existing `gofmt`, build, `go vet` and package loading as required; actual toolchain/commands/results | Affected compiled code; existing CI scope retained |
| GO-G3 Regression | Existing affected tests and focused characterization tests where equivalence is otherwise uncertain | Affected behavior/callers |
| GO-G4 Contract/integration | Existing fixtures/integration evidence for boundaries affected by moves; no new schema or semantics | When an affected external boundary requires it |
| GO-G5 Concurrency/lifecycle | Focused race/lifecycle checks when a move touches concurrent ownership or lifecycle; existing mandatory checks remain | Relevant changes only |
| GO-G6 System/HIL | Existing system/HIL policy only where the change actually requires it; no blanket RF/HIL rerun for Go source reorganization | Relevant system-facing changes only |
| GO-G7 Review | Existing Host/Auditor and human review, scope/exception resolution | Per repository policy and risk tier |

Statuses: `PASS`, `FAIL`, `NOT_RUN`, `BLOCKED`, `NOT_APPLICABLE` (with rationale). Missing mandatory checks block acceptance. Existing historical engineering receipts are not fabricated, repeated wholesale or converted into new GOCARS PASS claims. Do not remove tests to obtain PASS. A pure docs-only change does not require backend runtime tests unless existing policy mandates them.

Example commands from `backend-go/`, using the pinned toolchain and authorized environment; reconcile with actual CI before execution:

```sh
GOTOOLCHAIN=local go version
# Read-only structural/import discovery; may require module cache/network access.
GOTOOLCHAIN=local go list -deps ./...
# Existing formatting check.
test -z "$(gofmt -l .)"
GOTOOLCHAIN=local go vet ./...
GOTOOLCHAIN=local go test ./...
GOTOOLCHAIN=local go build ./cmd/server
# When applicable or mandated by existing repository policy:
GOTOOLCHAIN=local go test -race ./...
```

These are illustrative commands, not executed as part of this revision. Use actual repository presets, avoid unrelated module/toolchain updates, and do not migrate or access production systems for cleanup verification.

## 10. Agent/Host/CI integration

Use existing `AGENTS.md` and Host rule-selection/receipt mechanisms. Do not replace the existing mandatory Go Engineering Standard V2 or inject all GOCARS rules for ordinary feature tasks. Route GOCARS only to explicitly scoped structural cleanup or architecture-organization work. For Issue #359 adoption, GOCARS Rule IDs are a supplemental structural planning and evidence namespace, not entries in the existing deterministic Host catalog. The Coordinator selects applicable GOCARS rules and records them separately in the structural plan and Auditor input. The Host independently selects, validates and injects the existing V2 delta rules for the changed paths; the Auditor verifies the actual cumulative diff, both sets of applicable obligations and receipts. Do not submit GOCARS or agent-local CG IDs to the V2 catalog or bypass unknown-ID checks. Native instructions are not a deterministic interception mechanism. Adding GOCARS to a future Host catalog requires a separately reviewed integration.

After owner approval and integration, use the existing GO-BE-002 AST checker from the GOCARS-1.1 readiness pack (or equivalent reviewed implementation) to check the exact entry-point declaration and absence of package-level `var`. Verify checker fixtures with the repository-pinned toolchain, integrate through an authorized Issue/PR, and activate the hard gate with the compliant entry-point change or an approved staged rollout. Existing `gofmt`, `go vet`, package loading/build and tests remain the normal Go gates; no duplicate lint framework is required. AST cannot establish cohesion or detect a relocated God Function: review GO-BE-003 and GO-BE-004 separately.

### 10.1. Reusable coding-agent instruction

```text
You are a Go Codebase Organization and Structural Refactoring Agent.
Follow GOCARS-2.0 for structural work and existing repository governance.
The integrated backend is the accepted engineering baseline. Do not run a
second full-codebase Go Standard V2 compliance or security audit.

Default to AUDIT_ONLY. Inventory package/file ownership, dependency direction,
entry point, composition, source grouping, navigation and proven redundancy.
Report structural findings with stable Rule IDs and source evidence.
In PLAN_ONLY, propose the smallest coherent current-to-target moves, with
invariants, callers, risk, allowed paths and affected regression checks.
Keep accepted implementations intact; do not invent features or policy fixes.
Refactor only with authorized scope on a non-main Issue branch/worktree.
Make main.go a thin entry point under GO-BE-002/003; do not relocate a God Function.
Do not fix incidental security/reliability defects in the cleanup diff.
Reuse existing engineering approval evidence for unchanged code. Apply normal
V2 delta checks selected by the trusted Host to the changed diff; run the
existing required CI and affected regression checks. Never bypass governance.
Report structural improvements, changed files, evidence and separate follow-up
issues. Do not claim whole-backend recertification, unsupported PASS or approval.
```

### 10.2. Machine-readable structural audit/report example

```json
{
  "standard": "GOCARS-2.0",
  "mode": "AUDIT_ONLY",
  "base_sha": null,
  "baseline_policy": "INHERITED_ENGINEERING_BASELINE",
  "overall": "NOT_VERIFIED",
  "structural_findings": [
    {
      "finding_id": "S-001",
      "rule_ids": ["GO-BE-002", "GO-HTTP-001"],
      "path": "backend-go/cmd/server/main.go",
      "line_start": 30,
      "line_end": 41,
      "evidence": "Illustrative historical example: CORS middleware in entry point.",
      "impact": "Transport code obscures process orchestration.",
      "proposed_owner": "existing HTTP adapter",
      "risk": "R2",
      "invariants": ["CORS headers", "preflight status", "middleware order"],
      "required_gates": ["GO-G1", "GO-G2", "GO-G3"]
    }
  ],
  "incidental_defects": [],
  "changed_files": [],
  "checks": [],
  "blockers": ["Example only; refresh source and baseline before use."],
  "approval_required_for_edits": true
}
```

Use actual findings and exact source locations. Separate structural findings from incidental defects, and record test commands, exit status, configuration and evidence paths in `checks`. No historical engineering-compliance score is required in this report.

## Appendix A — Design references

- **S1** Robert C. Martin, *Clean Architecture: A Craftsman's Guide to Software Structure and Design* (2017), Ch. 7, 11, 13–14, 22, 26. https://www.oreilly.com/library/view/clean-architecture-a/9780134494272/ch26.xhtml — responsibility, dependencies, cohesion and Main Component.
- **S2** John Ousterhout, *A Philosophy of Software Design*, 2nd ed. (2021), Ch. 4–6. https://web.stanford.edu/~ouster/cgi-bin/book.php — deep modules, information hiding and complexity reduction.
- **S3** Go documentation, Organizing a Go module, server project. https://go.dev/doc/modules/layout — `cmd/` and `internal/` organization; not a mandate for a specific architecture.
- **S4** Go Blog, Package names. https://go.dev/blog/package-names — cohesive, meaningful package names.
- **S5** Steven van Deursen and Mark Seemann, *Dependency Injection Principles, Practices, and Patterns* (2019), Ch. 3, Composition Root. https://www.manning.com/books/dependency-injection-principles-practices-and-patterns — explicit composition close to the entry point.
- **S6** Martin Fowler, *Refactoring: Improving the Design of Existing Code*, 2nd ed. (2018), Ch. 2 and refactoring catalog. https://martinfowler.com/books/refactoring.html — small behavior-preserving transformations, not feature development.
- Go language executable definition: https://go.dev/ref/spec#Program_execution — GO-BE-002 is a stricter local file-organization rule, not a Go language requirement.

These references support the structural principles; local Rule IDs, metrics and adoption gates are repository policy choices, not external certification requirements.

## Appendix B — Rule identity, transition and adoption

GOCARS v2.0 intentionally narrows v1.1. Retained IDs preserve their structural meaning and are scoped to refactoring, not general engineering re-audit. Retired IDs remain reserved and must not be reused. A retired GOCARS rule does not remove its underlying engineering obligation: the applicable existing V2/contract rules continue to govern. The following registry records dispositions so stale agent prompts or Host indexes do not silently reinterpret IDs.

| Retired IDs (reserved; not active) | Disposition |
|---|---|
| `GO-API-003`, `GO-API-004`, `GO-API-008`, `GO-API-009`, `GO-API-010`, `GO-API-011` | Existing V2 API/error/context/data-contract implementation rules; preserve affected behavior only. |
| `GO-SAFE-001`, `GO-SAFE-002`, `GO-SAFE-003`, `GO-SAFE-004`, `GO-SAFE-005`, `GO-SAFE-006`, `GO-SAFE-007`, `GO-SAFE-008`, `GO-SAFE-009`, `GO-SAFE-010` | Existing security, concurrency, lifecycle and resource engineering rules; do not re-audit; incidental issues separate. |
| `GO-BE-001`, `GO-BE-007` | Language/runtime validity and readiness policies already governed by Go/V2; not organization findings. |
| `GO-HTTP-002`, `GO-HTTP-004`, `GO-HTTP-005`, `GO-HTTP-006` | HTTP/auth/WSS contract and resource behavior governed by V2; scoped regression only. |
| `GO-DB-002`, `GO-DB-003`, `GO-DB-004`, `GO-DB-005`, `GO-DB-006` | Persistence correctness, migrations and integration obligations remain V2/contract policy. |
| `GO-MQTT-002`, `GO-MQTT-003`, `GO-MQTT-004`, `GO-MQTT-005` | MQTT transport, configuration and delivery semantics remain V2/contract policy. |
| `GO-LORA-002`, `GO-LORA-004`, `GO-LORA-005` | Wire, event semantics and system evidence remain approved contract/architecture policy. |

Active structural Rule IDs: **52**. Retired/reserved IDs: **34** of the original 86. No ID reused for unrelated meaning. Existing GO-G0–GO-G7 gate labels remain, with refactor-specific applicability. Under the Issue #359 supplemental routing, the Coordinator and Auditor use only active GOCARS IDs in a separate structural ledger; the deterministic Host continues to recognize its existing V2 catalog only. A future catalog integration must register the adopted version and active ID index; retired IDs must never become active. Existing V2 IDs are not changed.

Adoption: `APPROVED_ON_OWNER_MERGE`. Issue [#359](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/359) proposes adoption of this exact version, GO-BE-002 and Section 8 review triggers as a supplemental structural profile. Owner approval and merge of the integration PR are the adoption record; before that event this profile is PROPOSED and read-only planning is permitted. Once the owner-approved integration is on main, no separate per-rule or metric approval is required. The entry-point AST hard gate is a separate staged rollout, not activated by this change. Adoption does not authorize backend edits; retain existing Issue/risk/operation authorization.

Issue #359 integrates the document and native agent configuration, not backend source refactoring, runtime verification, a new Host catalog or CI gate activation. Native AGY/CodeGraph execution remains NOT_VERIFIED until exercised in the operator environment. Historical source examples are illustrative and must be refreshed at the actual task SHA. The existing v1.1 readiness report and proposed R3 tickets are historical supporting material, not a mandatory quality-audit backlog under GOCARS v2.0.
