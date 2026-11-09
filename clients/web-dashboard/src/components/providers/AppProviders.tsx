"use client";

import React from "react";
import { AuthProvider } from "@/lib/auth/AuthContext";
import { RealtimeProvider } from "@/lib/realtime/RealtimeContext";
import { ThemeProvider } from "./ThemeProvider";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>
        <RealtimeProvider>{children}</RealtimeProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
