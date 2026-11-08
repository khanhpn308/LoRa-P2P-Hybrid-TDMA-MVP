import { test, describe, beforeEach, mock } from "node:test";
import assert from "node:assert/strict";
import { login, getWsTicket } from "../src/lib/api/auth.ts";
import { getNodes, getNode } from "../src/lib/api/nodes.ts";
import { getAlerts, acknowledgeAlert } from "../src/lib/api/alerts.ts";
import { getGatewayStatus, getChannels, getGateways } from "../src/lib/api/gateways.ts";
import { provisionDevice } from "../src/lib/api/provisioning.ts";
import { getWsBaseUrl } from "../src/lib/realtime/useWebSocketHub.ts";

describe("Web Integration Services & Realtime Contracts", () => {
  beforeEach(() => {
    mock.restoreAll();
    (globalThis as unknown as { window: unknown }).window = {
      location: { pathname: "/monitoring", href: "/monitoring" },
      dispatchEvent: () => true,
    };
    (globalThis as unknown as { localStorage: unknown }).localStorage = {
      getItem: (k: string) => (k === "access_token" ? "valid-jwt-token" : null),
      setItem: () => {},
      removeItem: () => {},
    };
  });

  test("POST /api/v1/auth/login handles valid credentials (ADR-0005)", async () => {
    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      assert.strictEqual(init?.method, "POST");
      assert.ok(String(input).includes("/api/v1/auth/login"));
      return new Response(
        JSON.stringify({
          access_token: "jwt-token-admin01-session",
          token_type: "Bearer",
          expires_in: 3600,
          role: "ADMIN",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    };

    const resp = await login({ username: "admin01", password: "password123" });
    assert.strictEqual(resp.access_token, "jwt-token-admin01-session");
    assert.strictEqual(resp.role, "ADMIN");
    assert.strictEqual(resp.expires_in, 3600);
  });

  test("POST /api/v1/auth/ws-ticket requests single-use handshake ticket", async () => {
    let capturedAuth: string | null = null;
    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      assert.strictEqual(init?.method, "POST");
      assert.ok(String(input).includes("/api/v1/auth/ws-ticket"));
      const headers = new Headers(init?.headers);
      capturedAuth = headers.get("Authorization");
      return new Response(
        JSON.stringify({
          ticket: "f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2",
          expires_in: 30,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    };

    const ticketResp = await getWsTicket();
    assert.strictEqual(capturedAuth, "Bearer valid-jwt-token");
    assert.strictEqual(ticketResp.ticket.length, 64);
    assert.strictEqual(ticketResp.expires_in, 30);
  });

  test("getWsBaseUrl correctly converts http to ws", () => {
    const wsUrl = getWsBaseUrl();
    assert.ok(wsUrl.startsWith("ws://") || wsUrl.startsWith("wss://"));
  });

  test("GET /api/v1/nodes returns confirmed nodes list", async () => {
    globalThis.fetch = async (input: RequestInfo | URL) => {
      assert.ok(String(input).includes("/api/v1/nodes"));
      return new Response(
        JSON.stringify({
          items: [
            {
              node_id: 12,
              gateway_id: "GW-01",
              name: "Node-12",
              assigned_slot_id: 2,
              last_seen_at: "2026-11-08T03:00:00Z",
              status: "ONLINE",
            },
          ],
          next_cursor: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    };

    const page = await getNodes({ limit: 10 });
    assert.strictEqual(page.items.length, 1);
    assert.strictEqual(page.items[0].node_id, 12);
    assert.strictEqual(page.items[0].status, "ONLINE");

    const single = await getNode(12);
    assert.ok(single);
    assert.strictEqual(single?.node_id, 12);
  });

  test("GET /api/v1/alerts and POST /api/v1/alerts/{id}/acknowledge flow", async () => {
    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const urlStr = String(input);
      if (urlStr.includes("/acknowledge")) {
        assert.strictEqual(init?.method, "POST");
        return new Response(
          JSON.stringify({
            alert_id: "101",
            node_id: 12,
            gateway_id: "GW-01",
            event_ref: 1,
            event_code: 1,
            event_value: 850,
            severity: "P0_EMERGENCY",
            triggered_at: "2026-11-08T03:00:00Z",
            received_at: "2026-11-08T03:00:01Z",
            ack_status: "ACKNOWLEDGED",
            acked_at: "2026-11-08T03:05:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response(
        JSON.stringify({
          items: [
            {
              alert_id: "101",
              node_id: 12,
              gateway_id: "GW-01",
              event_ref: 1,
              event_code: 1,
              event_value: 850,
              severity: "P0_EMERGENCY",
              triggered_at: "2026-11-08T03:00:00Z",
              received_at: "2026-11-08T03:00:01Z",
              ack_status: "UNACKNOWLEDGED",
              acked_at: null,
            },
          ],
          next_cursor: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    };

    const alerts = await getAlerts();
    assert.strictEqual(alerts.items.length, 1);
    assert.strictEqual(alerts.items[0].ack_status, "UNACKNOWLEDGED");

    const acked = await acknowledgeAlert("101", "operator");
    assert.strictEqual(acked.ack_status, "ACKNOWLEDGED");
  });

  test("POST /api/v1/devices/provision submits key registration payload", async () => {
    let capturedBody = "";
    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      assert.strictEqual(init?.method, "POST");
      assert.ok(String(input).includes("/api/v1/devices/provision"));
      capturedBody = String(init?.body);
      return new Response(
        JSON.stringify({
          device_mac: "e45f0134bc09",
          network_id: 1,
          generation: 1,
          status: "PROVISIONED",
          created_at: "2026-11-08T03:00:00Z",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    };

    const res = await provisionDevice({
      network_id: 1,
      device_mac: "e45f0134bc09",
      k_join: "0102030405060708090a0b0c0d0e0f10",
      generation: 1,
    });

    assert.strictEqual(res.status, "PROVISIONED");
    assert.strictEqual(res.device_mac, "e45f0134bc09");
    assert.ok(capturedBody.includes('"device_mac":"e45f0134bc09"'));
  });

  test("GET /api/v1/gateways/{id}/status and channels aggregation", async () => {
    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/channels")) {
        return new Response(
          JSON.stringify([
            {
              channel_id: "CH01",
              frequency_hz: 920500000,
              bandwidth_hz: 125000,
              status: "ALLOCATED",
              assigned_gateway_id: "GW-01",
            },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response(
        JSON.stringify({
          gateway_id: "GW-01",
          mode: "ACTIVE",
          active_schedule_version: 3,
          last_seen_at: "2026-11-08T03:00:00Z",
          rf_duty_permille: 12,
          node_count: 5,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    };

    const status = await getGatewayStatus("GW-01");
    assert.strictEqual(status.mode, "ACTIVE");
    assert.strictEqual(status.active_schedule_version, 3);

    const channels = await getChannels();
    assert.strictEqual(channels.length, 1);
    assert.strictEqual(channels[0].channel_id, "CH01");

    const gws = await getGateways();
    assert.ok(gws.length > 0);
    const gw01 = gws.find((g) => g.gateway_id === "GW-01");
    assert.ok(gw01);
    assert.strictEqual(gw01?.online, true);
    assert.strictEqual(gw01?.operating, true);
  });
});
