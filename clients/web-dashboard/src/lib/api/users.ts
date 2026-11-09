import type { User, CreateUserRequest, UserRole } from "@/types/api";
import { apiFetch } from "./client.ts";

export interface UpdateUserPayload {
  full_name?: string;
  email?: string;
  role?: UserRole;
  is_active?: boolean;
}

/**
 * Fetches all registered users via GET /api/v1/users.
 */
export async function getUsers(): Promise<User[]> {
  return apiFetch<User[]>("/api/v1/users", {
    method: "GET",
  });
}

/**
 * Fetches a single user by ID or username via GET /api/v1/users/{id}.
 */
export async function getUser(idOrUsername: string): Promise<User> {
  return apiFetch<User>(`/api/v1/users/${encodeURIComponent(idOrUsername)}`, {
    method: "GET",
  });
}

/**
 * Creates a new user with direct password setup via POST /api/v1/users.
 */
export async function createUser(payload: CreateUserRequest): Promise<User> {
  return apiFetch<User>("/api/v1/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Updates an existing user's information, role, or active status via PATCH /api/v1/users/{id}.
 */
export async function updateUser(idOrUsername: string, payload: UpdateUserPayload): Promise<User> {
  return apiFetch<User>(`/api/v1/users/${encodeURIComponent(idOrUsername)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/**
 * Updates an existing user's active status via updateUser.
 */
export async function updateUserStatus(idOrUsername: string, isActive: boolean): Promise<User> {
  return updateUser(idOrUsername, { is_active: isActive });
}

/**
 * Updates an existing user's RBAC role via updateUser.
 */
export async function updateUserRole(idOrUsername: string, role: UserRole): Promise<User> {
  return updateUser(idOrUsername, { role });
}

/**
 * Resets or updates a user's password via PUT /api/v1/users/{id}/password.
 */
export async function resetUserPassword(idOrUsername: string, newPassword: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/api/v1/users/${encodeURIComponent(idOrUsername)}/password`, {
    method: "PUT",
    body: JSON.stringify({ password: newPassword }),
  });
}
