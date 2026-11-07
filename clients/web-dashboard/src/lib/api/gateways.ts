import type { GatewayStatus, GatewayItem, ChannelInfo } from "@/types/api";
import { apiFetch } from "./client.ts";

/**
 * Known default gateways in the TDMA MVP deployment.
 */
export const KNOWN_GATEWAY_IDS = [
  "GW-01",
  "GW-02",
  "GW-03",
  "GW-04",
  "GW-05",
];

/**
 * Fetches the operational state of a specific gateway via GET /api/v1/gateways/{gw_id}/status.
 */
export async function getGatewayStatus(gwId: string): Promise<GatewayStatus> {
  return apiFetch<GatewayStatus>(`/api/v1/gateways/${gwId}/status`, {
    method: "GET",
  });
}

/**
 * Fetches available VN920_V1 RF channels via GET /api/v1/channels.
 */
export async function getChannels(): Promise<ChannelInfo[]> {
  return apiFetch<ChannelInfo[]>("/api/v1/channels", {
    method: "GET",
  });
}

/**
 * Aggregates known gateways with their backend status and channel mappings.
 */
export async function getGateways(): Promise<GatewayItem[]> {
  let channels: ChannelInfo[] = [];
  try {
    channels = await getChannels();
  } catch {
    // Ignore channel fetch error if offline
  }

  const results: GatewayItem[] = [];

  for (const gwId of KNOWN_GATEWAY_IDS) {
    try {
      const status = await getGatewayStatus(gwId);
      const assignedChannel = channels.find((c) => c.assigned_gateway_id === gwId);

      results.push({
        ...status,
        name: `Trạm điều hành ${gwId}`,
        online: status.mode !== "OFFLINE",
        operating: status.mode === "ACTIVE" || status.mode === "AUTONOMOUS",
        channel_id: assignedChannel?.channel_id || "CH01",
        frequency_hz: assignedChannel?.frequency_hz || 920500000,
      });
    } catch {
      // If gateway has never reported, provide default entry
      results.push({
        gateway_id: gwId,
        mode: "OFFLINE",
        active_schedule_version: 0,
        last_seen_at: null,
        rf_duty_permille: 0,
        node_count: 0,
        name: `Trạm điều hành ${gwId}`,
        online: false,
        operating: false,
        channel_id: "CH01",
        frequency_hz: 920500000,
      });
    }
  }

  return results;
}
