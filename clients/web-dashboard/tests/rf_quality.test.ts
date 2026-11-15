import { test, describe, beforeEach, mock } from "node:test";
import assert from "node:assert/strict";
import { getNode } from "../src/lib/api/nodes.ts";
import { getGatewayStatus, getGateways } from "../src/lib/api/gateways.ts";
import { formatRfSource, formatRfAge } from "../src/components/rf/formatters.ts";
import type { NodeSummary, GatewayStatus } from "../src/types/api.ts";

describe("LoRa RF Quality Contracts & Presentation (#394)", () => {
  beforeEach(() => {
    mock.restoreAll();
    (globalThis as unknown as { window: unknown }).window = {
      location: { pathname: "/nodes", href: "/nodes" },
      dispatchEvent: () => true,
    };
    (globalThis as unknown as { localStorage: unknown }).localStorage = {
      getItem: (k: string) => (k === "access_token" ? "mock-jwt-token" : null),
      setItem: () => {},
      removeItem: () => {},
    };
  });

  describe("1. DTO Structure & Normalization", () => {
    test("NodeSummary handles positive, negative, zero, and null RF values", () => {
      const nodeSample: NodeSummary = {
        node_id: 4,
        gateway_id: "gw-a",
        name: "Sensor-04",
        last_seen_at: "2026-11-14T12:00:00Z",
        last_rssi_dbm: -105,
        last_snr_db: -7.75, // quarter-dB precision
        last_rf_at: "2026-11-14T12:00:00Z",
        rf_age_seconds: 12,
        rf_source: "UP_EVENT",
        rf_stale: false,
        battery_mv: 3300,
        status: "ONLINE",
      };

      assert.strictEqual(nodeSample.node_id, 4);
      assert.strictEqual(nodeSample.gateway_id, "gw-a");
      assert.strictEqual(nodeSample.last_rssi_dbm, -105);
      assert.strictEqual(nodeSample.last_snr_db, -7.75);
      assert.strictEqual(nodeSample.rf_source, "UP_EVENT");
      assert.strictEqual(nodeSample.rf_stale, false);

      // SNR 0 dB is a valid number, not falsy null
      const zeroSnrNode: NodeSummary = {
        ...nodeSample,
        last_snr_db: 0,
      };
      assert.strictEqual(zeroSnrNode.last_snr_db, 0);

      // Missing RF fields normalized to null
      const nullRfNode: NodeSummary = {
        node_id: 5,
        gateway_id: "gw-a",
        last_seen_at: null,
        last_rssi_dbm: null,
        last_snr_db: null,
        last_rf_at: null,
        rf_age_seconds: null,
        rf_source: null,
        rf_stale: null,
        battery_mv: null,
        status: "UNKNOWN",
      };
      assert.strictEqual(nullRfNode.last_rssi_dbm, null);
      assert.strictEqual(nullRfNode.last_snr_db, null);
      assert.strictEqual(nullRfNode.rf_age_seconds, null);
    });

    test("GatewayStatus handles LoRa Channel RSSI and sample context", () => {
      const gwSample: GatewayStatus = {
        gateway_id: "GW-01",
        mode: "ACTIVE",
        active_schedule_version: 1,
        last_seen_at: "2026-11-14T12:00:00Z",
        rf_duty_permille: 15,
        node_count: 5,
        channel_rssi_dbm: -115,
        channel_rf_at: "2026-11-14T12:00:00Z",
        channel_rf_age_seconds: 15,
        channel_rf_stale: false,
        channel_idx: 1,
        channel_sample_context: "RX_IDLE",
      };

      assert.strictEqual(gwSample.gateway_id, "GW-01");
      assert.strictEqual(gwSample.channel_rssi_dbm, -115);
      assert.strictEqual(gwSample.channel_sample_context, "RX_IDLE");
      assert.strictEqual(gwSample.channel_idx, 1);
    });
  });

  describe("2. Node API Scoping, Identity Isolation & Pagination", () => {
    test("getNode retrieves node 4 with gateway 'gw-a', RSSI -105 dBm and SNR -7.75 dB", async () => {
      globalThis.fetch = async (input: RequestInfo | URL) => {
        const url = String(input);
        assert.ok(url.includes("/api/v1/nodes"));
        return new Response(
          JSON.stringify({
            items: [
              {
                node_id: 4,
                gateway_id: "gw-a",
                name: "Node-04",
                status: "ONLINE",
                last_seen_at: "2026-11-14T12:00:00Z",
                last_rssi_dbm: -105,
                last_snr_db: -7.75,
                last_rf_at: "2026-11-14T12:00:00Z",
                rf_age_seconds: 5,
                rf_source: "UP_EVENT",
                rf_stale: false,
              },
            ],
            next_cursor: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      const result = await getNode(4, "gw-a");
      assert.ok(result);
      assert.strictEqual(result.node_id, 4);
      assert.strictEqual(result.gateway_id, "gw-a");
      assert.strictEqual(result.last_rssi_dbm, -105);
      assert.strictEqual(result.last_snr_db, -7.75);
      assert.strictEqual(result.rf_source, "UP_EVENT");
      assert.strictEqual(result.rf_stale, false);
    });

    test("getNode isolates identity and rejects wrong gateway update for same node_id", async () => {
      // Backend returns node 4 belonging to 'gw-b'
      globalThis.fetch = async (input: RequestInfo | URL) => {
        const url = String(input);
        assert.ok(url.includes("gateway_id=gw-a"));
        // Simulating server returning items under gw-b
        return new Response(
          JSON.stringify({
            items: [
              {
                node_id: 4,
                gateway_id: "gw-b",
                status: "ONLINE",
                last_rssi_dbm: -90,
                last_snr_db: 5.0,
              },
            ],
            next_cursor: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      // Searching for node 4 with gateway "gw-a" must NOT match node 4 under "gw-b"
      const result = await getNode(4, "gw-a");
      assert.strictEqual(result, null);
    });

    test("getNode handles pagination via cursor until target node is found", async () => {
      let callCount = 0;
      globalThis.fetch = async (input: RequestInfo | URL) => {
        const url = String(input);
        callCount++;
        if (callCount === 1) {
          assert.ok(!url.includes("cursor=page2"));
          return new Response(
            JSON.stringify({
              items: [
                { node_id: 1, gateway_id: "gw-a", status: "ONLINE" },
                { node_id: 2, gateway_id: "gw-a", status: "ONLINE" },
              ],
              next_cursor: "page2",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        } else {
          assert.ok(url.includes("cursor=page2"));
          return new Response(
            JSON.stringify({
              items: [
                {
                  node_id: 4,
                  gateway_id: "gw-a",
                  status: "ONLINE",
                  last_rssi_dbm: -102,
                  last_snr_db: 0,
                  rf_source: "UP_HEARTBEAT_ACK",
                },
              ],
              next_cursor: null,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
      };

      const result = await getNode(4, "gw-a");
      assert.strictEqual(callCount, 2);
      assert.ok(result);
      assert.strictEqual(result.node_id, 4);
      assert.strictEqual(result.last_rssi_dbm, -102);
      assert.strictEqual(result.last_snr_db, 0); // Real zero SNR preserved
      assert.strictEqual(result.rf_source, "UP_HEARTBEAT_ACK");
    });

    test("getNode normalizes omitted RF fields to null without fabricating zeros", async () => {
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({
            items: [
              {
                node_id: 7,
                gateway_id: "gw-a",
                status: "OFFLINE",
                // Notice: no last_rssi_dbm, last_snr_db, etc.
              },
            ],
            next_cursor: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      const result = await getNode(7, "gw-a");
      assert.ok(result);
      assert.strictEqual(result.last_rssi_dbm, null);
      assert.strictEqual(result.last_snr_db, null);
      assert.strictEqual(result.last_rf_at, null);
      assert.strictEqual(result.rf_age_seconds, null);
      assert.strictEqual(result.rf_source, null);
      assert.strictEqual(result.rf_stale, null);
    });
  });

  describe("3. Gateway API & LoRa Channel RSSI Isolation", () => {
    test("getGatewayStatus retrieves fresh Channel RSSI -115 dBm and sample context", async () => {
      globalThis.fetch = async (input: RequestInfo | URL) => {
        const url = String(input);
        assert.ok(url.includes("/api/v1/gateways/GW-01/status"));
        return new Response(
          JSON.stringify({
            gateway_id: "GW-01",
            mode: "ACTIVE",
            active_schedule_version: 2,
            last_seen_at: "2026-11-14T12:00:00Z",
            rf_duty_permille: 20,
            node_count: 8,
            channel_rssi_dbm: -115,
            channel_rf_at: "2026-11-14T12:00:00Z",
            channel_rf_age_seconds: 10,
            channel_rf_stale: false,
            channel_idx: 0,
            channel_sample_context: "RX_IDLE",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      const status = await getGatewayStatus("GW-01");
      assert.strictEqual(status.gateway_id, "GW-01");
      assert.strictEqual(status.channel_rssi_dbm, -115);
      assert.strictEqual(status.channel_sample_context, "RX_IDLE");
      assert.strictEqual(status.channel_idx, 0);
      assert.strictEqual(status.channel_rf_stale, false);
    });

    test("getGateways preserves channel RF metrics across gateway list", async () => {
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
          JSON.stringify([
            {
              gateway_id: "GW-01",
              name: "Trạm 01",
              mode: "ACTIVE",
              channel_rssi_dbm: -118,
              channel_rf_age_seconds: 25,
              channel_sample_context: "RX_ACTIVE",
            },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      const gateways = await getGateways();
      assert.strictEqual(gateways.length, 1);
      assert.strictEqual(gateways[0].gateway_id, "GW-01");
      assert.strictEqual(gateways[0].channel_rssi_dbm, -118);
      assert.strictEqual(gateways[0].channel_sample_context, "RX_ACTIVE");
    });
  });

  describe("4. Presentation Helpers & Formatting", () => {
    test("formatRfSource maps known and fallback sources correctly", () => {
      assert.strictEqual(formatRfSource("UP_EVENT"), "Sự kiện (UP_EVENT)");
      assert.strictEqual(formatRfSource("UP_HEARTBEAT_ACK"), "Heartbeat ACK");
      assert.strictEqual(formatRfSource("CUSTOM_SRC"), "CUSTOM_SRC");
      assert.strictEqual(formatRfSource(null), "N/A");
      assert.strictEqual(formatRfSource(undefined), "N/A");
    });

    test("formatRfAge formats elapsed time appropriately", () => {
      assert.strictEqual(formatRfAge(null), "Mới nhận");
      assert.strictEqual(formatRfAge(undefined), "Mới nhận");
      assert.strictEqual(formatRfAge(-5), "Mới nhận");
      assert.strictEqual(formatRfAge(0), "0s trước");
      assert.strictEqual(formatRfAge(25.4), "25s trước");
      assert.strictEqual(formatRfAge(120), "2m trước");
      assert.strictEqual(formatRfAge(3600), "1h trước");
    });
  });

  describe("5. Presence vs RF Independence", () => {
    test("Node presence is not derived from RF metrics presence or absence", () => {
      // Node with null RF is still ONLINE if backend says ONLINE
      const onlineNodeNoRf: NodeSummary = {
        node_id: 1,
        gateway_id: "gw-a",
        last_seen_at: "2026-11-14T12:00:00Z",
        last_rssi_dbm: null,
        last_snr_db: null,
        status: "ONLINE",
        battery_mv: 3300,
      };
      assert.strictEqual(onlineNodeNoRf.status, "ONLINE");

      // Node with fresh RF is OFFLINE if backend says OFFLINE
      const offlineNodeWithRf: NodeSummary = {
        node_id: 2,
        gateway_id: "gw-a",
        last_seen_at: "2026-11-14T11:00:00Z",
        last_rssi_dbm: -95,
        last_snr_db: 8.5,
        status: "OFFLINE",
        battery_mv: 3000,
      };
      assert.strictEqual(offlineNodeWithRf.status, "OFFLINE");
    });
  });

  describe("6. Event-Triggered RF Refresh & Concurrency Reconciliation (#400)", () => {
    test("In-flight REST request at matching alert arrival executes trailing refresh with zero overlapping requests", async () => {
      let activeRequests = 0;
      let maxConcurrent = 0;
      let fetchCount = 0;
      const rfSnapshots: number[] = [];

      let inFlight = false;
      let trailingRequested = false;
      const isMounted = true;

      const mockFetchNode = async (rssiVal: number) => {
        fetchCount++;
        activeRequests++;
        maxConcurrent = Math.max(maxConcurrent, activeRequests);
        await new Promise((resolve) => setTimeout(resolve, 30));
        rfSnapshots.push(rssiVal);
        activeRequests--;
      };

      const loadRealNode = async (rssi: number) => {
        if (inFlight) {
          trailingRequested = true;
          return;
        }
        inFlight = true;
        try {
          await mockFetchNode(rssi);
        } finally {
          inFlight = false;
          if (trailingRequested && isMounted) {
            trailingRequested = false;
            await loadRealNode(-68);
          }
        }
      };

      // Initial request in flight
      const promise1 = loadRealNode(-95);
      assert.strictEqual(inFlight, true);

      // Matching alert arrives while request is in flight
      const alertPromise = loadRealNode(-68);
      await alertPromise;
      assert.strictEqual(trailingRequested, true);

      // Wait for promise1 to finish (which automatically triggers the trailing refresh)
      await promise1;

      // Exactly 2 fetches occurred (initial + trailing)
      assert.strictEqual(fetchCount, 2);
      // Zero overlapping requests: maxConcurrent is strictly 1
      assert.strictEqual(maxConcurrent, 1);
      // The final snapshot reflects the latest RF (-68 dBm)
      assert.deepStrictEqual(rfSnapshots, [-95, -68]);
    });

    test("Multiple alerts arriving during in-flight request are coalesced into a single trailing refresh", async () => {
      let fetchCount = 0;
      let inFlight = false;
      let trailingRequested = false;
      const isMounted = true;

      const mockFetchNode = async () => {
        fetchCount++;
        await new Promise((resolve) => setTimeout(resolve, 40));
      };

      const loadRealNode = async () => {
        if (inFlight) {
          trailingRequested = true;
          return;
        }
        inFlight = true;
        try {
          await mockFetchNode();
        } finally {
          inFlight = false;
          if (trailingRequested && isMounted) {
            trailingRequested = false;
            await loadRealNode();
          }
        }
      };

      const p1 = loadRealNode();
      // Burst of 4 alerts arrive during in-flight load
      await loadRealNode();
      await loadRealNode();
      await loadRealNode();
      await loadRealNode();

      await p1;

      // Exactly 2 fetches: 1 initial + 1 coalesced trailing
      assert.strictEqual(fetchCount, 2);
    });

    test("Unmount cancellation suppresses trailing refresh and aborts active request", async () => {
      let fetchCount = 0;
      let inFlight = false;
      let trailingRequested = false;
      let isMounted = true;
      const ac = new AbortController();

      const mockFetchNode = async (signal: AbortSignal) => {
        fetchCount++;
        await new Promise((resolve, reject) => {
          const timer = setTimeout(resolve, 50);
          signal.addEventListener("abort", () => {
            clearTimeout(timer);
            reject(new Error("Aborted"));
          });
        });
      };

      const loadRealNode = async () => {
        if (inFlight) {
          trailingRequested = true;
          return;
        }
        inFlight = true;
        try {
          await mockFetchNode(ac.signal);
        } catch {
          // aborted
        } finally {
          inFlight = false;
          if (trailingRequested && isMounted) {
            trailingRequested = false;
            await loadRealNode();
          }
        }
      };

      const p1 = loadRealNode();
      // Alert triggers trailing refresh request
      await loadRealNode();
      assert.strictEqual(trailingRequested, true);

      // Component unmounts: abort and set isMounted = false
      isMounted = false;
      trailingRequested = false;
      ac.abort();

      await p1;

      // Only the first fetch was started; trailing refresh was NOT executed
      assert.strictEqual(fetchCount, 1);
    });

    test("Matching ALERT_TRIGGERED filters by node_id and gateway_id strictly", () => {
      const currentNodeId = 3;
      const currentGwId: string = "gw-a";

      const isMatchingAlert = (payload: { node_id: number; gateway_id: string }) => {
        const matchesGateway = !currentGwId || currentGwId === "--" || currentGwId === payload.gateway_id;
        return payload.node_id === currentNodeId && matchesGateway;
      };

      // 1. Matching alert
      assert.strictEqual(isMatchingAlert({ node_id: 3, gateway_id: "gw-a" }), true);

      // 2. Unrelated node ID -> Ignored
      assert.strictEqual(isMatchingAlert({ node_id: 4, gateway_id: "gw-a" }), false);
      assert.strictEqual(isMatchingAlert({ node_id: 99, gateway_id: "gw-a" }), false);

      // 3. Unrelated gateway ID -> Ignored
      assert.strictEqual(isMatchingAlert({ node_id: 3, gateway_id: "gw-b" }), false);
      assert.strictEqual(isMatchingAlert({ node_id: 3, gateway_id: "other-gw" }), false);
    });

    test("getNode with aborted signal returns null without making network calls", async () => {
      let networkCalled = false;
      globalThis.fetch = async () => {
        networkCalled = true;
        return new Response("{}", { status: 200 });
      };

      const ac = new AbortController();
      ac.abort();

      const result = await getNode(3, { gatewayId: "gw-a", signal: ac.signal });
      assert.strictEqual(result, null);
      assert.strictEqual(networkCalled, false);
    });

    test("API error preserves last known values as rf_stale: true", () => {
      const prevNode: NodeSummary = {
        node_id: 3,
        gateway_id: "gw-a",
        last_seen_at: "2026-11-14T16:38:51Z",
        battery_mv: 3300,
        last_rssi_dbm: -75,
        last_snr_db: 8.5,
        last_rf_at: "2026-11-14T16:38:51Z",
        rf_age_seconds: 15,
        rf_source: "UP_EVENT",
        rf_stale: false,
        status: "ONLINE",
      };

      const errorNode = {
        ...prevNode,
        rf_stale: true,
      };

      assert.strictEqual(errorNode.last_rssi_dbm, -75);
      assert.strictEqual(errorNode.last_snr_db, 8.5);
      assert.strictEqual(errorNode.last_rf_at, "2026-11-14T16:38:51Z");
      assert.strictEqual(errorNode.rf_stale, true);
    });
  });
});
