"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { User, UserRole, LoginRequest, TokenResponse } from "@/types/api";
import { login as apiLogin } from "@/lib/api/auth";

interface AuthContextType {
  user: User | null;
  token: string | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginRequest) => Promise<TokenResponse>;
  logout: () => void;
  hasRole: (allowedRoles: UserRole[]) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function parseJwtClaims(token: string): { sub?: string; username?: string; role?: UserRole } | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const base64Url = parts[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(null);
  const [role, setRole] = useState<UserRole | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const initAuth = useCallback(() => {
    if (typeof window === "undefined") {
      setIsLoading(false);
      return;
    }

    const storedToken = localStorage.getItem("access_token");
    const storedRole = localStorage.getItem("user_role") as UserRole | null;

    if (storedToken) {
      setToken(storedToken);
      const claims = parseJwtClaims(storedToken);
      const resolvedRole = (claims?.role || storedRole || "VIEWER") as UserRole;
      setRole(resolvedRole);

      setUser({
        id: claims?.sub || "user-session",
        username: claims?.username || "authenticated_user",
        role: resolvedRole,
        is_active: true,
        created_at: new Date().toISOString(),
      });
    } else {
      setToken(null);
      setRole(null);
      setUser(null);
    }
    setIsLoading(false);
  }, []);

  useEffect(() => {
    initAuth();

    const handleUnauthorized = () => {
      logout();
    };

    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () => {
      window.removeEventListener("auth:unauthorized", handleUnauthorized);
    };
  }, [initAuth]);

  const login = async (credentials: LoginRequest): Promise<TokenResponse> => {
    setIsLoading(true);
    try {
      const resp = await apiLogin(credentials);

      localStorage.setItem("access_token", resp.access_token);
      localStorage.setItem("user_role", resp.role);

      setToken(resp.access_token);
      setRole(resp.role);

      const claims = parseJwtClaims(resp.access_token);
      setUser({
        id: claims?.sub || "user-session",
        username: claims?.username || credentials.username,
        role: resp.role,
        is_active: true,
        created_at: new Date().toISOString(),
      });

      return resp;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("user_role");
    }
    setToken(null);
    setRole(null);
    setUser(null);
  };

  const hasRole = (allowedRoles: UserRole[]): boolean => {
    if (!role) return false;
    return allowedRoles.includes(role);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        role,
        isAuthenticated: !!token,
        isLoading,
        login,
        logout,
        hasRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
