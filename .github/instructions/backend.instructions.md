---
applyTo: "backend-go/**"
---
# Go Backend — AI Worker / Auditor Routing (v2 DRAFT lookup)

> **Routing policy ACTIVE when this change merges; Engineering Standard v2 itself `PROPOSED / NOT_APPROVED`.** Do not import draft-only rules as approved project decisions. This file supersedes the stale v1 replacement/pending-merge wording; [v1 reference](../../docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V1.0.md) is preserved read-only.

## Mandatory input
1. For a backend Issue, **MUST READ AND ASSESS** the applicable portions of [Go Backend Engineering Standard v2.0.0-DRAFT](../../docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V2.md): metadata, §0 routing, Google style §1, affected IDs §2, blocked decisions §3 and evidence §4. AI Auditor independently checks relevant IDs. Selective loading; do not blindly consume 134 rules for every change.
2. Load `AGENTS.md`, `.github/copilot-instructions.md`, Issue/AC/exact allowed paths, current source, `backend-go/go.mod`, root `.go-version`, approved ADRs and *versioned contracts with their actual approval states*. Check branch/worktree and composition root `backend-go/cmd/server/main.go` when wiring services.
3. Before coding: report `APPLICABLE_RULE_IDS`, `RULE_APPROVAL_STATUS`, `BLOCKED_DECISIONS`, `SOURCE_AUTHORITY`, `TARGET_PATHS`, `TEST_PLAN`; STOP if an extra file/test/migration or interface change lies outside approved scope.

## Higher-authority invariants (unchanged architectural intent)
- Go `1.27.3` is pinned in `backend-go/go.mod` and `.go-version`; match actual toolchain and CI, do not use floating dependencies or auto-upgrade. Do not claim a real build without logs.
- Go backend is a **Modular Monolith**, PostgreSQL, and MQTT **5.0** per ADR-0002; Gateway owns local real-time Hybrid TDMA execution. No cloud per-slot TX, LoRaWAN, ChirpStack, Redis, InfluxDB, Kafka, extra ORM/router or unapproved dependency. The v1 preferred package names `net/http`, `pgx/v5` and `eclipse/paho.golang` are *DRAFT adoption choices* unless separately approved and installed.
- Contract/version/DB changes require explicit Issue scope and producer/consumer review. `PUBACK != STAGE_ACK != ACTIVE_REPORT`. MQTT QoS1 at-least-once implies application-level idempotency; preserve event identity, bounded queues/retries and error handling.
- **Schedule reconciliation STOP:** v1 `MQ-009` suggested `PROPOSED/SENT/STAGED → ACTIVE`, but current **DRAFT** `contracts/mqtt/semantic-rules.md` §4 lists only `STAGED → ACTIVE`. Delayed `ACTIVE_REPORT` after `EXPIRED` remains unresolved. **Do not silently code any proposed early/late transition; report conflict and obtain Gateway/Backend decision.**
- **Poison QoS1 STOP:** v1's permanent-invalid ACK/quarantine and Paho callback/manual ACK handling are proposed until exact Paho dependency, protocol semantics and broker trace are reviewed. Never assume a callback-returned Go error sends MQTT NACK.
- REST/WSS AuthN/RBAC/token lifecycle D13 remains BLOCKED. Do not store/log secrets, skip server-side auth, interpolate untrusted SQL, treat CRC as RF authentication, or claim RF/HIL outcomes from Go CI.
- For Go style: Google [Guide](https://google.github.io/styleguide/go/guide) is canonical/normative, [Decisions](https://google.github.io/styleguide/go/decisions) normative/subordinate, [Best Practices](https://google.github.io/styleguide/go/best-practices) advisory. Follow `gofmt`, MixedCaps and sensible Go naming; use `%w` only when exposing inspected error chains is deliberate, otherwise translate/hide errors at boundaries.

## JSON boundary policy (Issue #41)
- [GO-006, CT-003/004, TS-003] Preserve existing outbound serialization with `encoding/json`. For new inbound JSON object DTOs, use `internal/jsonboundary.DecodeObject(payload, maxBytes, &dto)` with a caller-approved positive byte limit and typed struct fields. The stdlib `encoding/json/v2` rejects duplicate names, invalid UTF-8 and unknown struct members, with case-sensitive matching. Keep decimal identifiers as strings.
- Decode success does not establish JSON Schema conformance. Validate required fields, version, enum/range/regex, nullability and cross-field invariants before side effects. Do not wire this helper into services or choose MQTT ACK policy without a scoped implementation Issue. Do not log raw payloads or unredacted decoder errors.

## Verify and handoff
- Implement only a small correct vertical slice, explicitly bounded goroutines/timeouts, DB transactions and shutdown handling. Do not create speculative packages, interfaces, caches or frameworks.
- Run actual checks when available: version guard, `gofmt -l .` **empty stdout**, `go vet ./...`, `go test ./...`, `go test -race ./...`; use real PostgreSQL/Mosquitto integration when making those claims. `NOT_RUN` is not PASS, and scaffold tests do not verify end-to-end service.
- Inspect actual diff against Issue's allowed paths, verify secrets, and report Rule IDs, source conflicts, exact commands/outcomes, contract/security/migration implications and `NOT_VERIFIED` aspects. **Draft PR and human approval only**, never self-approve/merge.
