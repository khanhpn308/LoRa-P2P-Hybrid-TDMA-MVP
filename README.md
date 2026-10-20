# LoRa P2P Hybrid TDMA — MVP

**Status: MONOREPO FOUNDATION / NOT PRODUCTION READY.**

One ESP32 + SX1276 gateway is both LoRa P2P packet bridge and **local TDMA Master** for 10–15 ESP32 + SX1276 sensor nodes. Go plans/version-controls schedules; Gateway validates and executes them without per-slot MQTT commands. Backhaul: Wi-Fi → Mosquitto MQTT → Go modular monolith → PostgreSQL; clients are React/TypeScript and (later) Flutter.

## Repository map

- [Architecture](docs/architecture/system-overview.md) and [requirements](docs/requirements/requirements.md)
- [Radio MAC](contracts/radio-mac/specification.md), [MQTT topics](contracts/mqtt/topics.md), [OpenAPI](contracts/api/openapi.yaml)
- `firmware/gateway_master` and `firmware/sensor_node` — minimal ESP-IDF **scaffolds, not radio implementations**
- `backend-go` — minimal Go scaffold; no MQTT/TDMA implementation yet
- `simulator` — model/test planning, **not a verified digital twin**
- `clients` — placeholders until web/mobile work begins
- [Acceptance gates](docs/verification/acceptance-gates.md), [coding standards](docs/development/coding-standards.md) and [Vietnamese Monorepo Handbook](docs/development/monorepo-guide.md)

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
