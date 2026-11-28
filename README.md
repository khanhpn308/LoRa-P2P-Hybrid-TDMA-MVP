# LoRa P2P Hybrid TDMA — MVP

**Status: MONOREPO FOUNDATION / NOT PRODUCTION READY.**

**MVP architecture:** Multi-Gateway Star (1–4 ESP32 + SX1276 Gateways), separate operating channels at LoRa BW 125 kHz; Node fixed to one Gateway/channel, no Mesh. Backend Go prepares schedules for User approval; Gateways validate and execute TDMA locally. Wi-Fi/MQTT 5.0/TLS (Mosquitto) connects Gateways to Go Modular Monolith + PostgreSQL. Web/Mobile are part of MVP. Architecture and remaining verification gaps: [System overview](docs/architecture/system-overview.md).

Owner direction dated 2026-11-04 ([#125](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/125), docs child [#126](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/126)): **Local Alarm + Event-Only Remote Logging + Static TDMA + Maintenance Superframe**. A Node raises its local alarm independently of radio delivery and persists Events in a bounded FIFO. It transmits only when an Event is pending, within its approved DATA slot, then receives the Gateway ACK in that slot. The Gateway ACK confirms durable Gateway acceptance, not Backend DB commit. Missing ACK retries the same Event in the next valid own slot; exhausted retries retain durable pending for recovery. Retry limits and FIFO overflow policy remain OPEN.

Scheduled Maintenance Superframes between DATA Superframes target a **300 s** sync/heartbeat interval: authenticated `SYNC_BEACON` followed by each Node's nonoverlapping `HEALTH_REPLY` slot. Beacon transmission alone does not prove a Node is alive. DATA/ACK/JOIN/RECOVERY and maintenance must share the single half-duplex radio safely. Timing, drift/guard/holdover/offline thresholds and wire compatibility remain `NOT_VERIFIED`. Gateway-origin Event ID and its durable RF-identity mapping remain in force; Node queue identity across reboot/retry needs G2 review. The former periodic business flow and contention access policy are superseded, with [approval history](docs/architecture/system-overview.md#7-lịch-sử-thay-thế-và-phạm-vi-migration). Firmware/backend remain scaffolds; contract/schema migration is tracked separately under #125.

## Repository map

- [Architecture](docs/architecture/system-overview.md) and [requirements](docs/requirements/requirements.md)
- [Radio MAC](contracts/radio-mac/specification.md), [MQTT topics](contracts/mqtt/topics.md), [OpenAPI](contracts/api/openapi.yaml)
- `firmware/gateway_master` and `firmware/sensor_node` — minimal ESP-IDF **scaffolds, not radio implementations**
- `backend-go` — minimal Go scaffold; no MQTT/TDMA implementation yet
- `simulator` — model/test planning, **not a verified digital twin**
- `clients` — placeholders until web/mobile work begins
- [Acceptance gates](docs/verification/acceptance-gates.md), [coding standards](docs/development/coding-standards.md) and [Vietnamese Monorepo Handbook](docs/development/monorepo-guide.md)
- [Pre-Task-Breakdown Readiness](docs/development/task-breakdown-readiness.md) — Gate field, CODEOWNERS and Path-Scoped Issues
- [Harness V2 Advanced Pack Index](docs/harness/ADVANCED_PACK.md), [Quality Score & Debt](docs/QUALITY_SCORE.md), and [Generated DB Schema Metadata](docs/generated/db-schema.md) (`SOURCE_DERIVED_ONLY`)

## ESP-IDF toolchain baseline — v6.1

**Approved ESP-IDF release for both Gateway and Node: `v6.1`.** The authoritative repository value is [`firmware/esp-idf-version.txt`](firmware/esp-idf-version.txt), documented in [ADR-0003](docs/adr/0003-esp-idf-v6-1.md). Firmware CI and the Agent Harness read this version instead of independently selecting toolchains. Build success does not establish SX1276/HIL/RF/timing correctness. Do not use floating `release-v6.1` or `latest`.

## Development

Use GitHub Issues + Project, one feature branch and reviewed PR per change. Changes to `contracts/` require cross-component impact review. `.github/CODEOWNERS` initially nominates the repository owner until all six collaborator usernames are assigned.

Read `.env.example` before local services: production credentials and TLS private keys must never enter Git. **No** ChirpStack/LoRaWAN Gateway/OTAA implementation in this MVP.

### Scaffold validation

- `python3 scripts/verify_structure.py`
- `cd backend-go && go test ./...`
- `cd firmware/gateway_master && idf.py set-target esp32 && idf.py build` (configured ESP-IDF environment)
- `cd firmware/sensor_node && idf.py set-target esp32 && idf.py build`

The buildable scaffolds do not transmit RF or claim working TDMA. Validate timing, security, RF compliance, power and latency with hardware and documented test evidence **before** approving any performance claims.

### Repository migration

Existing experimental firmware lives separately in `khanhpn308/esp32e_sx1768-915Mhz`. **It has not been copied.** Import after inventory/security review, via separate PR preserving provenance and license notices.

### Go backend version policy

**Pinned toolchain: Go 1.27.3.** Root [`.go-version`](.go-version) records the local development selection; [`backend-go/go.mod`](backend-go/go.mod) requires the same patch release; [backend CI](.github/workflows/ci-backend.yml) installs and checks the exact version with `GOTOOLCHAIN=local`. Verify `go version` prints `go1.27.3` before running backend checks. This is a Go-only change; the ESP-IDF firmware toolchain is independent.

[Go Backend Engineering Standard v1.0](docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V1.0.md) and [backend AI instructions](.github/instructions/backend.instructions.md) are **DRAFT, pending human technical review**.
