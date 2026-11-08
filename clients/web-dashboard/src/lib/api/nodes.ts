import type { NodeSummary, PageResponse } from "@/types/api";
import { apiFetch } from "./client.ts";

export interface ListNodesParams {
  limit?: number;
  cursor?: string;
  gateway_id?: string;
}

/**
 * Fetches the confirmed list of nodes reporting health via GET /api/v1/nodes.
 * Conforms to OpenAPI 3.0.3 and Event-Only V2 architecture.
 */
export async function getNodes(params?: ListNodesParams): Promise<PageResponse<NodeSummary>> {
  return apiFetch<PageResponse<NodeSummary>>("/api/v1/nodes", {
    method: "GET",
    params: params
      ? {
          limit: params.limit,
          cursor: params.cursor,
          gateway_id: params.gateway_id,
        }
      : undefined,
  });
}

/**
 * Fetches a single node's health summary by numeric or string ID.
 * Queries GET /api/v1/nodes and matches by node_id.
 */
export async function getNode(nodeId: number | string): Promise<NodeSummary | null> {
  const numericId = typeof nodeId === "number" ? nodeId : parseInt(nodeId.replace(/^N-?0*/, ""), 10);
  try {
    const page = await getNodes({ limit: 100 });
    const found = page.items.find((n) => n.node_id === numericId);
    return found || null;
  } catch {
    // Return null on error so UI can present fallback gracefully
    return null;
  }
}
