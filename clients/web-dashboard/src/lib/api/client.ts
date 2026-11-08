import type { ApiError } from "@/types/api";

export class ApiClientError extends Error {
  public status: number;
  public code: string;
  public details?: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/**
 * Resolves the Backend REST API base URL.
 * Defaults to http://localhost:8080 for local development.
 * If accessed via localhost, always targets localhost backend to avoid WSL2 host loopback drops.
 */
export function getApiBaseUrl(): string {
  let backendPort = "8080";
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) {
    try {
      const parsed = new URL(process.env.NEXT_PUBLIC_API_URL);
      if (parsed.port) {
        backendPort = parsed.port;
      }
    } catch {
      // ignore
    }
  }

  if (typeof window !== "undefined" && window.location) {
    if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
      return `${window.location.protocol}//${window.location.hostname}:${backendPort}`;
    }
  }
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL.replace(/\/+$/, "");
  }
  if (typeof window !== "undefined" && window.location) {
    return `${window.location.protocol}//${window.location.hostname}:${backendPort}`;
  }
  return `http://localhost:${backendPort}`;
}

/**
 * Retrieves the stored JWT access token from localStorage safely.
 */
export function getStoredToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem("access_token");
}

/**
 * Removes auth session tokens from storage and dispatches logout event.
 */
export function clearAuthSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("access_token");
  localStorage.removeItem("user_role");
  window.dispatchEvent(new CustomEvent("auth:unauthorized"));
}

export interface RequestOptions extends RequestInit {
  skipAuth?: boolean;
  params?: Record<string, string | number | boolean | null | undefined>;
}

/**
 * Standardized HTTP fetch wrapper for Backend Go REST API endpoints.
 * - Injects Authorization: Bearer <token>
 * - Intercepts 401 Unauthorized to trigger auth reset and redirection
 * - Parses and throws ApiClientError on HTTP error status codes
 * - Zero Secret Leakage: never logs token credentials or authorization headers.
 */
export async function apiFetch<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { skipAuth = false, params, ...fetchOptions } = options;
  const baseUrl = getApiBaseUrl();

  let urlPath = path.startsWith("/") ? path : `/${path}`;
  if (params) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    }
    const queryString = searchParams.toString();
    if (queryString) {
      urlPath += (urlPath.includes("?") ? "&" : "?") + queryString;
    }
  }

  const fullUrl = `${baseUrl}${urlPath}`;

  const headers = new Headers(fetchOptions.headers || {});
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  // Auto-attach Bearer token if not skipped
  if (!skipAuth) {
    const token = getStoredToken();
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  // Auto-set Content-Type for JSON payloads if body is an object string
  if (fetchOptions.body && typeof fetchOptions.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(fullUrl, {
      ...fetchOptions,
      headers,
    });
  } catch (networkError) {
    throw new ApiClientError(
      0,
      "NETWORK_ERROR",
      networkError instanceof Error ? networkError.message : "Failed to connect to backend server"
    );
  }

  // Handle 401 Unauthorized
  if (response.status === 401) {
    clearAuthSession();
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    let errorData: ApiError | null = null;
    try {
      errorData = await response.json();
    } catch {
      // ignore JSON parse error
    }
    throw new ApiClientError(
      401,
      errorData?.code || "UNAUTHORIZED",
      errorData?.message || "Phiên đăng nhập đã hết hạn hoặc không hợp lệ. Vui lòng đăng nhập lại."
    );
  }

  // Handle 403 Forbidden
  if (response.status === 403) {
    let errorData: ApiError | null = null;
    try {
      errorData = await response.json();
    } catch {
      // ignore JSON parse error
    }
    throw new ApiClientError(
      403,
      errorData?.code || "FORBIDDEN",
      errorData?.message || "Bạn không có quyền thực hiện hành động này (Quyền hạn không hợp lệ)."
    );
  }

  // Handle non-2xx responses
  if (!response.ok) {
    let errorData: ApiError | null = null;
    try {
      errorData = await response.json();
    } catch {
      // ignore JSON parse error
    }
    throw new ApiClientError(
      response.status,
      errorData?.code || "HTTP_ERROR",
      errorData?.message || `Request failed with status ${response.status}`,
      errorData?.details
    );
  }

  // 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  try {
    return await response.json();
  } catch {
    throw new ApiClientError(
      response.status,
      "JSON_PARSE_ERROR",
      "Failed to parse server response as JSON"
    );
  }
}
