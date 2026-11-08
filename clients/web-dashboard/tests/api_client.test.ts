import { test, describe, beforeEach, mock } from "node:test";
import assert from "node:assert/strict";
import {
  apiFetch,
  ApiClientError,
  getApiBaseUrl,
  getStoredToken,
  clearAuthSession,
} from "../src/lib/api/client.ts";

describe("HTTP API Client & Security Interceptor", () => {
  beforeEach(() => {
    mock.restoreAll();
  });

  test("getApiBaseUrl defaults to http://localhost:8080 when env not set", () => {
    const url = getApiBaseUrl();
    assert.ok(url.startsWith("http://"));
  });

  test("getStoredToken and clearAuthSession manage credentials", () => {
    let storageKey: string | null = "initial-token";
    (globalThis as unknown as { window: unknown }).window = {
      location: { pathname: "/nodes", href: "/nodes" },
      dispatchEvent: () => true,
    };
    (globalThis as unknown as { localStorage: unknown }).localStorage = {
      getItem: () => storageKey,
      removeItem: () => {
        storageKey = null;
      },
      setItem: () => {},
    };

    assert.strictEqual(getStoredToken(), "initial-token");
    clearAuthSession();
    assert.strictEqual(storageKey, null);
  });

  test("apiFetch attaches Authorization: Bearer <token> when available", async () => {
    const mockToken = "test-bearer-token-xyz123";
    let capturedAuth: string | null = null;

    (globalThis as unknown as { window: unknown }).window = {
      location: { pathname: "/nodes", href: "/nodes" },
      dispatchEvent: () => true,
    };
    (globalThis as unknown as { localStorage: unknown }).localStorage = {
      getItem: (key: string) => (key === "access_token" ? mockToken : null),
      setItem: () => {},
      removeItem: () => {},
    };

    globalThis.fetch = async (_input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      capturedAuth = headers.get("Authorization");
      return new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    const resp = await apiFetch<{ status: string }>("/api/v1/healthz");
    assert.strictEqual(resp.status, "ok");
    assert.strictEqual(capturedAuth, `Bearer ${mockToken}`);
  });

  test("apiFetch intercepts 401 Unauthorized and clears session", async () => {
    let cleared = false;
    (globalThis as unknown as { localStorage: unknown }).localStorage = {
      getItem: () => "expired-token",
      removeItem: (k: string) => {
        if (k === "access_token") cleared = true;
      },
      setItem: () => {},
    };
    (globalThis as unknown as { window: unknown }).window = {
      location: { pathname: "/nodes", href: "/nodes" },
      dispatchEvent: () => true,
    };

    globalThis.fetch = async () => {
      return new Response(JSON.stringify({ code: "UNAUTHORIZED", message: "invalid token" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    };

    await assert.rejects(
      async () => {
        await apiFetch("/api/v1/alerts");
      },
      (err: unknown) => {
        assert.ok(err instanceof ApiClientError);
        assert.strictEqual(err.status, 401);
        assert.strictEqual(err.code, "UNAUTHORIZED");
        return true;
      }
    );

    assert.strictEqual(cleared, true);
  });

  test("apiFetch throws 403 Forbidden on insufficient permissions", async () => {
    globalThis.fetch = async () => {
      return new Response(JSON.stringify({ code: "FORBIDDEN", message: "insufficient role permissions" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    };

    await assert.rejects(
      async () => {
        await apiFetch("/api/v1/devices/provision", { method: "POST" });
      },
      (err: unknown) => {
        assert.ok(err instanceof ApiClientError);
        assert.strictEqual(err.status, 403);
        assert.strictEqual(err.code, "FORBIDDEN");
        return true;
      }
    );
  });
});
