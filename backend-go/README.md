# Backend Go

**Scaffold only.** Go executable currently logs that business services are not yet implemented. Run `go test ./...` and `go run ./cmd/server` locally. No API endpoint, scheduler, MQTT client or database is active.

Architecture target: modular monolith with `internal/{domain,mqtt,scheduler,telemetry,alert,api,storage}`.

Under [#125](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/125), the target is Event-only remote logging with Gateway-origin Event IDs, durable dedup and replay/conflict handling. The Planner versions static DATA and Maintenance schedules for User approval; Gateway executes them locally. Maintenance targets 300s SYNC_BEACON (32B HMAC) and per-Node HEALTH_REPLY; Beacon transmission alone does not establish Node alive (N_MISSED > 3 disconnect observation). Periodic measurement publishing and SET_PERIODIC_MODE are superseded business flows. Existing `telemetry` package naming is retained; versioned MQTT/API/DB compatibility remains pending [#128](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/128)/[#132](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/132), with no new runtime implementation here.

## Go toolchain lock

- **Go 1.27.3 is required** for backend development, tests and CI. Root `.go-version` and `backend-go/go.mod` must match exactly.
- Verify with `go version` (expected `go1.27.3`) before `go test ./...` and `go run ./cmd/server`. In CI, `GOTOOLCHAIN=local` prevents silent toolchain downloads/upgrades.
- The Go Engineering Standard is at [docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V1.0.md](../docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V1.0.md) (**DRAFT**, human review pending). Backend AI rules live at [backend.instructions.md](../.github/instructions/backend.instructions.md).
- This version change does **not** implement MQTT, PostgreSQL, API or TDMA services; integration compatibility remains **NOT_VERIFIED**.
