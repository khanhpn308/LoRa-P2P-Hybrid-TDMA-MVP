---
applyTo: "backend-go/**"
---
# Go Backend AI Instructions — v1.0.1 DRAFT

> **Status:** DRAFT; this file is the sole path-scoped backend instruction (branch Issue #41, stacked on #40; pending review). **Canonical target:** `docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V1.0.md` (proposed in Issue #39; pending merge/review). References in `[RULE-ID]` correspond to the canonical full standard. Go 1.27.3 is an owner-directed repository lock; Engineering Standard remains DRAFT pending independent review.

## Priorities

[GB-001..010] Correctness > Safety > Reliability > Maintainability > Performance. Implement the **smallest correct, secure, observable vertical slice**. Clarity/explicit behavior > shortest LOC; no speculative generalization or unused dependencies.

## Mandatory preflight

1. [AI-001, AR-002] Read Issue, Acceptance Criteria, **Target Directories (allowed paths)**, branch, working tree, `.github/copilot-instructions.md`, path-specific instructions, requirements, ADRs, contracts and existing source. For a new vertical slice, check whether `backend-go/cmd/server/main.go` requires composition-root dependency wiring.
2. [AI-002, AR-002] Edit **only** approved paths. If wiring `main.go` or new test/doc/migration falls outside allowed paths, **STOP**, identify the exact needed file and request owner scope approval **before writing**. If `main.go` is allowed, wire only minimal startup/dependencies, no business logic.
3. [AI-006, GO-014, GB-007] Verify `backend-go/go.mod`, `.go-version`, exact dependency versions and `go doc`/API. Baseline is **Go 1.27.3**, locked in `backend-go/go.mod`, root `.go-version` and CI; MUST check `go env GOVERSION == go1.27.3`. `GOTOOLCHAIN=local` in CI; no silent toolchain upgrade or `@latest` dependencies.
4. [AI-003, AI-004] Produce a 5–10 line plan: inputs/outputs, invariants, error paths, modules/files, tests, composition root and scope gaps. Implement only an approved, buildable vertical slice; otherwise report `BLOCKED_SCOPE`.

## Architecture invariants

- [AR-001..008, SC-001..008, MQ-012] Go backend = **modular monolith**, PostgreSQL, MQTT; Gateway executes Hybrid TDMA locally. Go plans versioned schedules, **never per-slot RF timing**; entrypoint is composition root.
- [GB-003, GB-007, DB-001, DB-008] **Pre-approved Stack under this DRAFT standard:** HTTP `net/http` + Go 1.27.3 `http.ServeMux`; PostgreSQL `github.com/jackc/pgx/v5` (`pgxpool` default; `database/sql` adapter if justified); MQTT 5.0 `github.com/eclipse/paho.golang/autopaho` + `paho`. Module versions are NOT YET APPROVED; select explicit dependency versions compatible with Go 1.27.3 and verify build/security before installation. **No** Gin/Echo/Fiber, `paho.mqtt.golang` (MQTT 3.1.1), ORM or unapproved library.
- [AR-004, AR-005, SE-005] No LoRaWAN stack, ChirpStack, OTAA, Redis, InfluxDB, Kafka, microservices or unapproved abstraction/framework. Respect domain/adapter boundaries and custom LoRa P2P MAC.
- [CT-001..009, AI-007] Contracts/ADRs are versioned interfaces. No silent MQTT topic, API, MAC frame, security or SQL schema changes; follow cross-team review.
- [MQ-001, MQ-002, MQ-006..008, DB-005] MQTT 5.0 ADR-0002: QoS1 at-least-once; DB unique `(gateway_id,event_id)`; downlink expiry + `Retain=false`; transport `PUBACK` ≠ Gateway execution.
- [MQ-003..005, OB-003, OB-009, TS-005] **Poison QoS1:** classify permanent malformed JSON/schema/unsupported version → structured error log (redacted) + invalid/dropped metric + **PUBACK after recording drop**; do not redeliver forever. Transient DB/I/O → bounded backoff/jitter/retry and **no early ACK** before durable success; on exhaustion use reviewed controlled recovery (never silently drop). Paho auto-ACK happens when callback returns: process synchronously or enable manual ACK + `Client.Ack`, maintaining ACK order/backpressure. Test with actual broker; callback errors are not MQTT NACKs.
- [MQ-009, DB-004, SC-006] **Monotonic schedule lifecycle:** validated `STAGE_ACK` may advance `PROPOSED/SENT → STAGED`; validated `ACTIVE_REPORT` may advance `PROPOSED/SENT/STAGED → ACTIVE` (identity/version/request ID + activation evidence). Persist intent before publish; use DB conditional update/CAS so late `SENT` update cannot downgrade state. Reject stale/mismatched/terminal conflicts; duplicate reports idempotent. `STAGE_ACK` ≠ ACTIVE; **only valid `ACTIVE_REPORT`** yields ACTIVE. No MQTT network I/O inside DB transaction.
- [SC-002, TS-006, QG-008] RF parameters, latency and HIL targets not measured remain `NOT_VERIFIED`, not facts or SLAs.

## Coding rules

- [GO-001..005, GB-002..005] `gofmt`; meaningful MixedCaps; guard clauses; small cohesive functions; comments explain **why**. No speculative wrappers or nested pass-through layers.
- [GB-006, GB-008, AR-008] Avoid `util/common` dumping grounds, generic repositories, unnecessary interfaces, reflection, registry/factory patterns, global state.
- [GO-006, GO-008..010] Typed structs/JSON tags; wrap useful error context with `%w`, use `errors.Is/As`, handle each error, **log once at responsible boundary**.
- [GO-011..013, RT-005] `context.Context` first for I/O; propagate timeout/cancellation; UTC + correct timestamp source/units.
- [GO-006, CT-003..004, TS-003, AI-006] **Go 1.27 JSON:** preserve outbound wire serialization via `encoding/json` (v1-compatible) unless a contract review approves otherwise. For **new inbound JSON object** HTTP/MQTT DTOs, use `internal/jsonboundary.DecodeObject(payload, maxBytes, &dto)` (Go stdlib `encoding/json/v2`, strict duplicate/UTF-8 rejection + `RejectUnknownMembers`); size-limit payload before decode, typed fields/case-sensitive keys. **Decode success ≠ JSON Schema success**: validate required fields, `schema_version`, enum/range/regex, nullability and cross-field invariants separately before DB writes/MQTT ACK. IDs such as `event_seq` remain decimal strings; no `float64` conversion. Test duplicate top-level/nested, malformed/trailing JSON, unknowns, invalid UTF-8, null, overflow and legacy output representation; never assert exact stdlib error text.
- [CT-003..006, GB-009, SE-001..009] Validate trust boundaries and domain invariants; no silent fallbacks, secret logging, unsafe auth/RBAC, or normal-error `panic`.
- [RT-001..011, MQ-004..005] Concurrency only when justified; bounded queues/workers/retries; each goroutine owned and joined; graceful shutdown with finite deadline.
- [DB-001..010] SQL parameterized; DB constraints, short transactions, versioned migrations, idempotency; no assumption of DB↔MQTT atomicity.
- [OB-001..012, GO-009] Prefer stdlib `slog`; log meaningful state transitions with `request_id`, `gateway_id`, `event_id`, `schedule_version`; no secrets, high-cardinality metric labels or redundant logs.

## Tests and finish criteria

- [TS-001..011, SC-008] Test happy path, malformed/expired, duplicate/out-of-order, cancellations, boundary transitions and concurrency races. Use PostgreSQL + Mosquitto integration for real transport/storage behavior; scaffold unit PASS ≠ service operational.
- [QG-001..005] From `backend-go/`: run `gofmt -l .`, `go vet ./...`, `go test ./...`, `go test -race ./...` (runner supported) and approved `golangci-lint`, `govulncheck` if installed. **CI must assert empty output from `gofmt -l .`; its exit code alone is insufficient.** Report commands and actual evidence; otherwise `NOT_RUN`/`NOT_VERIFIED`.
- [AI-008..011, QG-006..008] Inspect diff, remove dead/speculative code, check secrets and scoped paths. Human review required; no self-approval/merge or unsupported RF/HIL/latency PASS.

## Final response required

[AI-012] Report: Issue/branch/base SHA; allowed paths and files changed; AC/invariants/errors; exact commands/results; contract/migration/security implications; open risks/`NOT_VERIFIED`; reviewers needed. Never claim implementation was built, tested, pushed or committed unless verified.