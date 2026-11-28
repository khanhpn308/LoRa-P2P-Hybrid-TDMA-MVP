# Repository Quality Score & Deferred Technical Debt

**Assessed Revision:** `ed97ca9e7fb69f359db717e40679cabaee18ae0d` (`origin/main` + P08-A `#437`)
**Last Assessed:** `2026-11-28` · **Scope:** Monorepo Foundation + Harness V2 (`P00–P08-A`)
**Owner:** Project Owner (`khanhpn308`) & Component Owners per [CODEOWNERS](../.github/CODEOWNERS)
**Companion Index:** [docs/harness/ADVANCED_PACK.md](harness/ADVANCED_PACK.md) · **DB Metadata:** [docs/generated/db-schema.md](generated/db-schema.md)

> [!CAUTION]
> **Hard-Gate Non-Override Invariant:** No grade (`A–D`) or aggregate score may override a failing hard gate (`SECRET-SCAN`, `DIFF-CHECK`, scope violation, missing G0/receipt), an unresolved `P0/P1` finding, or a `NOT_VERIFIED` dimension (`RF`, `HIL`, `TIMING`, `HUMAN_SECURITY_REVIEW`). Harness Python test `PASS` **never** certifies product build, runtime, RF/HIL, or security acceptance.

---

## 1. Grading Scale (`HARNESS_SPEC.md §7.3`)

- **`A`**: Verified at required layers, legible, stable, boundaries mechanically enforced, no open P0/P1 gaps.
- **`B`**: Working with minor documented gaps; software checks verified, no unresolved P0 defects in-domain.
- **`C`**: Partial or unstable; software checks only partially runnable or open P0/P1 baseline defects remain.
- **`D`**: Broken, unsafe, or structurally unclear.
- **`NOT_VERIFIED`**: Required verification evidence absent or unexecuted at current revision (never inferred from prose, syntax checks, or historical runs).

---

## 2. Product Domains

*Historical baseline receipts from P01 (`fdbc9a5c`, 2026-11-27, [HARNESS_BASELINE_REPORT.md](harness/phase-01/HARNESS_BASELINE_REPORT.md)) are explicitly separated from current revision (`059fa45fc`, 2026-11-28) measurements.*

