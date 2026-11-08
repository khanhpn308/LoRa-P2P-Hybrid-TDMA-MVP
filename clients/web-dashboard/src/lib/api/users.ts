import type { User, CreateUserRequest } from "@/types/api";
import { apiFetch } from "./client.ts";

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
