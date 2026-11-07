import type {
  ScheduleSummary,
  ScheduleReviewRequest,
  ScheduleActivationRequest,
} from "@/types/api";
import { apiFetch } from "./client.ts";

/**
 * Fetches a generated TDMA schedule via GET /api/v1/gateways/{gw_id}/schedules/{schedule_id}.
 */
export async function getSchedule(
  gwId: string,
  scheduleId: string
): Promise<ScheduleSummary> {
  return apiFetch<ScheduleSummary>(
    `/api/v1/gateways/${gwId}/schedules/${scheduleId}`,
    {
      method: "GET",
    }
  );
}

/**
 * Reviews (APPROVE/REJECT) a staged TDMA schedule via POST /api/v1/gateways/{gw_id}/schedules/{schedule_id}/review.
 * Role: ADMIN or OPERATOR.
 */
export async function reviewSchedule(
  gwId: string,
  scheduleId: string,
  req: ScheduleReviewRequest
): Promise<void> {
  return apiFetch<void>(
    `/api/v1/gateways/${gwId}/schedules/${scheduleId}/review`,
    {
      method: "POST",
      body: JSON.stringify(req),
    }
  );
}

/**
 * Requests activation of an approved schedule via POST /api/v1/gateways/{gw_id}/schedules/{schedule_id}/activation-requests.
 * Role: ADMIN.
 */
export async function requestScheduleActivation(
  gwId: string,
  scheduleId: string,
  req: ScheduleActivationRequest
): Promise<void> {
  return apiFetch<void>(
    `/api/v1/gateways/${gwId}/schedules/${scheduleId}/activation-requests`,
    {
      method: "POST",
      body: JSON.stringify(req),
    }
  );
}

/**
 * Convenience helper to list known or recent schedules.
 */
export async function getSchedules(): Promise<ScheduleSummary[]> {
  try {
    return await apiFetch<ScheduleSummary[]>("/api/v1/schedules", {
      method: "GET",
    });
  } catch {
    // If endpoint is not exposed as a collection in MVP, return empty list
    return [];
  }
}