| Domain | Grade | Owner | Current Evidence (`059fa45fc`) & Historical Provenance (`fdbc9a5c`) | Key Gaps & Hard-Gate Status | Last Assessed |
|---|---|---|---|---|---|
| **Firmware (`firmware/gateway_master`, `sensor_node`, `components/*`)** | `C` *(SW `PARTIAL`; RF/HIL `NOT_VERIFIED`)* | Embedded / RF Owners | **Current:** `verify_structure.py` & `dependency_checks.py --domain firmware` PASS. **Historical (`fdbc9a5c`):** `tests/unit` 44/44 PASS (`EV-021`); `--network=none` IDF v6.1 build FAIL (`exit 2`, uncached `espressif/mqtt`, `EV-018`). | Offline clean-worktree IDF build fails without cached `managed_components`; `#169` (RF/HIL timing), `#175` (NVS power-loss HIL), `#411` (Gateway mTLS) remain `OPEN` / `NOT_VERIFIED`. | 2026-11-28 |
| **Backend Go (`backend-go/`)** | `C` *(Static/Unit `PARTIAL`; Live E2E `NOT_VERIFIED`)* | Backend Go Owner | **Current:** `dependency_checks.py --domain backend-go` PASS. **Historical (`fdbc9a5c`):** Docker `golang:1.27.3-alpine` `go vet`, `go test` (13 pkgs), `go build ./cmd/server` PASS (`EV-017`), `gofmt` FAIL. | `backend-go/internal/presence/rf_tracker.go:140-145` fails `gofmt` in CI (`OWNER_WAIVED` quota); host Go `1.27.1 != 1.27.3`; live PostgreSQL/Mosquitto E2E `NOT_RUN`. | 2026-11-28 |
| **Database & Migrations (`backend-go/migrations/`)** | `C` *(Source metadata `PASS`; Runtime `NOT_VERIFIED`)* | Backend / Storage Owner | **Current:** `advanced_pack.py check-db-schema` PASS (`11` `.up.sql`, `13` active tables + `schema_migrations`, deterministic tree hash `4960b9e9...` in [db-schema.md](generated/db-schema.md)). | Duplicate `000004_*` prefix (`3` files) works with `/app/migrate.sh` but conflicts with `golang-migrate` mentioned in [POSTGRESQL_OPERATIONS_GUIDE.md](development/POSTGRESQL_OPERATIONS_GUIDE.md); live DB migration/restore at `059fa45fc` is `NOT_RUN`. | 2026-11-28 |
| **Contracts & Schemas (`contracts/`)** | `B` *(Syntax `PASS` historical; C↔Go & Security `NOT_VERIFIED`)* | Contract Producer / Consumer Owners | **Current:** `dependency_checks.py --domain contracts` PASS. **Historical (`fdbc9a5c`):** `check_contracts.py` & `tests/contract` (15 tests) PASS (`EV-019`, `EV-020`). | [OPEN_DECISIONS.md](../contracts/OPEN_DECISIONS.md) (`D01..D13`) open; C↔Go AES-GCM/HMAC vectors (`#173`) `NOT_VERIFIED`; superseded TDMA schemas kept for historical log decoding. | 2026-11-28 |
| **Clients — Web Dashboard (`clients/web-dashboard/`)** | `C` *(Clean-worktree unit `PARTIAL`; Runtime `NOT_VERIFIED`)* | Web Frontend Owner | **Current:** `dependency_checks.py --domain clients` PASS; `quality_gates.py` `SECRET-SCAN` FAIL (`integration.test.ts:31`, false positive `#424`). **Historical (`fdbc9a5c`):** `api_client`/`rf_quality` unit tests PASS; `integration.test.ts` FAIL (`no node_modules`, `EV-022`). | Open P0 `SECRET-SCAN` false positive (`#424`); clean-worktree `node_modules` missing; `ci-clients.yml` is a stub; live browser E2E (`#341`) `NOT_VERIFIED`. | 2026-11-28 |
| **Clients — Mobile Android (`clients/mobile-app/`)** | `NOT_VERIFIED` *(Stub / `N/A` runtime)* | Mobile Owner (`#80` assignee: `hieuvocong15`) | README/design placeholder only (`clients/DESIGN.md`, `#80` `OPEN`). | No Kotlin source implemented; excluded from runtime build/UI checks until `#80` layout approval & implementation. | 2026-11-28 |
| **Deploy & MQTT Infra (`deploy/`)** | `NOT_VERIFIED` *(Live runtime `NOT_RUN` at `059fa45fc`)* | Infra / Security Owner | **Historical docs:** [issue-404](verification/issue-404-mqtt-tls-auth-verification.md), [issue-405](verification/issue-405-prod-secrets-reverse-proxy-verification.md), [issue-406](verification/issue-406-compose-hardening-migrations-backup-verification.md). | `ci-integration.yml` is a stub; live Docker Compose TLS/ACL/PostgreSQL persistence suite `NOT_RUN` on `059fa45fc`. | 2026-11-28 |
| **Simulator (`simulator/`)** | `NOT_VERIFIED` *(Placeholder only)* | RF / Simulation Owner | Planning/model documentation only; not a verified digital twin. | No executable closed-loop digital twin verified against physical hardware. | 2026-11-28 |
| **Agent Harness (`scripts/agent_harness/`, `.agents/`, `docs/harness/`)** | `C` *(Baseline `#424` P0 open; Historical P07 `B`; Host unit `PASS`; Runtime sandbox `PARTIAL`)* | Harness / Owner | **Current (`#437` P08-A):** `orchestrator.py` unified admission/Role ACL/frozen policy/sequential `WIP=1`, `verify_structure.py`, `dependency_checks.py`, `harness_doctor.py --profile core`, `advanced_pack.py verify`, and `tests/agent_harness` PASS. **Historical P07 (`#435`):** `B` (`488` unit tests PASS). | Reassessed to `C` per §1 grading rule while P0 baseline `#424` (`SECRET-SCAN` FP) remains `OPEN`; Native Fast Lane Full Access is `SUPERVISED_ONLY` (`H2-TOL-02`); `P08-B..E` multi-round pilot/recovery/experiments & rubric calibration remain `NOT_VERIFIED`. | 2026-11-28 |

---

## 3. Architectural Layers

