import type { NodeSummary, PageResponse } from "@/types/api";
import { apiFetch } from "./client.ts";

export interface ListNodesParams {
  limit?: number;
  cursor?: string;
  gateway_id?: string;
}

export interface DeviceJoinRequestDTO {
  id: number;
  device_mac: string;
  gateway_id: string;
  rssi: number;
  snr: number;
  status: "PENDING" | "APPROVED" | "REJECTED";
  assigned_node_id?: number | null;
  created_at: string;
  updated_at: string;
}

/**
 * Fetches the confirmed list of nodes reporting health via GET /api/v1/nodes.
 * Conforms to OpenAPI 3.0.3 and Event-Only V2 architecture.
 */
export async function getNodes(
  params?: ListNodesParams,
  options?: { signal?: AbortSignal }
): Promise<PageResponse<NodeSummary>> {
  return apiFetch<PageResponse<NodeSummary>>("/api/v1/nodes", {
    method: "GET",
    signal: options?.signal,
    params: params
      ? {
          limit: params.limit,
          cursor: params.cursor,
          gateway_id: params.gateway_id,
        }
      : undefined,
  });
}

export interface GetNodeOptions {
  gatewayId?: string;
  signal?: AbortSignal;
}

/**
 * Fetches a single node's health summary by numeric or string ID.
 * Queries GET /api/v1/nodes scoped by optional gatewayId with pagination support.
 * Normalizes missing RF fields to null and preserves verified identity.
 */
export async function getNode(
  nodeId: number | string,
  optionsOrGatewayId?: string | GetNodeOptions
): Promise<NodeSummary | null> {
  const numericId = typeof nodeId === "number" ? nodeId : parseInt(String(nodeId).replace(/\D/g, "") || "0", 10);
  if (isNaN(numericId) || numericId <= 0) {
    return null;
  }

  let gatewayId: string | undefined;
  let signal: AbortSignal | undefined;

  if (typeof optionsOrGatewayId === "string") {
    gatewayId = optionsOrGatewayId.trim() || undefined;
  } else if (optionsOrGatewayId) {
    gatewayId = optionsOrGatewayId.gatewayId?.trim() || undefined;
    signal = optionsOrGatewayId.signal;
  }

  try {
    let cursor: string | undefined = undefined;
    const maxPages = 10;
    for (let pageNum = 0; pageNum < maxPages; pageNum++) {
      const page = await getNodes(
        {
          limit: 100,
          cursor,
          gateway_id: gatewayId,
        },
        { signal }
      );

      if (!page || !Array.isArray(page.items)) {
        return null;
      }

      const found = page.items.find((n) => {
        if (n.node_id !== numericId) return false;
        if (gatewayId && n.gateway_id && n.gateway_id !== gatewayId) return false;
        return true;
      });

      if (found) {
        return {
          ...found,
          last_rssi_dbm: found.last_rssi_dbm !== undefined ? found.last_rssi_dbm : null,
          last_snr_db: found.last_snr_db !== undefined ? found.last_snr_db : null,
          last_rf_at: found.last_rf_at ?? null,
          rf_age_seconds: found.rf_age_seconds ?? null,
          rf_source: found.rf_source ?? null,
          rf_stale: found.rf_stale ?? null,
        };
      }

      if (!page.next_cursor || page.items.length === 0) {
        break;
      }
      cursor = page.next_cursor;
    }

    return null;
  } catch {
    // Return null on error so UI can present fallback gracefully
    return null;
  }
}

/**
 * Fetches all pending node join requests awaiting user approval via GET /api/v1/devices/requests.
 */
export async function getDeviceJoinRequests(): Promise<DeviceJoinRequestDTO[]> {
  try {
    const list = await apiFetch<DeviceJoinRequestDTO[]>("/api/v1/devices/requests", {
      method: "GET",
    });
    return list || [];
  } catch {
    return [];
  }
}

/**
 * Approves a node join request and assigns an ID via POST /api/v1/devices/requests/{id}/approve.
 */
export async function approveDeviceJoinRequest(
  id: number,
  requestedNodeId?: number
): Promise<DeviceJoinRequestDTO> {
  return apiFetch<DeviceJoinRequestDTO>(`/api/v1/devices/requests/${id}/approve`, {
    method: "POST",
    body: JSON.stringify(requestedNodeId ? { node_id: requestedNodeId } : {}),
  });
}

/**
 * Rejects a node join request via POST /api/v1/devices/requests/{id}/reject.
 */
export async function rejectDeviceJoinRequest(id: number): Promise<{ status: string; id: number }> {
  return apiFetch<{ status: string; id: number }>(`/api/v1/devices/requests/${id}/reject`, {
    method: "POST",
  });
}

/**
 * Deletes / removes a node from topology, schedule slots, and health/device registry via DELETE /api/v1/nodes/{node_id}.
 */
export async function deleteNode(nodeId: number | string): Promise<void> {
  const cleanId = typeof nodeId === "number" ? nodeId : nodeId.trim();
  await apiFetch<{ status: string; node_id: string | number }>(`/api/v1/nodes/${cleanId}`, {
    method: "DELETE",
  });
}

