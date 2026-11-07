import type { Alert, AlertSeverity, AlertAckStatus, PageResponse } from "@/types/api";
import { apiFetch } from "./client.ts";

export interface ListAlertsParams {
  limit?: number;
  cursor?: string;
  severity?: AlertSeverity;
  node_id?: number;
  gateway_id?: string;
  ack_status?: AlertAckStatus;
}

/**
 * Lists triggered edge violation alerts via GET /api/v1/alerts.
 * Supports pagination, severity filtering, and status filtering.
 */
export async function getAlerts(params?: ListAlertsParams): Promise<PageResponse<Alert>> {
  return apiFetch<PageResponse<Alert>>("/api/v1/alerts", {
    method: "GET",
    params: params
      ? {
          limit: params.limit,
          cursor: params.cursor,
          severity: params.severity,
          node_id: params.node_id,
          gateway_id: params.gateway_id,
          ack_status: params.ack_status,
        }
      : undefined,
  });
}

/**
 * Acknowledges a triggered alert via POST /api/v1/alerts/{alert_id}/acknowledge.
 * Falls back to /api/v1/alerts/{alert_id}/ack if needed.
 * Strictly enforced by backend RBAC (OPERATOR and ADMIN only).
 */
export async function acknowledgeAlert(
  alertId: string,
  acknowledgedBy?: string
): Promise<Alert> {
  const payload = acknowledgedBy ? { acknowledged_by: acknowledgedBy } : {};
  try {
    return await apiFetch<Alert>(`/api/v1/alerts/${alertId}/acknowledge`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch (err) {
    // If backend uses /ack instead of /acknowledge
    if (err && typeof err === "object" && "status" in err && (err as { status: number }).status === 404) {
      return await apiFetch<Alert>(`/api/v1/alerts/${alertId}/ack`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    throw err;
  }
}