| Layer | Grade | Boundary Enforcement | Agent Legibility | Key Gaps | Last Assessed |
|---|---|---|---|---|---|
| **Firmware 3-Tier (`main` / app components / shared components)** | `B` | `dependency_checks.py` (`check_firmware_boundaries` via `CMakeLists.txt` + `#include`) | `Good` (CCARS v1.4 + ADR-0004 aligned) | Offline IDF build cache (`espressif/mqtt`); HIL/RF unverified | 2026-11-28 |
| **Backend Go Modular Monolith (`cmd` / `internal`)** | `B` | `dependency_checks.py` (`check_go_boundaries` via `go.mod` + AST/imports) | `Good` (GOCARS + Go V2) | `GO-BE-002` CI gate pending; `rf_tracker.go` `gofmt` drift | 2026-11-28 |
| **Web Client Layers (`types` / `lib` / `components` / `app`)** | `B` | `dependency_checks.py` (`check_client_boundaries` via TS imports) | `Good` (`clients/DESIGN.md`) | `node_modules` absent in clean worktrees; `SECRET-SCAN` FP (`#424`) | 2026-11-28 |
| **Versioned Contracts (`$ref` / Schemas / OpenAPI)** | `B` | `dependency_checks.py` (`check_contract_boundaries`) + `check_contracts.py` | `Good` (`contracts/README.md`) | `D01..D13` open; historical TDMA schemas retained read-only | 2026-11-28 |
| **Harness Control Plane & Host Gates** | `C` *(Historical P07 `B`; `#424` P0 open)* | `orchestrator.py`, `agent_context.py`, `scope.py`, `quality_gates.py`, `pr_review.py`, `check.py`, `feature_state.py`, `observability.py`, `advanced_pack.py`, `p1/{cli,state}.py` | `Good` (`ADVANCED_PACK.md` + `AGENTS.md`) | Baseline `#424` P0 open; Native Full Access lacks OS sandbox (`H2-TOL-02`); `P08-B..E` & `P09–P10` pending | 2026-11-28 |

---

## 4. Benchmark Snapshots & Simplification Log

### 4.1 Benchmark Snapshots (`HARNESS_SPEC.md §7.3` / `OD-06`)

