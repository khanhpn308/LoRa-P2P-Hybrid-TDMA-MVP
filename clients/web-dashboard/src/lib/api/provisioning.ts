import type { DeviceProvisionRequest, DeviceProvisionResponse } from "@/types/api";
import { apiFetch } from "./client.ts";

/**
 * Provisions a new LoRa node with its root join key (K_JOIN) via POST /api/v1/devices/provision.
 * Authority: OpenAPI 3.0.3, Issue #242.
 * Role: ADMIN only.
 */
export async function provisionDevice(
  req: DeviceProvisionRequest
): Promise<DeviceProvisionResponse> {
  return apiFetch<DeviceProvisionResponse>("/api/v1/devices/provision", {
    method: "POST",
    body: JSON.stringify(req),
  });
}
