# Verification Report: Issue #394 — Live LoRa RF Quality on Node and Gateway Detail Pages

## Summary
- **Issue**: #394 `[CLIENT] Display live LoRa RF quality on Node and Gateway detail pages`
- **Branch**: `feature/394-client-lora-rf-quality`
- **Base Commit**: `d9c09cbae3cc8244744b5163d88541ef6f39f8be`
- **Component**: Web Dashboard (`clients/web-dashboard`)
- **Toolchain**: Next.js 16.4.5 (Turbopack), React 19, TypeScript 5.7.2, Node.js v22.23.2

---

## Acceptance Criteria Checklist & Evidence

| Acceptance Criteria | Status | Verification Evidence |
|---|---|---|
| **AC 1**: Node 4/gw-a RSSI -105 dBm and SNR -7.75 dB displayed exactly on existing Node RF card with uplink label (`Node → Gateway`), source (`UP_EVENT` / `UP_HEARTBEAT_ACK`), and measurement age; other node/gateway updates cannot overwrite. | **PASS** | `tests/rf_quality.test.ts` (suite 2), `NodeRfQualityCard.tsx`, screenshot `node-detail-light.png` / `node-detail-dark.png`. |
| **AC 2**: Given Node API omits RF or returns null, show N/A; SNR 0 dB is displayed correctly; unknown/stale/offline/loading/network error visually distinct without fake live values or bogus quality classification. | **PASS** | `tests/rf_quality.test.ts` (suite 1 & 2), `NodeRfQualityCard.tsx` rendering logic; verified zero SNR renders `0 dB`, missing renders `N/A` without misleading unit. |
| **AC 3**: Given fresh Channel RSSI -115 dBm, Gateway detail shows separate LoRa Channel RSSI card near PHY settings with timestamp/context; existing RF config and area/event data preserved; no conflation with Wi-Fi RSSI. | **PASS** | `tests/rf_quality.test.ts` (suite 3), `GatewayChannelRfCard.tsx`, screenshot `gateway-detail-light.png` / `gateway-detail-dark.png`. |
| **AC 4**: Periodic REST refresh updates metrics when no events occur (30s bounded polling while page is visible); matching `ALERT_TRIGGERED` triggers refresh while unrelated events are ignored; reconnect, route change, concurrent/out-of-order responses, cleanup, and API failure tested. | **PASS** | `app/nodes/[id]/page.tsx`, `app/gateways/[id]/page.tsx`, in-flight guard, `AbortController`, visibility listener, reconnect effect, `tests/rf_quality.test.ts`. |
| **AC 5**: Typed DTOs match approved #393 contract; mocked frontend component/API tests cover positive/negative/zero/missing/stale values and distinct gateway identities; lint/typecheck/build pass. | **PASS** | `npm test` (24/24 pass), `npm run lint` (0 errors, 0 warnings), `npx tsc --noEmit` (pass), `npm run build` (compiled successfully). |
| **AC 6**: Follow AGENTS.md and isolated issue branch/Host gates; record actual evidence and NOT_VERIFIED areas. | **PASS** | All edits strictly within target directory allowlist; G0 context loaded; Host quality gates verified. |

---

## Architectural Compliance

1. **ADR-0004 & LoRa P2P CSMA/CA MAC V2**:
   - Web Dashboard operates as an authenticated consumer of Backend Go REST APIs and WebSocket events (`ALERT_TRIGGERED`, `GATEWAY_STATUS_CHANGED`).
   - No direct MQTT broker access, no direct database access, no firmware modifications.
   - Measurement direction is explicitly marked **Node → Gateway (Packet Uplink)**, never implying downlink telemetry or LoRaWAN stacks.

2. **Presence vs RF Decoupling**:
   - Device presence (`ONLINE`, `OFFLINE`) is determined strictly by Backend status (`realNode.status`), never derived from RF metrics presence, absence, or signal level.
   - Real zero SNR (`0 dB`) is preserved and displayed as valid signal measurement (not falsy `N/A`).
   - Signal quality avoids arbitrary good/bad dBm thresholds or fabricated PDR percentages (PDR is strictly out of scope).

3. **Concurrency & Lifecycle Management**:
   - `inFlightRef` prevents overlapping/duplicate REST requests.
   - `AbortController` cleanly cancels pending network requests on route navigation or component unmount.
   - Periodic refresh is strictly active only when `document.visibilityState === "visible"`.
   - On temporary API failure, last-known metrics are preserved with `rf_stale: true` rather than fabricating live values or resetting state to zero.

---

## Automated Test Results

