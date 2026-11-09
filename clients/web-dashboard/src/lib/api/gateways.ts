import type { GatewayStatus, GatewayItem, ChannelInfo } from "@/types/api";
import { apiFetch } from "./client.ts";

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
 * Retrieves all registered gateways directly from the database and live status reports via GET /api/v1/gateways.
 * Dynamically resolves names, locations, and channel mappings without hardcoded identifiers.
 */
export async function getGateways(): Promise<GatewayItem[]> {
  let channels: ChannelInfo[] = [];
  try {
    channels = await getChannels();
  } catch {
    // Ignore channel fetch error if offline
  }

  try {
    const rawList = await apiFetch<GatewayItem[] | GatewayItem>("/api/v1/gateways", {
      method: "GET",
    });
    const list = Array.isArray(rawList) ? rawList : (rawList ? [rawList] : []);

    return list.map((gw) => {
      const assignedChannel = channels.find(
        (c) => c.assigned_gateway_id === gw.gateway_id || c.channel_id === gw.channel_id
      );

      return {
        ...gw,
        name: gw.name || `Trạm ${gw.gateway_id}`,
        location: gw.location || "Khu vực chung",
        online: gw.mode !== "OFFLINE",
        operating: gw.mode === "ACTIVE" || gw.mode === "AUTONOMOUS",
        channel_id: assignedChannel?.channel_id || gw.channel_id || "CH00",
        frequency_hz: assignedChannel?.frequency_hz || gw.frequency_hz || 920250000,
      };
    });
  } catch {
    // If backend collection endpoint fails, fall back to channel allocations
    const results: GatewayItem[] = [];
    for (const ch of channels) {
      if (ch.assigned_gateway_id) {
        results.push({
          gateway_id: ch.assigned_gateway_id,
          name: `Trạm điều hành ${ch.assigned_gateway_id}`,
          location: "Khu vực chung",
          mode: "OFFLINE",
          active_schedule_version: 0,
          last_seen_at: null,
          rf_duty_permille: 0,
          node_count: 0,
          online: false,
          operating: false,
          channel_id: ch.channel_id,
          frequency_hz: ch.frequency_hz,
        });
      }
    }
    return results;
  }
}

export interface CreateGatewayInput {
  gateway_id: string;
  name: string;
  location?: string;
  ip_address?: string;
}

/**
 * Retrieves a single registered gateway by ID.
 */
export async function getGateway(gwId: string): Promise<GatewayItem | null> {
  try {
    const list = await getGateways();
    const found = list.find((g) => g.gateway_id === gwId);
    return found || null;
  } catch {
    return null;
  }
}

/**
 * Registers a new gateway in the system database via POST /api/v1/gateways.
 */
export async function createGateway(input: CreateGatewayInput): Promise<void> {
  await apiFetch<{ status: string; gateway_id: string }>("/api/v1/gateways", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
