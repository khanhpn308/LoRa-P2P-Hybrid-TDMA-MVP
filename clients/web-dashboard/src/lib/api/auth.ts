import type { LoginRequest, TokenResponse, WsTicketResponse } from "@/types/api";
import { apiFetch } from "./client.ts";

/**
 * Authenticates user credentials via POST /api/v1/auth/login (ADR-0005).
 * Returns access token, token type, expiry duration, and RBAC role.
 */
export async function login(credentials: LoginRequest): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    skipAuth: true,
    body: JSON.stringify(credentials),
  });
}

/**
 * Requests an atomic, single-use WebSocket handshake ticket via POST /api/v1/auth/ws-ticket (ADR-0005).
 * Ticket expires in 30 seconds and is consumed on upgrade handshake.
 */
export async function getWsTicket(): Promise<WsTicketResponse> {
  return apiFetch<WsTicketResponse>("/api/v1/auth/ws-ticket", {
    method: "POST",
  });
}