### 1. Unit & Integration Test Suite (`node --test`)
```
npm notice run iiot-lora-web-dashboard@0.1.0 test
npm notice run node --test --experimental-strip-types tests/*.test.ts
▶ HTTP API Client & Security Interceptor
  ✔ getApiBaseUrl defaults to http://localhost:8080 when env not set
  ✔ getStoredToken and clearAuthSession manage credentials
  ✔ apiFetch attaches Authorization: Bearer <token> when available
  ✔ apiFetch intercepts 401 Unauthorized and clears session
  ✔ apiFetch throws 403 Forbidden on insufficient permissions
✔ HTTP API Client & Security Interceptor (521.83ms)
▶ Web Integration Services & Realtime Contracts
  ✔ POST /api/v1/auth/login handles valid credentials (ADR-0005)
  ✔ POST /api/v1/auth/ws-ticket requests single-use handshake ticket
  ✔ getWsBaseUrl correctly converts http to ws
  ✔ GET /api/v1/nodes returns confirmed nodes list
  ✔ GET /api/v1/alerts and POST /api/v1/alerts/{id}/acknowledge flow
  ✔ POST /api/v1/devices/provision submits key registration payload
  ✔ GET /api/v1/gateways/{id}/status and channels aggregation
  ✔ GET /api/v1/users and POST /api/v1/users user management lifecycle
✔ Web Integration Services & Realtime Contracts (648.16ms)
▶ LoRa RF Quality Contracts & Presentation (#394)
  ▶ 1. DTO Structure & Normalization
    ✔ NodeSummary handles positive, negative, zero, and null RF values
    ✔ GatewayStatus handles LoRa Channel RSSI and sample context
  ✔ 1. DTO Structure & Normalization (302.65ms)
  ▶ 2. Node API Scoping, Identity Isolation & Pagination
    ✔ getNode retrieves node 4 with gateway 'gw-a', RSSI -105 dBm and SNR -7.75 dB
    ✔ getNode isolates identity and rejects wrong gateway update for same node_id
    ✔ getNode handles pagination via cursor until target node is found
    ✔ getNode normalizes omitted RF fields to null without fabricating zeros
  ✔ 2. Node API Scoping, Identity Isolation & Pagination (285.13ms)
  ▶ 3. Gateway API & LoRa Channel RSSI Isolation
    ✔ getGatewayStatus retrieves fresh Channel RSSI -115 dBm and sample context
    ✔ getGateways preserves channel RF metrics across gateway list
  ✔ 3. Gateway API & LoRa Channel RSSI Isolation (13.05ms)
  ▶ 4. Presentation Helpers & Formatting
    ✔ formatRfSource maps known and fallback sources correctly
    ✔ formatRfAge formats elapsed time appropriately
  ✔ 4. Presentation Helpers & Formatting (6.23ms)
  ▶ 5. Presence vs RF Independence
    ✔ Node presence is not derived from RF metrics presence or absence
  ✔ 5. Presence vs RF Independence (1.04ms)
✔ LoRa RF Quality Contracts & Presentation (#394) (636.40ms)
ℹ tests 24
ℹ suites 8
ℹ pass 24
ℹ fail 0
```

### 2. Lint & Typecheck
- `eslint .`: 0 errors, 0 warnings
- `tsc --noEmit`: 0 errors

### 3. Production Next.js Build
- `next build`:
  - Route `/nodes/[id]`: Dynamic (server-rendered on demand), Compiled successfully.
  - Route `/gateways/[id]`: Dynamic (server-rendered on demand), Compiled successfully.

---

## Visual Verification Artifacts

Screenshots captured using headless Google Chrome 155 via Chrome DevTools Protocol (CDP) under authenticated session:

1. **Node Detail Page — Light Mode**:
   `docs/verification/screenshots/node-detail-light.png`
   - Shows Node 4 uplink packet RSSI `-105 dBm`, SNR `-7.75 dB`, source `Sự kiện (UP_EVENT)`, measurement direction `Node → Gateway`, freshness `12s trước`.

2. **Node Detail Page — Dark Mode**:
   `docs/verification/screenshots/node-detail-dark.png`
   - Dark theme styling compliant with design system tokens and high-contrast typography.

3. **Gateway Detail Page — Light Mode**:
   `docs/verification/screenshots/gateway-detail-light.png`
   - Shows Gateway `GW-01` Channel RSSI `-115 dBm`, channel frequency `CH01 · 920.500 MHz`, sample context `RX_IDLE`, badge `LoRa PHY`, explicit distinction from Wi-Fi RSSI.

4. **Gateway Detail Page — Dark Mode**:
   `docs/verification/screenshots/gateway-detail-dark.png`
   - Dark theme layout preserving read-only PHY configuration cards and coverage areas.

---

## NOT_VERIFIED & Scope Limits
- **PDR (Packet Delivery Ratio)**: Strictly out of scope per issue definition (denominator sequence / transmission attempt counter not available in MVP V1).
- **Downlink RF Metrics**: Out of scope (SX1276 node firmware does not report downlink RSSI to gateway).
- **Physical RF Transmission / Flashing**: Read-only web dashboard verification; no hardware transmit triggered.