| Date | Revision | Variant | Completion Rate (VCR) | Retries | Verification Gap | Notes |
|---|---|---|---|---|---|---|
| 2026-11-27 | `fdbc9a5c` | P01 Baseline | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | Protocol frozen in [HARNESS_BASELINE_REPORT.md §7](harness/phase-01/HARNESS_BASELINE_REPORT.md#7-wp-f--benchmark-protocol--metric-specifications-harness_specmd-73--od-06); paired trials scheduled in P08/P10. |
| 2026-11-28 | `500acba0` + `#443` | P08-D Controlled Fixture (`CONTROLLED_FIXTURE` only) | `NOT_VERIFIED` *(live)* | `NOT_VERIFIED` *(live)* | `NOT_VERIFIED` *(live)* | Controlled-fixture demonstration only ([EXPERIMENT_LOG.md](harness/EXPERIMENT_LOG.md)): `EXP-DEMO-KEEP-001` (`instruction_snr` `+0.40`, `KEEP`/`FIXTURE_ONLY_NOT_PROMOTABLE`), `EXP-DEMO-REJECT-002` (`-0.25`, `REJECT`), `EXP-DEMO-GAMING-003` (`REJECT`). Real productivity gain & live provider evaluation remain `NOT_VERIFIED`. |

### 4.2 Simplification Log (`L12` / `H2-FBK-08`)

| Date | Revision | Component Simplified / Consolidated | Outcome & Regression Check | Decision |
|---|---|---|---|---|
| 2026-11-28 | `d76ce89` (`#419`) | Removed 221-page binary `learn-harness-engineering-en.pdf`; internalized to self-contained Markdown (`docs/references/harness-engineering/`) | `248/248` local anchors verified offline (`--network=none`) | `KEEP` |
| 2026-11-28 | `#435` (`P07`) | Consolidated 16 SPEC §5.2 logical surfaces into 1 routing index (`ADVANCED_PACK.md`) + `QUALITY_SCORE.md` + `db-schema.md` instead of 16 template copies | Verified via `advanced_pack.py verify` + `tests/agent_harness` | `KEEP` |

---

## 5. Deferred Technical Debt (GitHub Issues Projection)

**GitHub Issues remain the sole authoritative writable backlog.** This table is a read-only projection; do not track independent unlinked tasks here.

| Issue (Authority) | Area | Deferred Debt | Risk | Owner | Review / Resolution Trigger | Status |
|---|---|---|---|---|---|---|
| [#424](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/424) | Security / Harness | Baseline `SECRET-SCAN` false positives (`integration.test.ts:31` & 6 files in `verify_no_secrets.py`) | `P0` (`quality_gates.py` blocks `AUTO_CHECK_PASS`) | `UNASSIGNED` | Pre-P02 security remediation PR without weakening secret detection | `OPEN` |
| [#425](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/425) | Harness P02 | Instruction & knowledge simplification (`AGENTS.md` size target, TDMA doc cleanup) | `P1` (instruction bloat / drift) | `UNASSIGNED` | P02 PR + fresh-session / G0 recall parity check | `OPEN` |
| [#427](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/427) | Harness P03 | Remaining clean-worktree offline cache gaps (`espressif/mqtt`, host Go `1.27.3` alignment) | `P1` (offline clean builds fail) | `UNASSIGNED` | P03 follow-up or toolchain cache policy decision | `OPEN` |
| `Baseline §5.2` *(No dedicated Issue yet)* | Backend Go | `gofmt` doc-comment indentation drift in `backend-go/internal/presence/rf_tracker.go:140-145` | `P1` (Go CI `gofmt` step fails) | `UNASSIGNED` | Next scoped `backend-go/` PR (`gofmt -w`) | `DEFERRED_LOGGED` |
| [#364](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/364) | Governance | Reconcile PR Acceptance Policy with CCARS v1.3 & `OWNER_WAIVED` CI Standard | `P2` (policy consistency) | `UNASSIGNED` | Governance/Harness policy review | `OPEN` |
| [#169](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/169) | RF / HIL | Physical ESP32–SX1276 timing/ToA/guard measurement on hardware | `P1` (blocks Release Gates G1/G3) | `UNASSIGNED` | Physical RF/HIL bench availability (`OD-07`) | `OPEN` |
| [#175](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/175) | Firmware / Security | Gateway NVS `INSTALLED_INACTIVE` key-slot atomicity under power-loss fault injection | `P1` (blocks Release Gate G5) | `UNASSIGNED` | Programmable power-loss HIL bench | `OPEN` |
| [#411](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/411) | Firmware / MQTT | Gateway firmware MQTT 5.0 over mTLS | `P1` (security transport) | `UNASSIGNED` | Firmware + Infra security review | `OPEN` |
| [#341](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/341) | E2E Acceptance | Full-stack Join V2 acceptance (GPIO button -> Join Wait -> Web approve/reject) | `P1` (blocks E2E Join sign-off) | `UNASSIGNED` | Integrated firmware + Go + Web bench | `OPEN` |
| [#80](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/80) | Mobile Android | Kotlin Android MVP UI layouts & approval gate | `P2` (mobile client absent) | `hieuvocong15` | UI layout design approval before code | `OPEN` |

---

## 6. Quality & Debt Update History

| Date | Revision | Trigger / Evidence | Changes Recorded |
|---|---|---|---|
| 2026-11-28 | `059fa45fc` + `#435` | P07 Advanced Pack integration (`advanced_pack.py verify`, `check-db-schema`, `tests/agent_harness`) | Established initial evidence-backed domain/layer grades (`NOT_VERIFIED` preserved for RF/HIL/live runtime), added source-derived `docs/generated/db-schema.md`, and projected verified GitHub debt (`#424`..`#80`). Historical P07 Harness grade: `B`. Separate 6-dimension evaluator rubric calibration remains `NOT_VERIFIED` (`OD-06`/`OD-09`). |
| 2026-11-28 | `ed97ca9e7` + `#437` | P08-A Role & Control-Plane integration (`orchestrator.py`, `p1/state.py`, `run.py`, `p1/cli.py`) | Added unified Host admission/dispatch contract, Role ACLs, sequential `WIP=1`, and frozen per-run policy inputs for P08-B. Reassessed active Harness grade from historical `B` (`#435`) to `C` while P0 baseline `#424` remains `OPEN` (retaining historical `B` in provenance). |
| 2026-11-28 | `500acba0` + `#443` | P08-D Controlled Improvement Experiment (`improvement.py`, `p1/state.py`, `p1/cli.py`, `EXPERIMENT_LOG.md`, `test_improvement.py`) | Added bounded OD-10 meta-improvement loop with frozen oracle/holdout/negative-control hashes, SHA-bound receipts, safe owned-workspace discard, and controlled-fixture KEEP/REJECT verification. Active Harness grade remains `C` while P0 baseline `#424` stays `OPEN`; live-provider improvement & human calibration stay `NOT_VERIFIED`. |
